"""V6.5a · lectura acotada y resumida: get_scene filtrado/paginado/summary + get_topology
acotado + get_bom by_group. El principio: ninguna lectura de rutina vuelca la escena
entera; el agente entra por el resumen y trabaja por grupos."""

import json

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.assembly.groups import group_features
from apolo.doc import Document


def _big_model(chico=6):
    """Modelo sintético (~1000 piezas) con dos sub-ensamblajes: 'Grande' (filler) y
    'Chico' (grupo de trabajo de decenas de piezas). Barato: pattern_group."""
    doc = Document("escala")
    box = doc.execute("create_box", {"width": 20, "depth": 20, "height": 20})
    grid = doc.execute(
        "pattern_group",
        {"source": box, "count": 32, "spacing": {"x": 50}, "count2": 31, "spacing2": {"y": 50}},
    )
    small = doc.execute(
        "create_box", {"name": "Chumacera", "width": 10, "depth": 10, "height": 10, "position": {"z": 500}}
    )
    sgrid = doc.execute(
        "pattern_group",
        {"source": small, "count": chico, "spacing": {"x": 30}, "count2": chico, "spacing2": {"y": 30}},
    )
    doc.execute("create_group", {"name": "Grande", "members": [box, grid]})
    doc.execute("create_group", {"name": "Chico", "members": [small, sgrid]})
    return doc


def _client(doc):
    api.DOC = doc
    return TestClient(api.app)


def test_scene_no_params_is_full_payload():
    """Compat: sin parámetros, GET /api/scene sigue devolviendo el payload de mallas (features
    + definitions), no el brief ligero (solidos)."""
    doc = Document("t")
    doc.execute("create_box", {"width": 50})
    data = _client(doc).get("/api/scene").json()
    assert "features" in data and "definitions" in data
    assert "solidos" not in data  # el brief ligero solo aparece con filtros


def test_filter_by_group_equals_expand_by_hand():
    doc = _big_model()
    r = _client(doc).get("/api/scene", params={"ids": "Chico"})
    data = r.json()
    got = {s["id"] for s in data["solidos"]}
    esperado = set(group_features(doc.scene, doc.groups, "Chico"))
    assert got == esperado
    assert data["total_solidos"] == len(doc.scene)  # el total es de la escena entera
    assert data["total_filtrado"] == len(esperado)
    assert data["truncado"] is False


def test_pagination_stable_and_declares_truncation():
    """Paginar el grupo grande: orden determinista, sin caps silenciosos."""
    doc = _big_model()
    client = _client(doc)
    p1 = client.get("/api/scene", params={"ids": "Grande", "limit": 50, "offset": 0}).json()
    p2 = client.get("/api/scene", params={"ids": "Grande", "limit": 50, "offset": 50}).json()
    assert p1["solidos_mostrados"] == 50 and p1["truncado"] is True
    assert p1["total_filtrado"] == 992
    ids1 = [s["id"] for s in p1["solidos"]]
    ids2 = [s["id"] for s in p2["solidos"]]
    assert len(set(ids1) & set(ids2)) == 0  # páginas disjuntas
    # orden estable entre llamadas
    again = client.get("/api/scene", params={"ids": "Grande", "limit": 50, "offset": 0}).json()
    assert [s["id"] for s in again["solidos"]] == ids1


def test_filter_by_name_substring():
    doc = _big_model()
    r = _client(doc).get("/api/scene", params={"name": "chumacera"})  # case-insensitive
    data = r.json()
    assert data["total_filtrado"] >= 1
    assert all("chumacera" in s["nombre"].lower() for s in data["solidos"])


def test_summary_aggregates_match_global_mass():
    from apolo.library.engineering.mass import scene_mass_properties

    doc = _big_model()
    summ = _client(doc).get("/api/scene/summary").json()
    total_global = scene_mass_properties(doc.scene, default_material=doc.default_material())["total"]
    assert summ["total_solidos"] == len(doc.scene)
    assert abs(summ["masa_total_kg"] - total_global["masa_kg"]) < 1e-6
    # la suma de los grupos + sin_grupo cuadra con el total (partición de la escena)
    suma_grupos = sum(g["n_piezas"] for g in summ["grupos"]) + summ["sin_grupo"]["n_piezas"]
    assert suma_grupos == len(doc.scene)
    nombres = {g["grupo"] for g in summ["grupos"]}
    assert {"Grande", "Chico"} <= nombres


def test_byte_budget_filtered_group_and_summary():
    """Presupuesto: brief de un grupo de trabajo < 10 KB y summary < 5 KB en un modelo grande."""
    doc = _big_model()
    client = _client(doc)
    filt = client.get("/api/scene", params={"ids": "Chico"}).json()
    summ = client.get("/api/scene/summary").json()
    n_filt = len(json.dumps(filt, ensure_ascii=False).encode("utf-8"))
    n_summ = len(json.dumps(summ, ensure_ascii=False).encode("utf-8"))
    assert n_filt < 10_000, f"brief filtrado {n_filt} B"
    assert n_summ < 5_000, f"summary {n_summ} B"
    # la escena tiene ~1000 piezas → sin filtrar sería órdenes de magnitud mayor
    assert doc.__class__ and len(doc.scene) > 900


def test_topology_only_and_min_mm():
    doc = Document("topo")
    box = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    doc.execute("drill_hole", {"feature": box, "position": {"x": 0, "y": 0, "z": 50},
                               "axis": "-z", "diameter": 2, "depth": 10})
    client = _client(doc)
    full = client.get(f"/api/features/{box}/topology").json()
    assert "faces" in full and "edges" in full and "anchors" in full
    solo_caras = client.get(f"/api/features/{box}/topology", params={"only": "caras"}).json()
    assert "faces" in solo_caras and "edges" not in solo_caras and "anchors" not in solo_caras
    solo_anclas = client.get(f"/api/features/{box}/topology", params={"only": "anclas"}).json()
    assert "faces" not in solo_anclas and "edges" not in solo_anclas and "anchors" in solo_anclas
    # min_mm poda las aristas del taladro pequeño (Ø2)
    filtrado = client.get(f"/api/features/{box}/topology", params={"min_mm": 20}).json()
    assert len(filtrado["edges"]) < len(full["edges"])


def test_bom_by_group_marks_group():
    doc = _big_model()
    rows = _client(doc).get("/api/bom", params={"by_group": "true"}).json()
    assert any(r.get("grupo") for r in rows)
