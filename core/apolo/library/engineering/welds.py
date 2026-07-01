"""Cordones de soldadura en ángulo (fillet): tensión en garganta vs admisible.

Convención: `throat_mm` ES la garganta `a` del cordón (la distancia mínima raíz→
cara). Si conoces el CATETO z (lo que se mide con galga), a = 0.707·z. Se usa la
comprobación simplificada τ = F/(a·L) vs 0.6·σy del material BASE más débil.

Unidades: N, mm, MPa.
"""

from __future__ import annotations


def weld_throat_stress_mpa(load_n: float, throat_mm: float, length_mm: float) -> float:
    """Tensión media en la garganta (MPa): τ = F / (a·L). `length_mm` es la
    longitud TOTAL de cordón de la unión (suma de todos los tramos)."""
    area = max(float(throat_mm), 0.0) * max(float(length_mm), 0.0)
    if area <= 0:
        return float("inf")
    return max(float(load_n), 0.0) / area


def weld_allowable_mpa(yield_mpa: float) -> float:
    """Tensión admisible del cordón (MPa): 0.6·σy del material base más débil
    (criterio simplificado de cortante; electrodo asumido igual o superior)."""
    return 0.6 * max(float(yield_mpa), 0.0)
