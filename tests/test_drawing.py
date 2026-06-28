import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.drawing import compose_sheet, project_views, real_dims, sheet_to_dxf, sheet_to_pdf, sheet_to_svg
from apolo.drawing.sheet import _pick_scale  # noqa: PLC2701
from apolo.drawing.projection import ViewProjection


@pytest.fixture(scope="module")
def box_doc():
    doc = Document("plano-test")
    doc.execute("create_box", {"width": 200, "depth": 100, "height": 50})
    return doc


def test_projection_views_match_box(box_doc):
    views = project_views(box_doc.scene, ["alzado", "planta", "lateral"])
    assert views["alzado"].width == pytest.approx(200, rel=1e-2)
    assert views["alzado"].height == pytest.approx(50, rel=1e-2)
    assert views["planta"].width == pytest.approx(200, rel=1e-2)
    assert views["planta"].height == pytest.approx(100, rel=1e-2)
    assert views["lateral"].width == pytest.approx(100, rel=1e-2)
    assert all(len(v.visible) >= 4 for v in views.values())


def test_projection_empty_scene_rejected():
    with pytest.raises(ValueError, match="vacía"):
        project_views({}, ["alzado"])


def test_real_dims(box_doc):
    assert real_dims(box_doc.scene) == {"X": 200, "Y": 100, "Z": 50}


def test_pick_scale_standard():
    big = ViewProjection("alzado", bounds=(0, 0, 2000, 800))
    factor, label = _pick_scale({"alzado": big}, 170.0, 110.0)
    assert label == "1:20" and factor == 0.05
    small = ViewProjection("alzado", bounds=(0, 0, 100, 50))
    factor, label = _pick_scale({"alzado": small}, 170.0, 110.0)
    assert label == "1:1"


def test_pick_scale_intermediate():
    # pieza alta y angosta: el fit cae entre 1:20 (0.05) y 1:50 (0.02); con las escalas
    # intermedias debe elegir 1:25 (llena la celda) en vez de saltar hasta 1:50.
    tall = ViewProjection("alzado", bounds=(0, 0, 500, 2000))
    factor, label = _pick_scale({"alzado": tall}, 160.0, 98.5)
    assert label == "1:25" and factor == 0.04


def test_compose_sheet_contents(box_doc):
    model = compose_sheet(box_doc.scene, sheet="A3", project_name="Mi máquina")
    assert (model.width, model.height) == (420, 297)
    texts = [l.text for l in model.labels]
    assert "ALZADO" in texts and "PLANTA" in texts and "PERFIL" in texts
    assert "Mi máquina" in texts
    assert any(t.startswith("1:") for t in texts)  # escala en el cajetín nuevo (valor "1:2 · 1/1 A3")
    assert model.meta["scale_label"] == "1:2"  # 200 mm no cabe a 1:1 en la celda A3
    assert "200" in texts and "50" in texts and "100" in texts  # cotas generales
    kinds = {l.kind for l in model.lines}
    assert {"visible", "frame", "dim"} <= kinds
    # todo dentro de la lámina
    for line in model.lines:
        for v, lim in ((line.x1, 420), (line.x2, 420), (line.y1, 297), (line.y2, 297)):
            assert -1 <= v <= lim + 1


def test_hidden_lines_option(box_doc):
    doc = Document()
    doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    doc.execute("create_cylinder", {"radius": 20, "height": 200})
    doc.execute("boolean_op", {"operation": "cut", "target": "c1", "tools": ["c2"]})
    views = project_views(doc.scene, ["alzado"], include_hidden=True)
    assert len(views["alzado"].hidden) > 0  # el taladro interior aparece oculto


def test_svg_export(box_doc):
    svg = sheet_to_svg(compose_sheet(box_doc.scene))
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "ALZADO" in svg and "stroke-dasharray" not in svg.split("ISOMÉTRICA")[0][:200]


def test_pdf_export(box_doc):
    pdf = sheet_to_pdf(compose_sheet(box_doc.scene))
    assert pdf[:5] == b"%PDF-"


def test_dxf_export_roundtrip(box_doc, tmp_path):
    import ezdxf

    data = sheet_to_dxf(compose_sheet(box_doc.scene))
    path = tmp_path / "plano.dxf"
    path.write_bytes(data)
    doc = ezdxf.readfile(str(path))
    layers = {layer.dxf.name for layer in doc.layers}
    assert {"VISIBLE", "MARCO", "COTAS"} <= layers
    assert len(list(doc.modelspace().query("LINE"))) > 20


# ------------------------------------------------------------------- API HTTP
@pytest.fixture()
def client():
    api.DOC = Document("f5-api")
    return TestClient(api.app)


def test_drawing_endpoints(client):
    assert client.get("/api/drawing.svg").status_code == 400  # escena vacía

    client.post("/api/commands", json={"type": "create_box", "params": {"width": 300, "depth": 150, "height": 80}})
    svg = client.get("/api/drawing.svg?sheet=A4")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg")
    assert "ALZADO" in svg.text

    pdf = client.get("/api/drawing.pdf")
    assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"

    dxf = client.get("/api/drawing.dxf?hidden=true")
    assert dxf.status_code == 200 and b"VISIBLE" in dxf.content

    assert client.get("/api/drawing.svg?sheet=A9").status_code == 400
