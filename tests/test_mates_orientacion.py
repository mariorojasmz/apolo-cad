"""Mates de orientación: paralelo (normal de B || normal de A) y ángulo (a `value`
grados). Orientan sin mover la posición de B. (A1: mate paralelo/ángulo.)"""

import math

from apolo.assembly.mates import _desired_current_frames
from apolo.doc.document import Document


def _zaxis(m):
    return (m[0][2], m[1][2], m[2][2])  # frame(): columnas = ejes → z = col 2


def _ang(u, v):
    d = sum(u[i] * v[i] for i in range(3))
    return math.degrees(math.acos(max(-1.0, min(1.0, d))))


def test_paralelo_orienta_normal():
    desired, _ = _desired_current_frames((0, 0, 0), (1, 0, 0), (400, 0, 0), (0, 0, 1), "paralelo", 0, False)
    assert _ang(_zaxis(desired), (1, 0, 0)) < 0.5  # normal de B paralela a la de A


def test_angulo_orienta_a_value_grados():
    for val in (30, 45, 60):
        desired, _ = _desired_current_frames((0, 0, 0), (1, 0, 0), (400, 0, 0), (0, 0, 1), "angulo", val, False)
        assert abs(_ang(_zaxis(desired), (1, 0, 0)) - val) < 0.5


def test_mate_paralelo_end_to_end():
    """Caja alta (Z=120): tras paralelo (tope +Z → +X) el eje largo queda en X."""
    doc = Document("t")
    a = doc.execute("create_box", {"name": "A", "width": 100, "depth": 100, "height": 100})
    b = doc.execute("create_box", {"name": "B", "width": 60, "depth": 60, "height": 120, "position": {"x": 400}})
    bb0 = doc.scene[b].shape.bounding_box()
    assert (bb0.max.Z - bb0.min.Z) > 110  # alto en Z al inicio
    doc.execute("add_mate", {
        "name": "m", "type": "paralelo", "feature_a": a, "feature_b": b,
        "ref_a": {"mode": "cara", "face": "max_x"}, "ref_b": {"mode": "cara", "face": "tope"},
    })
    bb = doc.scene[b].shape.bounding_box()
    assert (bb.max.X - bb.min.X) > 110  # el eje largo (era Z) ahora va en X
