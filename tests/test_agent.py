import copy
import json
import sys
import types

from apolo.agent import build_tools, document_summary, validate_actions
from apolo.agent.agent import _sse
from apolo.commands.registry import REGISTRY
from apolo.doc import Document


def test_tools_cover_full_registry():
    tools = build_tools()
    names = {t["name"] for t in tools}
    assert {"get_document", "get_catalog", "propose_commands"} <= names
    propose = next(t for t in tools if t["name"] == "propose_commands")
    enum = propose["input_schema"]["properties"]["actions"]["items"]["properties"]["type"]["enum"]
    assert set(enum) == set(REGISTRY.keys())
    # los schemas de cada comando están documentados en la descripción de la tool
    for cmd_type in REGISTRY:
        assert cmd_type in propose["description"]


def test_validate_actions_accepts_placeholders():
    actions = [
        {"type": "create_box", "params": {"width": 100}, "reason": "base"},
        {"type": "pattern_linear", "params": {"feature": "$1", "count": 3, "spacing": {"x": 50}}, "reason": "copias"},
    ]
    assert validate_actions(actions) == []


def test_validate_actions_reports_errors_with_index():
    actions = [
        {"type": "create_box", "params": {"width": -1}, "reason": ""},
        {"type": "nope", "params": {}, "reason": ""},
    ]
    errors = validate_actions(actions)
    assert len(errors) == 2
    assert errors[0].startswith("Acción 1") and errors[1].startswith("Acción 2")


def test_document_summary_is_json_serializable():
    doc = Document()
    doc.execute("create_structural_profile", {"profile": "40x40", "length": 1000})
    summary = document_summary(doc)
    text = json.dumps(summary)
    assert "create_structural_profile" in text
    assert summary["features"][0]["volume_mm3"] > 0


def test_sse_framing():
    line = _sse({"type": "text", "text": "hola"})
    assert line.startswith("data: ") and line.endswith("\n\n")
    assert json.loads(line[6:].strip()) == {"type": "text", "text": "hola"}


def test_chat_stream_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from apolo.agent import chat_stream

    events = [json.loads(e[6:].strip()) for e in chat_stream(Document(), [{"role": "user", "content": "hola"}])]
    assert events[0]["type"] == "error"
    assert events[-1]["type"] == "done"


# ------------------------------------------------ despacho de tools (cliente FAKE)
class _Block:
    def __init__(self, id, name, input):
        self.type, self.id, self.name, self.input = "tool_use", id, name, input


class _Response:
    def __init__(self, stop_reason, content):
        self.stop_reason, self.content = stop_reason, content


class _FakeAnthropicModule(types.ModuleType):
    """Sustituto de `anthropic` sin red. Replica la regla del API real que tumbaba el
    chat: cada tool_use del turno previo DEBE tener su tool_result en el siguiente
    mensaje del usuario (si no, el API devuelve 400 → aquí APIError)."""

    def __init__(self, responses, on_stream=None):
        super().__init__("anthropic")
        self.calls: list[list] = []
        module = self

        class APIError(Exception):
            def __init__(self, message):
                super().__init__(message)
                self.message = message

        class _Stream:
            def __init__(self, response):
                self.text_stream = iter(())
                self._response = response

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def get_final_message(self):
                return self._response

        class _Messages:
            def stream(self, **kwargs):
                msgs = kwargs["messages"]
                module.calls.append(copy.deepcopy([m for m in msgs if isinstance(m["content"], list)]))
                if on_stream is not None:  # simula algo que ocurre MIENTRAS el LLM piensa
                    on_stream(len(module.calls))
                if len(msgs) >= 2 and msgs[-2]["role"] == "assistant":
                    pedidos = {b.id for b in msgs[-2]["content"] if b.type == "tool_use"}
                    respondidos = {r["tool_use_id"] for r in msgs[-1]["content"]}
                    if pedidos - respondidos:
                        raise APIError(f"tool_use sin tool_result: {sorted(pedidos - respondidos)}")
                return _Stream(responses.pop(0))

        class Anthropic:
            def __init__(self, *a, **k):
                self.messages = _Messages()

        self.APIError = APIError
        self.Anthropic = Anthropic


def test_chat_stream_answers_every_tool_use(monkeypatch):
    """Regresión: `test_sketch` estaba declarada y con handler pero FUERA del despacho,
    y el if/elif no tenía `else` → su tool_use quedaba sin tool_result, la siguiente
    llamada daba 400 y el chat moría. Toda tool (también una desconocida) responde."""
    from apolo.agent import chat_stream

    rect = {
        "points": {"a": [0, 0], "b": [100, 0], "c": [100, 50], "d": [0, 50]},
        "entities": [
            {"type": "line", "id": "l1", "from": "a", "to": "b"},
            {"type": "line", "id": "l2", "from": "b", "to": "c"},
            {"type": "line", "id": "l3", "from": "c", "to": "d"},
            {"type": "line", "id": "l4", "from": "d", "to": "a"},
        ],
        "constraints": [{"type": "fix", "point": "a"}],
    }
    fake = _FakeAnthropicModule(
        [
            _Response(
                "tool_use",
                [_Block("tu_1", "test_sketch", {"sketch": rect}), _Block("tu_2", "tool_inventada", {})],
            ),
            _Response("end_turn", []),
        ]
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-sin-red")

    events = [json.loads(e[6:].strip()) for e in chat_stream(Document(), [{"role": "user", "content": "hola"}])]

    assert not [e for e in events if e["type"] == "error"], events
    assert events[-1]["type"] == "done"
    assert len(fake.calls) == 2  # el segundo turno llegó: el API no rechazó la conversación
    results = {r["tool_use_id"]: r for r in fake.calls[1][-1]["content"]}
    assert set(results) == {"tu_1", "tu_2"}
    # test_sketch llega a su handler (JSON del solver), no a la rama de desconocidas
    assert not results["tu_1"].get("is_error")
    assert "ok" in json.loads(results["tu_1"]["content"])
    assert results["tu_2"]["is_error"] is True
    assert "tool desconocida: tool_inventada" in results["tu_2"]["content"]


def test_every_declared_tool_is_dispatched():
    """Toda tool declarada (modo normal y autónomo) tiene rama en el despacho."""
    import inspect

    from apolo.agent import agent as agent_mod

    src = inspect.getsource(agent_mod.chat_stream)
    declared = {t["name"] for t in build_tools()} | {t["name"] for t in build_tools(auto=True)}
    for name in declared:
        assert name in agent_mod.VALIDATION_TOOLS or f'"{name}"' in src, name


# ------------------------------------- el chat atado al documento activo (hooks.py)
_CAJA = {"actions": [{"type": "create_box", "params": {"width": 100}, "reason": "base"}]}


class _Ganchos:
    """Ganchos de prueba: `vivo` se apaga para simular que se abrió otro proyecto."""

    def __init__(self):
        self.vivo, self.guardados, self.avisos = True, 0, 0

    def hooks(self):
        from apolo.agent import AgentHooks

        def guardar():
            self.guardados += 1

        def avisar():
            self.avisos += 1

        return AgentHooks(alive=lambda: self.vivo, after_mutation=guardar, notify=avisar)


def _correr(monkeypatch, responses, hooks, on_stream=None, auto=True):
    from apolo.agent import chat_stream

    fake = _FakeAnthropicModule(responses, on_stream)
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-sin-red")
    doc = Document()
    events = [
        json.loads(e[6:].strip())
        for e in chat_stream(doc, [{"role": "user", "content": "hola"}], auto=auto, hooks=hooks)
    ]
    return doc, events, fake


def test_chat_no_muta_el_doc_huerfano_si_el_proyecto_cambia_mientras_el_llm_piensa(monkeypatch):
    """Bug: el chat seguía mutando el documento capturado al empezar aunque el usuario
    abriera otro proyecto → el autosave guardaba el NUEVO y los cambios se perdían."""
    from apolo.agent.hooks import PROYECTO_CAMBIO

    g = _Ganchos()

    def cambiar_de_proyecto(n_llamada):
        if n_llamada == 2:
            g.vivo = False

    responses = [
        _Response("tool_use", [_Block("tu_1", "execute_commands", _CAJA)]),
        _Response("tool_use", [_Block("tu_2", "execute_commands", _CAJA),
                               _Block("tu_3", "save_note", {"text": "nota"})]),
        _Response("end_turn", []),
    ]
    doc, events, fake = _correr(monkeypatch, responses, g.hooks(), cambiar_de_proyecto)

    assert len(doc.scene) == 1  # solo el lote de ANTES del cambio
    assert doc.agent_notes == []
    assert g.guardados == 1 and g.avisos == 1  # el autosave no se llamó por el doc huérfano
    assert [e["type"] for e in events] == ["actions", "tool", "error", "done"]
    assert events[2]["message"] == PROYECTO_CAMBIO
    assert len(fake.calls) == 2  # no hubo otra vuelta del LLM


def test_chat_no_gasta_otra_vuelta_si_el_proyecto_ya_cambio(monkeypatch):
    from apolo.agent import AgentHooks

    g = _Ganchos()

    def guardar_y_cambiar():  # el proyecto cambia justo después de la primera mutación
        g.guardados += 1
        g.vivo = False

    hooks = AgentHooks(alive=lambda: g.vivo, after_mutation=guardar_y_cambiar)
    responses = [
        _Response("tool_use", [_Block("tu_1", "execute_commands", _CAJA)]),
        _Response("end_turn", []),
    ]
    doc, events, fake = _correr(monkeypatch, responses, hooks)

    assert len(fake.calls) == 1  # no se razonó sobre el documento viejo
    assert events[-2]["type"] == "error" and events[-1]["type"] == "done"


def test_chat_flujo_normal_llama_los_ganchos_en_cada_mutacion(monkeypatch):
    g = _Ganchos()
    responses = [
        _Response("tool_use", [_Block("tu_1", "execute_commands", _CAJA),
                               _Block("tu_2", "save_note", {"text": "nota"}),
                               _Block("tu_3", "undo_last", {})]),
        _Response("end_turn", []),
    ]
    doc, events, fake = _correr(monkeypatch, responses, g.hooks())

    assert not [e for e in events if e["type"] == "error"], events
    assert doc.scene == {} and doc.agent_notes == ["nota"]  # creó, anotó y deshizo
    assert g.guardados == 3  # lote + nota + undo: cada mutación se autoguarda
    assert g.avisos == 2  # lote + undo avisan a los clientes (la nota no cambia la escena)
    assert len(fake.calls) == 2


def test_execute_actions_now_revalida_el_documento_bajo_el_lock():
    """Check + mutación en UNA adquisición de STATE_LOCK: un `alive` que solo falla con el
    lock tomado demuestra que el que manda es el chequeo de adentro (sin TOCTOU)."""
    import pytest

    from apolo.agent import AgentHooks
    from apolo.agent.agent import execute_actions_now, save_agent_note
    from apolo.agent.hooks import ProjectChanged
    from apolo.state import STATE_LOCK

    doc = Document()
    hooks = AgentHooks(alive=lambda: not STATE_LOCK._is_owned())
    with pytest.raises(ProjectChanged):
        execute_actions_now(doc, _CAJA["actions"], hooks)
    with pytest.raises(ProjectChanged):
        save_agent_note(doc, "nota", hooks)
    assert doc.scene == {} and doc.commands == [] and doc.agent_notes == []


def test_endpoint_del_chat_ata_el_stream_al_proyecto_activo(monkeypatch):
    """Integración con la API: abrir otro proyecto (DOC reemplazado) a mitad del chat."""
    from fastapi.testclient import TestClient

    import apolo.api.main as api
    from apolo.agent.hooks import PROYECTO_CAMBIO

    viejo, guardados = Document("viejo"), []
    monkeypatch.setattr(api, "DOC", viejo)
    monkeypatch.setattr(api, "PROJECT_ID", 1)
    monkeypatch.setattr(api, "_autosave", lambda: guardados.append(api.DOC))

    def abrir_otro(n_llamada):
        if n_llamada == 2:
            api.DOC, api.PROJECT_ID = Document("nuevo"), 2

    responses = [
        _Response("tool_use", [_Block("tu_1", "execute_commands", _CAJA)]),
        _Response("tool_use", [_Block("tu_2", "execute_commands", _CAJA)]),
        _Response("end_turn", []),
    ]
    monkeypatch.setitem(sys.modules, "anthropic", _FakeAnthropicModule(responses, abrir_otro))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-sin-red")

    r = TestClient(api.app).post(
        "/api/agent/chat", json={"messages": [{"role": "user", "content": "hola"}], "auto": True}
    )
    assert r.status_code == 200
    assert PROYECTO_CAMBIO in r.text
    assert len(viejo.scene) == 1 and api.DOC.scene == {}
    assert guardados == [viejo]  # un solo autosave, del lote aplicado ANTES del cambio


def test_el_agente_no_importa_la_api():
    """api → agent, nunca al revés: el agente recibe sus ganchos (hooks.py)."""
    import ast
    from pathlib import Path

    from apolo.agent import agent as agent_mod

    paquete = ["apolo", "agent"]
    archivos = list(Path(agent_mod.__file__).parent.glob("*.py"))
    assert any(a.name == "agent.py" for a in archivos)
    for archivo in archivos:
        for nodo in ast.walk(ast.parse(archivo.read_text(encoding="utf-8"))):
            if isinstance(nodo, ast.ImportFrom):  # relativo → absoluto; `from apolo import api` también
                raiz = ".".join(paquete[: len(paquete) - nodo.level + 1]) if nodo.level else ""
                mod = ".".join(p for p in (raiz, nodo.module or "") if p)
                modulos = [mod] + [f"{mod}.{a.name}" for a in nodo.names]
            elif isinstance(nodo, ast.Import):
                modulos = [a.name for a in nodo.names]
            else:
                continue
            for m in modulos:
                assert m != "apolo.api" and not m.startswith("apolo.api."), f"{archivo.name} importa {m}"
