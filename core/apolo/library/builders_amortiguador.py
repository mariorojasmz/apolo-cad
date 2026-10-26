"""Geometría del amortiguador hidráulico de fin de carrera (plan amortiguador-externo D1). Módulo
propio, como cada familia: `builders.py` está congelado por el trinquete de tamaño.

MARCO LOCAL: +X = hacia donde asoma el vástago (el lado del choque); el origen es el centro de
la cara DELANTERA del cuerpo roscado (de donde sale el vástago). El vástago sale EXTENDIDO (sin
carga). Un sólido: cuerpo roscado (cilindro del Ø nominal de la rosca, sin filetes), vástago, las
dos tuercas hexagonales de montaje y, si `tope`, la contratuerca de tope adelante.

Cotas de los params de cada ref (YAML, con su fuente): `rosca_d` Ø nominal, `L` largo del cuerpo,
`LL` largo total extendido, `D` Ø del vástago, `carrera_mm`, `B` entrecaras de la tuerca, `h` su
espesor, `h_tope` espesor de la contratuerca de tope. Lo que no es cota de la ficha (dónde van
las tuercas: con 10 mm de chapa entre ellas) es criterio de modelo: no cambia ningún entregable
de compra.
"""

from __future__ import annotations

import math

from build123d import Cylinder, Pos, RegularPolygon, Rotation, extrude

_SOLAPE = 0.5
#: Chapa entre las dos tuercas de montaje (criterio de modelo: la ménsula típica).
CHAPA_MM = 10.0
#: Separación entre la tuerca delantera y la cara del cuerpo (o la contratuerca de tope).
_LUZ = 2.0


def _cil_x(r: float, x0: float, x1: float):
    return Pos((x0 + x1) / 2.0, 0, 0) * (Rotation(0, 90, 0) * Cylinder(r, x1 - x0))


def _hex_x(entrecaras: float, x0: float, x1: float):
    """Prisma hexagonal de `entrecaras` a lo largo de X entre x0 y x1 (caras paralelas a Z)."""
    alto = x1 - x0
    prisma = extrude(RegularPolygon(radius=entrecaras / math.sqrt(3.0), side_count=6), amount=alto)
    return Pos((x0 + x1) / 2.0, 0, 0) * (Rotation(0, 90, 0) * (Pos(0, 0, -alto / 2.0) * prisma))


def _x_tope(p: dict) -> float:
    """Cara delantera de la contratuerca de tope: el vástago comprimido toda su carrera queda a ras."""
    return (p["LL"] - p["L"]) - p["carrera_mm"]


def _x_tuercas(p: dict) -> tuple[float, float]:
    """Cara delantera de la tuerca delantera y de la trasera (criterio de modelo)."""
    x0 = (_x_tope(p) - p["h_tope"] - _LUZ) if p.get("tope") else -_LUZ
    return x0, x0 - p["h"] - CHAPA_MM


def amortiguador_hidraulico(**params):
    p = dict(params)

    def build(length):
        sale = p["LL"] - p["L"]
        forma = _cil_x(p["rosca_d"] / 2.0, -p["L"], 0.0) + _cil_x(p["D"] / 2.0, -_SOLAPE, sale)
        for x in _x_tuercas(p):
            forma = forma + _hex_x(p["B"], x - p["h"], x)
        if p.get("tope"):
            xt = _x_tope(p)
            forma = forma + _hex_x(p["B"], xt - p["h_tope"], xt)
        return forma

    return build


def anclas(**p) -> dict:
    """Anclas LOCALES: `extremo_vastago` (donde golpea la carga, extendido), `fondo` del cuerpo,
    `rosca` (la cara delantera) y, con tope, `tope` (donde para la carga a fin de carrera)."""
    out = {"extremo_vastago": {"origin": [p["LL"] - p["L"], 0.0, 0.0], "axis": [1.0, 0.0, 0.0]},
           "rosca": {"origin": [0.0, 0.0, 0.0], "axis": [1.0, 0.0, 0.0]},
           "fondo": {"origin": [-p["L"], 0.0, 0.0], "axis": [-1.0, 0.0, 0.0]}}
    if p.get("tope"):
        out["tope"] = {"origin": [_x_tope(p), 0.0, 0.0], "axis": [1.0, 0.0, 0.0]}
    return out


BUILDERS = {"amortiguador_hidraulico": amortiguador_hidraulico}
ANCLAS = {"amortiguador_hidraulico": anclas}
