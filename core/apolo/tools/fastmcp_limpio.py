"""FastMCP que describe cada tool con su docstring LIMPIO, igual en Python 3.11, 3.12 y 3.13.

FastMCP usa el `__doc__` crudo de la función como descripción de la tool. Python 3.13 quita la
sangría común de los docstrings al compilar; 3.11 y 3.12 no: allí el agente recibía cada línea
con cuatro espacios de más y el golden (`tests/test_mcp_golden.py`, congelado en 3.13) fallaba
en el CI de Linux 3.11/3.12. `inspect.cleandoc` da en 3.11 exactamente el texto de 3.13 (medido
en las 79 tools) y en 3.13 no cambia nada.
"""

from __future__ import annotations

import inspect

from mcp.server.fastmcp import FastMCP


class FastMCPLimpio(FastMCP):
    def tool(self, *args, **kwargs):
        registrar = super().tool(*args, **kwargs)

        def decorar(fn):
            if fn.__doc__:
                fn.__doc__ = inspect.cleandoc(fn.__doc__)
            return registrar(fn)

        return decorar
