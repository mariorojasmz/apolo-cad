"""Viga continua (`library/engineering/viga_continua.py`) contra casos de libro.

Plan flecha-de-bastidor F1. Las fórmulas cerradas son exactas (Euler-Bernoulli) → tolerancia
1e-6; los coeficientes de tabla (Roark / AISC Manual, «Beam Diagrams and Formulas») vienen
redondeados a 3-4 cifras → tolerancia del redondeo. Los vanos desiguales se verifican por otro
método: la ecuación de los tres momentos (Clapeyron) + superposición de la elástica.
"""

from __future__ import annotations

import math

import pytest

from apolo.library.engineering.viga_continua import (
    APOYO,
    EMPOTRAMIENTO,
    Apoyo,
    CargaPuntual,
    CargaRepartida,
    q_peso_propio_n_mm,
    viga_continua,
)
from apolo.library.structural import beam_udl_deflection_mm

E = 200_000.0  # MPa
I = 4.58e5  # mm⁴ (ángulo L 75×6)
EI = E * I
EXACTO = 1e-6
MUESTREO = 1e-5  # máximos que el solver ubica por muestreo (resolución ≈ L/1200)


def _ss_udl(x: float, q: float, L: float) -> float:
    """Elástica de la simplemente apoyada con q uniforme (+ abajo)."""
    return q * x * (L**3 - 2 * L * x * x + x**3) / (24 * EI)


def _ss_momento_extremo(x: float, m0: float, L: float) -> float:
    """Elástica de la simplemente apoyada con un momento m0 en el extremo x=0 (M(x)=m0·(1−x/L))."""
    return m0 * x * (L - x) * (2 * L - x) / (6 * EI * L)


# ── Isostáticas ───────────────────────────────────────────────────────────────


def test_simplemente_apoyada_carga_uniforme():
    L, q = 4000.0, 1.5
    r = viga_continua(L, EI, [Apoyo(0), Apoyo(L)], [CargaRepartida(q)])
    assert r.flecha_max_mm == pytest.approx(5 * q * L**4 / (384 * EI), rel=EXACTO)
    assert r.flecha_max_mm == pytest.approx(beam_udl_deflection_mm(q, L, E, I), rel=EXACTO)
    assert r.flecha_x_mm == pytest.approx(L / 2)
    assert r.momento_max_nmm == pytest.approx(q * L * L / 8, rel=EXACTO)
    assert r.momento_negativo_nmm == pytest.approx(0.0, abs=1e-3)
    assert r.reacciones_n == pytest.approx((q * L / 2, q * L / 2), rel=EXACTO)
    assert [t.tipo for t in r.tramos] == ["vano"]


def test_simplemente_apoyada_puntual_centrada_y_excentrica():
    L, P = 3000.0, 2000.0
    r = viga_continua(L, EI, [Apoyo(0), Apoyo(L)], [CargaPuntual(L / 2, P)])
    assert r.flecha_max_mm == pytest.approx(P * L**3 / (48 * EI), rel=EXACTO)
    assert r.momento_max_nmm == pytest.approx(P * L / 4, rel=EXACTO)
    # excéntrica: a = 2000 desde la izquierda, b = 1000 → δmax = P·b·(L²−b²)^1.5 / (9√3·L·EI)
    a, b = 2000.0, 1000.0
    r = viga_continua(L, EI, [Apoyo(0), Apoyo(L)], [CargaPuntual(a, P)])
    assert r.flecha_max_mm == pytest.approx(P * b * (L * L - b * b) ** 1.5 / (9 * math.sqrt(3) * L * EI),
                                            rel=MUESTREO)
    assert r.flecha_x_mm == pytest.approx(math.sqrt((L * L - b * b) / 3), rel=2e-3)
    assert r.momento_max_nmm == pytest.approx(P * a * b / L, rel=EXACTO)
    assert r.momento_x_mm == pytest.approx(a)
    assert r.reacciones_n == pytest.approx((P * b / L, P * a / L), rel=EXACTO)


def test_voladizo_puntual_y_uniforme():
    L, P, q = 1500.0, 800.0, 0.6
    r = viga_continua(L, EI, [Apoyo(0, EMPOTRAMIENTO)], [CargaPuntual(L, P)])
    assert r.flecha_max_mm == pytest.approx(P * L**3 / (3 * EI), rel=EXACTO)
    assert r.flecha_x_mm == pytest.approx(L)
    assert r.momento_max_nmm == pytest.approx(-P * L, rel=EXACTO)  # tracciona arriba
    assert r.reacciones_n == pytest.approx((P,), rel=EXACTO)
    assert [t.tipo for t in r.tramos] == ["voladizo"]

    r = viga_continua(L, EI, [Apoyo(L, EMPOTRAMIENTO)], [CargaRepartida(q)])  # empotrado a la derecha
    assert r.flecha_max_mm == pytest.approx(q * L**4 / (8 * EI), rel=EXACTO)
    assert r.flecha_x_mm == pytest.approx(0.0)
    assert r.momento_negativo_nmm == pytest.approx(-q * L * L / 2, rel=EXACTO)


def test_vano_con_voladizo_da_reaccion_negativa():
    """Carga en la punta del voladizo: la flecha de la punta es P·a²·(L+a)/(3·EI) y el apoyo
    lejano TRACCIONA (R = −P·a/L): se publica negativa, no se recorta a cero."""
    L, a, P = 2000.0, 600.0, 1000.0
    r = viga_continua(L + a, EI, [Apoyo(0), Apoyo(L)], [CargaPuntual(L + a, P)])
    assert r.flecha_max_mm == pytest.approx(P * a * a * (L + a) / (3 * EI), rel=EXACTO)
    assert r.reacciones_n == pytest.approx((-P * a / L, P * (L + a) / L), rel=EXACTO)
    assert [t.tipo for t in r.tramos] == ["vano", "voladizo"]
    vano = r.tramos[0]
    # en el vano la viga SUBE (flecha negativa): máx en x = L/√3, δ = −P·a·L²/(9√3·EI)
    assert vano.flecha_max_mm == pytest.approx(-P * a * L * L / (9 * math.sqrt(3) * EI), rel=MUESTREO)


# ── Hiperestáticas: coeficientes de tabla ─────────────────────────────────────


def test_biempotrada_carga_uniforme():
    L, q = 3000.0, 2.0
    r = viga_continua(L, EI, [Apoyo(0, EMPOTRAMIENTO), Apoyo(L, EMPOTRAMIENTO)], [CargaRepartida(q)])
    assert r.momento_negativo_nmm == pytest.approx(-q * L * L / 12, rel=EXACTO)
    assert r.momento_positivo_nmm == pytest.approx(q * L * L / 24, rel=EXACTO)
    assert r.flecha_max_mm == pytest.approx(q * L**4 / (384 * EI), rel=EXACTO)


def test_continua_dos_vanos_iguales():
    """Tabla: R = 0.375·qL | 1.25·qL | 0.375·qL; M_apoyo = −0.125·qL²; M_vano = 0.0703·qL²;
    δmax = 0.00542·qL⁴/EI (= qL⁴/185EI) a 0.4215·L del extremo."""
    L, q = 2500.0, 1.2
    r = viga_continua(2 * L, EI, [Apoyo(0), Apoyo(L), Apoyo(2 * L)], [CargaRepartida(q)])
    assert [x / (q * L) for x in r.reacciones_n] == pytest.approx([0.375, 1.25, 0.375], rel=EXACTO)
    assert r.momento_negativo_nmm / (q * L * L) == pytest.approx(-0.125, rel=EXACTO)
    assert r.momento_positivo_nmm / (q * L * L) == pytest.approx(9 / 128, rel=EXACTO)  # 0.0703
    assert r.flecha_max_mm * EI / (q * L**4) == pytest.approx(0.00542, rel=1e-3)
    assert r.tramos[0].flecha_x_mm == pytest.approx(0.4215 * L, rel=2e-3)
    # exacto por superposición: SS + momento −qL²/8 en el apoyo central
    xs = [L * k / 20000 for k in range(20001)]
    exacto = max(_ss_udl(L - x, q, L) + _ss_momento_extremo(x, -q * L * L / 8, L) for x in xs)
    assert r.flecha_max_mm == pytest.approx(exacto, rel=MUESTREO)
    assert [t.tipo for t in r.tramos] == ["vano", "vano"]
    assert r.tramos[1].flecha_max_mm == pytest.approx(r.tramos[0].flecha_max_mm, rel=1e-9)


def test_continua_tres_vanos_iguales():
    """Tabla: R = 0.4 | 1.1 | 1.1 | 0.4 ·qL; M_apoyo = −0.10·qL²; M vano extremo 0.08·qL²,
    vano central 0.025·qL²; δmax = 0.0069·qL⁴/EI en el vano extremo (AISC Manual)."""
    L, q = 2000.0, 0.8
    r = viga_continua(3 * L, EI, [Apoyo(k * L) for k in range(4)], [CargaRepartida(q)])
    assert [x / (q * L) for x in r.reacciones_n] == pytest.approx([0.4, 1.1, 1.1, 0.4], rel=EXACTO)
    assert r.momento_negativo_nmm / (q * L * L) == pytest.approx(-0.1, rel=EXACTO)
    assert r.momento_positivo_nmm / (q * L * L) == pytest.approx(0.08, rel=1e-6)
    assert r.flecha_max_mm * EI / (q * L**4) == pytest.approx(0.0069, rel=5e-3)
    centro = r.tramos[1]
    assert centro.flecha_max_mm * EI / (q * L**4) == pytest.approx(
        # vano central: SS + dos momentos −0.1qL² en sus extremos
        5 / 384 - 0.1 / 8, rel=1e-6)
    # vano extremo exacto: SS + momento −0.1qL² en el apoyo interior
    xs = [L * k / 20000 for k in range(20001)]
    exacto = max(_ss_udl(L - x, q, L) + _ss_momento_extremo(x, -0.1 * q * L * L, L) for x in xs)
    assert r.tramos[0].flecha_max_mm == pytest.approx(exacto, rel=MUESTREO)


# ── Vanos desiguales: ecuación de los tres momentos (otro método) ──────────────


def test_dos_vanos_desiguales_carga_uniforme():
    """Clapeyron con M_A = M_C = 0: 2·M_B·(L1+L2) = −q·(L1³+L2³)/4."""
    L1, L2, q = 3000.0, 5000.0, 1.0
    r = viga_continua(L1 + L2, EI, [Apoyo(0), Apoyo(L1), Apoyo(L1 + L2)], [CargaRepartida(q)])
    m_b = -q * (L1**3 + L2**3) / (8 * (L1 + L2))
    r_a = q * L1 / 2 + m_b / L1
    r_c = q * L2 / 2 + m_b / L2
    r_b = q * (L1 + L2) - r_a - r_c
    assert r.reacciones_n == pytest.approx((r_a, r_b, r_c), rel=EXACTO)
    assert r.momento_negativo_nmm == pytest.approx(m_b, rel=EXACTO)
    xs = [L2 * k / 20000 for k in range(20001)]  # vano largo, x desde B
    exacto = max(_ss_udl(x, q, L2) + _ss_momento_extremo(x, m_b, L2) for x in xs)
    assert r.tramos[1].flecha_max_mm == pytest.approx(exacto, rel=MUESTREO)
    assert r.flecha_max_mm == pytest.approx(exacto, rel=MUESTREO)


def test_dos_vanos_desiguales_carga_puntual():
    """Clapeyron, P a distancia a de A en el vano 1: 2·M_B·(L1+L2) = −P·a·(L1²−a²)/L1."""
    L1, L2, P, a = 3000.0, 4500.0, 5000.0, 1000.0
    r = viga_continua(L1 + L2, EI, [Apoyo(0), Apoyo(L1), Apoyo(L1 + L2)], [CargaPuntual(a, P)])
    m_b = -P * a * (L1**2 - a**2) / (L1 * 2 * (L1 + L2))
    r_a = P * (L1 - a) / L1 + m_b / L1
    r_c = m_b / L2  # negativa: el vano descargado se levanta y el apoyo C tracciona
    r_b = P - r_a - r_c
    assert r.reacciones_n == pytest.approx((r_a, r_b, r_c), rel=EXACTO)
    assert r.reacciones_n[2] < 0
    assert r.momento_negativo_nmm == pytest.approx(m_b, rel=EXACTO)
    assert r.momento_positivo_nmm == pytest.approx(r_a * a, rel=EXACTO)


# ── Equilibrio, cargas parciales y entradas ───────────────────────────────────


def test_equilibrio_con_cargas_mezcladas():
    L = 6000.0
    apoyos = [Apoyo(500), Apoyo(2600), Apoyo(4100), Apoyo(5800)]
    cargas = [CargaRepartida(0.4), CargaRepartida(1.1, 1000, 3000), CargaPuntual(150, 900),
              CargaPuntual(3333, 2500), CargaPuntual(6000, 400)]
    r = viga_continua(L, EI, apoyos, cargas)
    total = 0.4 * L + 1.1 * 2000 + 900 + 2500 + 400
    momento = 0.4 * L * L / 2 + 1.1 * 2000 * 2000 + 900 * 150 + 2500 * 3333 + 400 * 6000
    assert sum(r.reacciones_n) == pytest.approx(total, rel=1e-9)
    assert sum(R * a.x_mm for R, a in zip(r.reacciones_n, apoyos)) == pytest.approx(momento, rel=1e-9)
    assert [t.tipo for t in r.tramos] == ["voladizo", "vano", "vano", "vano", "voladizo"]
    assert abs(r.flecha_max_mm) == max(abs(t.flecha_max_mm) for t in r.tramos)


def test_reacciones_en_el_orden_de_entrada():
    L, q = 4000.0, 1.0
    r = viga_continua(L, EI, [Apoyo(L), Apoyo(0)], [CargaRepartida(q, 0, 1000)])
    assert r.reacciones_n == pytest.approx((q * 1000 * 500 / L, q * 1000 * 3500 / L), rel=EXACTO)


def test_peso_propio():
    assert q_peso_propio_n_mm(10.0) == pytest.approx(0.0981)
    assert APOYO == "apoyo"


@pytest.mark.parametrize("apoyos, cargas, msg", [
    ([Apoyo(0)], [CargaPuntual(10, 1)], "inestable"),
    ([Apoyo(0), Apoyo(0)], [], "mismo punto"),
    ([Apoyo(0), Apoyo(1200)], [], "fuera de la viga"),
    ([Apoyo(0), Apoyo(1000)], [CargaPuntual(1500, 1)], "fuera de la viga"),
    ([Apoyo(0), Apoyo(1000)], [CargaRepartida(1, 800, 600)], "fuera de la viga"),
    ([Apoyo(0, "rotula"), Apoyo(1000)], [], "desconocido"),
    ([Apoyo(0), Apoyo(1000)], ["50 kg"], "desconocido"),
])
def test_entradas_invalidas(apoyos, cargas, msg):
    with pytest.raises(ValueError, match=msg):
        viga_continua(1000.0, EI, apoyos, cargas)
