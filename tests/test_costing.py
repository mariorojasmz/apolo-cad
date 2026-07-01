"""Tests del Frente B: costeo (costing.py), endpoint /api/costing.json y
cotización PDF (quote.py + /api/quote.pdf)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document
from apolo.drawing import sheets_to_pdf
from apolo.drawing.quote import quotation_pages
from apolo.library.catalog import CATALOG
from apolo.library.costing import FAB_FACTOR, HW_FACTOR, costed_bom, costing_totals, scene_costing
from apolo.library.materials import cost_per_kg


def _doc() -> Document:
    doc = Document("costing-test")
    doc.execute("insert_component", {"component": "NMRV-090", "position": {"x": 0, "y": 0, "z": 0}})
    doc.execute("insert_component", {"component": "UCP207", "position": {"x": 300, "y": 0, "z": 0}})
    doc.execute("insert_component", {"component": "UCP207", "position": {"x": 600, "y": 0, "z": 0}})
    doc.execute("create_box", {"name": "Placa base A36", "width": 200, "depth": 200,
                               "height": 10, "position": {"x": 0, "y": 400, "z": 5}})
    return doc


def _row(rows, ref):
    return next(r for r in rows if r["ref"] == ref)


# ---------------------------------------------------------------- costed_bom
def test_catalog_cost_from_specs():
    rows = costed_bom(_doc().scene)
    nmrv = _row(rows, "NMRV-090")
    assert nmrv["costo_ud_usd"] == 520.0
    assert nmrv["costo_fuente"] == "catálogo"
    ucp = _row(rows, "UCP207")
    assert ucp["cantidad"] == 2
    assert ucp["costo_total_usd"] == pytest.approx(2 * 18.0)


def test_custom_piece_cost_by_material_factor():
    rows = costed_bom(_doc().scene)
    placa = _row(rows, "A-MEDIDA")
    # 200×200×10 acero = 3.14 kg → 3.14 × 1.5 USD/kg × 2.5
    expected = placa["peso_unitario_kg"] * cost_per_kg("acero") * FAB_FACTOR
    assert placa["costo_ud_usd"] == pytest.approx(expected, rel=1e-3)
    assert "fabricación" in placa["costo_fuente"]


def test_hardware_without_price_estimates_with_floor():
    doc = Document("t")
    doc.execute("insert_component", {"component": "6305", "position": {"x": 0, "y": 0, "z": 0}})
    rows = costed_bom(doc.scene)
    r = _row(rows, "6305")
    assert r["costo_ud_usd"] is not None and r["costo_ud_usd"] >= 0.5
    assert "estimado" in r["costo_fuente"]
    assert str(HW_FACTOR) in r["costo_fuente"] or f"{HW_FACTOR:g}" in r["costo_fuente"]


def test_totals_and_most_expensive():
    data = scene_costing(_doc().scene)
    t = data["totales"]
    assert t["total_usd"] == pytest.approx(t["catalogo_usd"] + t["fabricacion_usd"], abs=0.05)
    assert t["item_mas_costoso"]["ref"] == "NMRV-090"
    assert t["por_categoria"]["motorreductores_sinfin"] == 520.0


def test_cuttable_component_costs_per_meter():
    doc = Document("t")
    doc.execute("insert_component", {"component": "TUBO-2X2", "position": {"x": 0, "y": 0, "z": 0},
                                     "length": 2000})
    rows = costed_bom(doc.scene)
    r = rows[0]
    # sin precio explícito: estimación por peso (que ya viene por longitud) — nunca None
    assert r["costo_ud_usd"] is not None and r["costo_ud_usd"] > 0


# ------------------------------------------------------------------ endpoint
def test_costing_endpoint():
    api.DOC = _doc()
    client = TestClient(api.app)
    r = client.get("/api/costing.json")
    assert r.status_code == 200
    data = r.json()
    assert data["totales"]["total_usd"] > 500
    assert all("costo_fuente" in row for row in data["rows"])


# ---------------------------------------------------------------- cotización
def test_quotation_pages_and_pdf():
    doc = _doc()
    pages = quotation_pages(doc.scene, project_name="Faja 4m",
                            requirements={"producto": "paquetería"}, margin_pct=25)
    assert len(pages) >= 2  # resumen + ≥1 detalle
    texts = [lb.text for lb in pages[0].labels]
    assert any("COTIZACIÓN" in t for t in texts)
    assert any("PRECIO DE VENTA" in t for t in texts)
    assert any("REFERENCIALES" in t for t in texts)  # nota de honestidad
    assert sheets_to_pdf(pages)[:4] == b"%PDF"


def test_quotation_margin_math():
    doc = _doc()
    data = scene_costing(doc.scene)
    directo = data["totales"]["total_usd"]
    pages = quotation_pages(doc.scene, margin_pct=20, tax_pct=18)
    texts = [lb.text for lb in pages[0].labels]
    venta = directo * 1.20 * 1.18
    assert any(f"{venta:,.2f}" in t for t in texts)


def test_quote_endpoint():
    api.DOC = _doc()
    client = TestClient(api.app)
    r = client.get("/api/quote.pdf", params={"margin_pct": 30, "currency": "USD"})
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


# ---------------------------------------------------- Frente C: moneda / fx / cost_por_m
def test_requirements_accept_currency_and_fx():
    doc = Document("t")
    doc.set_requirements({"carga_kg": 10, "largo_paquete_mm": 400,
                          "moneda": "PEN", "tipo_cambio": 3.75})
    assert doc.requirements["moneda"] == "PEN"
    assert doc.requirements["tipo_cambio"] == 3.75


def test_quote_fx_scales_amounts():
    doc = _doc()
    data = scene_costing(doc.scene)
    directo = data["totales"]["total_usd"]
    pages = quotation_pages(doc.scene, margin_pct=0, tax_pct=0, currency="PEN", fx=3.75)
    texts = [lb.text for lb in pages[0].labels]
    assert any(f"{directo * 3.75:,.2f} PEN" in t for t in texts)
    assert any("tipo de cambio 3.75" in t for t in texts)  # nota de conversión


def test_quote_endpoint_uses_project_currency():
    api.DOC = _doc()
    api.DOC.set_requirements({"carga_kg": 10, "largo_paquete_mm": 400,
                              "moneda": "PEN", "tipo_cambio": 3.75})
    client = TestClient(api.app)
    r = client.get("/api/quote.pdf")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_cuttable_profile_uses_cost_por_m():
    doc = Document("t")
    doc.execute("insert_component", {"component": "TUBO-2X2", "position": {"x": 0, "y": 0, "z": 0},
                                     "length": 2000})
    rows = costed_bom(doc.scene)
    r = rows[0]
    assert r["costo_fuente"] == "catálogo (USD/m)"
    from apolo.library.catalog import CATALOG
    expected = CATALOG["TUBO-2X2"].specs["cost_por_m"] * 2.0
    assert r["costo_ud_usd"] == pytest.approx(expected, rel=1e-6)


def test_export_stl_endpoint():
    api.DOC = Document("stl-test")
    api.DOC.execute("create_box", {"name": "Caja", "width": 50, "depth": 50, "height": 50})
    client = TestClient(api.app)
    r = client.get("/api/export/stl")
    assert r.status_code == 200
    # STL binario: 80 bytes de header + uint32 con nº de triángulos (>0)
    assert len(r.content) > 84
    import struct
    n_tri = struct.unpack("<I", r.content[80:84])[0]
    assert n_tri >= 12  # una caja tesela a >=12 triángulos
