"""Tests de la memoria de cálculo (Frente A, Fase 6): composición multipágina
+ endpoint /api/calc-report.pdf con fallback a requisitos."""

from __future__ import annotations

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document
from apolo.drawing import sheets_to_pdf
from apolo.drawing.calc_report import calc_report


RULES = [
    {"regla": "flecha del bastidor", "estado": "ok", "detalle": "Flecha 0.2 mm ≤ 5.3 mm.",
     "calc": {"titulo": "Flecha del bastidor",
              "entradas": {"vano L": "1333 mm", "E": "200000 MPa"},
              "formula": "δ = 5·w·L⁴ / (384·E·I)",
              "sustitucion": "δ = 5·0.42·1333⁴ / (384·200000·459000)",
              "resultado": "δ = 0.21 mm", "criterio": "δ ≤ L/250 = 5.33 mm", "fs": 25.4}},
    {"regla": "motorización", "estado": "aviso", "detalle": "Motor justo.",
     "recomendacion": "Sube un tamaño.",
     "calc": {"titulo": "Motorización", "entradas": {"F": "200 N"},
              "formula": "P = F·v/η·margen", "sustitucion": "P = 200·0.35/0.85·1.3",
              "resultado": "P requerida = 0.11 kW", "criterio": "P motor ≥ P requerida",
              "fs": 1.1}},
    {"regla": "apoyo del paquete", "estado": "ok", "detalle": "Soporte continuo por la banda."},
    {"regla": "geometría", "estado": "ok", "detalle": "Altura 800 mm."},
    {"regla": "transportador", "estado": "aviso", "detalle": "Sin paso conocido."},
]

REQ = {"carga_kg": 30.0, "largo_paquete_mm": 600.0, "velocidad_m_s": 0.35,
       "producto": "paquetería"}


def _scene():
    doc = Document("memoria-test")
    doc.execute("create_box", {"name": "Base", "width": 100, "depth": 100, "height": 100})
    return doc.scene


def test_page_count_cover_sections_misc():
    pages = calc_report(_scene(), rules=RULES, requirements=REQ, project_name="Faja 4m")
    # portada + 2 secciones con calc + 1 hoja de cualitativas
    assert len(pages) == 1 + 2 + 1


def test_pdf_bytes():
    pages = calc_report(_scene(), rules=RULES, requirements=REQ)
    pdf = sheets_to_pdf(pages)
    assert pdf[:4] == b"%PDF"


def test_cover_has_design_basis_and_verdict():
    pages = calc_report(_scene(), rules=RULES, requirements=REQ, project_name="Faja 4m")
    texts = [lb.text for lb in pages[0].labels]
    assert any("BASES DE DISEÑO" in t for t in texts)
    assert any("Carga por paquete" in t for t in texts)
    assert any("APROBADO CON AVISOS" in t for t in texts)  # hay avisos, sin errores
    assert any("MEMORIA DE CÁLCULO" in t for t in texts)


def test_verdict_not_conforming_with_error():
    rules = RULES + [{"regla": "par del motor", "estado": "error", "detalle": "Par insuficiente."}]
    pages = calc_report(_scene(), rules=rules, requirements=REQ)
    texts = [lb.text for lb in pages[0].labels]
    assert any("NO CONFORME" in t for t in texts)


def test_section_page_shows_formula_and_fs():
    pages = calc_report(_scene(), rules=RULES, requirements=REQ)
    texts = [lb.text for lb in pages[1].labels]  # 1.ª sección = flecha
    assert any("FÓRMULA" in t for t in texts)
    assert any("δ = 5·w·L⁴" in t for t in texts)
    assert any("FS = 25.4" in t for t in texts)
    assert any("CRITERIO" in t for t in texts)


def test_endpoint_uses_saved_requirements():
    api.DOC = Document("memoria-api")
    api.DOC.execute("create_box", {"name": "Tambor motriz", "width": 114, "depth": 600,
                                   "height": 114, "position": {"x": 0, "y": 0, "z": 400}})
    api.DOC.execute("create_box", {"name": "Larguero 80x40x3", "width": 2000, "depth": 40,
                                   "height": 80, "position": {"x": 0, "y": 300, "z": 300}})
    api.DOC.set_requirements(REQ)
    client = TestClient(api.app)
    r = client.get("/api/calc-report.pdf")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_endpoint_400_without_data():
    api.DOC = Document("memoria-vacia")
    client = TestClient(api.app)
    r = client.get("/api/calc-report.pdf")
    assert r.status_code == 400
    assert "set_requirements" in r.json()["detail"]


# ------------------------------------------------- V5.10: memoria NORMATIVA
def test_norma_de_referencia_en_pagina_y_portada():
    rules = [dict(RULES[0]), {**RULES[1], "calc": {**RULES[1]["calc"],
             "norma": "CEMA (unit handling) — slider bed, μ = 0.30–0.35"}}]
    pages = calc_report(_scene(), rules=rules, requirements=REQ)
    textos = " | ".join(lb.text for p in pages for lb in p.labels)
    assert "NORMA DE REFERENCIA" in textos
    assert "CEMA" in textos
    # portada: línea "Normas aplicadas"
    portada = " | ".join(lb.text for lb in pages[0].labels)
    assert "Normas aplicadas" in portada


def test_reglas_sin_norma_no_pintan_la_linea():
    pages = calc_report(_scene(), rules=RULES, requirements=REQ)  # RULES sin norma
    textos = " | ".join(lb.text for p in pages for lb in p.labels)
    assert "NORMA DE REFERENCIA" not in textos
    assert "Normas aplicadas" not in textos
