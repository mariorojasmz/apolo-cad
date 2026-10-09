"""`core/apolo/library/electrico/` es PURO (plan V8.1 F2, marco V8 D15): recibe el modelo
eléctrico evaluado y la ficha de catálogo, nunca un `Document`.

Por qué un gate: el ERC y las redes tienen que poder correr en el carril del documento (F3), en
la co-simulación (V8.3, otro proceso) y en tests sin OCCT. Si `library/electrico` importara
`doc`, `kernel`, `api` o el catálogo (que carga los builders y con ellos OCP), arrastraría la
geometría y la sesión a algo que sólo suma bornes y tensiones. El test mira el AST, archivo por
archivo:
  - de `apolo` sólo importa `library.electrico` mismo (también en imports perezosos);
  - no importa geometría ni transporte (`OCP`, `build123d`, `vtk`, `fastapi`, `starlette`);
  - no nombra `Document`, el estado de sesión (`DOC`, `STORE`, `PROJECT_ID`) ni `STATE_LOCK`.

Stdlib pura: no importa `apolo` (en un worktree resolvería al checkout principal). Que cada
módulo se importe SOLO lo comprueba un subproceso que hereda el `PYTHONPATH`; como
`apolo/library/__init__.py` carga el catálogo, el subproceso registra un paquete `apolo.library`
vacío con la misma ruta, para medir lo que trae `electrico` y nada más.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
ELECTRICO = RAIZ_REPO / "core" / "apolo" / "library" / "electrico"

#: Módulos de `apolo` que `library/electrico` puede importar: sólo él mismo.
PERMITIDO = ("library", "electrico")

#: Terceros que delatan geometría, render o transporte.
PROHIBIDOS_EXTERNOS = {"OCP", "build123d", "vtk", "vtkmodules", "fastapi", "starlette"}

#: Nombres que un módulo puro no puede ni mencionar.
NOMBRES_PROHIBIDOS = {"Document", "DOC", "STORE", "PROJECT_ID", "STATE_LOCK"}


def modulos() -> list[Path]:
    return sorted(p for p in ELECTRICO.rglob("*.py") if "__pycache__" not in p.parts)


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
        elif partes[0] == "apolo" and tuple(partes[1:3]) != PERMITIDO:
            errores.append(f"{rel}:{linea}: importa `{mod}` (fuera de library.electrico)")
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
    assert {"__init__.py", "modelo.py", "ficha.py", "tension.py", "referencias.py", "redes.py",
            "erc.py"} <= nombres


def test_electrico_no_conoce_el_documento_ni_la_geometria():
    errores = [e for m in modulos() for e in violaciones(m)]
    assert not errores, (
        "library/electrico/ es puro: recibe el modelo evaluado, nunca un Document "
        "(plan V8.1 F2):\n" + "\n".join(errores)
    )


def test_cada_modulo_se_importa_solo():
    """Un proceso por módulo: importar `library.electrico.*` no carga OCCT, el catálogo ni el doc."""
    for archivo in modulos():
        nombre = ".".join(archivo.relative_to(RAIZ_REPO / "core").with_suffix("").parts)
        nombre = nombre.removesuffix(".__init__")
        codigo = (
            "import sys, types, importlib, apolo, pathlib\n"
            "lib = types.ModuleType('apolo.library')\n"
            "lib.__path__ = [str(pathlib.Path(apolo.__file__).parent / 'library')]\n"
            "sys.modules['apolo.library'] = lib\n"
            f"importlib.import_module('{nombre}')\n"
            "pesados = [m for m in ('OCP', 'build123d', 'vtkmodules', 'apolo.doc', 'apolo.kernel', "
            "'apolo.state', 'apolo.library.catalog', 'apolo.library.loader') if m in sys.modules]\n"
            "assert not pesados, pesados\n"
        )
        res = subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, text=True, timeout=300)
        assert res.returncode == 0, f"{nombre} no se importa solo:\n{res.stderr[-2000:]}"


# ── El gate mismo ─────────────────────────────────────────────────────────────


def test_el_gate_caza_lo_que_prohibe(tmp_path, monkeypatch):
    malo = tmp_path / "core" / "apolo" / "library" / "electrico" / "malo.py"
    malo.parent.mkdir(parents=True)
    malo.write_text(
        "from apolo.doc import Document\n"
        "import apolo.state\n"
        "from ..catalog import CATALOG\n"
        "from ...kernel.render_vtk import render_snapshot_vtk\n"
        "def f(x):\n"
        "    import OCP\n"
        "    from apolo.api.main import DOC\n"
        "    from .redes import analizar\n"
        "    return x.STATE_LOCK\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "RAIZ_REPO", tmp_path)
    errores = "\n".join(violaciones(malo))
    for esperado in ("`apolo.doc`", "`apolo.state`", "`apolo.library.catalog`",
                     "`apolo.kernel.render_vtk`", "importa `OCP`", "`apolo.api.main`",
                     "importa `Document`", "importa `DOC`", "nombra `.STATE_LOCK`"):
        assert esperado in errores, f"no cazó {esperado}:\n{errores}"
    assert "redes" not in errores  # import relativo dentro de electrico: vale
