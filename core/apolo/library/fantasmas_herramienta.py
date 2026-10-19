"""Sólidos FANTASMA de las herramientas de apriete (plan acceso-de-herramienta, D1).

Cada fantasma se arma en un marco LOCAL del fijador: origen en el eje, sobre la cara de
asiento; +z hacia afuera; +x a lo largo de la normal de una cara del hexágono (las direcciones
de la boca y del mango se miden desde ahí, en grados). Medidas: `herramientas.py`.

Los sectores son anillo exacto ∩/− una CUÑA prismática de 3 caras (no polígonos con cuerdas):
pocas caras = booleanas baratas (una boca poligonizada costaba ~135 ms por cruce; bitácora F0).
`Fantasmas` memoiza por parámetros DENTRO de una corrida (40 tuercas iguales = cada fantasma se
construye una vez y sólo se recoloca); no hay caché global.
"""

from __future__ import annotations

import math

from .herramientas import GIRO_MIN_GRADOS


def _cilindro(r: float, z0: float, z1: float):
    from build123d import Cylinder, Pos

    return Pos(0, 0, (z0 + z1) / 2.0) * Cylinder(r, z1 - z0)


def _anillo(r_in: float, r_out: float, z0: float, z1: float):
    return _cilindro(r_out, z0, z1) - _cilindro(r_in, z0 - 1.0, z1 + 1.0)


def _cuna(r: float, centro: float, semi: float, z0: float, z1: float):
    """Cuña prismática (triángulo con vértice en el eje) que cubre el ángulo centro ± semi
    (grados, semi < 80) hasta más allá del radio `r`; un poco más alta que [z0, z1]."""
    from build123d import Polygon, Pos, extrude

    largo = 1.2 * r / math.cos(math.radians(semi))
    a, b = math.radians(centro - semi), math.radians(centro + semi)
    pts = [(0.0, 0.0), (largo * math.cos(a), largo * math.sin(a)),
           (largo * math.cos(b), largo * math.sin(b))]
    return Pos(0, 0, z0 - 1.0) * extrude(Polygon(*pts, align=None), z1 - z0 + 2.0)


def marco(base, eje, x_dir):
    """Plano local del fijador (z = `eje` hacia afuera, x = `x_dir`)."""
    from build123d import Plane

    return Plane(origin=base, x_dir=x_dir, z_dir=eje)


def semi_abertura_boca(s: float, b: float) -> float:
    """Semiángulo (grados) de la abertura de la boca que QUEDA libre al barrer ±15°: la
    abertura mide asin((s/2)/(b/2)) a cada lado y el giro se come GIRO_MIN_GRADOS."""
    return math.degrees(math.asin(min(1.0, (s / 2.0 + 0.3) / (b / 2.0)))) - GIRO_MIN_GRADOS


class Fantasmas:
    """Constructor memoizado de fantasmas locales (una instancia por corrida)."""

    def __init__(self):
        self._cache: dict[tuple, object] = {}

    def _memo(self, clave: tuple, fabrica):
        clave = tuple(round(x, 3) if isinstance(x, float) else x for x in clave)
        if clave not in self._cache:
            self._cache[clave] = fabrica()
        return self._cache[clave]

    def cilindro(self, r: float, z0: float, z1: float):
        """Copa (Ø copa_d), sonda del agujero o brazo de la llave Allen."""
        return self._memo(("cil", r, z0, z1), lambda: _cilindro(r, z0, z1))

    def anillo(self, r_in: float, r_out: float, z0: float, z1: float):
        """Anillo plano: cabeza de la llave de anillo, o sonda de asiento."""
        return self._memo(("ani", r_in, r_out, z0, z1), lambda: _anillo(r_in, r_out, z0, z1))

    def mango(self, r_cabeza: float, ancho: float, theta: float, z0: float, z1: float):
        """Arranque del mango (largo = ancho) hacia `theta`, barriendo ±GIRO_MIN_GRADOS."""
        gamma = math.degrees(math.atan((ancho / 2.0) / r_cabeza)) + GIRO_MIN_GRADOS
        r_out = r_cabeza + ancho
        return self._memo(
            ("man", r_cabeza, ancho, theta, z0, z1),
            lambda: _anillo(r_cabeza - 0.5, r_out, z0, z1) & _cuna(r_out, theta, gamma, z0, z1))

    def boca(self, r_esquinas: float, s: float, b: float, theta, z0: float, z1: float):
        """Cabeza de boca con el mango hacia `theta` y la abertura hacia theta + 180°: el anillo
        Ø b menos lo que queda de la abertura tras barrer ±15° (casi nada: por eso una tuerca a
        2.5 mm de un ala tampoco admite la boca). `theta=None` = lo COMÚN a las 6 direcciones
        (anillo menos las 6 aberturas): si eso ya choca, ninguna boca entra."""
        beta = semi_abertura_boca(s, b)
        r_in, rb = r_esquinas + 0.3, b / 2.0

        def fabrica():
            cabeza = _anillo(r_in, rb, z0, z1)
            if beta <= 0.0:
                return cabeza
            dirs = [theta + 180.0] if theta is not None else [60.0 * k for k in range(6)]
            for d in dirs:
                cabeza = cabeza - _cuna(rb, d, beta, z0, z1)
            return cabeza

        return self._memo(("boca", r_in, rb, theta, beta, z0, z1), fabrica)
