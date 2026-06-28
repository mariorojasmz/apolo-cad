"""Restricción de riel (lazo cerrado): la junta dependiente se resuelve para que
el punto ancla permanezca sobre la recta del riel, para cualquier valor del
driver. Mínima biela-manivela planar de dos eslabones iguales."""

import pytest

from apolo.assembly.constraints import (
    _anchor_world,
    _dist_to_line,
    _residual,
    solve_constraints,
)
from apolo.doc.document import Document, DocumentError


def _build():
    doc = Document("t")
    base = doc.execute("create_box", {"name": "base", "width": 50, "depth": 50, "height": 50})
    l1 = doc.execute(
        "create_box", {"name": "l1", "width": 400, "depth": 20, "height": 20, "position": {"x": 200}}
    )
    l2 = doc.execute(
        "create_box", {"name": "l2", "width": 400, "depth": 20, "height": 20, "position": {"x": 600}}
    )
    doc.execute("add_joint", {
        "name": "J1", "type": "giratoria", "parent": base, "child": l1,
        "origin": {"x": 0}, "axis": {"z": 1}, "lower": -170, "upper": 170,
    })
    doc.execute("add_joint", {
        "name": "J2", "type": "giratoria", "parent": l1, "child": l2,
        "origin": {"x": 400}, "axis": {"z": 1}, "lower": -170, "upper": 170,
    })
    doc.execute("add_rail_constraint", {
        "name": "rail", "joint": "J2",
        "anchor": {"x": 800, "y": 0, "z": 0}, "point": {"x": 0}, "axis": {"x": 1},
    })
    return doc, l2


def test_constraint_registered():
    doc, _ = _build()
    assert "rail" in doc.constraints
    assert doc.constraints["rail"]["joint"] == "J2"


def test_rail_keeps_anchor_on_line():
    doc, l2 = _build()
    for th1 in (5, 20, 40, 60, 75):
        vals = solve_constraints(doc.joints, doc.constraints, {"J1": th1})
        p = _anchor_world(doc.joints, vals, l2, [800, 0, 0])
        d = _dist_to_line(p, [0, 0, 0], [1, 0, 0])
        assert d < 1.0, f"th1={th1}: ancla a {d:.2f} mm del riel (J2={vals['J2']:.1f})"


def test_solve_is_identity_without_constraints():
    doc, _ = _build()
    free = {"J1": 30.0}
    assert solve_constraints(doc.joints, {}, free) == {"J1": 30.0}


def test_constraint_to_missing_joint_fails():
    doc = Document("t")
    with pytest.raises(DocumentError):
        doc.execute("add_rail_constraint", {
            "name": "rail", "joint": "NoExiste",
            "anchor": {"x": 1}, "point": {"x": 0}, "axis": {"x": 1},
        })


# --- Fase 5: multi-restricción / N-GDL (comando genérico add_constraint) ---

def test_add_constraint_rail_equivalent():
    """add_constraint tipo punto_en_recta == add_rail_constraint (1-GDL): el ancla sigue
    el riel para cualquier driver."""
    doc = Document("t")
    base = doc.execute("create_box", {"name": "base", "width": 50, "depth": 50, "height": 50})
    l1 = doc.execute("create_box", {"name": "l1", "width": 400, "depth": 20, "height": 20, "position": {"x": 200}})
    l2 = doc.execute("create_box", {"name": "l2", "width": 400, "depth": 20, "height": 20, "position": {"x": 600}})
    doc.execute("add_joint", {"name": "J1", "type": "giratoria", "parent": base, "child": l1, "origin": {"x": 0}, "axis": {"z": 1}, "lower": -170, "upper": 170})
    doc.execute("add_joint", {"name": "J2", "type": "giratoria", "parent": l1, "child": l2, "origin": {"x": 400}, "axis": {"z": 1}, "lower": -170, "upper": 170})
    doc.execute("add_constraint", {"name": "rail", "tipo": "punto_en_recta", "joint": "J2", "anchor": {"x": 800}, "point": {"x": 0}, "axis": {"x": 1}})
    for th1 in (10, 30, 50, 75):
        vals = solve_constraints(doc.joints, doc.constraints, {"J1": th1})
        p = _anchor_world(doc.joints, vals, l2, [800, 0, 0])
        assert _dist_to_line(p, [0, 0, 0], [1, 0, 0]) < 1.0


def _two_dof():
    doc = Document("t")
    base = doc.execute("create_box", {"name": "base", "width": 50, "depth": 50, "height": 50})
    a = doc.execute("create_box", {"name": "a", "width": 200, "depth": 20, "height": 20, "position": {"x": 100}})
    b = doc.execute("create_box", {"name": "b", "width": 200, "depth": 20, "height": 20, "position": {"x": 100}})
    doc.execute("add_joint", {"name": "JA", "type": "giratoria", "parent": base, "child": a, "origin": {"x": 0}, "axis": {"z": 1}, "lower": -180, "upper": 180})
    doc.execute("add_joint", {"name": "JB", "type": "giratoria", "parent": base, "child": b, "origin": {"x": 0}, "axis": {"z": 1}, "lower": -180, "upper": 180})
    # objetivos a 90° (config NO degenerada: a 180° exactos el gradiente es cero y el solver
    # no arranca — limitación numérica que la puerta evita con continuación).
    doc.execute("add_constraint", {"name": "CA", "tipo": "punto_coincidente", "joint": "JA", "anchor": {"x": 100}, "point": {"y": 100}})
    doc.execute("add_constraint", {"name": "CB", "tipo": "punto_coincidente", "joint": "JB", "anchor": {"x": 100}, "point": {"y": -100}})
    return doc


def test_add_constraint_multi_dof_solves_simultaneously():
    """Dos juntas dependientes con una restricción cada una se resuelven A LA VEZ (N-GDL):
    ambos residuos → 0 y cada junta alcanza su ángulo (±90°)."""
    doc = _two_dof()
    vals = solve_constraints(doc.joints, doc.constraints, {})
    for con in doc.constraints.values():
        assert _residual(doc.joints, vals, con) < 1.0
    assert abs(vals["JA"]) == pytest.approx(90, abs=2)
    assert abs(vals["JB"]) == pytest.approx(90, abs=2)


def test_add_constraint_distance_type():
    """Tipo `distancia`: el ancla acaba a `value` mm del punto de referencia."""
    doc = Document("t")
    base = doc.execute("create_box", {"name": "base", "width": 50, "depth": 50, "height": 50})
    a = doc.execute("create_box", {"name": "a", "width": 200, "depth": 20, "height": 20, "position": {"x": 100}})
    doc.execute("add_joint", {"name": "JA", "type": "giratoria", "parent": base, "child": a, "origin": {"x": 0}, "axis": {"z": 1}, "lower": -180, "upper": 180})
    doc.execute("add_constraint", {"name": "d", "tipo": "distancia", "joint": "JA", "anchor": {"x": 100}, "point": {"x": 100, "y": 100}, "value": 100})
    vals = solve_constraints(doc.joints, doc.constraints, {})
    assert _residual(doc.joints, vals, doc.constraints["d"]) < 1.0
