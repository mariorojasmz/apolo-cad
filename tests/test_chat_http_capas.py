"""Las fronteras del chat HTTP (plan chat-cliente-igual F5a/F5b, D4): lo que se lee del código.

- D4a/D4c: desde ningún módulo de `apolo.agent` (el paquete incluido, sin exentos desde la F5b)
  una cadena de imports llega a `apolo.state`, `apolo.api` ni `anyio` (transitivo, perezosos e
  `import_module` incluidos);
- el endpoint del chat no nombra `STATE_LOCK`;
- la cabecera es la de la guardia, la URL loopback sale del socket (o `APOLO_URL_INTERNA`), los
  recordatorios de modo van en una etiqueta propia y sólo nombran tools del chat, y los textos
  para la persona pasan el mismo gate que las pistas (`test_pistas.py::faltas`).
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
#: Módulos de `agent/` que el gate no recorre. Vacío desde la F5b (borró el chat viejo, que
#: tomaba `STATE_LOCK`): uno nuevo que haga falta eximir se anota aquí con su porqué.
EXENTOS: set[str] = set()
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


def _modulo(archivo: Path) -> str:
    return "apolo.agent" if archivo.name == "__init__.py" else f"apolo.agent.{archivo.stem}"


def test_ningun_modulo_del_agente_importa_estado_ni_api_ni_anyio():
    """D4a y D4c, transitivo: desde cada módulo de `apolo.agent` —el paquete incluido—
    ninguna cadena de imports llega a `apolo.state`, `apolo.api` ni `anyio`."""
    assert EXENTOS <= {p.name for p in AGENTE.glob("*.py")}, "EXENTOS nombra archivos que no hay"
    todos = sorted(_modulo(p) for p in AGENTE.glob("*.py") if p.name not in EXENTOS)
    assert {"apolo.agent", "apolo.agent.chat", "apolo.agent.eventos",
            "apolo.agent.herramientas", "apolo.agent.modelo"} <= set(todos)
    exentos = {_modulo(AGENTE / e) for e in EXENTOS}
    for inicio in todos:
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


def test_el_endpoint_del_chat_no_nombra_state_lock():
    arbol = ast.parse((RAIZ / "core/apolo/api/routers/core.py").read_text(encoding="utf-8"))
    (fn,) = [n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef) and n.name == "agent_chat"]
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


def _sin_etiqueta(texto: str) -> str:
    """El recordatorio sin su envoltorio `<modo_del_turno>…</modo_del_turno>`."""
    abre, cierra = f"<{chat.ETIQUETA_MODO}>", f"</{chat.ETIQUETA_MODO}>"
    assert texto.startswith(abre) and texto.endswith(cierra), texto
    cuerpo = texto[len(abre):-len(cierra)]
    assert "<" not in cuerpo and ">" not in cuerpo, cuerpo
    return cuerpo


def test_el_modo_va_en_una_etiqueta_propia_y_neutra():
    """Una etiqueta con nombre de sistema dentro de un mensaje de la persona puede leerse como
    texto inyectado: el modo va en `<modo_del_turno>`, una por modo y constante (caché)."""
    assert re.fullmatch(r"[a-z]+(?:_[a-z]+)*", chat.ETIQUETA_MODO)
    assert "system" not in chat.ETIQUETA_MODO and "reminder" not in chat.ETIQUETA_MODO
    assert set(chat.RECORDATORIO) == {herramientas.PROPUESTA, herramientas.AUTONOMO}
    for modo, texto in chat.RECORDATORIO.items():
        assert "system" not in texto.lower(), texto
        assert _sin_etiqueta(texto).startswith("Modo de este turno: ")
        uno, otro = (chat.preparar([{"role": "user", "content": t}], modo)[-1]["content"][-1]
                     for t in ("hola", "otra cosa"))
        assert uno == otro == {"type": "text", "text": texto}  # mismos bytes en cada turno


def test_los_recordatorios_solo_nombran_tools_del_chat():
    nombres = {d["name"] for d in herramientas.definiciones()}
    for texto in chat.RECORDATORIO.values():
        assert set(re.findall(r"\b[a-z]+(?:_[a-z]+)+\b", _sin_etiqueta(texto))) <= nombres


def test_los_textos_para_la_persona_cumplen_el_estandar():
    spec = importlib.util.spec_from_file_location("_pistas_gate", RAIZ / "tests" / "test_pistas.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    for texto in (chat.LLENO, chat.PROYECTO_CAMBIO, chat.SIN_PROYECTO, chat.FALLO):
        assert gate.faltas(texto) == [], f"«{texto}»: {gate.faltas(texto)}"
