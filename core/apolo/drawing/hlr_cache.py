"""Las proyecciones HLR de una escena, calculadas FUERA de `STATE_LOCK` y guardadas por la
identidad de sus formas (plan visor-para-evaluar D6–D8).

El HLR de OCCT (`project_to_viewport`) es lo caro de una lámina: en el banco de 369 piezas,
~70 s por vista. Una pasada da las aristas visibles Y las ocultas, así que aquí se guardan las
dos y «líneas ocultas» sólo filtra; la tabla BOM quita una vista, no la recalcula. El corte es
otra pasada geométrica y tiene su propia entrada.

Coreografía (la del llamador, la API):
  1. bajo `STATE_LOCK`: `p = pedido(scene, vistas, corte)`; si `p.falta`, `p.copiar()` pasa las
     formas visibles a bytes BinTools: el cálculo no comparte ni una cara con el documento vivo,
     que otro hilo puede teselar (BRepMesh escribe en la cara);
  2. FUERA de todo lock del documento, con `HLR_LOCK`: `p.calcular(avance)`, cada vista en SU
     proceso (`hlr_worker.py`: el HLR de OCCT no suelta el GIL y en un hilo congelaba la API
     entera), a la vez; se guarda bajo la clave de las formas ORIGINALES;
  3. bajo `STATE_LOCK` otra vez: `compose_sheet` llama a `project_views`/`section_projection`,
     que LEEN la caché (`vistas`, `corte`) y sólo calculan lo que no esté (como siempre).

Sólo `guardar` llena la caché: las láminas por pieza del juego y la explosionada (escenas
sintéticas, formas nuevas en cada llamada) leen y no la ensucian. Regla de `core/apolo`: la caché
por `id(shape)` guarda la REFERENCIA y verifica `is` (Python recicla los ids). Lock HOJA.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from typing import Callable

#: UNA pasada HLR a la vez (OCCT no es reentrante en el mismo algoritmo y la máquina tiene que
#: seguir atendiendo); nunca se toma `STATE_LOCK` con él tomado.
HLR_LOCK = threading.Lock()

#: Las vistas de la lámina de conjunto: se calculan las cuatro aunque la tabla BOM o el corte
#: oculten una, para que prender o apagar una casilla nunca pida otra pasada (D7).
VISTAS_BASE = ("alzado", "planta", "lateral", "iso")

TOPE = 4  # escenas retenidas (cada una guarda sus polilíneas: unos MB a 400 piezas)

_LOCK = threading.Lock()


@dataclass
class _Entrada:
    formas: tuple  # las formas ORIGINALES (referencias: el `is` del lookup)
    vistas: dict = field(default_factory=dict)  # nombre → ViewProjection con las ocultas
    cortes: dict = field(default_factory=dict)  # (eje, offset) → (proy, [(fid, anillos)], cut, eje)


_CACHE: OrderedDict[tuple, _Entrada] = OrderedDict()


def _visibles(scene: dict) -> list[tuple[str, object]]:
    return [(fid, f.shape) for fid, f in scene.items() if getattr(f, "visible", True)]


def clave(scene: dict) -> tuple[tuple, tuple]:
    """(clave, formas): la clave es (fid, id(forma)) de lo visible, en orden."""
    vis = _visibles(scene)
    return tuple((fid, id(s)) for fid, s in vis), tuple(s for _, s in vis)


def _entrada(scene: dict) -> _Entrada | None:
    k, formas = clave(scene)
    with _LOCK:
        e = _CACHE.get(k)
        if e is None or len(e.formas) != len(formas) or any(a is not b for a, b in zip(e.formas, formas)):
            return None
        _CACHE.move_to_end(k)
        return e


def filtrar(proj, include_hidden: bool):
    """La proyección como la habría dado `project_views(include_hidden)`: sin ocultas, los
    límites salen sólo de lo visible (el mismo cálculo de siempre)."""
    if include_hidden:
        return replace(proj, visible=list(proj.visible), hidden=list(proj.hidden), circles=list(proj.circles))
    out = replace(proj, visible=list(proj.visible), hidden=[], circles=list(proj.circles), bounds=(0, 0, 0, 0))
    xs = [x for poly in out.visible for x, _ in poly]
    ys = [y for poly in out.visible for _, y in poly]
    if xs:
        out.bounds = (min(xs), min(ys), max(xs), max(ys))
    return out


def vistas(scene: dict, nombres: list[str], include_hidden: bool) -> dict | None:
    """Las vistas pedidas desde la caché, o None si falta alguna."""
    e = _entrada(scene)
    if e is None or any(n not in e.vistas for n in nombres):
        return None
    return {n: filtrar(e.vistas[n], include_hidden) for n in nombres}


def corte(scene: dict, eje: str, offset, include_hidden: bool):
    """(proy, [(fid, anillos)], cut, eje) del corte desde la caché, o None."""
    e = _entrada(scene)
    hit = None if e is None else e.cortes.get((eje, offset))
    if hit is None:
        return None
    proj, polys, cut, axis = hit
    return filtrar(proj, include_hidden), polys, cut, axis


def guardar(formas_de: dict, vistas_calc: dict, cortes_calc: dict) -> None:
    """Guarda lo calculado bajo la clave de la escena ORIGINAL (`formas_de`: fid → forma)."""
    k = tuple((fid, id(s)) for fid, s in formas_de.items())
    formas = tuple(formas_de.values())
    with _LOCK:
        e = _CACHE.get(k)
        if e is None or any(a is not b for a, b in zip(e.formas, formas)):
            e = _Entrada(formas=formas)
            _CACHE[k] = e
        e.vistas.update(vistas_calc)
        e.cortes.update(cortes_calc)
        _CACHE.move_to_end(k)
        while len(_CACHE) > TOPE:
            _CACHE.popitem(last=False)


def vaciar() -> None:
    with _LOCK:
        _CACHE.clear()


@dataclass
class Pedido:
    """Lo que falta proyectar de una escena: se arma y se serializa bajo `STATE_LOCK`, se
    calcula fuera (`calcular`, en procesos aparte: `hlr_worker.py`) y queda en la caché."""

    formas_de: dict  # fid → forma ORIGINAL (lo visible, en orden)
    faltan: list  # vistas
    corte: tuple | None  # (eje, offset) si falta
    marco_vistas: tuple | None = None  # (centro, diagonal) de las ORIGINALES (`projection.marco`)
    caja_corte: object = None  # bbox de los sólidos ORIGINALES (`projection.caja_corte`)
    copias: list | None = None  # [(fid, bytes BinTools)]: la copia que viaja al worker

    @property
    def falta(self) -> bool:
        return bool(self.faltan or self.corte)

    @property
    def pasos(self) -> int:
        return len(self.faltan) + (1 if self.corte else 0)

    def copiar(self) -> None:
        """Bajo `STATE_LOCK`: cada forma visible a bytes BinTools (sin malla: la geometría
        exacta). Es la copia del documento que el HLR usa fuera: no comparte ni una cara."""
        from apolo.brep_io import serialize_robust

        copias = []
        for fid, s in self.formas_de.items():
            blob = serialize_robust(s.wrapped, cache_geometria=True)
            if blob is None:
                raise ValueError(f"No pudimos copiar la pieza {fid} para proyectarla.")
            copias.append((fid, blob))
        self.copias = copias

    def tareas(self) -> list[dict]:
        out = [{"tipo": "vista", "nombre": n, "marco": [list(self.marco_vistas[0]), self.marco_vistas[1]]}
               for n in self.faltan]
        if self.corte:
            bb = self.caja_corte
            out.append({"tipo": "corte", "eje": self.corte[0], "offset": self.corte[1],
                        "caja": [[bb.min.X, bb.min.Y, bb.min.Z], [bb.max.X, bb.max.Y, bb.max.Z]]})
        return out

    def calcular(self, avance: Callable[[int, int, str], None] | None = None) -> None:
        """FUERA de `STATE_LOCK`, con `HLR_LOCK`: cada vista y el corte en su proceso, a la vez
        (`hlr_proceso.correr`), y a la caché. `avance(hechas, total, que)` al empezar y cada vez
        que termina una; `que` es lo que sigue calculándose."""
        from . import hlr_proceso
        from .hlr_worker import proy_de_dict

        if self.copias is None:
            raise RuntimeError("Pedido.calcular sin copiar() antes, bajo STATE_LOCK")
        tareas = self.tareas()
        nombres = [t.get("nombre", "corte") for t in tareas]
        if avance:
            avance(0, len(tareas), nombres[0])
        resultados = hlr_proceso.correr(self.copias, tareas, avance=avance, nombres=nombres)
        vistas_calc: dict = {}
        cortes_calc: dict = {}
        for t, r in zip(tareas, resultados):
            if "error_valor" in r:
                raise ValueError(r["error_valor"])
            if t["tipo"] == "vista":
                vistas_calc[t["nombre"]] = proy_de_dict(r["vista"])
            else:
                c = r["corte"]
                polys = [(fid, [[tuple(pt) for pt in ring] for ring in rings]) for fid, rings in c["polys"]]
                cortes_calc[self.corte] = (proy_de_dict(c["proy"]), polys, c["cut"], c["axis"])
        guardar(self.formas_de, vistas_calc, cortes_calc)
        self.copias = None


def pedido(scene: dict, nombres=VISTAS_BASE, corte_de: tuple | None = None) -> Pedido:
    """Bajo `STATE_LOCK`: qué vistas (y qué corte, `(eje, offset)`) faltan en la caché."""
    formas_de = dict(_visibles(scene))
    if not formas_de:  # escena vacía: el error de siempre lo da `compose_sheet`, bajo el lock
        return Pedido(formas_de=formas_de, faltan=[], corte=None)
    e = _entrada(scene)
    faltan = [n for n in nombres if e is None or n not in e.vistas]
    falta_corte = corte_de if corte_de and (e is None or corte_de not in e.cortes) else None
    p = Pedido(formas_de=formas_de, faltan=faltan, corte=falta_corte)
    if faltan or falta_corte:
        from .projection import caja_corte, marco

        if faltan:
            p.marco_vistas = marco(list(formas_de.values()))
        if falta_corte:
            p.caja_corte = caja_corte(scene)
            if p.caja_corte is None:  # sin sólidos: el error de siempre, al componer
                p.corte = None
    return p
