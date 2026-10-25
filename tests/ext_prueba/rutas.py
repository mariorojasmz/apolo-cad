"""Las rutas de la extensión falsa (bajo `/api/prueba/`) y una que pisa un tramo del núcleo.

Las que tocan el documento usan SÓLO la fachada de `apolo.extensiones_api` (F1d): mutar con
undo, autosave y la guardia (`/caja`, también como job con `?async=true`), leer (`/piezas`) y
sus datos en el manifest (`/nota`, la clave `ext`). Su entregable en archivo (`/informe.txt`,
pedidos-de-extensiones D6) va por `entregable_documento`: extrae bajo el lock, compone fuera, en
directo o como job con `?async=true`."""

from __future__ import annotations

from fastapi import APIRouter, Query

from apolo.extensiones_api import (
    CommandError,
    entregable_documento,
    leer_documento,
    leer_ext,
    mutar_documento,
    poner_ext,
)

NOMBRE = "ext-prueba"  # su `Extension.nombre`: la clave de sus datos en el manifest

router = APIRouter()


@router.get("/api/prueba/hola")
def prueba_hola() -> dict:
    return {"hola": "desde la extensión de prueba"}


@router.post("/api/prueba/caja", response_model=dict)
def prueba_caja(lado: float = 40, async_: bool = Query(False, alias="async")):
    """Una caja `prueba.hola` por la fachada: un undo, autosave y la respuesta de siempre."""
    return mutar_documento(lambda doc: doc.execute("prueba.hola", {"lado": lado}),
                           asincrono=async_, tipo="prueba.caja",
                           armar=lambda doc: {"piezas": len(doc.scene)})


@router.get("/api/prueba/piezas")
def prueba_piezas() -> dict:
    return leer_documento(lambda doc: {"piezas": sorted(f.name for f in doc.scene.values())})


@router.get("/api/prueba/nota")
def prueba_nota() -> dict:
    return {"nota": leer_ext(NOMBRE)}


@router.put("/api/prueba/nota")
def prueba_poner_nota(nota: dict | None = None) -> dict:
    return {"nota": poner_ext(NOMBRE, nota)}


def _extraer(doc) -> dict:
    """Bajo `STATE_LOCK`: sólo datos puros (nombres), nada del shape vivo."""
    if not doc.scene:
        raise CommandError("No hay piezas que informar: el modelo está vacío.")
    return {"proyecto": doc.name or "proyecto", "piezas": sorted(f.name for f in doc.scene.values())}


def _componer(datos: dict) -> tuple[bytes, str, str]:
    """Fuera de todo lock: aquí iría lo lento (un PDF, un ZIP de láminas, un DWG)."""
    texto = "".join(f"{linea}\n" for linea in [f"Informe de {datos['proyecto']}", *datos["piezas"]])
    return texto.encode("utf-8"), "text/plain", f"{datos['proyecto']}-informe.txt"


@router.get("/api/prueba/informe.txt")
def prueba_informe(async_: bool = Query(False, alias="async")):
    return entregable_documento(_extraer, _componer, tipo="prueba.informe", asincrono=async_)


router_fea = APIRouter()


@router_fea.get("/api/fea/hola")
def fea_hola() -> dict:
    return {"hola": "esto no debe cargarse: /api/fea/ es del núcleo"}
