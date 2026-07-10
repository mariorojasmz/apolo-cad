"""V6.5c · snap_to: colocación por INTENCIÓN «junto a B hacia d con gap g», relacional
(se reevalúa al regenerar) — sin que el agente calcule offsets a mano."""

import pytest

from apolo.commands.registry import CommandError
from apolo.doc import Document, DocumentError


def _bb(doc, fid):
    b = doc.scene[fid].shape.bounding_box()
    return b


def _target_and_part(doc):
    tgt = doc.execute("create_box", {"name": "Target", "width": 100, "depth": 100, "height": 100})
    part = doc.execute("create_box", {"name": "Part", "width": 20, "depth": 20, "height": 20})
    return tgt, part


@pytest.mark.parametrize("lado,axis,expect_face", [
    ("+x", "X", ("min", 60.0)),   # part.min_x = target.max_x(50) + gap(10)
    ("-x", "X", ("max", -60.0)),  # part.max_x = target.min_x(-50) - gap(10)
    ("+y", "Y", ("min", 60.0)),
    ("-y", "Y", ("max", -60.0)),
    ("+z", "Z", ("min", 60.0)),
    ("-z", "Z", ("max", -60.0)),
])
def test_snap_to_six_sides_with_gap(lado, axis, expect_face, ):
    doc = Document("snap")
    tgt, part = _target_and_part(doc)
    doc.execute("snap_to", {"feature": part, "target": tgt, "lado": lado, "gap": 10})
    bb = _bb(doc, part)
    which, val = expect_face
    got = getattr(getattr(bb, which), axis)
    assert round(got, 3) == val


def test_snap_to_flush_gap_zero():
    """gap=0 = a ras: las caras se tocan."""
    doc = Document("flush")
    tgt, part = _target_and_part(doc)
    doc.execute("snap_to", {"feature": part, "target": tgt, "lado": "+x", "gap": 0})
    assert round(_bb(doc, part).min.X, 3) == 50.0  # pegado al max_x del target


def test_snap_to_gap_expression():
    doc = Document("expr")
    doc.execute("set_variable", {"name": "holgura", "expression": "15"})
    tgt, part = _target_and_part(doc)
    doc.execute("snap_to", {"feature": part, "target": tgt, "lado": "+x", "gap": "=holgura"})
    assert round(_bb(doc, part).min.X, 3) == 65.0  # 50 + 15


def test_snap_to_alinear_centers_other_axes():
    doc = Document("align")
    tgt = doc.execute("create_box", {"name": "T", "width": 100, "depth": 100, "height": 100})
    part = doc.execute("create_box", {"name": "P", "width": 20, "depth": 20, "height": 20,
                                      "position": {"y": 40, "z": 30}})
    doc.execute("snap_to", {"feature": part, "target": tgt, "lado": "+x", "gap": 0,
                            "alinear": ["y", "z"]})
    bb = _bb(doc, part)
    assert round((bb.min.Y + bb.max.Y) / 2, 3) == 0.0  # centrado en y con el target
    assert round((bb.min.Z + bb.max.Z) / 2, 3) == 0.0
    assert round(bb.min.X, 3) == 50.0  # el snap en x se respeta


def test_snap_to_reevaluates_when_target_moves():
    """Relacional: al mover el target, la pieza lo SIGUE en el regenerate (no coordenada fija)."""
    doc = Document("follow")
    tgt, part = _target_and_part(doc)
    doc.execute("snap_to", {"feature": part, "target": tgt, "lado": "+x", "gap": 10})
    assert round(_bb(doc, part).min.X, 3) == 60.0
    # mover el target +100 en x → su max_x pasa a 150; la pieza debe re-pegarse a 160
    doc.edit(tgt, {"name": "Target", "width": 100, "depth": 100, "height": 100,
                   "position": {"x": 100}})
    assert round(_bb(doc, part).min.X, 3) == 160.0


def test_snap_to_undo():
    doc = Document("undo")
    tgt, part = _target_and_part(doc)
    before = round(_bb(doc, part).min.X, 3)
    doc.execute("snap_to", {"feature": part, "target": tgt, "lado": "+x", "gap": 10})
    assert round(_bb(doc, part).min.X, 3) == 60.0
    doc.undo()
    assert round(_bb(doc, part).min.X, 3) == before  # -10 (centrada en origen)


def test_snap_to_self_rejected():
    doc = Document("self")
    tgt, _ = _target_and_part(doc)
    with pytest.raises((CommandError, DocumentError)):  # execute envuelve CommandError
        doc.execute("snap_to", {"feature": tgt, "target": tgt, "lado": "+x"})
