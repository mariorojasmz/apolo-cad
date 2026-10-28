"""Cómo se sujetan las guardas de `create_belt_conveyor` con el criterio 8 (F1c del plan
faja-larga-en-tramos, D12): cada unión con sus agujeros y ninguna tuerca dentro del larguero, que
es un tubo CERRADO.

- **Guardas laterales, cubre-ranura y pared de cabeza** (sobre la cara superior del larguero):
  espárragos M6 soldados (ISO 13918) en el larguero y el ala con su agujero de paso; arandela y
  tuerca por arriba. Antes eran «M6» declarados sin agujero ni largo: un tornillo a rosca en la
  pared de 4,8 mm no engancha 1·d (`calidad/agarre.py`) y uno con tuerca la dejaba adentro.
- **Guardas de los tambores** (pared a ras de la cara interior del larguero, por debajo del paso
  de los ejes): una OREJA por perno que sube lo justo para el buje, y perno M8 PASANTE con buje
  soldado (D4 de la F1): la tuerca, por la cara exterior. Las orejas van en la punta de la guarda
  que mira al centro de la faja (lejos de la placa porta-chumacera y del tensor).
- **Guardas inferiores**: su pared ya solapaba 30 mm el alma; perno M6 pasante con buje.

Los pernos evitan los de los soportes de la cama y de los rodillos de retorno (sus bujes se
tocarían) y las puntas de cada tubo; van todos en el larguero del tramo al que la guarda se
atornilla. Las posiciones son UNA cuenta (`pernos_*`): la usan la guarda y el larguero.
"""

from __future__ import annotations

import math

from .belt_conveyor_cotas import Cotas
from .belt_conveyor_plan import caja
from .belt_conveyor_taller import nota_esparrago, nota_pasante, paso, repartir, taladro_y, taladro_z

PERNO_INF, BUJE_INF = "M6", 10.0
PERNO_TAMBOR, BUJE_TAMBOR = "M8", 14.0
PERNO_ALA = "M6"
LIBRE_SOPORTE = 25.0     # de un perno de guarda al de un soporte de cama (bujes que no se tocan)
LIBRE_RODILLO = 45.0     # … al centro de un soporte de rodillo de retorno
DEL_EXTREMO = 30.0       # … a la punta del tubo (placa de empalme o de cierre)
ZONA_OREJAS = 160.0      # las orejas de la guarda de un tambor, en sus primeros 160 mm


def _tramo(c: Cotas, x: float) -> tuple[float, float]:
    tubos = c.tramos or ((c.x0, c.x1),)
    return min(tubos, key=lambda t: 0.0 if t[0] <= x <= t[1] else min(abs(x - t[0]),
                                                                       abs(x - t[1])))


def _prohibidos(c: Cotas, x_ref: float) -> list[tuple[float, float]]:
    """Donde no puede ir un perno pasante de guarda en el larguero del tramo de `x_ref`."""
    from .belt_conveyor_bastidor import x_soportes
    from .belt_conveyor_retorno import x_rodillos

    a, b = _tramo(c, x_ref)
    out = [(-math.inf, a + DEL_EXTREMO), (b - DEL_EXTREMO, math.inf)]
    out += [(x - LIBRE_SOPORTE, x + LIBRE_SOPORTE) for x in x_soportes(c)]
    out += [(x - LIBRE_RODILLO, x + LIBRE_RODILLO) for x in x_rodillos(c)]
    return out


# ------------------------------------------------------------------ guardas inferiores
def z_inferior(c: Cotas) -> float:
    from .belt_conveyor_guardas import SOLAPE_PARED

    d0 = paso(PERNO_INF)
    z = c.rail_bot + max(14.0, c.wall + BUJE_INF / 2.0 + 1.5)
    if z + d0 / 2.0 + 1.2 * d0 > c.rail_bot + SOLAPE_PARED + 1e-6:
        raise ValueError(f"el tubo {c.tubo} no deja el perno pasante de la guarda inferior con "
                         "su buje dentro de lo que la pared solapa el alma")
    return z


def pernos_inferior(c: Cotas, i: int, x0: float, x1: float) -> list[float]:
    """X de los pernos de la guarda inferior [x0, x1] del lado `i` (iguales a los dos lados)."""
    n = math.ceil((x1 - x0) / 600.0) + 1
    return repartir(x0, x1, n, _prohibidos(c, (x0 + x1) / 2.0))


def taladrar_inferior(forma, c: Cotas, s: float, xs):
    from .belt_conveyor_guardas import CHAPA

    z = z_inferior(c)
    for x in xs:
        forma = forma - taladro_y(x, z, s * (c.y_in - CHAPA - 1.0), s * (c.y_in + 1.0),
                                  paso(PERNO_INF))
    return forma


def nota_inferior(c: Cotas) -> str:
    from .belt_conveyor_guardas import CHAPA

    return nota_pasante("pared de la guarda inferior al alma del larguero", PERNO_INF,
                        CHAPA + c.rail_t, BUJE_INF)


# ------------------------------------------------------------------ guardas de los tambores
def z_tambor(c: Cotas) -> float:
    return c.rail_bot + c.wall + BUJE_TAMBOR / 2.0 + 1.5


def pernos_tambor(c: Cotas, xd: float, inb: float) -> list[float]:
    """X de los dos pernos de la guarda del tambor en `xd` (su punta interior en `inb`)."""
    lo, hi = (inb, inb + ZONA_OREJAS) if inb < xd else (inb - ZONA_OREJAS, inb)
    return repartir(lo, hi, 2, _prohibidos(c, xd), margen=20.0, separacion=60.0)


def orejas_tambor(forma, c: Cotas, s: float, xs, z_pared: float):
    """La pared de la guarda con una oreja por perno (sube lo que pide el buje) y su agujero."""
    from .belt_conveyor_guardas import CHAPA

    z = z_tambor(c)
    d0 = paso(PERNO_TAMBOR)
    h = 1.2 * d0 + d0 / 2.0   # EN 1993-1-8: borde ≥ 1,2·d0
    for x in xs:
        forma = forma + caja(x - h, x + h, s * (c.y_in - CHAPA), s * c.y_in, z_pared - 1.0, z + h)
    for x in xs:
        forma = forma - taladro_y(x, z, s * (c.y_in - CHAPA - 1.0), s * (c.y_in + 1.0), d0)
    return forma


def nota_tambor(c: Cotas) -> str:
    from .belt_conveyor_guardas import CHAPA

    return nota_pasante("oreja de la guarda atornillada a la cara interior del larguero",
                        PERNO_TAMBOR, CHAPA + c.rail_t, BUJE_TAMBOR)


# ------------------------------------------------------------------ alas sobre el larguero
def pernos_ala(a: float, b: float, n: int) -> list[float]:
    return repartir(a, b, n, margen=40.0 if b - a > 120.0 else (b - a) / 4.0)


def taladrar_ala(forma, c: Cotas, s: float, xs):
    from .belt_conveyor_guardas import CHAPA

    for x in xs:
        forma = forma - taladro_z(x, s * c.rail_y, c.rail_top - 1.0, c.rail_top + CHAPA + 1.0,
                                  paso(PERNO_ALA))
    return forma


def nota_ala(cubre: bool) -> str:
    from .belt_conveyor_guardas import CHAPA

    que = "guarda cubre-ranura sobre el larguero" if cubre else "ala de la guarda sobre el larguero"
    return nota_esparrago(que, PERNO_ALA, CHAPA)


# ------------------------------------------------------------------ el larguero
def pasantes_de_guardas(c: Cotas, i: int) -> list[tuple[float, float, float, float]]:
    """(x, z, Ø del agujero, Ø del buje) de los pernos pasantes de guarda en el larguero `i`
    (iguales a los dos lados): las orejas de las guardas de los tambores y las guardas
    inferiores."""
    from .belt_conveyor_guardas import piezas_inferiores, x_de_tambor

    if not c.guardas:
        return []
    out = []
    zt, d8 = z_tambor(c), paso(PERNO_TAMBOR)
    for xd, r, sentido, viaje in ((c.half, c.r_m, 1.0, 0.0), (-c.half, c.r_c, -1.0, c.viaje)):
        inb = x_de_tambor(c, xd, r, sentido, viaje)[0]
        out += [(x, zt, d8, BUJE_TAMBOR) for x in pernos_tambor(c, xd, inb)]
    if c.cierres:
        zi, d6 = z_inferior(c), paso(PERNO_INF)
        for x0, largo in piezas_inferiores(c):
            out += [(x, zi, d6, BUJE_INF) for x in pernos_inferior(c, i, x0, x0 + largo)]
    return out
