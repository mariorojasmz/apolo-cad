"""`core/apolo/cosim/modelos/` y `core/apolo/cosim/red/` son PUROS (plan V8.3 D2, F2 y F3): los
modelos de dispositivo reciben la ficha como dicts y las redes el formato plano de
`cosim/red/entrada.py`, sin MuJoCo, OCCT ni el documento.

Por qué un gate: corren en el worker de la co-simulación (F4, otro proceso) que no debe cargar la
geometría (F0 midió 6,3 s de import con OCP), y en tests sin MuJoCo. Más estricto que
`library/electrico`: de `apolo` cada paquete sólo se importa a sí mismo (ni siquiera
`apolo.library`, cuyo `__init__` carga el catálogo y con él OCP; por eso la traducción del modelo
eléctrico de V8.1 al formato plano vive en `services/cosim_red.py`). Las redes usan numpy y el
LAPACK de scipy, nada más. El test mira el AST archivo por archivo (perezosos incluidos) y, en un
subproceso por módulo, lo que de verdad se carga.

Stdlib pura: no importa `apolo` (en un worktree resolvería al checkout principal).
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ_REPO = Path(__file__).resolve().parents[1]
COSIM = RAIZ_REPO / "core" / "apolo" / "cosim"
#: paquete → lo único de `apolo` que puede importar.
PAQUETES = {"modelos": ("cosim", "modelos"), "red": ("cosim", "red")}

#: Terceros que delatan física, geometría, render o transporte.
PROHIBIDOS_EXTERNOS = {"mujoco", "OCP", "build123d", "vtk", "vtkmodules", "fastapi", "starlette"}
NOMBRES_PROHIBIDOS = {"Document", "DOC", "STORE", "PROJECT_ID", "STATE_LOCK", "PHYSICS_LOCK"}


def modulos(paquete: str = "modelos") -> list[Path]:
    return sorted(p for p in (COSIM / paquete).rglob("*.py") if "__pycache__" not in p.parts)


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


def violaciones(archivo: Path, permitido: tuple[str, str] = PAQUETES["modelos"]) -> list[str]:
    tree = ast.parse(archivo.read_text(encoding="utf-8"))
    rel = archivo.relative_to(RAIZ_REPO).as_posix()
    errores: list[str] = []
    for linea, mod in _imports(tree, archivo):
        partes = mod.split(".")
        if partes[0] in PROHIBIDOS_EXTERNOS:
            errores.append(f"{rel}:{linea}: importa `{mod}`")
        elif partes[0] == "apolo" and tuple(partes[1:3]) != permitido:
            errores.append(f"{rel}:{linea}: importa `{mod}` (fuera de {'.'.join(permitido)})")
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `{n.id}`")
        elif isinstance(n, ast.Attribute) and n.attr in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `.{n.attr}`")
    return errores


def test_existen_los_paquetes():
    assert {"__init__.py", "base.py", "protecciones.py", "maniobra.py", "motor.py", "variador.py",
            "alimentacion.py", "plc_es.py", "mandos.py"} <= {p.name for p in modulos("modelos")}
    assert {"__init__.py", "entrada.py", "topologia.py", "mna.py", "nodal.py", "mando.py", "potencia.py",
            "conductores.py", "fasores.py"} <= {p.name for p in modulos("red")}


@pytest.mark.parametrize("paquete", sorted(PAQUETES))
def test_no_conocen_el_documento_ni_la_fisica(paquete):
    errores = [e for m in modulos(paquete) for e in violaciones(m, PAQUETES[paquete])]
    assert not errores, f"cosim/{paquete} es puro (plan V8.3 D2):\n" + "\n".join(errores)


@pytest.mark.parametrize("paquete", sorted(PAQUETES))
def test_cada_modulo_se_importa_solo(paquete):
    """Un proceso por módulo: importar un modelo o una red no carga OCCT, MuJoCo, el catálogo ni
    el doc (y las redes tampoco los modelos de F2: no los necesitan)."""
    pesados = ["OCP", "build123d", "mujoco", "apolo.library", "apolo.doc", "apolo.kernel", "apolo.state",
               "apolo.physics", "apolo.api"] + (["apolo.cosim.modelos"] if paquete == "red" else [])
    for archivo in modulos(paquete):
        nombre = ".".join(archivo.relative_to(RAIZ_REPO / "core").with_suffix("").parts)
        nombre = nombre.removesuffix(".__init__")
        codigo = (
            "import sys, importlib\n"
            f"importlib.import_module('{nombre}')\n"
            f"pesados = [m for m in {pesados!r} if m in sys.modules]\n"
            "assert not pesados, pesados\n"
        )
        res = subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, text=True, timeout=300)
        assert res.returncode == 0, f"{nombre} no se importa solo:\n{res.stderr[-2000:]}"


def test_el_gate_caza_lo_que_prohibe(tmp_path, monkeypatch):
    malo = tmp_path / "core" / "apolo" / "cosim" / "red" / "malo.py"
    malo.parent.mkdir(parents=True)
    malo.write_text(
        "import mujoco\n"
        "from apolo.library.electrico.modelo import Dispositivo\n"
        "from ..modelos import crear_modelo\n"
        "from ...physics.dinamica import simulate_dynamics\n"
        "def f(x):\n"
        "    import vtk\n"
        "    from .mna import Sistema\n"
        "    return x.PHYSICS_LOCK\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "RAIZ_REPO", tmp_path)
    errores = "\n".join(violaciones(malo, PAQUETES["red"]))
    for esperado in ("importa `mujoco`", "`apolo.library.electrico.modelo`", "`apolo.cosim.modelos`",
                     "`apolo.physics.dinamica`", "importa `vtk`", "nombra `.PHYSICS_LOCK`"):
        assert esperado in errores, f"no cazó {esperado}:\n{errores}"
    assert "mna" not in errores  # import relativo dentro de red: vale
