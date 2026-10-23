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
def _publicacion_aislada(tmp_path_factory):
    """La biblioteca de música (`APOLO_MUSICA_DIR`) en una carpeta vacía y la tienda por
    defecto, en toda la suite: `publicar generar` sin `--musica` elige la pista menos usada de
    `~/.apolo/musica` y anota su uso (fabrica-de-publicaciones D9); sin esto, un test usaría la
    biblioteca REAL de la PC y le sumaría usos, y una `APOLO_TIENDA_URL` de la consola cambiaría
    las URL esperadas. Quien prueba la biblioteca pasa su propia carpeta. El candado de render de
    la fábrica (F3, D7) tampoco es el de la PC: un test no espera a una fábrica real. Se muda con
    la fábrica (F4 del plan nucleo-abierto)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("APOLO_MUSICA_DIR", str(tmp_path_factory.mktemp("musica-vacia")))
        mp.setenv("APOLO_CANDADO_RENDER",
                  str(tmp_path_factory.mktemp("candado") / "render.lock"))
        mp.delenv("APOLO_TIENDA_URL", raising=False)
        yield
