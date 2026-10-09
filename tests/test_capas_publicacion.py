"""`core/apolo/publicacion/` es un cliente de la API y de las capas de dominio, y nadie lo
importa (plan publicacion-tienda, F4 · D1).

Por qué un gate: la publicación corre en un proceso aparte que le habla a la API por HTTP y
renderiza sobre su propia copia del documento. Si importara `apolo.api` o `apolo.state`,
arrastraría la sesión del servidor (y sus locks) a un proceso que no es el servidor; si algo
del backend la importara, el CAD cargaría el pipeline de video. Este test lo hace cumplir,
archivo por archivo, mirando el AST:
  - de `apolo` sólo importa `services`, `doc`, `kernel`, `media`, `paths` y a sí mismo
    (también en imports perezosos);
  - no importa transporte de servidor (`fastapi`, `starlette`) ni nombra la sesión;
  - ningún módulo de `core/apolo` fuera de él lo importa;
  - cada módulo se importa SOLO sin cargar el CAD (los imports pesados van dentro de las
    funciones), y `entregables` ni siquiera carga `apolo.services`: el benchmark lo importa.

Stdlib pura: no importa `apolo` (en un worktree resolvería al checkout principal).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
APOLO = RAIZ_REPO / "core" / "apolo"
PUBLICACION = APOLO / "publicacion"

PERMITIDOS = {"publicacion", "services", "doc", "kernel", "media", "paths"}
PROHIBIDOS_EXTERNOS = {"fastapi", "starlette"}
NOMBRES_PROHIBIDOS = {"DOC", "STORE", "PROJECT_ID", "STATE_LOCK", "RENDER_LOCK"}


def _py(carpeta: Path) -> list[Path]:
    return sorted(p for p in carpeta.rglob("*.py") if "__pycache__" not in p.parts)


def _imports(tree: ast.AST, archivo: Path) -> list[tuple[int, str]]:
    """(línea, módulo absoluto) de cada import, perezosos incluidos. `from apolo import x`
    cuenta como `apolo.x`."""
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
            if mod == "apolo":
                out += [(n.lineno, f"apolo.{a.name}") for a in n.names]
            else:
                out.append((n.lineno, mod))
    return out


def violaciones(archivo: Path) -> list[str]:
    tree = ast.parse(archivo.read_text(encoding="utf-8"))
    rel = archivo.relative_to(RAIZ_REPO).as_posix()
    errores = []
    for linea, mod in _imports(tree, archivo):
        partes = mod.split(".")
        if partes[0] in PROHIBIDOS_EXTERNOS:
            errores.append(f"{rel}:{linea}: importa `{mod}`")
        elif partes[0] == "apolo" and len(partes) > 1 and partes[1] not in PERMITIDOS \
                and partes[1] != "__version__":
            errores.append(f"{rel}:{linea}: importa `{mod}`")
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `{n.id}`")
        elif isinstance(n, ast.Attribute) and n.attr in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `.{n.attr}`")
    return errores


def test_existe_el_paquete():
    nombres = {p.name for p in _py(PUBLICACION)}
    assert {"__init__.py", "entregables.py", "ficha.py", "saneo.py", "video.py", "paquete.py",
            "textos.py", "flujo.py", "linea_tiempo.py"} <= nombres


def test_publicacion_solo_usa_las_capas_de_dominio():
    errores = [e for m in _py(PUBLICACION) for e in violaciones(m)]
    assert not errores, ("publicacion/ le habla a la API por HTTP y usa sólo services, doc, "
                         "kernel, media y paths:\n" + "\n".join(errores))


def test_nadie_importa_publicacion():
    errores = []
    for archivo in _py(APOLO):
        if PUBLICACION in archivo.parents:
            continue
        tree = ast.parse(archivo.read_text(encoding="utf-8"))
        for linea, mod in _imports(tree, archivo):
            if mod.split(".")[:2] == ["apolo", "publicacion"]:
                errores.append(f"{archivo.relative_to(RAIZ_REPO).as_posix()}:{linea}: `{mod}`")
    assert not errores, "el backend no importa la publicación (D1):\n" + "\n".join(errores)


def test_cada_modulo_se_importa_solo_y_liviano():
    for archivo in _py(PUBLICACION):
        nombre = ".".join(archivo.relative_to(RAIZ_REPO / "core").with_suffix("").parts)
        nombre = nombre.removesuffix(".__init__")
        pesados = ["OCP", "build123d", "vtkmodules", "apolo.doc", "apolo.kernel", "apolo.state",
                   "apolo.api", "fastapi"]
        if nombre.endswith("entregables"):
            pesados += ["apolo.services", "apolo.media", "PIL"]
        codigo = (f"import sys, {nombre}\n"
                  f"cargados = [m for m in {pesados!r} if m in sys.modules]\n"
                  "assert not cargados, cargados\n")
        res = subprocess.run([sys.executable, "-B", "-c", codigo],
                             capture_output=True, text=True, timeout=300)
        assert res.returncode == 0, f"{nombre} no se importa solo y liviano:\n{res.stderr[-2000:]}"


def test_el_gate_caza_lo_que_prohibe(tmp_path, monkeypatch):
    malo = tmp_path / "core" / "apolo" / "publicacion" / "malo.py"
    malo.parent.mkdir(parents=True)
    malo.write_text(
        "from apolo import state\n"
        "import apolo.api.main\n"
        "from ..library import catalog\n"
        "def f(x):\n"
        "    from fastapi import HTTPException\n"
        "    from .ficha import validar\n"
        "    from apolo import paths\n"
        "    return x.STATE_LOCK\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "RAIZ_REPO", tmp_path)
    errores = "\n".join(violaciones(malo))
    for esperado in ("`apolo.state`", "`apolo.api.main`", "`apolo.library`", "`fastapi`",
                     "nombra `.STATE_LOCK`"):
        assert esperado in errores, f"no cazó {esperado}:\n{errores}"
    assert "ficha" not in errores and "paths" not in errores
