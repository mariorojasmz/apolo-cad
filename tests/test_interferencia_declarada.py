"""Plan puerta-fuera-de-catalogo F3 (D6): una unión declarada no tapa una interferencia de volumen
(`union.interferencia_declarada`).

El caso que lo motivó: la silla plegable aprobó con 9 903 mm³ de travesaño dentro de la pata porque
entre los dos había un `fasten` (la entrega excluye el par entero). La rosca engranada (pie
nivelador o espárrago en su agujero de broca de roscar) es volumen intencional: los cinco casos
reales de la F0 no fallan.
"""

from __future__ import annotations

import math

import pytest

from apolo.doc.document import Document
from apolo.library.calidad import interferencia_declarada as idc
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR
from apolo.library.calidad.registro import REGISTRO, VERSION_REGISTRO, evaluar
from apolo.library.checks import EXCESS_TOL_MM3
from apolo.services.calidad_interferencia_declarada import interferencia_declarada


def _juzgar(doc) -> dict:
    return idc.interferencia_declarada({"interferencia_declarada": interferencia_declarada(doc)})


def _pata_y_travesano(d: Document, penetra_mm: float, fasten: str | None = "soldadura"):
    """Pata 40×40×600 y un travesaño 400×30×30 que entra `penetra_mm` en ella (900 mm³ por mm)."""
    pata = d.execute("create_box", {"name": "Pata (1)", "width": 40, "depth": 40, "height": 600,
                                    "position": {"z": 300}})
    trav = d.execute("create_box", {"name": "Travesaño (1)", "width": 400, "depth": 30,
                                    "height": 30, "position": {"x": 20 + 200 - penetra_mm,
                                                               "z": 400}})
    if fasten:
        d.execute("fasten", {"name": "trav_pata", "a": trav, "b": pata, "kind": fasten})
    return pata, trav


# ------------------------------------------------------------------ el caso de la silla
def test_el_travesano_metido_en_la_pata_con_su_union_falla_con_el_par_y_el_volumen():
    d = Document("silla")
    pata, trav = _pata_y_travesano(d, 9903 / 900)
    r = _juzgar(d)
    assert r["estado"] == FALLA
    (s,) = r["evidencia"]["solapes"]
    assert {s["a"], s["b"]} == {pata, trav}
    assert s["volumen_mm3"] == pytest.approx(9903, abs=1)
    assert s["uniones"] == ["trav_pata"] and s["kinds"] == ["soldadura"]
    assert "9903.0 mm³ comunes bajo trav_pata (soldadura)" in r["detalle"]
    assert set(r["piezas"]) == {pata, trav}


@pytest.mark.parametrize("kind", ["contacto", "pegado", "perno"])
def test_cualquier_tipo_de_union_declarada_falla_igual(kind):
    d = Document("silla")
    _pata_y_travesano(d, 5.0, kind)  # 4 500 mm³
    assert _juzgar(d)["estado"] == FALLA


def test_cara_con_cara_y_un_asiento_dentro_de_la_tolerancia_pasan():
    d = Document("silla")
    _pata_y_travesano(d, 0.0)  # soldado a tope: se tocan, no comparten volumen
    r = _juzgar(d)
    assert r["estado"] == OK and r["evidencia"]["pares"] == 1
    d2 = Document("silla")
    _pata_y_travesano(d2, 0.05)  # 45 mm³ ≤ 50: un asiento, como en los pares no declarados
    assert 0.05 * 900 <= EXCESS_TOL_MM3
    assert _juzgar(d2)["estado"] == OK


def test_un_par_sin_union_sigue_por_la_entrega_como_hoy():
    from apolo.services.delivery_inputs import delivery_inputs

    d = Document("silla")
    pata, trav = _pata_y_travesano(d, 9903 / 900, fasten=None)
    base = d.execute("create_box", {"name": "Placa base", "width": 200, "depth": 200,
                                    "height": 10, "position": {"z": -5}})
    d.execute("fasten", {"name": "pata_base", "a": pata, "b": base, "kind": "soldadura"})
    assert _juzgar(d)["estado"] == OK  # el par sin unión no es de este ítem
    inter = delivery_inputs(d, expand=lambda x: x)["interferencias"]
    assert [{i["a"], i["b"]} for i in inter] == [{pata, trav}]


# ------------------------------------------------------------------ la rosca engranada
#: (métrica, espesor de la pieza roscada, volumen de la F0): pie M16 en placa de 12, espárrago M10
#: en buje de 21 (cilindro), pies M10/M12 en placas de 8, 1/4″ y 10 mm.
ROSCAS = [("M16", 12.0, 565.5, "placa"), ("M10", 21.0, 457.7, "buje"),
          ("M10", 8.0, 174.3, "placa"), ("M12", 6.35, 199.3, "placa"),
          ("M10", 10.0, 217.9, "placa")]


def _roscado(metrica: str, t: float, forma: str, broca: str | None = None, sin_agujero=False):
    d = Document("pie")
    if forma == "placa":
        pieza = d.execute("create_box", {"name": "Placa de pie", "width": 80, "depth": 80,
                                         "height": t, "position": {"z": t / 2}})
    else:
        pieza = d.execute("create_cylinder", {"name": "Buje", "radius": 15, "height": t,
                                              "position": {"z": t / 2}})
    if not sin_agujero:
        taladro = {"feature": pieza, "position": {"x": 0, "y": 0, "z": t}, "axis": "-z"}
        taladro.update({"thread": metrica} if broca is None else {"diameter": broca})
        d.execute("drill_hole", taladro)
    dn = float(metrica[1:])
    pie = d.execute("create_cylinder", {"name": f"Pie nivelador {metrica} (vástago)",
                                        "radius": dn / 2, "height": t + 60,
                                        "position": {"z": t / 2 + 10}})
    d.execute("fasten", {"name": "pie_placa", "a": pie, "b": pieza, "kind": "contacto"})
    return d


@pytest.mark.parametrize("metrica,t,volumen,forma", ROSCAS,
                         ids=[f"{m}-{t:g}-{f}" for m, t, _v, f in ROSCAS])
def test_la_rosca_engranada_no_cuenta(metrica, t, volumen, forma):
    d = _roscado(metrica, t, forma)
    ins = interferencia_declarada(d)
    (s,) = ins["solapes"]
    assert s["volumen_mm3"] == pytest.approx(volumen, abs=0.2)  # la cifra de la F0
    r = idc.interferencia_declarada({"interferencia_declarada": ins})
    assert r["estado"] == OK, r["detalle"]
    (rosca,) = r["evidencia"]["roscas_engranadas"]
    assert rosca["rosca"] == metrica and rosca["enganche_mm"] == pytest.approx(t, abs=0.05)


def test_el_vastago_en_un_agujero_mas_chico_o_sin_agujero_falla():
    # M16 en Ø12 (no es la broca de M16, 14): el anillo no es de rosca, todo el volumen cuenta
    assert _juzgar(_roscado("M16", 12.0, "placa", broca=12.0))["estado"] == FALLA
    # sin agujero: el vástago macizo dentro de la placa (2 412 mm³)
    assert _juzgar(_roscado("M16", 12.0, "placa", sin_agujero=True))["estado"] == FALLA


def test_lo_que_supera_la_rosca_si_cuenta():
    fila = {"a": "p", "b": "q", "uniones": ["u"], "kinds": ["contacto"], "volumen_mm3": 1565.5,
            "solidos": [{"volumen_mm3": 1565.5,
                         "anillos": [{"d_ext": 16.0, "d_int": 14.0, "largo_mm": 12.0}]}]}
    ex, roscas = idc.exceso(fila)
    assert roscas[0]["rosca"] == "M16"
    assert ex == pytest.approx(1565.5 - 565.49 * 1.05, abs=0.5)
    r = idc.interferencia_declarada({"interferencia_declarada": {"pares": 1, "solapes": [fila]}})
    assert r["estado"] == FALLA and "rosca engranada" in r["detalle"]


def test_rosca_de_y_anillo():
    assert idc.rosca_de(16.0, 14.0) == "M16" and idc.rosca_de(10.0, 8.5) == "M10"
    assert idc.rosca_de(16.0, 12.0) is None and idc.rosca_de(11.0, 8.5) is None
    assert idc.anillo_mm3("M16", 12) == pytest.approx(math.pi / 4 * (256 - 196) * 12)


# ------------------------------------------------------------------ lo que no se mide
def test_seeger_y_cable_no_se_miden():
    d = Document("rodillo")
    tubo = d.execute("create_cylinder", {"name": "Rodillo de cola", "radius": 40, "height": 300,
                                         "axis": "y"})
    seeger = d.execute("create_cylinder", {"name": "Tensor · Anillo Seeger DIN 472-72 (1)",
                                           "radius": 38, "height": 2, "axis": "y",
                                           "position": {"y": 140}})
    cable = d.execute("create_cylinder", {"name": "Cable motor 4x2.5 mm2 (variador -> motor)",
                                          "radius": 6, "height": 200, "axis": "x"})
    tira = d.execute("create_cylinder", {"name": "Tirafondo 4,5x50 travesano-pata del. (-X)",
                                         "radius": 2.25, "height": 50, "position": {"z": 30}})
    d.execute("fasten", {"name": "s", "a": tubo, "b": seeger, "kind": "contacto"})
    d.execute("fasten", {"name": "c", "a": cable, "b": tubo, "kind": "contacto"})
    d.execute("fasten", {"name": "t", "a": tira, "b": tubo, "kind": "contacto"})
    r = _juzgar(d)
    assert r["estado"] == OK and r["evidencia"]["pares"] == 0
    # el rol va anclado: un «Taco del tirafondo» metido en el rodillo sí se mide
    taco = d.execute("create_box", {"name": "Taco del tirafondo", "width": 20, "depth": 20,
                                    "height": 20, "position": {"x": 40}})
    d.execute("fasten", {"name": "k", "a": taco, "b": tubo, "kind": "pegado"})
    assert _juzgar(d)["estado"] == FALLA


def test_la_pieza_entera_dentro_de_un_equipo_de_catalogo_esta_alojada():
    fila = {"a": "c1", "b": "c2", "uniones": ["u"], "kinds": ["perno"], "volumen_mm3": 1000.0,
            "solidos": [{"volumen_mm3": 1000.0, "anillos": []}], "catalogo_a": False,
            "catalogo_b": True, "volumen_a_mm3": 1000.0, "volumen_b_mm3": 4.0e7}
    assert idc.alojada(fila) == "c1" and idc.exceso(fila) == (0.0, [])
    r = idc.interferencia_declarada({"interferencia_declarada": {"pares": 1, "solapes": [fila]}})
    assert r["estado"] == OK and r["evidencia"]["alojadas_en_catalogo"] == [
        {"pieza": "c1", "en": "c2"}]
    # dentro de una pieza A MEDIDA maciza: falla
    assert idc.alojada({**fila, "catalogo_b": False}) is None
    # a medias dentro del equipo: no está alojada
    assert idc.alojada({**fila, "volumen_a_mm3": 2000.0}) is None


def test_sin_medir_y_con_error_sale_sin_evaluar():
    assert idc.interferencia_declarada({})["estado"] == SIN_EVALUAR
    assert idc.interferencia_declarada(
        {"interferencia_declarada": {"error": "x"}})["estado"] == SIN_EVALUAR
    r = idc.interferencia_declarada({"interferencia_declarada": {
        "pares": 1, "solapes": [], "errores": [{"a": "p", "b": "q", "error": "OCCT"}]}})
    assert r["estado"] == SIN_EVALUAR and r["piezas"] == ["p", "q"]


# ------------------------------------------------------------------ en el registro
def test_el_item_esta_en_el_registro_y_no_aplica_sin_uniones():
    assert int(VERSION_REGISTRO) >= 36  # la F3 la subió a 36; las fases siguientes la suben más
    assert idc.ENTRADA in REGISTRO
    r = evaluar({"hechos": {"uniones_declaradas": False}}, registro=(idc.ENTRADA,))
    (it,) = r["items"]
    assert (it["id"], it["estado"], it["familia"]) == (
        "union.interferencia_declarada", NO_APLICA, "montaje")
