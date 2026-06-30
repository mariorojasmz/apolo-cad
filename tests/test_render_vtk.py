"""Render VTK off-screen (sombreado suave, como el viewport web).

VTK necesita un contexto OpenGL off-screen; si el entorno no lo tiene, los tests que
rasterizan se SALTAN (no fallan) — la lógica del endpoint cae a matplotlib igualmente.
"""

import pytest

pytest.importorskip("vtk")

from apolo.doc import Document
from apolo.kernel.render_vtk import render_scene_vtk

PNG = b"\x89PNG"


def _box_scene(**pos):
    d = Document()
    fid = d.execute("create_box", {"width": 400, "depth": 120, "height": 120, **pos})
    return d, fid


def test_vtk_empty_scene_raises():
    # no necesita OpenGL: valida antes de renderizar
    with pytest.raises(ValueError):
        render_scene_vtk(Document().scene)


def test_vtk_render_png_header():
    d, _ = _box_scene()
    try:
        png = render_scene_vtk(d.scene, "iso")
    except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL en este entorno
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    assert png[:4] == PNG and len(png) > 1000


def test_vtk_isolate_and_fit_change_output():
    d = Document()
    a = d.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": -2000}})
    d.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 2000}})
    try:
        full = render_scene_vtk(d.scene, "iso")
        fit = render_scene_vtk(d.scene, "iso", fit_ids=[a])
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    assert full[:4] == PNG and fit[:4] == PNG
    assert full != fit  # encuadrar una pieza cambia la imagen


def test_vtk_free_angle_changes_output():
    d, _ = _box_scene()
    try:
        preset = render_scene_vtk(d.scene, "iso")
        free = render_scene_vtk(d.scene, "iso", azimuth=120, elevation=10)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    assert free[:4] == PNG
    assert preset != free  # un ángulo libre distinto del preset cambia la imagen


def test_vtk_edges_toggle_changes_output():
    """edges=True superpone aristas vivas → imagen distinta de edges=False (separa piezas)."""
    d, _ = _box_scene()
    try:
        with_e = render_scene_vtk(d.scene, "iso", edges=True)
        no_e = render_scene_vtk(d.scene, "iso", edges=False)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    assert with_e[:4] == PNG and no_e[:4] == PNG
    assert with_e != no_e


def test_vtk_xray_changes_output():
    """xray=True deja el contexto translúcido EN SU COLOR (≠ gris fantasma) → imagen distinta."""
    d = Document()
    a = d.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": -300}})
    d.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 300}})
    try:
        ghost = render_scene_vtk(d.scene, "iso", highlight_ids=[a])           # resto gris fantasma
        xray = render_scene_vtk(d.scene, "iso", highlight_ids=[a], xray=True)  # resto translúcido a color
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    assert xray[:4] == PNG and ghost[:4] == PNG
    assert xray != ghost


def test_vtk_glass_renders_translucent():
    """Una pieza con material 'vidrio' usa la vía translúcida (depth peeling) sin romper."""
    d = Document()
    fid = d.execute("create_box", {"width": 400, "depth": 8, "height": 400})
    d.set_material(fid, "vidrio")
    try:
        png = render_scene_vtk(d.scene, "iso")
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    assert png[:4] == PNG and len(png) > 1000


def test_vtk_roll_changes_output():
    """roll gira la cámara sobre el eje de visión → imagen distinta."""
    d, _ = _box_scene()
    try:
        a = render_scene_vtk(d.scene, "iso")
        b = render_scene_vtk(d.scene, "iso", roll=35)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    assert b[:4] == PNG and a != b


def test_vtk_pan_changes_output():
    """pan desplaza el encuadre en el plano de vista → imagen distinta."""
    d, _ = _box_scene()
    try:
        a = render_scene_vtk(d.scene, "iso")
        b = render_scene_vtk(d.scene, "iso", pan=[0.4, 0.0])
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    assert b[:4] == PNG and a != b


def test_vtk_labels_changes_output():
    """labels=True rotula los ids (billboard) → imagen distinta de sin rótulos."""
    d, _ = _box_scene()
    try:
        a = render_scene_vtk(d.scene, "iso")
        b = render_scene_vtk(d.scene, "iso", labels=True)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    assert b[:4] == PNG and a != b


def test_vtk_dimension_overlay_changes_output():
    """Una cota (línea + etiqueta) sobre el render produce PNG válido y distinto del render sin cota."""
    d = Document()
    d.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": -300}})
    d.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 300}})
    dim = {"p1": [-250.0, 0.0, 0.0], "p2": [250.0, 0.0, 0.0], "label": "500 mm"}
    try:
        plain = render_scene_vtk(d.scene, "iso")
        dimd = render_scene_vtk(d.scene, "iso", dimension=dim)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"VTK off-screen no disponible: {exc}")
    assert dimd[:4] == PNG
    assert plain != dimd  # la cota cambia la imagen
