"""Rutas de cinemática: juntas, estudios de movimiento, su GIF y la exportación URDF/SDF.

Router de la API (F6b del plan `docs/plans/partir-api-main.md`): movidas tal cual desde
`main.py`. Los estudios son metadato de manifest (fuera del log); el GIF sigue el patrón
dos-locks (FK + teselado bajo `STATE_LOCK`, el bucle VTK fuera).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from apolo.doc import DocumentError
from apolo.state import STATE_LOCK

from ..common import _autosave, _remove_owner_command, _state_or_error
from ..scene import _feature_colors
from ..session import S

router = APIRouter()


@router.get("/api/kinematics")
def get_kinematics() -> dict:
    from apolo.robotics import joints_payload

    with STATE_LOCK:
        return joints_payload(S.doc)


@router.delete("/api/joints/{name}")
def delete_joint(name: str) -> dict:
    return _state_or_error(lambda: _remove_owner_command(
        S.doc.joints, name, "add_joint", f"No existe la junta '{name}'",
        "Esta junta pertenece a una plantilla (p. ej. un brazo): edita o elimina su comando"))


class MotionIn(BaseModel):
    name: str
    keyframes: list[dict] = []


class MotionDeleteIn(BaseModel):
    name: str


class ScanIn(BaseModel):
    name: str
    steps: int = 24


def _motion_studies() -> list[dict]:
    from apolo.robotics.motion import duration

    return [
        {"name": n, "keyframes": kfs, "duration": duration(kfs)}
        for n, kfs in sorted(S.doc.motion.items())
    ]


@router.get("/api/motion")
def get_motion() -> dict:
    with STATE_LOCK:
        return {"studies": _motion_studies()}


@router.put("/api/motion")
def put_motion(body: MotionIn) -> dict:
    with STATE_LOCK:
        try:
            S.doc.set_motion(body.name, body.keyframes)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _autosave()
        return {"ok": True, "studies": _motion_studies()}


@router.delete("/api/motion")
def delete_motion(body: MotionDeleteIn) -> dict:
    with STATE_LOCK:
        S.doc.delete_motion(body.name)
        _autosave()
        return {"ok": True, "studies": _motion_studies()}


def _motion_values_or_400(name: str, kfs: list[dict]) -> None:
    """Estudio persistido sin ningún 'values' (formato viejo/mal formado): mejor un 400
    accionable que 'reproducir' un recorrido que no mueve ninguna junta."""
    if kfs and not any(k.get("values") for k in kfs):
        raise HTTPException(
            status_code=400,
            detail=(
                f"El estudio '{name}' no tiene valores de junta en ningún fotograma — "
                'formato: {"t": segundos, "values": {junta: valor}}. Reescríbelo con '
                "PUT /api/motion."
            ),
        )


@router.post("/api/motion/scan")
def scan_motion(body: ScanIn) -> dict:
    from apolo.robotics.motion import scan_collisions

    with STATE_LOCK:
        kfs = S.doc.motion.get(body.name, [])
        _motion_values_or_400(body.name, kfs)
        return {"colisiones": scan_collisions(S.doc, kfs, body.steps)}


class MotionGifIn(BaseModel):
    name: str
    steps: int = 48          # intervalos del recorrido (steps+1 fotogramas)
    fps: int = 12
    pingpong: bool = False   # añade la vuelta → el bucle no salta al reiniciar
    view: str = "iso"
    azimuth: float | None = None
    elevation: float | None = None
    zoom: float = 1.0
    size_px: int = 720
    edges: bool = True


@router.post("/api/motion.gif")
def motion_gif(body: MotionGifIn) -> Response:
    """GIF animado de un estudio de movimiento CON NOMBRE: interpola las juntas a lo largo
    del recorrido y pinta cada fotograma con el MISMO motor VTK que `render_view`, con la
    cámara FIJA a todo el recorrido (si no, el encuadre 'respira' al moverse el mecanismo).
    Espejo de `/api/physics/drop.gif` pero para cinemática, no para física."""
    from apolo.robotics.anim import extract_motion_frames, render_motion_gif

    with STATE_LOCK:  # FASE OCCT: FK + teselado → snapshots de datos PUROS
        kfs = S.doc.motion.get(body.name)
        if not kfs:
            disponibles = ", ".join(sorted(S.doc.motion)) or "ninguno"
            raise HTTPException(
                status_code=404,
                detail=f"No existe el estudio de movimiento '{body.name}' (hay: {disponibles})",
            )
        _motion_values_or_400(body.name, kfs)
        try:
            snaps = extract_motion_frames(
                S.doc, kfs, steps=body.steps, pingpong=body.pingpong,
                view=body.view, azimuth=body.azimuth, elevation=body.elevation,
                zoom=body.zoom, size_px=body.size_px, colors=_feature_colors(),
                edges=body.edges,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    # FUERA de STATE_LOCK: el bucle VTK (lo lento) corre bajo RENDER_LOCK
    try:
        gif = render_motion_gif(snaps, fps=body.fps)
    except RuntimeError as exc:  # sin Pillow
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL u otro fallo VTK
        raise HTTPException(status_code=503, detail=f"El render VTK falló: {exc}") from exc
    return Response(content=gif, media_type="image/gif")


def _robot_export(builder) -> bytes:
    with STATE_LOCK:
        try:
            return builder(S.doc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/export/urdf")
def export_urdf() -> Response:
    from apolo.robotics import export_urdf_zip

    data = _robot_export(export_urdf_zip)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "robot"}-urdf.zip"'},
    )


@router.get("/api/export/sdf")
def export_sdf() -> Response:
    from apolo.robotics import export_sdf_zip

    data = _robot_export(export_sdf_zip)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "robot"}-sdf.zip"'},
    )
