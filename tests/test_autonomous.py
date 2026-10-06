import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.batch import execute_batch
from apolo.commands.registry import CommandError
from apolo.doc import Document


# ------------------------------------------------------------------- batch
def test_execute_batch_with_refs():
    doc = Document()
    ids = execute_batch(
        doc,
        [
            {"type": "create_box", "params": {"width": 100}},
            {"type": "pattern_linear", "params": {"feature": "$1", "count": 3, "spacing": {"x": 200}}},
        ],
    )
    assert len(ids) == 2 and len(doc.scene) == 3


def test_execute_batch_bad_ref():
    doc = Document()
    with pytest.raises(CommandError, match="\\$5"):
        execute_batch(doc, [{"type": "transform", "params": {"feature": "$5"}}])


def test_batch_is_single_undo_step():
    """Un lote = 1 paso de undo (1 regenerate). Un solo undo deshace TODO el lote."""
    doc = Document()
    ids = execute_batch(
        doc,
        [
            {"type": "create_box", "params": {"width": 100}},
            {"type": "create_box", "params": {"width": 50, "position": {"x": 300}}},
            {"type": "pattern_linear", "params": {"feature": "$1", "count": 2, "spacing": {"x": 200}}},
        ],
    )
    assert len(ids) == 3 and len(doc.scene) > 0 and doc.can_undo
    doc.undo()
    assert doc.scene == {} and not doc.can_undo  # un solo undo revierte el lote entero


def test_batch_atomic_rollback_on_bad_ref():
    """Si una acción del lote falla, se revierte TODO (atómico): nada queda."""
    doc = Document()
    with pytest.raises(CommandError):
        execute_batch(
            doc,
            [
                {"type": "create_box", "params": {"width": 100}},
                {"type": "transform", "params": {"feature": "$9", "translate": {"x": 10}}},
            ],
        )
    assert doc.scene == {} and not doc.can_undo


def test_batch_set_variable_then_use():
    """set_variable + uso de la variable en el MISMO lote (sin pre-validar; el
    regenerate final valida en orden con las vars hoist-eadas)."""
    doc = Document()
    ids = execute_batch(
        doc,
        [
            {"type": "set_variable", "params": {"name": "L", "expression": "500"}},
            {"type": "create_box", "params": {"width": "=L", "depth": 100, "height": 100}},
        ],
    )
    assert len(ids) == 2 and len(doc.scene) == 1
    assert doc.variables_resolved == {"L": 500.0}


# ------------------------------------------------------- memoria del agente
def test_agent_notes_memory():
    """Las notas que guarda el agente (MCP o chat de la app, los dos por `POST
    /api/agent/notes`) viajan en el .apolo. El recorte y el tope de 30 los cubre
    `test_guardia_documento.py`."""
    api.DOC = doc = Document()
    client = TestClient(api.app)
    client.post("/api/agent/notes", json={"text": "El cliente prefiere rodillos Ø60 por margen de carga"})
    client.post("/api/agent/notes", json={"text": "  con espacios  "})
    assert doc.agent_notes == ["El cliente prefiere rodillos Ø60 por margen de carga", "con espacios"]
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert doc2.agent_notes == doc.agent_notes


# -------------------------------------------------------------- servidor MCP
def test_mcp_server_module_tools():
    """El módulo MCP debe importar y declarar sus tools (sin servidor vivo)."""
    import asyncio

    from apolo import mcp_server

    tools = asyncio.run(mcp_server.mcp.list_tools())
    names = {t.name for t in tools}
    assert {
        "get_scene", "get_command_schemas", "get_catalog", "run_command", "run_batch",
        "edit_command", "undo", "set_variable", "check_interference", "engineering_check",
        "render_view", "list_projects", "create_project", "export_step",
    } <= names
    # las descripciones existen (el agente las necesita para elegir)
    assert all(t.description for t in tools)


def test_mcp_connection_error_message(monkeypatch):
    from apolo import mcp_server

    monkeypatch.setattr(mcp_server, "APOLO_URL", "http://127.0.0.1:9")  # puerto imposible
    with pytest.raises(RuntimeError, match="arranca el servidor"):
        mcp_server._api("GET", "/api/scene")
