"""Fase 2 · medición exacta y consulta espacial (no existían)."""

from apolo.doc import Document
from apolo.kernel.measure import features_near, measure_distance


def test_measure_distance_gap():
    """Cajas 100³ en x=0 y x=300: caras internas en x=50 y x=250 → gap 200 mm."""
    doc = Document()
    a = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    b = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 300}})
    res = measure_distance(doc.scene[a].shape, doc.scene[b].shape)
    assert res["dist_mm"] == 200.0
    assert len(res["punto_a"]) == 3 and len(res["punto_b"]) == 3


def test_measure_overlap_is_zero():
    doc = Document()
    a = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    b = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 50}})
    assert measure_distance(doc.scene[a].shape, doc.scene[b].shape)["dist_mm"] == 0.0


def test_features_near_filters_and_sorts():
    doc = Document()
    a = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 1000}})
    cercanas = features_near(doc.scene, [0, 0, 0], 60)
    assert [e["id"] for e in cercanas] == [a]  # la lejana queda fuera del radio
