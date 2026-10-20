"""Simulaciones físicas de la API (MuJoCo): gravedad sobre la máquina, drop-test y dinámica.

Movido tal cual desde `main.py` (F6a del plan `docs/plans/partir-api-main.md`). Patrón
dos-locks (V6.2c): bajo `STATE_LOCK` se EXTRAE la geometría (grafo de sujeción, cascos, AABB) a
un snapshot de datos puros; el bucle de integración corre FUERA, bajo `PHYSICS_LOCK`. Lo usan
los endpoints de ensamblaje y física y la puerta de entrega (gravedad opt-in).
"""

from __future__ import annotations

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

    peticion = dict(body.model_extra or {})
    escena = None
    try:
        with STATE_LOCK:
            d = S.doc
            snap = prepare_dynamics(d.scene, d.joints, d.fasteners, d.grounds, peticion, mates=d.mates)
            if con_escena and snap.early is None:   # colores: los del viewport
                escena = extraer_gif_dinamica(d.scene, snap.piezas, d.colors,
                                              apariencias=apariencias_documento(d))
        with PHYSICS_LOCK:
            res = simulate_dynamics(snap)
    except PhysicsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return (res, escena) if con_escena else res


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
