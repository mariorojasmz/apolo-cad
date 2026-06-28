"""Sweep (barrido) y loft (transición) desde perfiles de croquis (V3 bloque #4)."""
import math

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.commands.registry import CommandError
from apolo.doc import Document, DocumentError


def _circle(r=10):
    return {
        "points": {"c": [0, 0]},
        "entities": [{"type": "circle", "id": "k", "center": "c", "radius": r}],
        "constraints": [{"type": "fix", "point": "c"}, {"type": "radius", "entity": "k", "value": r}],
    }


def _square(side):
    h = side / 2
    pts = {"a": [-h, -h], "b": [h, -h], "c": [h, h], "d": [-h, h]}
    ents = [
        {"type": "line", "id": "l1", "from": "a", "to": "b"},
        {"type": "line", "id": "l2", "from": "b", "to": "c"},
        {"type": "line", "id": "l3", "from": "c", "to": "d"},
        {"type": "line", "id": "l4", "from": "d", "to": "a"},
    ]
    return {"points": pts, "entities": ents, "constraints": [{"type": "fix", "point": p} for p in pts]}


# ------------------------------------------------------------------- sweep
def test_sweep_straight_volume():
    d = Document()
    cid = d.execute("sketch_sweep", {"name": "tubo", "sketch": _circle(10), "path": [[0, 0, 0], [0, 0, 200]]})
    assert d.scene[cid].shape.volume == pytest.approx(math.pi * 100 * 200, rel=1e-3)


def test_sweep_corner_follows_all_segments():
    """El barrido sigue TODOS los tramos de la polilínea (no se trunca en la esquina)."""
    d = Document()
    cid = d.execute("sketch_sweep", {"sketch": _circle(10), "path": [[0, 0, 0], [0, 0, 150], [120, 0, 150]]})
    bb = d.scene[cid].shape.bounding_box()
    assert bb.max.X == pytest.approx(120, abs=1)   # llega al fin del 2º tramo (truncado daría ~10)
    assert bb.max.Z == pytest.approx(160, abs=1)   # 150 + radio del perfil en el codo


def test_sweep_smooth_builds():
    d = Document()
    cid = d.execute("sketch_sweep", {"sketch": _circle(8), "smooth": True,
                                     "path": [[0, 0, 0], [50, 0, 80], [0, 0, 160]]})
    assert d.scene[cid].shape.volume > 0


def test_sweep_parametric_path():
    d = Document()
    d.execute("set_variable", {"name": "L", "expression": "200"})
    cid = d.execute("sketch_sweep", {"sketch": _circle(10), "path": [[0, 0, 0], [0, 0, "=L"]]})
    assert d.scene[cid].shape.volume == pytest.approx(math.pi * 100 * 200, rel=1e-3)
    var = next(c["id"] for c in d.commands if c["type"] == "set_variable")
    d.edit(var, {"name": "L", "expression": "300"})
    assert d.scene[cid].shape.volume == pytest.approx(math.pi * 100 * 300, rel=1e-3)


def test_sweep_short_path_rejected():
    d = Document()
    with pytest.raises((CommandError, DocumentError)):
        d.execute("sketch_sweep", {"sketch": _circle(10), "path": [[0, 0, 0]]})
    assert d.commands == []


# --------------------------------------------------- G1: lazo cerrado + helix
_LOOP = [[-500, 0, 751], [500, 0, 751], [541, 0, 710], [500, 0, 669],
         [-500, 0, 669], [-541, 0, 710], [-500, 0, 751]]  # racetrack en X-Z (banda)


def test_sweep_closed_loop():
    """Trayectoria cerrada → banda en lazo, un solo sólido; is_frenet mantiene el
    ancho del perfil sin girar (bbox Y ≈ ancho del perfil, no del lazo)."""
    d = Document()
    cid = d.execute("sketch_sweep", {"name": "Banda", "sketch": _square(20), "path": _LOOP, "closed": True})
    bb = d.scene[cid].shape.bounding_box()
    assert d.scene[cid].shape.volume > 0
    assert bb.size.X == pytest.approx(1102, abs=40)   # abarca el lazo en X
    assert bb.size.Y == pytest.approx(20, abs=2)      # el ancho del perfil se queda en Y


def test_sweep_auto_closed_repeated_endpoint():
    """Sin flag, un path cuyo primer punto == último también cierra el lazo."""
    d = Document()
    cid = d.execute("sketch_sweep", {"sketch": _square(20), "path": _LOOP})  # _LOOP ya repite el extremo
    bb = d.scene[cid].shape.bounding_box()
    assert d.scene[cid].shape.volume > 0
    assert bb.size.Y == pytest.approx(20, abs=2)


def test_sweep_helix_spring():
    d = Document()
    cid = d.execute("sketch_sweep", {"name": "Resorte", "sketch": _circle(3),
                                     "helix": {"radius": 20, "pitch": 10, "turns": 5}})
    bb = d.scene[cid].shape.bounding_box()
    assert d.scene[cid].shape.volume > 0
    assert bb.size.Z == pytest.approx(50, abs=8)   # pitch · turns
    assert bb.size.X == pytest.approx(46, abs=2)   # 2 · (radius + r_perfil)


def test_sweep_helix_parametric():
    d = Document()
    d.execute("set_variable", {"name": "R", "expression": "25"})
    cid = d.execute("sketch_sweep", {"sketch": _circle(3), "helix": {"radius": "=R", "pitch": 8, "turns": 4}})
    assert d.scene[cid].shape.bounding_box().size.X == pytest.approx(56, abs=2)  # 2·(25+3)


def test_sweep_requires_path_or_helix():
    d = Document()
    with pytest.raises((CommandError, DocumentError)):
        d.execute("sketch_sweep", {"sketch": _circle(10)})
    assert d.commands == []


# -------------------------------------------------------------------- loft
def test_loft_frustum_volume():
    d = Document()
    cid = d.execute("sketch_loft", {
        "name": "tolva",
        "sections": [{"sketch": _square(100), "z": 0}, {"sketch": _square(40), "z": 80}],
        "ruled": True,
    })
    a1, a2 = 100 * 100, 40 * 40
    expected = 80 / 3 * (a1 + a2 + math.sqrt(a1 * a2))  # tronco de pirámide
    assert d.scene[cid].shape.volume == pytest.approx(expected, rel=1e-3)


def test_loft_rect_to_circle_builds():
    d = Document()
    cid = d.execute("sketch_loft", {
        "sections": [{"sketch": _square(80), "z": 0}, {"sketch": _circle(25), "z": 100}],
    })
    assert d.scene[cid].shape.volume > 0


def test_loft_parametric_z():
    d = Document()
    d.execute("set_variable", {"name": "h", "expression": "80"})
    cid = d.execute("sketch_loft", {
        "sections": [{"sketch": _square(100), "z": 0}, {"sketch": _square(40), "z": "=h"}], "ruled": True,
    })
    v80 = d.scene[cid].shape.volume
    var = next(c["id"] for c in d.commands if c["type"] == "set_variable")
    d.edit(var, {"name": "h", "expression": "160"})
    assert d.scene[cid].shape.volume == pytest.approx(2 * v80, rel=1e-3)  # doble altura = doble volumen


def test_loft_one_section_rejected():
    d = Document()
    with pytest.raises((CommandError, DocumentError)):
        d.execute("sketch_loft", {"sections": [{"sketch": _square(50), "z": 0}]})
    assert d.commands == []


# ----------------------------------------------------------------- API HTTP
def test_sweep_loft_api():
    api.DOC = Document("sl-test")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "sketch_sweep", "params": {
        "sketch": _circle(10), "path": [[0, 0, 0], [0, 0, 120]]}})
    assert r.status_code == 200
    feats = client.get("/api/scene").json()["features"]
    assert any(f["volume_mm3"] > 0 for f in feats)
    r2 = client.post("/api/commands", json={"type": "sketch_loft", "params": {
        "sections": [{"sketch": _square(80), "z": 0}, {"sketch": _square(30), "z": 60}]}})
    assert r2.status_code == 200
