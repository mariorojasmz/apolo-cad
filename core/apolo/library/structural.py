"""Cálculos estructurales puros (viga / eje) para la validación de ingeniería.

Resistencia de materiales sin estado ni dependencia del documento: inercia de
sección, flecha de viga y flexión de eje. Los consume `rules.py` para los chequeos
del bastidor y los ejes de un transportador, y son reutilizables (weldments, etc.).
Unidades: mm, N, MPa (N/mm²). I en mm⁴.
"""

from __future__ import annotations

import math


def rect_tube_inertia_mm4(width: float, depth: float, wall: float) -> float:
    """Segundo momento de área (mm⁴) de un tubo rectangular hueco respecto al eje
    de flexión, con `depth` = altura de la sección EN la dirección de la carga
    (vertical) y `width` el ancho. Pared `wall`. Tubo macizo si wall ≥ mitad."""
    width = max(float(width), 1e-6)
    depth = max(float(depth), 1e-6)
    wi = max(width - 2.0 * wall, 0.0)
    di = max(depth - 2.0 * wall, 0.0)
    return (width * depth**3 - wi * di**3) / 12.0


def beam_udl_deflection_mm(w_n_per_mm: float, span_mm: float, e_mpa: float, i_mm4: float) -> float:
    """Flecha máxima (mm) de una viga simplemente apoyada con carga uniformemente
    repartida: δ = 5·w·L⁴ / (384·E·I)."""
    if e_mpa <= 0 or i_mm4 <= 0:
        return 0.0
    return 5.0 * w_n_per_mm * span_mm**4 / (384.0 * e_mpa * i_mm4)


def shaft_bending_stress_mpa(load_n: float, span_mm: float, diam_mm: float) -> float:
    """Tensión de flexión (MPa) de un eje macizo simplemente apoyado con carga
    central: M = P·L/4, σ = 32·M / (π·d³)."""
    if diam_mm <= 0:
        return 0.0
    moment = load_n * span_mm / 4.0
    return 32.0 * moment / (math.pi * diam_mm**3)
