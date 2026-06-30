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
    d.set_motion("Carrera", [{"t": 2, "values": {"desliza": 100}}, {"t": 0, "values": {"desliza": 0}}])
    assert [k["t"] for k in d.motion["Carrera"]] == [0, 2]  # ordenado
    d2 = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert d2.motion == d.motion


def test_multiple_named_studies_coexist():
    d = _arm_into_obstacle()
    d.set_motion("A", [{"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 50}}])
    d.set_motion("B", [{"t": 0, "values": {"desliza": 50}}, {"t": 1, "values": {"desliza": 0}}])
    assert set(d.motion) == {"A", "B"}
    d.set_motion("A", [])           # lista vacía → borra el estudio
    assert set(d.motion) == {"B"}
    d.delete_motion("B")
    assert d.motion == {}


def test_migration_old_list_motion():
    # un manifest viejo guardaba el motion como UNA lista → migra a {"Estudio 1": [...]}
    import json, io, zipfile

    d = _arm_into_obstacle()
    raw = d.to_apolo_bytes()
    buf = io.BytesIO(raw)
    with zipfile.ZipFile(buf) as zf:
        manifest = json.loads(zf.read("manifest.json"))
        others = {n: zf.read(n) for n in zf.namelist() if n != "manifest.json"}
    manifest["motion"] = [{"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 50}}]
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        for n, b in others.items():
            zf.writestr(n, b)
    d2 = Document.from_apolo_bytes(out.getvalue())
    assert list(d2.motion) == ["Estudio 1"]
    assert [k["t"] for k in d2.motion["Estudio 1"]] == [0, 1]


def test_set_motion_validation():
    d = Document()
    with pytest.raises(DocumentError):
        d.set_motion("X", [{"values": {"j": 0}}])           # falta t
    with pytest.raises(DocumentError):
        d.set_motion("X", [{"t": -1, "values": {}}])         # t negativo
    with pytest.raises(DocumentError):
        d.set_motion("  ", [{"t": 0, "values": {}}])         # nombre vacío


# ------------------------------------------------------------------- scan
def test_scan_detects_collision_along_travel():
    d = _arm_into_obstacle()
    d.set_motion("R", [{"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 170}}])
    cols = scan_collisions(d, d.motion["R"], steps=10)
    assert len(cols) > 0                                # el brazo entra en el obstáculo a media carrera
    assert all("interferencias" in c and c["interferencias"] for c in cols)


def test_scan_no_collision_when_clear():
    d = _arm_into_obstacle()
    d.set_motion("R", [{"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 40}}])
    assert scan_collisions(d, d.motion["R"], steps=10) == []  # nunca llega al obstáculo


def test_scan_empty_without_keyframes():
    d = _arm_into_obstacle()
    assert scan_collisions(d, [], steps=10) == []


# ----------------------------------------------------------------- API HTTP
def test_api_motion_crud():
    api.DOC = _arm_into_obstacle()
    client = TestClient(api.app)
    assert client.get("/api/motion").json() == {"studies": []}
    r = client.put("/api/motion", json={"name": "Carrera", "keyframes": [
        {"t": 0, "values": {"desliza": 0}}, {"t": 1, "values": {"desliza": 170}}]})
    assert r.status_code == 200
    studies = r.json()["studies"]
    assert len(studies) == 1 and studies[0]["name"] == "Carrera" and studies[0]["duration"] == 1
    got = client.get("/api/motion").json()
    assert len(got["studies"][0]["keyframes"]) == 2
    scan = client.post("/api/motion/scan", json={"name": "Carrera", "steps": 10}).json()
    assert len(scan["colisiones"]) > 0
    # un segundo estudio coexiste
    client.put("/api/motion", json={"name": "Otra", "keyframes": [{"t": 0, "values": {"desliza": 0}}]})
    assert {s["name"] for s in client.get("/api/motion").json()["studies"]} == {"Carrera", "Otra"}
    # borrar por nombre
    client.request("DELETE", "/api/motion", json={"name": "Otra"})
    assert {s["name"] for s in client.get("/api/motion").json()["studies"]} == {"Carrera"}
    # validación
    assert client.put("/api/motion", json={"name": "X", "keyframes": [{"values": {}}]}).status_code == 400
