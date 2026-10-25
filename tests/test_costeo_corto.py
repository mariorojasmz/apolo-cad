"""Leer el costo sin volcar el costeo entero (`services/costeo_corto.py`, `quote.resumen_precio`).

- `GET /api/costing.json` sin parámetros es el costeo de siempre (byte-idéntico); `resumen=true`
  deja todo menos las filas (+ `n_filas`); `categoria` deja las filas de esa categoría (+ `filtro`
  con su suma); una categoría que no está es 400 con las que hay.
- `GET /api/quote.pdf` manda el resumen económico (costo directo, margen, impuesto, precio de
  venta) en `X-Apolo-Precio`, con las MISMAS cifras que rotula la hoja de resumen; la tool
  `quotation` las devuelve junto al path.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from tablero_electrico import arranque_variador_plc

import apolo.api.main as api
from apolo.doc.document import Document
from apolo.drawing.quote import precio_de_venta, quotation_pages, resumen_precio
from apolo.services.cobros import costeo
from apolo.services.costeo_corto import acotar
from apolo.services.errors import ServiceError
from apolo.tools.entregable import precio_de


@pytest.fixture
def doc() -> Document:
    d = Document("costeo-corto")
    d.execute("insert_component", {"component": "VFD-2K2-220", "name": "Variador de frecuencia"})
    d.execute_many(arranque_variador_plc())
    return d


def test_sin_filtros_el_costeo_de_siempre(doc, monkeypatch):
    monkeypatch.setattr(api, "DOC", doc)
    r = TestClient(api.app).get("/api/costing.json")
    assert r.json() == json.loads(json.dumps(costeo(doc)))
    assert acotar(costeo(doc)) == costeo(doc)


def test_resumen_sin_filas(doc, monkeypatch):
    monkeypatch.setattr(api, "DOC", doc)
    entero = costeo(doc)
    corto = TestClient(api.app).get("/api/costing.json", params={"resumen": "true"}).json()
    assert "rows" not in corto and corto["n_filas"] == len(entero["rows"])
    assert corto["totales"] == entero["totales"] and corto["avisos"] == entero["avisos"]
    assert corto["monto_en_riesgo_usd"] == entero["monto_en_riesgo_usd"]
    assert len(json.dumps(corto)) < len(json.dumps(entero)) / 3


def test_una_categoria(doc, monkeypatch):
    monkeypatch.setattr(api, "DOC", doc)
    entero = costeo(doc)
    cat, total = next(iter(entero["totales"]["por_categoria"].items()))
    c = TestClient(api.app)
    js = c.get("/api/costing.json", params={"categoria": cat.upper()}).json()
    assert js["rows"] and all((r.get("categoria") or "otros") == cat for r in js["rows"])
    assert js["filtro"]["categoria"] == cat and js["filtro"]["total_usd"] == pytest.approx(total)
    assert js["filtro"]["n_filas"] == len(js["rows"]) and js["totales"] == entero["totales"]
    # con resumen: el filtro de la categoría, sin filas
    js = c.get("/api/costing.json", params={"categoria": cat, "resumen": "true"}).json()
    assert "rows" not in js and js["filtro"]["total_usd"] == pytest.approx(total)
    r = c.get("/api/costing.json", params={"categoria": "inexistente"})
    assert r.status_code == 400 and "categoría «inexistente» no está" in r.json()["detail"]
    assert cat in r.json()["detail"]


def test_categoria_inexistente_en_un_costeo_vacio():
    with pytest.raises(ServiceError, match=r"categorías: \(ninguna\)"):
        acotar({"rows": [], "totales": {}}, categoria="x")


def test_el_precio_es_el_de_la_hoja_de_resumen(doc, monkeypatch):
    monkeypatch.setattr(api, "DOC", doc)
    r = TestClient(api.app).get("/api/quote.pdf", params={"margin_pct": 30, "tax_pct": 18})
    precio = json.loads(r.headers["X-Apolo-Precio"])
    directo = costeo(doc)["totales"]["total_usd"]
    p = precio_de_venta(directo, 30, 18)
    assert precio == {"moneda": "USD", "costo_directo": round(directo, 2), "margen_pct": 30.0,
                      "margen": round(p["margen"], 2), "impuesto_pct": 18.0,
                      "impuesto": round(p["impuesto"], 2), "precio_venta": round(p["precio_venta"], 2)}
    # la hoja de resumen rotula esas mismas cifras
    hoja = quotation_pages(doc.scene, margin_pct=30, tax_pct=18, costeo=costeo(doc))[0]
    textos = [lb.text for lb in hoja.labels]
    assert f"{precio['precio_venta']:,.2f} USD" in textos and f"{precio['margen']:,.2f} USD" in textos
    # la tool la devuelve tal cual
    assert precio_de(SimpleNamespace(headers=r.headers)) == {"precio": precio}
    assert precio_de(SimpleNamespace(headers={})) == {}


def test_el_precio_en_otra_moneda_y_sin_impuesto(doc):
    data = costeo(doc)
    p = resumen_precio(data, margin_pct=25, tax_pct=0, currency="PEN", fx=3.7)
    assert p["moneda"] == "PEN" and p["tipo_cambio"] == 3.7 and "impuesto" not in p
    assert p["costo_directo"] == round(data["totales"]["total_usd"] * 3.7, 2)
    hoja = quotation_pages(doc.scene, currency="PEN", fx=3.7, costeo=data)[0]
    assert f"{p['precio_venta']:,.2f} PEN" in [lb.text for lb in hoja.labels]
