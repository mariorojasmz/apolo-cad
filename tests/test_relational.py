"""Fase 4 · colocación por intención: center_in y distribute."""

from apolo.doc import Document


def _center(doc, cid, ax):
    bb = doc.scene[cid].shape.bounding_box()
    return {
        "x": (bb.min.X + bb.max.X) / 2,
        "y": (bb.min.Y + bb.max.Y) / 2,
        "z": (bb.min.Z + bb.max.Z) / 2,
    }[ax]


def test_center_in_centers_and_follows_changes():
    """center_in centra el sólido en el contenedor; al mover/redimensionar el contenedor,
    se recentra solo en el regenerate (relacional, no coordenada fija)."""
    doc = Document()
    big = doc.execute(
        "create_box", {"width": 400, "depth": 400, "height": 40, "position": {"x": 100, "y": 50}}
    )
    small = doc.execute("create_box", {"width": 50, "depth": 50, "height": 50})
    doc.execute("center_in", {"feature": small, "into": big, "axes": ["x", "y"]})
    assert round(_center(doc, small, "x")) == 100
    assert round(_center(doc, small, "y")) == 50

    doc.edit(big, {"width": 400, "depth": 400, "height": 40, "position": {"x": -200, "y": 0}})
    assert round(_center(doc, small, "x")) == -200  # cascada: se recentra solo
    assert round(_center(doc, small, "y")) == 0


def test_distribute_even_spacing():
    doc = Document()
    ids = [doc.execute("create_box", {"width": 20, "depth": 20, "height": 20}) for _ in range(4)]
    doc.execute("distribute", {"features": ids, "axis": "x", "start": 0, "end": 300})
    assert [round(_center(doc, c, "x")) for c in ids] == [0, 100, 200, 300]


def test_distribute_accepts_expression_bounds():
    """start/end aceptan =expr (resueltas contra variables del proyecto)."""
    doc = Document()
    doc.execute("set_variable", {"name": "ancho", "expression": "600"})
    ids = [doc.execute("create_box", {"width": 20, "depth": 20, "height": 20}) for _ in range(3)]
    doc.execute("distribute", {"features": ids, "axis": "x", "start": 0, "end": "=ancho"})
    assert [round(_center(doc, c, "x")) for c in ids] == [0, 300, 600]
