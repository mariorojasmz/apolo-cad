"""Copia el bundle de la UI dentro del paquete, para que la wheel lo lleve.

    npm --prefix ui run build          # genera ui/dist
    python scripts/stage_ui.py         # ui/dist -> core/apolo/webui
    python -m build core               # wheel CON la UI incluida

`core/apolo/webui/` es artefacto de build (está en .gitignore): NO se versiona, se
regenera antes de publicar. Sin él la wheel sigue siendo válida — la API queda
headless y el servidor MCP funciona igual.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ui" / "dist"
DST = ROOT / "core" / "apolo" / "webui"


def main() -> int:
    if not (SRC / "index.html").is_file():
        print(f"No hay build de la UI en {SRC}", file=sys.stderr)
        print("Ejecuta primero:  npm --prefix ui run build", file=sys.stderr)
        return 1

    if DST.exists():
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST)

    files = sum(1 for p in DST.rglob("*") if p.is_file())
    size_mb = sum(p.stat().st_size for p in DST.rglob("*") if p.is_file()) / 1e6
    print(f"UI empaquetada en {DST}  ({files} archivos, {size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
