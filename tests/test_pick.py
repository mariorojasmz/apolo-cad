"""Fase 2 · píxel→3D (pick): señalar en el render → pieza/coordenada."""

from apolo.doc import Document
from apolo.kernel.pick import pick_point


def test_pick_distinguishes_two_separated_boxes():
    """Vista frente (X horizontal): pickear a izquierda y derecha de la imagen devuelve las
    DOS cajas (cada (u,v) cae sobre una distinta). Flip-agnóstico: solo exige que se separen."""
    doc = Document()
    a = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": -400}})
    b = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 400}})
    left = pick_point(doc.scene, "frente", 0.2, 0.5)
    right = pick_point(doc.scene, "frente", 0.8, 0.5)
    assert {left["feature_id"], right["feature_id"]} == {a, b}


def test_pick_returns_world_point_and_kind():
    doc = Document()
    doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    res = pick_point(doc.scene, "iso", 0.5, 0.5)
    assert res["tipo"] in {"feature", "face"}
    assert len(res["world_point"]) == 3
