"""Builders de la fijación de taller de `join_bolted` (plan union-en-perfil-hueco, D1/D4):
remache ciego y tornillo para madera de cabeza hexagonal. Módulo propio: `builders.py` está
congelado por el trinquete de tamaño.

Convención de la tornillería (la de `hex_bolt`): eje Z, ORIGEN en la cara de asiento de la
cabeza, cabeza hacia +Z y vástago hacia −Z. Rosca modelada lisa.
"""

from __future__ import annotations

from build123d import Cone, Cylinder, Pos

from .builders import _hex_prism


def _remache(d: float, dk: float, k: float, cuerpo: float, ciega: float):
    """Cabeza plana Ø dk × k sobre el asiento + cuerpo Ø d de `cuerpo` mm + (colocado) la
    cabeza ciega Ø 1,5·d × `ciega` que forma el mandril detrás de la pared. Las partes solapan
    0,5 mm (un sólido, no un compound de piezas tangentes)."""
    cabeza = Pos(0, 0, k / 2.0) * Cylinder(dk / 2.0, k)
    vastago = Pos(0, 0, -cuerpo / 2.0) * Cylinder(d / 2.0, cuerpo + 1.0)  # z ∈ [−cuerpo−½, ½]
    pieza = cabeza + vastago
    if ciega > 0:  # z ∈ [−cuerpo−ciega, −cuerpo]: apoya en la cara de atrás de la pared
        pieza = pieza + Pos(0, 0, -cuerpo - ciega / 2.0) * Cylinder(0.75 * d, ciega)
    return pieza


def blind_rivet(d: float, dk: float, k: float, length: float = 10.0):
    """Remache ciego de cabeza plana (DIN 7337 forma A / ISO 15983) SIN colocar, para la ficha
    de catálogo: cuerpo de `length` mm (el mandril no se modela)."""

    def build(largo=None):
        return _remache(d, dk, k, float(largo) if largo else length, 0.0)

    return build


def remache_colocado(d: float, dk: float, k: float, agarre: float, largo: float):
    """El remache YA colocado en una unión de `agarre` mm: el cuerpo atraviesa el agarre y lo
    que sobra del largo se recalca en la cabeza ciega (≈ la mitad del sobrante, Ø 1,5·d)."""
    ciega = max(0.6 * d, (largo - agarre) * 0.5)
    return _remache(d, dk, k, agarre, ciega)


def hex_wood_screw(d: float, across_flats: float, head_h: float, length: float = 40.0):
    """Tornillo para madera de cabeza HEXAGONAL (DIN 571, «tirafondo»): cabeza hex + vástago
    Ø d con punta cónica. `largo` = largo bajo cabeza (la punta incluida)."""

    def build(largo=None):
        L = float(largo) if largo else length
        punta = min(d, L / 3.0)
        recto = L - punta
        cabeza = Pos(0, 0, head_h / 2.0) * _hex_prism(across_flats, head_h)
        vastago = Pos(0, 0, -recto / 2.0) * Cylinder(d / 2.0, recto + 1.0)  # z ∈ [−recto−½, ½]
        cono = Pos(0, 0, -recto - punta / 2.0) * Cone(0.2, d / 2.0, punta)  # angosta abajo
        return cabeza + vastago + cono

    return build


BUILDERS = {"blind_rivet": blind_rivet, "hex_wood_screw": hex_wood_screw}
