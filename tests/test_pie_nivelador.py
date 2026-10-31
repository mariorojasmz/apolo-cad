"""`apoyo.nivelador` (plan pie-nivelador, F2: D1–D4 y D8 con la Bitácora § F0): cada pie nivelador
engancha su rosca, va trabado y nivela lo que pide el piso.

Fixtures sintéticas con los casos que midió la F0 en la tanda: la placa de 8 mm sin tuerca del lado
de la carga (mesa de ensamble atornillada), 6,35 mm en M12, la placa de 12 mm + tuerca a tope en
M16 (mesa Ø28), la tuerca alta DIN 6334 (mesa de bolas), material en el eje, la contratuerca de la
pila (mesa Ø16), la traba fundida (mesa inox con poza), el parche declarado (mesa inox), sin traba,
la carrera corta y el requisito `nivelacion_mm`; y los pies de las plantillas (faja y rodillos)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from apolo.doc import Document
from apolo.library.calidad import pie_nivelador as pn
from apolo.library.calidad.interferencia_declarada import interferencia_declarada as juzgar_idc
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR
from apolo.library.calidad.registro import REGISTRO, VERSION_REGISTRO, evaluar
from apolo.library.catalog import CATALOG
from apolo.services import puerta_publicacion as pp
from apolo.services.calidad_interferencia_declarada import interferencia_declarada
from apolo.services.calidad_pies import pies_niveladores

TESTIGOS = Path(__file__).resolve().parent / "data" / "testigos"


# ------------------------------------------------------------------ armar los casos
def _pie(d, ref: str = "PIE-M10-40", x: float = 0.0) -> str:
    """Un pie de catálogo con la cara de apoyo de su base en z = 0."""
    p = CATALOG[ref].params
    return d.execute("insert_component", {"component": ref, "position": {
        "x": x, "y": 0, "z": float(p["altura"]) / 2.0 + float(p["disco_t"])}})


def _placa(d, z0: float, t: float, x: float = 0.0, rosca: str | None = None,
           paso: float | None = None, nombre: str = "Placa de la pata") -> str:
    pl = d.execute("create_box", {"name": nombre, "width": 80, "depth": 80, "height": t,
                                  "position": {"x": x, "y": 0, "z": z0 + t / 2.0}})
    if rosca or paso:
        d.execute("drill_hole", {"feature": pl, "position": {"x": x, "y": 0, "z": z0 + t},
                                 "axis": "-z", **({"thread": rosca} if rosca else {}),
                                 "diameter": paso or 8})
    return pl


def _tuerca(d, ref: str, z0: float, x: float = 0.0, nombre: str | None = None) -> str:
    m = float(CATALOG[ref].params["thickness"])
    return d.execute("insert_component", {"component": ref, **({"name": nombre} if nombre else {}),
                                          "position": {"x": x, "y": 0, "z": z0 + m / 2.0}})


def _hexagono(sw: float) -> list[list[float]]:
    r = sw / math.sqrt(3)
    return [[r * math.cos(math.radians(60 * k)), r * math.sin(math.radians(60 * k))]
            for k in range(6)]


def _pie_a_mano(d, nombre: str, dn: float, largo: float, base_d: float, base_t: float,
                x: float = 0.0, hexagono: tuple | None = None) -> str:
    """Base Ø base_d × base_t en z = 0 y vástago Ø dn de `largo` encima (y un hexágono fundido
    (sw, z0, h) en el vástago)."""
    base = d.execute("create_cylinder", {"name": "Base", "radius": base_d / 2.0, "height": base_t,
                                         "position": {"x": x, "y": 0, "z": base_t / 2.0}})
    vas = d.execute("create_cylinder", {"name": "Vástago", "radius": dn / 2.0,
                                        "height": largo + 1.0,
                                        "position": {"x": x, "y": 0,
                                                     "z": base_t + largo / 2.0 - 0.5}})
    tools = [base]
    if hexagono:
        sw, z0, h = hexagono
        tools.append(d.execute("create_extrude_poly", {
            "name": "Tuerca fundida", "points": _hexagono(sw), "height": h,
            "position": {"x": x, "y": 0, "z": z0 + h / 2.0}}))
    d.execute("boolean_op", {"name": nombre, "operation": "union", "target": vas, "tools": tools})
    return next(fid for fid, f in d.scene.items() if f.name == nombre)


def _caso(d, fid: str) -> dict:
    datos = pies_niveladores(d)
    r = pn.nivelador({"pies_niveladores": datos,
                      "justificadas": getattr(d, "justificadas", None)})
    return next(c for c in r["evidencia"]["casos"] if c["id"] == fid)


# ------------------------------------------------------------------ D1: qué es un pie
def test_reconoce_el_de_catalogo_y_el_a_mano_por_rol_y_geometria():
    d = Document("pies")
    cat = _pie(d)
    mano = _pie_a_mano(d, "Pie nivelador M10 (compra)", 10, 50, 60, 10, x=300)
    caja = d.execute("create_box", {"name": "Pie nivelador M12 (compra)", "width": 60, "depth": 60,
                                    "height": 12, "position": {"x": 600, "y": 0, "z": 6}})
    # un disco con un agujero (cilindro CÓNCAVO, el caladrillo de la F0) no es un vástago
    disco = d.execute("create_cylinder", {"name": "Nivelador M10 con buje", "radius": 30,
                                          "height": 12, "position": {"x": 900, "y": 0, "z": 6}})
    d.execute("drill_hole", {"feature": disco, "position": {"x": 900, "y": 0, "z": 12},
                             "axis": "-z", "diameter": 10})
    # sin rol de pie nivelador no se mira: una pata de madera, una garrucha
    d.execute("create_box", {"name": "Pie (1)", "width": 40, "depth": 40, "height": 400,
                             "position": {"x": 1200, "y": 0, "z": 200}})
    _pie_a_mano(d, "Garrucha Ø100", 10, 50, 60, 10, x=1500)
    datos = pies_niveladores(d)
    assert {p["id"]: p["por"] for p in datos["pies"]} == {cat: "catalogo", mano: "geometria"}
    assert {n["id"] for n in datos["no_reconocidos"]} == {caja, next(
        f for f, x in d.scene.items() if x.name == "Nivelador M10 con buje")}
    pie = next(p for p in datos["pies"] if p["id"] == cat)
    assert pie["d"] == 10.0 and pie["vastago"] == [12.0, 52.0] and pie["dir"][2] == 1.0


def test_lo_no_reconocido_es_sin_evaluar_y_se_justifica():
    datos = {"pies": [], "no_reconocidos": [{"id": "p1", "nombre": "Pie nivelador", "motivo": "x"}]}
    r = pn.nivelador({"pies_niveladores": datos})
    assert r["estado"] == SIN_EVALUAR and r["piezas"] == ["p1"]
    js = [{"regla": pn.REGLA_NO_RECONOCIDO, "pieza": "p1",
           "porque": "es un regatón de goma sin rosca: no regula ni se nivela"}]
    r = pn.nivelador({"pies_niveladores": datos, "justificadas": js})
    assert r["estado"] == OK and r["evidencia"]["justificadas"][0]["pieza"] == "p1"


# ------------------------------------------------------------------ D2: la rosca
def test_placa_delgada_sin_tuerca_del_lado_de_la_carga_falla():
    """Mesa de ensamble atornillada: M10 en 8 mm de placa roscada, la contratuerca ENCIMA (no
    carga): 8 < 1·d. La contratuerca sí traba. El anillo es el de la F0 (174,3 mm³)."""
    d = Document("ensamble")
    p = _pie(d)
    pl = _placa(d, 16, 8, rosca="M10")
    _tuerca(d, "TUERCA-M10", 24, nombre="Contratuerca del pie")
    c = _caso(d, p)
    assert c["estado"] == FALLA and "8.0 mm" in c["d2_rosca"] and "pide ≥ 1·d" in c["d2_rosca"]
    assert c["d3_traba"].startswith("contratuerca")
    assert c["baja_mm"] == pytest.approx(4.0, abs=0.1)  # la base toca la placa (F0: −4)
    datos = pies_niveladores(d)
    r = pn.nivelador({"pies_niveladores": datos})
    (an,) = r["evidencia"]["roscas_engranadas"]
    assert an["pieza"] == pl and an["anillo_mm3"] == pytest.approx(174.4, abs=0.2)


def test_6_35_mm_en_m12_falla_y_sin_traba():
    d = Document("soldada")
    p = _pie(d, "PIE-M12-50")
    _placa(d, 39, 6.35, rosca="M12")
    c = _caso(d, p)
    assert c["estado"] == FALLA and "6.4 mm;" in c["d2_rosca"]
    assert c["d3_traba"].startswith("sin traba")


def test_placa_de_12_mas_tuerca_a_tope_debajo_pasa_en_m16():
    """Mesa Ø28: M16 en 12 mm de placa (12 < 16 sola) + la DIN 934 a tope debajo: 25 ≥ 16; esa
    tuerca es también la contratuerca de la pila. Anillo de la F0: 565,5 mm³."""
    d = Document("d28")
    p = _pie_a_mano(d, "Pie nivelador M16x50 articulado base Ø100 (compra)", 16, 48, 100, 24)
    _placa(d, 47, 12, rosca="M16")
    _tuerca(d, "TUERCA-M16", 47 - float(CATALOG["TUERCA-M16"].params["thickness"]))
    c = _caso(d, p)
    assert c["estado"] == OK, c
    assert "tuerca a tope del lado de la carga" in c["d2_rosca"] and c["enganche_mm"] >= 24.9
    r = pn.nivelador({"pies_niveladores": pies_niveladores(d)})
    assert r["evidencia"]["roscas_engranadas"][0]["anillo_mm3"] == pytest.approx(565.5, abs=0.3)


def test_la_tuerca_alta_din_6334_es_rosca_en_pieza():
    d = Document("bolas")
    p = _pie(d, "PIE-M12-50")
    buje = d.execute("create_cylinder", {"name": "Tuerca alta DIN 6334 M12", "radius": 10,
                                         "height": 36, "position": {"x": 0, "y": 0, "z": 38}})
    d.execute("drill_hole", {"feature": buje, "position": {"x": 0, "y": 0, "z": 56},
                             "axis": "-z", "diameter": 13})
    c = _caso(d, p)
    assert c["d2_rosca"].startswith("rosca en Tuerca alta") and c["enganche_mm"] == 36.0
    assert c["pide_rosca_mm"] == 12.0 and c["sube_mm"] == pytest.approx(32.0, abs=0.1)
    d2 = Document("bolas-corta")
    p2 = _pie(d2, "PIE-M12-50")
    b2 = d2.execute("create_cylinder", {"name": "Tuerca alta DIN 6334 M12", "radius": 10,
                                        "height": 36, "position": {"x": 0, "y": 0, "z": 78}})
    d2.execute("drill_hole", {"feature": b2, "position": {"x": 0, "y": 0, "z": 96},
                              "axis": "-z", "diameter": 13})
    c2 = _caso(d2, p2)
    assert c2["estado"] == FALLA and "4.0 mm" in c2["d2_rosca"]  # 64 − 60: 4 < 12


def test_material_en_el_eje_no_se_puede_enroscar():
    d = Document("maciza")
    p = _pie(d)
    _placa(d, 42, 10, nombre="Placa base maciza")
    c = _caso(d, p)
    assert c["estado"] == FALLA and c["d2_rosca"].startswith("no se puede enroscar")


def test_nada_recibe_la_rosca_falla():
    d = Document("paso")
    p = _pie(d)
    _placa(d, 30, 8, paso=11)
    c = _caso(d, p)
    assert c["estado"] == FALLA and "nada recibe la rosca" in c["d2_rosca"]


# ------------------------------------------------------------------ D3: la traba
def test_la_contratuerca_a_tope_de_la_pila_traba():
    """Mesa Ø16: tuerca soldada SOBRE una placa de paso y la contratuerca a tope de la placa (no
    de la tuerca): traba la pila."""
    d = Document("d16")
    p = _pie(d, "PIE-M12-50")
    m = float(CATALOG["TUERCA-M12"].params["thickness"])
    _placa(d, 40, 8, paso=13.5)
    _tuerca(d, "TUERCA-M12", 48, nombre="Tuerca soldada del pie")
    _tuerca(d, "TUERCA-M12", 40 - m, nombre="Contratuerca del pie")
    c = _caso(d, p)
    assert c["estado"] == OK, c
    assert c["d2_rosca"].startswith("tuerca Tuerca soldada") and "Contratuerca" in c["d3_traba"]
    assert c["sube_mm"] == pytest.approx(64 - 48 - m, abs=0.1)
    assert c["baja_mm"] == pytest.approx(40 - m - 14, abs=0.1)


def test_la_tuerca_fundida_a_tope_de_la_pila_traba():
    d = Document("poza")
    p = _pie_a_mano(d, "Pie nivelador higiénico M10 (compra)", 10, 60, 60, 10,
                    hexagono=(17, 30, 8))
    _placa(d, 38, 12, rosca="M10")
    c = _caso(d, p)
    assert c["estado"] == OK, c
    assert c["d3_traba"].startswith("tuerca de bloqueo fundida")
    assert c["baja_mm"] == pytest.approx(38 - 10 - 8, abs=0.2)  # la tuerca va entre base y placa


def test_el_parche_declarado_traba_y_sin_el_falla():
    d = Document("inox")
    p = _pie(d, "PIE-M12-50")
    pl = _placa(d, 30, 12, rosca="M12")
    c = _caso(d, p)
    assert c["estado"] == FALLA and c["d3_traba"].startswith("sin traba")
    d.execute("fasten", {"name": "pie_buje", "a": p, "b": pl, "kind": "contacto",
                         "nota": "vástago roscado en la placa, con parche DIN 267-28"})
    c = _caso(d, p)
    assert c["estado"] == OK and c["d3_traba"].startswith("parche DIN 267-28"), c


def test_la_base_fija_soldada_traba():
    d = Document("piso")
    p = _pie(d, "PIE-M12-50")
    _placa(d, 30, 12, rosca="M12")
    piso = d.execute("create_box", {"name": "Placa de piso", "width": 150, "depth": 150,
                                    "height": 10, "position": {"x": 0, "y": 0, "z": -5}})
    d.execute("fasten", {"name": "disco_piso", "a": p, "b": piso, "kind": "soldadura",
                         "nota": "disco soldado a la placa de piso tras nivelar"})
    c = _caso(d, p)
    assert c["d3_traba"].startswith("base fija soldada"), c


# ------------------------------------------------------------------ D4: la carrera
def test_lo_que_pide_el_piso_sale_de_din_18202_o_del_requisito():
    assert pn.nivelacion_pedida(1300, None)[0] == pytest.approx(8 + 4 + 6 * 0.3 / 3)
    assert pn.nivelacion_pedida(2000, None)[0] == pytest.approx(14.0)
    assert pn.nivelacion_pedida(400, None)[0] == pytest.approx(3 + 2 + 2 * 0.3 / 0.9)
    assert pn.nivelacion_pedida(40000, None)[0] == pytest.approx(45.0)
    assert pn.nivelacion_pedida(2000, 6.0) == (6.0, "requisito nivelacion_mm")
    assert pn.nivelacion_pedida(None, None)[0] is None


def _pie_puro(sube_hasta: float, baja: float) -> dict:
    """Una tuerca soldada de 10 mm en t 30–40 y la contratuerca a tope debajo (rosca M12): sube =
    punta − 40."""
    tuerca = {"fid": "n", "nombre": "Tuerca", "rol": "tuerca", "material": "acero", "t0": 30.0,
              "t1": 40.0, "rosca": [], "en_eje": [], "autoblocante": False}
    contra = {**tuerca, "fid": "c", "nombre": "Contratuerca", "t0": 20.0, "t1": 30.0}
    return {"id": "p", "nombre": "Pie", "ref": None, "por": "geometria", "d": 12.0, "paso": 1.75,
            "vastago": [10.0, 40.0 + sube_hasta], "tramos": [contra, tuerca], "fundidas": [],
            "tuerca_ficha": None, "parche": None, "base_soldada": None, "baja_mm": baja,
            "baja_limita": "la base toca la contratuerca"}


def test_carrera_corta_falla_y_un_sentido_corto_avisa_justificable():
    assert pn.evaluar_pie(_pie_puro(10, 10), 14.1, "x")["estado"] == OK
    r = pn.evaluar_pie(_pie_puro(4, 6), 14.1, "x")  # 10 < 14,1
    assert r["estado"] == FALLA and "no alcanza a nivelar" in r["caso"]["d4_carrera"]
    r = pn.evaluar_pie(_pie_puro(20, 4), 14.1, "x")  # 24 ≥ 14,1 pero baja 4 < 7,05
    assert r["estado"] == FALLA and r["caso"]["regla"] == pn.REGLA_SENTIDO
    assert "baja menos de la mitad" in r["caso"]["d4_carrera"]
    js = [{"regla": pn.REGLA_SENTIDO, "pieza": "p",
           "porque": "la mesa se instala sobre piso nuevo con pendiente hacia el sumidero"}]
    r = pn.evaluar_pie(_pie_puro(20, 4), 14.1, "x", js)
    assert r["estado"] == OK and r["justificadas"]
    # con nivelacion_mm declarado manda el requisito
    d = {"pies": [_pie_puro(4, 6)], "no_reconocidos": [], "diagonal_mm": 2000.0,
         "nivelacion_mm": None}
    assert pn.nivelador({"pies_niveladores": d})["estado"] == FALLA
    assert pn.nivelador({"pies_niveladores": {**d, "nivelacion_mm": 8.0}})["estado"] == OK


def test_el_requisito_nivelacion_mm_llega_del_documento():
    d = Document("req")
    p = _pie(d, "PIE-M12-50")
    m = float(CATALOG["TUERCA-M12"].params["thickness"])
    _tuerca(d, "TUERCA-M12", 48, nombre="Tuerca soldada del pie")
    _tuerca(d, "TUERCA-M12", 48 - m, nombre="Contratuerca del pie")
    assert _caso(d, p)["estado"] == OK
    d.set_requirements({"nivelacion_mm": 80})
    c = _caso(d, p)
    assert c["estado"] == FALLA and c["fuente"] == "requisito nivelacion_mm"


# ------------------------------------------------------------------ D8: la rosca engranada
def test_el_anillo_del_pie_es_el_que_reconoce_la_interferencia_declarada():
    d = Document("d8")
    p = _pie(d)
    pl = _placa(d, 16, 12, rosca="M10")
    d.execute("fasten", {"name": "pie_placa", "a": p, "b": pl, "kind": "contacto",
                         "nota": "vástago roscado en la placa"})
    r = pn.nivelador({"pies_niveladores": pies_niveladores(d)})
    (an,) = r["evidencia"]["roscas_engranadas"]
    it = juzgar_idc({"interferencia_declarada": interferencia_declarada(d)})
    assert it["estado"] == OK, it
    (rosca,) = it["evidencia"]["roscas_engranadas"]
    assert rosca["anillo_mm3"] == an["anillo_mm3"] and rosca["rosca"] == an["rosca"] == "M10"


# ------------------------------------------------------------------ las plantillas y el registro
def _item(doc) -> dict:
    ins = pp.reunir(doc, expand=lambda x: x, gravedad={"resultado": None, "motivo": ""},
                    sobrantes=False)
    r = evaluar(ins)
    return {i["id"]: i for i in r["items"]}["apoyo.nivelador"]


def test_los_pies_de_la_faja_testigo_pasan_y_los_de_la_v5_no():
    doc = Document.from_apolo_bytes((TESTIGOS / "faja.apolo").read_bytes())
    it = _item(doc)
    assert it["estado"] == OK, it["detalle"]
    assert it["evidencia"]["elementos"] == {"catalogo": 4}
    assert {c["carrera"] for c in it["evidencia"]["casos"]} == {"−15 / +15"}
    (cmd,) = [c for c in doc.commands if c["type"] == "create_belt_conveyor"]
    doc.edit(cmd["id"], {**cmd["params"], "criterio": 5})  # la placa con agujero liso Ø12
    it = _item(doc)
    assert it["estado"] == FALLA and "nada recibe la rosca" in it["detalle"]


def test_los_pies_de_los_rodillos_testigo_pasan():
    doc = Document.from_apolo_bytes((TESTIGOS / "rodillos.apolo").read_bytes())
    datos = pies_niveladores(doc)
    r = pn.nivelador({"pies_niveladores": datos})
    assert r["estado"] == OK, r["detalle"]
    assert {c["d3_traba"][:17] for c in r["evidencia"]["casos"]} == {"base fija soldada"}


def test_sin_pies_no_aplica_y_el_registro_lo_lleva():
    doc = Document.from_apolo_bytes((TESTIGOS / "mensula_atornillada.apolo").read_bytes())
    assert _item(doc)["estado"] == NO_APLICA
    assert pn.ENTRADA in REGISTRO and int(VERSION_REGISTRO) >= 40  # la F2 la subió a 40
    from apolo.library.calidad import historial_registro

    assert "v42 (pie-nivelador F2" in historial_registro.__doc__
