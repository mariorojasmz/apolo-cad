"""V6.6 «croquis vivo»: entidades SPLINE y ELIPSE en el croquis restringido + arrastre
de un punto (endpoint read-only). Los tests corren en los DOS motores (planegcs y scipy),
como exige la fachada de V5.1."""
import math
import os

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.kernel.sketch_geom import sketch_to_face
from apolo.kernel.sketch_solver import SketchError


@pytest.fixture(params=["planegcs", "scipy"])
def motor(request, monkeypatch):
    """Parametriza el MOTOR del solver (la fachada lo elige por env)."""
    if request.param == "planegcs":
        from apolo.kernel import sketch_gcs
        if not sketch_gcs.is_available():
            pytest.skip("planegcs no instalado")
    monkeypatch.setenv("APOLO_SKETCH_SOLVER", request.param)
    return request.param


def _elipse(rx=50.0, ry=30.0, rot=0.0):
    return {"points": {"c": [0.0, 0.0]},
            "entities": [{"id": "e1", "type": "ellipse", "center": "c",
                          "rx": rx, "ry": ry, "rotation": rot}],
            "constraints": []}


def _spline_cerrada():
    pts = {f"p{i}": [x, y] for i, (x, y) in
           enumerate([(0, 0), (60, 10), (80, 50), (30, 70), (-10, 40)])}
    return {"points": pts,
            "entities": [{"id": "s1", "type": "spline", "points": list(pts), "closed": True}],
            "constraints": []}


# ------------------------------------------------------------------ B: entidades nuevas
def test_ellipse_area_is_exact(motor):
    """El área de la elipse cuadra ANALÍTICAMENTE con π·rx·ry."""
    face, solved = sketch_to_face(_elipse())
    assert solved["ok"]
    assert face.area == pytest.approx(math.pi * 50 * 30, rel=1e-3)


def test_ellipse_rotation_swaps_the_bbox(motor):
    """Rotada 90° el bbox intercambia ejes (el rotation llega a la geometría)."""
    f0, _ = sketch_to_face(_elipse(rot=0.0))
    f90, _ = sketch_to_face(_elipse(rot=90.0))
    b0, b90 = f0.bounding_box(), f90.bounding_box()
    assert (b0.max.X - b0.min.X) == pytest.approx(100, rel=1e-2)
    assert (b90.max.X - b90.min.X) == pytest.approx(60, rel=1e-2)
    assert f0.area == pytest.approx(f90.area, rel=1e-3)      # el área no cambia


def test_closed_spline_is_a_profile(motor):
    face, solved = sketch_to_face(_spline_cerrada())
    assert solved["ok"] and face.area > 1000        # perfil real, no degenerado


def test_spline_control_points_are_solver_points(motor):
    """Los puntos de control son PUNTOS del croquis: una restricción los mueve y la
    spline los sigue (por eso se pueden restringir y arrastrar gratis)."""
    sk = _spline_cerrada()
    sk["constraints"] = [{"type": "distance", "a": "p0", "b": "p2", "value": 200.0}]
    face, solved = sketch_to_face(sk)
    assert solved["ok"]
    p0, p2 = solved["points"]["p0"], solved["points"]["p2"]
    assert math.dist(p0, p2) == pytest.approx(200.0, abs=0.01)


def test_ellipse_as_hole_in_a_rectangle(motor):
    """Elipse dentro de un contorno = AGUJERO (misma regla que el círculo)."""
    sk = {
        "points": {"a": [0, 0], "b": [200, 0], "c2": [200, 120], "d": [0, 120], "e": [100, 60]},
        "entities": [
            {"id": "l1", "type": "line", "from": "a", "to": "b"},
            {"id": "l2", "type": "line", "from": "b", "to": "c2"},
            {"id": "l3", "type": "line", "from": "c2", "to": "d"},
            {"id": "l4", "type": "line", "from": "d", "to": "a"},
            {"id": "el", "type": "ellipse", "center": "e", "rx": 40, "ry": 20},
        ],
        "constraints": [],
    }
    face, _ = sketch_to_face(sk)
    assert face.area == pytest.approx(200 * 120 - math.pi * 40 * 20, rel=1e-3)


def test_spline_needs_three_points(motor):
    sk = {"points": {"p0": [0, 0], "p1": [10, 10]},
          "entities": [{"id": "s", "type": "spline", "points": ["p0", "p1"], "closed": True}],
          "constraints": []}
    with pytest.raises(SketchError, match="al menos 3"):
        sketch_to_face(sk)


# ------------------------------------------------------------------- A: arrastre
def _cuadrado_con_lados_fijos():
    """Cuadrado 100×100 con las 4 longitudes fijas (queda libre de girar/moverse)."""
    return {
        "points": {"a": [0, 0], "b": [100, 0], "c": [100, 100], "d": [0, 100]},
        "entities": [
            {"id": "l1", "type": "line", "from": "a", "to": "b"},
            {"id": "l2", "type": "line", "from": "b", "to": "c"},
            {"id": "l3", "type": "line", "from": "c", "to": "d"},
            {"id": "l4", "type": "line", "from": "d", "to": "a"},
        ],
        "constraints": [{"type": "length", "entity": f"l{i}", "value": 100.0} for i in (1, 2, 3, 4)],
    }


def test_drag_moves_the_point_and_keeps_hard_constraints(motor):
    api.DOC = Document("t")
    client = TestClient(api.app)
    r = client.post("/api/sketch/drag", json={
        "sketch": _cuadrado_con_lados_fijos(), "point_id": "c", "target_xy": [140.0, 130.0]})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"]                                   # las DURAS se siguen cumpliendo
    pts = d["points"]
    assert math.dist(pts["b"], pts["c"]) == pytest.approx(100.0, abs=0.05)
    assert math.dist(pts["c"], pts["d"]) == pytest.approx(100.0, abs=0.05)
    assert math.dist(pts["c"], [140.0, 130.0]) < math.dist([100.0, 100.0], [140.0, 130.0])


def test_drag_is_read_only_and_reports_the_gap(motor):
    """El endpoint NO persiste y DECLARA cuánto tuvo que separarse del cursor."""
    api.DOC = Document("t")
    sk = _cuadrado_con_lados_fijos()
    r = TestClient(api.app).post("/api/sketch/drag", json={
        "sketch": sk, "point_id": "c", "target_xy": [140.0, 130.0]})
    d = r.json()
    assert "movido_mm" in d and isinstance(d["sigue_al_cursor"], bool)
    assert sk["points"]["c"] == [100, 100]           # el croquis de entrada, intacto
    assert api.DOC.commands == []                    # nada se persistió


def test_drag_unknown_point_404(motor):
    api.DOC = Document("t")
    r = TestClient(api.app).post("/api/sketch/drag", json={
        "sketch": _cuadrado_con_lados_fijos(), "point_id": "zz", "target_xy": [1.0, 2.0]})
    assert r.status_code == 404 and "zz" in r.json()["detail"]
