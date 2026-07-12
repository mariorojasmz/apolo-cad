"""V6.5b · frente C — errores con sugerencia («¿quisiste decir…?»).

Un id inventado en las lecturas (near/measure/topology/mass) y en edit_command deja de
costar un round-trip a ciegas: el 404 trae candidatos cercanos del universo vigente.
"""

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document


def _doc_chumacera():
    api.DOC = Document("suggest")
    a = api.DOC.execute("create_box", {"name": "Chumacera UCP207", "width": 50, "depth": 50, "height": 50})
    b = api.DOC.execute("create_box", {"name": "Larguero", "width": 50, "depth": 50, "height": 50,
                                       "position": {"x": 300}})
    return a, b


def test_near_typo_suggests_real_id():
    a, _ = _doc_chumacera()  # a == "c1"
    client = TestClient(api.app)
    r = client.get("/api/near", params={"feature": f"{a}_0"})  # typo típico: 'c1_0'
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "¿Quisiste decir" in detail and a in detail


def test_measure_typo_suggests():
    a, b = _doc_chumacera()
    client = TestClient(api.app)
    r = client.post("/api/measure", json={"a": a, "b": f"{b}_0"})  # typo de sufijo: 'c2_0'
    assert r.status_code == 404
    assert "¿Quisiste decir" in r.json()["detail"] and b in r.json()["detail"]


def test_topology_partial_name_suggests():
    _doc_chumacera()
    client = TestClient(api.app)
    r = client.get("/api/features/chumacera/topology")  # nombre parcial, no id
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "c1" in detail  # sugiere la pieza cuyo nombre contiene 'chumacera'


def test_edit_command_typo_suggests():
    _doc_chumacera()
    client = TestClient(api.app)
    r = client.put("/api/commands/c22", json={"params": {}})  # typo cercano a c2
    assert r.status_code == 404
    assert "comando" in r.json()["detail"] and "¿Quisiste decir" in r.json()["detail"]


def test_no_close_match_is_clean_404():
    _doc_chumacera()
    client = TestClient(api.app)
    r = client.post("/api/measure", json={"a": "c1", "b": "zzzzzzzz"})
    assert r.status_code == 404
    assert "¿Quisiste decir" not in r.json()["detail"]  # sin ruido si nada se parece


def test_verify_selector_suggestion():
    a, _ = _doc_chumacera()
    client = TestClient(api.app)
    r = client.post("/api/verify", json={"checks": [
        {"tipo": "distancia", "a": a, "b": f"{a}_0", "max": 5}]})
    assert r.status_code == 200
    res = r.json()["resultados"][0]
    assert res["ok"] is False and "¿Quisiste decir" in res["error"]


def test_expect_contract_error_suggestion():
    """El contrato de un lote también sugiere ante un id inexistente en la aserción."""
    api.DOC = Document("suggest-expect")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", json={
        "actions": [{"type": "create_box", "params": {"name": "Placa", "width": 50, "depth": 50, "height": 50}}],
        "expect": [{"tipo": "distancia", "a": "$1", "b": "c1_0", "max": 5}],
    })
    assert r.status_code == 400
    assert "¿Quisiste decir" in r.json()["detail"]
