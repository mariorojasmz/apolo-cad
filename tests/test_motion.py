"""Motion study (V3 bloque #6): interpolación de fotogramas, persistencia y
escaneo de colisiones a lo largo del recorrido."""
import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document, DocumentError
from apolo.robotics.motion import duration, scan_collisions, values_at


def _arm_into_obstacle():
    """base + brazo (junta prismática en X) y un obstáculo estático en x=150.
    A valor bajo no colisiona; a valor alto el brazo entra en el obstáculo."""
    d = Document()
    base = d.execute("create_box", {"name": "base", "width": 100, "depth": 100, "height": 100})
    arm = d.execute("create_box", {"name": "brazo", "width": 60, "depth": 60, "height": 60})
    d.execute("create_box", {"name": "obst", "width": 60, "depth": 60, "height": 60, "position": {"x": 150}})
    d.execute("add_joint", {
        "name": "desliza", "type": "prismatica", "parent": base, "child": arm,
        "axis": {"x": 1}, "lower": 0, "upper": 200,
    })
    return d


# ------------------------------------------------------------- interpolación
def test_values_at_interpolation():
    kf = [{"t": 0, "values": {"j": 0}}, {"t": 2, "values": {"j": 90}}]
    assert values_at(kf, 1)["j"] == pytest.approx(45)
    assert values_at(kf, 0)["j"] == 0
    assert values_at(kf, -5)["j"] == 0      # antes del primero → constante
    assert values_at(kf, 9)["j"] == 90      # después del último → constante
    assert duration(kf) == 2
    assert values_at([], 1) == {}


# --------------------------------------------------------------- persistencia
def test_set_motion_sorts_and_roundtrips():
    d = _arm_into_obstacle()
    d.set_motion([{"t": 2, "values": {"desliza": 100}}, {"t": 0, "values": {"desliza": 0}}])
    assert [k["t"] for k in d.motion] == [0, 2]  # ordenado
    d2 = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert d2.motion == d.motion


def test_set_motion_validation():
    d = Document()
    with pytest.raises(DocumentError):
        d.set_motion([{"values": {"j": 0}}])           # falta t
    with pytest.raises(DocumentError):
        d.set_motion([{"t": -1, "values": {}}])         # t negativo


# ------------------------------------------------------------------- scan
def test_scan_detects_collision_along_travel():
    d = _arm_into_obstacle()
    d.set_motion([{"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 170}}])
    cols = scan_collisions(d, d.motion, steps=10)
    assert len(cols) > 0                                # el brazo entra en el obstáculo a media carrera
    assert all("interferencias" in c and c["interferencias"] for c in cols)


def test_scan_no_collision_when_clear():
    d = _arm_into_obstacle()
    d.set_motion([{"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 40}}])
    assert scan_collisions(d, d.motion, steps=10) == []  # nunca llega al obstáculo


def test_scan_empty_without_keyframes():
    d = _arm_into_obstacle()
    assert scan_collisions(d, [], steps=10) == []


# ----------------------------------------------------------------- API HTTP
def test_api_motion_crud():
    api.DOC = _arm_into_obstacle()
    client = TestClient(api.app)
    assert client.get("/api/motion").json() == {"keyframes": [], "duration": 0}
    r = client.put("/api/motion", json={"keyframes": [
        {"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 170}}]})
    assert r.status_code == 200 and r.json()["duration"] == 1
    got = client.get("/api/motion").json()
    assert len(got["keyframes"]) == 2
    scan = client.post("/api/motion/scan", json={"steps": 10}).json()
    assert len(scan["colisiones"]) > 0
    # validación
    assert client.put("/api/motion", json={"keyframes": [{"values": {}}]}).status_code == 400
