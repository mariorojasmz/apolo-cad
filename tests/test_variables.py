import math

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.agent import validate_actions
from apolo.doc import Document, DocumentError


def test_variables_hoisted_to_log_head():
    doc = Document()
    doc.execute("create_box", {})
    doc.execute("set_variable", {"name": "L", "expression": "500"})
    assert [c["type"] for c in doc.commands] == ["set_variable", "create_box"]
    assert doc.variables_resolved == {"L": 500}


def test_expression_params_and_cascade():
    doc = Document()
    var = doc.execute("set_variable", {"name": "L", "expression": "2000"})
    box = doc.execute("create_box", {"width": "=L/2", "depth": "=L/10", "height": 50})
    assert math.isclose(doc.scene[box].shape.volume, 1000 * 200 * 50, rel_tol=1e-6)
    # el log conserva la expresión, no el valor resuelto
    assert doc.commands[-1]["params"]["width"] == "=L/2"

    doc.edit(var, {"name": "L", "expression": "1000"})
    assert math.isclose(doc.scene[box].shape.volume, 500 * 100 * 50, rel_tol=1e-6)


def test_invalid_expression_rejected_upfront():
    doc = Document()
    with pytest.raises((DocumentError, Exception)) as exc:
        doc.execute("create_box", {"width": "=noexiste * 2"})
    assert "noexiste" in str(exc.value)
    assert doc.commands == []
    with pytest.raises(Exception, match="circular"):
        doc.execute("set_variable", {"name": "a", "expression": "a + 1"})


def test_delete_referenced_variable_rolls_back():
    doc = Document()
    var = doc.execute("set_variable", {"name": "L", "expression": "300"})
    doc.execute("create_cylinder", {"radius": "=L/10", "height": "=L"})
    with pytest.raises(DocumentError):
        doc.remove_commands([var])
    assert doc.variables_resolved == {"L": 300}
    assert len(doc.commands) == 2


def test_coalesced_edits_share_one_undo_step():
    doc = Document()
    box = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    for width in (120, 140, 160):
        doc.edit(box, {"width": width, "depth": 100, "height": 100}, coalesce=True)
    bb = doc.scene[box].shape.bounding_box()
    assert math.isclose(bb.max.X - bb.min.X, 160, abs_tol=1e-6)
    doc.undo()  # un solo undo deshace toda la sesión de vista previa
    bb = doc.scene[box].shape.bounding_box()
    assert math.isclose(bb.max.X - bb.min.X, 100, abs_tol=1e-6)


def test_variables_survive_apolo_roundtrip():
    doc = Document()
    doc.execute("set_variable", {"name": "paso", "expression": "75"})
    doc.execute("set_variable", {"name": "n", "expression": "4"})
    doc.execute("create_cylinder", {"radius": 25, "height": "=paso*n"})
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert doc2.variables_resolved == {"paso": 75, "n": 4}
    feat = next(iter(doc2.scene.values()))
    bb = feat.shape.bounding_box()
    assert math.isclose(bb.max.Z - bb.min.Z, 300, abs_tol=1e-6)


def test_agent_batch_defines_and_uses_variables():
    actions = [
        {"type": "set_variable", "params": {"name": "L", "expression": "2000"}, "reason": ""},
        {"type": "create_box", "params": {"width": "=L/2", "depth": 50, "height": 50}, "reason": ""},
    ]
    assert validate_actions(actions) == []
    # sin la variable definida en el lote, el uso debe fallar
    assert validate_actions(actions[1:]) != []


# ----------------------------------------------------------------- API HTTP
@pytest.fixture()
def client():
    api.DOC = Document("vars-test")
    return TestClient(api.app)


def test_variables_api_crud(client):
    r = client.post("/api/variables", json={"name": "L", "expression": "2000"})
    assert r.status_code == 200
    variables = r.json()["document"]["variables"]
    assert variables == [
        {"name": "L", "expression": "2000", "value": 2000.0, "command_id": variables[0]["command_id"]}
    ]

    # editar por nombre reutiliza el mismo comando
    r = client.post("/api/variables", json={"name": "L", "expression": "1500"})
    assert r.json()["document"]["variables"][0]["value"] == 1500.0
    assert len([c for c in r.json()["document"]["commands"] if c["type"] == "set_variable"]) == 1

    r = client.post("/api/commands", json={"type": "create_box", "params": {"width": "=L"}})
    assert r.status_code == 200

    # borrar una variable usada → 400 y el modelo queda intacto
    r = client.delete("/api/variables/L")
    assert r.status_code == 400
    assert client.get("/api/document").json()["variables"][0]["name"] == "L"

    # variable inexistente → 404
    assert client.delete("/api/variables/nada").status_code == 404


def test_transient_edit_single_undo(client):
    r = client.post("/api/commands", json={"type": "create_box", "params": {}})
    cmd = r.json()["features"][0]["command_id"]
    for width in (110, 130, 150):
        r = client.put(
            f"/api/commands/{cmd}?transient=true",
            json={"params": {"width": width, "depth": 100, "height": 100}},
        )
        assert r.status_code == 200
    r = client.post("/api/undo")
    bbox = r.json()["features"][0]["bbox"]
    assert bbox["max"][0] - bbox["min"][0] == pytest.approx(100, abs=1e-3)
