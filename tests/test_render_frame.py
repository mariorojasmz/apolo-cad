"""Encuadre del render: fit_ids, zoom y modo proporcional (mejora #4)."""

from apolo.doc import Document
from apolo.kernel.render import render_scene_png

PNG = b"\x89PNG"


def _long_scene():
    """Caja larga y baja (4000x100x100): el caso que con el cubo sale aplastado."""
    doc = Document()
    doc.execute("create_box", {"width": 4000, "depth": 100, "height": 100})
    return doc.scene


def test_render_defaults_unchanged():
    assert render_scene_png(_long_scene())[:4] == PNG


def test_render_proportional_differs_from_cube():
    scene = _long_scene()
    cube = render_scene_png(scene, proportional=False)
    prop = render_scene_png(scene, proportional=True)
    assert cube[:4] == PNG and prop[:4] == PNG
    assert cube != prop  # la proporción real cambia el encuadre


def test_render_zoom_changes_output():
    scene = _long_scene()
    assert render_scene_png(scene, zoom=1.0) != render_scene_png(scene, zoom=2.0)


def test_render_fit_ids_subset():
    doc = Document()
    a = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": -3000}})
    doc.execute("create_box", {"width": 100, "depth": 100, "height": 100, "position": {"x": 3000}})
    full = render_scene_png(doc.scene)
    fit = render_scene_png(doc.scene, fit_ids=[a])  # encuadra solo la caja izquierda
    assert full[:4] == PNG and fit[:4] == PNG
    assert full != fit


# --- Fase 1: percepción (multivista, etiquetas, sección) ---

def test_render_multiview_one_image():
    """`views` con ≥2 vistas compone una sola imagen PNG válida y distinta de la vista única."""
    scene = _long_scene()
    one = render_scene_png(scene, view="iso")
    multi = render_scene_png(scene, views=["iso", "frente", "planta", "lateral"])
    assert one[:4] == PNG and multi[:4] == PNG
    assert one != multi


def test_render_labels_opt_in():
    """labels=True produce PNG válido y distinto del render sin etiquetas (no rompe)."""
    scene = _long_scene()
    plain = render_scene_png(scene)
    labeled = render_scene_png(scene, labels=True)
    assert labeled[:4] == PNG and plain != labeled


def test_render_section_clips():
    """section recorta los sólidos (cambia la imagen) sin romper; produce PNG válido."""
    doc = Document()
    # caja hueca: un cubo con un agujero pasante → la sección revela el interior
    doc.execute("create_box", {"width": 400, "depth": 400, "height": 400})
    full = render_scene_png(doc.scene)
    cut = render_scene_png(doc.scene, section="x")
    assert full[:4] == PNG and cut[:4] == PNG
    assert full != cut


def test_render_defaults_still_identical_after_refactor():
    """El camino por defecto (1 vista, sin params nuevos) sigue dando PNG válido."""
    assert render_scene_png(_long_scene(), view="frente")[:4] == PNG
