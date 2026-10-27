"""La lámina de conjunto del diálogo «Planos» sin congelar Apolo (plan visor-para-evaluar D6–D11).

Coreografía de los dos locks (raíz § Concurrencia), en `lamina(op)`:
  (a) bajo `STATE_LOCK`: la firma de lo que dibuja la lámina; si ya está compuesta, sale de la
      caché. Si no, qué proyecciones HLR faltan (`drawing.hlr_cache.pedido`) y la COPIA de las
      formas visibles (`Pedido.copiar`);
  (b) FUERA de `STATE_LOCK`, con `HLR_LOCK`: el HLR sobre las copias (lo caro: ~70 s por vista a
      369 piezas), con su progreso al job (`jobs.avance`);
  (c) bajo `STATE_LOCK` otra vez: `compose_sheet`, que lee las proyecciones de la caché (cotas,
      tablas, cajetín: lo barato) y guarda la lámina bajo su firma.

Con la caché, «líneas ocultas» y «BOM» no piden otra pasada (una pasada da visibles y ocultas;
la BOM sólo quita una vista) y volver a una combinación ya vista es inmediato; el corte es otra
pasada, con su propia entrada. Las láminas viven EN MEMORIA (`LAMINAS`, lock hoja).
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from fastapi import HTTPException

from apolo.state import STATE_LOCK

from .common import ENTREGABLES_JOBS, _drawing_meta, _mismo_proyecto
from .jobs import avance
from .session import S


@dataclass(frozen=True)
class Opciones:
    """Lo que el diálogo pide: hoja y casillas (y las piezas a acotar)."""

    sheet: str = "A3"
    hidden: bool = False
    dims: tuple = ()
    section: bool = False
    bom: bool = False

    @classmethod
    def de(cls, sheet: str, hidden: bool, dims: str, section: bool, bom: bool) -> "Opciones":
        return cls(sheet, bool(hidden), tuple(s for s in (dims or "").split(",") if s), bool(section), bool(bom))


class _Laminas:
    """firma → `SheetModel` compuesto; y, por proyecto y opciones, la última lámina servida (la
    vista previa mientras se calcula la nueva, D10). Lock HOJA."""

    TOPE = 24

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._d: OrderedDict = OrderedDict()
        self._ultima: dict = {}
        self._en_curso: dict[str, str] = {}
        self._seg_por_paso: dict = {}
        self._svg: dict[str, str] = {}

    def get(self, firma: str):
        with self._lock:
            m = self._d.get(firma)
            if m is not None:
                self._d.move_to_end(firma)
            return m

    def poner(self, firma: str, modelo, clave_ultima) -> None:
        with self._lock:
            self._d[firma] = modelo
            self._d.move_to_end(firma)
            while len(self._d) > self.TOPE:
                self._d.popitem(last=False)
            self._ultima[clave_ultima] = firma
            self._ultima[("proyecto", clave_ultima[0])] = firma

    def svg(self, firma: str, texto: str | None = None) -> str | None:
        """El SVG ya armado de la lámina `firma` (con `texto`, lo guarda)."""
        with self._lock:
            if texto is not None and firma in self._d:
                self._svg[firma] = texto
                for k in [k for k in self._svg if k not in self._d]:
                    del self._svg[k]
            return self._svg.get(firma) if texto is None else texto

    def ultima(self, clave_ultima) -> str | None:
        """La firma de la última lámina compuesta con esas opciones (si no, la última del
        proyecto con cualquier opción), si sigue en la caché."""
        with self._lock:
            for k in (clave_ultima, ("proyecto", clave_ultima[0])):
                f = self._ultima.get(k)
                if f in self._d:
                    return f
            return None

    def en_curso(self, firma: str, job_id: str | None = None) -> str | None:
        with self._lock:
            if job_id is not None:
                self._en_curso[firma] = job_id
            return self._en_curso.get(firma)

    def termino(self, firma: str) -> None:
        with self._lock:
            self._en_curso.pop(firma, None)

    def medir(self, proyecto, seg_por_paso: float) -> None:
        with self._lock:
            self._seg_por_paso[proyecto] = seg_por_paso

    def estimado(self, proyecto, pasos: int) -> float | None:
        with self._lock:
            s = self._seg_por_paso.get(proyecto)
        return round(s * pasos, 1) if s and pasos else None

    def vaciar(self) -> None:
        with self._lock:
            self._d.clear()
            self._ultima.clear()
            self._en_curso.clear()
            self._seg_por_paso.clear()
            self._svg.clear()


LAMINAS = _Laminas()


def _firma(op: Opciones, meta: dict) -> str:
    """Bajo `STATE_LOCK`: lo que decide la lámina. El log (la geometría sale de él), lo que la
    escena dice de cada pieza (nombre, visibilidad, material: la BOM), las uniones (soldadura),
    el cajetín y las opciones. El color no: la lámina de líneas no lo usa."""
    doc = S.doc
    piezas = [(fid, f.name, bool(f.visible), str(getattr(f, "material", None)), f.command_id)
              for fid, f in doc.scene.items()]
    datos = [S.project_id, doc.name, doc.commands, piezas, doc.fasteners, meta, op.sheet,
             op.hidden, list(op.dims), op.section, op.bom]
    return hashlib.sha1(json.dumps(datos, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:20]


def _componer(op: Opciones, meta: dict):
    from apolo.drawing import compose_sheet

    try:
        return compose_sheet(
            S.doc.scene, sheet=op.sheet, include_hidden=op.hidden, project_name=S.doc.name,
            dims_features=list(op.dims) or None, section=op.section, bom=op.bom, meta=meta,
            fasteners=S.doc.fasteners,  # V7.2 A: símbolos de soldadura ISO 2553 (no-op sin cordones)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _pedido(op: Opciones):
    from apolo.drawing import hlr_cache

    return hlr_cache.pedido(S.doc.scene, hlr_cache.VISTAS_BASE, ("x", None) if op.section else None)


def _calcular(p, proyecto) -> None:
    """(b): el HLR fuera de `STATE_LOCK`, con su progreso; un corte que no interseca es el
    mismo 400 que daría la lámina."""
    from apolo.drawing.hlr_cache import HLR_LOCK

    def paso(hechas: int, total: int, que: str) -> None:
        avance({"hechas": hechas, "total": total, "fase": que})

    t0 = time.perf_counter()
    with HLR_LOCK:
        try:
            p.calcular(paso)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    LAMINAS.medir(proyecto, (time.perf_counter() - t0) / max(p.pasos, 1))


def precalcular(proyecto=None, vistas: tuple = ("alzado", "planta", "iso")) -> None:
    """(a)+(b) de esas vistas de conjunto, para quien compone después bajo su lock: el juego de
    planos (D12) lee su conjunto de la caché y su HLR grande sale de `STATE_LOCK`. Sólo las que
    el conjunto dibuja (con DESPIECE no hay perfil; sombreado, no hay isométrica de líneas)."""
    from apolo.drawing import hlr_cache

    with STATE_LOCK:
        _mismo_proyecto(proyecto)
        p = hlr_cache.pedido(S.doc.scene, vistas)
        if not p.falta:
            return
        p.copiar()
        pid = S.project_id
    _calcular(p, pid)


def avance_laminas(hechas: int, total: int) -> None:
    """El progreso del juego de planos: lámina `hechas` de `total` (`sheet_set(avance=)`)."""
    avance({"hechas": hechas, "total": total, "fase": "laminas"})


def lamina(op: Opciones, proyecto=None):
    """La `SheetModel` de esas opciones, con la coreografía del docstring. `proyecto` (el activo
    al encolar) se revalida en cada toma del lock: 409 si se abrió otro."""
    return _lamina(op, proyecto)[1]


def _lamina(op: Opciones, proyecto=None) -> tuple[str, object]:
    for _ in range(2):  # si el documento cambió durante el HLR, una vuelta más con lo nuevo
        with STATE_LOCK:
            _mismo_proyecto(proyecto)
            meta = _drawing_meta()
            firma = _firma(op, meta)
            modelo = LAMINAS.get(firma)
            if modelo is not None:
                return firma, modelo
            p = _pedido(op)
            if not p.falta:
                modelo = _componer(op, meta)
                LAMINAS.poner(firma, modelo, (S.project_id, op))
                return firma, modelo
            p.copiar()
            pid = S.project_id
        _calcular(p, pid)
    with STATE_LOCK:  # el documento no se quedó quieto: se compone con lo que haya (como antes)
        _mismo_proyecto(proyecto)
        meta = _drawing_meta()
        firma, modelo = _firma(op, meta), _componer(op, meta)
        LAMINAS.poner(firma, modelo, (S.project_id, op))
        return firma, modelo


def url(firma: str) -> str:
    return f"/api/drawing/lamina.svg?k={firma}"


def pedir(op: Opciones):
    """Lo que pide el visor (D10): la lámina ya lista (`{lista, svg}`) o un job en la cola de
    entregables con lo que se puede mostrar mientras tanto (`previa`: la última lámina de estas
    opciones, de antes de los últimos cambios) y cuánto se espera (`estimado_s`). Sin HLR que
    hacer (sólo cambió una casilla), compone en el momento: ya no hay nada caro."""
    with STATE_LOCK:
        meta = _drawing_meta()
        firma = _firma(op, meta)
        pid = S.project_id
        if LAMINAS.get(firma) is None:
            p = _pedido(op)
            if not p.falta:
                LAMINAS.poner(firma, _componer(op, meta), (pid, op))
        if LAMINAS.get(firma) is not None:
            return {"lista": True, "svg": url(firma)}
        pasos = p.pasos
    previa = LAMINAS.ultima((pid, op))
    job = LAMINAS.en_curso(firma)
    if job is None or ENTREGABLES_JOBS.get(job) is None or ENTREGABLES_JOBS.get(job)["estado"] in ("ok", "error"):
        def trabajo():
            try:
                return {"svg": url(_lamina(op, pid)[0])}
            finally:
                LAMINAS.termino(firma)

        job = ENTREGABLES_JOBS.submit("lamina_visor", trabajo, origen="visor")
        LAMINAS.en_curso(firma, job)
    return {"lista": False, "job_id": job, "pasos": pasos,
            **({"previa": url(previa)} if previa else {}),
            **({"estimado_s": e} if (e := LAMINAS.estimado(pid, pasos)) else {})}


def svg_de(firma: str) -> str:
    """El SVG de una lámina de la caché (se arma una vez: a 369 piezas no es gratis)."""
    from apolo.drawing import sheet_to_svg

    hecho = LAMINAS.svg(firma)
    if hecho is not None:
        return hecho
    modelo = LAMINAS.get(firma)
    if modelo is None:
        raise HTTPException(status_code=404, detail=(
            "Esa lámina ya no está en memoria (el servidor se reinició o la reemplazaron otras): "
            "vuelve a abrir «Planos»."))
    return LAMINAS.svg(firma, sheet_to_svg(modelo))
