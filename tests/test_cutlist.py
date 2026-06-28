"""Fase D · lista de corte, cédula de herraje y nesting."""

from apolo.doc import Document
from apolo.library.cutlist import cut_list, cut_list_totals, hardware_schedule
from apolo.library.nesting import nest_1d, nest_2d, waste_2d


def test_cut_list_splits_union_into_solids():
    """Una hoja = unión de 2 largueros (compound) → la lista de corte cuenta 2 tablas."""
    doc = Document()
    a = doc.execute("create_box", {"name": "larguero izq", "width": 100, "depth": 18, "height": 2000, "position": {"x": -200}})
    b = doc.execute("create_box", {"name": "larguero der", "width": 100, "depth": 18, "height": 2000, "position": {"x": 200}})
    doc.execute("boolean_op", {"name": "Hoja", "operation": "union", "target": a, "tools": [b]})
    rows = cut_list(doc.scene)
    larg = next(r for r in rows if sorted((r["espesor_mm"], r["ancho_mm"], r["largo_mm"])) == [18.0, 100.0, 2000.0])
    assert larg["cantidad"] == 2
    assert larg["material"] == "madera"


def test_cut_list_groups_identical_and_totals():
    doc = Document()
    for i in range(3):
        doc.execute("create_box", {"name": f"travesano {i}", "width": 500, "depth": 18, "height": 100, "position": {"z": i * 300}})
    doc.execute("create_box", {"name": "Vidrio panel", "width": 300, "depth": 8, "height": 1800})
    rows = cut_list(doc.scene)
    trav = next(r for r in rows if r["material"] == "madera")
    assert trav["cantidad"] == 3
    totals = cut_list_totals(rows)
    assert "madera" in totals and "vidrio" in totals
    assert totals["madera"]["piezas"] == 3


def test_hardware_schedule_lists_catalog_hardware():
    doc = Document()
    doc.execute("create_box", {"name": "tabla", "width": 200, "depth": 18, "height": 400})
    doc.execute("insert_component", {"component": "CORR-D100"})  # corredera (no cortable)
    hw = hardware_schedule(doc.scene)
    assert any(r["ref"] == "CORR-D100" for r in hw)
    # la corredera NO aparece en la lista de corte (es herraje)
    assert all(r["material"] != "" for r in cut_list(doc.scene))


def test_nest_1d_respects_stock_no_overlap():
    bars = nest_1d([1200, 1200, 800, 800, 500], stock_len=2440, kerf=3)
    for bar in bars:
        end = -1.0
        for off, length in bar:
            assert off >= end - 1e-9
            assert off + length <= 2440 + 1e-6
            end = off + length


def test_nest_2d_no_overlap_and_in_stock():
    rects = [(600, 400), (600, 400), (300, 300), (300, 300), (700, 500)]
    sheets = nest_2d(rects, 2440, 1220, kerf=3)
    for placed in sheets:
        for (x, y, w, h) in placed:
            assert 0 <= x and x + w <= 2440 + 1e-6
            assert 0 <= y and y + h <= 1220 + 1e-6
        for i in range(len(placed)):
            for j in range(i + 1, len(placed)):
                x1, y1, w1, h1 = placed[i]
                x2, y2, w2, h2 = placed[j]
                sep = (x1 + w1 <= x2 + 1e-6 or x2 + w2 <= x1 + 1e-6
                       or y1 + h1 <= y2 + 1e-6 or y2 + h2 <= y1 + 1e-6)
                assert sep, "rectángulos solapados en el nesting"
    assert 0 <= waste_2d(sheets, 2440, 1220) <= 100
