"""Mates persistentes (V3 bloque #2): relaciones de ensamblaje que se
re-resuelven en cada regeneración (a diferencia de attach, one-shot)."""
import math

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.commands.registry import CommandError
from apolo.doc import Document, DocumentError


def _two_boxes(d, bz=200):
    a = d.execute("create_box", {"name": "A", "width": 100, "depth": 100, "height": 40})
    b = d.execute("create_box", {"name": "B", "width": 40, "depth": 40, "height": 40,
                                 "position": {"x": 500, "y": 300, "z": bz}})
    return a, b


def _coincide(d, a, b, **extra):
    return d.execute("add_mate", {
        "name": "m1", "type": "coincidente", "feature_a": a, "feature_b": b,
        "ref_a": {"mode": "cara", "face": "tope"}, "ref_b": {"mode": "cara", "face": "base"},
        **extra,
    })


# ------------------------------------------------------------- tipos de mate
def test_coincidente_flush():
    d = Document()
    a, b = _two_boxes(d)
    _coincide(d, a, b)
    bb = d.scene[b].shape.bounding_box()
    assert bb.min.Z == pytest.approx(20, abs=1e-3)          # a ras del tope de A (z=+20)
    assert (bb.min.X + bb.max.X) / 2 == pytest.approx(0, abs=1e-3)  # centrado sobre A
    assert (bb.min.Y + bb.max.Y) / 2 == pytest.approx(0, abs=1e-3)


def test_mate_is_persistent():
    """El diferenciador frente a attach: editar A recoloca B sola."""
    d = Document()
    a, b = _two_boxes(d)
    _coincide(d, a, b)
    assert d.scene[b].shape.bounding_box().min.Z == pytest.approx(20, abs=1e-3)
    # subir A a alto 80 (tope z=+40) → B debe seguir pegada
    d.edit(d.commands[0]["id"], {"name": "A", "width": 100, "depth": 100, "height": 80})
    assert d.scene[b].shape.bounding_box().min.Z == pytest.approx(40, abs=1e-3)


def test_distancia_con_expresion():
    d = Document()
    d.execute("set_variable", {"name": "gap", "expression": "25"})
    a, b = _two_boxes(d)
    d.execute("add_mate", {
        "name": "m1", "type": "distancia", "feature_a": a, "feature_b": b,
        "ref_a": {"mode": "cara", "face": "tope"}, "ref_b": {"mode": "cara", "face": "base"},
        "value": "=gap",
    })
    assert d.scene[b].shape.bounding_box().min.Z == pytest.approx(45, abs=1e-3)  # 20 + 25
    # cambiar la variable propaga
    var = next(c["id"] for c in d.commands if c["type"] == "set_variable")
    d.edit(var, {"name": "gap", "expression": "10"})
    assert d.scene[b].shape.bounding_box().min.Z == pytest.approx(30, abs=1e-3)


def test_concentrico_tornillo_en_agujero():
    d = Document()
    placa = d.execute("create_box", {"name": "placa", "width": 120, "depth": 80, "height": 15})
    d.execute("drill_hole", {"feature": placa, "position": {"x": 0, "y": 0, "z": -7.5},
                             "axis": "z", "diameter": 8.5, "depth": 0})
    torn = d.execute("insert_component", {"component": "DIN912-M8", "position": {"x": 400}})
    d.execute("add_mate", {
        "name": "t1", "type": "concentrico", "feature_a": placa, "feature_b": torn,
        "ref_a": {"mode": "cerca", "point": [0, 4.25, 0]},
        "ref_b": {"mode": "cerca", "point": [400, 4, -5]},
    })
    bb = d.scene[torn].shape.bounding_box()
    assert (bb.min.X + bb.max.X) / 2 == pytest.approx(0, abs=1e-2)  # eje del tornillo en el agujero
    assert (bb.min.Y + bb.max.Y) / 2 == pytest.approx(0, abs=1e-2)


def test_flip_invierte_lado():
    d = Document()
    a, b = _two_boxes(d)
    _coincide(d, a, b, flip=True)
    # con flip sigue a ras (el giro es alrededor del eje normal) → mismo z
    assert d.scene[b].shape.bounding_box().min.Z == pytest.approx(20, abs=1e-3)


def test_mate_sobre_instancia():
    """Una instancia de catálogo (mesh_key+matrix) se recoloca y mantiene matrix."""
    d = Document()
    a = d.execute("create_box", {"name": "A", "width": 200, "depth": 200, "height": 40})
    perfil = d.execute("insert_component", {"component": "PERFIL-4040", "length": 100,
                                            "position": {"x": 600}})
    d.execute("add_mate", {
        "name": "m1", "type": "coincidente", "feature_a": a, "feature_b": perfil,
        "ref_a": {"mode": "cara", "face": "tope"}, "ref_b": {"mode": "cara", "face": "base"},
    })
    feat = d.scene[perfil]
    assert feat.matrix is not None  # sigue siendo instancia
    assert feat.shape.bounding_box().min.Z == pytest.approx(20, abs=1e-3)


# --------------------------------------------------------- integridad / validación
def test_borrar_referencia_falla_y_revierte():
    d = Document()
    a, b = _two_boxes(d)
    _coincide(d, a, b)
    n = len(d.commands)
    with pytest.raises(DocumentError):
        d.execute("delete_feature", {"feature": a})
    assert len(d.commands) == n          # rollback
    assert "m1" in d.mates


def test_validaciones():
    d = Document()
    a, b = _two_boxes(d)
    _coincide(d, a, b)
    with pytest.raises(DocumentError, match="existe"):
        _coincide(d, a, b)  # nombre duplicado
    with pytest.raises(DocumentError, match="árbol|mateado"):
        d.execute("add_mate", {"name": "m2", "type": "coincidente", "feature_a": a, "feature_b": b})
    c = d.execute("create_box", {"name": "C", "width": 20, "depth": 20, "height": 20})
    with pytest.raises(DocumentError, match="consigo mismo"):
        d.execute("add_mate", {"name": "m3", "type": "coincidente", "feature_a": c, "feature_b": c})


def test_no_ciclo():
    d = Document()
    a = d.execute("create_box", {"name": "A"})
    b = d.execute("create_box", {"name": "B", "position": {"x": 200}})
    d.execute("add_mate", {"name": "m1", "type": "coincidente", "feature_a": a, "feature_b": b})
    with pytest.raises(DocumentError, match="ciclo"):
        d.execute("add_mate", {"name": "m2", "type": "coincidente", "feature_a": b, "feature_b": a})


def test_tipo_desconocido_rechazado():
    d = Document()
    a, b = _two_boxes(d)
    with pytest.raises((CommandError, DocumentError)):
        d.execute("add_mate", {"name": "m1", "type": "magia", "feature_a": a, "feature_b": b})


def test_roundtrip_preserva_mates():
    d = Document()
    a, b = _two_boxes(d)
    _coincide(d, a, b)
    d2 = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert list(d2.mates.keys()) == ["m1"]
    assert d2.scene[b].shape.bounding_box().min.Z == pytest.approx(20, abs=1e-3)


# ----------------------------------------------------------------- API HTTP
def test_api_mates_crud():
    api.DOC = Document("mate-test")
    client = TestClient(api.app)
    a = client.post("/api/commands", json={"type": "create_box", "params": {"name": "A"}}).json()
    a_id = a["features"][0]["id"]
    client.post("/api/commands", json={"type": "create_box", "params": {"name": "B", "position": {"x": 300}}})
    b_id = next(f["id"] for f in client.get("/api/scene").json()["features"] if f["name"] == "B")
    r = client.post("/api/commands", json={"type": "add_mate", "params": {
        "name": "m1", "type": "coincidente", "feature_a": a_id, "feature_b": b_id,
        "ref_a": {"mode": "cara", "face": "tope"}, "ref_b": {"mode": "cara", "face": "base"}}})
    assert r.status_code == 200
    mates = client.get("/api/mates").json()
    assert [m["name"] for m in mates] == ["m1"]
    assert client.delete("/api/mates/m1").status_code == 200
    assert client.get("/api/mates").json() == []
    assert client.delete("/api/mates/nope").status_code == 404
