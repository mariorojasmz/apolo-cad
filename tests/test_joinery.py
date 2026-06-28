"""Uniones de ebanistería (`add_joinery`): espiga-mortaja, dado y clavijas (dowel).
Verifica que cortan/añaden la geometría correcta y que la espiga encaja en la mortaja
con holgura (sin interpenetración)."""

from apolo.doc.document import Document
from apolo.library.checks import interference_report


def _two_boards():
    """B = tabla base (recibe), A = tabla que llega por arriba (entra). Interfaz en y=20."""
    doc = Document("t")
    b = doc.execute("create_box", {"name": "B", "width": 200, "depth": 40, "height": 200})
    a = doc.execute("create_box", {"name": "A", "width": 60, "depth": 200, "height": 200, "position": {"y": 120}})
    return doc, a, b


def test_espiga_mortaja_encaja():
    doc, a, b = _two_boards()
    va0, vb0 = doc.scene[a].shape.volume, doc.scene[b].shape.volume
    doc.execute("add_joinery", {
        "name": "u1", "type": "espiga_mortaja", "feature_a": a, "feature_b": b,
        "position": {"y": 20}, "axis": {"y": 1}, "width": 20, "height": 30, "depth": 25, "clearance": 0.3,
    })
    assert doc.scene[a].shape.volume > va0   # A gana la espiga
    assert doc.scene[b].shape.volume < vb0   # B pierde la mortaja
    # encaja con holgura: A y B casi no se solapan
    rep = interference_report(doc.scene)
    vol = rep["interferencias"][0]["volumen_mm3"] if rep["interferencias"] else 0.0
    assert vol < 50.0


def test_dado_corta_canal_solo_en_B():
    doc, a, b = _two_boards()
    va0, vb0 = doc.scene[a].shape.volume, doc.scene[b].shape.volume
    doc.execute("add_joinery", {
        "name": "u2", "type": "dado", "feature_a": a, "feature_b": b,
        "position": {"y": 20}, "axis": {"y": 1}, "width": 18, "height": 200, "depth": 10,
    })
    assert doc.scene[a].shape.volume == va0   # A intacta
    assert doc.scene[b].shape.volume < vb0    # B con el canal


def test_dowel_taladra_ambas_y_anade_clavijas():
    doc, a, b = _two_boards()
    va0, vb0 = doc.scene[a].shape.volume, doc.scene[b].shape.volume
    n0 = len(doc.scene)
    doc.execute("add_joinery", {
        "name": "u3", "type": "dowel", "feature_a": a, "feature_b": b,
        "position": {"y": 20}, "axis": {"y": 1}, "width": 8, "depth": 40, "count": 3, "spacing": 32,
    })
    assert doc.scene[a].shape.volume < va0
    assert doc.scene[b].shape.volume < vb0
    pins = [f for f in doc.scene.values() if "clavija" in f.name]
    assert len(pins) == 3 and len(doc.scene) == n0 + 3
