"""Extensión FALSA de la suite (D9 del plan nucleo-abierto-extensiones-privadas): usa cada punto
de extensión del núcleo con lo mínimo, sin instalarse (se carga con
`APOLO_EXTENSIONES_EXTRA=ext_prueba:EXTENSION`; `tests/` está en el `sys.path` de la suite).

- un comando `prueba.hola` que crea una caja (`comandos.py`), con su pista y su pestaña;
- una ruta `GET /api/prueba/hola` (`rutas.py`);
- una tool MCP `prueba_hola` que corre el comando (`tools.py`);
- un YAML de catálogo con UNA ref, `prueba.caja` (`catalogo/`);
- un modelo de co-simulación mínimo, tipo `prueba.lampara` (`modelos.py`).

Los campos pesados van PEREZOSOS (funciones): así lo hace una extensión real para que el MCP no
cargue OCCT al leerla. Abajo, las variantes que el núcleo debe RECHAZAR (`test_extensiones.py`).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from apolo.extensiones import Extension

from .tools import registrar, registrar_con_punto

CATALOGO = Path(__file__).resolve().parent / "catalogo"


def _comandos():
    from .comandos import SPECS

    return SPECS


def _routers():
    from .rutas import router

    return [router]


def _modelos():
    from .modelos import Lampara

    return {"prueba.lampara": Lampara}


EXTENSION = Extension(
    nombre="ext-prueba",
    prefijo="prueba",
    version="0.1.0",
    nucleo=(1, 1),
    comandos=_comandos,
    pistas={"prueba.hola": "Crea una caja de prueba para comprobar que la extensión se cargó."},
    pestanas={"prueba": {"orden": 90, "rotulo": "Prueba"}},
    routers=_routers,
    tools_mcp=registrar,
    catalogo=(str(CATALOGO),),
    modelos_cosim=_modelos,
    epoch_catalogo=1,
)


def _sin_prefijo():
    from .comandos import sin_prefijo

    return [sin_prefijo()]


def _electrico():
    from .comandos import electrico

    return [electrico()]


def _routers_fea():
    from .rutas import router_fea

    return [router_fea]


# ── lo que el núcleo rechaza (todo o nada: nada de la extensión queda registrado) ──────────────
SIN_PREFIJO = replace(EXTENSION, comandos=_sin_prefijo)
CONTRATO_VIEJO = replace(EXTENSION, nombre="ext-vieja", nucleo=(2, 3))
ELECTRICA = replace(EXTENSION, comandos=_electrico)
TOOL_CON_PUNTO = replace(EXTENSION, tools_mcp=registrar_con_punto)
DUPLICADA = replace(EXTENSION, nombre="ext-prueba-2")  # mismo prefijo que EXTENSION
EN_RUTAS_DEL_NUCLEO = replace(EXTENSION, nombre="ext-fea", prefijo="fea", comandos=(), pistas={},
                              pestanas={}, catalogo=(), modelos_cosim={}, tools_mcp=None,
                              routers=_routers_fea)
NO_ES_EXTENSION = "una cadena no es una extensión"
