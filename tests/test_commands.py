import math

import pytest

from apolo.commands.registry import CommandError, command_schemas
from apolo.doc import Document, DocumentError


@pytest.fixture()
def doc():
    return Document("test")


def test_command_schemas_filtered():
    todos = command_schemas()
    assert len(todos) >= 35
    uno = command_schemas("create_box")
    assert len(uno) == 1 and uno[0]["type"] == "create_box"
    assert "properties" in uno[0]["schema"]
    assert command_schemas("no_existe") == []


def test_pattern_group_arrays_all_features(doc):
    """Arraya TODAS las features de un comando (no solo una). Fuente multi-feature
    fabricada con pattern_linear (count=3 → 2 copias bajo un mismo command_id)."""
    box = doc.execute("create_box", {"width": 50, "depth": 50, "height": 50})
    patt = doc.execute("pattern_linear", {"feature": box, "count": 3, "spacing": {"x": 200}})
    assert len([f for f in doc.scene.values() if f.command_id == patt]) == 2  # fuente = 2 features
    grp = doc.execute("pattern_group", {"source": patt, "count": 3, "spacing": {"y": 500}})
    copies = [fid for fid, f in doc.scene.items() if f.command_id == grp]
    assert len(copies) == 4  # (count=3 → 2 filas extra) × 2 features
    assert all(fid.startswith(grp + "_") for fid in copies)


def test_pattern_group_grid(doc):
    box = doc.execute("create_box", {"width": 50})
    src = doc.execute("pattern_linear", {"feature": box, "count": 2, "spacing": {"x": 200}})  # 1 feature
    grp = doc.execute(
        "pattern_group",
        {"source": src, "count": 2, "spacing": {"x": 1000}, "count2": 2, "spacing2": {"y": 1000}},
    )
    copies = [f for f in doc.scene.values() if f.command_id == grp]
    assert len(copies) == 3  # (2*2 - 1) combinaciones × 1 feature


def test_pattern_group_single_solid_source(doc):
    box = doc.execute("create_box", {"width": 50})
    grp = doc.execute("pattern_group", {"source": box, "count": 4, "spacing": {"x": 100}})
    assert len([f for f in doc.scene.values() if f.command_id == grp]) == 3  # como pattern_linear


def test_pattern_group_unknown_source_errors(doc):
    doc.execute("create_box", {"width": 50})
    with pytest.raises((CommandError, DocumentError)):
        doc.execute("pattern_group", {"source": "cZ", "count": 3, "spacing": {"x": 100}})


def test_pattern_group_blocks_on_joint(doc):
    a = doc.execute("create_box", {"width": 50})
    b = doc.execute("create_box", {"width": 50, "position": {"x": 200}})
    doc.execute("add_joint", {"name": "J1", "type": "giratoria", "parent": a, "child": b})
    with pytest.raises((CommandError, DocumentError)):
        doc.execute("pattern_group", {"source": a, "count": 3, "spacing": {"y": 300}})


def test_pattern_group_zero_spacing_errors(doc):
    box = doc.execute("create_box", {"width": 50})
    with pytest.raises((CommandError, DocumentError)):
        doc.execute("pattern_group", {"source": box, "count": 3, "spacing": {"x": 0, "y": 0, "z": 0}})


def test_pattern_group_preserves_component_for_bom(doc):
    comp = doc.execute("insert_component", {"component": "6000"})
    grp = doc.execute("pattern_group", {"source": comp, "count": 3, "spacing": {"x": 100}})
    copies = [f for f in doc.scene.values() if f.command_id == grp]
    assert copies and all(f.component == "6000" for f in copies)


def test_pattern_group_count_expr(doc):
    doc.execute("set_variable", {"name": "n", "expression": "4"})
    box = doc.execute("create_box", {"width": 50})
    grp = doc.execute("pattern_group", {"source": box, "count": "=n", "spacing": {"x": 100}})
    assert len([f for f in doc.scene.values() if f.command_id == grp]) == 3  # count=4 → 3 copias


def test_create_box_volume(doc):
    fid = doc.execute("create_box", {"width": 100, "depth": 50, "height": 20})
    assert math.isclose(doc.scene[fid].shape.volume, 100 * 50 * 20, rel_tol=1e-6)


def test_create_cylinder_volume(doc):
    fid = doc.execute("create_cylinder", {"radius": 30, "height": 100})
    assert math.isclose(doc.scene[fid].shape.volume, math.pi * 30**2 * 100, rel_tol=1e-3)


def test_structural_profile_bbox_and_volume(doc):
    fid = doc.execute("create_structural_profile", {"profile": "40x40", "length": 500})
    shape = doc.scene[fid].shape
    bb = shape.bounding_box()
    assert math.isclose(bb.max.X - bb.min.X, 40, abs_tol=1e-3)
    assert math.isclose(bb.max.Y - bb.min.Y, 40, abs_tol=1e-3)
    assert math.isclose(bb.max.Z - bb.min.Z, 500, abs_tol=1e-3)
    # con ranuras y taladro debe quedar bastante menos material que el bloque macizo
    assert 0.3 * 40 * 40 * 500 < shape.volume < 0.9 * 40 * 40 * 500


def test_boolean_cut_reduces_volume(doc):
    box = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    cyl = doc.execute("create_cylinder", {"radius": 20, "height": 200})
    result = doc.execute("boolean_op", {"operation": "cut", "target": box, "tools": [cyl]})
    assert box not in doc.scene and cyl not in doc.scene
    expected = 100**3 - math.pi * 20**2 * 100
    assert math.isclose(doc.scene[result].shape.volume, expected, rel_tol=1e-3)


def test_duplicate_feature(doc):
    fid = doc.execute("create_box", {"width": 100, "depth": 100, "height": 100})
    did = doc.execute("duplicate_feature", {"feature": fid, "offset": {"x": 200}})
    assert fid in doc.scene and did in doc.scene and did != fid
    # mismo volumen, desplazada +200 en X
    assert math.isclose(doc.scene[did].shape.volume, doc.scene[fid].shape.volume, rel_tol=1e-6)
    bb = doc.scene[did].shape.bounding_box()
    assert math.isclose((bb.max.X + bb.min.X) / 2, 200, abs_tol=1e-3)
    doc.undo()
    assert did not in doc.scene  # es un comando del log → deshacible


def test_duplicate_preserves_catalog(doc):
    fid = doc.execute("insert_component", {"component": "RODILLO-50", "length": 600})
    did = doc.execute("duplicate_feature", {"feature": fid, "offset": {"y": 100}})
    assert doc.scene[did].component == "RODILLO-50"
    assert doc.scene[did].cut_length == 600


def test_transform_moves_and_rotates(doc):
    fid = doc.execute("create_box", {"width": 100, "depth": 40, "height": 20})
    doc.execute("transform", {"feature": fid, "translate": {"x": 500}, "rotate": {"z": 90}})
    bb = doc.scene[fid].shape.bounding_box()
    # girada 90° en Z: el ancho 100 pasa al eje Y; centrada en x=500
    assert math.isclose(bb.max.Y - bb.min.Y, 100, abs_tol=1e-3)
    assert math.isclose((bb.max.X + bb.min.X) / 2, 500, abs_tol=1e-3)


def test_pattern_linear_creates_copies(doc):
    fid = doc.execute("create_cylinder", {"radius": 25, "height": 60})
    pid = doc.execute("pattern_linear", {"feature": fid, "count": 5, "spacing": {"x": 75}})
    copies = [f for f in doc.scene if f.startswith(f"{pid}_")]
    assert len(copies) == 4 and fid in doc.scene
    last = doc.scene[f"{pid}_4"].shape.bounding_box()
    assert math.isclose((last.max.X + last.min.X) / 2, 300, abs_tol=1e-3)


def _pattern_copies(doc, pid):
    return [f for f in doc.scene if f.startswith(f"{pid}_")]


def test_pattern_count_by_expression_and_cascade(doc):
    """count acepta =expresión y recalcula el nº de copias al cambiar la variable."""
    var = doc.execute("set_variable", {"name": "n", "expression": "5"})
    fid = doc.execute("create_box", {"width": 50, "depth": 50, "height": 50})
    pid = doc.execute("pattern_linear", {"feature": fid, "count": "=n", "spacing": {"x": 100}})
    assert len(_pattern_copies(doc, pid)) == 4  # n=5 → 5 instancias = base + 4
    assert doc.commands[-1]["params"]["count"] == "=n"  # el log conserva la expresión
    doc.edit(var, {"name": "n", "expression": "8"})
    assert len(_pattern_copies(doc, pid)) == 7  # cascada: 8 instancias = base + 7


def test_pattern_count_expression_floors(doc):
    """Una expresión no entera se trunca (floor) a int."""
    doc.execute("set_variable", {"name": "m", "expression": "13/3"})  # 4.33
    fid = doc.execute("create_box", {"width": 50, "depth": 50, "height": 50})
    pid = doc.execute("pattern_linear", {"feature": fid, "count": "=m", "spacing": {"x": 100}})
    assert len(_pattern_copies(doc, pid)) == 3  # floor(4.33)=4 instancias = base + 3


def test_pattern_circular_count_by_expression(doc):
    doc.execute("set_variable", {"name": "n", "expression": "6"})
    fid = doc.execute("create_box", {"width": 30, "depth": 30, "height": 30})
    pid = doc.execute(
        "pattern_circular",
        {"feature": fid, "count": "=n", "axis_point": {"x": 300}, "total_angle": 360},
    )
    assert len(_pattern_copies(doc, pid)) == 5  # 6 instancias = base + 5


def test_pattern_count_expression_below_min_rejected(doc):
    """Si la expresión resuelve por debajo de ge=2, se rechaza (sin clamping silencioso)."""
    doc.execute("set_variable", {"name": "k", "expression": "1"})
    fid = doc.execute("create_box", {"width": 50, "depth": 50, "height": 50})
    with pytest.raises((CommandError, DocumentError)):
        doc.execute("pattern_linear", {"feature": fid, "count": "=k", "spacing": {"x": 100}})


def test_delete_feature(doc):
    fid = doc.execute("create_box", {})
    doc.execute("delete_feature", {"feature": fid})
    assert fid not in doc.scene


def test_invalid_params_rejected(doc):
    with pytest.raises(CommandError):
        doc.execute("create_box", {"width": -5})
    with pytest.raises(CommandError):
        doc.execute("comando_inexistente", {})
    with pytest.raises((CommandError, DocumentError)):
        doc.execute("transform", {"feature": "no_existe"})
    assert doc.commands == []


def test_definitions_lru_touch_and_eviction_order():
    """DEFINITIONS es LRU (V6.1): un HIT (register o touch) reinserta al final; al
    llenar el cap, la evicción saca la MENOS recientemente usada, no la más vieja por
    orden de inserción."""
    import apolo.commands.registry as reg
    from build123d import Box

    saved = dict(reg.DEFINITIONS)
    try:
        reg.DEFINITIONS.clear()
        cap = reg._DEFINITIONS_CAP
        for i in range(cap):
            reg.register_definition(f"k{i}", Box(10 + i * 0.1, 10, 10))
        reg.touch_definition("k0")  # k0 pasa a ser la más reciente
        reg.register_definition("nueva", Box(5, 5, 5))  # evicta la LRU real (k1)
        assert "k0" in reg.DEFINITIONS and "nueva" in reg.DEFINITIONS
        assert "k1" not in reg.DEFINITIONS
        # re-registrar una clave existente también la "toca" (no crece el dict)
        n = len(reg.DEFINITIONS)
        reg.register_definition("k0", Box(1, 1, 1))
        assert len(reg.DEFINITIONS) == n
    finally:
        reg.DEFINITIONS.clear()
        reg.DEFINITIONS.update(saved)
