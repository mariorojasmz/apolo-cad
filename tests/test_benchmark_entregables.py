"""El benchmark y la publicación de tienda piden los MISMOS entregables (plan
publicacion-tienda, F4): la lista vive en `apolo.publicacion.entregables` y
`scripts/benchmark_package.py` la importa.

Se congela lo que el benchmark pedía antes de la extracción (método, ruta, parámetros, cuerpo
y archivo de cada artefacto A2–A6): si alguien cambia un plano para la tienda, el benchmark lo
nota. Un transporte falso de httpx prueba que el recolector escribe esos mismos archivos.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from urllib.parse import parse_qsl

import httpx

from apolo.publicacion import entregables as E

RAIZ = Path(__file__).resolve().parents[1]

_GA = {
    "sheet": "A3", "cutlist": True, "hardware": True, "shaded": True, "assembly_notes": [],
    "format": "pdf",
    "notes": ["Cotas en mm salvo indicación.",
              "Tolerancia general ISO 2768-mK (en cajetín); soldadura ISO 2553 (símbolos en el GA)."],
    "meta": {"drawing_no": "GA-P38-001", "material": "A36 / catálogo",
             "title": "FAJA PAQUETERÍA — CONJUNTO GENERAL"},
}
_RENDER = {"shade": "true", "vtk_only": "true", "zoom": "1.0"}
#: (método, ruta, archivo, query, cuerpo) de cada artefacto A2–A6 del benchmark, tal como los
#: pedía `benchmark_package.py` antes de la extracción.
BENCHMARK_38 = [
    ("GET", "/api/drawingset.pdf", "planos/juego.pdf",
     {"template": "generico", "sheet": "A3", "shaded": "true"}, None),
    ("GET", "/api/drawingset.dwg", "planos/juego_dwg.zip", {"template": "generico", "sheet": "A3"},
     None),
    ("POST", "/api/drawing/spec", "planos/conjunto_GA.pdf", {}, _GA),
    ("GET", "/api/cutlist.json", "planos/cutlist.json", {}, None),
    ("GET", "/api/cutlist.csv", "planos/cutlist.csv", {}, None),
    ("GET", "/api/nesting.json", "planos/nesting_1d_acero.json",
     {"mode": "1d", "stock_w": "6000", "material": "acero", "kerf": "3"}, None),
    ("GET", "/api/calc-report.pdf", "memoria.pdf", {"rev": "A", "sheet": "A4"}, None),
    ("GET", "/api/bom", "bom.json", {"by_group": "true"}, None),
    ("GET", "/api/costing.json", "costeo.json", {}, None),
    ("GET", "/api/quote.pdf", "cotizacion.pdf",
     {"margin_pct": "25", "tax_pct": "13", "currency": "USD"}, None),
    ("GET", "/api/assembly-manual.pdf", "manual.pdf", {"sheet": "A3"}, None),
    ("GET", "/api/export/step", "modelo.step", {}, None),
    ("GET", "/api/render.png", "render/iso.png", {**_RENDER, "view": "iso"}, None),
    ("GET", "/api/render.png", "render/lateral.png", {**_RENDER, "view": "lateral"}, None),
    ("GET", "/api/render.png", "render/planta.png", {**_RENDER, "view": "planta"}, None),
]


def _benchmark():
    previo = sys.dont_write_bytecode  # el script lo apaga para su proceso; aquí se restaura
    spec = importlib.util.spec_from_file_location("benchmark_package",
                                                  RAIZ / "scripts" / "benchmark_package.py")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = previo
    return mod


def test_el_benchmark_usa_la_lista_compartida():
    bench = _benchmark()
    assert bench.E is E  # la misma, no una copia
    pedidos = bench.benchmark_entregables(38, "Faja paquetería")
    assert [e.archivo for e in pedidos] == [x[2] for x in BENCHMARK_38]


def test_el_recolector_pide_y_escribe_lo_mismo_que_antes(tmp_path):
    vistos = []

    def responder(req: httpx.Request) -> httpx.Response:
        cuerpo = json.loads(req.content) if req.content else None
        vistos.append((req.method, req.url.path, dict(parse_qsl(req.url.query.decode())), cuerpo))
        if req.url.path in ("/api/cutlist.json", "/api/nesting.json", "/api/bom",
                            "/api/costing.json"):
            return httpx.Response(200, json={"ruta": req.url.path})
        if req.url.path == "/api/drawingset.dwg":
            return httpx.Response(400, json={"detail": "El export DWG requiere ODA"})
        return httpx.Response(200, content=b"BYTES " + req.url.path.encode())

    cliente = httpx.Client(transport=httpx.MockTransport(responder), base_url="http://apolo")
    rec = E.Recolector(cliente, tmp_path, eco=False)
    registros = rec.traer(_benchmark().benchmark_entregables(38, "Faja paquetería"))
    assert vistos == [(m, r, q, c) for m, r, _a, q, c in BENCHMARK_38]
    escritos = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert escritos == sorted(a for _m, _r, a, _q, _c in BENCHMARK_38 if a != "planos/juego_dwg.zip")
    dwg = next(r for r in registros if r["file"] == "planos/juego_dwg.zip")
    assert dwg["status"] == "error" and dwg["note"] == "400: El export DWG requiere ODA"
    assert json.loads((tmp_path / "bom.json").read_text(encoding="utf-8")) == {"ruta": "/api/bom"}


def test_la_tienda_sale_de_la_misma_lista_y_nunca_trae_precios():
    todos = E.lista(38, "Faja paquetería")
    gratis, completo = E.para(E.GRATIS, todos), E.para(E.COMPLETO, todos)
    assert {e.archivo for e in gratis} == {"planos/conjunto_GA.pdf", "bom.csv", "modelo.step",
                                           "render/iso.png", "render/lateral.png",
                                           "render/planta.png"}
    assert {e.archivo for e in gratis} <= {e.archivo for e in completo}
    for e in (*gratis, *completo):
        assert e.archivo not in E.NUNCA_PUBLICAR, e
    # lo único que la tienda pide y el benchmark no: la BOM resumida en CSV
    assert {e.archivo for e in todos} - {x[2] for x in BENCHMARK_38} == {"bom.csv"}
