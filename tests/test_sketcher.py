import math

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document, DocumentError
from apolo.kernel.sketch_geom import SketchError, sketch_to_face
from apolo.kernel.sketch_solver import solve_sketch


def _rect_sketch(rough=True):
    pts = (
        {"a": [2, -1], "b": [97, 3], "c": [103, 52], "d": [-4, 47]}
        if rough
        else {"a": [0, 0], "b": [100, 0], "c": [100, 50], "d": [0, 50]}
    )
    return {
        "points": pts,
        "entities": [
            {"type": "line", "id": "l1", "from": "a", "to": "b"},
            {"type": "line", "id": "l2", "from": "b", "to": "c"},
            {"type": "line", "id": "l3", "from": "c", "to": "d"},
            {"type": "line", "id": "l4", "from": "d", "to": "a"},
        ],
        "constraints": [
            {"type": "fix", "point": "a"},
            {"type": "horizontal", "entity": "l1"},
            {"type": "vertical", "entity": "l2"},
            {"type": "horizontal", "entity": "l3"},
            {"type": "vertical", "entity": "l4"},
            {"type": "length", "entity": "l1", "value": 100},
            {"type": "length", "entity": "l2", "value": 50},
        ],
    }


# -------------------------------------------------------------------- solver
def test_solver_makes_rough_rectangle_exact():
    s = solve_sketch(_rect_sketch())
    assert s["ok"] and s["residual"] < 1e-4
    a, b, c = s["points"]["a"], s["points"]["b"], s["points"]["c"]
    assert math.hypot(b[0] - a[0], b[1] - a[1]) == pytest.approx(100, abs=1e-3)
    assert math.hypot(c[0] - b[0], c[1] - b[1]) == pytest.approx(50, abs=1e-3)
    assert b[1] == pytest.approx(a[1], abs=1e-3)  # horizontal


def test_solver_angle_and_parallel():
    sketch = {
        "points": {"a": [0, 0], "b": [100, 5], "c": [0, 30], "d": [95, 40]},
        "entities": [
            {"type": "line", "id": "l1", "from": "a", "to": "b"},
            {"type": "line", "id": "l2", "from": "c", "to": "d"},
        ],
        "constraints": [
            {"type": "fix", "point": "a"},
            {"type": "horizontal", "entity": "l1"},
            {"type": "parallel", "a": "l1", "b": "l2"},
        ],
    }
    s = solve_sketch(sketch)
    assert s["ok"]
    c, d = s["points"]["c"], s["points"]["d"]
    assert d[1] == pytest.approx(c[1], abs=1e-3)  # paralela a horizontal

    sketch["constraints"][-1] = {"type": "angle", "a": "l1", "b": "l2", "value": 45}
    s = solve_sketch(sketch)
    c, d = s["points"]["c"], s["points"]["d"]
    ang = math.degrees(math.atan2(d[1] - c[1], d[0] - c[0]))
    assert ang == pytest.approx(45, abs=0.05)


def test_solver_impossible_diagnoses():
    bad = _rect_sketch()
    bad["constraints"].append({"type": "length", "entity": "l3", "value": 70})
    s = solve_sketch(bad)
    assert not s["ok"] and len(s["diagnostico"]) > 0


def test_solver_validation_errors():
    with pytest.raises(SketchError, match="puntos"):
        solve_sketch({"points": {}, "entities": [], "constraints": []})
    with pytest.raises(SketchError, match="inexistente"):
        solve_sketch({"points": {"a": [0, 0]}, "entities": [{"type": "line", "id": "l", "from": "a", "to": "z"}]})
    with pytest.raises(SketchError, match="desconocido"):
        solve_sketch({"points": {"a": [0, 0]}, "entities": [], "constraints": [{"type": "magia"}]})


# ------------------------------------------------------------------ geometría
def test_face_area_with_holes():
    sketch = _rect_sketch(rough=False)
    sketch["points"]["h"] = [50, 25]
    sketch["entities"].append({"type": "circle", "id": "c1", "center": "h", "radius": 10})
    face, _ = sketch_to_face(sketch)
    assert face.area == pytest.approx(100 * 50 - math.pi * 100, rel=1e-4)


def test_open_loop_rejected():
    sketch = _rect_sketch(rough=False)
    sketch["entities"] = sketch["entities"][:3]  # falta el cierre
    sketch["constraints"] = [
        c for c in sketch["constraints"] if c.get("entity") != "l4"
    ]
    with pytest.raises(SketchError, match="lazo|cierra"):
        sketch_to_face(sketch)


def test_arc_in_loop():
    # rectángulo con tapa en arco (semicírculo superior)
    sketch = {
        "points": {"a": [0, 0], "b": [60, 0], "c": [60, 30], "d": [0, 30], "m": [30, 30]},
        "entities": [
            {"type": "line", "id": "l1", "from": "a", "to": "b"},
            {"type": "line", "id": "l2", "from": "b", "to": "c"},
            {"type": "arc", "id": "a1", "center": "m", "from": "c", "to": "d", "ccw": True},
            {"type": "line", "id": "l4", "from": "d", "to": "a"},
        ],
        "constraints": [{"type": "fix", "point": "a"}, {"type": "fix", "point": "b"},
                         {"type": "fix", "point": "c"}, {"type": "fix", "point": "d"},
                         {"type": "fix", "point": "m"}],
    }
    face, _ = sketch_to_face(sketch)
    assert face.area == pytest.approx(60 * 30 + math.pi * 900 / 2, rel=1e-3)


# ------------------------------------------------------------------- comandos
def test_sketch_extrude_volume_and_parametric_edit():
    doc = Document()
    cid = doc.execute("sketch_extrude", {"sketch": _rect_sketch(), "height": 20})
    assert doc.scene[cid].shape.volume == pytest.approx(100 * 50 * 20, rel=1e-6)

    # edición paramétrica: cambiar una cota del croquis regenera
    params = doc.commands[0]["params"]
    params["sketch"]["constraints"][5]["value"] = 80  # length l1: 100 → 80
    doc.edit(cid, params)
    assert doc.scene[cid].shape.volume == pytest.approx(80 * 50 * 20, rel=1e-6)


def test_sketch_with_variable_dimension():
    doc = Document()
    doc.execute("set_variable", {"name": "ancho", "expression": "120"})
    sketch = _rect_sketch()
    sketch["constraints"][5]["value"] = "=ancho"
    cid = doc.execute("sketch_extrude", {"sketch": sketch, "height": 10})
    assert doc.scene[cid].shape.volume == pytest.approx(120 * 50 * 10, rel=1e-6)
    # cascada: cambiar la variable redimensiona el croquis
    var_cmd = next(c["id"] for c in doc.commands if c["type"] == "set_variable")
    doc.edit(var_cmd, {"name": "ancho", "expression": "200"})
    assert doc.scene[cid].shape.volume == pytest.approx(200 * 50 * 10, rel=1e-6)


def test_sketch_revolve():
    doc = Document()
    anillo = {
        "points": {"a": [20, 0], "b": [30, 0], "c": [30, 15], "d": [20, 15]},
        "entities": [
            {"type": "line", "id": "l1", "from": "a", "to": "b"},
            {"type": "line", "id": "l2", "from": "b", "to": "c"},
            {"type": "line", "id": "l3", "from": "c", "to": "d"},
            {"type": "line", "id": "l4", "from": "d", "to": "a"},
        ],
        "constraints": [{"type": "fix", "point": "a"}, {"type": "fix", "point": "b"},
                         {"type": "fix", "point": "c"}, {"type": "fix", "point": "d"}],
    }
    cid = doc.execute("sketch_revolve", {"sketch": anillo})
    assert doc.scene[cid].shape.volume == pytest.approx(math.pi * (30**2 - 20**2) * 15, rel=1e-4)


def test_sketch_revolve_negative_radius_rejected():
    doc = Document()
    sketch = _rect_sketch(rough=False)
    sketch["points"] = {k: [v[0] - 50, v[1]] for k, v in sketch["points"].items()}
    sketch["constraints"] = [{"type": "fix", "point": p} for p in sketch["points"]]
    with pytest.raises(DocumentError, match="radio|x="):
        doc.execute("sketch_revolve", {"sketch": sketch})


def test_unsatisfiable_sketch_command_rolls_back():
    doc = Document()
    bad = _rect_sketch()
    bad["constraints"].append({"type": "length", "entity": "l3", "value": 70})
    with pytest.raises(DocumentError, match="no satisface"):
        doc.execute("sketch_extrude", {"sketch": bad, "height": 10})
    assert doc.commands == []


# ------------------------------------------------------------------- API HTTP
def test_solve_endpoint():
    api.DOC = Document()
    client = TestClient(api.app)
    r = client.post("/api/sketch/solve", json={"sketch": _rect_sketch()})
    assert r.status_code == 200 and r.json()["ok"]
    r = client.post("/api/sketch/solve", json={"sketch": {"points": {}}})
    assert r.status_code == 400
