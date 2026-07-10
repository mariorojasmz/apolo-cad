"""V6.5d · preview con retorno ESTRUCTURADO (data=true): fantasmas (bbox/volumen) +
colisiones nuevas, SIN mutar el documento — el agente ensaya N colocaciones y compromete
1 sin generar escombro de log."""

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document


def _client(doc):
    api.DOC = doc
    return TestClient(api.app)


def _base():
    doc = Document("preview")
    a = doc.execute("create_box", {"name": "Base", "width": 100, "depth": 100, "height": 100})
    return doc, a


def test_preview_data_reports_ghost_bbox_and_no_collision():
    doc, a = _base()
    client = _client(doc)
    body = {
        "data": True,
        "actions": [{"type": "create_box", "params": {
            "name": "Nueva", "width": 20, "depth": 20, "height": 20, "position": {"x": 300}}}],
    }
    out = client.post("/api/commands/preview", json=body).json()
    assert len(out["fantasmas"]) == 1
    g = out["fantasmas"][0]
    assert g["name"] == "Nueva" and "bbox" in g and g["volumen_mm3"] == 8000.0
    assert out["colisiones_nuevas"] == []  # lejos de la base


def test_preview_data_reports_new_collision():
    doc, a = _base()
    client = _client(doc)
    body = {
        "data": True,
        "actions": [{"type": "create_box", "params": {
            "name": "Solapa", "width": 60, "depth": 60, "height": 60, "position": {"x": 20}}}],
    }
    out = client.post("/api/commands/preview", json=body).json()
    assert len(out["colisiones_nuevas"]) == 1
    col = out["colisiones_nuevas"][0]
    assert col["tipo"] == "solape" and col["volumen_mm3"] > 0
    assert a in (col["a"], col["b"])  # el fantasma choca contra la base


def test_preview_does_not_mutate_document():
    doc, a = _base()
    before = list(doc.commands)
    client = _client(doc)
    client.post("/api/commands/preview", json={
        "data": True,
        "actions": [{"type": "create_box", "params": {"name": "X", "width": 50, "position": {"x": 10}}}],
    })
    assert doc.commands == before  # firma del log intacta
    assert len(doc.scene) == 1     # la base sigue sola


def test_preview_default_returns_png():
    """Compat: sin `data`, preview sigue devolviendo el PNG."""
    doc, a = _base()
    client = _client(doc)
    r = client.post("/api/commands/preview", json={
        "actions": [{"type": "create_box", "params": {"name": "Y", "position": {"x": 300}}}],
    })
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_preview_invalid_command_errors_without_effects():
    doc, a = _base()
    before = list(doc.commands)
    client = _client(doc)
    r = client.post("/api/commands/preview", json={
        "data": True,
        "actions": [{"type": "create_box", "params": {"width": -5}}],  # inválido (gt=0)
    })
    assert r.status_code == 400
    assert doc.commands == before  # el documento no cambió
