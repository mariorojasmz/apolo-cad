"""Rutas del FEA: estático de pieza y bonded de ensamblaje, resultados guardados y fringes.

Router de la API (F6c del plan `docs/plans/partir-api-main.md`): movidas tal cual desde
`main.py`. La coreografía (fases, tmp dir, guardia de proyecto, campo en memoria) es de
`fea_runs.py`; la preparación, de `apolo.services.fea_setup`. El ORDEN importa: las rutas
`static`/`assembly` (y sus `.png`) y `GET /api/fea/group/{name}` van antes que
`GET /api/fea/{feature_id}`, y `GET /api/fea/group/{name}` antes que
`GET /api/fea/{feature_id}/fringe.png` (los dos casan `/api/fea/group/fringe.png`).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from apolo.state import STATE_LOCK

from ..fea_runs import (
    FeaAssemblyIn,
    FeaStaticIn,
    _fea_assembly_run,
    _fea_static_run,
    _last_fea_field,
)
from ..session import S

router = APIRouter()


@router.post("/api/fea/static")
def fea_static(body: FeaStaticIn) -> dict:
    """FEA estático lineal de UNA pieza (malla tet P2 + elasticidad lineal).
    Read-only sobre la geometría; el resumen se guarda como metadato para la
    memoria de cálculo (save=false para no persistir)."""
    resumen, _ = _fea_static_run(body)
    return resumen


@router.post("/api/fea/static.png")
def fea_static_png(body: FeaStaticIn) -> Response:
    """Igual que /api/fea/static pero devuelve el FRINGE von Mises (PNG, mapa de
    colores + barra de escala) del campo resuelto."""
    from apolo.fea.fringe import fringe_png

    resumen, field = _fea_static_run(body)
    png = fringe_png(field, title=f"von Mises [MPa] · {resumen['pieza']} · FS={resumen['fs']}")
    return Response(content=png, media_type="image/png")


@router.post("/api/fea/assembly")
def fea_assembly(body: FeaAssemblyIn) -> dict:
    """FEA estático lineal BONDED de un SUB-ENSAMBLAJE (V7.4): el bastidor pegado bajo
    la carga de diseño, multi-material, con FS POR PIEZA. Deriva el empotramiento de
    los grounds y la carga de los requisitos (sobre la cama) salvo override explícito.
    El solve puede tardar MINUTOS: invoca con mesh_size_mm generoso primero."""
    resumen, _ = _fea_assembly_run(body)
    return resumen


@router.post("/api/fea/assembly.png")
def fea_assembly_png(body: FeaAssemblyIn) -> Response:
    """Igual que /api/fea/assembly pero devuelve el FRINGE von Mises del ensamblaje."""
    from apolo.fea.fringe import fringe_png

    resumen, field = _fea_assembly_run(body)
    png = fringe_png(field, title=f"von Mises [MPa] · {resumen['grupo']} · FS={resumen['fs']}")
    return Response(content=png, media_type="image/png")


@router.get("/api/fea/group/{name}")
def get_fea_group(name: str) -> dict:
    with STATE_LOCK:
        res = S.doc.fea.get(f"group:{name}")
        if res is None:
            raise HTTPException(status_code=404, detail="El grupo no tiene FEA guardado")
        return res


@router.get("/api/fea/{feature_id}")
def get_fea(feature_id: str) -> dict:
    with STATE_LOCK:
        res = S.doc.fea.get(feature_id)
        if res is None:
            raise HTTPException(status_code=404, detail="La pieza no tiene FEA guardado")
        return res


@router.get("/api/fea/group/{name}/fringe.png")
def get_fea_group_fringe(name: str) -> Response:
    """Fringe del ÚLTIMO análisis del ensamblaje SIN re-resolver (campo en memoria del
    proceso; si el server se reinició, re-ejecuta POST /api/fea/assembly)."""
    from apolo.fea.fringe import fringe_png

    key = f"group:{name}"
    field = _last_fea_field(key)
    if field is None:
        raise HTTPException(status_code=404,
                            detail="No hay campo FEA en memoria para ese grupo: "
                                   "corre POST /api/fea/assembly primero")
    with STATE_LOCK:
        res = S.doc.fea.get(key) or {}
    title = f"von Mises [MPa] · {res.get('grupo', name)} · FS={res.get('fs')}"
    return Response(content=fringe_png(field, title=title), media_type="image/png")


@router.get("/api/fea/{feature_id}/fringe.png")
def get_fea_fringe(feature_id: str) -> Response:
    """Fringe del ÚLTIMO análisis de la pieza SIN re-resolver (campo en memoria del
    proceso; si el server se reinició, re-ejecuta POST /api/fea/static)."""
    from apolo.fea.fringe import fringe_png

    field = _last_fea_field(feature_id)
    if field is None:
        raise HTTPException(status_code=404,
                            detail="No hay campo FEA en memoria para esa pieza: "
                                   "corre POST /api/fea/static primero")
    with STATE_LOCK:
        res = S.doc.fea.get(feature_id) or {}
    title = f"von Mises [MPa] · {res.get('pieza', feature_id)} · FS={res.get('fs')}"
    return Response(content=fringe_png(field, title=title), media_type="image/png")
