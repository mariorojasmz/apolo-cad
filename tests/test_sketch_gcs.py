"""Solver de croquis V5.1: motor PlaneGCS + fallback scipy (fachada de dos motores).

test_sketcher.py queda INTACTO como contrato de compatibilidad (corre con el motor
por defecto). Aquí: paridad de ambos motores en los tipos clásicos, los 6 tipos
nuevos (solo GCS), DOF/redundantes/conflictivas, y el croquis grande que motivó el
cambio de solver."""

from __future__ import annotations

import math

import pytest

from apolo.kernel import sketch_gcs
from apolo.kernel.sketch_geom import sketch_to_face
from apolo.kernel.sketch_solver import SketchError, solve_sketch

gcs_available = sketch_gcs.is_available()
requires_gcs = pytest.mark.skipif(not gcs_available, reason="planegcs no instalado")


@pytest.fixture(params=["planegcs", "scipy"])
def engine(request, monkeypatch):
    if request.param == "planegcs" and not gcs_available:
        pytest.skip("planegcs no instalado")
    monkeypatch.setenv("APOLO_SKETCH_SOLVER", request.param)
    return request.param


@pytest.fixture()
def gcs(monkeypatch):
    if not gcs_available:
        pytest.skip("planegcs no instalado")
    monkeypatch.setenv("APOLO_SKETCH_SOLVER", "planegcs")


def _rect(l1=100.0, l2=50.0, extra=None):
    sk = {
        "points": {"a": [2, -1], "b": [97, 3], "c": [103, 52], "d": [-4, 47]},
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
            {"type": "length", "entity": "l1", "value": l1},
            {"type": "length", "entity": "l2", "value": l2},
        ],
    }
    sk["constraints"].extend(extra or [])
    return sk


# ------------------------------------------------------- paridad de ambos motores
def test_rectangle_both_engines(engine):
    s = solve_sketch(_rect())
    assert s["ok"] and s["residual"] < 1e-4
    a, b, c = s["points"]["a"], s["points"]["b"], s["points"]["c"]
    assert math.hypot(b[0] - a[0], b[1] - a[1]) == pytest.approx(100, abs=1e-3)
    assert math.hypot(c[0] - b[0], c[1] - b[1]) == pytest.approx(50, abs=1e-3)
    # subrestringido cerca del boceto: 'a' se queda fijada donde estaba
    assert s["points"]["a"] == pytest.approx([2, -1], abs=1e-6)
    # claves nuevas presentes en ambos motores
    assert "dof" in s and "redundantes" in s and "conflictivas" in s


def test_angle_both_engines(engine):
    sk = {
        "points": {"a": [0, 0], "b": [100, 5], "c": [0, 30], "d": [95, 40]},
        "entities": [
            {"type": "line", "id": "l1", "from": "a", "to": "b"},
            {"type": "line", "id": "l2", "from": "c", "to": "d"},
        ],
        "constraints": [
            {"type": "fix", "point": "a"},
            {"type": "horizontal", "entity": "l1"},
            {"type": "angle", "a": "l1", "b": "l2", "value": 45},
        ],
    }
    s = solve_sketch(sk)
    assert s["ok"]
    c, d = s["points"]["c"], s["points"]["d"]
    ang = math.degrees(math.atan2(d[1] - c[1], d[0] - c[0]))
    assert ang == pytest.approx(45, abs=0.05)


def test_impossible_diagnoses_both_engines(engine):
    s = solve_sketch(_rect(extra=[{"type": "length", "entity": "l3", "value": 70}]))
    assert not s["ok"] and len(s["diagnostico"]) > 0


def test_validation_errors_both_engines(engine):
    with pytest.raises(SketchError, match="puntos"):
        solve_sketch({"points": {}, "entities": [], "constraints": []})
    with pytest.raises(SketchError, match="desconocido"):
        solve_sketch({"points": {"a": [0, 0]}, "entities": [], "constraints": [{"type": "magia"}]})


# --------------------------------------------------------------- diagnóstico GCS
def test_dof_reporting(gcs):
    assert solve_sketch(_rect())["dof"] == 0
    sk = _rect()
    sk["constraints"] = [c for c in sk["constraints"] if c.get("value") != 50.0]
    assert solve_sketch(sk)["dof"] == 1
    sk2 = _rect()
    sk2["constraints"] = [c for c in sk2["constraints"] if c["type"] != "fix"]
    assert solve_sketch(sk2)["dof"] == 2  # traslación libre (la rotación la matan H/V)


def test_redundant_detected(gcs):
    # l3=100 no aporta: lo implican l1=100 + H/V — resuelve OK y se reporta
    s = solve_sketch(_rect(extra=[{"type": "length", "entity": "l3", "value": 100}]))
    assert s["ok"]
    assert s["redundantes"] and any("l3" in r for r in s["redundantes"])
    assert s["conflictivas"] == []


def test_conflicting_detected(gcs):
    s = solve_sketch(_rect(extra=[{"type": "length", "entity": "l3", "value": 70}]))
    assert not s["ok"]
    assert s["conflictivas"]  # el solver identifica el subconjunto en conflicto
    assert s["diagnostico"]  # y sketch_geom sigue teniendo texto para su error


# ------------------------------------------------------------- tipos nuevos (GCS)
def _slot(ccw_right=True):
    """Coliso: 2 líneas + 2 arcos tapa, centros fijos a 60 mm, r=10."""
    return {
        "points": {
            "ts": [-30.5, 9], "te": [29, 10.5], "bs": [30.2, -9.5], "be": [-29, -10],
            "cl": [-30, 0], "cr": [30, 0],
        },
        "entities": [
            {"type": "line", "id": "l_top", "from": "ts", "to": "te"},
            {"type": "line", "id": "l_bot", "from": "bs", "to": "be"},
            # tapa derecha: de bs(-90°) a te(+90°) ccw pasa por 0° (o cw invertida)
            ({"type": "arc", "id": "a_r", "center": "cr", "from": "bs", "to": "te", "ccw": True}
             if ccw_right else
             {"type": "arc", "id": "a_r", "center": "cr", "from": "te", "to": "bs", "ccw": False}),
            {"type": "arc", "id": "a_l", "center": "cl", "from": "ts", "to": "be", "ccw": True},
        ],
        "constraints": [
            {"type": "fix", "point": "cl"},
            {"type": "fix", "point": "cr"},
            {"type": "horizontal", "entity": "l_top"},
            {"type": "horizontal", "entity": "l_bot"},
            {"type": "tangent", "a": "l_top", "b": "a_r"},
            {"type": "tangent", "a": "l_top", "b": "a_l"},
            {"type": "tangent", "a": "l_bot", "b": "a_r"},
            {"type": "tangent", "a": "l_bot", "b": "a_l"},
            {"type": "equal_radius", "a": "a_l", "b": "a_r"},
            {"type": "radius", "entity": "a_r", "value": 10},
        ],
    }


def test_slot_tangent_solves_and_face_area(gcs):
    s = solve_sketch(_slot())
    assert s["ok"], s["diagnostico"]
    ts, te = s["points"]["ts"], s["points"]["te"]
    assert ts[1] == pytest.approx(10, abs=1e-4) and te[1] == pytest.approx(10, abs=1e-4)
    # cara del lazo línea-arco-línea-arco: área = 60·20 + π·10²
    face, _ = sketch_to_face(_slot())
    assert face.area == pytest.approx(60 * 20 + math.pi * 100, rel=1e-4)


def test_slot_with_cw_arc(gcs):
    # el mismo coliso con la tapa derecha declarada CW (from/to invertidos)
    s = solve_sketch(_slot(ccw_right=False))
    assert s["ok"], s["diagnostico"]
    face, _ = sketch_to_face(_slot(ccw_right=False))
    assert face.area == pytest.approx(60 * 20 + math.pi * 100, rel=1e-4)


def test_tangent_arc_arc(gcs):
    # dos arcos tapa tangentes entre sí (S invertida): centros a r1+r2
    sk = {
        "points": {"c1": [0, 0], "c2": [31, 0], "p1": [0, 10.5], "m": [9, 3], "p2": [31, -20.5]},
        "entities": [
            {"type": "arc", "id": "a1", "center": "c1", "from": "p1", "to": "m", "ccw": False},
            {"type": "arc", "id": "a2", "center": "c2", "from": "m", "to": "p2", "ccw": True},
        ],
        "constraints": [
            {"type": "fix", "point": "c1"},
            {"type": "fix", "point": "c2"},
            {"type": "radius", "entity": "a1", "value": 10},
            {"type": "radius", "entity": "a2", "value": 21},
            {"type": "coincident", "a": "m", "b": "m"},  # no-op estructural
            {"type": "tangent", "a": "a1", "b": "a2"},
        ],
    }
    del sk["constraints"][4]  # quitar el no-op
    s = solve_sketch(sk)
    assert s["ok"], s["diagnostico"]
    c1, c2 = s["points"]["c1"], s["points"]["c2"]
    d = math.hypot(c2[0] - c1[0], c2[1] - c1[1])
    # tangencia interna (|r1-r2|=11) o externa (r1+r2=31): con centros fijos a 31 → externa
    assert d == pytest.approx(31, abs=1e-6)


def test_symmetric(gcs):
    sk = {
        "points": {"a": [0, 0], "b": [0, 100], "p": [30, 48], "q": [-28, 52]},
        "entities": [{"type": "line", "id": "eje", "from": "a", "to": "b"}],
        "constraints": [
            {"type": "fix", "point": "a"},
            {"type": "fix", "point": "b"},
            {"type": "fix", "point": "p"},
            {"type": "symmetric", "a": "p", "b": "q", "line": "eje"},
        ],
    }
    s = solve_sketch(sk)
    assert s["ok"], s["diagnostico"]
    assert s["points"]["q"] == pytest.approx([-30, 48], abs=1e-4)


def test_concentric_and_equal_radius_circles(gcs):
    sk = {
        "points": {"c1": [0, 0], "c2": [3, 2]},
        "entities": [
            {"type": "circle", "id": "k1", "center": "c1", "radius": 20},
            {"type": "circle", "id": "k2", "center": "c2", "radius": 12},
        ],
        "constraints": [
            {"type": "fix", "point": "c1"},
            {"type": "radius", "entity": "k1", "value": 20},
            {"type": "concentric", "a": "k1", "b": "k2"},
            {"type": "equal_radius", "a": "k1", "b": "k2"},
        ],
    }
    s = solve_sketch(sk)
    assert s["ok"], s["diagnostico"]
    assert s["points"]["c2"] == pytest.approx([0, 0], abs=1e-6)
    assert s["radii"]["k2"] == pytest.approx(20, abs=1e-6)


def test_midpoint_and_distance_point_line(gcs):
    sk = {
        "points": {"a": [0, 0], "b": [100, 0], "m": [40, 8], "p": [50, 20]},
        "entities": [{"type": "line", "id": "l1", "from": "a", "to": "b"}],
        "constraints": [
            {"type": "fix", "point": "a"},
            {"type": "fix", "point": "b"},
            {"type": "midpoint", "point": "m", "entity": "l1"},
            {"type": "distance_point_line", "point": "p", "entity": "l1", "value": 25},
        ],
    }
    s = solve_sketch(sk)
    assert s["ok"], s["diagnostico"]
    assert s["points"]["m"] == pytest.approx([50, 0], abs=1e-4)
    assert abs(s["points"]["p"][1]) == pytest.approx(25, abs=1e-4)


def test_arc_radius_constraint_gcs_only_capability(gcs):
    # 'radius' sobre un ARCO: capacidad nueva del motor GCS (scipy lo rechaza)
    sk = {
        "points": {"c": [0, 0], "f": [9, 0.5], "t": [-0.5, 9.5]},
        "entities": [{"type": "arc", "id": "a1", "center": "c", "from": "f", "to": "t", "ccw": True}],
        "constraints": [
            {"type": "fix", "point": "c"},
            {"type": "radius", "entity": "a1", "value": 15},
        ],
    }
    s = solve_sketch(sk)
    assert s["ok"], s["diagnostico"]
    f = s["points"]["f"]
    assert math.hypot(f[0], f[1]) == pytest.approx(15, abs=1e-4)


# --------------------------------------------------------- robustez / fallback
def _zigzag(n=24):
    """Cadena de n puntos con ángulos alternos: el caso que motivó PlaneGCS."""
    import random

    rng = random.Random(7)
    points = {f"p{i}": [i * 10 + rng.uniform(-3, 3), rng.uniform(-4, 4)] for i in range(n)}
    entities = [
        {"type": "line", "id": f"l{i}", "from": f"p{i}", "to": f"p{i + 1}"}
        for i in range(n - 1)
    ]
    cons = [
        {"type": "fix", "point": "p0"},
        {"type": "horizontal", "entity": "l0"},
        {"type": "length", "entity": "l0", "value": 10},
    ]
    for i in range(n - 2):
        cons.append({"type": "angle", "a": f"l{i}", "b": f"l{i + 1}",
                     "value": 15 if i % 2 == 0 else -15})
        cons.append({"type": "equal_length", "a": f"l{i}", "b": f"l{i + 1}"})
    return {"points": points, "entities": entities, "constraints": cons}


def test_large_zigzag_converges_fully_constrained(gcs):
    s = solve_sketch(_zigzag())
    assert s["ok"], s["diagnostico"]
    assert s["dof"] == 0


def test_new_type_with_scipy_engine_fails_clearly(monkeypatch):
    monkeypatch.setenv("APOLO_SKETCH_SOLVER", "scipy")
    sk = _slot()
    with pytest.raises(SketchError, match="PlaneGCS"):
        solve_sketch(sk)


# --------------------------------------------------------------- exposición API
from fastapi.testclient import TestClient  # noqa: E402

import apolo.api.main as api  # noqa: E402
from apolo.doc.document import Document  # noqa: E402


def test_endpoint_returns_new_keys(gcs):
    api.DOC = Document("t")
    client = TestClient(api.app)
    r = client.post("/api/sketch/solve", json={"sketch": _rect()})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] and data["dof"] == 0
    assert data["redundantes"] == [] and data["conflictivas"] == []


def test_sketch_extrude_slot_command(gcs):
    doc = Document("t")
    fid = doc.execute("sketch_extrude", {"name": "Placa coliso", "sketch": _slot(), "height": 12})
    vol = doc.scene[fid].shape.volume
    assert vol == pytest.approx((60 * 20 + math.pi * 100) * 12, rel=1e-4)
