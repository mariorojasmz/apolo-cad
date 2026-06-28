# -*- coding: utf-8 -*-
"""Regresión de las 6 mejoras al MCP/servidor de Apolo (set_variable '=', materiales,
BOM con peso/agrupación, filtro de catálogo, engineering_check de primitivas, eje de
conveniencia). Ejecuta: PYTHONPATH=core python -m pytest core/tests/test_mejoras_mcp.py
"""
from build123d import Box, Cylinder

from apolo.commands.expressions import eval_expression
from apolo.commands.registry import Feature, _orient_axis
from apolo.kernel.shapes import make_cylinder
from apolo.library import rules
from apolo.library.bom import bom_from_scene
from apolo.library.materials import resolve_material


def _feat(name, shape, material=None, fid="x", cid="c"):
    return Feature(fid, name, shape, cid, material=material)


# ----------------------------------------------------------------- #1 expresiones
def test_set_variable_acepta_prefijo_igual():
    assert eval_expression("=10/2", {}) == 5.0
    assert eval_expression("10/2", {}) == 5.0
    assert eval_expression("=d*2", {"d": 3}) == 6.0


# ------------------------------------------------------------------ #2 materiales
def test_seccion_de_acero_gana_sobre_palabra_de_carpinteria():
    # el bug original: "Larguero/Travesaño ... A36" se clasificaba como madera
    assert resolve_material(_feat("Larguero 80x40x3 A36", Box(100, 40, 80)), {}) == "acero"
    assert resolve_material(_feat("Travesaño 40x40x2 A36", Box(40, 760, 40)), {}) == "acero"


def test_carpinteria_sigue_siendo_madera():
    assert resolve_material(_feat("Larguero pino", Box(100, 40, 80)), {}) == "madera"
    assert resolve_material(_feat("Tablero MDF", Box(1200, 600, 18)), {}) == "madera"


def test_override_explicito_gana():
    assert resolve_material(_feat("Caja", Box(10, 10, 10), material="aluminio"), {}) == "aluminio"


def test_default_por_vertical():
    # pieza sin pista: el default lo fija el vertical del proyecto
    assert resolve_material(_feat("Pieza", Box(10, 10, 10)), {}, default="madera") == "madera"
    assert resolve_material(_feat("Pieza", Box(10, 10, 10)), {}, default="acero") == "acero"


# ------------------------------------------------------------------------- #3 BOM
def test_bom_agrupa_identicas_y_calcula_peso():
    scene = {
        "a": Feature("a", "Pata 50x50x2 A36", Box(50, 50, 755), "c1"),
        "b": Feature("b", "Pata 50x50x2 A36", Box(50, 50, 755), "c2"),
    }
    rows = [r for r in bom_from_scene(scene) if r["ref"] == "A-MEDIDA"]
    assert len(rows) == 1
    r = rows[0]
    assert r["cantidad"] == 2
    assert r["material"] == "acero"
    assert r["peso_unitario_kg"] > 0
    assert abs(r["peso_total_kg"] - 2 * r["peso_unitario_kg"]) < 1e-6
    assert r["longitud_mm"] == 755.0


def test_bom_no_mezcla_piezas_distintas():
    scene = {
        "a": Feature("a", "Pieza", Box(50, 50, 100), "c1"),
        "b": Feature("b", "Pieza", Box(50, 50, 200), "c2"),  # mismo nombre, otro tamaño
    }
    rows = [r for r in bom_from_scene(scene) if r["ref"] == "A-MEDIDA"]
    assert len(rows) == 2


def test_bom_colapsa_instancias_de_patron():
    # los sufijos de patrón/espejo/copia se ignoran -> una sola fila con la cantidad
    names = [
        "Perno M12", "Perno M12 (1,2)", "Perno M12 (2,1)",
        "Perno M12 (espejo)", "Perno M12 (espejo) (copia)",
    ]
    scene = {str(i): Feature(str(i), n, Box(20, 20, 60), f"c{i}") for i, n in enumerate(names)}
    rows = [r for r in bom_from_scene(scene) if r["ref"] == "A-MEDIDA"]
    assert len(rows) == 1
    assert rows[0]["cantidad"] == 5
    assert rows[0]["descripcion"] == "Perno M12"


# ----------------------------------------------------------- #5 engineering_check
def _faja_primitivas():
    return {
        "d": Feature("d", "Tambor cola Ø114", Cylinder(57, 760), "c"),
        "l": Feature("l", "Larguero 80x40x3 A36", Box(4000, 40, 80), "c"),
        "b": Feature("b", "Banda PVC 2mm", Box(3900, 700, 2), "c"),
    }


def test_detecta_faja_de_primitivas_por_nombre():
    det = rules.detect_conveyor(_faja_primitivas())
    assert det is not None
    assert det["tipo"] == "banda"
    assert det["tambor_d"] == 114.0
    assert det["largo"] == 4000.0
    assert det["ancho"] == 700.0


def test_infiere_faja_de_ids_explicitos():
    inf = rules.infer_from_solids(_faja_primitivas(), ["d", "l", "b"])
    assert inf is not None
    assert inf["largo"] > 0 and inf["ancho"] > 0


def test_no_inventa_faja_en_escena_no_faja():
    escena = {"x": Feature("x", "Mesa de comedor", Box(1000, 600, 30), "c")}
    assert rules.detect_conveyor(escena) is None


# ------------------------------------------------------------------------ #6 axis
def test_cilindro_a_lo_largo_de_y():
    bb = _orient_axis(make_cylinder(25, 100), "y").bounding_box()
    assert round(bb.max.Y - bb.min.Y) == 100
    assert round(bb.max.X - bb.min.X) == 50


def test_cilindro_a_lo_largo_de_x():
    bb = _orient_axis(make_cylinder(25, 100), "x").bounding_box()
    assert round(bb.max.X - bb.min.X) == 100
    assert round(bb.max.Z - bb.min.Z) == 50


def test_eje_z_por_defecto_sin_cambios():
    bb = _orient_axis(make_cylinder(25, 100), "z").bounding_box()
    assert round(bb.max.Z - bb.min.Z) == 100
