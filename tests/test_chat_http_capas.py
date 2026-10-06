"""Las fronteras del chat HTTP (plan chat-cliente-igual F5a, D4): lo que se lee del código.

- D4a/D4c: desde ningún módulo nuevo de `apolo.agent` una cadena de imports llega a
  `apolo.state`, `apolo.api` ni `anyio` (transitivo, perezosos e `import_module` incluidos);
- el endpoint del chat nuevo no nombra `STATE_LOCK`;
- la cabecera es la de la guardia, la URL loopback sale del socket (o `APOLO_URL_INTERNA`), los
  recordatorios de modo sólo nombran tools del chat y los textos para la persona pasan el
  mismo gate que las pistas (`test_pistas.py::faltas`).
"""

from __future__ import annotations

import ast
import importlib.util
import re
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from apolo.agent import chat, herramientas  # noqa: E402
from apolo.api import guardia_documento  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
AGENTE = RAIZ / "core" / "apolo" / "agent"
#: El chat viejo y lo que sólo él usa: F5b los borra (y esta lista con ellos).
EXENTOS = {"agent.py", "hooks.py", "__init__.py"}
PROHIBIDOS = ("apolo.state", "apolo.api")


def _archivo(modulo: str) -> Path | None:
    base = RAIZ / "core" / Path(*modulo.split("."))
    for p in (base.with_suffix(".py"), base / "__init__.py"):
        if p.is_file():
            return p
    return None


def _importados(modulo: str, archivo: Path) -> set[str]:
    """Los módulos que `archivo` importa (perezosos y `importlib.import_module` incluidos)."""
    paquete = modulo if archivo.name == "__init__.py" else modulo.rpartition(".")[0]
    out: set[str] = set()
    for n in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            base = n.module or ""
            if n.level:
                partes = paquete.split(".")[: len(paquete.split(".")) - (n.level - 1)]
                base = ".".join(partes + ([n.module] if n.module else []))
            out.add(base)
            out |= {f"{base}.{a.name}" for a in n.names if _archivo(f"{base}.{a.name}")}
        elif (isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "import_module"
              and n.args and isinstance(n.args[0], ast.Constant)):
            out.add(n.args[0].value)
    # importar `a.b.c` importa también los paquetes `a.b` y `a`
    return out | {m.rsplit(".", k)[0] for m in out for k in range(1, m.count(".") + 1)}


def test_el_chat_nuevo_no_importa_estado_ni_api_ni_anyio():
    """D4a y D4c, transitivo: desde cada módulo nuevo de `apolo.agent` ninguna cadena de
    imports llega a `apolo.state`, `apolo.api` ni `anyio` (el paquete `apolo.agent` y el chat
    viejo quedan exentos hasta F5b)."""
    assert EXENTOS <= {p.name for p in AGENTE.glob("*.py")}, "F5b: achica EXENTOS"
    nuevos = sorted(f"apolo.agent.{p.stem}" for p in AGENTE.glob("*.py") if p.name not in EXENTOS)
    assert {"apolo.agent.chat", "apolo.agent.eventos", "apolo.agent.herramientas",
            "apolo.agent.modelo"} <= set(nuevos)
    exentos = {"apolo.agent"} | {f"apolo.agent.{Path(e).stem}" for e in EXENTOS}
    for inicio in nuevos:
        vistos, pendientes = set(), [(inicio, (inicio,))]
        while pendientes:
            modulo, cadena = pendientes.pop()
            assert not modulo.startswith(PROHIBIDOS) and modulo.split(".")[0] != "anyio", (
                " → ".join(cadena))
            archivo = _archivo(modulo) if modulo.startswith("apolo") else None
            if archivo is None or modulo in vistos or (modulo in exentos and modulo != inicio):
                continue
            vistos.add(modulo)
            pendientes += [(m, (*cadena, m)) for m in _importados(modulo, archivo)]
        assert "apolo.mcp_server" in vistos or inicio != "apolo.agent.herramientas"


def test_el_endpoint_nuevo_no_nombra_state_lock():
    arbol = ast.parse((RAIZ / "core/apolo/api/routers/core.py").read_text(encoding="utf-8"))
    (fn,) = [n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name == "_chat_http"]
    assert "STATE_LOCK" not in {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)}


def test_la_cabecera_es_la_de_la_guardia():
    assert chat.CABECERA == guardia_documento.CABECERA


def test_url_interna(monkeypatch):
    monkeypatch.delenv("APOLO_URL_INTERNA", raising=False)
    assert chat.url_interna(("127.0.0.1", 8123)) == "http://127.0.0.1:8123"
    assert chat.url_interna(("0.0.0.0", 8000)) == "http://127.0.0.1:8000"
    assert chat.url_interna(("::1", 8000)) == "http://[::1]:8000"
    assert chat.url_interna(("::", 8000)) == "http://[::1]:8000"
    for sin in (None, ("/tmp/apolo.sock", None)):
        with pytest.raises(ValueError, match="APOLO_URL_INTERNA"):
            chat.url_interna(sin)
    monkeypatch.setenv("APOLO_URL_INTERNA", "http://apolo.interno:9000/")
    assert chat.url_interna(None) == "http://apolo.interno:9000"


def test_los_recordatorios_solo_nombran_tools_del_chat():
    nombres = {d["name"] for d in herramientas.definiciones()}
    for texto in chat.RECORDATORIO.values():
        assert set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", texto)) <= nombres


def test_los_textos_para_la_persona_cumplen_el_estandar():
    spec = importlib.util.spec_from_file_location("_pistas_gate", RAIZ / "tests" / "test_pistas.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    for texto in (chat.LLENO, chat.PROYECTO_CAMBIO, chat.SIN_PROYECTO, chat.FALLO):
        assert gate.faltas(texto) == [], f"«{texto}»: {gate.faltas(texto)}"
