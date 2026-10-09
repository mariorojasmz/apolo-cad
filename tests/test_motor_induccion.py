"""Motor de inducción + reductor por la rama estable de Kloss (V8.2 D3): helper puro."""

import math

import pytest

from apolo.library.engineering.motor_induccion import (
    inercia_rotor_estimada,
    kloss_linealizado,
    kloss_par,
)

PLACA = {"potencia_kW": 1.5, "rpm": 1750, "frecuencia_hz": 60, "tk_tn": 2.5}


def test_kloss_pasa_por_el_nominal_y_el_maximo():
    k = kloss_linealizado(PLACA)
    assert k["polos"] == 4 and k["ns_rpm"] == pytest.approx(1800)
    assert k["sn"] == pytest.approx(50 / 1800)
    assert k["Tn_Nm"] == pytest.approx(1500 / (1750 * 2 * math.pi / 60))
    assert kloss_par(k["sn"], k["Tk_Nm"], k["sk"]) == pytest.approx(k["Tn_Nm"], rel=1e-9)
    assert kloss_par(k["sk"], k["Tk_Nm"], k["sk"]) == pytest.approx(k["Tk_Nm"], rel=1e-9)


def test_reflejado_al_reductor():
    """kv = 2·Tk/(sk·ωs)·i²·η, tope Tk·i·η, consigna ωs/i (contrato D3)."""
    i, eta = 9.3, 0.85
    k1, k = kloss_linealizado(PLACA), kloss_linealizado(PLACA, i, eta)
    ws = 2 * math.pi * 1800 / 60
    assert k["kv"] == pytest.approx(2 * k1["Tk_Nm"] / (k1["sk"] * ws) * i * i * eta)
    assert k["par_max_Nm"] == pytest.approx(k1["Tk_Nm"] * i * eta)
    assert k["omega_sinc_rad_s"] == pytest.approx(ws / i)
    assert k["omega_nominal_rad_s"] == pytest.approx(1750 * 2 * math.pi / 60 / i)
    # la recta tangente da el par nominal a menos de 5 % del deslizamiento nominal
    t_lineal = k1["kv"] * (ws - 1750 * 2 * math.pi / 60)
    assert t_lineal / k1["Tn_Nm"] == pytest.approx(1.0, abs=0.05)


def test_variador_mueve_la_consigna_no_la_pendiente():
    k60 = kloss_linealizado(PLACA, 10, 0.9)
    k30 = kloss_linealizado(PLACA, 10, 0.9, frecuencia_hz=30)
    assert k30["omega_sinc_rad_s"] == pytest.approx(k60["omega_sinc_rad_s"] / 2)
    assert k30["kv"] == pytest.approx(k60["kv"]) and k30["par_max_Nm"] == pytest.approx(k60["par_max_Nm"])
    k90 = kloss_linealizado(PLACA, 10, 0.9, frecuencia_hz=90)
    assert k90["par_max_Nm"] == pytest.approx(k60["par_max_Nm"] * (60 / 90) ** 2)
    assert any("debilitamiento" in h for h in k90["hipotesis"])


def test_inercia_del_rotor_reflejada():
    k = kloss_linealizado({**PLACA, "inercia_rotor_kgm2": 0.004}, 40, 0.8)
    assert k["inercia_reflejada_kgm2"] == pytest.approx(0.004 * 1600)
    est = kloss_linealizado(PLACA, 40, 0.8)
    assert est["inercia_rotor_kgm2"] == pytest.approx(inercia_rotor_estimada(1.5))
    assert 0.003 < est["inercia_rotor_kgm2"] < 0.008     # orden de catálogo, 4 polos 1,5 kW
    assert any("inercia del rotor" in h for h in est["hipotesis"])


def test_supuestos_declarados_y_errores():
    k = kloss_linealizado({"potencia_kW": 0.75, "rpm": 1720})
    assert any("Tk/Tn" in h for h in k["hipotesis"]) and any("60 Hz" in h for h in k["hipotesis"])
    with pytest.raises(ValueError, match="rpm"):
        kloss_linealizado({"potencia_kW": 1.5})
    with pytest.raises(ValueError, match="potencia"):
        kloss_linealizado({"potencia_kw": 1.5, "rpm": 1750})
    with pytest.raises(ValueError, match="coherente"):
        kloss_linealizado({"potencia_kW": 1.5, "rpm": 1750, "polos": 2})
    with pytest.raises(ValueError, match="rendimiento"):
        kloss_linealizado(PLACA, 10, 1.2)
