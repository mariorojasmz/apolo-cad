"""Simulación de gravedad de toda la máquina (Fase 2): qué pieza se cae.

Requiere MuJoCo (extra opcional `physics`); se omite si no está instalado."""

import pytest

pytest.importorskip("mujoco")

from apolo.doc.document import Document  # noqa: E402
from apolo.physics.hull import hull_vertices  # noqa: E402
from apolo.physics.stability import stability_test  # noqa: E402


def _box(doc, name, z, size=100):
    return doc.execute("create_box", {"name": name, "width": size, "depth": size, "height": size,
                                      "position": {"x": 0, "y": 0, "z": z}})


def _sim(doc, **kw):
    return stability_test(doc.scene, doc.joints, doc.mates, doc.fasteners, doc.grounds,
                          seconds=1.5, **kw)


def test_hull_vertices_of_box():
    doc = Document("t")
    b = _box(doc, "B", 50)
    verts = hull_vertices(doc.scene[b].shape)
    assert len(verts) >= 4  # un cubo da al menos sus 8 esquinas


def test_grounded_stays_floating_falls():
    doc = Document("t")
    a = _box(doc, "anclada", 50)
    b = _box(doc, "en_aire", 600)
    doc.execute("ground", {"name": "g", "feature": a})
    res = _sim(doc)
    assert res["n_dynamic"] == 1  # solo la no anclada es cuerpo dinámico
    fell_ids = [r["id"] for r in res["fell"]]
    assert b in fell_ids
    assert a not in fell_ids
    assert next(r["caida_mm"] for r in res["fell"] if r["id"] == b) > 100


def test_resting_part_does_not_fall():
    """El valor de la Fase 2 sobre el chequeo estático: una pieza NO sujeta que REPOSA
    sobre algo firme NO cae (la física decide quién aguanta a quién)."""
    doc = Document("t")
    a = _box(doc, "base", 50)         # sobre el piso
    b = _box(doc, "encima", 150)      # apoyada justo sobre 'base' (no fijada)
    doc.execute("ground", {"name": "g", "feature": a})
    res = _sim(doc)
    fell_ids = [r["id"] for r in res["fell"]]
    assert b not in fell_ids  # apoyada → aguanta, aunque no esté fijada
    assert any(r["id"] == b for r in res["estables"])


def test_exclude_forces_fall():
    """`exclude` trata una pieza como NO sujeta ('¿y si le falta el tornillo?')."""
    doc = Document("t")
    a = _box(doc, "base", 50)
    b = _box(doc, "encima", 150)
    doc.execute("ground", {"name": "g", "feature": a})
    doc.execute("fasten", {"name": "f", "a": a, "b": b})  # b sujeta a la base
    assert _sim(doc)["n_dynamic"] == 0  # todo sujeto
    res = _sim(doc, exclude=[b])  # ahora b NO está sujeta → es dinámica
    assert res["n_dynamic"] == 1
