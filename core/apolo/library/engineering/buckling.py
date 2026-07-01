"""Pandeo de columnas (Euler) para las patas/postes de un bastidor.

Pcr = π²·E·I / (K·L)². Por defecto K=2.0 (empotrada abajo, libre arriba):
CONSERVADOR para una pata atornillada a una placa base cuyo tope está
arriostrado por el bastidor — la hipótesis se declara en el detalle de la regla.

Unidades: N, MPa, mm, mm⁴.
"""

from __future__ import annotations

import math

from ..structural import rect_tube_inertia_mm4

# Factor de seguridad mínimo aceptable frente a Pcr de Euler (las fórmulas de
# Euler ignoran imperfecciones/plastificación → se exige margen amplio).
BUCKLING_FS = 3.0


def euler_critical_load_n(e_mpa: float, i_mm4: float, length_mm: float, k: float = 2.0) -> float:
    """Carga crítica de pandeo de Euler (N): Pcr = π²·E·I / (K·L)²."""
    kl = max(float(k), 1e-6) * max(float(length_mm), 1e-6)
    return math.pi**2 * max(float(e_mpa), 0.0) * max(float(i_mm4), 0.0) / kl**2


def rect_tube_min_inertia_mm4(width: float, depth: float, wall: float) -> float:
    """Inercia MÍNIMA (mm⁴) de un tubo rectangular hueco: el pandeo ocurre
    alrededor del eje débil, así que se toma el menor de los dos ejes."""
    return min(
        rect_tube_inertia_mm4(width, depth, wall),
        rect_tube_inertia_mm4(depth, width, wall),
    )
