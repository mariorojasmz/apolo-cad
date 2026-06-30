"""Fase 2 · píxel→3D (pick): señalar en el render → pieza/coordenada."""

import pytest

from apolo.doc import Document
from apolo.kernel.pick import _resolved_shapes, _vtk_projector, pick_point


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


def test_pick_free_angle_separates_boxes():
    """A ÁNGULO LIBRE (azimuth/elevation), dos cajas separadas en X siguen distinguiéndose:
    pickear a izquierda y derecha devuelve cajas distintas (la separación se conserva)."""
    doc = Document()
    a = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": -600}})
    b = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 600}})
    left = pick_point(doc.scene, "frente", 0.15, 0.5, azimuth=-90, elevation=12)
    right = pick_point(doc.scene, "frente", 0.85, 0.5, azimuth=-90, elevation=12)
    assert {left["feature_id"], right["feature_id"]} == {a, b}


def test_pick_free_angle_returns_valid_dict():
    doc = Document()
    doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    res = pick_point(doc.scene, "iso", 0.5, 0.5, azimuth=30, elevation=20)
    assert res["tipo"] in {"feature", "face"}
    assert len(res["world_point"]) == 3 and "feature_id" in res


def test_pick_isolate_restricts_candidates():
    """Con isolate, el pick SOLO considera esas piezas: un punto donde sin isolate ganaría la pieza
    del medio (c), con isolate=[a,b] devuelve una de las externas (coherente con un render aislado)."""
    doc = Document()
    a = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": -600}})
    c = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 0}})
    b = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 600}})
    assert pick_point(doc.scene, "frente", 0.5, 0.5)["feature_id"] == c  # sin isolate: la del centro
    res = pick_point(doc.scene, "frente", 0.5, 0.5, isolate=[a, b])
    assert res["feature_id"] in {a, b}  # con isolate: nunca la del medio


def test_pick_section_excludes_clipped_piece():
    """section recorta como el render: de dos cajas a lados opuestos del centro, una queda fuera
    de la semicaja → un solo candidato sobrevive (coherente con la foto seccionada)."""
    doc = Document()
    doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": -600}})
    doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 600}})
    items = _resolved_shapes(doc.scene, None, None, "x")
    assert len(items) == 1  # la mitad recortada desaparece
    res = pick_point(doc.scene, "frente", 0.5, 0.5, section="x")
    assert res["feature_id"] in doc.scene


def test_vtk_projector_centers_bbox():
    """Proyección EXACTA de VTK: el centro del bbox encuadrado cae en el centro de la imagen."""
    proj = _vtk_projector([-100.0, -100.0, -100.0], [100.0, 100.0, 100.0], "iso", None, None, 1.0)
    if proj is None:
        pytest.skip("VTK no disponible")
    u, v = proj([0.0, 0.0, 0.0])
    assert abs(u - 0.5) < 0.05 and abs(v - 0.5) < 0.05


def test_vtk_projector_pan_shifts_center():
    """pan en la cámara mueve a dónde proyecta el centro del bbox (mismo encuadre que el render)."""
    box = ([-100.0, -100.0, -100.0], [100.0, 100.0, 100.0])
    p0 = _vtk_projector(*box, "iso", None, None, 1.0)
    pp = _vtk_projector(*box, "iso", None, None, 1.0, 0.0, [0.5, 0.0])
    if p0 is None or pp is None:
        pytest.skip("VTK no disponible")
    u0, _ = p0([0.0, 0.0, 0.0])
    up, _ = pp([0.0, 0.0, 0.0])
    assert abs(up - u0) > 0.05  # el pan desplaza el centro en la imagen
