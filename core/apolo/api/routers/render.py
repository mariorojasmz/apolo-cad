"""Render de la escena (PNG) y su inverso, el píxel → pieza/cara (`pick`).

Router de la API (F6b del plan `docs/plans/partir-api-main.md`): movidas tal cual desde
`main.py`. Dos-locks del render: bajo `STATE_LOCK` sólo se EXTRAE un snapshot de datos puros; el
render VTK corre fuera, bajo `RENDER_LOCK`. `pick` usa la MISMA cámara que el render: se le
pasan los mismos parámetros que a la foto.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from apolo.state import STATE_LOCK

from ..common import _expand_ids
from ..scene import _feature_colors
from ..session import S

router = APIRouter()


@router.get("/api/pick")
def pick_endpoint(
    u: float,
    v: float,
    view: str = "iso",
    fit: str | None = None,
    zoom: float = 1.0,
    azimuth: float | None = None,
    elevation: float | None = None,
    isolate: str | None = None,
    section: str | None = None,
    roll: float = 0.0,
    pan: str | None = None,
) -> dict:
    """Píxel→3D: para el punto (u,v) NORMALIZADO [0,1] de un render (vista `view`, opcionalmente a
    ÁNGULO LIBRE `azimuth`/`elevation`, `roll`, `pan`), devuelve la feature/cara cuyo centro proyectado
    queda más cerca (snap a geometría). Usa la misma cámara que el render VTK (orto, proporciones reales).
    Pasa los MISMOS view/azimuth/elevation/roll/pan/fit/zoom/isolate/section que usaste en el render: con
    `isolate` (CSV de ids) el pick solo considera esas piezas y con `section` ∈ {x,y,z} las recorta
    igual que la foto → coherencia render↔pick. Read-only."""
    from apolo.kernel.pick import pick_point

    fit_ids = _expand_ids(fit)  # acepta NOMBRES de grupo (V5.2)
    isolate_ids = _expand_ids(isolate)
    pan_xy = None
    if pan:
        try:
            pan_xy = [float(s) for s in pan.split(",")]
            assert len(pan_xy) == 2
        except Exception as exc:
            raise HTTPException(status_code=400, detail="pan debe ser 'px,py' (dos números)") from exc
    with STATE_LOCK:
        try:
            return pick_point(
                S.doc.scene, view, u, v, fit_ids=fit_ids, zoom=zoom,
                azimuth=azimuth, elevation=elevation, isolate=isolate_ids, section=section,
                roll=roll, pan=pan_xy,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/render.png")
def render_png(
    view: str = "iso",
    highlight: str | None = None,
    show_axes: bool = False,
    show_bbox: bool = False,
    joints: str | None = None,
    fit: str | None = None,
    zoom: float = 1.0,
    proportional: bool = False,
    views: str | None = None,
    labels: bool = False,
    section: str | None = None,
    shade: bool = False,
    isolate: str | None = None,
    azimuth: float | None = None,
    elevation: float | None = None,
    vtk_only: bool = False,
    measure: str | None = None,
    edges: bool = True,
    xray: bool = False,
    roll: float = 0.0,
    pan: str | None = None,
) -> Response:
    """Render de la escena. `highlight` = CSV de ids a resaltar (el resto se atenúa);
    `shade`=true usa el COLOR real por pieza (igual que el viewport web) en vez de la paleta
    por índice → render sombreado a color, más legible para distinguir piezas.
    `isolate` = CSV de ids para renderizar SOLO esas piezas (aislado real sobre una copia de la
    escena; NO toca la visibilidad del documento). Es la forma limpia de fotografiar una pieza:
    sin ocultar/restaurar nada en vivo. Respeta la visibilidad actual (una pieza oculta no aparece).
    `show_axes` dibuja los ejes del origen; `show_bbox` la caja envolvente.
    `joints` = JSON {junta: valor} para renderizar una POSE cinemática (resuelve las
    restricciones de riel y posa el mecanismo; read-only, no muta el documento).
    `fit` = CSV de ids para encuadrar la cámara en esas piezas (primer plano);
    `zoom`>1 acerca; `proportional`=true ciñe los ejes al bbox con proporciones reales
    (recomendado para máquinas largas y bajas). `views` = CSV de vistas (≥2) para componer
    varias en una imagen; `labels`=true rotula ids; `section` ∈ {x,y,z} corta para ver dentro.
    `azimuth`/`elevation` (grados) fijan la cámara a un ÁNGULO LIBRE (anulan el preset `view`;
    override parcial); aplican a vista única (con `views`/multivista se ignoran).
    `vtk_only`=true EXIGE el motor VTK (sombreado suave): ignora multivista/etiquetas y NO cae a
    matplotlib (sin OpenGL → 503 claro). Lo usa el tool MCP `render_view` para garantizar capturas
    limpias VTK; el resto de la API conserva matplotlib (fallback/multivista/labels/plomería).
    `measure`="a,b" (dos ids) dibuja una COTA (línea + "X mm" del gap mínimo OCCT entre las dos
    piezas) ENCIMA del render (solo vía VTK; en multivista/matplotlib se ignora).
    `xray`=true (rayos-X, solo VTK): lo NO resaltado se vuelve translúcido EN SU COLOR (no oculto)
    para ver una pieza interna en su contexto sin cortar; el vidrio siempre sale translúcido.
    `labels`=true rotula el id de cada pieza sobre el render (VTK billboard en vista única; matplotlib
    en multivista). `roll` (grados) gira la cámara sobre su eje de visión; `pan`="px,py" desplaza el
    encuadre en el plano de vista (fracción de la semialtura; +px→derecha, +py→arriba) — ambos solo
    vía VTK (vista única)."""
    from apolo.kernel.render import render_scene_png

    highlight_ids = _expand_ids(highlight)  # acepta NOMBRES de grupo (V5.2)
    fit_ids = _expand_ids(fit)
    isolate_ids = _expand_ids(isolate)
    view_list = [s.strip() for s in views.split(",") if s.strip()] if views else None
    pan_xy = None
    if pan:
        try:
            pan_xy = [float(s) for s in pan.split(",")]
            assert len(pan_xy) == 2
        except Exception as exc:
            raise HTTPException(status_code=400, detail="pan debe ser 'px,py' (dos números)") from exc
    if vtk_only and view_list:
        raise HTTPException(status_code=400, detail="vtk_only no soporta multivista (views); usa matplotlib o llamadas por vista")
    with STATE_LOCK:
        scene = S.doc.scene
        if isolate_ids:
            scene = {fid: S.doc.scene[fid] for fid in isolate_ids if fid in S.doc.scene}
            if not scene:
                raise HTTPException(status_code=400, detail="isolate: ningún id existe en la escena")
        override = None
        if joints:
            try:
                vals = json.loads(joints)
                assert isinstance(vals, dict)
                vals = {k: float(v) for k, v in vals.items()}
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"joints debe ser JSON {{junta: valor}}: {exc}") from exc
            from apolo.assembly.constraints import solve_constraints
            from apolo.robotics.pose import posed_shapes

            vals = solve_constraints(S.doc.joints, S.doc.constraints, vals)
            override, _ = posed_shapes(S.doc, vals)
        # COTA: distancia mínima entre dos piezas → la dibuja la vía VTK encima de la geometría.
        # Usa las shapes RENDERIZADAS (override si hay pose) para que coincida con lo que se ve.
        dimension = None
        if measure:
            from apolo.kernel.measure import measure_distance

            parts = [s.strip() for s in measure.split(",") if s.strip()]
            if len(parts) != 2:
                raise HTTPException(status_code=400, detail="measure: pasa exactamente dos ids 'a,b'")
            a_id, b_id = parts
            fa, fb = S.doc.scene.get(a_id), S.doc.scene.get(b_id)
            if fa is None or fb is None:
                missing = a_id if fa is None else b_id
                raise HTTPException(status_code=404, detail=f"measure: no existe el sólido '{missing}'")
            sa = override.get(a_id, fa.shape) if override else fa.shape
            sb = override.get(b_id, fb.shape) if override else fb.shape
            try:
                m = measure_distance(sa, sb)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            dimension = {"p1": m["punto_a"], "p2": m["punto_b"], "label": f"{m['dist_mm']:g} mm"}
        # Dos-locks del render (V6.2c): bajo STATE_LOCK solo se EXTRAE la geometría (teselado
        # con caché) a un snapshot de datos PUROS; el render VTK (depth-peeling/FXAA, lo lento)
        # corre FUERA del lock → una foto no congela las mutaciones. SOLO la MULTIVISTA (views) o
        # un fallo de VTK (sin OpenGL) → matplotlib. vtk_only=true (tool MCP render_view): EXIGE
        # VTK y NO cae a matplotlib (si no hay OpenGL → 503 claro, no una imagen con cuadrícula).
        feat_colors = _feature_colors()
        snapshot = None
        if (vtk_only or shade) and not view_list:
            try:
                from apolo.kernel.render_vtk import extract_render_scene

                snapshot = extract_render_scene(
                    scene, view,
                    highlight_ids=highlight_ids, shapes_override=override,
                    fit_ids=fit_ids, zoom=zoom, section=section,
                    show_axes=show_axes, show_bbox=show_bbox, colors=feat_colors,
                    ignore_visibility=bool(isolate_ids),
                    azimuth=azimuth, elevation=elevation, dimension=dimension, edges=edges,
                    xray=xray, labels=labels, roll=roll, pan=pan_xy,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
    # FUERA de STATE_LOCK: render VTK (bajo RENDER_LOCK) desde el snapshot de datos puros
    png = None
    if snapshot is not None:
        try:
            from apolo.kernel.render_vtk import RENDER_LOCK, render_snapshot_vtk

            with RENDER_LOCK:
                png = render_snapshot_vtk(snapshot)
        except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL u otro fallo VTK
            if vtk_only:
                raise HTTPException(
                    status_code=503,
                    detail=f"Render VTK no disponible (¿sin contexto OpenGL?): {exc}",
                ) from exc
            import logging

            logging.getLogger("uvicorn.error").warning(
                "VTK render falló; usando matplotlib", exc_info=True
            )
            png = None
    if png is None:  # matplotlib (multivista/fallback): tesela dentro → bajo STATE_LOCK
        with STATE_LOCK:
            try:
                png = render_scene_png(
                    scene, view,
                    highlight_ids=highlight_ids, show_axes=show_axes, show_bbox=show_bbox,
                    shapes_override=override, fit_ids=fit_ids, zoom=zoom, proportional=proportional,
                    views=view_list, labels=labels, section=section,
                    colors=feat_colors if shade else None,
                    ignore_visibility=bool(isolate_ids),
                    azimuth=azimuth, elevation=elevation, roll=roll,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=png, media_type="image/png")
