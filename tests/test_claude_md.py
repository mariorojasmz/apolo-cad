"""Los CLAUDE.md tienen tope de tamaño y sus links no se rompen.

Los CLAUDE.md se cargan en cada sesión (el raíz siempre; uno anidado cuando la sesión lee
un archivo de su carpeta): cada línea cuesta contexto. El raíz llegó a 177 KB, se podó a
76 KB en julio sin un gate y volvió a crecer hasta 125 KB (plan `poda-claude-md`). Este
test hace que la poda dure:

  - raíz ≤ 30 KB;
  - `core/apolo/CLAUDE.md` ≤ 10 KB (se carga al leer CUALQUIER archivo del backend);
  - cualquier otro CLAUDE.md anidado ≤ 35 KB;
  - todo link relativo de un CLAUDE.md apunta a un archivo que existe.

Tamaño = bytes UTF-8 con saltos LF (CRLF del checkout de Windows no cuenta doble).

Correrlo como script imprime el tamaño de cada CLAUDE.md:
    python tests/test_claude_md.py

Stdlib pura: no importa `apolo`.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]

KB = 1024
TOPE_RAIZ = 30 * KB
TOPE_ANIDADO = 35 * KB
#: Anidados con tope propio (ruta relativa a la raíz del repo, con `/`).
TOPES_PROPIOS = {"core/apolo/CLAUDE.md": 10 * KB}

#: Nunca se recorren: worktrees de otras sesiones, dependencias, artefactos.
CARPETAS_IGNORADAS = {".git", ".claude", ".venv", "node_modules", "dist", "build", "webui", "__pycache__"}

#: `[texto](destino)` de markdown; el destino sin espacios.
LINK = re.compile(r"\]\(([^)\s]+)\)")


def claude_mds() -> list[str]:
    """Todos los CLAUDE.md del repo, como rutas relativas con `/`."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(RAIZ_REPO):
        dirnames[:] = [d for d in dirnames if d not in CARPETAS_IGNORADAS and not d.endswith(".egg-info")]
        if "CLAUDE.md" in filenames:
            out.append((Path(dirpath) / "CLAUDE.md").relative_to(RAIZ_REPO).as_posix())
    return sorted(out)


def tamano(rel: str) -> int:
    texto = (RAIZ_REPO / rel).read_bytes().decode("utf-8").replace("\r\n", "\n")
    return len(texto.encode("utf-8"))


def tope_de(rel: str) -> int:
    if rel == "CLAUDE.md":
        return TOPE_RAIZ
    return TOPES_PROPIOS.get(rel, TOPE_ANIDADO)


def links_rotos(rel: str) -> list[str]:
    archivo = RAIZ_REPO / rel
    rotos = []
    for n, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1):
        for destino in LINK.findall(linea):
            if re.match(r"^[a-z]+:", destino) or destino.startswith("#"):
                continue  # URL externa o ancla dentro del mismo archivo
            ruta = destino.split("#", 1)[0]
            if ruta and not (archivo.parent / ruta).exists():
                rotos.append(f"{rel}:{n}: {destino}")
    return rotos


def test_hay_raiz_y_anidados():
    encontrados = claude_mds()
    assert "CLAUDE.md" in encontrados
    assert len(encontrados) > 1, "se esperaban CLAUDE.md anidados (plan poda-claude-md)"


def test_ningun_claude_md_pasa_su_tope():
    pasados = [
        f"{rel}: {tamano(rel) / KB:.1f} KB > {tope_de(rel) / KB:.0f} KB"
        for rel in claude_mds()
        if tamano(rel) > tope_de(rel)
    ]
    assert not pasados, (
        "CLAUDE.md por encima de su tope (la historia va al plan, al devlog o al commit; "
        "el detalle de un paquete, a su CLAUDE.md):\n" + "\n".join(pasados)
    )


def test_los_links_relativos_existen():
    rotos = [r for rel in claude_mds() for r in links_rotos(rel)]
    assert not rotos, "Links rotos en CLAUDE.md:\n" + "\n".join(rotos)


def test_el_tamano_no_cuenta_crlf_doble(tmp_path, monkeypatch):
    (tmp_path / "CLAUDE.md").write_bytes("a\r\nb\r\n".encode("utf-8"))
    monkeypatch.setattr(__import__(__name__), "RAIZ_REPO", tmp_path)
    assert tamano("CLAUDE.md") == len(b"a\nb\n")


if __name__ == "__main__":
    for rel in claude_mds():
        print(f"{tamano(rel) / KB:6.1f} KB  (tope {tope_de(rel) / KB:.0f})  {rel}")
