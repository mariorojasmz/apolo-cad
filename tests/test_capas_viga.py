"""La viga continua y las secciones (plan flecha-de-bastidor F1) son PURAS.

`library` nunca recibe un `Document` (CLAUDE.md raíz): estos dos módulos reciben números y la
ficha (`builder`, `params`) de una pieza, y la regla de F2 (`services`) los alimenta. El test
mira el AST: de `apolo` sólo pueden importar `library.engineering` y `library.structural`; nada
de geometría ni transporte. Y un subproceso comprueba que importarlos no carga OCCT, el
catálogo ni el documento (con un paquete `apolo.library` vacío, como `test_capas_electrico`).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
ENGINEERING = RAIZ_REPO / "core" / "apolo" / "library" / "engineering"
MODULOS = (ENGINEERING / "viga_continua.py", ENGINEERING / "secciones.py")

PERMITIDOS = ("apolo.library.engineering", "apolo.library.structural")
PROHIBIDOS_EXTERNOS = {"OCP", "build123d", "vtk", "vtkmodules", "fastapi", "starlette"}
NOMBRES_PROHIBIDOS = {"Document", "DOC", "STORE", "PROJECT_ID", "STATE_LOCK"}


def _imports(archivo: Path) -> list[tuple[int, str]]:
    tree = ast.parse(archivo.read_text(encoding="utf-8"))
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
    errores = []
    for linea, mod in _imports(archivo):
        if mod.split(".")[0] in PROHIBIDOS_EXTERNOS:
            errores.append(f"{archivo.name}:{linea}: importa `{mod}`")
        elif mod.startswith("apolo") and not mod.startswith(PERMITIDOS):
            errores.append(f"{archivo.name}:{linea}: importa `{mod}`")
    for n in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
        nombre = n.id if isinstance(n, ast.Name) else n.attr if isinstance(n, ast.Attribute) else None
        if nombre in NOMBRES_PROHIBIDOS:
            errores.append(f"{archivo.name}:{n.lineno}: nombra `{nombre}`")
    return errores


def test_modulos_puros():
    errores = [e for m in MODULOS for e in violaciones(m)]
    assert not errores, "viga continua / secciones son puras (flecha-de-bastidor F1):\n" + "\n".join(errores)


def test_se_importan_sin_occt_ni_documento():
    for archivo in MODULOS:
        nombre = "apolo.library.engineering." + archivo.stem
        codigo = (
            "import sys, types, importlib, apolo, pathlib\n"
            "lib = types.ModuleType('apolo.library')\n"
            "lib.__path__ = [str(pathlib.Path(apolo.__file__).parent / 'library')]\n"
            "sys.modules['apolo.library'] = lib\n"
            f"importlib.import_module('{nombre}')\n"
            "pesados = [m for m in ('OCP', 'build123d', 'vtkmodules', 'apolo.doc', 'apolo.kernel', "
            "'apolo.api', 'apolo.state', 'apolo.library.catalog', 'apolo.library.loader') "
            "if m in sys.modules]\n"
            "assert not pesados, pesados\n"
        )
        res = subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, text=True, timeout=300)
        assert res.returncode == 0, f"{nombre} no se importa solo:\n{res.stderr[-2000:]}"


def test_el_gate_caza_lo_prohibido(tmp_path):
    malo = tmp_path / "core" / "apolo" / "library" / "engineering" / "malo.py"
    malo.parent.mkdir(parents=True)
    malo.write_text("from apolo.doc import Document\nfrom ...kernel import shapes\nimport OCP\n"
                    "from .secciones import Seccion\nx = DOC\n", encoding="utf-8")
    global RAIZ_REPO
    previo, RAIZ_REPO = RAIZ_REPO, tmp_path
    try:
        errores = "\n".join(violaciones(malo))
    finally:
        RAIZ_REPO = previo
    for esperado in ("`apolo.doc`", "`apolo.kernel`", "`OCP`", "nombra `DOC`"):
        assert esperado in errores, errores
    assert "secciones" not in errores
