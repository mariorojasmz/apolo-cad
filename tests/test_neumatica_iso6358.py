"""Caudal ISO 6358-1 y conversiones de entrada (plan V8.9 D3, F1a).

Los valores «a mano» están resueltos en el comentario de cada test; los de la F0 salen de la
bitácora del plan (§ F0, tabla 1: referencia de pistón rígido a 10 µs)."""

from __future__ import annotations

import math

import pytest

from apolo.library.neumatica import iso6358 as I
from apolo.library.neumatica.calculo import areas


def test_phi_sonico_subsonico_y_cerrado():
    assert I.phi(0.2, 0.3) == 1.0 and I.phi(0.3, 0.3) == 1.0  # p2/p1 ≤ b: bloqueo
    assert I.phi(1.0, 0.3) == 0.0
    # r = 0,65, b = 0,3: ((0,65 − 0,3)/0,7)² = 0,25 → φ = √0,75
    assert I.phi(0.65, 0.3) == pytest.approx(math.sqrt(0.75), rel=1e-12)
    with pytest.raises(ValueError):
        I.phi(0.5, 1.0)


def test_caudal_en_bloqueo_es_c_por_p1():
    # sónico: q_ANR = C·p1 (dm³/s) y q_m = ρ0·q_ANR
    assert I.caudal_anr(0.8, 0.3, 7.0, 1.0) == pytest.approx(5.6, rel=1e-12)
    assert I.caudal_masico(0.8, 0.3, 7.0, 1.0) == pytest.approx(5.6e-3 * 1.185, rel=1e-12)
    assert I.caudal_anr(0.8, 0.3, 5.0, 5.0) == 0.0 and I.caudal_anr(0.8, 0.3, 4.0, 5.0) == 0.0


def test_regimen_a_mano_de_la_f0_con_escape_libre():
    # Ø32/12, válvula C = 0,8: A anular = π/4·(32² − 12²) = 691,150 mm²;
    # v = C·p_ANR/A = 0,8·1000/691,150 = 1,15749 m/s: la cota «a mano» de la F0 (1,157)
    _A, Ab, _a = areas(32, 12)
    assert Ab == pytest.approx(691.150, abs=1e-3)
    v = I.velocidad_regimen_sonica(0.8, Ab)
    assert v == pytest.approx(1.15749, rel=1e-5)
    assert v == pytest.approx(1.157, rel=0.002)  # ±0,2 % de la cota a mano de la F0
    # la referencia fina de la F0 dio 1,155 (máx.): la F0 lo publicó como −0,2 % (−0,22 % sin
    # redondear; el prototipo usó ρ0·R·T0 = 0,997·p_ANR para pasar de masa a volumen)
    assert v == pytest.approx(1.155, rel=0.0025)


def test_regimen_a_mano_de_la_f0_con_escape_estrangulado():
    # C serie = 1/√(1/0,8² + 1/0,15²) = 1/√46,0069 = 0,147431; v = 0,147431·1000/691,150 = 0,21331
    C = I.c_serie(0.8, 0.15)
    assert C == pytest.approx(0.147431, rel=1e-5)
    v = I.velocidad_regimen_sonica(C, areas(32, 12)[1])
    assert v == pytest.approx(0.21331, rel=1e-4)
    assert v == pytest.approx(0.213, rel=0.002)  # ±0,2 % de la referencia de la F0


def test_qn_anr_ida_y_vuelta():
    # C desde Qn de 6 a 5 bar man., y el caudal ISO 6358 en ese punto devuelve el Qn
    C = I.c_desde_qn(680, 6, 5, 0.3, referencia="ANR")
    p1, p2 = 6 + I.P_ATM_ESTANDAR_BAR, 5 + I.P_ATM_ESTANDAR_BAR
    assert I.caudal_anr(C, 0.3, p1, p2) * 60 == pytest.approx(680, rel=1e-12)
    # a mano: r = 6,01325/7,01325 = 0,857413; ((r − 0,3)/0,7)² = 0,634100; φ = √0,365900 = 0,604897
    # C = (680/60)/(7,01325·0,604897) = 11,33333/4,24230 = 2,67152
    assert C == pytest.approx(2.67152, rel=1e-4)


def test_qn_din1343_pasa_a_anr_por_gas_ideal():
    # 1 L normal (0 °C, 1,01325 bar) = 293,15/273,15 · 1,01325/1 = 1,08746 L ANR
    a = I.c_desde_qn(100, 6, 5, 0.3, referencia="ANR")
    n = I.c_desde_qn(100, 6, 5, 0.3, referencia="DIN1343")
    assert n / a == pytest.approx(293.15 / 273.15 * 1.01325, rel=1e-12)
    with pytest.raises(ValueError, match="referencia"):
        I.c_desde_qn(100, 6, 5, 0.3, referencia="SCFM")
    with pytest.raises(ValueError, match="p1 > p2"):
        I.c_desde_qn(100, 5, 6, 0.3, referencia="ANR")


def test_kv_por_cv_sale_de_las_unidades():
    # IEC 60534-1: Kv = 0,865·Cv (redondeo de 0,86498)
    assert I.KV_POR_CV == pytest.approx(0.865, abs=5e-4)
    # VDI/VDE 2173, 6 → 5 bar man.: 514·√(1·6,01325/(1,293·293,15)) = 64,74 m³/h = 1079 L/min,
    # la regla de catálogo «Qn ≈ 1078·Kv»
    assert I.qn_desde_kv(1.0, 6, 5) == pytest.approx(1079.0, rel=1e-3)
    # crítico (Δp ≥ p1/2): 257·Kv·p1/√(ρN·T1), continuo con el subcrítico en la frontera
    p1 = 6 + I.P_ATM_ESTANDAR_BAR
    q = I.qn_desde_kv(1.0, 6, p1 / 2 - I.P_ATM_ESTANDAR_BAR)
    assert q == pytest.approx(257 * p1 / math.sqrt(1.293 * 293.15) * 1000 / 60, rel=1e-9)


def test_cv_de_una_ficha_real_da_su_c():
    # SMC VF3130 (5/2 G1/4, listado del distribuidor): Cv 1,0 / 0,75 y C 4,0 / 3,1 dm³/(s·bar).
    # Con b = 0,3 (hipótesis) la conversión de D3 da 3,99 y 2,99: la cadena Cv → Kv → Qn → C
    # es coherente con el C que publica la misma ficha.
    assert I.c_desde_cv(1.0, 6, 5, 0.3) == pytest.approx(4.0, rel=0.01)
    assert I.c_desde_cv(0.75, 6, 5, 0.3) == pytest.approx(3.1, rel=0.04)


def test_area_efectiva_es_tobera_ideal():
    # tobera ideal k = 1,4: C ≈ 0,199·S, el orden de la regla de catálogo S ≈ 5·C
    assert I.c_desde_s(5.0) == pytest.approx(1.0, rel=0.01)
    assert I.c_desde_s(12.0) == pytest.approx(12 * 0.19919, rel=1e-3)


def test_c_serie_rechaza_cero():
    with pytest.raises(ValueError):
        I.c_serie(0.8, 0.0)
    assert I.c_serie(2.0) == 2.0
