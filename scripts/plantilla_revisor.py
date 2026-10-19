"""Regenera `docs/revisor-de-taller.md` desde `core/apolo/design/revision.py`.

    python -B scripts/plantilla_revisor.py            # reescribe la plantilla
    python -B scripts/plantilla_revisor.py --comparar # exit 1 si está desactualizada

La plantilla del revisor de taller no se edita a mano: las preguntas viven en el módulo
(fuente única) y `tests/test_revision_taller.py` exige que el archivo coincida.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# Mide ESTE árbol: en un worktree el venv apunta al checkout principal (CLAUDE.md raíz).
if str(RAIZ / "core") not in sys.path:
    sys.path.insert(0, str(RAIZ / "core"))

from apolo.design.revision import plantilla_revisor  # noqa: E402

DESTINO = RAIZ / "docs" / "revisor-de-taller.md"


def main(argv: list[str]) -> int:
    texto = plantilla_revisor()
    if "--comparar" in argv:
        actual = DESTINO.read_text(encoding="utf-8").replace("\r\n", "\n") if DESTINO.exists() else ""
        if actual != texto:
            print(f"{DESTINO.relative_to(RAIZ)} está desactualizada: corre "
                  "python -B scripts/plantilla_revisor.py")
            return 1
        return 0
    DESTINO.write_text(texto, encoding="utf-8", newline="\n")
    print(f"escrito {DESTINO.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
