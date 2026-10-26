"""El bloque `flujo` del escenario, las señales del balance en el veredicto y la regla de las
puertas (plan balance-de-producto, D1–D3, D7–D10, D13). Puro: sin simular (los resultados son
los que daría la dinámica, `tests/test_flujo_dinamica.py` los produce de verdad)."""

from __future__ import annotations

import copy

import pytest

from apolo.cosim.escenario import EscenarioInvalido, leer_escenario
from apolo.cosim.flujo import resumen, texto_balance
from apolo.cosim.veredicto import evaluar
from apolo.doc.document import Document
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR
from apolo.library.calidad.registro import evaluar as evaluar_puerta
from apolo.library.delivery import ROJO, delivery_report
from apolo.services import escenarios as E
from apolo.services import flujo_producto as FP
from apolo.services.errors import ServiceError

SUMIDEROS = [{"nombre": "rampa", "punto_mm": [900, 0, 0], "normal": [1, -6, 0]},
             {"nombre": "fin", "punto_mm": [1400, 0, 0], "normal": [1, 0, 0]}]
CAJA = {"tipo": "producto", "dims_mm": [150, 120, 100], "masa_kg": 2.0}


def _esc(ritmo=30, aserciones=("flujo.cuadra al_final",), **extra) -> dict:
    return {"duracion_s": 14, "mecanica": {"sumideros": copy.deepcopy(SUMIDEROS)},
            "eventos": [{**CAJA, "nombre": "izq", "posicion_mm": [-1000, -120, 850.5]},
                        {**CAJA, "nombre": "der", "posicion_mm": [-1000, 120, 850.5]}],
            "flujo": {"plazo_s": 8, **({"ritmo_por_min": ritmo} if ritmo is not None else {})},
            "aserciones": list(aserciones), **extra}


# ── lectura ────────────────────────────────────────────────────────────────────────────────


def test_el_ritmo_reparte_las_series_alternadas():
    e = leer_escenario(_esc())
    izq, der = e.productos
    assert (izq["cada_s"], izq["desde_s"]) == (4.0, 0.0)   # T = 2 s; dos series: cada 4 s
    assert (der["cada_s"], der["desde_s"]) == (4.0, 2.0)   # desfasada T: alternan
    assert e.flujo["ritmo_por_min"] == 30.0 and e.flujo["quieto_s"] == 2.0
    assert e.flujo["sumideros"] == ["rampa", "fin"]


def test_sin_ritmo_el_ritmo_sale_de_las_series():
    esc = _esc(ritmo=None)
    esc["eventos"][0]["cada_s"] = 3.0
    e = leer_escenario(esc)
    assert e.flujo["ritmo_por_min"] == 20.0  # sólo la serie con cada_s; la otra es una caja suelta


def test_el_ritmo_no_arrastra_el_redondeo_de_cada_s():
    """Trabas de flujo: 18/min da `cada_s` = 3,333333 s; el ritmo es el declarado (18), y sin él,
    Σ 60/`cada_s` a la milésima (18,0, no 18,000002)."""
    esc = _esc(ritmo=18)
    esc["eventos"] = esc["eventos"][:1]
    e = leer_escenario(esc)
    assert e.productos[0]["cada_s"] == 3.333333 and e.flujo["ritmo_por_min"] == 18.0
    esc = _esc(ritmo=None)
    esc["eventos"][0]["cada_s"] = 3.333333
    assert leer_escenario(esc).flujo["ritmo_por_min"] == 18.0


def test_un_escenario_sin_flujo_se_lee_igual():
    esc = _esc()
    del esc["flujo"]
    esc["aserciones"] = []
    antes = copy.deepcopy(esc)
    e = leer_escenario(esc)
    assert e.flujo is None and esc == antes
    assert "cada_s" not in e.productos[0]
    assert e.mecanica["sumideros"][0]["nombre"] == "rampa"   # el nombre sólo se valida
    assert E.hash_escenario(esc) == E.hash_escenario(antes)


def test_los_sumideros_toman_su_nombre_por_defecto_sin_tocar_el_dict():
    esc = _esc()
    for s in esc["mecanica"]["sumideros"]:
        del s["nombre"]
    esc["aserciones"] = ["flujo.sumidero_2 >= 1 al_final"]
    e = leer_escenario(esc)
    assert e.flujo["sumideros"] == ["sumidero_1", "sumidero_2"]
    assert "nombre" not in esc["mecanica"]["sumideros"][0]


@pytest.mark.parametrize("cambio, texto", [
    (lambda e: e["flujo"].pop("plazo_s"), "falta «plazo_s»"),
    (lambda e: e["mecanica"].pop("sumideros"), "al menos un sumidero"),
    (lambda e: e["mecanica"]["sumideros"][1].update(nombre="rampa"), "nombres repetidos"),
    (lambda e: e["mecanica"]["sumideros"][0].update(nombre="fin de faja"), "sin espacios ni puntos"),
    (lambda e: e["mecanica"]["sumideros"][0].update(nombre="trabados"), "señal fija"),
    (lambda e: e["eventos"][0].update(cada_s=2), "quita «cada_s»"),
    (lambda e: e["flujo"].update(ritmo_por_minuto=30), "¿Quisiste decir «ritmo_por_min»?"),
    (lambda e: e["flujo"].update(ritmo_por_min="nominal"), "lo resuelve el documento"),
    (lambda e: e.update(aserciones=["flujo.rampas >= 1 al_final"]), "¿Quisiste decir «flujo.rampa»?"),
    (lambda e: (e.pop("flujo"), e.update(aserciones=["flujo.cuadra al_final"])), "no declara «flujo»"),
    (lambda e: e["flujo"].update(zonas_espera=[{"min_mm": [0, 0, 0], "max_mm": [0, 1, 1]}]),
     "menor que «max_mm»"),
])
def test_lo_que_no_se_puede_leer_dice_como_arreglarlo(cambio, texto):
    esc = _esc()
    cambio(esc)
    with pytest.raises(EscenarioInvalido, match=texto):
        leer_escenario(esc)


# ── el veredicto ───────────────────────────────────────────────────────────────────────────


def _flujo(cuadra=True, trabado=False) -> dict:
    trabados = ([{"producto": "p_der_1", "desde_s": 6.4, "t": 8.4, "pos_mm": [512.0, 120.0, 849.9]}]
                if trabado else [])
    return {"plazo_s": 8.0, "quieto_s": 2.0, "sumideros": ["rampa", "fin"], "entraron": 7, "salieron": 5,
            "por_sumidero": {"rampa": 3, "fin": 2}, "perdidos": [], "trabados": trabados,
            "retenidos": [], "en_transito": ["p_izq_3", "p_der_2"], "sin_entrar": [], "demorados": [],
            "transito_max_s": 4.85, "cuadra": cuadra,
            "senales": {"flujo.cuadra": [[0.0, True]] + ([[8.4, False]] if not cuadra else []),
                        "flujo.rampa": [[0.0, 0], [2.4, 1], [6.4, 2], [10.4, 3]],
                        "flujo.trabados": [[0.0, 0]] + ([[8.4, 1]] if trabado else [])}}


def _res(fl) -> dict:
    return {"resumen": {"duracion_s": 14.0}, "trazas": {"discretas": {}}, "final": {},
            "mecanica": {"flujo": fl}}


def _aserciones(*textos):
    return leer_escenario(_esc(aserciones=textos)).aserciones


def test_las_senales_del_flujo_se_afirman_como_las_del_tablero():
    v = evaluar(_aserciones("flujo.cuadra al_final", "flujo.rampa == 3 al_final",
                            "flujo.rampa >= 2 en 7 s", "flujo.trabados > 0 nunca"), _res(_flujo()))
    assert v["veredicto"] == "pasa", v


def test_un_trabado_falla_con_el_producto_el_lugar_y_la_hora():
    res = _res(_flujo(cuadra=False, trabado=True))
    v = evaluar(_aserciones("flujo.cuadra al_final", "flujo.trabados > 0 nunca"), res)
    assert v["veredicto"] == "falla" and v["n_fallidas"] == 2
    for fila in v["aserciones"]:
        assert "p_der_1 trabado en (512, 120, 850) mm desde t = 6.4 s" in fila["detalle"], fila
    assert "trazas" in res and res["final"] == {}  # el Lector no toca el resultado


def test_el_texto_del_balance():
    fl = _flujo(cuadra=False, trabado=True)
    assert texto_balance(fl) == "7 entraron · 3 rampa · 2 fin · 1 trabados"
    r = resumen(fl)
    assert "senales" not in r and r["n_trabados"] == 1 and r["balance"] == texto_balance(fl)
    fl["perdidos"] = [{"producto": "x", "t": 1.0, "pos_mm": [0, 0, 50]}]
    assert texto_balance(fl).endswith("1 trabados · 1 perdidos")


# ── la regla de las puertas ────────────────────────────────────────────────────────────────


def _doc(ppm=30) -> Document:
    d = Document("flujo")
    if ppm:
        d.set_requirements({"paquetes_por_minuto": ppm})
    return d


def _guardar(doc, nombre, esc, fl):
    E.poner(doc, nombre, esc)
    esc = doc.escenarios[nombre]["escenario"]
    ver = evaluar(leer_escenario(esc).aserciones, _res(fl))
    E.guardar_resultado(doc, nombre, E.resultado_compacto(
        ver, _res(fl), firma=E.firma_documento(doc), hash_esc=E.hash_escenario(esc), simulacion=None))


def _puerta(doc) -> dict:
    ins = {"hechos": {"mueve_producto": FP.mueve_producto(doc)}, "flujo": FP.evaluar(doc)}
    items = evaluar_puerta(ins)["items"]
    return next(i for i in items if i["id"] == "funcion.flujo_de_producto")


def test_sin_producto_no_aplica():
    doc = _doc()
    assert FP.evaluar(doc)["estado"] == "no_aplica" and FP.regla_entrega(doc) is None
    assert _puerta(doc)["estado"] == NO_APLICA


def test_sin_escenario_de_flujo_sale_sin_evaluar_con_la_accion():
    doc = _doc()
    esc = _esc()
    del esc["flujo"]
    esc["aserciones"] = []
    E.poner(doc, "marcha", esc)  # mueve producto (cajas en un escenario), sin balance
    it = _puerta(doc)
    assert it["estado"] == SIN_EVALUAR and "set_scenario" in it["detalle"] and "flujo.cuadra" in it["detalle"]
    assert FP.regla_entrega(doc)["estado"] == "aviso"


def test_sin_capacidad_nominal_sale_sin_evaluar():
    doc = _doc(ppm=None)
    E.poner(doc, "flujo", _esc())
    r = FP.evaluar(doc)
    assert r["estado"] == "falta" and "paquetes_por_minuto" in r["accion"]
    with pytest.raises(ServiceError, match="paquetes_por_minuto"):
        E.poner(doc, "otro", _esc(ritmo="nominal"))


def test_declarado_sin_correr_pide_correrlo_y_corrido_cuadra_ok():
    doc = _doc()
    E.poner(doc, "flujo", _esc(ritmo="nominal"))
    assert doc.escenarios["flujo"]["escenario"]["flujo"]["ritmo_por_min"] == 30.0
    r = FP.evaluar(doc)
    assert r["estado"] == "falta" and r["accion"].startswith("córrelo")
    _guardar(doc, "flujo", doc.escenarios["flujo"]["escenario"], _flujo())
    assert _puerta(doc)["estado"] == OK
    assert FP.regla_entrega(doc)["estado"] == "ok"
    assert E.listar(doc)["escenarios"][0]["balance"] == "7 entraron · 3 rampa · 2 fin · 0 trabados"


def test_el_balance_roto_es_falla_y_rojo_con_el_producto_y_la_hora():
    doc = _doc()
    _guardar(doc, "flujo", _esc(), _flujo(cuadra=False, trabado=True))
    it = _puerta(doc)
    assert it["estado"] == FALLA and "p_der_1 trabado" in it["detalle"] and "6.4 s" in it["detalle"]
    fila = FP.regla_entrega(doc)
    assert fila["estado"] == "error"
    rep = delivery_report(interferencias=[], soundness={"has_ground": True, "floating": []},
                          n_solidos=0, lints=[], integridad=[], suprimidos=[], poses=None, flujo=fila)
    assert rep["veredicto"] == ROJO and rep["bloqueantes"][0]["regla"] == "balance de producto"


def test_el_margen_es_un_dato_no_un_veredicto():
    doc = _doc()
    _guardar(doc, "flujo", _esc(), _flujo())
    _guardar(doc, "a_36", _esc(ritmo=36, aserciones=()), _flujo(cuadra=False, trabado=True))
    r = FP.evaluar(doc)
    assert r["estado"] == "ok"
    (m,) = r["margen"]
    assert m["escenario"] == "a_36" and m["sobre_nominal_pct"] == 20.0 and m["cuadra"] is False
    assert _puerta(doc)["evidencia"]["margen"][0]["balance"].endswith("1 trabados")


def test_un_ritmo_por_debajo_del_nominal_no_cubre():
    doc = _doc(ppm=40)
    _guardar(doc, "flujo", _esc(), _flujo())  # a 30/min
    r = FP.evaluar(doc)
    assert r["estado"] == "falta" and "«flujo» a 30/min" in r["detalle"]
