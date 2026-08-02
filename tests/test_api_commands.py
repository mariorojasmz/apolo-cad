"""GET /api/commands (V6.8-B): buscar en el log por type/feature/name — el command_id
de una operación deja de deducirse por aritmética de lotes (el 404 real de la sesión
camastro: editar los chaflanes de las cremalleras exigió adivinar sus ids)."""
import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document


@pytest.fixture()
def client():
    api.DOC = Document("find-commands-test")
    return TestClient(api.app)


def _modelo(client) -> dict:
    """2 cajas + patrón sobre la primera + junta entre ambas → ids por rol."""
    r = client.post("/api/commands", json={"type": "create_box", "params": {
        "name": "Larguero (+Y)", "width": 400, "depth": 40, "height": 40}})
    larguero = r.json()["features"][-1]["id"]
    r = client.post("/api/commands", json={"type": "create_box", "params": {
        "name": "Pata delantera", "width": 40, "depth": 40, "height": 300,
        "position": {"x": 200, "z": -170}}})
    pata = r.json()["features"][-1]["id"]
    r = client.post("/api/commands", json={"type": "pattern_linear", "params": {
        "feature": pata, "count": 2, "spacing": {"y": 200}}})
    patron = r.json()["affected_command_ids"][0]
    r = client.post("/api/commands", json={"type": "add_joint", "params": {
        "name": "bisagra", "type": "giratoria", "parent": larguero, "child": pata,
        "axis": {"y": 1}}})
    junta = r.json()["affected_command_ids"][0]
    return {"larguero": larguero, "pata": pata, "patron": patron, "junta": junta}


def test_filtro_por_type(client):
    ids = _modelo(client)
    out = client.get("/api/commands", params={"type": "create_box"}).json()
    assert out["total"] == 2 and not out["truncado"]
    assert {c["id"] for c in out["commands"]} == {ids["larguero"], ids["pata"]}
    assert all(c["type"] == "create_box" for c in out["commands"])


def test_filtro_por_feature_creador_y_referencias(client):
    """`feature` trae el comando que CREÓ la pieza y los que la REFERENCIAN
    (patrón por param `feature`, junta por `parent`/`child`)."""
    ids = _modelo(client)
    out = client.get("/api/commands", params={"feature": ids["pata"]}).json()
    got = {c["id"] for c in out["commands"]}
    assert {ids["pata"], ids["patron"], ids["junta"]} <= got
    assert ids["larguero"] not in got
    # combinado: solo el patrón sobre la pata
    out = client.get("/api/commands",
                     params={"feature": ids["pata"], "type": "pattern_linear"}).json()
    assert [c["id"] for c in out["commands"]] == [ids["patron"]]
    # resumen compacto: el patrón no tiene name → «tipo sobre X»
    assert out["commands"][0]["resumen"] == f"pattern_linear sobre {ids['pata']}"


def test_filtro_por_name_substring(client):
    ids = _modelo(client)
    out = client.get("/api/commands", params={"name": "larguero"}).json()  # case-insensitive
    assert [c["id"] for c in out["commands"]] == [ids["larguero"]]
    assert out["commands"][0]["resumen"] == "Larguero (+Y)"


def test_sin_filtros_400(client):
    _modelo(client)
    r = client.get("/api/commands")
    assert r.status_code == 400 and "filtro" in r.json()["detail"]


def test_feature_inexistente_404_con_sugerencia(client):
    ids = _modelo(client)
    r = client.get("/api/commands", params={"feature": ids["pata"] + "99"})
    assert r.status_code == 404
    assert "quisiste decir" in r.json()["detail"].lower()


def test_limit_declara_truncado(client):
    _modelo(client)
    out = client.get("/api/commands", params={"type": "create_box", "limit": 1}).json()
    assert out["total"] == 2 and out["truncado"] and len(out["commands"]) == 1
