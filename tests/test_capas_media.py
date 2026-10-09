"""`core/apolo/media/` compone y codifica el video SIN conocer el documento (plan
publicacion-tienda, F3): recibe imágenes, textos y rutas, nunca un `Document`.

Por qué un gate: el video se arma en un proceso aparte (D1) a partir de fotogramas que
le pasan F1 y F2. Si `media` importara `doc`, `kernel` o el estado de la API, el pipeline
arrastraría OCCT y la sesión a algo que sólo dibuja texto y habla con ffmpeg, y dejaría de
poder probarse aislado. Este test lo hace cumplir, archivo por archivo, mirando el AST:
  - de `apolo` sólo importa `media` mismo (también en imports perezosos);
  - no importa geometría ni render (`OCP`, `build123d`, `vtk`) ni transporte (`fastapi`,
    `starlette`);
  - no nombra `Document`, el estado de sesión (`DOC`, `STORE`, `PROJECT_ID`) ni
    `STATE_LOCK`.

Stdlib pura: no importa `apolo` (en un worktree resolvería al checkout principal). Que cada
módulo se importe SOLO lo comprueba un subproceso, que hereda el `PYTHONPATH`.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
MEDIA = RAIZ_REPO / "core" / "apolo" / "media"

#: Módulos de `apolo` que `media` puede importar: sólo él mismo.
PERMITIDOS = {"media"}

#: Terceros que delatan geometría, render o transporte.
PROHIBIDOS_EXTERNOS = {"OCP", "build123d", "vtk", "vtkmodules", "fastapi", "starlette"}

#: Nombres que un módulo de `media` no puede ni mencionar.
NOMBRES_PROHIBIDOS = {"Document", "DOC", "STORE", "PROJECT_ID", "STATE_LOCK"}


def modulos() -> list[Path]:
    return sorted(p for p in MEDIA.rglob("*.py") if "__pycache__" not in p.parts)


def _imports(tree: ast.AST, archivo: Path) -> list[tuple[int, str]]:
    """(línea, módulo absoluto) de cada import del archivo, perezosos incluidos."""
    paquete = ".".join(archivo.relative_to(RAIZ_REPO / "core").with_suffix("").parts[:-1])
    out: list[tuple[int, str]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out += [(n.lineno, a.name) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                base = paquete.split(".")[: len(paquete.split(".")) - (n.level - 1)]
                mod = ".".join(base + ([n.module] if n.module else []))
            else:
                mod = n.module or ""
            out.append((n.lineno, mod))
    return out


def violaciones(archivo: Path) -> list[str]:
    tree = ast.parse(archivo.read_text(encoding="utf-8"))
    rel = archivo.relative_to(RAIZ_REPO).as_posix()
    errores: list[str] = []
    for linea, mod in _imports(tree, archivo):
        partes = mod.split(".")
        if partes[0] in PROHIBIDOS_EXTERNOS:
            errores.append(f"{rel}:{linea}: importa `{mod}`")
        elif partes[0] == "apolo" and (len(partes) < 2 or partes[1] not in PERMITIDOS):
            errores.append(f"{rel}:{linea}: importa `{mod}` (fuera de media)")
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `{n.id}`")
        elif isinstance(n, ast.Attribute) and n.attr in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `.{n.attr}`")
        elif isinstance(n, ast.alias) and (n.asname or n.name).split(".")[-1] in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{getattr(n, 'lineno', '?')}: importa `{n.name}`")
    return errores


def test_existe_el_paquete():
    nombres = {p.name for p in modulos()}
    assert {"__init__.py", "composicion.py", "codificar.py"} <= nombres


def test_media_no_conoce_el_documento():
    errores = [e for m in modulos() for e in violaciones(m)]
    assert not errores, (
        "media/ recibe imágenes, textos y rutas; nunca un Document ni la sesión "
        "(plan publicacion-tienda, F3):\n" + "\n".join(errores)
    )


def test_cada_modulo_se_importa_solo():
    """Un proceso por módulo, y sin arrastrar el CAD: importar `media` no carga OCCT ni VTK."""
    for archivo in modulos():
        nombre = ".".join(archivo.relative_to(RAIZ_REPO / "core").with_suffix("").parts)
        nombre = nombre.removesuffix(".__init__")
        codigo = (f"import sys, {nombre}\n"
                  "pesados = [m for m in ('OCP', 'build123d', 'vtkmodules', 'apolo.doc', "
                  "'apolo.kernel', 'apolo.state') if m in sys.modules]\n"
                  "assert not pesados, pesados\n")
        res = subprocess.run([sys.executable, "-B", "-c", codigo],
                             capture_output=True, text=True, timeout=300)
        assert res.returncode == 0, f"{nombre} no se importa solo:\n{res.stderr[-2000:]}"


# ── El gate mismo ─────────────────────────────────────────────────────────────


def test_el_gate_caza_lo_que_prohibe(tmp_path, monkeypatch):
    malo = tmp_path / "core" / "apolo" / "media" / "malo.py"
    malo.parent.mkdir(parents=True)
    malo.write_text(
        "from apolo.doc import Document\n"
        "import apolo.state\n"
        "from ..kernel.render_vtk import render_snapshot_vtk\n"
        "from ..commands import registry\n"
        "def f(x):\n"
        "    import vtk\n"
        "    from apolo.api.main import DOC\n"
        "    from .composicion import portada\n"
        "    return x.STATE_LOCK\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "RAIZ_REPO", tmp_path)
    errores = "\n".join(violaciones(malo))
    for esperado in ("`apolo.doc`", "`apolo.state`", "`apolo.kernel.render_vtk`",
                     "`apolo.commands`", "importa `vtk`", "`apolo.api.main`",
                     "importa `Document`", "importa `DOC`", "nombra `.STATE_LOCK`"):
        assert esperado in errores, f"no cazó {esperado}:\n{errores}"
    assert "composicion" not in errores  # import relativo dentro de media: vale
