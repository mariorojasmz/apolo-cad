"""Catálogo del armado del tablero (plan V8.5 F1a: A2, A3, A4 y las refs nuevas de D9).

- El interior de los 3 gabinetes (placa útil, fondo útil, placa–fondo, espesores, bisagra,
  placa pasacables), declarado SIN verificar y con su línea de referencia.
- El marco de montaje por familia (la caja apoya por −Y, la seta por −Z) y el fondo de cada mando
  de puerta partido en lo de delante y lo de detrás (la seta, contra su geometría).
- Los 4 accesorios que van pegados a su aparato (`acopla_a`).
- Las refs nuevas: riel DIN TH35 (EN 60715), canaletas ranuradas y los topes de la bornera.
- El loader rechaza un bloque `tablero:` mal escrito con un mensaje que dice qué corregir.
"""

from __future__ import annotations

import re

import pytest
import yaml

from apolo.library.catalog import CATALOG, build_component, refs_in_category
from apolo.library.electrico.ficha_tablero import APOYO_POR_FAMILIA, apoyo_de
from apolo.library.loader import load_catalog

GABINETES = ["TABLERO-5040", "GAB-6040", "GAB-8060"]
ACCESORIOS = {"GM-AUX-1NA1NC": ("guardamotor_3p", "frente"),
              "CONT-AUX-1NA1NC": ("contactor_3p", "frente"),
              "RT-2.5-4A": ("contactor_3p", "abajo"), "RT-4-6A": ("contactor_3p", "abajo")}
NUEVAS = ["RIEL-DIN-TH35-7.5", "RIEL-DIN-TH35-15", "CANALETA-25X25", "CANALETA-25X40",
          "CANALETA-40X40", "CANALETA-40X60", "CANALETA-60X60", "CANALETA-60X80",
          "TOPE-DIN-35", "TAPA-BORNE-2.5-4"]


def _puerta() -> list[str]:
    return [r for r, c in CATALOG.items() if c.electrico is not None and c.electrico.montaje == "puerta"]


# ── gabinetes (A2) ────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ref", GABINETES)
def test_el_gabinete_declara_su_interior(ref):
    c = CATALOG[ref]
    g = c.tablero.gabinete
    w, d, h = (c.params[k] for k in ("width", "depth", "height"))
    assert g.cotas_verificadas is False and g.linea_referencia.strip()
    assert 0 < g.placa_ancho_mm < w and 0 < g.placa_alto_mm < h
    assert g.espesor_mm + g.placa_fondo_mm + g.fondo_util_mm + g.espesor_puerta_mm <= d
    assert g.bisagra in ("izquierda", "derecha") and g.pasacables.cara == "inferior"
    # la caja no cambió: el interior lo lee la colocación, no el builder (sin bump de epoch)
    bb = build_component(ref)[0].bounding_box()
    assert (round(bb.size.X), round(bb.size.Y), round(bb.size.Z)) == (w, d, h)


def test_los_gabinetes_crecen_en_placa_util():
    areas = [CATALOG[r].tablero.gabinete for r in GABINETES]
    assert [g.placa_ancho_mm * g.placa_alto_mm for g in areas] == sorted(
        g.placa_ancho_mm * g.placa_alto_mm for g in areas)
    assert all(g.fondo_util_mm >= 160 for g in areas)  # entra el variador de la faja (145 de fondo)


# ── marco de montaje (A3) ─────────────────────────────────────────────────────────────────
def test_la_cara_de_apoyo_es_por_familia():
    assert APOYO_POR_FAMILIA["box"] == "-Y" and APOYO_POR_FAMILIA["seta_emergencia"] == "-Z"
    assert apoyo_de("box", CATALOG["ITM-C16-3P"].tablero) == "-Y"
    assert apoyo_de(CATALOG["ESTOP-40"].familia, CATALOG["ESTOP-40"].tablero) == "-Z"
    assert apoyo_de("caster", None) is None  # una familia que no va en tablero no tiene marco
    for ref, c in CATALOG.items():
        e = c.electrico
        if e is not None and e.conductor is None and e.montaje in ("din", "placa", "puerta"):
            assert apoyo_de(c.familia, c.tablero) is not None, ref


def test_todo_mando_de_puerta_parte_su_fondo():
    assert len(_puerta()) == 11  # los 10 en caja + la seta
    for ref in _puerta():
        c = CATALOG[ref]
        p = c.tablero.puerta
        assert p is not None and p.delante_mm > 0 and p.detras_mm > 0, ref
        if c.familia == "box":
            assert p.delante_mm + p.detras_mm == pytest.approx(c.params["depth"], abs=0.5), ref


def test_la_seta_parte_su_fondo_como_su_geometria():
    """El origen de la seta es el frente de la puerta y +Z sale hacia el operador."""
    p = CATALOG["ESTOP-40"].tablero.puerta
    bb = build_component("ESTOP-40")[0].bounding_box()
    assert bb.max.Z == pytest.approx(p.delante_mm, abs=0.5)
    assert -bb.min.Z == pytest.approx(p.detras_mm, abs=0.5)


# ── accesorios acoplados (A4) ─────────────────────────────────────────────────────────────
def test_los_accesorios_van_pegados_a_su_aparato():
    simbolos = {c.electrico.simbolo for c in CATALOG.values() if c.electrico is not None}
    con_acople = {r for r, c in CATALOG.items() if c.tablero is not None and c.tablero.acopla_a}
    assert con_acople == set(ACCESORIOS)
    for ref, (simbolo, cara) in ACCESORIOS.items():
        a = CATALOG[ref].tablero.acopla_a
        assert a.simbolos == (simbolo,) and a.cara == cara and a.orden == 1, ref
        assert set(a.simbolos) <= simbolos, ref


# ── refs nuevas (D9) ──────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ref", NUEVAS)
def test_cada_ref_nueva_es_honesta(ref):
    c = CATALOG[ref]
    s = c.specs
    assert c.category == "tableros" and c.electrico is None
    assert s["linea_referencia"].startswith("orden de ") and s["cotas_verificadas"] is False
    assert "verificar con" in c.description.lower()
    assert ("cost" in s) != ("cost_por_m" in s)
    if c.cuttable:
        assert c.default_length == 1000 and s["cost_por_m"] > 0


@pytest.mark.parametrize("ref,alto", [("RIEL-DIN-TH35-7.5", 7.5), ("RIEL-DIN-TH35-15", 15)])
def test_el_riel_es_el_th35_de_en_60715(ref, alto):
    c = CATALOG[ref]
    assert c.tablero.riel.norma == "EN 60715" and c.cuttable
    shape, largo = build_component(ref, 250)
    bb = shape.bounding_box()
    assert largo == 250 and (bb.size.X, bb.size.Y, bb.size.Z) == pytest.approx((35, alto, 250))
    assert shape.is_valid and len(shape.solids()) == 1


@pytest.mark.parametrize("ref", [r for r in NUEVAS if r.startswith("CANALETA-")])
def test_la_canaleta_declara_lo_que_llenan_los_conductores(ref):
    c = CATALOG[ref]
    k = c.tablero.canaleta
    pared = c.params["pared"]
    interior = (k.ancho_mm - 2 * pared) * (k.alto_mm - 2 * pared)
    assert 0.8 * interior <= k.seccion_util_mm2 <= interior, ref
    assert c.specs["seccion"] == f"{k.ancho_mm:g}x{k.alto_mm:g}"
    shape, _ = build_component(ref, 100)
    assert shape.volume == pytest.approx((k.ancho_mm * k.alto_mm - interior) * 100, rel=1e-3)


def test_las_refs_nuevas_estan_en_tableros():
    assert set(NUEVAS) <= set(refs_in_category("tableros"))


# ── el loader rechaza un bloque mal escrito ───────────────────────────────────────────────
_GAB = {"placa_util_mm": [450, 350], "fondo_util_mm": 160, "placa_fondo_mm": 25,
        "espesor_mm": 1.5, "espesor_puerta_mm": 1.5, "bisagra": "izquierda",
        "pasacables": {"cara": "inferior", "ancho_mm": 400, "fondo_mm": 120},
        "linea_referencia": "orden de x", "cotas_verificadas": False}
_PUERTA = {"funcion": "S", "simbolo": "pulsador_na", "montaje": "puerta",
           "bornes": [{"id": "13", "rol": "contacto"}, {"id": "14", "rol": "contacto"}]}
_DIN = {**_PUERTA, "montaje": "din"}


def _cargar(tmp_path, tablero, *, electrico=None, builder="box", params=None):
    comp = {"ref": "R", "name": "Prueba", "builder": builder, "weight": 1, "tablero": tablero,
            "params": params or {"width": 500, "depth": 200, "height": 400}}
    if electrico is not None:
        comp["electrico"] = electrico
    doc = {"category": "x", "components": [comp]}
    (tmp_path / "a.yaml").write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return load_catalog(str(tmp_path))


def test_un_bloque_bueno_carga(tmp_path):
    g = _cargar(tmp_path, {"gabinete": _GAB})["R"].tablero.gabinete
    assert (g.placa_ancho_mm, g.placa_alto_mm, g.pasacables.ancho_mm) == (450, 350, 400)
    p = _cargar(tmp_path, {"puerta": {"delante_mm": 12, "detras_mm": 38}}, electrico=_PUERTA,
                params={"width": 30, "depth": 50, "height": 30})["R"].tablero.puerta
    assert (p.delante_mm, p.detras_mm) == (12, 38)


def test_la_familia_pasa_su_bloque_a_cada_variante(tmp_path):
    familia = {"family": "F", "name_tpl": "Canaleta {ref}", "builder": "canaleta",
               "param_keys": ["ancho", "alto", "pared"], "weight": 0.2, "cuttable": True,
               "default_length": 1000, "tablero": {"apoyo": "-Y"},
               "variants": [{"ref": "K1", "ancho": 25, "alto": 40, "pared": 1.5,
                             "tablero": {"canaleta": {"seccion_util_mm2": 700}}}]}
    (tmp_path / "a.yaml").write_text(yaml.safe_dump({"category": "x", "families": [familia]}),
                                     encoding="utf-8")
    k1 = load_catalog(str(tmp_path))["K1"]
    assert k1.tablero.apoyo == "-Y" and k1.tablero.canaleta.seccion_util_mm2 == 700
    assert "tablero" not in k1.specs


MALOS = [
    ({"gabinte": _GAB}, {}, r"clave desconocida «gabinte».*¿Quisiste decir «gabinete»"),
    ({"gabinete": {**_GAB, "bisagra": "arriba"}}, {}, r"gabinete\.bisagra: «arriba» no es válido"),
    ({"gabinete": {**_GAB, "fondo_util_mm": 190}}, {}, r"= 218 mm pasa el fondo de la caja \(200 mm\)"),
    ({"gabinete": {**_GAB, "placa_util_mm": [520, 350]}}, {}, r"la placa útil 520×350 no entra"),
    ({"gabinete": {k: v for k, v in _GAB.items() if k != "linea_referencia"}}, {},
     r"gabinete: falta `linea_referencia`"),
    ({"gabinete": {**_GAB, "cotas_verificadas": "no"}}, {}, r"cotas_verificadas: se espera true o false"),
    ({"apoyo": "-W"}, {}, r"tablero\.apoyo: «-W» no es válido"),
    ({"puerta": {"delante_mm": 12, "detras_mm": 30}},
     {"electrico": _PUERTA, "params": {"width": 30, "depth": 50, "height": 30}},
     r"delante_mm 12 \+ detras_mm 30 = 42 no es el fondo de la caja \(50 mm\)"),
    ({"puerta": {"delante_mm": 12, "detras_mm": 38}},
     {"electrico": _DIN, "params": {"width": 30, "depth": 50, "height": 30}},
     r"sólo un mando de puerta .* el montaje es «din»"),
    ({"puerta": {"delante_mm": 0, "detras_mm": 50}},
     {"electrico": _PUERTA, "params": {"width": 30, "depth": 50, "height": 30}},
     r"puerta\.delante_mm: se espera un número > 0"),
    ({"acopla_a": {"simbolos": ["contactor_3p"], "cara": "atras"}}, {},
     r"acopla_a\.cara: «atras» no es válido"),
    ({"acopla_a": {"simbolos": [], "cara": "abajo"}}, {}, r"acopla_a\.simbolos: se espera una lista"),
    ({"acopla_a": {"simbolos": ["contactor_3p"], "cara": "abajo", "orden": 0}}, {},
     r"acopla_a\.orden: se espera un entero ≥ 1"),
    ({"canaleta": {"seccion_util_mm2": 500}}, {}, r"sólo una canaleta .* el builder es «box»"),
    ({"canaleta": {"seccion_util_mm2": 1200}},
     {"builder": "canaleta", "params": {"ancho": 25, "alto": 40, "pared": 1.5}},
     r"1200 mm² no cabe en la sección exterior 25×40 = 1000 mm²"),
    ({"riel": {"norma": "EN 60715", "perfil": "TH35-7,5"}}, {}, r"sólo un riel .* el builder es «box»"),
]


@pytest.mark.parametrize("bloque,extra,mensaje", MALOS)
def test_un_bloque_mal_escrito_no_carga(tmp_path, bloque, extra, mensaje):
    with pytest.raises(ValueError, match=r"Componente 'R': tablero") as exc:
        _cargar(tmp_path, bloque, **extra)
    assert re.search(mensaje, str(exc.value)), str(exc.value)
