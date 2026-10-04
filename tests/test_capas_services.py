"""`core/apolo/services/` es la capa de dominio que LEE un `Document`: recibe `doc`
explícito, no conoce el transporte ni el agente y no toma locks.

Capas (plan `docs/plans/partir-api-main.md`, D2):
kernel/commands/doc/library/drawing/fea/assembly/robotics ← services ← api y agent.

Por qué un gate y no una convención: la lógica que vivía en `api/main.py` leía el `DOC`
GLOBAL aunque recibiera su `doc` (`_piece_dim_tols` medía con el documento activo y los tests
lo tapaban con `api.DOC = doc`), y un servicio que importa `fastapi` o `apolo.api` no lo
puede usar el agente (que no importa la API). Este test lo hace cumplir, archivo por
archivo, mirando el AST:
  - de `apolo` sólo importa las capas de abajo (y `services` mismo), también en los
    imports perezosos dentro de una función;
  - no importa `fastapi` ni `starlette`: un 400/404 es un error de DOMINIO que la API
    traduce;
  - no nombra el estado de sesión (`DOC`, `STORE`, `PROJECT_ID`, `AUTOSAVE_ERROR`,
    `STARTUP_ERROR`), ni `STATE_LOCK` (el llamador sostiene el lock), ni `HTTPException`, ni
    declara `global` sobre ellos.

Stdlib pura: no importa `apolo` (en un worktree resolvería al checkout principal). Que cada
módulo se importe SOLO lo comprueba un subproceso, que hereda el `PYTHONPATH`.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

RAIZ_REPO = Path(__file__).resolve().parents[1]
SERVICES = RAIZ_REPO / "core" / "apolo" / "services"

#: Paquetes/módulos de `apolo` que `services` puede importar: las capas de abajo y él
#: mismo. `batch` (lotes de comandos sobre un Document) es de la capa de `doc`.
PERMITIDOS = {"kernel", "commands", "doc", "library", "drawing", "fea", "assembly",
              "robotics", "batch", "services"}

#: Terceros que delatan transporte.
PROHIBIDOS_EXTERNOS = {"fastapi", "starlette"}

#: Nombres que un servicio no puede ni mencionar.
NOMBRES_PROHIBIDOS = {"DOC", "STORE", "PROJECT_ID", "AUTOSAVE_ERROR", "STARTUP_ERROR",
                      "STATE_LOCK", "HTTPException"}


def modulos() -> list[Path]:
    return sorted(p for p in SERVICES.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(p: Path) -> str:
    return p.relative_to(RAIZ_REPO).as_posix()


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
    rel = _rel(archivo)
    errores: list[str] = []
    for linea, mod in _imports(tree, archivo):
        partes = mod.split(".")
        if partes[0] in PROHIBIDOS_EXTERNOS:
            errores.append(f"{rel}:{linea}: importa `{mod}` (transporte)")
        elif partes[0] == "apolo" and (len(partes) < 2 or partes[1] not in PERMITIDOS):
            errores.append(f"{rel}:{linea}: importa `{mod}` (fuera de las capas de abajo)")
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and n.id in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{n.lineno}: nombra `{n.id}`")
        elif isinstance(n, ast.Global):
            for nombre in set(n.names) & NOMBRES_PROHIBIDOS:
                errores.append(f"{rel}:{n.lineno}: `global {nombre}`")
        elif isinstance(n, ast.alias) and (n.asname or n.name).split(".")[-1] in NOMBRES_PROHIBIDOS:
            errores.append(f"{rel}:{getattr(n, 'lineno', '?')}: importa `{n.name}`")
    return errores


def test_existe_la_capa():
    assert (SERVICES / "__init__.py").is_file()
    assert len(modulos()) > 1


def test_services_respeta_sus_fronteras():
    errores = [e for m in modulos() for e in violaciones(m)]
    assert not errores, (
        "services/ recibe `doc` explícito, sin transporte, sin sesión y sin locks "
        "(plan partir-api-main, D2):\n" + "\n".join(errores)
    )


def test_cada_modulo_se_importa_solo():
    """Un proceso por módulo: un ciclo de imports o una dependencia implícita de que otro
    módulo ya esté cargado revienta aquí, no en producción."""
    for archivo in modulos():
        nombre = ".".join(archivo.relative_to(RAIZ_REPO / "core").with_suffix("").parts)
        nombre = nombre.removesuffix(".__init__")
        res = subprocess.run([sys.executable, "-B", "-c", f"import {nombre}"],
                             capture_output=True, text=True, timeout=300)
        assert res.returncode == 0, f"{nombre} no se importa solo:\n{res.stderr[-2000:]}"


# ── El gate mismo ─────────────────────────────────────────────────────────────


def test_el_gate_caza_lo_que_prohibe(tmp_path, monkeypatch):
    malo = tmp_path / "core" / "apolo" / "services" / "malo.py"
    malo.parent.mkdir(parents=True)
    malo.write_text(
        "from fastapi import HTTPException\n"
        "import apolo.api.main as api\n"
        "from ..agent import chat_stream\n"
        "from apolo.state import STATE_LOCK\n"
        "def f(doc):\n"
        "    global DOC\n"
        "    from apolo.library.catalog import CATALOG\n"
        "    return DOC.scene\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "RAIZ_REPO", tmp_path)
    errores = "\n".join(violaciones(malo))
    for esperado in ("`fastapi`", "`apolo.api.main`", "`apolo.agent`", "`apolo.state`",
                     "nombra `DOC`", "`global DOC`", "importa `HTTPException`",
                     "importa `STATE_LOCK`"):
        assert esperado in errores, f"no cazó {esperado}:\n{errores}"
    assert "apolo.library.catalog" not in errores  # perezoso y de una capa de abajo: vale
