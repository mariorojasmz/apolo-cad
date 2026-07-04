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


# ================================================================ V5.8 ingletes
def _dir(a, b):
    return tuple(b[i] - a[i] for i in range(3))


def test_frame_inglete_triangulo():
    """Los 3 vértices son de grado 2 → inglete a la bisectriz; cut_length = longitud
    EXTERIOR calculada por fórmula desde las direcciones del fixture."""
    from apolo.library.catalog import build_component
    from apolo.library.miter import miter_angle

    A = build_component("PERFIL-4040", 1000)[0].volume / 1000.0
    d = Document()
    d.execute("create_frame", {"nodes": TRI_NODES, "edges": TRI_EDGES,
                               "perfil": "PERFIL-4040", "cordones": False,
                               "esquinas": "inglete"})
    members = {f.name.split("(")[1][:3]: f for f in _members(d)}
    pts = [tuple(map(float, n)) for n in TRI_NODES]
    for (i, j) in TRI_EDGES:
        f = members[f"{i}-{j}"]
        a, b = pts[i], pts[j]
        span = math.dist(a, b)
        # ancla exacta: V = A·span para CUALQUIER ángulo (bisector por el nodo)
        assert f.shape.volume == pytest.approx(A * span, rel=1e-4), f.name
        # α por extremo desde las direcciones salientes del fixture
        others = {(i, j) for (i, j) in TRI_EDGES}
        k_a = next(k for (m, k) in [(m, k) for m, k in TRI_EDGES] + [(k, m) for m, k in TRI_EDGES]
                   if m == i and k != j)
        k_b = next(k for (m, k) in [(m, k) for m, k in TRI_EDGES] + [(k, m) for m, k in TRI_EDGES]
                   if m == j and k != i)
        a1 = miter_angle(_dir(a, b), _dir(a, pts[k_a]))
        a2 = miter_angle(_dir(b, a), _dir(b, pts[k_b]))
        assert f.miter == (pytest.approx(a1, abs=0.1), pytest.approx(a2, abs=0.1)), f.name
        assert f.cut_length > span  # exterior: la punta rebasa el nodo


def test_frame_inglete_grado3_a_tope():
    # arista extra al ápice → grado 3: sus extremos caen a tope; la base sigue a inglete
    nodes = TRI_NODES + [[500, 500, 400]]
    edges = TRI_EDGES + [[2, 3]]
    d = Document()
    d.execute("create_frame", {"nodes": nodes, "edges": edges, "perfil": "PERFIL-4040",
                               "cordones": False, "esquinas": "inglete"})
    ms = {f.name.split("(")[1][:3]: f for f in _members(d)}
    assert ms["0-1"].miter is not None and ms["0-1"].miter[0] is not None  # base: 0 y 1 grado 2
    assert ms["1-2"].miter == (pytest.approx(ms["1-2"].miter[0]), None)    # extremo en 2 → tope
    assert ms["2-3"].miter is None                                          # ambos extremos tope


def test_frame_inglete_colineal_recto():
    # dos aristas colineales: corte RECTO en el nodo compartido (α=0), no inglete
    d = Document()
    d.execute("create_frame", {"nodes": [[0, 0, 0], [500, 0, 0], [1000, 0, 0]],
                               "edges": [[0, 1], [1, 2]], "perfil": "PERFIL-4040",
                               "cordones": False, "esquinas": "inglete"})
    m01 = next(f for f in _members(d) if "(0-1)" in f.name)
    assert m01.miter == (None, 0.0)  # extremo libre a tope, nodo compartido recto
    # los dos miembros se tocan EXACTAMENTE en x=500 (sin hueco de 2·sec)
    bb = m01.shape.bounding_box()
    assert bb.max.X == pytest.approx(500, abs=0.01)


def test_frame_inglete_no_interference():
    d = Document()
    d.execute("create_frame", {"nodes": TRI_NODES, "edges": TRI_EDGES,
                               "perfil": "PERFIL-4040", "cordones": True,
                               "esquinas": "inglete"})
    report = interference_report(d.scene, exclude_pairs=same_command_pairs(d))
    assert report["interferencias"] == []


def test_frame_inglete_api():
    api.DOC = Document("frame-ing")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_frame", "params": {
        "nodes": TRI_NODES, "edges": TRI_EDGES, "perfil": "PERFIL-4040",
        "esquinas": "inglete"}})
    assert r.status_code == 200
    bom = client.get("/api/bom").json()
    assert any("∠" in row["descripcion"] for row in bom)
