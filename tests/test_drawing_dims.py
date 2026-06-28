"""Fase A · motor de cotas (flechas + tolerancia) y marcas de centro."""

from apolo.doc import Document
from apolo.drawing.dimensions import center_mark, linear_dim
from apolo.drawing.dxf import sheet_to_dxf
from apolo.drawing.pdf import sheet_to_pdf
from apolo.drawing.sheet import SheetModel, compose_sheet
from apolo.drawing.svg import sheet_to_svg


def test_linear_dim_arrows_and_tolerance():
    m = SheetModel(100, 100)
    linear_dim(m, (10, 10), (60, 10), vertical=False, value=50, tol=0.5, name="ANCHO")
    assert sum(1 for ln in m.lines if ln.kind == "dim") >= 5  # testigos + línea + flechas
    assert any("±0.5" in lab.text and "ANCHO" in lab.text for lab in m.labels)


def test_center_mark_adds_center_lines():
    m = SheetModel(100, 100)
    center_mark(m, 50, 50, 4)
    cross = [ln for ln in m.lines if ln.kind == "center"]
    assert len(cross) == 2  # cruz (horizontal + vertical)


def test_compose_sheet_marks_centers_on_cylinder():
    """Un cilindro proyecta un círculo en planta → marca de centro en el plano."""
    doc = Document()
    doc.execute("create_cylinder", {"radius": 30, "height": 80})
    model = compose_sheet(doc.scene)
    assert any(ln.kind == "center" for ln in model.lines)


def test_exporters_valid_with_new_kinds():
    doc = Document()
    doc.execute("create_cylinder", {"radius": 30, "height": 80})
    model = compose_sheet(doc.scene)
    assert sheet_to_svg(model).lstrip().startswith("<svg")
    assert b"SECTION" in sheet_to_dxf(model)[:80]
    assert sheet_to_pdf(model)[:4] == b"%PDF"
