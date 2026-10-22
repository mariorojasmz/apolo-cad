"""F6 de la puerta de publicación — la BOM de la tornillería y los comerciales (revisores ciegos
de las fajas de la tienda, proyectos 6 y 7):

1. una pieza COMERCIAL modelada a mano («Perno M8x20 DIN 933 …», «Anillo seeger DIN 472-52»,
   «Silentblock …») sale en la categoría de COMPRA del catálogo (ref `COMPRA`), no en «a medida»,
   en BOM, costeo y cédula; lo que se fabrica no cambia;
2. el perno tensor de `create_take_up` (geometría Allen con ficha hexagonal PERNO-HEX-M12) salía
   L = 84,5 (80 + k Allen 12 − k hex 7,5): la BOM pone el NOMINAL (80); un largo medido que no es
   de la serie, el inmediato superior con aviso;
3. el seeger del tensor es «Anillo Seeger DIN 472-52» (comercial, sin medida de corte);
4. el perno de cuello cuadrado DIN 603 existe en el catálogo (M6–M12) con su tuerca.
"""

from dataclasses import dataclass

import pytest
from build123d import Box, Cylinder

from apolo.doc import Document
from apolo.library.bom import bom_from_scene
from apolo.library.builders import hex_bolt
from apolo.library.catalog import CATALOG, catalog_payload
from apolo.library.costing import costing_totals, costed_bom
from apolo.library.cutlist import cut_list, hardware_schedule
from apolo.library.designacion_comercial import (
    categoria_de_compra, es_comercial, nombre_de_compra, norma_del_nombre,
)
from apolo.library.largo_tornilleria import largo_de_compra_con_aviso


@dataclass
class _F:
    name: str
    shape: object = None
    material: str | None = None
    component: str | None = None
    visible: bool = True
    cut_length: float | None = None
    is_guide: bool = False


# ── 1 · comerciales a mano → categoría de compra ─────────────────────────────────────────


@pytest.mark.parametrize("nombre,categoria", [
    ("Perno M8x20 DIN 933 guarda sup. drive (+X, +Y, inf)", "pernos"),
    ("Tornillo M8x30 tensor de cola", "pernos"),
    ("Tuerca M8 DIN 934", "tuercas"),
    ("Arandela cuña DIN 434 M8 (guarda cabeza +Y, 1)", "tornilleria"),
    ("Anillo seeger DIN 472-52 (+Y)", "tornilleria"),
    ("Tambor de cabeza · Seeger retención", "tornilleria"),
    ("Silentblock M8 Ø30x20 del motor", "comerciales"),
    ("Banda PVC 2 capas", "bandas"),
    ("Rodamiento 6205 (+Y)", "rodamientos"),
])
def test_comercial_a_mano_y_su_categoria(nombre, categoria):
    assert es_comercial(nombre)
    assert categoria_de_compra(nombre) == categoria


@pytest.mark.parametrize("nombre", [
    "Placa base de pata (cola, +Y)",
    "Placa (taladros M12) ISO 2768-mK",          # norma de PLANO aunque traiga una rosca
    "Canal de refuerzo M12 DIN 1026-1",           # norma de PERFIL: se corta de barra
    "Eje fijo de cola Ø25 g6 (roscado p/ perno)",
    "Tapa porta-rodamiento del tambor de cola (+Y)",
    "Buje elástico de caucho del brazo de reacción",
])
def test_lo_que_se_fabrica_no_es_comercial(nombre):
    assert not es_comercial(nombre)


def test_nombre_de_compra_quita_la_ubicacion_solo_con_norma():
    assert nombre_de_compra("Arandela cuña DIN 434 M8 (guarda cabeza +Y, 1)") == \
        "Arandela cuña DIN 434 M8"
    # sin norma, el paréntesis puede ser la especificación: se queda
    banda = "Banda PVC 2 capas con empalme mecánico (grapas articuladas)"
    assert nombre_de_compra(banda) == banda
    assert norma_del_nombre("Placa (taladros M12) ISO 2768-mK") == ""


def _escena_comerciales():
    return {
        "p1": _F("Perno M8x20 DIN 933 guarda sup. drive (+X, +Y, inf)", Cylinder(4, 25.3)),
        "p2": _F("Perno M8x20 DIN 933 guarda sup. drive (-X, +Y, inf)", Cylinder(4, 25.3)),
        "s1": _F("Anillo seeger DIN 472-52 (+Y)", Cylinder(27.5, 2) - Cylinder(23, 2)),
        "s2": _F("Anillo seeger DIN 472-52 (-Y)", Cylinder(27.5, 2) - Cylinder(23, 2)),
        "sb": _F("Silentblock M8 Ø30x20 del motor", Cylinder(15, 20)),
        "pl": _F("Placa base de pata (cola, +Y)", Box(100, 100, 6)),
    }


def test_bom_pone_lo_comercial_en_su_categoria_de_compra():
    filas = {r["descripcion"]: r for r in bom_from_scene(_escena_comerciales(), "acero")}
    perno = filas["Perno M8x20 DIN 933 guarda sup. drive"]  # las dos ubicaciones, una fila
    assert (perno["ref"], perno["categoria"], perno["cantidad"]) == ("COMPRA", "pernos", 2)
    assert perno["norma"] == "DIN 933" and perno["longitud_mm"] == 20
    seeger = filas["Anillo seeger DIN 472-52"]
    assert (seeger["categoria"], seeger["cantidad"], seeger["longitud_mm"]) == ("tornilleria", 2, None)
    assert filas["Silentblock M8 Ø30x20 del motor"]["categoria"] == "comerciales"
    placa = filas["Placa base de pata (cola, +Y)"]  # lo de fabricar no cambia
    assert (placa["ref"], placa["categoria"]) == ("A-MEDIDA", "a medida")
    assert placa["longitud_mm"] == pytest.approx(100)


def test_costeo_compra_lo_comercial_y_fabrica_lo_demas():
    rows = costed_bom(_escena_comerciales(), "acero")
    perno = next(r for r in rows if r["descripcion"].startswith("Perno M8x20"))
    assert perno["costo_fuente"].startswith("estimado comercial a mano")
    assert perno["costo_ud_usd"] >= 0.5  # piso de un ítem comercial
    placa = next(r for r in rows if r["ref"] == "A-MEDIDA")
    assert placa["costo_fuente"].startswith("fabricación")
    tot = costing_totals(rows)
    comprado = sum(r["costo_total_usd"] for r in rows if r["ref"] == "COMPRA")
    assert tot["catalogo_usd"] == pytest.approx(comprado, abs=0.02)  # lo comprado, no fabricado
    assert tot["fabricacion_usd"] == pytest.approx(placa["costo_total_usd"], abs=0.02)


def test_cedula_y_lista_de_corte_coinciden_con_la_bom():
    scene = _escena_comerciales()
    corte = {r["nombre"] for r in cut_list(scene, "acero")}
    assert corte == {"Placa base de pata (cola, +Y)"}  # el seeger con norma ya no se corta
    cedula = {r["nombre"]: r for r in hardware_schedule(scene)}
    assert cedula["Anillo seeger DIN 472-52"]["cantidad"] == 2
    assert cedula["Anillo seeger DIN 472-52"]["categoria"] == "tornilleria"
    assert cedula["Perno M8x20 DIN 933 guarda sup. drive"]["categoria"] == "pernos"


# ── 2 · largo nominal de la tornillería de catálogo ──────────────────────────────────────


def _tensor(**extra):
    d = Document("f6-tensor")
    d.execute("create_take_up", {"perno": "PERNO-HEX-M12", "rodamiento": "6205",
                                 "diam_rodillo": 101.6, "ancho_banda": 500, **extra})
    return d


def test_perno_tensor_allen_con_ficha_hex_sale_por_su_nominal():
    d = _tensor()
    pernos = [r for r in bom_from_scene(d.scene, "acero") if r["ref"] == "PERNO-HEX-M12"]
    assert len(pernos) == 1 and pernos[0]["cantidad"] == 2
    assert pernos[0]["longitud_mm"] == 80  # «M12×80»; antes 84,5 (k Allen 12 − k hex 7,5)
    assert "aviso" not in pernos[0]


def test_largo_medido_fuera_de_serie_pide_el_superior_con_aviso():
    comp = CATALOG["PERNO-HEX-M10"]
    feat = _F("Perno hexagonal PERNO-HEX-M10 8.8", hex_bolt(10, 16, 6.4)(47),
              component="PERNO-HEX-M10")
    largo, aviso = largo_de_compra_con_aviso(feat, comp)
    assert largo == 50 and "47" in aviso and "inmediato superior" in aviso
    # el nombre manda y, si la geometría lo contradice, lo dice
    feat = _F("Perno M10×40 DIN 933", hex_bolt(10, 16, 6.4)(50), component="PERNO-HEX-M10")
    largo, aviso = largo_de_compra_con_aviso(feat, comp)
    assert largo == 40 and "50" in aviso
    fila = bom_from_scene({"x": feat}, "acero")[0]
    assert fila["longitud_mm"] == 40 and "aviso" in fila


# ── 3 · el seeger del tensor es comercial ────────────────────────────────────────────────


def test_seeger_del_tensor_es_anillo_din_472_del_alojamiento():
    d = _tensor()
    nombres = [f.name.split(" · ")[-1] for f in d.scene.values() if "Seeger" in f.name]
    assert nombres == ["Anillo Seeger DIN 472-52 (1)", "Anillo Seeger DIN 472-52 (2)"]
    fila = next(r for r in bom_from_scene(d.scene, "acero") if "Seeger" in r["descripcion"])
    assert (fila["ref"], fila["categoria"], fila["norma"]) == ("COMPRA", "tornilleria", "DIN 472")
    assert fila["cantidad"] == 2 and fila["longitud_mm"] is None
    rodillo = Document("f6-motriz")
    rodillo.execute("create_drive_roller", {"rodamiento": "6205", "perno": "PERNO-HEX-M12"})
    assert sum("Anillo Seeger DIN 472-52" in f.name for f in rodillo.scene.values()) == 2


def test_tensor_y_motriz_subieron_su_version():
    from apolo.commands.registry import REGISTRY

    assert REGISTRY["create_take_up"].version == 2
    assert REGISTRY["create_drive_roller"].version == 2


# ── 4 · perno de cuello cuadrado DIN 603 ─────────────────────────────────────────────────


@pytest.mark.parametrize("m", ["M6", "M8", "M10", "M12"])
def test_perno_de_cuello_cuadrado_din_603(m):
    comp = CATALOG[f"PERNO-COCHE-{m}"]
    assert comp.category == "pernos" and comp.specs["norma"] == "DIN 603"
    assert comp.specs["tuerca"] in CATALOG and not comp.cuttable
    pieza = comp.builder(40)
    assert len(pieza.solids()) == 1
    bb = pieza.bounding_box()
    assert bb.min.Z == pytest.approx(-40, abs=0.01)  # largo nominal bajo cabeza, cuello incluido
    assert bb.max.Z == pytest.approx(comp.specs["head_k"], abs=0.01)
    fila = next(r for r in catalog_payload("pernos") if r["ref"] == comp.ref)
    assert 40 in fila["largos_mm"]


def test_perno_de_cuello_cuadrado_en_la_bom_con_su_largo():
    d = Document("f6-coche")
    d.execute("insert_component", {"component": "PERNO-COCHE-M8", "length": 60})
    fila = bom_from_scene(d.scene, "acero")[0]
    assert (fila["ref"], fila["longitud_mm"], fila["norma"]) == ("PERNO-COCHE-M8", 60, "DIN 603")
    assert "L=60 mm" in fila["descripcion"]
