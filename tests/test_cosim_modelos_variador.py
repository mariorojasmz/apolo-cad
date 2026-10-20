"""Variador de la co-simulación, modelo promedio (plan V8.3 F2, D7): rampa en su tiempo,
consigna por AI1 o frecuencias fijas, límite de corriente, STO de dos canales sin rearranque
automático, y las fallas por sobrecorriente, sobrecarga y red."""

from __future__ import annotations

import pytest

from apolo.cosim.modelos import ModeloIncompleto, crear_modelo
from apolo.library.catalog import CATALOG

DT = 0.002
SEGURO = {"S1": 24.0, "S2": 24.0}
RED = {"U_red_V": [220.0, 220.0, 220.0]}
MARCHA = {**RED, **SEGURO, "DI1": 24.0, "AI1": 10.0}


def vfd(ref: str = "VFD-2K2-220", **ajustes):
    return crear_modelo("-T1", ref, CATALOG[ref].electrico.modelo, ajustes)


def correr(v, segundos: float, entradas: dict) -> dict:
    out = {}
    for _ in range(round(segundos / DT)):
        out = v.paso(DT, entradas)
    return out


def test_rampa_en_el_tiempo_dado():
    v = vfd()
    assert v.acel == 10 and v.f_max == 60
    assert correr(v, 5.0, MARCHA)["f_Hz"] == pytest.approx(30.0, abs=0.1)
    s = correr(v, 5.0, MARCHA)
    assert s["f_Hz"] == pytest.approx(60.0) and s["estado"] == "marcha"
    assert s["U_V"] == pytest.approx(220.0)  # V/f: a f_base, la tensión de red
    s = correr(v, 2.5, {**MARCHA, "DI1": 0.0})  # sin marcha: baja con su rampa
    assert s["f_Hz"] == pytest.approx(45.0, abs=0.1)
    v2 = vfd(acel_s=2)
    assert correr(v2, 2.0, MARCHA)["f_Hz"] == pytest.approx(60.0)


def test_consigna_por_ai1_frecuencias_fijas_y_sentido():
    v = vfd()
    assert correr(v, 12, {**MARCHA, "AI1": 5.0})["f_Hz"] == pytest.approx(30.0)
    assert correr(v, 12, {**MARCHA, "DI4": 24.0})["f_Hz"] == pytest.approx(15.0)  # bit 0 → f_fija1
    atras = {**RED, **SEGURO, "DI2": 24.0, "AI1": 10.0}
    assert correr(v, 30, atras)["f_Hz"] == pytest.approx(-60.0)
    s = correr(vfd(), 1, {**MARCHA, "DI2": 24.0})  # adelante y atrás a la vez: no marcha
    assert s["f_Hz"] == 0 and s["estado"] == "parado"
    with pytest.raises(ModeloIncompleto, match="DI1_funcion.*no es válido"):
        vfd(DI1_funcion="arrancar")


def test_sto_corta_el_par_y_no_rearranca_sin_orden_nueva():
    v = vfd()
    correr(v, 10, MARCHA)
    s = v.paso(DT, {**MARCHA, "S1": 0.0})  # se abre UN canal
    assert s["par_habilitado"]  # dentro del tiempo de reacción
    s = correr(v, 0.010, {**MARCHA, "S1": 0.0})
    assert s["sto"] and not s["par_habilitado"] and s["U_V"] == 0 and s["f_Hz"] == 0
    assert s["estado"] == "sto" and not s["rele_falla"]  # el STO no es una falla
    s = correr(v, 1, MARCHA)  # vuelve el STO con la marcha sostenida: NO rearranca
    assert not s["sto"] and s["f_Hz"] == 0
    correr(v, 0.1, {**MARCHA, "DI1": 0.0})  # flanco: suelta y vuelve a dar marcha
    assert correr(v, 1, MARCHA)["f_Hz"] > 0


def test_limita_la_corriente_bajando_la_frecuencia():
    v = vfd()
    correr(v, 5, MARCHA)
    f0 = v.f
    s = v.paso(DT, {**MARCHA, "I_motor_A": 1.6 * 11.0})  # sobre el 150 %
    assert s["limitando"] and s["estado"] == "limitando" and s["f_Hz"] < f0
    s = correr(v, 1, {**MARCHA, "I_motor_A": 11.0})
    assert not s["limitando"] and s["f_Hz"] > f0 - 1


def test_falla_por_sobrecorriente_corta_y_se_rearma_con_flanco():
    v = vfd()
    correr(v, 5, MARCHA)
    s = v.paso(DT, {**MARCHA, "I_motor_A": 2.0 * 11.0})
    assert s["falla"] == "sobrecorriente" and s["rele_falla"] and not s["par_habilitado"]
    assert v.senales()["-T1.falla"] == "sobrecorriente" and v.senales()["-T1.estado"] == "falla"
    s = correr(v, 0.1, {**MARCHA, "DI3": 24.0})  # DI3 = rearme
    assert not s["falla"] and s["f_Hz"] == 0  # rearmado, pero espera una orden de marcha nueva
    correr(v, 0.1, {**MARCHA, "DI1": 0.0})
    assert correr(v, 1, MARCHA)["f_Hz"] > 0


def test_sobrecarga_de_placa_150_por_ciento_60_s_desde_regimen():
    v = vfd()
    correr(v, 10, MARCHA)
    v.theta = 1.0  # en régimen nominal
    t = 0.0
    while not v.falla and t < 120:
        v.paso(DT, {**MARCHA, "I_motor_A": 1.5 * 11.0 - 1e-6})
        v.f = 60.0  # sin el límite de corriente de por medio: se mide la imagen I²t
        t += DT
    assert v.falla == "sobrecarga" and t == pytest.approx(60.0, abs=0.05)


def test_fallas_de_red():
    v = vfd()
    correr(v, 5, MARCHA)
    assert correr(v, 0.010, {**MARCHA, "U_red_V": [0, 0, 0]})["falla"] == ""  # retiene 20 ms
    assert correr(v, 0.012, {**MARCHA, "U_red_V": [0, 0, 0]})["falla"] == "subtension"
    v = vfd()
    correr(v, 5, MARCHA)
    s = correr(v, 1.0, {**MARCHA, "U_red_V": [220.0, 50.0, 50.0]})
    assert s["falla"] == "perdida_fase"
    parado = vfd()
    s = correr(parado, 1, {**RED, **SEGURO, "U_red_V": [0, 0, 0]})
    assert s["estado"] == "sin_red" and not s["falla"]  # detenido: sin red no es falla


def test_determinista():
    def corrida():
        v = vfd()
        trazas = []
        for k in range(3000):
            e = {**MARCHA, "I_motor_A": 11.0 + 7.0 * ((k // 400) % 2), "S2": 0.0 if 2000 <= k < 2100 else 24.0}
            trazas.append(tuple(sorted(v.paso(DT, e).items())))
        return trazas
    assert corrida() == corrida()
