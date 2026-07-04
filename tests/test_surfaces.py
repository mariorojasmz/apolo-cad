"""Superficies básicas V5.11: boundary_surface / fill_surface / thicken.

Una superficie es una Face de volumen 0 (geometría de CONSTRUCCIÓN); solo el sólido de
thicken es fabricable → excluida de BOM/masa/costeo y de la vista de sección.
"""
import math
import tempfile
from pathlib import Path

import pytest

from apolo.doc import Document, DocumentError


def _square_curves(side, z=0.0, x0=0.0, y0=0.0):
    """Cuatro segmentos que cierran un cuadrado de lado `side` con esquina en (x0,y0)."""
    a = [x0, y0, z]
    b = [x0 + side, y0, z]
    c = [x0 + side, y0 + side, z]
    d = [x0, y0 + side, z]
    return [{"points": [a, b]}, {"points": [b, c]}, {"points": [c, d]}, {"points": [d, a]}]


# ------------------------------------------------------------- boundary_surface
def test_boundary_square_is_zero_volume_face():
    d = Document()
    cid = d.execute("boundary_surface", {"name": "Placa", "curves": _square_curves(100)})
    sh = d.scene[cid].shape
    assert sh.area == pytest.approx(10000.0, rel=1e-3)
    assert sh.volume == pytest.approx(0.0, abs=1e-6)
    assert len(sh.faces()) == 1
    assert len(sh.solids()) == 0


def test_boundary_tessellates_for_viewport():
    d = Document()
    cid = d.execute("boundary_surface", {"curves": _square_curves(100)})
    verts, tris = d.scene[cid].shape.tessellate(0.5, 0.25)
    assert len(verts) > 0 and len(tris) > 0


def test_boundary_shaping_point_makes_nonplanar_larger_area():
    d = Document()
    cid = d.execute("boundary_surface",
                    {"curves": _square_curves(100), "points": [[50, 50, 40]]})
    # un punto elevado al centro abomba la superficie → más área que el plano
    assert d.scene[cid].shape.area > 10000.0


def test_boundary_open_loop_rejected():
    d = Document()
    with pytest.raises(DocumentError, match="(?i)cerrar|contorno|lazo|superficie"):
        d.execute("boundary_surface", {"curves": [{"points": [[0, 0, 0], [100, 0, 0]]}]})


def test_boundary_with_hole_subtracts_area():
    d = Document()
    cid = d.execute("boundary_surface", {
        "curves": _square_curves(100),
        "holes": [_square_curves(20, x0=40, y0=40)],  # hueco centrado, lado 20 → área 400
    })
    # área ≈ exterior − hueco.
    assert d.scene[cid].shape.area == pytest.approx(10000.0 - 400.0, rel=1e-2)


def test_boundary_accepts_expressions():
    d = Document()
    d.execute("set_variable", {"name": "w", "expression": "80"})
    a, b, c, e = [0, 0, 0], ["=w", 0, 0], ["=w", "=w", 0], [0, "=w", 0]
    cid = d.execute("boundary_surface",
                    {"curves": [{"points": [a, b]}, {"points": [b, c]},
                                {"points": [c, e]}, {"points": [e, a]}]})
    assert d.scene[cid].shape.area == pytest.approx(80 * 80, rel=1e-3)


# ----------------------------------------------------------------- fill_surface
def test_fill_box_top_covers_face():
    d = Document()
    b = d.execute("create_box", {"width": 80, "depth": 60, "height": 30})
    fc = d.execute("fill_surface", {"feature": b, "edges": {"mode": "cara", "face": "tope"}})
    sh = d.scene[fc].shape
    assert sh.area == pytest.approx(80 * 60, rel=1e-3)
    assert len(sh.solids()) == 0


def test_fill_does_not_mutate_target():
    d = Document()
    b = d.execute("create_box", {"width": 80, "depth": 60, "height": 30})
    vol0 = d.scene[b].shape.volume
    d.execute("fill_surface", {"feature": b, "edges": {"mode": "cara", "face": "tope"}})
    assert d.scene[b].shape.volume == pytest.approx(vol0)  # el sólido sigue intacto


def test_fill_hole_caps_circle():
    d = Document()
    b = d.execute("create_box", {"width": 80, "depth": 60, "height": 30})
    # la caja está centrada en el origen → centro del tope = (0,0,15). Barreno pasante.
    d.execute("drill_hole", {"feature": b, "position": {"x": 0, "y": 0, "z": 15},
                             "axis": "-z", "diameter": 16, "depth": 0})
    fc = d.execute("fill_surface",
                   {"feature": b, "edges": {"mode": "cerca", "point": [0, 0, 15], "count": 1}})
    assert d.scene[fc].shape.area == pytest.approx(math.pi * 8 * 8, rel=5e-2)


def test_fill_tangent_perpendicular_walls_rejected():
    d = Document()
    b = d.execute("create_box", {"width": 80, "depth": 60, "height": 30})
    with pytest.raises(DocumentError, match="(?i)tangent|perpendicular"):
        d.execute("fill_surface", {"feature": b, "tangent": True,
                                   "edges": {"mode": "cara", "face": "tope"}})


# --------------------------------------------------------------------- thicken
def test_thicken_makes_solid_of_expected_volume():
    d = Document()
    s = d.execute("boundary_surface", {"curves": _square_curves(100)})
    d.execute("thicken", {"feature": s, "thickness": 3})
    sh = d.scene[s].shape
    assert sh.volume == pytest.approx(100 * 100 * 3, rel=1e-3)
    assert len(sh.solids()) == 1


def test_thicken_both_doubles_wall():
    d = Document()
    s = d.execute("boundary_surface", {"curves": _square_curves(100)})
    d.execute("thicken", {"feature": s, "thickness": 3, "both": True})
    # both engruesa `thickness` a CADA lado → espesor total 6 mm
    assert d.scene[s].shape.volume == pytest.approx(100 * 100 * 6, rel=1e-3)


def test_thicken_flip_same_volume():
    d = Document()
    s = d.execute("boundary_surface", {"curves": _square_curves(100)})
    d.execute("thicken", {"feature": s, "thickness": 3, "flip": True})
    assert d.scene[s].shape.volume == pytest.approx(100 * 100 * 3, rel=1e-3)


def test_thicken_on_solid_rejected():
    d = Document()
    b = d.execute("create_box", {"width": 50, "depth": 50, "height": 50})
    with pytest.raises(DocumentError, match="(?i)superficie"):
        d.execute("thicken", {"feature": b, "thickness": 2})


def test_thicken_is_parametric():
    d = Document()
    d.execute("set_variable", {"name": "esp", "expression": "4"})
    s = d.execute("boundary_surface", {"curves": _square_curves(100)})
    d.execute("thicken", {"feature": s, "thickness": "=esp"})
    assert d.scene[s].shape.volume == pytest.approx(100 * 100 * 4, rel=1e-3)


# ------------------------------------------ superficie = geometría de construcción
def test_bare_surface_excluded_from_bom_and_mass():
    from apolo.library.bom import bom_from_scene
    from apolo.library.engineering.mass import scene_mass_properties

    d = Document()
    d.execute("create_box", {"name": "Caja acero", "width": 100, "depth": 100, "height": 100})
    d.execute("boundary_surface", {"name": "Deflector", "curves": _square_curves(300, z=200)})
    bom = bom_from_scene(d.scene)
    mass = scene_mass_properties(d.scene)
    assert len(bom) == 1  # solo la caja
    assert all("Deflector" not in (r.get("descripcion") or "") for r in bom)
    assert mass["total"]["n_piezas"] == 1


def test_thickened_surface_enters_bom():
    from apolo.library.bom import bom_from_scene

    d = Document()
    s = d.execute("boundary_surface", {"name": "Pared", "curves": _square_curves(100)})
    assert len(bom_from_scene(d.scene)) == 0  # superficie desnuda: nada
    d.execute("thicken", {"feature": s, "thickness": 3})
    assert len(bom_from_scene(d.scene)) == 1  # ya es pieza fabricable


# ------------------------------------------------------ robustez de la sección
def test_section_survives_surface_in_scene():
    from apolo.drawing.projection import section_projection

    d = Document()
    d.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    d.execute("boundary_surface", {"curves": _square_curves(300, z=200)})
    proj, faces, coord, axis = section_projection(d.scene, axis="x")  # no debe lanzar
    assert axis == "x"


def test_section_only_surface_warns():
    from apolo.drawing.projection import section_projection

    d = Document()
    d.execute("boundary_surface", {"curves": _square_curves(300, z=200)})
    with pytest.raises(ValueError, match="(?i)sólido|thicken|superficie"):
        section_projection(d.scene, axis="x")


# ------------------------------------------------------------------- interop
def test_surface_exports_step():
    from apolo.kernel.io import export_step_file

    d = Document()
    cid = d.execute("boundary_surface", {"curves": _square_curves(100)})
    with tempfile.TemporaryDirectory() as tmp:
        out = str(Path(tmp) / "sup.step")
        export_step_file([d.scene[cid].shape], out)  # no debe lanzar
        assert Path(out).stat().st_size > 0


# ------------------------------------------------------------------- registro
def test_commands_registered_in_superficies_category():
    from apolo.commands.registry import REGISTRY

    for t in ("boundary_surface", "fill_surface", "thicken"):
        assert t in REGISTRY
        assert REGISTRY[t].category == "superficies"
