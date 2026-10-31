"""Ficha del encargo en los requisitos (plan revision-de-taller, F2: D1).

Las claves (`carga_kg`, `ancho_producto_mm`, `desarmable`, `plegable` —plegables-en-la-puerta
D1—, `instalacion`, `entorno`) se
validan; lo que el agente supone entra como `{"valor": …, "asumido": true}` y se guarda plano
más la lista `asumidos` (los lectores de `requirements[...]` siguen viendo un escalar). Es
metadato: nunca entra al log. Un manifest viejo sin esas claves abre igual, y el briefing de
`open_project` dice qué falta y qué está asumido.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document, DocumentError
from apolo.drawing.calc_report import _req_rows
from apolo.library.requisitos import FICHA, estado_ficha, normalizar_requisitos


def test_ficha_completa_se_normaliza():
    req = normalizar_requisitos({
        "carga_kg": "15", "ancho_producto_mm": 450, "desarmable": "sí",
        "instalacion": "Movil", "entorno": "interior, polvo",
    })
    assert req == {"carga_kg": 15.0, "ancho_producto_mm": 450.0, "desarmable": True,
                   "instalacion": "móvil", "entorno": "interior, polvo"}


@pytest.mark.parametrize("fields", [
    {"ancho_producto_mm": 0},
    {"ancho_producto_mm": "ancho"},
    {"desarmable": "a veces"},
    {"instalacion": "colgada"},
    {"entorno": 3},
    {"carga_kg": True},
    {"carga_kg": {"valor": 15, "asumido": True, "por": "mí"}},
    {"carga_kg": {"asumido": True}},
    {"asumidos": {"carga_kg": True}},
])
def test_valores_invalidos_se_rechazan_con_documenterror(fields):
    with pytest.raises(DocumentError):
        Document("t").set_requirements(fields)


def test_asumido_se_guarda_plano_mas_la_lista():
    doc = Document("t")
    doc.set_requirements({
        "carga_kg": {"valor": 15, "asumido": True},
        "instalacion": {"valor": "piso", "asumido": True},
        "desarmable": {"valor": False, "asumido": False},
        "producto": "cajas",
    })
    assert doc.requirements == {"carga_kg": 15.0, "instalacion": "piso", "desarmable": False,
                                "producto": "cajas", "asumidos": ["carga_kg", "instalacion"]}


def test_asumidos_entra_como_lista_o_como_texto_del_panel():
    """El panel Requisitos reenvía cada valor como texto: la lista vuelve como «a,b»."""
    a = normalizar_requisitos({"carga_kg": 15, "entorno": "x", "asumidos": ["carga_kg"]})
    b = normalizar_requisitos({"carga_kg": "15", "entorno": "x", "asumidos": "carga_kg"})
    assert a == b == {"carga_kg": 15.0, "entorno": "x", "asumidos": ["carga_kg"]}
    # una marca sin su valor no marca nada; sin marcas no hay lista
    assert normalizar_requisitos({"entorno": "x", "asumidos": "carga_kg"}) == {"entorno": "x"}


def test_la_ficha_no_entra_al_log_y_viaja_en_el_apolo():
    doc = Document("t")
    doc.set_requirements({"carga_kg": {"valor": 15, "asumido": True}, "desarmable": True})
    assert doc.commands == []
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert doc2.requirements == {"carga_kg": 15.0, "desarmable": True, "asumidos": ["carga_kg"]}


def _con_requisitos_viejos(requisitos: dict) -> bytes:
    """Un `.apolo` cuyo manifest trae requisitos escritos antes de la ficha."""
    src = io.BytesIO(Document("viejo").to_apolo_bytes())
    out = io.BytesIO()
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "manifest.json":
                manifest = json.loads(data)
                manifest["requirements"] = requisitos
                data = json.dumps(manifest).encode()
            zout.writestr(item, data)
    return out.getvalue()


def test_manifest_viejo_sin_ficha_abre_igual():
    viejo = {"carga_kg": 30.0, "largo_paquete_mm": 600.0, "producto": "paquetería"}
    doc = Document.from_apolo_bytes(_con_requisitos_viejos(viejo))
    assert doc.requirements == viejo
    assert estado_ficha(doc.requirements) == {
        "faltan": ["ancho_producto_mm", "desarmable", "plegable", "instalacion", "entorno"],
        "asumidos": [], "como": estado_ficha({})["como"]}


def test_manifest_viejo_con_valores_libres_no_se_revalida_al_abrir():
    """La carga no valida: un texto libre de antes (instalación «en el almacén») se abre tal
    cual; sólo un set_requirements nuevo lo exige en forma."""
    viejo = {"instalacion": "en el almacén", "desarmable": "a veces", "asumidos": "raro"}
    doc = Document.from_apolo_bytes(_con_requisitos_viejos(viejo))
    assert doc.requirements == viejo
    estado = estado_ficha(doc.requirements)
    assert estado["asumidos"] == [] and "instalacion" not in estado["faltan"]


def test_estado_ficha_completa_no_trae_como():
    req = normalizar_requisitos({k: v for k, v in zip(FICHA, (15, 450, "no", "no", "anclado",
                                                               "x"))}
                                | {"asumidos": ["entorno"]})
    assert estado_ficha(req) == {"faltan": [], "asumidos": ["entorno"]}


def test_el_briefing_de_open_project_trae_la_ficha():
    api.DOC = Document("briefing")
    api.DOC.set_requirements({"carga_kg": {"valor": 15, "asumido": True}, "entorno": "interior"})
    b = api._open_briefing()
    assert b["requisitos"]["asumidos"] == ["carga_kg"]
    assert b["ficha"]["faltan"] == ["ancho_producto_mm", "desarmable", "plegable", "instalacion"]
    assert b["ficha"]["asumidos"] == ["carga_kg"]
    assert "asumido" in b["ficha"]["como"]


def test_endpoint_rechaza_con_400_y_acepta_la_forma_asumida():
    api.DOC = Document("req")
    client = TestClient(api.app)
    r = client.put("/api/requirements", json={"fields": {"instalacion": "colgada"}})
    assert r.status_code == 400 and "piso" in r.json()["detail"]
    r = client.put("/api/requirements",
                   json={"fields": {"ancho_producto_mm": {"valor": 500, "asumido": True}}})
    assert r.status_code == 200
    assert r.json()["requirements"] == {"ancho_producto_mm": 500.0,
                                        "asumidos": ["ancho_producto_mm"]}


def test_la_memoria_marca_lo_asumido():
    filas = _req_rows({"carga_kg": 15.0, "desarmable": False, "asumidos": ["carga_kg"]})
    assert filas == ["Carga por paquete:  15 kg  (asumido)", "Desarmable:  no"]
