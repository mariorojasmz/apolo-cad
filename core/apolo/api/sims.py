"""Simulaciones físicas de la API (MuJoCo): gravedad sobre la máquina, drop-test, dinámica y la
serie de la marcha que reproduce el visor (con su caché en memoria, `MARCHAS`).

Movido tal cual desde `main.py` (F6a del plan `docs/plans/partir-api-main.md`). Patrón
dos-locks (V6.2c): bajo `STATE_LOCK` se EXTRAE la geometría (grafo de sujeción, cascos, AABB) a
un snapshot de datos puros; el bucle de integración corre FUERA, bajo `PHYSICS_LOCK`. Lo usan
los endpoints de ensamblaje y física y la puerta de entrega (gravedad opt-in).
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from collections import OrderedDict

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from apolo.state import STATE_LOCK

from .common import PHYSICS_LOCK
from .session import S


class StabilityIn(BaseModel):
    seconds: float = 2.0
    gravity: float = 9.81
    fps: int = 12
    with_autodetect: bool = False
    exclude: list[str] = []  # piezas a tratar como NO sujetas ("¿y si le falta el tornillo?")
    include_frames: bool = False  # incluir las poses por fotograma (para animar en el viewport)


def _stability(body: StabilityIn) -> dict:
    """Dos-locks (V6.2c): (a) STATE_LOCK extrae la geometría (grafo de sujeción + cascos
    convexos) → snapshot PURO; (b) PHYSICS_LOCK corre el bucle MuJoCo FUERA del lock del
    doc → una gravedad de varios segundos no congela las mutaciones/lecturas del server."""
    from apolo.physics import PhysicsError
    from apolo.physics.stability import prepare_stability, simulate_stability

    try:
        with STATE_LOCK:
            snap = prepare_stability(
                S.doc.scene, S.doc.joints, S.doc.mates, S.doc.fasteners, S.doc.grounds,
                seconds=body.seconds, gravity=body.gravity, fps=body.fps,
                with_autodetect=body.with_autodetect, exclude=body.exclude,
            )
        with PHYSICS_LOCK:
            return simulate_stability(snap)
    except PhysicsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class Product(BaseModel):
    w: float
    d: float
    h: float
    mass: float | None = None
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class DropIn(BaseModel):
    products: list[Product]
    seconds: float = 2.0
    gravity: float = 9.81
    fps: int = 20


class DynamicsIn(BaseModel):
    """Simulación dinámica (V8.2 D10). Los campos son del TRANSPORTE; toda otra clave es la
    petición D3–D8 (motores, productos, sensores, bandas, juntas, duracion_s…) y va TAL CUAL a
    `physics.dinamica_peticion`, que valida cada una y rechaza la desconocida con su corrección
    (un 400 accionable, no el 422 de pydantic ni un silencio)."""

    model_config = ConfigDict(extra="allow")

    include_frames: bool = False  # poses por fotograma (para animar); el GIF va aparte
    view: str = "iso"             # sólo el .gif
    size_px: int = Field(640, ge=200, le=1600)
    max_frames: int = Field(90, ge=2, le=240)


def _dynamics(body: DynamicsIn, *, con_escena: bool = False):
    """Dos-locks (V6.2c): bajo STATE_LOCK `prepare_dynamics` hornea el MJCF (y, para el GIF,
    se tesela la escena EN LA MISMA adquisición: el dibujo es del mismo documento que la
    física); el bucle MuJoCo corre bajo PHYSICS_LOCK, fuera del lock del doc. Read-only.
    Devuelve el resultado, o `(resultado, escena)` con `con_escena`."""
    from apolo.physics import PhysicsError
    from apolo.physics.dinamica import prepare_dynamics, simulate_dynamics
    from apolo.physics.gif_dinamica import extraer_gif_dinamica
    from apolo.services.apariencia import apariencias_documento
    from apolo.services.definiciones import definiciones_de

    peticion = dict(body.model_extra or {})
    escena = None
    try:
        with STATE_LOCK:
            d = S.doc
            proyecto = S.project_id
            snap = prepare_dynamics(d.scene, d.joints, d.fasteners, d.grounds, peticion, mates=d.mates)
            if con_escena and snap.early is None:   # colores: los del viewport
                escena = extraer_gif_dinamica(d.scene, snap.piezas, d.colors,
                                              apariencias=apariencias_documento(d),
                                              definiciones=definiciones_de(d.scene))
        with PHYSICS_LOCK:
            res = simulate_dynamics(snap)
    except PhysicsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if snap.early is None:   # la última marcha del proyecto: la que el visor reproduce
        MARCHAS.recordar_escenario(proyecto, peticion)
    return (res, escena) if con_escena else res


# ------------------------------------------------- la marcha para el visor (visor-realista D4)
#: Muestras por segundo simulado de la serie del reproductor (D4).
HZ_SERIE = 50


def firma_dinamica(doc) -> str:
    """Huella de lo que decide la marcha: el log (geometría, juntas, uniones, variables) y los
    materiales (la masa). Color y ocultos no cuentan: no cambian la física."""
    texto = json.dumps([doc.commands, doc.materials], sort_keys=True, default=str)
    return hashlib.sha256(texto.encode()).hexdigest()[:20]


def clave_escenario(peticion: dict) -> str:
    """El escenario normalizado (sin `fps`: la serie lleva el suyo)."""
    esc = {k: v for k, v in peticion.items() if k != "fps"}
    return hashlib.sha256(json.dumps(esc, sort_keys=True, default=str).encode()).hexdigest()[:20]


class Marchas:
    """Caché EN MEMORIA de las series del reproductor, por (firma del documento, escenario), y
    el último escenario simulado de cada proyecto. Nunca entra al `.apolo`: se regenera
    simulando otra vez (D4). Su lock es HOJA: puede tomarse con STATE_LOCK tomado, pero dentro
    no se toma ningún otro lock ni se simula."""

    TOPE_SERIES = 4
    TOPE_PROYECTOS = 16

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._series: OrderedDict = OrderedDict()
        self._ultimo: OrderedDict = OrderedDict()

    def recordar_escenario(self, proyecto, peticion: dict) -> None:
        with self._lock:
            self._ultimo[proyecto] = copy.deepcopy(peticion)
            self._ultimo.move_to_end(proyecto)
            while len(self._ultimo) > self.TOPE_PROYECTOS:
                self._ultimo.popitem(last=False)

    def ultimo_escenario(self, proyecto) -> dict | None:
        with self._lock:
            esc = self._ultimo.get(proyecto)
            return copy.deepcopy(esc) if esc is not None else None

    def serie(self, clave: tuple) -> dict | None:
        with self._lock:
            s = self._series.get(clave)
            if s is not None:
                self._series.move_to_end(clave)
            return s

    def guardar(self, clave: tuple, serie: dict) -> None:
        with self._lock:
            self._series[clave] = serie
            self._series.move_to_end(clave)
            while len(self._series) > self.TOPE_SERIES:
                self._series.popitem(last=False)

    def vaciar(self) -> None:
        with self._lock:
            self._series.clear()
            self._ultimo.clear()


MARCHAS = Marchas()


def _extraer_visual(doc, snap) -> dict | None:
    """La faja y las cadenas del documento para dibujarlas en marcha (visor-realista D6), bajo
    el STATE_LOCK del llamador. Un fallo aquí no tumba la marcha: se dibuja sin ellas."""
    from apolo.services.marcha_visual import bandas_de_snap, extraer_marcha_visual

    if snap.early is not None:
        return None
    try:
        return extraer_marcha_visual(doc, bandas_de_snap(snap))
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _sumar_visual(serie: dict, vis: dict | None, res: dict) -> None:
    """Agrega a la serie las cadenas y fajas animables (fuera de los locks: datos puros)."""
    from apolo.library.marcha_visual import armar

    if vis is None:
        serie.update({"cadenas": [], "fajas": []})
        return
    try:
        if "error" in vis:
            raise RuntimeError(vis["error"])
        extra = armar(vis, res)
    except Exception as exc:  # noqa: BLE001
        serie.update({"cadenas": [], "fajas": []})
        serie["avisos"].append(f"La faja y las cadenas se dibujan rígidas: no se pudo armar su "
                               f"marcha ({exc})")
        return
    serie["cadenas"], serie["fajas"] = extra["cadenas"], extra["fajas"]
    serie["avisos"] += extra["avisos"]


def _serie_dinamica(peticion: dict) -> dict:
    """La serie del reproductor para `peticion` sobre el documento ACTIVO, de la caché si la
    firma del documento y el escenario coinciden; si no, simula (dos locks, como `_dynamics`) y
    la guarda. `en_cache` dice cuál de las dos fue."""
    from apolo.physics import PhysicsError
    from apolo.physics.dinamica import prepare_dynamics, simulate_dynamics
    from apolo.physics.dinamica_serie import hz_para, serie_reproduccion

    peticion = {**peticion, "fps": HZ_SERIE}
    try:
        with STATE_LOCK:
            d = S.doc
            proyecto = S.project_id
            clave = (firma_dinamica(d), clave_escenario(peticion))
            hecha = MARCHAS.serie(clave)
            if hecha is None:
                snap = prepare_dynamics(d.scene, d.joints, d.fasteners, d.grounds, peticion,
                                        mates=d.mates)
                vis = _extraer_visual(d, snap)   # misma adquisición: el mismo documento
        if hecha is not None:
            MARCHAS.recordar_escenario(proyecto, peticion)
            return {**hecha, "en_cache": True}
        hz = hz_para(snap.duracion_s, len(snap.cuerpos) + len(snap.productos), HZ_SERIE)
        if hz < HZ_SERIE:
            snap.fps = hz
            snap.avisos.append(f"La marcha se muestrea a {hz} por segundo (no {HZ_SERIE}): son "
                               "muchas cajas por mucho tiempo para el visor")
        with PHYSICS_LOCK:
            res = simulate_dynamics(snap)
    except PhysicsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    serie = serie_reproduccion(res, snap.bandas, hz=hz)   # fuera de los locks: datos puros
    _sumar_visual(serie, vis, res)
    serie["firma"], serie["escenario"] = clave
    if snap.early is None:
        MARCHAS.guardar(clave, serie)
        MARCHAS.recordar_escenario(proyecto, peticion)
    return {**serie, "en_cache": False}


def _drop(body: DropIn) -> dict:
    """Corre el drop-test sobre la escena actual (read-only). Dos-locks (V6.2c):
    STATE_LOCK hornea la escena estática (AABB, OCCT); el bucle MuJoCo corre bajo
    PHYSICS_LOCK, fuera del lock del doc. 400 si falta el motor o los datos no valen."""
    from apolo.physics import PhysicsError, prepare_drop, simulate_drop

    products = [p.model_dump() for p in body.products]
    try:
        with STATE_LOCK:
            snap = prepare_drop(S.doc.scene, products, body.seconds, body.gravity, body.fps)
        with PHYSICS_LOCK:
            return simulate_drop(snap)
    except PhysicsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
