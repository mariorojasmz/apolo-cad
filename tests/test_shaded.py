"""Planos a color tipo Inventor: isométrica SOMBREADA embebida (render 3D en la lámina)."""

import importlib.util

import pytest

from apolo.doc import Document
from apolo.drawing import compose_sheet
from apolo.drawing.svg import sheet_to_svg

_HAS_MPL = importlib.util.find_spec("matplotlib") is not None


@pytest.mark.skipif(not _HAS_MPL, reason="requiere matplotlib para el render 3D")
def test_shaded_embeds_color_iso():
    doc = Document()
    doc.execute("create_box", {"name": "a", "width": 200, "depth": 100, "height": 40})
    doc.execute("create_box", {"name": "b", "width": 200, "depth": 100, "height": 40, "position": {"z": 60}})
    model = compose_sheet(doc.scene, cutlist=True, shaded=True)  # conjunto (sin perfil) → con rótulo
    assert len(model.images) == 1                       # render iso embebido
    img = model.images[0]
    assert img.w > 0 and img.h > 0 and img.png[:4] == b"\x89PNG"  # PNG válido con tamaño
    assert any(l.text == "ISOMÉTRICA · sombreado" for l in model.labels)
    assert "ISOMÉTRICA (sin escala)" not in [l.text for l in model.labels]  # reemplaza el alambre
    assert "<image" in sheet_to_svg(model)              # el SVG lleva la imagen base64


def test_no_shaded_keeps_wireframe():
    """Sin shaded, no hay imagen embebida y se mantiene la isométrica de alambre."""
    doc = Document()
    doc.execute("create_box", {"name": "a", "width": 200, "depth": 100, "height": 40})
    model = compose_sheet(doc.scene)
    assert not model.images
    assert any("ISOMÉTRICA" in l.text for l in model.labels)
