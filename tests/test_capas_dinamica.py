"""La dinámica de V8.2 no conoce el documento ni el transporte (plan V8.2, F1).

`physics/dinamica*.py`, `banda.py` y `sensores.py` reciben la escena y los dicts de juntas,
fijadores y anclajes, nunca un `Document`, y no importan `apolo.api`, `apolo.doc` ni
`apolo.state`: el bucle de MuJoCo corre bajo `PHYSICS_LOCK` sobre datos puros (patrón de
dos fases) y V8.3 lo moverá a un proceso aparte sin arrastrar la sesión. El helper de Kloss
(`library/engineering/motor_induccion.py`) es más estricto: puro, sin `apolo` ni geometría.

Stdlib pura (el AST); no importa `apolo`.
"""

from __future__ import annotations

import ast
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
FISICA = RAIZ / "core" / "apolo" / "physics"
KLOSS = RAIZ / "core" / "apolo" / "library" / "engineering" / "motor_induccion.py"

PROHIBIDOS = ("apolo.api", "apolo.doc", "apolo.state", "fastapi", "starlette")
NOMBRES_PROHIBIDOS = {"Document", "DOC", "STORE", "PROJECT_ID", "STATE_LOCK"}


def modulos() -> list[Path]:
    return sorted([*FISICA.glob("dinamica*.py"), FISICA / "banda.py", FISICA / "sensores.py"])


def _imports(archivo: Path) -> list[tuple[int, str]]:
    paquete = ".".join(archivo.relative_to(RAIZ / "core").with_suffix("").parts[:-1])
    out = []
    for n in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            out += [(n.lineno, a.name) for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            if n.level:
                base = paquete.split(".")[: len(paquete.split(".")) - (n.level - 1)]
                out.append((n.lineno, ".".join(base + ([n.module] if n.module else []))))
            else:
                out.append((n.lineno, n.module or ""))
    return out


def violaciones(archivo: Path) -> list[str]:
    rel = archivo.relative_to(RAIZ).as_posix()
    errores = [f"{rel}:{ln}: importa `{mod}`" for ln, mod in _imports(archivo)
               if any(mod == p or mod.startswith(p + ".") for p in PROHIBIDOS)]
    for n in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Name) and n.id in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `{n.id}`")
        elif isinstance(n, ast.Attribute) and n.attr in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `.{n.attr}`")
    return errores


def test_existen_los_modulos_de_la_dinamica():
    nombres = {p.name for p in modulos()}
    assert {"dinamica.py", "dinamica_modelo.py", "banda.py", "sensores.py"} <= nombres


def test_la_dinamica_no_conoce_el_documento_ni_la_api():
    errores = [e for m in modulos() for e in violaciones(m)]
    assert not errores, "la dinámica trabaja sobre datos puros (V8.2 D1):\n" + "\n".join(errores)


def test_kloss_es_puro():
    mods = [m for _, m in _imports(KLOSS)]
    assert not [m for m in mods if m.split(".")[0] in ("apolo", "OCP", "build123d", "mujoco")], mods


def test_el_gate_caza_lo_que_prohibe(tmp_path, monkeypatch):
    import sys

    malo = tmp_path / "core" / "apolo" / "physics" / "dinamica_mala.py"
    malo.parent.mkdir(parents=True)
    malo.write_text(
        "from apolo.doc import Document\n"
        "import apolo.state\n"
        "from ..api.common import PHYSICS_LOCK\n"
        "def f(x):\n"
        "    return x.STATE_LOCK\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "RAIZ", tmp_path)
    errores = "\n".join(violaciones(malo))
    for esperado in ("`apolo.doc`", "`apolo.state`", "`apolo.api.common`", "nombra `.STATE_LOCK`"):
        assert esperado in errores, f"no cazó {esperado}:\n{errores}"
