"""Mide las cifras del núcleo que antes se escribían a mano en «Estado actual» del CLAUDE.md raíz.

La línea `N tests · N vitest · N tools MCP · N comandos · catálogo N refs` se editaba en cada
fase y chocaba en cada rebase; ahora se MIDE:

    python scripts/conteos.py            # todo (~35 s de recolección de pytest + vitest)
    python scripts/conteos.py --rapido   # sin recolectar pytest (vitest por regex): ~10 s
    python scripts/conteos.py --json     # las cifras como JSON, para otro script

Qué cuenta cada cifra:
  · tests: los ítems que `pytest tests` recolecta por defecto (`pytest.ini`: sin tortura), cada
    caso parametrizado por separado = lo que suma la línea passed/skipped/failed de una corrida.
    Se recolecta en proceso con `--collect-only`: no corre ningún test.
  · tortura: los ítems con `@pytest.mark.torture` (los que `-m torture` corre aparte).
  · vitest: `vitest list --json` si hay `ui/node_modules` (≈ 15 s); si no, o con `--rapido`, las
    llamadas `it(`/`test(` de `ui/src/**/*.test.ts(x)` por regex (igual a `vitest list` el
    2026-10-24: 521 y 521; un `it` dentro de un bucle contaría una vez).
  · tools MCP: `list_tools()` del servidor (lo que ve un cliente, también las de `tools/*.py`).
  · comandos: `len(REGISTRY)`; refs: `len(CATALOG)`.

Todo con las extensiones apagadas (`APOLO_EXTENSIONES=0`, antes de importar `apolo`): son las
cifras del NÚCLEO, también para `release.py`, que importa este módulo.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

os.environ["APOLO_EXTENSIONES"] = "0"

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"
_LLAMADA_TEST = re.compile(r"^\s*(?:it|test)(?:\.(?:each|skip|only|todo|concurrent)[^(]*)?\(", re.M)


def _core_en_path() -> None:
    core = str(ROOT / "core")
    if core not in sys.path:
        sys.path.insert(0, core)


def tools() -> int:
    _core_en_path()
    from apolo.mcp_server import mcp

    return len(asyncio.run(mcp.list_tools()))


def comandos() -> int:
    _core_en_path()
    from apolo.commands.registry import REGISTRY

    return len(REGISTRY)


def refs() -> int:
    _core_en_path()
    from apolo.library.catalog import CATALOG

    return len(CATALOG)


class _Recuento:
    """Plugin de pytest: cuántos ítems quedan tras la selección y cuántos llevan `torture`."""

    def __init__(self) -> None:
        self.tests = 0
        self.tortura = 0

    @staticmethod
    def _con_marca(items) -> int:
        return sum(1 for i in items if i.get_closest_marker("torture") is not None)

    def pytest_collection_modifyitems(self, items) -> None:  # corre antes de deseleccionar
        self.tortura = self._con_marca(items)

    def pytest_collection_finish(self, session) -> None:
        self.tests = len(session.items)


def tests() -> tuple[int, int]:
    """(tests por defecto, tortura) recolectando `tests/` en este proceso, sin correrlos."""
    import pytest

    _core_en_path()
    rec = _Recuento()
    previo = os.getcwd()
    os.chdir(ROOT)  # `pytest.ini` (testpaths, `-m "not torture"`) se lee desde la raíz
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            codigo = pytest.main(["tests", "--collect-only", "-q", "-p", "no:cacheprovider",
                                  "-p", "no:warnings"], plugins=[rec])
    finally:
        os.chdir(previo)
    if codigo != 0:
        raise RuntimeError(f"pytest --collect-only salió con {codigo}: hay errores de recolección")
    return rec.tests, rec.tortura


def vitest_regex() -> int:
    total = 0
    for patron in ("*.test.ts", "*.test.tsx"):
        for ruta in (UI / "src").rglob(patron):
            total += len(_LLAMADA_TEST.findall(ruta.read_text(encoding="utf-8")))
    return total


def vitest() -> tuple[int, str]:
    """(cifra, cómo se midió): `vitest list` si se puede, si no la regex."""
    bin_ = UI / "node_modules" / ".bin" / ("vitest.cmd" if os.name == "nt" else "vitest")
    if bin_.exists() and shutil.which("node"):
        out = subprocess.run([str(bin_), "list", "--json"], cwd=UI, capture_output=True,
                             text=True, encoding="utf-8", timeout=300)
        if out.returncode == 0:
            with contextlib.suppress(ValueError):
                return len(json.loads(out.stdout)), "vitest list"
    return vitest_regex(), "regex"


def medir(rapido: bool = False) -> dict:
    datos: dict = {}
    if rapido:
        datos["tests"] = datos["tortura"] = None
        datos["vitest"], datos["vitest_por"] = vitest_regex(), "regex"
    else:
        datos["tests"], datos["tortura"] = tests()
        datos["vitest"], datos["vitest_por"] = vitest()
    datos.update(tools=tools(), comandos=comandos(), refs=refs())
    return datos


def linea(d: dict) -> str:
    t = "? tests (sin --rapido)" if d["tests"] is None else (
        f"{d['tests']} tests (+{d['tortura']} de tortura vía `-m torture`)")
    return (f"{t} · {d['vitest']} tests vitest · {d['tools']} tools MCP · {d['comandos']} comandos"
            f" · catálogo {d['refs']} refs")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Mide las cifras del núcleo de Apolo.")
    ap.add_argument("--rapido", action="store_true", help="sin recolectar pytest; vitest por regex")
    ap.add_argument("--json", action="store_true", help="imprime las cifras como JSON")
    args = ap.parse_args(argv)
    d = medir(args.rapido)
    print(json.dumps(d, ensure_ascii=False) if args.json else linea(d))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
