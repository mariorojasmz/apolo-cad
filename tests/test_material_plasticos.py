"""Los plásticos de máquina pesan lo suyo y un material desconocido AVISA que se pesa como acero
(lavadora de bandejas, 2026-10-29: `set_material('acetal')` aceptaba el texto y pesaba la rueda
dentada 5,6× más; la zapata de «concreto», 3,3×)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from apolo.api import main as api
from apolo.doc.document import Document
from apolo.library.apariencia import acabado_de
from apolo.library.materials import (DEFAULT_DENSITY, _norm, density, known_material,
                                     resolve_material)


@pytest.mark.parametrize("material, kg_m3", [
    ("acetal", 1410), ("POM", 1410), ("Delrin", 1410), ("UHMW-PE", 930), ("polietileno", 930),
    ("PEAD", 930), ("polipropileno", 905), ("poliamida 6", 1140), ("nylon", 1140)])
def test_plasticos_pesan_lo_suyo(material, kg_m3):
    assert density(material) == pytest.approx(kg_m3 * 1e-9)
    assert known_material(material)


def test_plasticos_se_ven_plasticos():
    assert acabado_de("acetal") == "plastico_blanco"
    assert acabado_de("UHMW-PE") == "plastico_blanco"


@pytest.mark.parametrize("texto, clave", [
    ("Guía de nylon", "poliamida"), ("Rueda de poliamida", "poliamida"),
    ("Banda de acetal", "acetal"), ("acero clase 8 con anillo de nylon", "acero"),
    ("acero c/ arandela de nylon", "acero"), ("acero c/arandela de nylon", "acero"),
    ("Rueda de acetal con banda de PU", "acetal"), ("concreto", "concreto")])
def test_el_accesorio_con_no_decide_el_material(texto, clave):
    """Lo que sigue a «con» / «c/» es un accesorio: el material es el de la pieza."""
    assert _norm(texto) == clave


@pytest.mark.parametrize("nombre, material", [
    # la sección de 3 cotas manda a `_norm(nombre)`: antes, el anillo de la DIN 985 la volvía PA
    ("Tuerca 8x13x8 con anillo de nylon", "acero"),
    ("Tuerca autoblocante M8 DIN 985 con anillo de nylon", "acero"),
    ("Perno 8x8x40 con arandela de nylon", "acero"),
    ("Rueda 100x100x30 con banda de poliuretano", "acero"),
    ("Rueda con banda de PU", "acero"),
    ("Rueda con banda de caucho", "acero"),
    ("Rueda de caucho con centro de acero", "caucho"),
    ("Recubrimiento del tambor con poliuretano", "pvc"),  # el forro nombra SU material
    ("Recubrimiento del tambor motriz", "caucho"),
    ("Guía de nylon 30x10x500", "poliamida"),
    ("Rueda de poliamida 100x100x30", "poliamida"),
    ("Banda de acetal 30x10x500", "pvc"),  # rol banda = polímero (regla aparte)
])
def test_resolve_material_ignora_el_accesorio(nombre, material):
    feat = SimpleNamespace(name=nombre, material=None, component=None)
    assert resolve_material(feat, None, "acero") == material
    assert resolve_material(feat) == material


def test_el_acabado_ignora_el_accesorio():
    assert acabado_de("acero clase 8 con anillo de nylon") != "plastico_gris"
    assert acabado_de("nylon con inserto de acero") == "plastico_gris"


def test_desconocido_cae_al_acero_y_se_sabe():
    assert not known_material("unobtainium")
    assert density("unobtainium") == DEFAULT_DENSITY


def test_set_material_avisa_si_no_conoce_el_material():
    api.DOC = Document("t")
    api.DOC.execute("create_box", {"name": "Guía", "width": 10, "depth": 10, "height": 10})
    fid = next(iter(api.DOC.scene))
    c = TestClient(api.app)
    r = c.post("/api/features/material", json={"ids": [fid], "material": "unobtainium"}).json()
    assert "se pesa y se cotiza como acero" in r["aviso_material"]
    r = c.post("/api/features/material", json={"ids": [fid], "material": "acetal"}).json()
    assert "aviso_material" not in r
    r = c.post(f"/api/features/{fid}/material", json={"material": None}).json()
    assert "aviso_material" not in r
