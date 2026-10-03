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

    def __init__(self, responses):
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
