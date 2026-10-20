"""`core/apolo/cosim/modelos/` es PURO (plan V8.3 D2, F2): un modelo por dispositivo que recibe
la ficha como dicts, sin MuJoCo, OCCT ni el documento.

Por qué un gate: los modelos corren en el worker de la co-simulación (F4, otro proceso) que no
debe cargar la geometría (F0 midió 6,3 s de import con OCP), y en tests sin MuJoCo. Más estricto
que `library/electrico`: de `apolo` sólo importa `apolo.cosim.modelos` (ni siquiera
`apolo.library`, cuyo `__init__` carga el catálogo y con él OCP). El test mira el AST archivo
por archivo (perezosos incluidos) y, en un subproceso por módulo, lo que de verdad se carga.

Stdlib pura: no importa `apolo` (en un worktree resolvería al checkout principal).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
MODELOS = RAIZ_REPO / "core" / "apolo" / "cosim" / "modelos"

#: Terceros que delatan física, geometría, render o transporte.
PROHIBIDOS_EXTERNOS = {"mujoco", "OCP", "build123d", "vtk", "vtkmodules", "fastapi", "starlette"}
NOMBRES_PROHIBIDOS = {"Document", "DOC", "STORE", "PROJECT_ID", "STATE_LOCK", "PHYSICS_LOCK"}


def modulos() -> list[Path]:
    return sorted(p for p in MODELOS.rglob("*.py") if "__pycache__" not in p.parts)


def _imports(tree: ast.AST, archivo: Path) -> list[tuple[int, str]]:
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
        elif partes[0] == "apolo" and tuple(partes[1:3]) != ("cosim", "modelos"):
            errores.append(f"{rel}:{linea}: importa `{mod}` (fuera de cosim.modelos)")
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `{n.id}`")
        elif isinstance(n, ast.Attribute) and n.attr in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `.{n.attr}`")
    return errores


def test_existe_el_paquete():
    nombres = {p.name for p in modulos()}
    assert {"__init__.py", "base.py", "protecciones.py", "maniobra.py", "motor.py", "variador.py",
            "alimentacion.py", "plc_es.py", "mandos.py"} <= nombres


def test_los_modelos_no_conocen_el_documento_ni_la_fisica():
    errores = [e for m in modulos() for e in violaciones(m)]
    assert not errores, "cosim/modelos es puro (plan V8.3 D2):\n" + "\n".join(errores)


def test_cada_modulo_se_importa_solo():
    """Un proceso por módulo: importar un modelo no carga OCCT, MuJoCo, el catálogo ni el doc."""
    for archivo in modulos():
        nombre = ".".join(archivo.relative_to(RAIZ_REPO / "core").with_suffix("").parts)
        nombre = nombre.removesuffix(".__init__")
        codigo = (
            "import sys, importlib\n"
            f"importlib.import_module('{nombre}')\n"
            "pesados = [m for m in ('OCP', 'build123d', 'mujoco', 'apolo.library', "
            "'apolo.doc', 'apolo.kernel', 'apolo.state', 'apolo.physics', 'apolo.api') if m in sys.modules]\n"
            "assert not pesados, pesados\n"
        )
        res = subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, text=True, timeout=300)
        assert res.returncode == 0, f"{nombre} no se importa solo:\n{res.stderr[-2000:]}"


def test_el_gate_caza_lo_que_prohibe(tmp_path, monkeypatch):
    malo = tmp_path / "core" / "apolo" / "cosim" / "modelos" / "malo.py"
    malo.parent.mkdir(parents=True)
    malo.write_text(
        "import mujoco\n"
        "from apolo.library.engineering.motor_induccion import kloss_linealizado\n"
        "from ...physics.dinamica import simulate_dynamics\n"
        "def f(x):\n"
        "    import vtk\n"
        "    from .base import Modelo\n"
        "    return x.PHYSICS_LOCK\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "RAIZ_REPO", tmp_path)
    errores = "\n".join(violaciones(malo))
    for esperado in ("importa `mujoco`", "`apolo.library.engineering.motor_induccion`",
                     "`apolo.physics.dinamica`", "importa `vtk`", "nombra `.PHYSICS_LOCK`"):
        assert esperado in errores, f"no cazó {esperado}:\n{errores}"
    assert "base" not in errores  # import relativo dentro de modelos: vale
