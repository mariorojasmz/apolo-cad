"""Las tools que viven fuera de `mcp_server.py` se registran en el `mcp` que CORRE.

`.mcp.json` arranca el servidor con `python -m apolo.mcp_server`: el módulo es `__main__`. Si
`tools/simulacion.py` (o `tools/mcp_electrico.py`) importara `apolo.mcp_server`, cargaría una
SEGUNDA copia y la tool quedaría en el `mcp` de esa copia: el que corre exponía 79 tools sin
`simulate` (V8.2 F2). Por eso `mcp_server.py` llama `registrar(mcp, api)` de cada uno con el
suyo, y nada de `tools/` lo importa.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

RAIZ = Path(__file__).resolve().parents[1]

_SONDA = """
import asyncio, json, runpy, sys
import apolo.tools.fastmcp_limpio as f

def run(self, *a, **k):
    nombres = [t.name for t in asyncio.run(self.list_tools())]
    print(json.dumps({"n": len(nombres), "nombres": nombres,
                      "copia": "apolo.mcp_server" in sys.modules}))

f.FastMCPLimpio.run = run
runpy.run_module("apolo.mcp_server", run_name="__main__", alter_sys=True)
"""


#: Las tools que viven en `tools/` (registradas con `registrar(mcp, api)`).
FUERA_DEL_ARCHIVO = {"get_circuit", "electrical_check", "simulate", "remove_commands",
                     "test_plc", "get_simulation", "get_scenarios", "set_scenario",
                     # una de cada bloque de partir-nucleo-congelado F1
                     "get_scene", "render_view", "open_project", "check_assembly", "verify",
                     "drawing", "set_visibility", "fea_static"}


def test_las_tools_de_afuera_estan_en_el_mcp_que_corre_con_menos_m():
    entorno = {**os.environ,
               "PYTHONPATH": os.pathsep.join([str(RAIZ / "core"), os.environ.get("PYTHONPATH", "")])}
    out = subprocess.run([sys.executable, "-B", "-c", _SONDA], capture_output=True, text=True,
                         env=entorno, timeout=300, cwd=RAIZ)
    assert out.returncode == 0, out.stderr[-2000:]
    sonda = json.loads(out.stdout.strip().splitlines()[-1])
    faltan = FUERA_DEL_ARCHIVO - set(sonda["nombres"])
    assert not faltan, f"el mcp que corre no tiene {sorted(faltan)} ({sonda['n']} tools)"
    assert not sonda["copia"], "algo importó apolo.mcp_server: hay una segunda copia del servidor"


def test_nada_de_tools_importa_el_servidor():
    for ruta in (RAIZ / "core" / "apolo" / "tools").glob("*.py"):
        for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.Import):
                mods = [a.name for a in nodo.names]
            elif isinstance(nodo, ast.ImportFrom):
                mods = [nodo.module or ""] + [f"{nodo.module}.{a.name}" for a in nodo.names]
            else:
                continue
            assert "apolo.mcp_server" not in mods, f"{ruta.name} importa apolo.mcp_server"
