"""F1 del plan pie-nivelador: el catálogo trae los pies que el mercado vende (D5) y la fila de
compra de un pie lleva su ficha (D6).

- Familias de mercado con cifras de ficha citadas: pie articulado de espárrago (del orden de Ganter
  GN 343.2), de base de tecnopolímero (Elesa LV.A y LV.A-SST, carga de ROTURA con factor) e
  higiénico inox (Ganter GN 20, sin verificar).
- El builder modela el hexágono de llave y la tuerca de bloqueo que la ficha trae; los 6 refs de
  siempre conservan su geometría (sin bump de epoch).
- La BOM ya no compra «Pie nivelador PIE-M10-40» pelado.
"""

from __future__ import annotations

import math

import pytest

from apolo.doc.document import Document
from apolo.library.bom import bom_from_scene
from apolo.library.bom_comprable import motivo
from apolo.library.catalog import CATALOG, build_component
from apolo.library.pies_ficha import ficha, texto

G = 9.80665


def _pies(prefijo: str) -> list:
    return [c for c in CATALOG.values()
            if c.category == "pies_niveladores" and c.ref.startswith(prefijo)]


# --- los 6 refs de siempre: misma geometría (volumen, caras y caja de antes de la F1) -------------

_VIEJOS = {
    "PIE-M8-30": (29782.298, 5, (-30.0, -30.0, -25.0, 30.0, 30.0, 15.0)),
    "PIE-M10-40": (56155.969, 5, (-37.5, -37.5, -32.0, 37.5, 37.5, 20.0)),
    "PIE-M12-50": (94719.019, 5, (-45.0, -45.0, -39.0, 45.0, 45.0, 25.0)),
    "PIE-BA-M8-30": (150429.204, 10, (-95.0, -40.0, -25.0, 95.0, 40.0, 15.0)),
    "PIE-BA-M10-40": (181847.08, 10, (-95.0, -40.0, -32.0, 95.0, 40.0, 20.0)),
    "PIE-BA-M12-50": (214144.602, 10, (-95.0, -40.0, -39.0, 95.0, 40.0, 25.0)),
}


@pytest.mark.parametrize("ref", sorted(_VIEJOS))
def test_los_refs_de_siempre_conservan_su_geometria(ref):
    vol, caras, caja = _VIEJOS[ref]
    s, _ = build_component(ref)
    bb = s.bounding_box()
    assert s.volume == pytest.approx(vol, abs=1e-2)
    assert len(s.faces()) == caras
    assert (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z) == pytest.approx(caja)


def test_los_refs_de_siempre_siguen_con_su_carga_y_ganan_su_ficha():
    for ref, carga in (("PIE-M8-30", 120), ("PIE-M10-40", 200), ("PIE-M12-50", 350)):
        s = CATALOG[ref].specs
        assert s["carga_kg"] == carga and s["base"] == "disco fijo"
        assert s["tuerca_incluida"] is False and s["cotas_verificadas"] is False


# --- las familias de mercado ----------------------------------------------------------------------

def test_cada_familia_trae_su_fuente_y_su_carga_de_servicio():
    familias = {"PIE-ART-": 16, "PIE-TP-": 11, "PIE-TPX-": 5, "PIE-HIG-": 6}
    for prefijo, n in familias.items():
        pies = _pies(prefijo)
        assert len(pies) == n, prefijo
        for c in pies:
            s = c.specs
            assert s["fuente"].startswith("ficha "), c.ref
            assert s["linea_referencia"].startswith("del orden de "), c.ref
            assert isinstance(s["cotas_verificadas"], bool) and s["no_publicado"], c.ref
            assert s["carga_kg"] > 0 and s["designacion_fabricante"], c.ref
    assert len([c for c in CATALOG.values() if c.category == "pies_niveladores"]) == 6 + 38


def test_articulado_de_esparrago_ganter_gn_343_2():
    pies = _pies("PIE-ART-")
    # rosca M8–M20 con la serie de largos de la ficha por rosca y base
    largos = {}
    for c in pies:
        s = c.specs
        largos.setdefault((s["disco_d"], s["rosca"]), []).append(s["altura"])
        assert s["designacion_fabricante"] == (
            f"GN 343.2-{s['disco_d']:g}-M{s['rosca']:g}-{s['altura']:g}-OS")
        assert s["base"] == "articulada" and s["tuerca_incluida"] is True
        assert s["tuerca"] == f"ISO 4032 M{s['rosca']:g}" and s["cotas_verificadas"] is True
        # la carga de la ficha es ADMISIBLE: carga_kg = kN / g, sin otro factor
        assert s["carga_kg"] == math.floor(s["carga_estatica_kn"] * 1000 / G)
    assert sorted(largos[(40, 10)]) == [50, 63, 80]
    assert sorted(largos[(50, 12)]) == [63, 80, 100]
    assert sorted(largos[(60, 16)]) == [80, 100, 125]
    assert sorted(largos[(60, 20)]) == [98, 138, 158]
    m16 = CATALOG["PIE-ART-60-M16-100"].specs
    assert (m16["sw"], m16["carga_estatica_kn"], m16["tuerca_m"]) == (24, 62, 14.8)


def test_base_de_tecnopolimero_elesa_lva_su_carga_es_de_rotura_con_factor_4():
    for c in _pies("PIE-TP-") + _pies("PIE-TPX-"):
        s = c.specs
        assert s["factor_rotura"] == 4 and s["tuerca_incluida"] is False
        assert s["carga_kg"] == math.floor(s["carga_rotura_n"] / 4 / G), c.ref
        assert s["carga_rotura_n"] in (16000, 18000) and s["articulacion_grados"] in (14, 24)
        assert c.weight < 0.5  # el peso es el de la ficha (base de plástico), no acero macizo
    assert CATALOG["PIE-TP-80-M10-68"].specs["material"] == "acero zincado"
    assert CATALOG["PIE-TPX-80-M12-98"].specs["material"] == "acero inoxidable AISI 304"
    assert CATALOG["PIE-TP-80-M20-138"].specs["designacion_fabricante"] == "LV.A-80-24-M20x138"


def test_higienico_inox_ganter_gn_20_sin_verificar_y_sin_buje():
    pies = _pies("PIE-HIG-")
    assert {c.specs["rosca"] for c in pies} == {12, 16, 20, 24}
    for c in pies:
        s = c.specs
        assert s["cotas_verificadas"] is False and s["buje_de_soldar"] is False
        assert s["material"] == "acero inoxidable AISI 304"
        assert s["altura"] == s["largo_total"] - 35  # vástago libre = l1 − l3 (lectura nuestra)
        assert s["carga_kg"] == math.floor(s["carga_estatica_kn"] * 1000 / G)


# --- el builder: hexágono de llave y tuerca de bloqueo --------------------------------------------

def _hex(sw: float) -> float:
    return math.sqrt(3) / 2 * sw * sw


def test_el_articulado_lleva_hexagono_de_llave_y_tuerca_de_bloqueo_a_media_rosca():
    c = CATALOG["PIE-ART-40-M10-63"]
    p = c.params
    s, _ = build_component(c.ref)
    assert len(s.solids()) == 1
    bb = s.bounding_box()
    alto = p["altura"] + p["sw_h"] + p["cuerpo_h"] + p["disco_t"]
    assert bb.max.Z - bb.min.Z == pytest.approx(alto)
    assert bb.max.X - bb.min.X == pytest.approx(p["disco_d"])
    esperado = (math.pi / 4 * (p["rosca"] ** 2 * p["altura"] + p["disco_d"] ** 2 * p["disco_t"]
                               + p["cuerpo_d"] ** 2 * p["cuerpo_h"])
                + _hex(p["sw"]) * p["sw_h"]
                + (_hex(p["tuerca_sw"]) - math.pi / 4 * p["rosca"] ** 2) * p["tuerca_m"])
    assert s.volume == pytest.approx(esperado, rel=1e-3)
    # la tuerca: a media rosca (su cara de arriba en el centro del vástago, z = 0)
    corte = s.intersect(_losa(-p["tuerca_m"] / 2.0))
    assert corte.volume == pytest.approx(_hex(p["tuerca_sw"]) * 1.0, rel=1e-3)
    sobre = s.intersect(_losa(0.6))
    assert sobre.volume == pytest.approx(math.pi / 4 * p["rosca"] ** 2, rel=1e-3)


def _losa(z: float):
    """Losa de 1 mm de alto centrada en z, más ancha que cualquier pie."""
    from build123d import Box, Pos

    return Pos(0, 0, z) * Box(300, 300, 1.0)


def test_el_de_tecnopolimero_lleva_hexagono_y_ninguna_tuerca():
    c = CATALOG["PIE-TP-80-M16-98"]
    p = c.params
    s, _ = build_component(c.ref)
    assert len(s.solids()) == 1
    bb = s.bounding_box()
    # altura total = l1 + l (la L de la ficha: 141)
    assert bb.max.Z - bb.min.Z == pytest.approx(141.0)
    # a media rosca sólo el vástago (no hay tuerca)
    assert s.intersect(_losa(0.0)).volume == pytest.approx(math.pi / 4 * 16 ** 2, rel=1e-3)
    # el hexágono SW24 bajo el vástago
    z_hex = -p["altura"] / 2.0 - p["sw_h"] / 2.0
    assert s.intersect(_losa(z_hex)).volume == pytest.approx(_hex(24), rel=1e-3)


# --- D6: la fila de compra lleva la ficha ---------------------------------------------------------

def test_la_ficha_de_compra_de_un_pie_de_siempre():
    f = ficha(CATALOG["PIE-M10-40"])
    assert f == {"rosca": "M10", "largo_vastago_mm": 40.0, "base": "disco Ø75 fijo",
                 "articulada": False, "material": "acero zincado", "carga_servicio_kg": 200.0,
                 "tuerca_incluida": False}
    assert texto(CATALOG["PIE-M10-40"]) == (
        " — M10 × 40 mm, disco Ø75 fijo, acero zincado, carga 200 kg/pie, sin tuerca de bloqueo")
    assert ficha(CATALOG["UCP205"]) is None and texto(CATALOG["UCP205"]) == ""


def test_la_ficha_de_compra_del_articulado_y_de_la_base_de_anclaje():
    t = texto(CATALOG["PIE-ART-60-M16-100"])
    assert t == (" — M16 × 100 mm, base Ø60 articulada, SW24, acero zincado, carga 6322 kg/pie, "
                 "con tuerca ISO 4032 M16, del orden de GN 343.2-60-M16-100-OS")
    assert "base Ø80 articulada 24°" in texto(CATALOG["PIE-TP-80-M16-98"])
    assert "placa de anclaje 190×80 con 2 agujeros Ø14" in texto(CATALOG["PIE-BA-M10-40"])


def test_la_bom_ya_no_compra_el_pie_pelado():
    d = Document()
    for i, ref in enumerate(("PIE-M10-40", "PIE-M10-40", "PIE-ART-40-M10-63")):
        d.execute("insert_component", {"component": ref, "name": f"Pie nivelador ({i + 1})",
                                       "position": {"x": 200.0 * i, "y": 0.0, "z": 0.0}})
    filas = {f["ref"]: f for f in bom_from_scene(d.scene)}
    viejo = filas["PIE-M10-40"]
    assert viejo["cantidad"] == 2
    assert viejo["descripcion"] != "Pie nivelador PIE-M10-40"
    assert "M10 × 40 mm" in viejo["descripcion"] and "carga 200 kg/pie" in viejo["descripcion"]
    assert viejo["ficha"]["largo_vastago_mm"] == 40.0
    assert viejo["ficha"]["carga_servicio_kg"] == 200.0
    nuevo = filas["PIE-ART-40-M10-63"]
    assert nuevo["ficha"]["tuerca_incluida"] is True and nuevo["ficha"]["articulada"] is True
    assert "del orden de GN 343.2-40-M10-63-OS" in nuevo["descripcion"]
    assert motivo(viejo) is None and motivo(nuevo) is None  # `bom.comprable` no cambia


@pytest.mark.parametrize("ref", ["PIE-ART-32-M8-50", "PIE-ART-60-M20-158", "PIE-TP-80-M10-43",
                                 "PIE-TPX-80-M20-138", "PIE-HIG-60-M12-175",
                                 "PIE-HIG-100-M24-235"])
def test_cada_familia_construye_un_solido(ref):
    s, _ = build_component(ref)
    assert len(s.solids()) == 1 and s.volume > 0
