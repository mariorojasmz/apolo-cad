"""Deshacer y rehacer en corto: el diff del paso (plan mcp-sin-friccion, D1).

`POST /api/undo|redo?detail=diff` responde lo que cambió el paso —etiqueta, comandos, piezas,
uniones y variables— en vez de la escena con mallas (como `remove?detail=diff`); sin `detail`,
lo de siempre. Las tools `undo`/`redo` lo piden por defecto y `detail="full"` vuelve a la escena.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.services import paso


def _ok(r) -> dict:
    assert r.status_code == 200, r.text
    return r.json()


def _cliente(doc: Document) -> TestClient:
    api.DOC = doc
    return TestClient(api.app)


def _doc() -> Document:
    doc = Document("paso-corto")
    doc.execute("set_variable", {"name": "L", "expression": "100"})  # c1
    doc.execute("create_box", {"name": "Base", "width": "=L", "height": 20})  # c2
    return doc


def test_deshacer_un_comando_nuevo():
    doc = _doc()
    doc.execute("create_box", {"name": "Tapa", "position": {"z": 200}})  # c3
    doc.execute("ground", {"name": "piso", "feature": "c3"})  # c4
    out = _ok(_cliente(doc).post("/api/undo", params={"detail": "diff"}))
    assert out["deshecho"].startswith("Anclaje")
    assert out["comandos_quitados"] == ["c4"]
    assert out["uniones_borradas"] == [{"nombre": "piso", "tipo": "anclaje"}]
    assert out["total_solidos"] == 2 and out["puede_rehacer"] is True
    assert "features" not in out and "document" not in out
    for k in ("piezas_nuevas", "piezas_borradas", "variables", "comandos_editados"):
        assert k not in out  # lo que no cambió no viaja
    out = _ok(_cliente(doc).post("/api/undo", params={"detail": "diff"}))
    assert out["piezas_borradas"] == [{"id": "c3", "nombre": "Tapa"}]


def test_rehacer_y_editar_una_variable():
    doc = _doc()
    client = _cliente(doc)
    _ok(client.post("/api/variables", json={"name": "L", "expression": "250"}))
    out = _ok(client.post("/api/undo", params={"detail": "diff"}))
    assert out["comandos_editados"] == ["c1"]
    assert out["variables"] == [{"name": "L", "expression": "100", "value": 100.0}]
    out = _ok(client.post("/api/redo", params={"detail": "diff"}))
    assert out["rehecho"].startswith("Variable") and out["comandos_editados"] == ["c1"]
    assert out["variables"][0]["value"] == 250.0 and out["puede_deshacer"] is True


def test_editar_una_pieza_la_nombra():
    doc = _doc()
    client = _cliente(doc)
    _ok(client.put("/api/commands/c2", params={"merge": True}, json={"params": {"height": 40}}))
    out = _ok(client.post("/api/undo", params={"detail": "diff"}))
    assert out["comandos_editados"] == ["c2"]
    assert out["piezas_editadas"] == [{"id": "c2", "nombre": "Base"}]


def test_varios_pasos_y_listas_recortadas():
    doc = _doc()
    doc.execute("create_box", {"name": "Barra"})  # c3
    doc.execute("pattern_linear", {"feature": "c3", "count": 60, "spacing": {"x": 150}})  # c4
    doc.execute("create_box", {"name": "Otra", "position": {"z": 500}})  # c5
    out = _ok(_cliente(doc).post("/api/undo", params={"pasos": 2, "detail": "diff"}))
    assert isinstance(out["deshecho"], list) and len(out["deshecho"]) == 2
    assert out["comandos_quitados"] == ["c4", "c5"]
    assert len(out["piezas_borradas"]) == paso.MAX_LISTA
    assert out["piezas_borradas_omitidas"] == 60 - paso.MAX_LISTA


def test_sin_detail_byte_identico_y_detail_invalido():
    doc = _doc()
    doc.execute("create_box", {"name": "Tapa"})
    client = _cliente(doc)
    completo = _ok(client.post("/api/undo"))
    assert "features" in completo and "document" in completo
    r = client.post("/api/redo", params={"detail": "full"})
    assert r.status_code == 400 and "detail admite sólo 'diff'" in r.json()["detail"]
    r = client.post("/api/undo", params={"detail": "diff", "pasos": 9})
    assert r.status_code == 400  # el rango lo sigue validando el documento


def test_las_tools_piden_el_diff(monkeypatch):
    pytest.importorskip("mcp")
    import json

    from apolo import mcp_server

    doc = _doc()
    doc.execute("create_box", {"name": "Tapa"})
    client = _cliente(doc)
    monkeypatch.setattr(mcp_server, "_api",
                        lambda method, path, **kw: client.request(method, path, **kw))
    out = json.loads(mcp_server.undo())
    assert out["piezas_borradas"] == [{"id": "c3", "nombre": "Tapa"}] and "solidos" not in out
    out = json.loads(mcp_server.redo())
    assert out["piezas_nuevas"] == [{"id": "c3", "nombre": "Tapa"}]
    out = json.loads(mcp_server.undo(detail="full"))  # la escena entera, a pedido
    assert out["deshecho"] and {s["id"] for s in out["solidos"]} == {"c2"}
