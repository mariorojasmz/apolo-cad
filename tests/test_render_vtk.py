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
