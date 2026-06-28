import json

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
