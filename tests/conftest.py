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
# 393 refs, golden). Una extensión instalada en el mismo .venv (D11) no se carga, tampoco en los
# procesos que lanzan los tests (uvicorn, el MCP por stdio, el worker): por eso `os.environ` y
# no monkeypatch, y ANTES de importar `apolo`. `test_extensiones.py` la prende a propósito.
os.environ["APOLO_EXTENSIONES"] = "0"
# Y los tests que la prenden (`extensiones_aisladas` quita la de arriba, `APOLO_EXTENSIONES_EXTRA`
# pide la falsa de `tests/ext_prueba`) tampoco ven las INSTALADAS por entry point: con una real en
# el venv, `cargar()` devolvía [real, ext-prueba]. Los procesos hijos lo heredan. Un test que
# quiera los entry points quita ésta con `monkeypatch.delenv`. El plugin `apolo.pruebas` no la fija:
# la suite de una extensión SÍ se carga por su entry point.
os.environ["APOLO_EXTENSIONES_INSTALADAS"] = "0"

pytest_plugins = ["apolo.pruebas"]


def pytest_configure(config):
    """Con pytest-xdist (`-n N`), reparto `loadgroup` en vez de `load`: los módulos marcados con
    `xdist_group` (`test_flota.py`) corren juntos en un worker y en orden. Sin `-n` no cambia
    nada; así nadie tiene que recordar `--dist loadgroup` (uno explícito se respeta).

    Dos mitades: el controlador elige el planificador por `option.dist`; cada worker re-parsea
    los argumentos de la línea de comandos (no recibe las opciones del controlador) y sólo suma
    el sufijo `@grupo` al nodeid si `option.loadgroup` → se lo pasa `workerinput`."""
    if hasattr(config, "workerinput"):
        if config.workerinput.get("apolo_dist") == "loadgroup":
            config.option.loadgroup = True
    elif getattr(config.option, "dist", "no") == "load" and getattr(config.option,
                                                                      "numprocesses", None):
        config.option.dist = "loadgroup"


@pytest.hookimpl(optionalhook=True)
def pytest_configure_node(node):
    """Hook de pytest-xdist (en el controlador, por worker): le avisa el reparto elegido."""
    node.workerinput["apolo_dist"] = node.config.option.dist


@pytest.fixture(autouse=True, scope="session")
def _tienda_por_defecto():
    """El cierre del video (`media/cierre.py`) toma su dominio de `APOLO_TIENDA_URL`: una de la
    consola cambiaría lo esperado. Lo demás que aislaba la fábrica de publicaciones (música,
    candado de render) se fue con ella fuera del núcleo (F4a de nucleo-abierto)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("APOLO_TIENDA_URL", raising=False)
        yield
