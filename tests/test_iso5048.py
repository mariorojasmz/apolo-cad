"""ISO 5048 / DIN 22101 + Euler-Eytelwein (V5.10): tabla C(L), resistencias y
adherencia del tambor — anclas contra valores publicados y ejemplo a mano."""
import math

import pytest

from apolo.library.engineering.iso5048 import (
    F_ISO, MU_DRUM, c_coefficient, drive_power_kw, effective_tension_n,
    eytelwein_fs, eytelwein_ratio, eytelwein_t2_min_n, main_resistance_n,
    slope_resistance_n,
)

# valores de C(L) ampliamente publicados (DIN 22101 / ISO 5048) — L ≥ 80 m
PUBLICADOS = [(80, 1.92), (100, 1.78), (200, 1.45), (500, 1.20), (1000, 1.09)]


@pytest.mark.parametrize("l_m,c", PUBLICADOS)
def test_c_publicados(l_m, c):
    assert c_coefficient(l_m) == pytest.approx(c, abs=1e-6)


def test_c_monotonia_y_clamp():
    ls = [10, 15, 20, 30, 40, 63, 80, 100, 150, 200, 300, 500, 1000]
    cs = [c_coefficient(l) for l in ls]
    assert all(a > b for a, b in zip(cs, cs[1:]))  # estrictamente decreciente
    assert c_coefficient(3) == c_coefficient(10) == 4.5   # clamp corto (referencial)
    assert c_coefficient(5000) == 1.09                     # clamp largo
    assert 1.78 < c_coefficient(90) < 1.92                 # interpola entre nodos


def test_resistencia_principal_ancla():
    # f=0.02, L=100, q_RO=10, q_RU=3, q_B=8, q_G=50, δ=0:
    # F_H = 0.02·100·9.81·(10+3+(16+50)) = 19.62·79 = 1549.98 N
    fh = main_resistance_n(F_ISO, 100, 10, 3, 8, 50)
    assert fh == pytest.approx(1549.98, abs=0.01)


def test_pendiente_y_tension_efectiva_ancla():
    assert slope_resistance_n(50, 5) == pytest.approx(2452.5, abs=0.01)
    # F_U = C(100)·F_H = 1.78·1549.98 = 2758.96 N (sin desnivel)
    fu = effective_tension_n(F_ISO, 100, 10, 3, 8, 50)
    assert fu == pytest.approx(2758.96, abs=0.05)
    # con H=5 m se suma la elevación
    fu_h = effective_tension_n(F_ISO, 100, 10, 3, 8, 50, h_m=5)
    assert fu_h == pytest.approx(2758.96 + 2452.5, abs=0.1)


def test_potencia_ancla():
    # P = 2758.96·1.5/0.85/1000 = 4.869 kW
    assert drive_power_kw(2758.96, 1.5) == pytest.approx(4.869, abs=0.001)


def test_eytelwein_anclas():
    # e^(0.35·π) = 3.003
    assert eytelwein_ratio(MU_DRUM["engomado"]) == pytest.approx(3.0028, abs=1e-3)
    # T2_min = 1000/(3.003−1) = 499.3 N
    assert eytelwein_t2_min_n(1000, 0.35) == pytest.approx(499.3, abs=0.1)
    # T1/T2 = 3 con capacidad 3.003 → FS = 1.00
    assert eytelwein_fs(3000, 1000, 0.35) == pytest.approx(1.0009, abs=1e-3)
    # tambor liso transmite menos: e^(0.25π) = 2.193 < 3.003
    assert eytelwein_ratio(MU_DRUM["liso"]) == pytest.approx(2.1933, abs=1e-3)
    assert eytelwein_t2_min_n(1000, 0.25) > eytelwein_t2_min_n(1000, 0.35)


def test_eytelwein_validacion():
    with pytest.raises(ValueError):
        eytelwein_fs(1000, 0, 0.35)


def test_inclinacion_reduce_normal():
    # a 30° el término (2q_B+q_G) pesa cos30 < 1 → F_H baja
    plano = main_resistance_n(F_ISO, 100, 10, 3, 8, 50, 0)
    inclinado = main_resistance_n(F_ISO, 100, 10, 3, 8, 50, 30)
    assert inclinado < plano
