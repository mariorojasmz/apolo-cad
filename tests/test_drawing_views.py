"""Fase B · cortes nombrados/por eje + material, vistas de detalle, rayado."""

from apolo.doc import Document
from apolo.drawing.dxf import sheet_to_dxf
from apolo.drawing.pdf import sheet_to_pdf
from apolo.drawing.projection import detail_view, project_views, section_projection
from apolo.drawing.sheet import compose_sheet
from apolo.drawing.svg import sheet_to_svg


def test_section_by_axis_carries_material():
    doc = Document()
    doc.execute("create_box", {"name": "tabla madera", "width": 200, "depth": 100, "height": 40})
    for axis in ("x", "y", "z"):
        proj, polys, cut, ax = section_projection(doc.scene, axis=axis)
        assert ax == axis
        assert polys, f"el corte {axis} no produjo caras"
        rings, material = polys[0]
        assert material == "madera"
        assert len(rings[0]) >= 3  # contorno cerrado


def test_detail_view_crops_and_scales():
    doc = Document()
    doc.execute("create_box", {"width": 200, "depth": 100, "height": 40})
    alz = project_views(doc.scene, ["alzado"])["alzado"]
    det = detail_view(alz, center=(0, 0), radius=300, scale=2.0)
    assert det.visible  # captura el alzado completo
    assert det.width >= alz.width * 1.5  # a ×2 es claramente más grande


def test_section_exporters_hatch_by_material():
    doc = Document()
    doc.execute("create_box", {"name": "tabla", "width": 200, "depth": 100, "height": 40})
    model = compose_sheet(doc.scene, section=True, bom=False)
    assert any(p.material for p in model.polygons)
    assert "url(#h_" in sheet_to_svg(model)  # patrón de rayado por material
    assert b"SECTION" in sheet_to_dxf(model)[:80]
    assert sheet_to_pdf(model)[:4] == b"%PDF"


def test_section_named_b_b():
    """section='y' produce un CORTE B-B."""
    doc = Document()
    doc.execute("create_box", {"name": "tabla", "width": 200, "depth": 100, "height": 40})
    model = compose_sheet(doc.scene, section="y", bom=False)
    assert any("CORTE B-B" in lab.text for lab in model.labels)


def test_detail_bubble_on_sheet():
    doc = Document()
    doc.execute("create_box", {"width": 200, "depth": 100, "height": 40})
    model = compose_sheet(doc.scene, detail={"view": "alzado", "u": 0, "v": 0, "radius": 80, "scale": 2.0})
    assert any("DETALLE A" in lab.text for lab in model.labels)
