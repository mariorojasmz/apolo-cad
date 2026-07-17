"""Estudio de movimiento → GIF animado (VTK + Pillow).

Espejo de `physics/anim.py`, pero para las JUNTAS: interpola los fotogramas clave
(`motion.values_at`), posa la escena con el FK (`pose.posed_shapes`) y pinta cada
fotograma con el MISMO motor que `render_view` → la animación se ve igual que las
fotos del modelo (sombreado suave, color real por pieza).

Patrón DOS LOCKS (V6.2c): `extract_motion_frames` hace la fase OCCT (FK + teselado)
y el caller la corre bajo STATE_LOCK; devuelve snapshots de datos PUROS que
`render_motion_gif` pinta fuera, bajo RENDER_LOCK.
"""

from __future__ import annotations

import io

from ..kernel.render_vtk import RENDER_LOCK, extract_render_scene, render_snapshot_vtk
from .motion import duration, values_at
from .pose import posed_shapes

MAX_STEPS = 240


def extract_motion_frames(doc, keyframes: list[dict], *, steps: int = 48,
                          pingpong: bool = False, **render_kw) -> list:
    """FASE OCCT (el caller sostiene STATE_LOCK): un RenderSnapshot por fotograma.

    `steps` = intervalos del recorrido (steps+1 fotogramas). `pingpong` añade la
    vuelta (sin repetir los extremos) → el GIF cicla ida y vuelta sin salto.
    `render_kw` se pasa tal cual a `extract_render_scene` (view/azimuth/zoom/...).
    """
    import numpy as np

    if not keyframes:
        raise ValueError("El estudio de movimiento no tiene fotogramas clave")
    dur = duration(keyframes)
    steps = max(2, min(int(steps), MAX_STEPS))
    ts = [dur * i / steps for i in range(steps + 1)] if dur > 0 else [0.0]
    if pingpong and len(ts) > 2:
        ts = ts + ts[-2:0:-1]

    solve = None
    if getattr(doc, "constraints", None):
        from apolo.assembly.constraints import solve_constraints

        solve = solve_constraints

    snaps = []
    for t in ts:
        vals = values_at(keyframes, t)
        if solve is not None:
            vals = solve(doc.joints, doc.constraints, vals)
        shapes, _ = posed_shapes(doc, vals)
        snaps.append(extract_render_scene(doc.scene, shapes_override=shapes, **render_kw))

    # CÁMARA ÚNICA para todo el recorrido: sin esto `render_snapshot_vtk` re-encuadra
    # cada fotograma a su propio bbox y la pieza "respira"/salta al moverse el mecanismo.
    # fmins/fmaxs (caja de encuadre) manda sobre smins/smaxs → los fijamos a la UNIÓN.
    if not render_kw.get("fit_ids"):
        umins = np.min(np.array([s.smins for s in snaps]), axis=0)
        umaxs = np.max(np.array([s.smaxs for s in snaps]), axis=0)
        for s in snaps:
            s.fmins, s.fmaxs = umins, umaxs
    return snaps


def render_motion_gif(snaps: list, *, fps: int = 12) -> bytes:
    """FASE VTK (fuera de STATE_LOCK): pinta cada snapshot y ensambla el GIF. NO toca OCCT."""
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Pillow no está instalado: `pip install pillow` para el GIF") from exc

    if not snaps:
        raise ValueError("Nada que animar: el recorrido no produjo fotogramas")
    frames = []
    with RENDER_LOCK:
        for snap in snaps:
            png = render_snapshot_vtk(snap)
            frames.append(Image.open(io.BytesIO(png)).convert("RGB"))
    out = io.BytesIO()
    frames[0].save(out, format="GIF", save_all=True, append_images=frames[1:],
                   duration=max(1, int(1000 / max(1, fps))), loop=0, optimize=True)
    return out.getvalue()
