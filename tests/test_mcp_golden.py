"""Golden del MCP: lo que ve un cliente MCP (instructions, `list_tools()` y las peticiones y
salidas de una `call_tool` real por tool) es byte-idéntico a lo congelado.

Permanente (plan chat-cliente-igual, F1): el chat de la app pasará a usar estas mismas tools
y cualquier refactor del cliente fino (destino inyectable, brief fuera, instructions fuera)
tiene que dejarlas iguales. Si un cambio es DELIBERADO (una tool nueva, un docstring, un
default), se revisa el diff y se re-congela con `python scripts/golden_mcp.py --congelar`.
Los casos y las respuestas canónicas están en `scripts/golden_mcp_casos.py`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("mcp")  # el cliente MCP necesita el paquete mcp

_RAIZ = Path(__file__).resolve().parents[1]


def _motor():
    ruta = _RAIZ / "scripts" / "golden_mcp.py"
    spec = importlib.util.spec_from_file_location("golden_mcp", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def motor():
    return _motor()


def test_cada_tool_tiene_al_menos_un_caso(motor):
    faltan = motor.tools_sin_caso()
    assert not faltan, (
        f"tools sin caso en scripts/golden_mcp_casos.py: {faltan} — añade uno y re-congela"
    )


def test_golden_identico(motor):
    import mcp
    import pydantic

    difs = motor.comparar()
    assert not difs, (
        "El MCP cambió respecto del golden congelado (mcp "
        f"{getattr(mcp, '__version__', '?')}, pydantic {pydantic.VERSION}). Si es deliberado, "
        "revisa el diff y corre `python scripts/golden_mcp.py --congelar`:\n\n" + "\n\n".join(difs)
    )


def test_el_golden_cubre_los_caminos_de_error(motor):
    """Los cuatro caminos de error que el contrato exige siguen en el golden."""
    import json

    llamadas = json.loads((motor.DIR_GOLDEN / "llamadas.json").read_text(encoding="utf-8"))
    errores = " ".join(c.get("error", "") for c in llamadas)
    assert "Apolo rechazó la operación (400): No existe el comando" in errores  # 400 con detail
    assert "Contrato incumplido" in errores  # job en error
    assert "(404)" in errores  # 404 de job
    assert "No hay conexión con Apolo" in errores  # conexión rechazada
