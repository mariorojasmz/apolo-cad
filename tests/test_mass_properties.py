"""Tests de get_mass_properties (Frente A, Fase 2): masa/COM por pieza y del
conjunto, coherencia con scene_weight_kg, endpoint HTTP."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document
from apolo.library.cutlist import scene_weight_kg
from apolo.library.engineering.mass import feature_mass, scene_mass_properties


def _doc_with_boxes() -> Document:
    doc = Document("mass-test")
    doc.execute("create_box", {"name": "Bloque acero", "width": 100, "depth": 100, "height": 100})
    doc.execute(
        "create_box",
        {"name": "Tablero lateral", "width": 100, "depth": 100, "height": 100,
         "position": {"x": 300, "y": 0, "z": 0}},
    )
    return doc


def test_steel_cube_mass():
    doc = _doc_with_boxes()
    feat = next(f for f in doc.scene.values() if "acero" in f.name.lower() or "Bloque" in f.name)
    row = feature_mass(feat)
    # 100³ mm³ × 7.85e-6 kg/mm³ = 7.85 kg, a medida (volumen)
    assert row["fuente"] == "volumen"
    assert row["masa_kg"] == pytest.approx(7.85, rel=1e-3)
    # position = CENTRO del bbox → el cubo queda centrado en el origen
    assert row["com_mm"][2] == pytest.approx(0.0, abs=0.5)


def test_wood_name_resolves_lower_density():
    doc = _doc_with_boxes()
    tablero = next(f for f in doc.scene.values() if "Tablero" in f.name)
    row = feature_mass(tablero)
    assert row["material"] == "madera"
    assert row["masa_kg"] == pytest.approx(0.5, rel=1e-3)  # ρ madera 5e-7


def test_aggregate_weighted_com():
    doc = _doc_with_boxes()
    out = scene_mass_properties(doc.scene)
    assert out["total"]["n_piezas"] == 2
    # COM X ponderado (cubos centrados en x=0 y x=300): (7.85·0 + 0.5·300)/8.35 ≈ 17.96
    assert out["total"]["com_mm"][0] == pytest.approx((7.85 * 0 + 0.5 * 300) / 8.35, rel=1e-3)
    assert out["total"]["masa_kg"] == pytest.approx(8.35, rel=1e-3)


def test_total_consistent_with_scene_weight():
    doc = _doc_with_boxes()
    out = scene_mass_properties(doc.scene)
    assert out["total"]["masa_kg"] == pytest.approx(scene_weight_kg(doc.scene), rel=1e-3)


def test_catalog_component_uses_nameplate_weight():
    doc = Document("mass-cat")
    doc.execute("insert_component", {"component": "6207", "position": {"x": 0, "y": 0, "z": 0}})
    from apolo.library.catalog import CATALOG

    row = feature_mass(next(iter(doc.scene.values())))
    assert row["fuente"] == "catálogo"
    assert row["masa_kg"] == pytest.approx(CATALOG["6207"].weight, rel=1e-6)


def test_missing_id_raises_keyerror():
    doc = _doc_with_boxes()
    with pytest.raises(KeyError):
        scene_mass_properties(doc.scene, ids=["no-existe"])


def test_endpoint_mass_properties():
    api.DOC = _doc_with_boxes()
    client = TestClient(api.app)
    r = client.get("/api/mass-properties")
    assert r.status_code == 200
    data = r.json()
    assert data["total"]["n_piezas"] == 2
    assert data["piezas"][0]["masa_kg"] > 0

    only = client.get("/api/mass-properties", params={"ids": data["piezas"][0]["id"]})
    assert only.status_code == 200
    assert only.json()["total"]["n_piezas"] == 1

    assert client.get("/api/mass-properties", params={"ids": "zzz"}).status_code == 404
