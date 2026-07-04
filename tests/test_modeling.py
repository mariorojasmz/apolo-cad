import io
import math

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.commands.registry import CommandError
from apolo.doc import Document, DocumentError
from apolo.kernel.selectors import SelectorError, resolve_edges, resolve_faces


@pytest.fixture()
def box_shape():
    doc = Document()
    fid = doc.execute("create_box", {"width": 100, "depth": 80, "height": 50})
    return doc.scene[fid].shape


# ----------------------------------------------------------------- selectores
def test_selector_direccion(box_shape):
    assert len(resolve_edges(box_shape, {"mode": "direccion", "direction": "z"})) == 4
    assert len(resolve_edges(box_shape, {"mode": "direccion", "direction": "x"})) == 4


def test_selector_cara(box_shape):
    edges = resolve_edges(box_shape, {"mode": "cara", "face": "tope"})
    assert len(edges) == 4
    assert all(abs(e.center().Z - 25) < 1e-6 for e in edges)
    faces = resolve_faces(box_shape, {"mode": "cara", "face": "base"})
    assert len(faces) == 1 and abs(faces[0].center().Z + 25) < 1e-6


def test_selector_longitud_y_cerca(box_shape):
    assert len(resolve_edges(box_shape, {"mode": "longitud", "min": 90})) == 4  # solo las de 100
    edge = resolve_edges(box_shape, {"mode": "cerca", "point": [0, -40, 25], "count": 1})[0]
    assert abs(edge.center().Y + 40) < 1e-6 and abs(edge.center().Z - 25) < 1e-6


def test_selector_errores(box_shape):
    with pytest.raises(SelectorError, match="ninguna arista"):
        resolve_edges(box_shape, {"mode": "longitud", "min": 9999})
    with pytest.raises(SelectorError, match="cerca"):
        resolve_edges(box_shape, {"mode": "cerca"})
    with pytest.raises(SelectorError, match="desconocido"):
        resolve_edges(box_shape, {"mode": "magia"})


# ------------------------------------------------------------------ comandos
def test_fillet_analytical():
    doc = Document()
    b = doc.execute("create_box", {"width": 100, "depth": 100, "height": 50})
    doc.execute("fillet", {"feature": b, "edges": {"mode": "direccion", "direction": "z"}, "radius": 10})
    expected = 100 * 100 * 50 - 4 * (100 - math.pi * 25) * 50
    assert doc.scene[b].shape.volume == pytest.approx(expected, rel=1e-6)


def test_fillet_impossible_radius_rejected():
    doc = Document()
    b = doc.execute("create_box", {"width": 20, "depth": 20, "height": 20})
    with pytest.raises(DocumentError, match="[Rr]edondeo"):
        doc.execute("fillet", {"feature": b, "edges": {"mode": "todas"}, "radius": 50})
    assert len(doc.commands) == 1  # rollback


def test_fillet_error_reports_edge_ceiling():
    """Fix H (V6.1): el error de un redondeo imposible nombra el TOPE — la longitud de
    la arista más corta seleccionada — para que el radio sea accionable."""
    doc = Document()
    b = doc.execute("create_box", {"width": 20, "depth": 20, "height": 20})
    with pytest.raises(DocumentError, match="arista más corta.*20"):
        doc.execute("fillet", {"feature": b, "edges": {"mode": "todas"}, "radius": 50})


def test_shell_thickness_too_large_precheck():
    """Fix H (V6.1): un espesor que se come más de la mitad de la dimensión menor se
    RECHAZA con un mensaje claro ANTES de llamar a OCCT (pre-check por bbox)."""
    doc = Document()
    b = doc.execute("create_box", {"width": 60, "depth": 60, "height": 20})  # dim menor = 20
    with pytest.raises(DocumentError, match="dimensión menor.*20"):
        doc.execute("shell", {"feature": b, "openings": {"mode": "cara", "face": "tope"},
                              "thickness": 12})  # 2*12=24 >= 20 → vacío garantizado
    assert len(doc.commands) == 1  # rollback, doc intacto


def test_chamfer_and_shell():
    doc = Document()
    b = doc.execute("create_box", {"width": 60, "depth": 60, "height": 60})
    v0 = doc.scene[b].shape.volume
    doc.execute("chamfer", {"feature": b, "edges": {"mode": "cara", "face": "tope"}, "distance": 5})
    assert doc.scene[b].shape.volume < v0

    c = doc.execute("create_box", {"width": 80, "depth": 80, "height": 60, "position": {"x": 200}})
    doc.execute("shell", {"feature": c, "openings": {"mode": "cara", "face": "tope"}, "thickness": 4})
    shelled = doc.scene[c].shape.volume
    assert 0.1 * 80 * 80 * 60 < shelled < 0.4 * 80 * 80 * 60


def test_drill_hole_through_and_blind():
    doc = Document()
    b = doc.execute("create_box", {"width": 100, "depth": 100, "height": 30})
    doc.execute("drill_hole", {"feature": b, "position": {"z": 15}, "axis": "-z", "diameter": 20, "depth": 0})
    expected = 100 * 100 * 30 - math.pi * 100 * 30
    assert doc.scene[b].shape.volume == pytest.approx(expected, rel=1e-4)

    c = doc.execute("create_box", {"width": 100, "depth": 100, "height": 30, "position": {"x": 300}})
    doc.execute(
        "drill_hole",
        {"feature": c, "position": {"x": 300, "z": 15}, "axis": "-z", "diameter": 10, "depth": 10,
         "counterbore_d": 20, "counterbore_depth": 5},
    )
    # broca Ø10×10 + caladrillo Ø20×5, descontando el solape de ambos cilindros
    expected_c = 100 * 100 * 30 - math.pi * 25 * 10 - math.pi * 100 * 5 + math.pi * 25 * 5
    assert doc.scene[c].shape.volume == pytest.approx(expected_c, rel=1e-3)

    # taladro que no toca el sólido → error con rollback
    with pytest.raises(DocumentError, match="no toca"):
        doc.execute("drill_hole", {"feature": b, "position": {"x": 999, "z": 15}, "axis": "-z", "diameter": 5})


def test_pattern_circular_positions():
    doc = Document()
    p = doc.execute("create_cylinder", {"radius": 5, "height": 20, "position": {"x": 100}})
    pid = doc.execute("pattern_circular", {"feature": p, "count": 4, "axis_dir": "z"})
    copies = [f for f in doc.scene if f.startswith(f"{pid}_")]
    assert len(copies) == 3
    bb = doc.scene[f"{pid}_1"].shape.bounding_box()  # 90°: (100,0) → (0,100)
    assert (bb.min.X + bb.max.X) / 2 == pytest.approx(0, abs=1e-3)
    assert (bb.min.Y + bb.max.Y) / 2 == pytest.approx(100, abs=1e-3)


def test_mirror_feature():
    doc = Document()
    b = doc.execute("create_box", {"width": 40, "depth": 40, "height": 40, "position": {"x": 50}})
    m = doc.execute("mirror_feature", {"feature": b, "plane": "yz"})
    bb = doc.scene[m].shape.bounding_box()
    assert (bb.min.X + bb.max.X) / 2 == pytest.approx(-50, abs=1e-6)


def test_create_revolve_tube():
    doc = Document()
    r = doc.execute("create_revolve", {"profile": [[20, 0], [40, 0], [40, 30], [20, 30]]})
    assert doc.scene[r].shape.volume == pytest.approx(math.pi * (40**2 - 20**2) * 30, rel=1e-6)
    with pytest.raises((CommandError, DocumentError), match="negativo"):
        doc.execute("create_revolve", {"profile": [[-5, 0], [10, 0], [10, 10]]})


def test_create_extrude_poly():
    doc = Document()
    e = doc.execute("create_extrude_poly", {"points": [[0, 0], [60, 0], [60, 40], [30, 60], [0, 40]], "height": 20})
    assert doc.scene[e].shape.volume == pytest.approx(3000 * 20, rel=1e-6)  # shoelace = 3000 mm²


def test_modeling_with_expressions():
    doc = Document()
    doc.execute("set_variable", {"name": "r", "expression": "8"})
    b = doc.execute("create_box", {"width": 100, "depth": 100, "height": 50})
    doc.execute("fillet", {"feature": b, "edges": {"mode": "direccion", "direction": "z"}, "radius": "=r"})
    expected = 100 * 100 * 50 - 4 * (64 - math.pi * 16) * 50
    assert doc.scene[b].shape.volume == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------- import STEP
def _box_step_bytes() -> bytes:
    import os
    import tempfile
    from pathlib import Path

    from apolo.kernel import export_step_file

    doc = Document()
    doc.execute("create_box", {"width": 50, "depth": 40, "height": 30})
    fd, raw_path = tempfile.mkstemp(suffix=".step")
    os.close(fd)  # en Windows el descriptor abierto bloquea escritura/borrado
    tmp = Path(raw_path)
    export_step_file([doc.scene["c1"].shape], str(tmp))
    data = tmp.read_bytes()
    tmp.unlink(missing_ok=True)
    return data


def test_import_step_roundtrip_and_apolo_v2():
    doc = Document()
    digest = doc.add_attachment(_box_step_bytes())
    fid = doc.execute("import_step", {"attachment": digest, "name": "Proveedor"})
    assert doc.scene[fid].shape.volume == pytest.approx(50 * 40 * 30, rel=1e-6)

    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert doc2.scene[fid].shape.volume == pytest.approx(50 * 40 * 30, rel=1e-6)
    assert digest in doc2.attachments


def test_import_missing_attachment():
    doc = Document()
    with pytest.raises(DocumentError, match="adjunto"):
        doc.execute("import_step", {"attachment": "nope", "name": "x"})


# ------------------------------------------------------------------- API HTTP
@pytest.fixture()
def client():
    api.DOC = Document("f7-api")
    return TestClient(api.app)


def test_import_endpoint_and_fillet_cerca(client):
    files = {"file": ("pieza.step", io.BytesIO(_box_step_bytes()), "application/step")}
    r = client.post("/api/import", files=files)
    assert r.status_code == 200
    feat = r.json()["features"][0]
    assert feat["name"] == "pieza"

    r = client.post(
        "/api/commands",
        json={
            "type": "fillet",
            "params": {
                "feature": feat["id"],
                "edges": {"mode": "cerca", "point": [25, 20, 15], "count": 1},
                "radius": 5,
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["features"][0]["volume_mm3"] < 50 * 40 * 30
