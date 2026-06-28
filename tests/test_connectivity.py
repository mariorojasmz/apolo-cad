"""Conectividad de ensamblaje + validación de soundness (¿cada pieza tiene
sujeción hasta el piso?). Fase 0+1 de la validación de ensamblaje por gravedad."""

import pytest

from apolo.assembly.autodetect import detect_connections
from apolo.assembly.connectivity import build_graph, soundness_report
from apolo.doc.document import Document, DocumentError


def _box(doc, name, z):
    """Caja 100³ centrada en (0,0,z) → su base está en z-50."""
    return doc.execute("create_box", {"name": name, "width": 100, "depth": 100, "height": 100,
                                      "position": {"x": 0, "y": 0, "z": z}})


def _report(doc, **kw):
    graph = build_graph(doc.scene, doc.joints, doc.mates, doc.fasteners, doc.grounds, **kw)
    return soundness_report(graph)


# ----------------------------------------------------------- comandos / registro
def test_ground_and_fasten_register():
    doc = Document("t")
    a = _box(doc, "A", 50)
    b = _box(doc, "B", 150)
    doc.execute("ground", {"name": "g1", "feature": a})
    doc.execute("fasten", {"name": "f1", "a": a, "b": b, "kind": "perno"})
    assert len(doc.grounds) == 1
    assert len(doc.fasteners) == 1
    rep = _report(doc)
    assert rep["n_floating"] == 0
    assert set(rep["grounded"]) == {a, b}


def test_floating_part_detected():
    doc = Document("t")
    a = _box(doc, "A", 50)
    b = _box(doc, "B", 500)  # en el aire, sin unión
    doc.execute("ground", {"name": "g1", "feature": a})
    rep = _report(doc)
    assert rep["floating"] == [b]
    assert b in rep["isolated"]  # sin ninguna unión


def test_no_ground_everything_floats():
    doc = Document("t")
    a = _box(doc, "A", 50)
    b = _box(doc, "B", 150)
    doc.execute("fasten", {"name": "f1", "a": a, "b": b})
    rep = _report(doc)
    assert rep["has_ground"] is False
    assert rep["n_floating"] == 2  # unidas entre sí pero a nada del piso


def test_transitive_support_chain():
    doc = Document("t")
    a = _box(doc, "A", 50)
    b = _box(doc, "B", 150)
    c = _box(doc, "C", 250)
    doc.execute("ground", {"name": "g", "feature": a})
    doc.execute("fasten", {"name": "f1", "a": a, "b": b})
    doc.execute("fasten", {"name": "f2", "a": b, "b": c})
    rep = _report(doc)
    assert rep["n_floating"] == 0  # C llega a tierra por la cadena A-B-C


# ----------------------------------------------------------- validación / integridad
def test_fasten_self_rejected():
    doc = Document("t")
    a = _box(doc, "A", 50)
    with pytest.raises(DocumentError):
        doc.execute("fasten", {"name": "bad", "a": a, "b": a})


def test_fasten_dangling_ref_rejected():
    doc = Document("t")
    a = _box(doc, "A", 50)
    with pytest.raises(DocumentError):
        doc.execute("fasten", {"name": "f", "a": a, "b": "c999"})


def test_removing_fastened_solid_rejects():
    doc = Document("t")
    a = _box(doc, "A", 50)
    b = _box(doc, "B", 150)
    doc.execute("fasten", {"name": "f", "a": a, "b": b})
    with pytest.raises(DocumentError):
        doc.remove_commands([b])  # el fijador quedaría colgando


def test_duplicate_name_rejected():
    doc = Document("t")
    a = _box(doc, "A", 50)
    b = _box(doc, "B", 150)
    doc.execute("fasten", {"name": "dup", "a": a, "b": b})
    with pytest.raises(DocumentError):
        doc.execute("fasten", {"name": "dup", "a": b, "b": a})


# ----------------------------------------------------------- persistencia / undo
def test_connectivity_survives_roundtrip():
    doc = Document("t")
    a = _box(doc, "A", 50)
    b = _box(doc, "B", 150)
    doc.execute("ground", {"name": "g", "feature": a})
    doc.execute("fasten", {"name": "f", "a": a, "b": b})
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert len(doc2.grounds) == 1 and len(doc2.fasteners) == 1
    assert _report(doc2)["n_floating"] == 0


def test_undo_removes_fastener():
    doc = Document("t")
    a = _box(doc, "A", 50)
    b = _box(doc, "B", 150)
    doc.execute("ground", {"name": "g", "feature": a})
    doc.execute("fasten", {"name": "f", "a": a, "b": b})
    assert _report(doc)["n_floating"] == 0
    doc.undo()  # deshace el fasten → B vuelve a flotar
    assert _report(doc)["floating"] == [b]


# ----------------------------------------------------------- auto-detección
def test_autodetect_floor_and_contact():
    doc = Document("t")
    floor = _box(doc, "piso", 50)     # base en z=0
    stack = _box(doc, "encima", 150)  # base en z=100, toca la de arriba de 'piso'
    air = _box(doc, "aire", 600)      # base en z=550, sin contacto
    det = detect_connections(doc.scene)
    grounded_ids = {g["feature"] for g in det["grounds"]}
    assert floor in grounded_ids
    assert air not in grounded_ids
    pairs = {frozenset((c["a"], c["b"])) for c in det["fasteners"]}
    assert frozenset((floor, stack)) in pairs
    assert frozenset((floor, air)) not in pairs


def test_soundness_with_autodetect_overlay():
    doc = Document("t")
    floor = _box(doc, "piso", 50)
    stack = _box(doc, "encima", 150)
    air = _box(doc, "aire", 600)
    # sin declarar nada, con la geometría: piso y apilado quedan sujetos, el del aire no
    det = detect_connections(doc.scene)
    extra_edges = [(c["a"], c["b"], "contacto", "") for c in det["fasteners"]]
    extra_grounds = {g["feature"] for g in det["grounds"]}
    rep = _report(doc, extra_edges=extra_edges, extra_grounds=extra_grounds)
    assert rep["floating"] == [air]
