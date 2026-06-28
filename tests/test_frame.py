"""G3: bastidor de esqueleto de aristas ARBITRARIO (create_frame)."""
import math

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.commands.registry import CommandError
from apolo.doc import Document, DocumentError
from apolo.kernel.matrix import direction_to_euler
from apolo.library.bom import bom_from_scene
from apolo.library.checks import interference_report, same_command_pairs

# triángulo en el plano X-Z (cercha simple)
TRI_NODES = [[0, 0, 0], [1000, 0, 0], [500, 0, 800]]
TRI_EDGES = [[0, 1], [1, 2], [2, 0]]


def _members(doc):
    return [f for f in doc.scene.values() if "Miembro" in f.name]


def test_direction_to_euler_axes():
    assert len(direction_to_euler((0, 0, 1))) == 3  # devuelve euler XYZ
    # Z→X: un perfil orientado debe quedar largo en X
    d = Document()
    d.execute("create_frame", {"nodes": [[0, 0, 0], [500, 0, 0]], "edges": [[0, 1]],
                               "perfil": "PERFIL-4040", "cordones": False})
    bb = _members(d)[0].shape.bounding_box()
    assert bb.size.X > bb.size.Y and bb.size.X > bb.size.Z  # tumbado a lo largo de X


def test_frame_triangle_members_and_beads():
    d = Document()
    d.execute("create_frame", {"name": "Cercha", "nodes": TRI_NODES, "edges": TRI_EDGES,
                               "perfil": "PERFIL-4040"})
    assert len(_members(d)) == 3
    assert len([f for f in d.scene.values() if f.name.endswith("Cordón")]) == 3
    # el miembro inclinado (1-2) abarca de x=1000 a x=500 y sube en Z
    side = next(f for f in _members(d) if "(1-2)" in f.name).shape.bounding_box()
    assert side.min.X < 520 and side.max.X > 980
    assert side.max.Z > 700


def test_frame_cut_list():
    d = Document()
    d.execute("create_frame", {"nodes": TRI_NODES, "edges": TRI_EDGES, "perfil": "PERFIL-4040"})
    sec = 40.0
    base_len = round(1000 - 2 * sec, 1)
    side_len = round(math.hypot(500, 800) - 2 * sec, 1)
    rows = {round(r["longitud_mm"], 1): r["cantidad"] for r in bom_from_scene(d.scene)
            if r["ref"] == "PERFIL-4040"}
    assert rows[base_len] == 1        # base
    assert rows[side_len] == 2        # dos lados iguales → misma fila


def test_frame_no_self_interference():
    d = Document()
    d.execute("create_frame", {"nodes": TRI_NODES, "edges": TRI_EDGES, "perfil": "PERFIL-4040"})
    report = interference_report(d.scene, exclude_pairs=same_command_pairs(d))
    assert report["interferencias"] == []


def test_frame_validations():
    d = Document()
    with pytest.raises((CommandError, DocumentError)):  # índice fuera de rango
        d.execute("create_frame", {"nodes": [[0, 0, 0], [100, 0, 0]], "edges": [[0, 5]],
                                   "perfil": "PERFIL-4040"})
    with pytest.raises((CommandError, DocumentError)):  # arista más corta que 2·sección
        d.execute("create_frame", {"nodes": [[0, 0, 0], [30, 0, 0]], "edges": [[0, 1]],
                                   "perfil": "PERFIL-4040"})
    assert d.commands == []


def test_frame_parametric_node_edit():
    d = Document()
    d.execute("set_variable", {"name": "H", "expression": "800"})
    cid = d.execute("create_frame", {"nodes": [[0, 0, 0], [1000, 0, 0], [500, 0, "=H"]],
                                     "edges": TRI_EDGES, "perfil": "PERFIL-4040", "cordones": False})
    top = lambda: max(f.shape.bounding_box().max.Z for f in _members(d))
    t1 = top()  # ~777 (miembros recortados sec en el ápice inclinado)
    var = next(c["id"] for c in d.commands if c["type"] == "set_variable")
    d.edit(var, {"name": "H", "expression": "1200"})
    t2 = top()
    assert t2 - t1 > 350  # el ápice sube al cambiar la variable (cascada paramétrica)


def test_frame_api():
    api.DOC = Document("frame-api")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_frame", "params": {
        "nodes": TRI_NODES, "edges": TRI_EDGES, "perfil": "PERFIL-4545"}})
    assert r.status_code == 200
    bom = client.get("/api/bom").json()
    assert any(row["ref"] == "PERFIL-4545" for row in bom)
