"""Prepara una versión nueva: sincroniza versión y cifras en TODOS los sitios.

Publicar Apolo toca cinco archivos que se desincronizan solos. Este script los
pone de acuerdo en un comando, para que una release no dependa de acordarse:

    python scripts/release.py --version 0.2.0            # rápido
    python scripts/release.py --version 0.2.0 --tests    # + recuenta los tests (lento)
    python scripts/release.py --check                    # solo audita, no escribe

Qué sincroniza:
  · core/pyproject.toml   version
  · server.json           version  (×2: raíz y packages[0])
  · README.md · README.es.md · core/README.md
        cifras de tools MCP, comandos, refs de catálogo y tests (badges y texto)

Lo que NO hace (a propósito): construir, subir a PyPI ni publicar en el registro.
Eso son acciones con credenciales y las lanza una persona — el script te imprime
los comandos exactos al terminar.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "core" / "pyproject.toml"
SERVER_JSON = ROOT / "server.json"
READMES = [ROOT / "README.md", ROOT / "README.es.md", ROOT / "core" / "README.md"]


# --------------------------------------------------------------------- cifras
def count_tools() -> int:
    src = (ROOT / "core" / "apolo" / "mcp_server.py").read_text(encoding="utf-8")
    return len(re.findall(r"^@mcp\.tool", src, re.M))


def count_commands() -> int:
    sys.path.insert(0, str(ROOT / "core"))
    from apolo.commands import command_schemas

    return len(command_schemas())


def count_catalog() -> int:
    sys.path.insert(0, str(ROOT / "core"))
    from apolo.library import catalog_payload

    payload = catalog_payload()
    items = payload.get("components", payload) if isinstance(payload, dict) else payload
    return len(items)


def count_tests() -> int | None:
    """Cuenta REAL vía pytest (tarda ~1 min). None si no se puede determinar."""
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "--collect-only"],
        cwd=ROOT, capture_output=True, text=True,
    )
    m = re.search(r"(\d+)(?:/\d+)? tests collected", out.stdout)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------- escrituras
def set_version(version: str) -> list[str]:
    changed = []

    text = PYPROJECT.read_text(encoding="utf-8")
    new = re.sub(r'^version = ".*?"', f'version = "{version}"', text, count=1, flags=re.M)
    if new != text:
        PYPROJECT.write_text(new, encoding="utf-8")
        changed.append("core/pyproject.toml")

    data = json.loads(SERVER_JSON.read_text(encoding="utf-8"))
    if data.get("version") != version or data["packages"][0].get("version") != version:
        data["version"] = version
        data["packages"][0]["version"] = version  # los DOS: el registro valida ambos
        SERVER_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        changed.append("server.json")

    return changed


def set_counts(tools: int, commands: int, catalog: int, tests: int | None) -> list[str]:
    """Reescribe las cifras en los README. Cada patrón lleva su unidad para no
    tocar números ajenos (versiones, medidas, años)."""
    subs = [
        (r"MCP-\d+%20tools", f"MCP-{tools}%20tools"),
        (r"alt=\"MCP \d+ tools\"", f'alt="MCP {tools} tools"'),
        (r"\b\d+ MCP tools\b", f"{tools} MCP tools"),
        (r"\b\d+ tools MCP\b", f"{tools} tools MCP"),
        (r"(rest of the )\d+( tools)", rf"\g<1>{tools}\g<2>"),
        (r"(de las )\d+( tools)", rf"\g<1>{tools}\g<2>"),
        (r"MCP server \(\d+ tools\)", f"MCP server ({tools} tools)"),
        (r"servidor MCP \(\d+ tools\)", f"servidor MCP ({tools} tools)"),
        (r"\b\d+-reference catalog\b", f"{catalog}-reference catalog"),
        (r"catálogo de \d+ referencias", f"catálogo de {catalog} referencias"),
        (r"catalog \(\d+ refs\)", f"catalog ({catalog} refs)"),
        (r"catálogo \(\d+ refs\)", f"catálogo ({catalog} refs)"),
        (r"\b\d+-reference catalog\b", f"{catalog}-reference catalog"),
    ]
    if tests is not None:
        subs += [
            (r"tests-\d+%20passing", f"tests-{tests}%20passing"),
            (r"alt=\"\d+ tests\"", f'alt="{tests} tests"'),
            (r"# \d+ tests", f"# {tests} tests"),
        ]

    changed = []
    for path in READMES:
        text = original = path.read_text(encoding="utf-8")
        for pattern, repl in subs:
            text = re.sub(pattern, repl, text)
        if text != original:
            path.write_text(text, encoding="utf-8")
            changed.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return changed


def main() -> int:
    ap = argparse.ArgumentParser(description="Sincroniza versión y cifras para una release.")
    ap.add_argument("--version", help="versión nueva, p. ej. 0.2.0")
    ap.add_argument("--tests", action="store_true", help="recuenta los tests (lento, ~1 min)")
    ap.add_argument("--check", action="store_true", help="solo informa; no escribe nada")
    args = ap.parse_args()

    if not args.version and not args.check:
        ap.error("indica --version X.Y.Z (o usa --check para solo auditar)")

    tools, commands, catalog = count_tools(), count_commands(), count_catalog()
    tests = count_tests() if args.tests else None

    print("Cifras medidas del proyecto:")
    print(f"  tools MCP        : {tools}")
    print(f"  comandos         : {commands}")
    print(f"  refs de catálogo : {catalog}")
    print(f"  tests            : {tests if tests is not None else '(sin recontar — usa --tests)'}")

    if args.check:
        print("\n--check: no se escribió nada.")
        return 0

    changed = set_version(args.version) + set_counts(tools, commands, catalog, tests)
    print("\nArchivos actualizados:" if changed else "\nTodo ya estaba sincronizado.")
    for c in changed:
        print(f"  {c}")

    print(f"""
Siguiente (a mano, porque piden credenciales):

  npm --prefix ui run build
  python scripts/stage_ui.py
  python -m build core --outdir dist
  python -m twine upload dist/*
  .\\mcp-publisher.exe publish

Y no olvides el tag:  git tag v{args.version} ; git push --tags""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
