"""Lo que el agente lee de un docstring sale igual en Python 3.11, 3.12 y 3.13.

3.13 quita la sangría común de los docstrings al compilar; 3.11 y 3.12 no. Las tools del MCP
(`tools/fastmcp_limpio.py`) y la description de cada comando (`registry._schema_entry`, la del
schema de pydantic) pasan por `inspect.cleandoc`. En 3.13 el golden del MCP no ve la diferencia:
el primer test fabrica el docstring como lo deja 3.11 para probar el mecanismo en cualquier
versión.
"""

from __future__ import annotations

import asyncio
import inspect
import logging

from apolo.commands.registry import command_schemas
from apolo.tools.fastmcp_limpio import FastMCPLimpio


def test_la_tool_se_describe_con_el_docstring_limpio():
    raiz = logging.getLogger()  # FastMCP reconfigura el logger raíz al construirse
    nivel, previos = raiz.level, raiz.handlers[:]
    try:
        srv = FastMCPLimpio("prueba")
    finally:
        raiz.handlers[:] = previos
        raiz.setLevel(nivel)

    def herramienta() -> str:
        return ""

    herramienta.__doc__ = "Primera línea.\n    segunda\n      con sangría relativa\n    "
    srv.tool()(herramienta)
    (tool,) = asyncio.run(srv.list_tools())
    assert tool.description == "Primera línea.\nsegunda\n  con sangría relativa"


def test_ninguna_descripcion_trae_la_sangria_del_docstring():
    import apolo.mcp_server as mcp_server

    for tool in asyncio.run(mcp_server.mcp.list_tools()):
        assert tool.description == inspect.cleandoc(tool.description), tool.name
    for entrada in command_schemas():
        assert entrada["description"] == inspect.cleandoc(entrada["description"]), entrada["type"]
        assert entrada["description"] == entrada["schema"].get("description", "")
