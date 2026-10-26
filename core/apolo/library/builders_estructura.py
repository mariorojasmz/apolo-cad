"""Perfiles y piezas ESTRUCTURALES del catálogo: perfil ranurado, tubos rectangular y redondo,
ángulo, canal, viga I, cilindro macizo, caja fija, pata, guarda/faldón y pie nivelador.

La fachada `builders.py` re-exporta cada nombre por IDENTIDAD y conserva `BUILDERS`
(plan `docs/plans/partir-nucleo-congelado-ii.md`, F1). Contrato de cada builder: una
*factory* `(**params) -> ((length|None) -> shape)`, forma centrada, Z arriba.
"""

from __future__ import annotations

from build123d import Box, Cylinder, Pos

from apolo.kernel.shapes import make_rect_tube, make_structural_profile


def profile(size: str):
    """Perfil de aluminio ranurado (T-slot), cortable a lo largo de Z."""
    return lambda length: make_structural_profile(size, length)


def rect_tube(width: float, height: float, wall: float = 3.0):
    """Tubo estructural rectangular de ACERO (hueco), cortable a lo largo de Z.
    Pareja de acero de ``profile`` (aluminio): largueros, patas y travesaños del bastidor."""
    return lambda length: make_rect_tube(width, height, wall, length)


def cylinder(diameter: float):
    """Cilindro macizo eje Z, cortable (ejes, piezas a medida)."""
    return lambda length: Cylinder(diameter / 2.0, length)


def box(width: float, depth: float, height: float):
    """Caja fija centrada en el origen."""
    return lambda _length=None: Box(width, depth, height)


def leg(profile_size: str = "40x40", plate: float = 120.0, plate_t: float = 10.0):
    """Pata regulable = columna de perfil + placa base; length = altura total."""

    def build(length):
        column = Pos(0, 0, plate_t / 2) * make_structural_profile(profile_size, length - plate_t)
        base = Pos(0, 0, -(length - plate_t) / 2) * Box(plate, plate, plate_t)
        return column + base

    return build


def guard(thickness: float = 6.0, height: float = 150.0):
    """Guarda/faldón lateral: chapa cortable a lo largo de X."""
    return lambda length: Box(length, thickness, height)


def leveling_foot(rosca: float, altura: float, disco_d: float, disco_t: float):
    """Pie nivelador: vástago roscado (eje Z) sobre un disco de apoyo."""

    def build(_length=None):
        stem = Cylinder(rosca / 2.0, altura)
        disk = Pos(0, 0, -altura / 2.0 - disco_t / 2.0) * Cylinder(disco_d / 2.0, disco_t)
        return stem + disk

    return build


def round_tube(od: float, wall: float):
    """Tubo redondo de acero HUECO, eje Z, cortable a lo largo de Z.
    od = Ø exterior, wall = espesor de pared. Pareja redonda de `rect_tube`."""

    def build(length):
        outer = Cylinder(od / 2.0, length)
        if 0.0 < wall < od / 2.0:
            outer = outer - Cylinder(od / 2.0 - wall, length)
        return outer

    return build


def angle(leg: float, t: float):
    """Ángulo de acero de lados iguales (perfil L), cortable a lo largo de Z.
    Sección en XY centrada en su caja; leg = lado, t = espesor."""

    def build(length):
        horiz = Pos(0, -leg / 2.0 + t / 2.0, 0) * Box(leg, t, length)
        vert = Pos(-leg / 2.0 + t / 2.0, 0, 0) * Box(t, leg, length)
        return horiz + vert

    return build


def channel(h: float, b: float, tw: float, tf: float):
    """Perfil U / canal (tipo UPN, prismático simplificado sin conicidad), cortable en Z.
    h = altura (alma, Y), b = ancho de ala (X), tw = espesor de alma, tf = espesor de ala."""

    def build(length):
        web = Pos(-b / 2.0 + tw / 2.0, 0, 0) * Box(tw, h, length)
        top = Pos(0, h / 2.0 - tf / 2.0, 0) * Box(b, tf, length)
        bot = Pos(0, -h / 2.0 + tf / 2.0, 0) * Box(b, tf, length)
        return web + top + bot

    return build


def i_beam(h: float, b: float, tw: float, tf: float):
    """Viga doble T (tipo IPE/IPN, prismático simplificado), cortable a lo largo de Z.
    h = altura (Y), b = ancho de ala (X), tw = espesor de alma, tf = espesor de ala."""

    def build(length):
        web = Box(tw, h, length)
        top = Pos(0, h / 2.0 - tf / 2.0, 0) * Box(b, tf, length)
        bot = Pos(0, -h / 2.0 + tf / 2.0, 0) * Box(b, tf, length)
        return web + top + bot

    return build
