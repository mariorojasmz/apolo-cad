"""`scripts/conteos.py` mide las cifras de «Estado actual» (ya no se escriben a mano en el
CLAUDE.md raíz): sus cifras de comandos, refs y tools son las mismas que vigilan los gates del
núcleo (`test_extensiones.py`), y su modo rápido corre como script."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _conteos():
    spec = importlib.util.spec_from_file_location("conteos_t", RAIZ / "scripts" / "conteos.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_cuenta_lo_mismo_que_los_registros_del_nucleo():
    from apolo import mcp_server
    from apolo.commands.registry import REGISTRY
    from apolo.library.catalog import CATALOG

    c = _conteos()
    assert c.comandos() == len(REGISTRY) and c.refs() == len(CATALOG)
    assert c.tools() == len(asyncio.run(mcp_server.mcp.list_tools()))


def test_la_regex_de_vitest_cuenta_it_y_test_y_no_otra_cosa():
    texto = ("describe('x', () => {\n  it('a', () => {})\n  test.each([1])('b', () => {})\n"
             "  it.skip('c', () => {})\n  const fit = () => {}\n  expect(test).toBe(1)\n})\n")
    assert len(_conteos()._LLAMADA_TEST.findall(texto)) == 3


def test_el_modo_rapido_corre_como_script():
    out = subprocess.run([sys.executable, "-B", str(RAIZ / "scripts" / "conteos.py"), "--rapido",
                          "--json"], capture_output=True, text=True, timeout=300, cwd=RAIZ)
    assert out.returncode == 0, out.stderr[-2000:]
    d = json.loads(out.stdout.strip().splitlines()[-1])
    c = _conteos()
    assert d["tests"] is None and d["vitest_por"] == "regex" and d["vitest"] > 0
    assert (d["comandos"], d["refs"], d["tools"]) == (c.comandos(), c.refs(), c.tools())
    assert re.fullmatch(r"\? tests \(sin --rapido\) · \d+ tests vitest · \d+ tools MCP · \d+ "
                        r"comandos · catálogo \d+ refs", c.linea(d))
