"""La ruta de la extensión falsa (bajo `/api/prueba/`) y una que pisa un tramo del núcleo."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/api/prueba/hola")
def prueba_hola() -> dict:
    return {"hola": "desde la extensión de prueba"}


router_fea = APIRouter()


@router_fea.get("/api/fea/hola")
def fea_hola() -> dict:
    return {"hola": "esto no debe cargarse: /api/fea/ es del núcleo"}
