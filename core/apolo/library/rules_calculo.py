"""Reglas de la faja: fuerza y potencia de arrastre de rodillos, velocidad de banda y la
recomendación de motorreductor y rodillo de catálogo. Sale de `rules.py` (plan
partir-nucleo-congelado-ii, F3), que lo re-exporta por identidad. Puro.
"""

from __future__ import annotations

import math

from .catalog import CATALOG, category_refs_sorted
from .rules_comun import EFFICIENCY, FRICTION_COEFF, POWER_MARGIN


def required_force_n(carga_kg: float, largo_mm: float, largo_paquete_mm: float) -> float:
    """Fuerza de arrastre (N) para mover los paquetes simultáneos (rodadura+cojinetes)."""
    n_paquetes = max(1, math.floor(largo_mm / (largo_paquete_mm * 2.0)))
    return n_paquetes * carga_kg * 9.81 * FRICTION_COEFF


def required_power_kw(carga_kg: float, largo_mm: float, largo_paquete_mm: float, velocidad_m_s: float) -> float:
    """Potencia mínima recomendada (con margen) para mover los paquetes simultáneos."""
    force_n = required_force_n(carga_kg, largo_mm, largo_paquete_mm)
    return force_n * velocidad_m_s / EFFICIENCY / 1000.0 * POWER_MARGIN


def band_speed_m_s(rpm_salida: float, tambor_d_mm: float) -> float:
    """Velocidad lineal de banda (m/s) = rpm · π · Ø_tambor / 60000."""
    return rpm_salida * math.pi * tambor_d_mm / 60000.0


def recommend_motor_kw(p_req: float) -> str:
    """Ref de motorreductor comercial más chico que cubre `p_req` kW."""
    refs = category_refs_sorted("motorreductores", "potencia_kW")
    for ref in refs:
        if CATALOG[ref].specs["potencia_kW"] >= p_req:
            return ref
    return refs[-1]


def recommend_motor(carga_kg: float, largo_mm: float, largo_paquete_mm: float, velocidad_m_s: float) -> str:
    return recommend_motor_kw(required_power_kw(carga_kg, largo_mm, largo_paquete_mm, velocidad_m_s))


def recommend_roller(carga_kg: float, largo_paquete_mm: float, paso_mm: float) -> str:
    apoyo = max(1, math.floor(largo_paquete_mm / paso_mm))
    carga_por_rodillo = carga_kg / apoyo
    refs = category_refs_sorted("rodillos", "capacidad_kg")
    for ref in refs:
        if CATALOG[ref].specs["capacidad_kg"] >= carga_por_rodillo:
            return ref
    return refs[-1]
