"""Fase F · salida e interoperabilidad (lineweight DXF, fuentes PDF, A0–A4, barra/zonas)."""

import io

from apolo.doc import Document
from apolo.drawing.dxf import sheet_to_dxf
from apolo.drawing.pdf import sheet_to_pdf
from apolo.drawing.sheet import compose_sheet


def _box():
    doc = Document()
    doc.execute("create_box", {"width": 200, "depth": 100, "height": 50})
    return doc


def test_sheet_sizes_a0_to_a4():
    model = compose_sheet(_box().scene, sheet="A0")
    assert (model.width, model.height) == (1189.0, 841.0)
    assert (compose_sheet(_box().scene, sheet="A2").width) == 594.0


def test_zone_grid_and_scale_bar():
    texts = [lab.text for lab in compose_sheet(_box().scene).labels]
    assert "ESCALA (mm)" in texts
    assert "A" in texts and "1" in texts and "8" in texts  # zonas de referencia


def test_dxf_layers_have_lineweight():
    import ezdxf

    data = sheet_to_dxf(compose_sheet(_box().scene, section=True))
    doc = ezdxf.read(io.StringIO(data.decode("utf-8")))
    assert doc.layers.get("VISIBLE").dxf.lineweight == 50
    assert doc.layers.get("COTAS").dxf.lineweight == 25


def test_pdf_renders_a4():
    pdf = sheet_to_pdf(compose_sheet(_box().scene, sheet="A4"))
    assert pdf[:4] == b"%PDF"
