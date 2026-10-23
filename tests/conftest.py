"""Fixtures globales de la suite.

Mínimo a propósito: el aislamiento común (registro de errores, sandbox perezoso y la SESIÓN de
la API por test) viene del plugin `apolo.pruebas`, que viaja en la wheel para que una extensión
lo use igual (A6 de nucleo-abierto-extensiones-privadas). Aquí queda sólo lo de ESTA suite. El
resto del estado global (cachés de proceso, `WS`, jobs) sigue a cargo de cada test.
"""

from __future__ import annotations

import os

import pytest

# A3 (nucleo-abierto-extensiones-privadas): la suite mide el NÚCLEO (59 comandos, 90 tools,
# 378 refs, golden). Una extensión instalada en el mismo .venv (D11) no se carga, tampoco en los
# procesos que lanzan los tests (uvicorn, el MCP por stdio, el worker): por eso `os.environ` y
# no monkeypatch, y ANTES de importar `apolo`. `test_extensiones.py` la prende a propósito.
os.environ["APOLO_EXTENSIONES"] = "0"

pytest_plugins = ["apolo.pruebas"]


@pytest.fixture(autouse=True, scope="session")
def _tienda_por_defecto():
    """El cierre del video (`media/cierre.py`) toma su dominio de `APOLO_TIENDA_URL`: una de la
    consola cambiaría lo esperado. Lo demás que aislaba la fábrica de publicaciones (música,
    candado de render) se fue con ella fuera del núcleo (F4a de nucleo-abierto)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("APOLO_TIENDA_URL", raising=False)
        yield
