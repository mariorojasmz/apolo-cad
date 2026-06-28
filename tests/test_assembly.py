import math

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.kernel.matrix import (
    compose_place,
    euler_between_axes,
    multiply,
    rotation_xyz,
    to_column_major16,
    translation,
)
from apolo.library import interference_report
from apolo.robotics.pose import posed_shapes


# ------------------------------------------------------------------- matrices
def test_matrix_compose_place_matches_build123d():
    """La matriz T·R debe colocar puntos igual que place() de build123d."""
    from build123d import Box

    from apolo.kernel.shapes import place

    m = compose_place((100, 50, 20), (0, 0, 90))
    shape = place(Box(40, 20, 10), (100, 50, 20), (0, 0, 90))
    bb = shape.bounding_box()
    # caja 40x20x10 girada 90° en Z: spans → 20 en X, 40 en Y, centrada en (100,50,20)
    assert (bb.min.X + bb.max.X) / 2 == pytest.approx(m[0][3], abs=1e-6)
    assert bb.max.X - bb.min.X == pytest.approx(20, abs=1e-6)
    assert bb.max.Y - bb.min.Y == pytest.approx(40, abs=1e-6)


def test_matrix_multiply_and_column_major():
    t = translation(1, 2, 3)
    r = rotation_xyz(0, 0, 90)
    m = multiply(t, r)
    col = to_column_major16(m)
    assert col[12] == 1 and col[13] == 2 and col[14] == 3  # traslación en columna 4
    assert col[0] == pytest.approx(0, abs=1e-9)  # cos90
    assert col[1] == pytest.approx(1, abs=1e-9)  # sin90


@pytest.mark.parametrize("a,b", [("z", "x"), ("z", "y"), ("x", "z"), ("y", "x"), ("x", "y"), ("y", "z")])
def test_euler_between_axes_maps_unit_vector(a, b):
    euler = euler_between_axes(a, b)
    r = rotation_xyz(*euler)
    vec = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[a]
    out = [sum(r[i][j] * vec[j] for j in range(3)) for i in range(3)]
    expected = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[b]
    assert out == pytest.approx(expected, abs=1e-9)


# ------------------------------------------------------------------ instancias
def test_conveyor_is_fully_instanced():
    doc = Document()
    doc.execute("create_conveyor", {"largo": 2000, "ancho": 600, "altura": 750, "paso": 100, "motor": "MOTOR-037"})
    instanced = [f for f in doc.scene.values() if f.mesh_key and f.matrix]
    assert len(instanced) == len(doc.scene) == 28
    assert len({f.mesh_key for f in instanced}) == 5  # larguero, rodillo, pata, travesaño, motor


def test_payload_shares_definitions():
    api.DOC = Document("inst")
    api.DOC.execute("create_conveyor", {"largo": 2000, "ancho": 600, "altura": 750, "paso": 100})
    payload = api.scene_payload()
    assert len(payload["definitions"]) == 4  # sin motor
    assert all(f["mesh"] is None for f in payload["features"])
    assert all(f["matrix"] is not None and len(f["matrix"]) == 16 for f in payload["features"])


def test_transform_composes_instance_matrix():
    doc = Document()
    fid = doc.execute("create_box", {"width": 50, "depth": 50, "height": 50})
    doc.execute("transform", {"feature": fid, "translate": {"x": 100}, "rotate": {"z": 45}})
    feat = doc.scene[fid]
    assert feat.mesh_key is not None
    # la matriz debe reproducir el bbox real (centro en x=100)
    bb = feat.shape.bounding_box()
    assert feat.matrix[0][3] == pytest.approx((bb.min.X + bb.max.X) / 2, abs=1e-6)


def test_modify_ops_make_unique():
    doc = Document()
    fid = doc.execute("create_box", {"width": 100, "depth": 100, "height": 50})
    assert doc.scene[fid].mesh_key
    doc.execute("drill_hole", {"feature": fid, "position": {"z": 25}, "axis": "-z", "diameter": 10})
    assert doc.scene[fid].mesh_key is None and doc.scene[fid].matrix is None


def test_pattern_copies_share_definition():
    doc = Document()
    fid = doc.execute("create_cylinder", {"radius": 10, "height": 30})
    pid = doc.execute("pattern_linear", {"feature": fid, "count": 5, "spacing": {"x": 50}})
    keys = {doc.scene[f].mesh_key for f in doc.scene}
    assert len(keys) == 1  # todos comparten cyl|10|30
    last = doc.scene[f"{pid}_4"]
    assert last.matrix[0][3] == pytest.approx(200)


# -------------------------------------------------------- attach con alineación
def test_attach_align_axis():
    doc = Document()
    caja = doc.execute("create_box", {"width": 200, "depth": 200, "height": 100})
    cil = doc.execute("create_cylinder", {"radius": 20, "height": 150, "position": {"x": 500}})
    doc.execute(
        "attach",
        {"feature": cil, "anchor": "base", "target": caja, "target_anchor": "tope",
         "align_my": "z", "align_to": "x"},
    )
    bb = doc.scene[cil].shape.bounding_box()
    assert bb.max.X - bb.min.X == pytest.approx(150, abs=1e-3)  # tumbado a lo largo de X
    assert bb.min.Z == pytest.approx(50, abs=1e-3)  # apoyado en el tope de la caja
    assert (bb.min.X + bb.max.X) / 2 == pytest.approx(0, abs=1e-3)  # centrado


# ---------------------------------------------------------- colisión en pose
def test_posed_collision_detects_swing():
    from apolo.library.checks import joint_pairs

    doc = Document()
    doc.execute("create_robot_arm", {"name": "R1", "alcance": 600})
    doc.execute("create_box", {"width": 60, "depth": 60, "height": 800, "position": {"y": 450, "z": 400}})
    exclude = joint_pairs(doc)
    # con los solapes de junta excluidos, en reposo no hay colisiones REALES
    base = interference_report(doc.scene, exclude_pairs=exclude)["interferencias"]
    assert base == []

    shapes, warnings = posed_shapes(doc, {"j1_base_c1": 90.0})
    posed = interference_report(doc.scene, shapes_override=shapes, exclude_pairs=exclude)["interferencias"]
    assert warnings == []
    assert len(posed) == 1  # al girar 90°, el brazo barre el poste
    nombres = {posed[0]["nombre_a"], posed[0]["nombre_b"]}
    assert any("Caja" in n for n in nombres)


def test_posed_shapes_zero_pose_is_identity():
    doc = Document()
    doc.execute("create_robot_arm", {"name": "R1", "alcance": 500})
    shapes, _ = posed_shapes(doc, {})
    for fid, shape in shapes.items():
        assert shape.volume == pytest.approx(doc.scene[fid].shape.volume, rel=1e-9)


# ------------------------------------------------------------------- API HTTP
@pytest.fixture()
def client():
    api.DOC = Document("f8-api")
    return TestClient(api.app)


def test_checks_endpoint_with_pose(client):
    client.post("/api/commands", json={"type": "create_robot_arm", "params": {"alcance": 600}})
    client.post(
        "/api/commands",
        json={"type": "create_box", "params": {"width": 60, "depth": 60, "height": 800, "position": {"y": 450, "z": 400}}},
    )
    rest = client.post("/api/checks", json={}).json()
    swung = client.post("/api/checks", json={"joint_values": {"j1_base_c1": 90}}).json()
    assert rest["interferencias"]["interferencias"] == []  # solapes de junta excluidos
    assert len(swung["interferencias"]["interferencias"]) == 1  # el poste
    assert swung["interferencias"]["avisos_pose"] == []
