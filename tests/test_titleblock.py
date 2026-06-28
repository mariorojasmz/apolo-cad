"""Fase C · cajetín profesional + bloque de revisiones."""

from apolo.doc import Document
from apolo.drawing.sheet import compose_sheet
from apolo.drawing.svg import sheet_to_svg


def test_title_block_pro_fields():
    doc = Document()
    doc.execute("create_box", {"name": "tabla", "width": 200, "depth": 18, "height": 400})
    model = compose_sheet(doc.scene, meta={
        "drawing_no": "28", "material": "madera", "drawn_by": "AB", "tolerance": "±0.3", "finish": "barniz",
    })
    labels = " ".join(lab.text for lab in model.labels)
    assert "Plano 28" in labels
    assert "madera" in labels and "barniz" in labels
    assert "Material" in labels and "±0.3" in labels
    assert sheet_to_svg(model).lstrip().startswith("<svg")


def test_title_block_revisions_table():
    doc = Document()
    doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    revs = [{"rev": 1, "date": "2026-06-24", "note": "inicial"},
            {"rev": 2, "date": "2026-06-25", "note": "ajuste hojas"}]
    model = compose_sheet(doc.scene, meta={"revisions": revs})
    labels = " ".join(lab.text for lab in model.labels)
    assert "Rev" in labels and "ajuste hojas" in labels


def test_title_block_auto_weight_material():
    doc = Document()
    doc.execute("create_box", {"name": "tabla madera", "width": 1000, "depth": 18, "height": 300})
    model = compose_sheet(doc.scene)  # sin meta → material/peso automáticos
    labels = " ".join(lab.text for lab in model.labels)
    assert "madera" in labels and "kg" in labels
