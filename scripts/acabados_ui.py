"""Copia al visor la tabla de acabados (D5 de docs/plans/visor-realista.md).

    python -B scripts/acabados_ui.py            # sólo compara: sale con 1 si está desfasada
    python -B scripts/acabados_ui.py --escribir # reescribe ui/src/viewport/acabados.json

La fuente única es `core/apolo/library/apariencia.py`; el JSON es su copia para el navegador y
`tests/test_apariencia.py` falla si difieren. Escribe UTF-8 con LF (no uses `>` en PowerShell
5.1: escribe UTF-16).
"""

from __future__ import annotations

import sys
from pathlib import Path

from apolo.library.apariencia import json_ui

DESTINO = Path(__file__).resolve().parents[1] / "ui" / "src" / "viewport" / "acabados.json"


def main(argv: list[str]) -> int:
    texto = json_ui()
    # sin distinguir CRLF/LF: con core.autocrlf el checkout de Windows lo trae en CRLF
    actual = (DESTINO.read_bytes().decode("utf-8").replace("\r\n", "\n")
              if DESTINO.is_file() else None)
    if actual == texto:
        print(f"{DESTINO} al día")
        return 0
    if "--escribir" not in argv:
        print(f"{DESTINO} desfasado: corre con --escribir", file=sys.stderr)
        return 1
    DESTINO.write_bytes(texto.encode("utf-8"))
    print(f"{DESTINO} reescrito")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
