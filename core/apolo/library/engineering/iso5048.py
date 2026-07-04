"""Transportadores de banda según ISO 5048 / DIN 22101 + adherencia Euler-Eytelwein.

APLICABILIDAD (el matiz que evita usar mal la norma): el método ISO 5048/DIN 22101
—resistencia principal con coeficiente ficticio f≈0.02 y coeficiente C(L) de
resistencias secundarias— es para banda soportada sobre RODILLOS (idlers). Una banda
sobre CAMA DESLIZANTE (slider bed, la construcción típica del vertical de paquetería)
se rige por fricción de DESLIZAMIENTO: ahí aplica el factor CEMA slider-bed
μ=0.30–0.35 que implementa `belt.py` (belt_pull_n, μ=0.33). La capa de reglas elige
el método POR CONSTRUCCIÓN.

La verificación de ADHERENCIA del tambor motriz (Euler-Eytelwein, T1/T2 ≤ e^{μα})
es física clásica citada por ambas normas y aplica a las dos construcciones.

Funciones puras; unidades: N, m, kg/m, grados. G = 9.81 m/s².
"""

from __future__ import annotations

import math

G = 9.81

# coeficiente ficticio de fricción por rodadura sobre idlers (ISO 5048: 0.017–0.030
# según alineación/mantenimiento; 0.02 = instalación normal bien alineada)
F_ISO = 0.02

# μ del tambor motriz para Eytelwein (banda de goma sobre tambor)
MU_DRUM = {"engomado": 0.35, "liso": 0.25}

# Coeficiente C(L) de resistencias secundarias (DIN 22101 / ISO 5048). Los valores
# L ≥ 80 m son los ampliamente publicados de la norma; la zona L < 80 m es la
# extensión corta de la tabla (REFERENCIAL — en fajas cortas dominan las
# resistencias secundarias y la norma recomienda calcularlas individualmente).
_C_TABLE = (
    (10.0, 4.5), (20.0, 3.2), (40.0, 2.4), (63.0, 2.0), (80.0, 1.92),
    (100.0, 1.78), (150.0, 1.58), (200.0, 1.45), (300.0, 1.31),
    (500.0, 1.20), (1000.0, 1.09),
)


def c_coefficient(l_m: float) -> float:
    """C(L) por interpolación lineal en log(L); fuera de tabla → extremo (clamp)."""
    if l_m <= _C_TABLE[0][0]:
        return _C_TABLE[0][1]
    if l_m >= _C_TABLE[-1][0]:
        return _C_TABLE[-1][1]
    for (l0, c0), (l1, c1) in zip(_C_TABLE, _C_TABLE[1:]):
        if l0 <= l_m <= l1:
            t = (math.log(l_m) - math.log(l0)) / (math.log(l1) - math.log(l0))
            return c0 + t * (c1 - c0)
    return _C_TABLE[-1][1]  # pragma: no cover


def main_resistance_n(f: float, l_m: float, q_ro: float, q_ru: float,
                      q_b: float, q_g: float, delta_deg: float = 0.0) -> float:
    """Resistencia principal ISO 5048: F_H = f·L·g·(q_RO + q_RU + (2·q_B + q_G)·cosδ).
    q_RO/q_RU = masa por metro de partes giratorias del tramo superior/retorno;
    q_B = masa de banda por metro (un tramo); q_G = masa de carga por metro."""
    cos_d = math.cos(math.radians(delta_deg))
    return f * l_m * G * (q_ro + q_ru + (2.0 * q_b + q_g) * cos_d)


def slope_resistance_n(q_g: float, h_m: float) -> float:
    """Resistencia de elevación: F_St = q_G·H·g (H = desnivel total; negativo baja)."""
    return q_g * h_m * G


def effective_tension_n(f: float, l_m: float, q_ro: float, q_ru: float,
                        q_b: float, q_g: float, delta_deg: float = 0.0,
                        h_m: float = 0.0, c: float | None = None) -> float:
    """Tensión efectiva en el tambor motriz: F_U = C(L)·F_H + F_St."""
    cc = c_coefficient(l_m) if c is None else c
    return cc * main_resistance_n(f, l_m, q_ro, q_ru, q_b, q_g, delta_deg) \
        + slope_resistance_n(q_g, h_m)


def drive_power_kw(f_u_n: float, v_m_s: float, efficiency: float = 0.85) -> float:
    """Potencia en el motor: P_M = F_U·v / η (kW)."""
    return f_u_n * v_m_s / efficiency / 1000.0


def eytelwein_ratio(mu: float, alpha_deg: float = 180.0) -> float:
    """Relación máxima transmisible T1/T2 = e^{μ·α} (α en grados → rad)."""
    return math.exp(mu * math.radians(alpha_deg))


def eytelwein_t2_min_n(f_u_n: float, mu: float, alpha_deg: float = 180.0) -> float:
    """Tensión mínima del ramal flojo para transmitir F_U sin patinar:
    T2_min = F_U / (e^{μα} − 1). Es lo que el TENSOR debe garantizar."""
    return f_u_n / (eytelwein_ratio(mu, alpha_deg) - 1.0)


def eytelwein_fs(t1_n: float, t2_n: float, mu: float, alpha_deg: float = 180.0) -> float:
    """Factor de seguridad contra patinaje: FS = e^{μα} / (T1/T2)."""
    if t2_n <= 0 or t1_n <= 0:
        raise ValueError("T1 y T2 deben ser positivas")
    return eytelwein_ratio(mu, alpha_deg) / (t1_n / t2_n)
