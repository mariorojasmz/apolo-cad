"""V6.5b · consultas espaciales: near por feature/box (además de point) e interferencia
acotada por `focus`. Barrido O(n) sobre AABBs (sin índice espacial)."""

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.kernel.measure import features_near_box, features_near_feature
from apolo.library.checks import interference_report


def _three_boxes():
    """A en x=0, B en x=150 (gap 50 a los flancos), C lejos en x=2000."""
    doc = Document("near")
    a = doc.execute("create_box", {"name": "A", "width": 100, "depth": 100, "height": 100})
    b = doc.execute("create_box", {"name": "B", "width": 100, "depth": 100, "height": 100,
                                   "position": {"x": 150}})
    c = doc.execute("create_box", {"name": "C", "width": 100, "depth": 100, "height": 100,
                                   "position": {"x": 2000}})
    return doc, a, b, c


def test_near_feature_excludes_self_and_sorts():
    doc, a, b, c = _three_boxes()
    res = features_near_feature(doc.scene, a, radius=100)
    ids = [e["id"] for e in res]
    assert a not in ids  # se excluye X
    assert ids[0] == b  # B (gap 50) antes que C (lejos, fuera de radio)
    assert c not in ids
    assert res[0]["dist_mm"] == 50.0  # gap AABB-AABB entre A (max_x=50) y B (min_x=100)


def test_near_box_region():
    doc, a, b, c = _three_boxes()
    # región que abarca A y B pero no C
    res = features_near_box(doc.scene, [[-60, -60, -60], [210, 60, 60]], radius=0)
    ids = {e["id"] for e in res}
    assert ids == {a, b}


def test_near_endpoint_modes_and_exclusivity():
    doc, a, b, c = _three_boxes()
    api.DOC = doc
    client = TestClient(api.app)
    # por feature
    r = client.get("/api/near", params={"feature": a, "radius": 100})
    assert r.status_code == 200 and r.json()["cercanas"][0]["id"] == b
    # por caja (JSON)
    import json as _j
    r = client.get("/api/near", params={"box": _j.dumps([[-60, -60, -60], [210, 60, 60]]), "radius": 0})
    assert {e["id"] for e in r.json()["cercanas"]} == {a, b}
    # por punto (compat)
    r = client.get("/api/near", params={"point": _j.dumps([0, 0, 0]), "radius": 60})
    assert [e["id"] for e in r.json()["cercanas"]] == [a]
    # exclusividad: dar dos → 400
    r = client.get("/api/near", params={"feature": a, "point": _j.dumps([0, 0, 0])})
    assert r.status_code == 400
    # ninguno → 400
    assert client.get("/api/near").status_code == 400


def test_near_limit():
    doc, a, b, c = _three_boxes()
    api.DOC = doc
    client = TestClient(api.app)
    r = client.get("/api/near", params={"feature": a, "radius": 5000, "limit": 1})
    assert len(r.json()["cercanas"]) == 1


def _colliding_scene():
    """Cuatro cajas: par A/B se solapan; par C/D se solapan; los dos pares lejos entre sí."""
    doc = Document("focus")
    a = doc.execute("create_box", {"name": "A", "width": 100, "depth": 100, "height": 100})
    b = doc.execute("create_box", {"name": "B", "width": 100, "depth": 100, "height": 100,
                                   "position": {"x": 50}})
    c = doc.execute("create_box", {"name": "C", "width": 100, "depth": 100, "height": 100,
                                   "position": {"x": 2000}})
    d = doc.execute("create_box", {"name": "D", "width": 100, "depth": 100, "height": 100,
                                   "position": {"x": 2050}})
    return doc, a, b, c, d


def test_interference_focus_is_subset_of_global():
    doc, a, b, c, d = _colliding_scene()
    glob = interference_report(doc.scene)["interferencias"]
    pares_glob = {frozenset((col["a"], col["b"])) for col in glob}
    assert pares_glob == {frozenset((a, b)), frozenset((c, d))}
    # acotar a {a}: solo el par que toca A
    foc = interference_report(doc.scene, focus={a})["interferencias"]
    pares_foc = {frozenset((col["a"], col["b"])) for col in foc}
    assert pares_foc == {frozenset((a, b))}
    assert pares_foc <= pares_glob  # subconjunto exacto de la global


def test_checks_endpoint_bounded_by_ids():
    doc, a, b, c, d = _colliding_scene()
    api.DOC = doc
    client = TestClient(api.app)
    full = client.post("/api/checks", json={}).json()["interferencias"]["interferencias"]
    assert len(full) == 2
    bounded = client.post("/api/checks", json={"interference_ids": [c]}).json()
    cols = bounded["interferencias"]["interferencias"]
    assert len(cols) == 1
    assert {cols[0]["a"], cols[0]["b"]} == {c, d}
