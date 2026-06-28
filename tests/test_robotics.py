import io
import math
import zipfile
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document, DocumentError
from apolo.robotics import export_sdf_zip, export_urdf_zip, joints_payload
from apolo.robotics.urdf import build_urdf


@pytest.fixture()
def arm_doc():
    doc = Document("robot-test")
    doc.execute("create_robot_arm", {"name": "R1", "alcance": 600})
    return doc


def test_robot_arm_creates_links_and_chained_joints(arm_doc):
    assert len(arm_doc.scene) == 5
    assert len(arm_doc.joints) == 4
    joints = list(arm_doc.joints.values())
    # cadena: el hijo de cada junta es el padre de la siguiente
    for prev, nxt in zip(joints, joints[1:]):
        assert prev["child"] == nxt["parent"]
    payload = joints_payload(arm_doc)
    assert payload["roots"] == ["c1_base"]
    assert payload["errors"] == []


def test_add_joint_validations():
    doc = Document()
    a = doc.execute("create_box", {})
    b = doc.execute("create_cylinder", {"position": {"x": 200}})
    doc.execute("add_joint", {"name": "j1", "parent": a, "child": b, "origin": {"x": 100}})
    # hijo duplicado
    with pytest.raises(DocumentError, match="hijo de otra"):
        doc.execute("add_joint", {"name": "j2", "parent": a, "child": b})
    # ciclo
    with pytest.raises(DocumentError, match="ciclo|hijo de otra"):
        doc.execute("add_joint", {"name": "j3", "parent": b, "child": a})
    # eje nulo
    with pytest.raises(DocumentError, match="eje"):
        doc.execute(
            "add_joint",
            {"name": "j4", "parent": b, "child": doc.execute("create_box", {"position": {"x": 500}}),
             "axis": {"x": 0, "y": 0, "z": 0}},
        )


def test_delete_linked_feature_rolls_back(arm_doc):
    with pytest.raises(DocumentError):
        arm_doc.execute("delete_feature", {"feature": "c1_brazo"})
    assert len(arm_doc.scene) == 5  # rollback


def test_joints_survive_roundtrip(arm_doc):
    doc2 = Document.from_apolo_bytes(arm_doc.to_apolo_bytes())
    assert list(doc2.joints.keys()) == list(arm_doc.joints.keys())


def test_urdf_structure_and_frames(arm_doc):
    xml, meshes = build_urdf(arm_doc)
    root = ET.fromstring(xml)
    assert len(root.findall("link")) == 5
    assert len(root.findall("joint")) == 4
    assert len(meshes) == 5

    j2 = next(j for j in root.findall("joint") if j.get("name").startswith("j2"))
    assert j2.get("type") == "revolute"
    # hombro (z=220 mundo) relativo al marco de la columna (z=80): 0.14 m
    assert [float(v) for v in j2.find("origin").get("xyz").split()] == pytest.approx([0, 0, 0.14])
    assert float(j2.find("limit").get("upper")) == pytest.approx(math.radians(100), rel=1e-3)
    j4 = next(j for j in root.findall("joint") if j.get("name").startswith("j4"))
    assert j4.get("type") == "continuous"

    for link in root.findall("link"):
        assert link.find("inertial/mass") is not None
        assert link.find("visual/geometry/mesh") is not None


def test_urdf_zip_contains_meshes(arm_doc):
    zf = zipfile.ZipFile(io.BytesIO(export_urdf_zip(arm_doc)))
    names = zf.namelist()
    assert "robot.urdf" in names
    assert sum(1 for n in names if n.startswith("meshes/") and n.endswith(".stl")) == 5
    stl = zf.read(next(n for n in names if n.endswith(".stl")))
    assert len(stl) > 200


def test_sdf_export(arm_doc):
    zf = zipfile.ZipFile(io.BytesIO(export_sdf_zip(arm_doc)))
    sdf = ET.fromstring(zf.read("model.sdf").decode())
    model = sdf.find("model")
    assert len(model.findall("link")) == 5
    assert len(model.findall("joint")) == 4
    j1 = next(j for j in model.findall("joint") if j.get("name").startswith("j1"))
    assert j1.find("axis/xyz").text.split() == ["0.000000", "0.000000", "1.000000"]


def test_export_without_joints_rejected():
    doc = Document()
    doc.execute("create_box", {})
    with pytest.raises(ValueError, match="juntas"):
        export_urdf_zip(doc)


# ------------------------------------------------------------------- API HTTP
@pytest.fixture()
def client():
    api.DOC = Document("f6-api")
    return TestClient(api.app)


def test_kinematics_and_export_endpoints(client):
    client.post("/api/commands", json={"type": "create_robot_arm", "params": {"alcance": 500}})
    kin = client.get("/api/kinematics").json()
    assert len(kin["joints"]) == 4 and kin["errors"] == []

    urdf = client.get("/api/export/urdf")
    assert urdf.status_code == 200 and urdf.headers["content-type"] == "application/zip"
    sdf = client.get("/api/export/sdf")
    assert sdf.status_code == 200

    # las juntas de plantilla no se borran sueltas
    name = kin["joints"][0]["name"]
    assert client.delete(f"/api/joints/{name}").status_code == 400
    assert client.delete("/api/joints/no_existe").status_code == 404


def test_manual_joint_delete_via_api(client):
    client.post("/api/commands", json={"type": "create_box", "params": {}})
    client.post("/api/commands", json={"type": "create_cylinder", "params": {"position": {"x": 300}}})
    client.post(
        "/api/commands",
        json={"type": "add_joint", "params": {"name": "puerta", "parent": "c1", "child": "c2", "origin": {"x": 150}}},
    )
    assert len(client.get("/api/kinematics").json()["joints"]) == 1
    r = client.delete("/api/joints/puerta")
    assert r.status_code == 200
    assert client.get("/api/kinematics").json()["joints"] == []
