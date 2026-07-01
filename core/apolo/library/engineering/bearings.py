"""Vida nominal L10 de rodamientos rígidos de bolas (ISO 281).

L10 = (C/P)³ en millones de revoluciones; en horas: L10h = L10·10⁶/(60·n).
C (capacidad dinámica, kN) viene de las specs del catálogo (`C_kN` en
70_rodamientos.yaml / 95_chumaceras.yaml); P es la carga radial equivalente.

Unidades: kN, rpm, horas.
"""

from __future__ import annotations

# Umbrales de aceptación para maquinaria industrial de servicio normal
# (transportadores ~8 h/día): objetivo 20 000 h; por debajo de 5 000 h es error.
L10_TARGET_H = 20000.0
L10_MIN_H = 5000.0


def l10_hours(c_kn: float, p_kn: float, rpm: float) -> float:
    """Vida nominal L10 en HORAS: (C/P)³ · 10⁶ / (60·n). Si la carga o las rpm
    son ~cero la vida es ilimitada a efectos prácticos → inf."""
    if p_kn <= 0 or rpm <= 0:
        return float("inf")
    l10_mrev = (max(float(c_kn), 0.0) / float(p_kn)) ** 3
    return l10_mrev * 1e6 / (60.0 * float(rpm))
