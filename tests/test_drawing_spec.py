"""Fase G · planos por intención: cotas desde datum + (endpoint en test_api)."""

from apolo.doc import Document
from apolo.drawing.sheet import compose_sheet


def test_datum_dims_position_from_base():
    doc = Document()
    doc.execute("create_box", {"name": "base", "width": 400, "depth": 200, "height": 20})
    doc.execute("create_box", {"name": "tapa", "width": 400, "depth": 200, "height": 20, "position": {"z": 500}})
    model = compose_sheet(doc.scene, datum_dims=list(doc.scene.keys()))
    labels = " ".join(lab.text for lab in model.labels)
    assert "tapa" in labels  # cota de POSICIÓN de la tapa desde la base (datum)
    assert any(ln.kind == "dim" for ln in model.lines)


def test_datum_dims_value_is_position():
    doc = Document()
    a = doc.execute("create_box", {"name": "base", "width": 200, "depth": 100, "height": 20})
    b = doc.execute("create_box", {"name": "alto", "width": 200, "depth": 100, "height": 20, "position": {"z": 500}})
    model = compose_sheet(doc.scene, datum_dims=[a, b])
    # base en z[-10,10], alto en z[490,510]; datum = z min = -10 → posición del 'alto' = 500
    assert any("alto 500" in lab.text for lab in model.labels)
