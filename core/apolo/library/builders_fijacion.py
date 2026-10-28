"""Builders de la fijación de taller de `join_bolted` (plan union-en-perfil-hueco, D1/D4):
remache ciego y tornillo para madera de cabeza hexagonal; y el perno de cuello cuadrado DIN 603
(F6 de la puerta de publicación) y el anclaje de expansión a concreto (F6 de
plantilla-rodillos-cadena). Módulo propio: `builders.py` está congelado por el trinquete
de tamaño.

Convención de la tornillería (la de `hex_bolt`): eje Z, ORIGEN en la cara de asiento de la
cabeza, cabeza hacia +Z y vástago hacia −Z. Rosca modelada lisa.
"""

from __future__ import annotations

from build123d import Box, Cone, Cylinder, Pos, Sphere

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


def carriage_bolt(d: float, head_d: float, head_k: float, neck_v: float, neck_f: float,
                  length: float = 50.0):
    """Perno de cuello cuadrado DIN 603 («de coche»): cabeza de hongo Ø head_d × head_k (casquete
    esférico, lisa: no se le mete llave), cuello cuadrado neck_v × neck_v de neck_f de alto que
    se clava en la madera o en un agujero cuadrado y frena el giro, y vástago Ø d. `largo` =
    largo nominal bajo cabeza (el cuello incluido), como en la norma. Se aprieta por la TUERCA
    DIN 934 (TUERCA-M*). Las partes solapan 0,5 mm (un sólido)."""

    def build(largo=None):
        L = float(largo) if largo else length
        a = head_d / 2.0
        r = (a * a + head_k * head_k) / (2.0 * head_k)  # radio de la esfera del casquete
        domo = (Pos(0, 0, head_k - r) * Sphere(r)) & (Pos(0, 0, head_k / 2.0) * Box(
            head_d + 2.0, head_d + 2.0, head_k))
        cuello = Pos(0, 0, -neck_f / 2.0 + 0.25) * Box(neck_v, neck_v, neck_f + 0.5)
        vastago = Pos(0, 0, -L / 2.0 + 0.25) * Cylinder(d / 2.0, L + 0.5)  # z ∈ [−L, ½]
        return domo + cuello + vastago

    return build


def expansion_anchor(d: float, length: float, sobre: float, across_flats: float, nut_h: float,
                     washer_d: float, washer_t: float):
    """Anclaje de expansión YA colocado (F6 de plantilla-rodillos-cadena): arandela Ø washer_d ×
    washer_t sobre la placa, tuerca hexagonal AF × nut_h encima y el espárrago Ø d de `length`
    que asoma `sobre` mm por encima del asiento y baja el resto (placa + concreto). ORIGEN = cara
    de asiento de la arandela (la cara superior de la placa), eje Z. La camisa de expansión no se
    modela (es del Ø del espárrago). Las partes solapan: un sólido."""

    def build(_length=None):
        arandela = Pos(0, 0, washer_t / 2.0) * Cylinder(washer_d / 2.0, washer_t)
        tuerca = Pos(0, 0, washer_t + nut_h / 2.0) * _hex_prism(across_flats, nut_h)
        esparrago = Pos(0, 0, sobre - length / 2.0) * Cylinder(d / 2.0, length)
        return arandela + tuerca + esparrago

    return build


BUILDERS = {"blind_rivet": blind_rivet, "hex_wood_screw": hex_wood_screw,
            "carriage_bolt": carriage_bolt, "expansion_anchor": expansion_anchor}
