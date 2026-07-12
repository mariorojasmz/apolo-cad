"""V6.5c — fixes de la revisión de V6.5b.

1. `$k` del expect resuelve a los FEATURE_IDS del comando (multi-sólido expande en `ids`;
   en campo singular con varios sólidos → error accionable + rollback).
2. join_bolted RECHAZA contacto no plano (pieza rotada) y asientos no prismáticos.
3. Perno con protrusión = tuerca + 3 filetes; tuerca DIN 934 insertada y en BOM.
4. Errores accionables: clave desconocida en aserción, «sin piezas» con tokens y
   sugerencia, `$0` explica el 1-indexado, command_id vivo sugiere sus fids hijos.
"""

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document


def _client(name: str) -> TestClient:
    api.DOC = Document(name)
    return TestClient(api.app)


def _plates_and_join(join_extra: dict | None = None) -> list[dict]:
    """Dos placas 200×150 en contacto en z=6 + join_bolted M12 2×2 vía $k."""
    return [
        {"type": "create_box", "params": {"name": "Placa base", "width": 200, "depth": 150,
                                          "height": 12, "material": "acero"}},
        {"type": "create_box", "params": {"name": "Placa superior", "width": 200, "depth": 150,
                                          "height": 10, "material": "acero",
                                          "position": {"x": 0, "y": 0, "z": 11}}},
        {"type": "join_bolted", "params": {"a": "$1", "b": "$2", "size": "M12",
                                           "patron": [2, 2], **(join_extra or {})}},
    ]


# ---------------------------------------------------------- 1 · $k multi-sólido en expect
def test_expect_dollar_k_multi_solid_expands_in_ids():
    client = _client("k-multi-ids")
    r = client.post("/api/commands/batch", json={
        "actions": _plates_and_join(),
        # $3 = join_bolted (multi-sólido: 4 pernos + 4 tuercas) → expande en `ids`
        "expect": [{"tipo": "volumen", "ids": ["$3"], "min": 1.0}],
    })
    assert r.status_code == 200, r.text
    assert r.json()["contrato"]["ok"] is True
    assert len(api.DOC.scene) == 2 + 8  # 2 placas + 4 pernos + 4 tuercas


def test_expect_dollar_k_multi_solid_in_singular_field_fails_actionably():
    client = _client("k-multi-singular")
    r = client.post("/api/commands/batch", json={
        "actions": _plates_and_join(),
        "expect": [{"tipo": "existe", "id": "$3"}],  # $3 creó VARIOS → error, no elegir uno
    })
    assert r.status_code == 400
    assert "creó" in r.json()["detail"] and "ids" in r.json()["detail"]
    assert len(api.DOC.scene) == 0  # rollback completo


def test_expect_dollar_k_mono_solid_in_singular_field_ok():
    client = _client("k-mono")
    r = client.post("/api/commands/batch", json={
        "actions": _plates_and_join(),
        "expect": [{"tipo": "distancia", "a": "$1", "b": "$2", "max": 1.0}],  # en contacto
    })
    assert r.status_code == 200, r.text


# ------------------------------------------------- 2 · contacto plano obligatorio (v1)
def test_join_bolted_rejects_rotated_plate():
    client = _client("rotated")
    r = client.post("/api/commands/batch", json={"actions": [
        {"type": "create_box", "params": {"name": "Base", "width": 200, "depth": 150,
                                          "height": 12}},
        {"type": "create_box", "params": {"name": "Inclinada", "width": 200, "depth": 150,
                                          "height": 10, "position": {"x": 0, "y": 0, "z": 60},
                                          "rotation": {"x": 30, "y": 0, "z": 0}}},
    ]})
    assert r.status_code == 200, r.text
    fids = list(api.DOC.scene.keys())
    # acercarla hasta tocar la base por la arista (bbox de la rotada baja hasta ~z=6)
    bb = api.DOC.scene[fids[1]].shape.bounding_box()
    dz = 6.0 - bb.min.Z
    r = client.post("/api/commands", json={"type": "transform", "params": {
        "feature": fids[1], "translate": {"x": 0, "y": 0, "z": dz}}})
    assert r.status_code == 200, r.text
    r = client.post("/api/commands", json={"type": "join_bolted", "params": {
        "a": fids[0], "b": fids[1], "size": "M10", "count": 2}})
    assert r.status_code == 400
    assert "PLANA" in r.json()["detail"] or "plana" in r.json()["detail"]


# ------------------------------------------- 3 · protrusión + tuerca + edge con count=1
def test_bolt_length_includes_thread_allowance_and_nut_in_bom():
    client = _client("nut-bom")
    r = client.post("/api/commands/batch", json={"actions": _plates_and_join()})
    assert r.status_code == 200, r.text
    # grip 22 + protrusión (0.8·12 + 3·1.75 = 14.85) = 36.85 → comercial 40 (antes: 35)
    pernos = [f for f in api.DOC.scene.values() if "Perno M12" in f.name]
    assert len(pernos) == 4 and all("×40" in f.name for f in pernos)
    tuercas = [f for f in api.DOC.scene.values() if f.component == "TUERCA-M12"]
    assert len(tuercas) == 4
    bom = client.get("/api/bom").json()
    rows = {r["ref"]: r for r in bom}
    assert rows["TUERCA-M12"]["cantidad"] == 4
    assert rows["TUERCA-M12"]["norma"] == "DIN 934"


def test_join_bolted_count1_respects_edge_distance():
    client = _client("edge-n1")
    r = client.post("/api/commands/batch", json={"actions": [
        {"type": "create_box", "params": {"name": "A", "width": 20, "depth": 20, "height": 10}},
        {"type": "create_box", "params": {"name": "B", "width": 20, "depth": 20, "height": 10,
                                          "position": {"x": 0, "y": 0, "z": 10}}},
    ]})
    assert r.status_code == 200, r.text
    # huella 20×20; M12 exige borde ≥18 por lado → ni UN perno cabe
    r = client.post("/api/commands", json={"type": "join_bolted", "params": {
        "a": "c1", "b": "c2", "size": "M12", "count": 1}})
    assert r.status_code == 400
    assert "borde" in r.json()["detail"]


def test_patron_capped_at_100():
    client = _client("patron-cap")
    client.post("/api/commands/batch", json={"actions": _plates_and_join()[:2]})
    r = client.post("/api/commands", json={"type": "join_bolted", "params": {
        "a": "c1", "b": "c2", "size": "M6", "patron": [40, 40]}})
    assert r.status_code in (400, 422)
    assert "tope" in r.text or "100" in r.text


# --------------------------------------------------- 4 · errores accionables en verify
def test_verify_unknown_key_is_actionable_not_silent():
    client = _client("unknown-key")
    client.post("/api/commands/batch", json={"actions": _plates_and_join()[:2]})
    r = client.post("/api/verify", json={"checks": [
        {"tipo": "existe", "feature": "c1"},  # clave equivocada (el campo es `id`)
    ]})
    assert r.status_code == 200
    res = r.json()["resultados"][0]
    assert res["ok"] is False
    assert "no reconocida" in res["error"] and "feature" in res["error"]


def test_verify_sin_piezas_names_tokens_and_suggests():
    client = _client("sin-piezas")
    client.post("/api/commands/batch", json={"actions": _plates_and_join()[:2]})
    r = client.post("/api/verify", json={"checks": [
        {"tipo": "volumen", "ids": ["c1_typo"], "min": 1},
        {"tipo": "existe", "id": "c1_typo"},
    ]})
    res = r.json()["resultados"]
    assert "c1_typo" in res[0]["error"]  # nombra el token que no resolvió
    assert "sólido inexistente 'c1_typo'" in res[1]["error"]


def test_batch_dollar_zero_explains_one_indexing():
    client = _client("dollar-zero")
    r = client.post("/api/commands/batch", json={"actions": [
        {"type": "create_box", "params": {"name": "A", "width": 10, "depth": 10, "height": 10}},
        {"type": "fasten", "params": {"name": "w", "a": "$0", "b": "$1", "kind": "contacto"}},
    ]})
    assert r.status_code == 400
    assert "$1" in r.json()["detail"]


def test_suggest_command_id_offers_child_fids():
    client = _client("suggest-kids")
    r = client.post("/api/commands/batch", json={"actions": _plates_and_join()})
    assert r.status_code == 200, r.text
    join_cmd = api.DOC.commands[-1]["id"]  # join_bolted: multi-sólido, sin fid propio
    sug = api._suggest_ids(join_cmd)
    assert sug and all(s.startswith(f"{join_cmd}_") for s in sug)  # hijos, no él mismo
