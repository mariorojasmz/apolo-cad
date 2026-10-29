"""Los plásticos de máquina pesan lo suyo y un material desconocido AVISA que se pesa como acero
(lavadora de bandejas, 2026-10-29: `set_material('acetal')` aceptaba el texto y pesaba la rueda
dentada 5,6× más; la zapata de «concreto», 3,3×)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apolo.api import main as api
from apolo.doc.document import Document
from apolo.library.apariencia import acabado_de
from apolo.library.materials import DEFAULT_DENSITY, density, known_material


@pytest.mark.parametrize("material, kg_m3", [
    ("acetal", 1410), ("POM", 1410), ("Delrin", 1410), ("UHMW-PE", 930), ("polietileno", 930),
    ("PEAD", 930), ("polipropileno", 905), ("poliamida 6", 1140), ("nylon", 1140)])
def test_plasticos_pesan_lo_suyo(material, kg_m3):
    assert density(material) == pytest.approx(kg_m3 * 1e-9)
    assert known_material(material)


def test_plasticos_se_ven_plasticos():
    assert acabado_de("acetal") == "plastico_blanco"
    assert acabado_de("UHMW-PE") == "plastico_blanco"


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
