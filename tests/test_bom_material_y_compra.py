"""F6 — la BOM compra lo que el modelo DICE (tres máquinas de alimentos de 2026-10-27):

1. `set_material` sobre una ref de catálogo (un `TUBOR-2`, un `PERNO-HEX-M10`) no cambiaba la BOM
   («acero ASTM A500», «8.8»): ahora la fila compra la EQUIVALENTE en el material asignado;
2. la tornillería de una unión DECLARADA salía siempre en acero 8.8 aunque la nota dijera «A2-70»:
   la nota (o el campo `material_tornilleria`) decide el material;
3. un sólido a mano «Válvula … (compra)» salía A-MEDIDA, «a medida»: la compra DECLARADA cuenta;
4. los pernos de OTRA unión (los de un `join_bolted` vecino) cubrían los de una unión declarada.
"""

import pytest

from apolo.doc import Document
from apolo.library.bom import COMPRA, bom_from_scene
from apolo.library.costing import costed_bom
from apolo.library.cutlist import cut_list, hardware_schedule
from apolo.library.designacion_comercial import (
    compra_declarada, es_comercial, nombre_de_compra, sin_marca_de_compra,
)
from apolo.library.tornilleria_declarada import filas_declaradas, material_de_nota

INOX = "acero inoxidable AISI 304"


def _bb(feat):
    return feat.shape.bounding_box()


# ── 1 · set_material sobre una ref de catálogo ───────────────────────────────────────────


def _patas_y_pernos(d):
    patas = [d.execute("insert_component", {"component": "TUBOR-2", "length": 800,
                                            "position": {"x": 200.0 * i}}) for i in range(3)]
    pernos = [d.execute("insert_component", {"component": "PERNO-HEX-M10", "length": 30,
                                             "position": {"x": 200.0 * i, "y": 300}})
              for i in range(2)]
    return patas, pernos


def test_set_material_en_una_ref_compra_la_equivalente():
    d = Document("f6-material-ref")
    patas, pernos = _patas_y_pernos(d)
    antes = {r["ref"]: r for r in bom_from_scene(d.scene, "acero")}
    for fid in patas[:2] + pernos:
        d.set_material(fid, INOX)
    filas = bom_from_scene(d.scene, "acero")
    tubos = [r for r in filas if r["ref"] == "TUBOR-2"]
    inox = next(r for r in tubos if r["material"] == INOX)
    acero = next(r for r in tubos if r["material"] == "acero ASTM A500")
    assert (inox["cantidad"], acero["cantidad"]) == (2, 1)  # una fila por material
    assert inox["material_ficha"] == "acero ASTM A500" and "material_ficha" not in acero
    assert inox["descripcion"].endswith(
        f"en {INOX} (la ref de catálogo es de acero ASTM A500: pedir la equivalente)")
    assert inox["norma"] == ""  # «ASTM A500 round HSS» es la norma del MATERIAL de la ficha
    assert acero["norma"] == "ASTM A500 round HSS"
    peso_ficha = antes["TUBOR-2"]["peso_unitario_kg"]
    assert inox["peso_unitario_kg"] == pytest.approx(peso_ficha * 8.0 / 7.85, abs=0.002)
    (perno,) = [r for r in filas if r["ref"] == "PERNO-HEX-M10"]
    assert perno["material"] == INOX and perno["cantidad"] == 2
    assert perno["norma"] == "DIN 933"  # la norma de la FORMA sigue valiendo
    assert "la ref de catálogo es de acero grado 8.8" in perno["descripcion"]


def test_el_costeo_escala_el_precio_de_la_ficha_al_material():
    d = Document("f6-material-costo")
    patas, _ = _patas_y_pernos(d)
    d.set_material(patas[0], INOX)
    filas = [r for r in costed_bom(d.scene, "acero") if r["ref"] == "TUBOR-2"]
    acero = next(r for r in filas if "material_ficha" not in r)
    inox = next(r for r in filas if r.get("material_ficha"))
    factor = (5.5 * 8.0) / (1.5 * 7.85)  # USD/kg × densidad de cada material
    assert inox["costo_ud_usd"] == pytest.approx(acero["costo_ud_usd"] * factor, abs=0.02)
    assert "escalado de acero ASTM A500" in inox["costo_fuente"]
    assert acero["costo_fuente"] == "catálogo (USD/m)"


def test_el_mismo_material_que_la_ficha_no_cambia_nada():
    d = Document("f6-material-igual")
    patas, pernos = _patas_y_pernos(d)
    antes = bom_from_scene(d.scene, "acero")
    d.set_material(patas[0], "Acero ASTM A500")  # el de la ficha, con otra caja
    assert bom_from_scene(d.scene, "acero") == antes


def test_la_cedula_y_la_lista_de_corte_dicen_el_material_asignado():
    d = Document("f6-material-cedula")
    patas, pernos = _patas_y_pernos(d)
    d.set_material(pernos[0], INOX)
    d.set_material(patas[0], INOX)
    ced = [r for r in hardware_schedule(d.scene) if r["ref"] == "PERNO-HEX-M10"]
    assert sorted(r["material"] for r in ced) == sorted([INOX, "acero grado 8.8"])
    assert any(r["material"] == INOX for r in cut_list(d.scene, "acero"))


# ── 2 · el material de la tornillería declarada ──────────────────────────────────────────


def _placas(d):
    a = d.execute("create_box", {"name": "Labio de la caja", "width": 100, "depth": 100,
                                 "height": 5})
    za = _bb(d.scene[a]).max.Z
    b = d.execute("create_box", {"name": "Brida de la boca", "width": 100, "depth": 100,
                                 "height": 5, "position": {"z": za + 2.5}})
    return a, b


@pytest.mark.parametrize("nota,material", [
    ("8x ISO 4017 M8x25 A2-70 + tuerca ISO 4032 A2", "acero inoxidable A2-70"),
    ("M6x16 DIN 933 A2 + tuerca", "acero inoxidable A2"),
    ("M5x12 DIN 933 + tuerca, inox", "acero inoxidable"),
    ("M10x30 DIN 933 AISI 316", "acero inoxidable AISI 316"),
    ("M8x40 DIN 933 + tuerca DIN 934", None),
    ("brida MF1 (paso A4)", "acero inoxidable A4"),
])
def test_material_de_la_nota(nota, material):
    assert material_de_nota(nota) == material


def test_la_nota_inox_compra_perno_y_tuerca_inox():
    d = Document("f6-declarada-inox")
    a, b = _placas(d)
    d.execute("fasten", {"name": "caja_boca", "a": a, "b": b, "kind": "perno", "size": "M8",
                         "qty": 8, "nota": "8x ISO 4017 M8x25 A2-70 + tuerca ISO 4032 A2"})
    d.execute("fasten", {"name": "caja_boca_acero", "a": a, "b": b, "kind": "perno",
                         "size": "M8", "qty": 2, "nota": "M8x25 DIN 933 + tuerca"})
    filas = filas_declaradas(d.scene, d.fasteners)
    pernos = {r["material"]: r for r in filas if r["ref"] == "PERNO-HEX-M8"}
    assert pernos["acero inoxidable A2-70"]["cantidad"] == 8
    assert pernos["acero grado 8.8"]["cantidad"] == 2  # sin material: la ficha, como antes
    assert "pedir la equivalente" in pernos["acero inoxidable A2-70"]["descripcion"]
    assert pernos["acero inoxidable A2-70"]["descripcion"].endswith(
        "(unión declarada sin pieza modelada)")
    tuercas = {r["material"]: r["cantidad"] for r in filas if r["ref"] == "TUERCA-M8"}
    assert tuercas == {"acero inoxidable A2-70": 8, "acero grado 8": 2}


def test_el_campo_de_la_union_gana_a_la_nota_y_sin_el_el_dict_de_siempre():
    d = Document("f6-declarada-campo")
    a, b = _placas(d)
    d.execute("fasten", {"name": "u", "a": a, "b": b, "kind": "perno", "size": "M8", "qty": 2,
                         "nota": "M8x25 DIN 933 A2 + tuerca",
                         "material_tornilleria": "acero 8.8 zincado"})
    d.execute("fasten", {"name": "v", "a": a, "b": b, "kind": "perno", "size": "M8", "qty": 1})
    assert d.fasteners["u"]["material_tornilleria"] == "acero 8.8 zincado"
    assert "material_tornilleria" not in d.fasteners["v"]  # un log viejo regenera igual
    filas = filas_declaradas(d.scene, d.fasteners)
    assert {r["material"] for r in filas if "u" in r["uniones"]} == {"acero 8.8 zincado"}


@pytest.mark.parametrize("nota", [
    "tornillo del tope (incluido)", "prisionero de la ranura en T (incluido con el detector)",
    "4 cierres de palanca inox (sin perno suelto) aprietan el aro",
])
def test_lo_incluido_o_sin_perno_no_se_compra(nota):
    d = Document("f6-declarada-nada")
    a, b = _placas(d)
    d.execute("fasten", {"name": "u", "a": a, "b": b, "kind": "perno", "size": "M4", "qty": 2,
                         "nota": nota})
    assert filas_declaradas(d.scene, d.fasteners) == []


# ── 3 · compra declarada en un sólido a mano ─────────────────────────────────────────────


@pytest.mark.parametrize("nombre,declarada", [
    ("Válvula de bola de descarga DN40 1 1/2\" AISI 316 ASME B16.11 (compra)", True),
    ("Bisagra de la boca 1 (pala 63 mm AISI 304, compra)", True),
    ("Retén del paso de eje (DIN 3760 25x40x7 NBR, compra)", True),
    ("Tapa (de compra)", True),
    ("Placa de piso (compra local de 2 m)", False),
    ("Válvula de bola de descarga", False),
    ("Compra · Placa", False),
])
def test_compra_declarada(nombre, declarada):
    assert compra_declarada(nombre) is declarada
    assert es_comercial(nombre) is declarada


def test_la_marca_no_sale_en_lo_que_se_pide():
    assert sin_marca_de_compra("Bisagra 1 (pala 63 mm AISI 304, compra)") == \
        "Bisagra 1 (pala 63 mm AISI 304)"
    assert nombre_de_compra("Válvula de bola DN40 (compra)") == "Válvula de bola DN40"
    assert sin_marca_de_compra("Placa (a; b) (compra)") == "Placa (a; b)"


def test_el_solido_a_mano_declarado_compra_sale_de_compra():
    d = Document("f6-compra-declarada")
    v = d.execute("create_box", {"name": "Válvula de bola DN40 ASME B16.11 (compra)",
                                 "width": 160, "depth": 60, "height": 80})
    bis = [d.execute("create_box", {"name": "Bisagra de la boca (pala 63 mm AISI 304, compra)",
                                    "width": 63, "depth": 2, "height": 50,
                                    "position": {"x": 300 + 100 * i}}) for i in range(2)]
    for fid in [v] + bis:
        d.set_material(fid, INOX)
    filas = {r["descripcion"]: r for r in bom_from_scene(d.scene, "acero")}
    valv = filas["Válvula de bola DN40 ASME B16.11"]
    assert (valv["ref"], valv["categoria"], valv["norma"]) == (COMPRA, "comerciales", "ASME B16.11")
    assert valv["longitud_mm"] is None  # se pide por designación, no por corte
    bisagra = filas["Bisagra de la boca (pala 63 mm AISI 304)"]
    assert (bisagra["ref"], bisagra["categoria"], bisagra["cantidad"]) == (COMPRA, "bisagras", 2)
    costo = next(r for r in costed_bom(d.scene, "acero") if r["ref"] == COMPRA
                 and r["descripcion"].startswith("Válvula"))
    assert costo["costo_fuente"].startswith("estimado comercial")
    assert cut_list(d.scene, "acero") == []  # nada de esto se corta


# ── 4 · la tornillería de otra unión no cubre la declarada ───────────────────────────────


def _caja_boca_guia(d):
    """Caja de compuerta cuya caja (abierta) envuelve la zona de la guía; boca encima."""
    caja = d.execute("create_box", {"name": "Caja de compuerta", "width": 400, "depth": 400,
                                    "height": 300, "position": {"z": 150}})
    boca = d.execute("create_box", {"name": "Boca de descarga", "width": 400, "depth": 400,
                                    "height": 10, "position": {"z": 305}})
    guia = d.execute("create_box", {"name": "Guía der.", "width": 40, "depth": 300,
                                    "height": 10, "position": {"x": 150, "z": 295}})
    return caja, boca, guia


def _perno_vertical(d, ref, x, y, z_cabeza, length):
    return d.execute("insert_component", {"component": ref, "length": length,
                                          "position": {"x": x, "y": y, "z": z_cabeza}})


def test_los_pernos_de_un_join_bolted_vecino_no_cubren_la_union_declarada():
    d = Document("f6-pernos-ajenos")
    caja, boca, guia = _caja_boca_guia(d)
    ajenos = [_perno_vertical(d, "PERNO-HEX-M8", 150, y, 310, 35) for y in (-100, 0, 100)]
    for fid in ajenos:  # cruzan las cajas de la caja de compuerta y de la boca
        assert _bb(d.scene[fid]).min.Z < 300 < _bb(d.scene[fid]).max.Z
    cmd = d.scene[ajenos[0]].command_id
    fasteners = dict(d.fasteners)
    # lo que deja un join_bolted: la unión `jb_<cmd>` con el command_id de SUS pernos
    for fid in ajenos:
        d.scene[fid].command_id = cmd
    fasteners["jb_guia"] = {"name": "jb_guia", "a": guia, "b": boca, "kind": "perno",
                            "size": "M8", "qty": 3, "nota": "Guía der. a boca", "command_id": cmd}
    fasteners["caja_boca"] = {"name": "caja_boca", "a": caja, "b": boca, "kind": "perno",
                              "size": "M8", "qty": 8, "nota": "8x ISO 4017 M8x25 A2-70",
                              "command_id": "c99"}
    (fila,) = filas_declaradas(d.scene, fasteners)
    assert (fila["ref"], fila["longitud_mm"], fila["cantidad"]) == ("PERNO-HEX-M8", 25, 8)
    assert fila["uniones"] == ["caja_boca"]


def test_un_perno_de_otra_metrica_no_cuenta():
    d = Document("f6-pernos-metrica")
    a, b = _placas(d)
    top = _bb(d.scene[b]).max.Z
    d.execute("insert_component", {"component": "PERNO-HEX-M10", "length": 25,
                                   "position": {"z": top}})
    d.execute("fasten", {"name": "u", "a": a, "b": b, "kind": "perno", "size": "M8", "qty": 1,
                         "nota": "M8x25 DIN 933"})
    (fila,) = filas_declaradas(d.scene, d.fasteners)
    assert (fila["ref"], fila["cantidad"]) == ("PERNO-HEX-M8", 1)
