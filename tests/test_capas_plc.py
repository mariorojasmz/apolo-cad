"""`core/apolo/plc/` es PURO (plan V8.3 D2, F1): no conoce el documento, la API, el estado,
la física ni la geometría, y no trae dependencias nuevas.

Por qué: el PLC corre en el worker de la co-simulación (D11), un proceso aparte que no puede
arrastrar OCCT ni la sesión, y el compilador también lo usa la mutación `add_program` (F5).
Este gate mira el AST de cada módulo (imports perezosos incluidos):
  - de `apolo` sólo importa `plc` mismo;
  - de terceros, nada: sólo la biblioteca estándar (ni Lark, ni numpy, ni OCP/build123d);
  - no nombra `Document`, el estado de sesión ni `STATE_LOCK`;
  - `exec`, `eval` y `compile` sólo aparecen donde se arma el código verificado.

Stdlib pura: no importa `apolo` (en un worktree resolvería al checkout principal). Que el
paquete se importe sin OCCT lo comprueba un subproceso, que hereda el `PYTHONPATH`.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
PLC = RAIZ_REPO / "core" / "apolo" / "plc"

STDLIB_PERMITIDA = {"__future__", "ast", "collections", "dataclasses", "difflib", "fractions",
                    "math", "re", "time", "typing"}
NOMBRES_PROHIBIDOS = {"Document", "DOC", "STORE", "PROJECT_ID", "STATE_LOCK", "PHYSICS_LOCK"}
#: Dónde puede aparecer cada primitiva de ejecución dinámica.
DINAMICAS = {"exec": {"runtime.py"}, "compile": {"compilador.py"}, "eval": set()}


def modulos() -> list[Path]:
    return sorted(p for p in PLC.rglob("*.py") if "__pycache__" not in p.parts)


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
        if partes[0] == "apolo":
            if len(partes) < 2 or partes[1] != "plc":
                errores.append(f"{rel}:{linea}: importa `{mod}` (fuera de plc)")
        elif partes[0] not in STDLIB_PERMITIDA:
            errores.append(f"{rel}:{linea}: importa `{mod}` (plc sólo usa la stdlib)")
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `{n.id}`")
        elif isinstance(n, ast.Attribute) and n.attr in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `.{n.attr}`")
        elif (isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
              and n.func.id in DINAMICAS and archivo.name not in DINAMICAS[n.func.id]):
            errores.append(f"{rel}:{n.lineno}: llama `{n.func.id}` fuera de su lugar")
    return errores


def test_existe_el_paquete():
    nombres = {p.name for p in modulos()}
    assert {"lexer.py", "parser.py", "compilador.py", "runtime.py", "bloques.py",
            "verificador.py"} <= nombres


def test_plc_es_puro():
    errores = [e for m in modulos() for e in violaciones(m)]
    assert not errores, "plc/ es puro (V8.3 D2):\n" + "\n".join(errores)


def test_el_gate_caza_lo_que_prohibe(tmp_path, monkeypatch):
    malo = tmp_path / "core" / "apolo" / "plc" / "malo.py"
    malo.parent.mkdir(parents=True)
    malo.write_text(
        "import numpy\n"
        "from apolo.doc import Document\n"
        "from ..physics import dinamica\n"
        "def f(x):\n"
        "    eval('1')\n"
        "    return x.STATE_LOCK\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "RAIZ_REPO", tmp_path)
    errores = "\n".join(violaciones(malo))
    for esperado in ("`numpy`", "`apolo.doc`", "`apolo.physics`", "llama `eval`",
                     "nombra `.STATE_LOCK`"):
        assert esperado in errores, f"no cazó {esperado}:\n{errores}"


def test_importar_plc_no_carga_occt_ni_la_api():
    codigo = ("import sys, apolo.plc; "
              "malos = [m for m in ('OCP', 'build123d', 'mujoco', 'numpy', 'apolo.doc', "
              "'apolo.api', 'apolo.state', 'apolo.physics') if m in sys.modules]; "
              "print(malos)")
    r = subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "[]"
