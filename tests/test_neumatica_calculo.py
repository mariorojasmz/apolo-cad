"""Cálculo neumático de la memoria (plan V8.9 D10, F1a): cada caso resuelto a mano en el test."""

from __future__ import annotations

import math

import pytest

from apolo.library.catalog import CATALOG
from apolo.library.neumatica import calculo as K

_CLAVES_CALC = {"titulo", "entradas", "formula", "sustitucion", "resultado", "criterio", "fs", "norma"}


def test_fuerza_teorica_contra_la_ficha_smc():
    # SMC C96SDB32-100C: 402 N de avance y 346 N de retroceso a 0,5 MPa (hoja de datos)
    r = K.fuerzas(32, 12, 5, friccion_pct=10)
    assert r["valor"]["F_avance_N"] == pytest.approx(402, abs=0.5)
    assert r["valor"]["F_retroceso_N"] == pytest.approx(346, abs=0.5)
    # SMC CP96SDB63-60C: 1559 / 1402 N a 0,5 MPa
    r = K.fuerzas(63, 20, 5, friccion_N=0)
    assert r["valor"]["F_avance_N"] == pytest.approx(1559, abs=1)
    assert r["valor"]["F_retroceso_N"] == pytest.approx(1402, abs=1)
    assert set(r["calc"]) == _CLAVES_CALC


def test_fuerza_de_la_f0_y_la_efectiva():
    # F0: Ø32/12 a 6 bar → 483 / 415 N; Ø50/20 → 1178 / 990 N
    v = K.fuerzas(32, 12, 6, friccion_pct=10)["valor"]
    assert (round(v["F_avance_N"]), round(v["F_retroceso_N"])) == (483, 415)
    assert v["F_avance_ef_N"] == pytest.approx(0.9 * v["F_avance_N"])
    v = K.fuerzas(50, 20, 6, friccion_N=30)["valor"]
    assert (round(v["F_avance_N"]), round(v["F_retroceso_N"])) == (1178, 990)
    assert v["F_retroceso_ef_N"] == pytest.approx(v["F_retroceso_N"] - 30)
    with pytest.raises(ValueError, match="UNA fricción"):
        K.fuerzas(32, 12, 6)


def test_fuerza_de_ficha_fuera_de_presion_es_error():
    f = CATALOG["CIL-ISO15552-32"].neumatico
    assert K.fuerzas_de_ficha(f, 6)["estado"] == "ok"
    assert K.fuerzas_de_ficha(f, 12)["estado"] == "error"  # sobre los 10 bar de la ficha
    assert any("friccion_pct" in h for h in K.fuerzas_de_ficha(f, 6)["hipotesis"])


def test_consumo_isotermo_a_mano():
    # Ø32, carrera 300, 8 cm³ muertos, 6 bar man., p_atm 1,01325, p_ANR 1:
    # A·s = π/4·32²·300 = 241,2743 cm³ → V_fin = 249,2743 cm³
    # ΔV = (7,01325·249,2743 − 1,01325·8)/1 = 1748,2232 − 8,1060 = 1740,117 cm³ = 1,740117 NL
    A, _Ab, _a = K.areas(32, 12)
    assert K.consumo_carrera_nl(A, 300, 8, 6) == pytest.approx(1.740117, rel=1e-6)
    # sin volumen muerto ni tubo es la fórmula de catálogo con p_ANR: A·s·(p + p_atm)/p_ANR
    assert K.consumo_carrera_nl(A, 300, 0, 6) == pytest.approx(0.2412743 * 7.01325, rel=1e-6)


def test_consumo_por_ciclo_y_por_minuto():
    # ciclo doble Ø32/12 s300 sin muertos: (241,2743 + 207,3451)·7,01325/1000 = 3,14628 NL ANR.
    # La F0 dio 3,11 con aire libre referido a p_atm (·7,01325/1,01325): la razón es p_atm/p_ANR.
    r = K.consumo_ciclo(32, 12, 300, 6, V_muerto_A_cm3=0, V_muerto_B_cm3=0, ciclos_min=12)
    assert r["valor"]["ciclo_NL"] == pytest.approx(3.14628, rel=1e-5)
    assert r["valor"]["ciclo_NL"] / 1.01325 == pytest.approx(3.105, rel=1e-3)
    assert r["valor"]["NL_min"] == pytest.approx(12 * 3.14628, rel=1e-5)
    assert any("ISO 2533" in h for h in r["hipotesis"])  # p_atm supuesta, declarada
    # con tubos: 2 m de PU Ø6×4 por cámara = π·4²/4·2 = 25,133 cm³ cada uno
    vt = K.volumen_tubo_cm3(4, 2)
    assert vt == pytest.approx(25.1327, rel=1e-5)
    r2 = K.consumo_ciclo(32, 12, 300, 6, V_muerto_A_cm3=0, V_muerto_B_cm3=0, V_tubo_A_cm3=vt,
                         V_tubo_B_cm3=vt, p_atm=1.01325)
    # cada cámara suma (7,01325 − 1,01325)·25,133/1000 = 0,150796 NL
    assert r2["valor"]["ciclo_NL"] - r["valor"]["ciclo_NL"] == pytest.approx(2 * 0.150796, rel=1e-4)
    assert not any("ISO 2533" in h for h in r2["hipotesis"])


def test_caudal_pico_y_la_valvula_que_lo_pasa():
    # Ø32 a 1 m/s y 6 bar: 804,248 mm²·1 m/s = 0,804248 L/s a 7,01325 bar → ·60·7,01325 = 338,43 NL/min
    A, _Ab, _a = K.areas(32, 12)
    q = K.caudal_pico(A, 1.0, 6)
    assert q == pytest.approx(338.43, rel=1e-4)
    v = CATALOG["VAL-52-MONO-G18"].neumatico.caudal
    r = K.verificar_caudal("-QM1", v.C, v.b, q, 6, 1.0, m=v.m)
    # con Δp = 1 bar es el punto de medición del Qn: 680 NL/min
    assert r["valor"]["q_disponible_NL_min"] == pytest.approx(680, rel=1e-9)
    assert r["estado"] == "ok"
    assert K.verificar_caudal("-QM1", v.C, v.b, 900, 6, 1.0)["estado"] == "aviso"


def test_regimen_y_su_condicion_de_bloqueo():
    _A, Ab, _a = K.areas(32, 12)
    r = K.regimen(0.8, Ab, 300, b=0.3)
    # t = 0,3/1,15749 = 0,25918 s
    assert r["valor"]["t_s"] == pytest.approx(0.25918, rel=1e-4)
    assert r["estado"] == "ok" and any("bloqueo" in h for h in r["hipotesis"])
    # p_atm/b = 1,01325/0,3 = 3,3775 bar abs: con la cámara a 1 bar man. no bloquea
    assert K.regimen(0.8, Ab, 300, b=0.3, p_camara_bar_g=1.0)["estado"] == "aviso"
    assert K.regimen(0.8, Ab, 300, b=0.3, p_camara_bar_g=4.0)["estado"] == "ok"


def test_pandeo_del_vastago_euler_a_mano():
    # Ø12, 500 mm libres, caso 1 (K = 2): I = π·12⁴/64 = 1017,876 mm⁴; Lk = 1000 mm
    # Pcr = π²·210000·1017,876/1000² = 2109,67 N; contra 483 N → FS = 4,368 ≥ 3: ok
    r = K.pandeo_vastago(12, 500, 1, 483)
    assert r["valor"]["Pcr_N"] == pytest.approx(2109.67, rel=1e-5)
    assert r["valor"]["fs"] == pytest.approx(4.368, rel=1e-3)
    assert r["valor"]["lambda"] == pytest.approx(1000 / 3)
    assert r["estado"] == "ok"
    # 800 mm: Lk = 1600 → Pcr = 2109,67/2,56 = 824,09 N, FS = 1,706 < 3: error
    r = K.pandeo_vastago(12, 800, 1, 483)
    assert r["valor"]["Pcr_N"] == pytest.approx(824.09, rel=1e-4)
    assert r["estado"] == "error" and r["calc"]["fs"] == pytest.approx(1.71, abs=0.01)


def test_pandeo_corto_pasa_a_johnson_con_fy():
    # Ø20, 100 mm, caso 2 (K = 1): λ = 100/(20/4) = 20 < λc = π·√(2·210000/400) = 101,8
    # Johnson: Pcr = A·fy·(1 − fy·λ²/(4π²E)) = 314,159·400·(1 − 400·400/(4π²·210000))
    #        = 125663,7·(1 − 0,0192995) = 123238,5 N
    r = K.pandeo_vastago(20, 100, 2, 1000, fy_mpa=400)
    assert r["valor"]["Pcr_N"] == pytest.approx(123238.5, rel=1e-5)
    assert "Johnson" in r["calc"]["resultado"]
    # sin fy, con λ < 100: Euler con aviso (puede sobreestimar)
    r = K.pandeo_vastago(20, 100, 2, 1000)
    assert r["estado"] == "aviso" and "Euler" in r["calc"]["resultado"]
    with pytest.raises(ValueError):
        K.pandeo_vastago(20, 100, 5, 1000)


def test_energia_de_impacto_contra_la_amortiguacion_de_la_ficha():
    m = CATALOG["CIL-ISO15552-32"].neumatico.modelo
    assert m["E_amortiguacion_J"] == 2.3  # SMC C96*-OM0001Q, tabla 1
    # masa al llegar: 0,12 + 0,000888·300 + 3 kg de carga = 3,3864 kg
    masa = K.masa_movil_kg(m, 300, 3.0)
    assert masa == pytest.approx(3.3864, rel=1e-9)
    # a 1,155 m/s: E = ½·3,3864·1,155² = 2,2588 J ≤ 2,3: ok
    r = K.energia_impacto(masa, 1.155, m["E_amortiguacion_J"])
    assert r["valor"]["E_J"] == pytest.approx(2.2588, rel=1e-4) and r["estado"] == "ok"
    # a 1,2 m/s: E = ½·3,3864·1,44 = 2,4382 J > 2,3: error
    r = K.energia_impacto(masa, 1.2, m["E_amortiguacion_J"])
    assert r["valor"]["E_J"] == pytest.approx(2.4382, rel=1e-4) and r["estado"] == "error"


def test_demanda_de_aire_con_fugas_declaradas():
    # 3,146 NL × 12 ciclos/min + 1,0 NL × 30 = 37,75 + 30 = 67,75; con 10 % de fugas: 74,53 NL/min
    r = K.demanda_aire([("-MM1", 3.146, 12), ("-MM2", 1.0, 30)], 10)
    assert r["valor"]["sin_fugas_NL_min"] == pytest.approx(67.752, rel=1e-6)
    assert r["valor"]["NL_min"] == pytest.approx(74.5272, rel=1e-6)
    assert r["hipotesis"] == ["fugas = 10 % declarado (hipótesis)"]
    assert math.isclose(r["valor"]["NL_min"] / 1000, 0.0745272, rel_tol=1e-6)
