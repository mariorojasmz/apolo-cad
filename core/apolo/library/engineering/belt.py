"""Faja transportadora sobre cama deslizante: arrastre, potencia y par.

El coeficiente 0.06 de `rules.py::FRICTION_COEFF` es de RODADURA (transportador
de rodillos). Una BANDA que desliza sobre cama de acero fricciona mucho más:
μ ≈ 0.30–0.35 (banda PVC / chapa). Estas funciones modelan ese caso, con
componente de inclinación y par de arranque.

Unidades: mm, kg, N, kW, N·m, grados. g = 9.81 m/s².
"""

from __future__ import annotations

import math

G = 9.81  # m/s²

# Banda PVC sobre cama de acero (rango típico 0.30-0.35; engomada sube a ~0.4).
BED_FRICTION = 0.33
# Par de arranque vs régimen (vencer inercia + fricción estática): 1.5-2.0.
STARTUP_FACTOR = 1.6


def belt_pull_n(
    carga_kg: float,
    banda_kg: float = 0.0,
    mu_bed: float = BED_FRICTION,
    incline_deg: float = 0.0,
) -> float:
    """Fuerza de arrastre efectiva (N) de una banda sobre cama deslizante:
    F = g·(μ·(m_carga + m_banda) + m_carga·sin θ). La banda fricciona con su
    propio peso pero no "sube" (el lazo se compensa a sí mismo en la pendiente)."""
    m_carga = max(float(carga_kg), 0.0)
    m_banda = max(float(banda_kg), 0.0)
    theta = math.radians(incline_deg)
    return G * (mu_bed * (m_carga + m_banda) + m_carga * math.sin(theta))


def belt_power_kw(
    pull_n: float,
    v_m_s: float,
    efficiency: float = 0.85,
    margin: float = 1.3,
) -> float:
    """Potencia requerida (kW) en el motor: P = F·v / η · margen."""
    if efficiency <= 0:
        return 0.0
    return pull_n * max(float(v_m_s), 0.0) / efficiency / 1000.0 * margin


def belt_startup_torque_nm(
    pull_n: float,
    tambor_d_mm: float,
    factor: float = STARTUP_FACTOR,
) -> float:
    """Par de ARRANQUE requerido en el eje del tambor motriz (N·m):
    T = F·r · factor (el arranque exige vencer fricción estática + inercia)."""
    return pull_n * (max(float(tambor_d_mm), 0.0) / 2.0 / 1000.0) * factor


def estimate_belt_kg(
    largo_mm: float,
    ancho_mm: float,
    thickness_mm: float = 2.0,
    density_kg_mm3: float = 1.4e-6,
) -> float:
    """Peso estimado (kg) del lazo de banda: ida + retorno (2×largo) × ancho ×
    espesor × ρ PVC (1.4e-6 kg/mm³). Para banda engomada usa ρ 1.5e-6."""
    return 2.0 * max(largo_mm, 0.0) * max(ancho_mm, 0.0) * max(thickness_mm, 0.0) * density_kg_mm3
