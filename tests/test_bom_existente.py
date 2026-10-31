"""Lo EXISTENTE del sitio no se compra (`library/suministro.py`, registro v43): la cubierta
«Calamina existente» sobre la que apoya una estructura de paneles solares y la «Correa delantera
existente» del techo están en la escena (apoyo, gravedad, planos) pero no en la BOM de compra, el
costeo, la lista de corte ni la cédula, y no cuentan en `bom.comprable`. Lo que sólo MENCIONA algo
existente en un complemento lateral se sigue comprando."""

from __future__ import annotations

import pytest

from apolo.doc.document import Document
from apolo.library.bom import bom_from_scene
from apolo.library.calidad.comprable import bom_comprable
from apolo.library.calidad.item import FALLA, OK
from apolo.library.costing import scene_costing
from apolo.library.cutlist import cut_list, hardware_schedule
from apolo.library.designacion_comercial import categoria_de_compra, es_comercial
from apolo.library.suministro import no_suministrada
from apolo.services.calidad_bom import insumo_bom


@pytest.mark.parametrize("nombre", [
    "Calamina existente",
    "Correa delantera existente",
    "Correa delantera existente (2)",
    "Techo existente · Correa (1)",
    "Losa de concreto (existente)",
    "Losa existente de concreto",
    "Tanque (no suministrado)",
    "Viga no suministrada",
    "Mesa del cliente",
    "Mesa de trabajo (del cliente, 2)",
    "Poste del sitio",
    "Tanque por el cliente",
    "Muro (existente en obra)",
])
def test_lo_que_el_nombre_declara_existente(nombre):
    assert no_suministrada(nombre)


@pytest.mark.parametrize("nombre", [
    "Correa de transmisión",
    "Correa en V A-42",
    "Ménsula a correa existente",            # complemento lateral: la ménsula se compra
    "Soporte de calamina existente",
    "Placa de anclaje (sobre losa existente)",
    "Riel de montaje sobre calamina existente",
    "Soporte de la mesa del cliente",
    "Pata · Ménsula para la viga existente",
    "Base del tanque del cliente",           # «del cliente» no sigue a la cabeza
    "Existencias de repuesto",
    "",
    None,
])
def test_lo_que_solo_menciona_algo_existente_se_compra(nombre):
    assert not no_suministrada(nombre)


def test_la_correa_de_techo_no_es_una_banda_y_la_de_transmision_si():
    assert es_comercial("Correa de transmisión") and categoria_de_compra("Correa de transmisión") \
        == "bandas"
    assert es_comercial("Correa trapezoidal perfil SPZ")  # «perfil» de la correa en V
    assert es_comercial("Correa en V Z 32")
    for nombre in ("Correa de techo C100x50", "Correa de la cubierta", "Correa delantera existente"):
        assert not es_comercial(nombre), nombre


def _estructura_solar() -> tuple[Document, dict]:
    """Paneles sobre rieles apoyados en una cubierta existente de calamina con su correa."""
    d = Document("estructura solar")
    ids = {
        "calamina": d.execute("create_box", {"name": "Calamina existente", "width": 2000,
                                             "depth": 1200, "height": 0.5}),
        "correa": d.execute("create_box", {"name": "Correa delantera existente", "width": 2000,
                                           "depth": 50, "height": 100,
                                           "position": {"z": -50.25}}),
        "riel": d.execute("create_box", {"name": "Riel de montaje sobre calamina existente",
                                         "width": 1800, "depth": 40, "height": 40,
                                         "position": {"z": 20.25}}),
        "transmision": d.execute("create_box", {"name": "Correa de transmisión", "width": 300,
                                                "depth": 10, "height": 10,
                                                "position": {"y": 900}}),
    }
    for clave in ("calamina", "correa"):
        d.set_material(ids[clave], "acero zincado")  # sin norma: la BOM pediría designación
    d.set_material(ids["riel"], "acero A36")
    return d, ids


def test_la_estructura_solar_no_compra_lo_existente():
    d, ids = _estructura_solar()
    filas = bom_from_scene(d.scene, d.default_material())
    descr = {r["descripcion"] for r in filas}
    assert "Calamina existente" not in descr and "Correa delantera existente" not in descr
    assert "Riel de montaje sobre calamina existente" in descr  # se compra
    (t,) = [r for r in filas if r["descripcion"].startswith("Correa de transmisión")]
    assert t["ref"] == "COMPRA" and t["categoria"] == "bandas"  # la de transmisión, como siempre
    costeo = {r["descripcion"] for r in scene_costing(d.scene, d.default_material())["rows"]}
    assert not {"Calamina existente", "Correa delantera existente"} & costeo
    corte = {r["nombre"] for r in cut_list(d.scene, d.default_material())}
    assert corte == {"Riel de montaje sobre calamina existente"}
    assert not [r for r in hardware_schedule(d.scene) if "existente" in r["nombre"]]
    assert ids["calamina"] in d.scene and ids["correa"] in d.scene  # siguen en la escena


def test_bom_comprable_no_le_pide_designacion_a_lo_existente():
    d, ids = _estructura_solar()
    ins = insumo_bom(d)
    assert ins["no_suministradas"] == ["Calamina existente", "Correa delantera existente"]
    assert not {m["pieza"] for m in ins["incompletas"]} & {ids["calamina"], ids["correa"]}
    r = bom_comprable({"bom": ins})
    assert r["evidencia"]["no_suministradas"] == {
        "n": 2, "piezas": ["Calamina existente", "Correa delantera existente"]}
    # renombradas como piezas que la máquina suministra, la puerta les pide la designación
    d.scene[ids["calamina"]].name = "Calamina"
    ins = insumo_bom(d)
    assert ins["no_suministradas"] == ["Correa delantera existente"]
    malas = {m["pieza"] for m in ins["incompletas"]}
    assert ids["calamina"] in malas and ids["correa"] not in malas
    assert bom_comprable({"bom": ins})["estado"] == FALLA


def test_sin_existentes_la_evidencia_no_cambia():
    ins = {"filas": 1, "grupos_compra": 0, "grupos_invalidos": [], "incompletas": [],
           "no_suministradas": []}
    r = bom_comprable({"bom": ins})
    assert r["estado"] == OK and "no_suministradas" not in r["evidencia"]
