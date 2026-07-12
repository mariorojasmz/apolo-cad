"""V6.5b · frente D — briefing de apertura (economía de arranque).

`open_project` devuelve un `briefing` compacto (resumen por grupo + variables + requisitos +
notas del agente + salud + variantes) para arrancar una sesión en UNA llamada en vez de 4-5.
"""

import pytest

import apolo.api.main as api
from apolo.doc import Document
from apolo.projects import ProjectStore


def _rich_doc():
    doc = Document("briefing")
    doc.execute("set_variable", {"name": "L", "expression": "2000"})
    c1 = doc.execute("create_box", {"name": "Pata", "width": 50, "depth": 50, "height": 800})
    doc.execute("create_group", {"name": "Estructura", "members": [c1], "role": "estructura"})
    doc.set_requirements({"carga_kg": 15, "producto": "cajas"})
    doc.agent_notes.append("Eje motriz Ø35 h7")
    return doc


def test_open_briefing_shape():
    api.DOC = _rich_doc()
    b = api._open_briefing()
    assert set(b) >= {"resumen", "requisitos", "notas_agente", "salud"}
    # resumen por grupo (de scene_summary_dict)
    assert any(g["grupo"] == "Estructura" for g in b["resumen"]["grupos"])
    assert b["resumen"]["variables"]  # variables resueltas
    assert b["requisitos"]["carga_kg"] == 15
    assert "Eje motriz Ø35 h7" in b["notas_agente"]
    assert b["salud"]["ok"] is True


def test_open_briefing_includes_configurations():
    api.DOC = _rich_doc()
    api.DOC.save_configuration("4m")
    b = api._open_briefing()
    assert b.get("configuraciones") == ["4m"]


def test_open_endpoint_returns_briefing(tmp_path):
    from fastapi.testclient import TestClient

    api.DOC = _rich_doc()
    api.STORE = ProjectStore(tmp_path / "b.db")
    pid = api.STORE.create(api.DOC)
    try:
        client = TestClient(api.app)
        r = client.post(f"/api/projects/{pid}/open")
        assert r.status_code == 200, r.text
        brief = r.json()["briefing"]
        assert brief["resumen"]["proyecto"] == "briefing"
        assert brief["requisitos"]["producto"] == "cajas"
    finally:
        api._autosave_sched.cancel()
        api.STORE = None
        api.PROJECT_ID = None
