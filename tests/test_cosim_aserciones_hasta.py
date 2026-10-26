"""`siempre`/`nunca … hasta <ancla> [+ N s|ms]` (plan trabas-de-modelado, D4), puras, sobre el
resultado armado a mano de `test_cosim_aserciones.py`. La repro: el modelador escribió «caja_1.x_mm
> 2495 nunca desde pulsar -S1 + 6 s y antes» y recibió un 400 que hablaba del ancla."""

from __future__ import annotations

import copy
import re

import pytest

from apolo.cosim.escenario import EscenarioInvalido, leer_escenario
from apolo.cosim.veredicto import evaluar
from test_cosim_aserciones import ACCIONES, EVENTOS, RES


def _una(asercion, res=RES):
    esc = leer_escenario({"duracion_s": 4, "acciones": ACCIONES, "eventos": EVENTOS,
                          "aserciones": [asercion]})
    [fila] = evaluar(esc.aserciones, res)["aserciones"]
    return fila


@pytest.mark.parametrize("asercion,pasa", [
    # en_marcha sube a 0,31 s; -S1 se pulsa a 0,3 s
    ("-K1.Main.en_marcha nunca hasta pulsar -S1", True),
    ("-K1.Main.en_marcha nunca hasta pulsar -S1 + 50 ms", False),
    ("-K1.Main.en_marcha nunca hasta pulsar -S1 + 0,005 s", True),
    # caja.x_mm pasa 0 a los 2 s: «nunca > 0 hasta el atasco (2 s)» toca el 0 exacto, no > 0
    ("caja.x_mm > 0 nunca hasta atasco", True),
    ("caja.x_mm > 0 nunca hasta atasco + 1 s", False),
    # desde … hasta: en marcha de 0,31 a 2,21; la seta a 2,2
    ("-K1.Main.en_marcha siempre desde pulsar -S1 + 20 ms hasta presionar -S0", True),
    ("-K1.Main.en_marcha siempre desde pulsar -S1 hasta presionar -S0", False),       # 0,30: aún no
    ("-K1.Main.en_marcha siempre desde pulsar -S1 + 20 ms hasta presionar -S0 + 20 ms", False),
    ({"senal": "-K1.Main.en_marcha", "ventana": "nunca", "hasta": "pulsar -S1", "hasta_tras_ms": 50},
     False),
])
def test_hasta_corta_la_ventana_en_el_ancla(asercion, pasa):
    fila = _una(asercion)
    assert fila["pasa"] is pasa, fila


def test_texto_y_objeto_son_la_misma_asercion():
    esc = leer_escenario({"duracion_s": 4, "acciones": ACCIONES, "aserciones": [
        "caja.x_mm > 2495 nunca hasta pulsar -S1 + 6 s",
        {"senal": "caja.x_mm", "op": ">", "valor": 2495, "ventana": "nunca", "hasta": "pulsar -S1",
         "hasta_tras_ms": 6000}]})
    a, b = esc.aserciones
    assert a == b and a["texto"] == "caja.x_mm > 2495 nunca hasta pulsar -S1 + 6 s"
    esc = leer_escenario({"duracion_s": 4, "acciones": ACCIONES, "aserciones": [
        "-K1.Main.en_marcha siempre desde pulsar -S1 + 20 ms hasta presionar -S0 + 250 ms"]})
    assert esc.aserciones[0]["texto"] == ("-K1.Main.en_marcha siempre desde pulsar -S1 + 20 ms hasta "
                                          "presionar -S0 + 250 ms")


@pytest.mark.parametrize("asercion,dice", [
    ("caja.x_mm > 2495 nunca desde pulsar -S1 + 6 s y antes", "nunca hasta pulsar -S1 + 6 s"),
    ("-M1.rpm >= 1700 dentro_de 3 s desde pulsar -S1 hasta presionar -S0", "va con siempre o nunca"),
    ("-K1.Main.en_marcha nunca hasta pulsar -S9", "no tiene «pulsar -S9»"),
    ({"senal": "-K1.Main.en_marcha", "ventana": "nunca", "hasta_tras_ms": 5}, "pide «hasta <ancla>»"),
])
def test_errores_al_declarar(asercion, dice):
    with pytest.raises(EscenarioInvalido, match=re.escape(dice)):
        leer_escenario({"duracion_s": 4, "acciones": ACCIONES, "eventos": EVENTOS,
                        "aserciones": [asercion]})


def test_un_hasta_que_no_ocurrio_o_antes_del_desde_falla_con_su_motivo():
    res = copy.deepcopy(RES)
    res["eventos"] = [e for e in res["eventos"] if e.get("dispositivo") != "-S0"]
    fila = _una("-K1.Main.en_marcha nunca hasta presionar -S0", res)
    assert not fila["pasa"] and "no ocurrió" in fila["detalle"]
    fila = _una("-K1.Main.en_marcha nunca desde presionar -S0 hasta pulsar -S1")
    assert not fila["pasa"] and "antes de empezar" in fila["detalle"]
