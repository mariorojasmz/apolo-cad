import math

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.commands.registry import CommandError
from apolo.doc import Document, DocumentError
from apolo.library import CATALOG, bom_from_scene, bom_to_csv, build_component


def test_catalog_geometry_builds():
    for ref, comp in CATALOG.items():
        shape, cut = build_component(ref)
        assert shape.volume > 0, f"{ref} sin volumen"
        if comp.cuttable:
            assert cut == comp.default_length
        else:
            assert cut is None


def test_cuttable_length_drives_bbox():
    shape, cut = build_component("PERFIL-4040", 750)
    bb = shape.bounding_box()
    assert math.isclose(bb.max.Z - bb.min.Z, 750, abs_tol=1e-3)
    assert cut == 750
    leg, _ = build_component("PATA-REG", 600)
    bb = leg.bounding_box()
    assert math.isclose(bb.max.Z - bb.min.Z, 600, abs_tol=1e-3)


def test_insert_component_with_expression():
    doc = Document()
    doc.execute("set_variable", {"name": "L", "expression": "800"})
    fid = doc.execute("insert_component", {"component": "RODILLO-50", "length": "=L"})
    feat = doc.scene[fid]
    assert feat.component == "RODILLO-50"
    assert feat.cut_length == 800  # longitud de cara (cuttable) = expresión resuelta
    bb = feat.shape.bounding_box()
    # el rodillo realista lleva eje pasante con muñones (2×25) → Z = cara + 50
    assert math.isclose(bb.max.Z - bb.min.Z, 800 + 2 * 25, abs_tol=1e-3)


def test_insert_unknown_component_rejected():
    doc = Document()
    with pytest.raises((CommandError, DocumentError)):
        doc.execute("insert_component", {"component": "NO-EXISTE"})
    assert doc.commands == []


def test_attach_base_to_top():
    doc = Document()
    a = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    b = doc.execute("create_box", {"width": 50, "depth": 50, "height": 50, "position": {"x": 500}})
    doc.execute("attach", {"feature": b, "anchor": "base", "target": a, "target_anchor": "tope"})
    bb = doc.scene[b].shape.bounding_box()
    assert math.isclose(bb.min.Z, 50, abs_tol=1e-6)  # sobre la caja a (tope z=+50)
    assert math.isclose((bb.min.X + bb.max.X) / 2, 0, abs_tol=1e-6)  # centrado en a


def test_attach_with_offset_and_self_rejected():
    doc = Document()
    a = doc.execute("create_box", {})
    b = doc.execute("create_cylinder", {})
    doc.execute("attach", {"feature": b, "anchor": "centro", "target": a, "target_anchor": "max_x", "offset": {"x": 25}})
    bb = doc.scene[b].shape.bounding_box()
    assert math.isclose((bb.min.X + bb.max.X) / 2, 75, abs_tol=1e-6)
    with pytest.raises((CommandError, DocumentError)):
        doc.execute("attach", {"feature": a, "anchor": "base", "target": a, "target_anchor": "tope"})


def test_conveyor_layout_and_bom():
    doc = Document()
    cid = doc.execute(
        "create_conveyor",
        {"largo": 2000, "ancho": 600, "altura": 750, "paso": 100, "rodillo": "RODILLO-50", "motor": "MOTOR-037"},
    )
    feats = list(doc.scene.values())
    rollers = [f for f in feats if f.component == "RODILLO-50"]
    assert len(rollers) == 19  # floor((2000-80)/100)
    assert len([f for f in feats if f.component == "PATA-REG"]) == 4
    assert len([f for f in feats if f.component == "MOTOR-037"]) == 1

    top = max(f.shape.bounding_box().max.Z for f in rollers)
    assert math.isclose(top, 750, abs_tol=1e-3)
    floor_z = min(f.shape.bounding_box().min.Z for f in feats)
    assert math.isclose(floor_z, 0, abs_tol=1e-3)

    bom = bom_from_scene(doc.scene)
    roller_row = next(r for r in bom if r["ref"] == "RODILLO-50")
    assert roller_row["cantidad"] == 19
    assert roller_row["peso_total_kg"] == pytest.approx(19 * 1.9 * 0.516, rel=1e-3)
    assert all(f.command_id == cid for f in feats)


def test_conveyor_validations():
    doc = Document()
    with pytest.raises((CommandError, DocumentError), match="[Pp]aso"):
        doc.execute("create_conveyor", {"largo": 2000, "ancho": 600, "altura": 750, "paso": 40, "rodillo": "RODILLO-50"})
    with pytest.raises((CommandError, DocumentError), match="[Aa]ncho"):
        doc.execute("create_conveyor", {"largo": 2000, "ancho": 150, "altura": 750, "paso": 100})
    assert doc.commands == []


def test_conveyor_parametric_edit_changes_roller_count():
    doc = Document()
    var = doc.execute("set_variable", {"name": "L", "expression": "2000"})
    doc.execute("create_conveyor", {"largo": "=L", "ancho": 600, "altura": 750, "paso": 100})
    count = lambda: len([f for f in doc.scene.values() if f.component == "RODILLO-50"])
    n1 = count()
    doc.edit(var, {"name": "L", "expression": "3000"})
    assert count() == n1 + 10


def test_bom_csv_totals():
    doc = Document()
    doc.execute("insert_component", {"component": "PERFIL-4040", "length": 1000})
    doc.execute("insert_component", {"component": "PERFIL-4040", "length": 1000, "position": {"x": 100}})
    doc.execute("insert_component", {"component": "FOTO-M18"})
    csv_text = bom_to_csv(bom_from_scene(doc.scene))
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("Ref;")
    assert any("PERFIL-4040" in l and ";2;" in l for l in lines)
    assert lines[-1].endswith(str(round(2 * 1.6 + 0.08, 3)))


# ----------------------------------------------------------------- API HTTP
@pytest.fixture()
def client():
    api.DOC = Document("lib-test")
    return TestClient(api.app)


def test_catalog_endpoint(client):
    items = client.get("/api/catalog").json()
    refs = {i["ref"] for i in items}
    assert {"PERFIL-4040", "RODILLO-50", "MOTOR-037", "PATA-REG", "FOTO-M18"} <= refs
    perfil = next(i for i in items if i["ref"] == "PERFIL-4040")
    assert perfil["cuttable"] and perfil["specs"]["seccion"] == "40x40"


def test_bom_endpoints(client):
    client.post("/api/commands", json={"type": "create_conveyor", "params": {"largo": 1500, "ancho": 500, "altura": 700}})
    bom = client.get("/api/bom").json()
    assert any(r["ref"] == "RODILLO-50" for r in bom)
    csv_resp = client.get("/api/bom.csv")
    assert csv_resp.status_code == 200
    assert "RODILLO-50" in csv_resp.text


def test_scene_includes_component_fields(client):
    client.post("/api/commands", json={"type": "insert_component", "params": {"component": "RODILLO-60", "length": 700}})
    feat = client.get("/api/scene").json()["features"][0]
    assert feat["component"] == "RODILLO-60"
    assert feat["cut_length"] == 700
