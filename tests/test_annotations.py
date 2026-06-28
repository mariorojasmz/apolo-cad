"""Fase 5 · anotaciones / GD&T ligero: bloque de notas, acabado, datum, marco de control."""

from apolo.doc import Document
from apolo.drawing import compose_sheet
from apolo.drawing.dimensions import datum_flag, feature_control_frame, notes_block, surface_finish
from apolo.drawing.sheet import SheetModel


def test_notes_block_emits_title_and_numbered_lines():
    m = SheetModel(420, 297)
    notes_block(m, 10, 200, ["Romper aristas vivas", "Material certificado"])
    texts = [l.text for l in m.labels]
    assert "NOTAS" in texts
    assert any("Romper aristas" in t for t in texts)
    assert any(t.startswith("1.") for t in texts) and any(t.startswith("2.") for t in texts)


def test_gdt_primitives_draw():
    m = SheetModel(420, 297)
    surface_finish(m, 50, 50, 3.2)
    datum_flag(m, 80, 50, "A")
    w = feature_control_frame(m, 100, 50, "POS", "0.2", ("A", "B"))
    texts = [l.text for l in m.labels]
    assert any("Ra 3.2" in t for t in texts)            # símbolo de acabado
    assert "A" in texts and "POS" in texts and "0.2" in texts  # datum + marco de control
    assert w > 0
    assert sum(1 for l in m.lines if l.kind == "frame") >= 4  # recuadros del datum + FCF


def test_compose_sheet_with_notes():
    doc = Document()
    doc.execute("create_box", {"name": "pieza", "width": 200, "depth": 100, "height": 30})
    texts = [l.text for l in compose_sheet(doc.scene, notes=["Tolerancia general ±0.5", "Romper cantos"]).labels]
    assert "NOTAS" in texts and any("Romper cantos" in t for t in texts)


def _doc_con_herraje() -> Document:
    doc = Document()
    doc.execute("create_box", {"name": "tabla", "width": 300, "depth": 18, "height": 1200})
    doc.execute("insert_component", {"component": "BIS-H-75-A", "position": {"x": 0, "y": 0, "z": 0}})
    doc.execute("insert_component", {"component": "BIS-H-75-A", "position": {"x": 0, "y": 0, "z": 400}})
    return doc


def test_assembly_notes_auto_seed_from_hardware():
    """assembly_notes=[] auto-genera el bloque NOTAS DE MONTAJE desde la cédula de herraje."""
    doc = _doc_con_herraje()
    texts = [l.text for l in compose_sheet(doc.scene, assembly_notes=[]).labels]
    assert "NOTAS DE MONTAJE" in texts                       # título del bloque
    assert any("BIS-H-75-A" in t and "EN 1935" in t for t in texts)  # nota con norma
    assert any("explosionada" in t for t in texts)           # remite a la secuencia


def test_assembly_notes_explicit_and_off():
    doc = _doc_con_herraje()
    # explícitas: el usuario sobrescribe la auto-semilla
    texts = [l.text for l in compose_sheet(doc.scene, assembly_notes=["Aplicar Loctite 243"]).labels]
    assert "NOTAS DE MONTAJE" in texts and any("Loctite" in t for t in texts)
    assert not any("BIS-H-75-A" in t for t in texts)         # no auto-semilla cuando hay explícitas
    # None (por defecto) → sin bloque de montaje
    assert "NOTAS DE MONTAJE" not in [l.text for l in compose_sheet(doc.scene).labels]
