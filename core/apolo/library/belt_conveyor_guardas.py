"""Resguardos de `create_belt_conveyor` (v4), todos de chapa ATORNILLADA (se quitan con
herramienta, ISO 14120):

- guarda lateral en L sobre cada larguero: la pared contiene los paquetes y el ala tapa por
  arriba la ranura entre el borde de la banda y el larguero (3 mm a la banda), por donde se
  llegaba a las cuñas banda ↔ tambor en los extremos de los tambores;
- guarda de cada tambor: bandeja bajo el ramal de retorno, paredes a ras de la cara interior de
  los largueros y tapa de extremo; la de cola lleva además techo sobre el tambor (la cabeza
  descarga por arriba). Llega ≥ 330 mm hacia adentro de la cuña: desde el piso, un brazo no
  alcanza la cuña rodeando la bandeja (850 mm de alcance, ISO 13857).
"""

from __future__ import annotations

import math

from .belt_conveyor_cotas import Cotas
from .belt_conveyor_plan import Plan, caja

CHAPA = 3.0
ALTO_PARED = 150.0
HOLGURA_BANDA = 3.0       # del borde de la banda a la pared de la guarda lateral
HOLGURA_RETORNO = 20.0    # de la bandeja al ramal de retorno (≤ 20: ranura ISO 13857, sr 120)
HOLGURA_EXTREMO = 10.0    # de la banda (en su carrera) a la tapa de extremo
ALCANCE = 330.0           # de la cuña hacia adentro (ISO 13857: 850 mm de alcance desde el piso)


def laterales(plan: Plan, c: Cotas) -> None:
    yb = c.ancho / 2.0 + HOLGURA_BANDA
    z0 = c.rail_top
    largo = c.x1 - c.x0
    for i, s in ((1, -1.0), (2, 1.0)):
        pared = caja(c.x0, c.x1, s * yb, s * (yb + CHAPA), z0, z0 + ALTO_PARED)
        ala = caja(c.x0, c.x1, s * yb, s * c.y_out, z0, z0 + CHAPA)
        plan.pieza(f"guarda{i}", f"Guarda lateral ({i})", pared + ala, material="acero")
        plan.union(f"guarda{i}_larg", f"guarda{i}", f"rail{i}", "perno",
                   "ala de la guarda atornillada sobre el larguero", size="M6",
                   qty=math.ceil(largo / 600.0) + 1)


def de_tambor(plan: Plan, c: Cotas, suf: str, nombre: str, xd: float, r: float, sentido: float,
              viaje: float, techo: bool) -> None:
    """Caja de chapa alrededor del extremo de un tambor (`sentido` +1: hacia +X)."""
    z_ret = min(c.zm - c.r_m, c.zc - c.r_c) - c.t       # cara inferior del ramal de retorno
    zp0 = z_ret - HOLGURA_RETORNO - CHAPA
    out = xd + sentido * (r + c.t + viaje + HOLGURA_EXTREMO)
    disponible = (c.largo - c.r_m - c.r_c - c.carrera) / 2.0 - 40.0
    inb = xd - sentido * (r + viaje + max(40.0, min(ALCANCE, disponible)))
    xe = out + sentido * CHAPA
    z_pared = min(c.rail_bot + 20.0, c.zm - c.d_m / 2.0 - 6.0, c.zc - c.d_c / 2.0 - 6.0)
    forma = caja(inb, xe, -c.y_in, c.y_in, zp0, zp0 + CHAPA)                       # bandeja
    for s in (-1.0, 1.0):                                                             # paredes
        forma = forma + caja(inb, xe, s * (c.y_in - CHAPA), s * c.y_in, zp0, z_pared)
    forma = forma + caja(out, xe, -c.y_in, c.y_in, zp0, c.rail_top)                  # extremo
    if techo:
        yb = c.ancho / 2.0 + HOLGURA_BANDA
        forma = forma + caja(out, xe, -yb, yb, c.rail_top - 1.0, c.rail_top + CHAPA)
        forma = forma + caja(xd - sentido * 5.0, xe, -yb, yb, c.rail_top + CHAPA,
                             c.rail_top + 2.0 * CHAPA)
    plan.pieza(suf, nombre, forma, material="acero")
    for i in (1, 2):
        plan.union(f"{suf}_larg{i}", suf, f"rail{i}", "perno",
                   "pared de la guarda atornillada a la cara interior del larguero", size="M8",
                   qty=2)


def de_tambores(plan: Plan, c: Cotas) -> None:
    de_tambor(plan, c, "guarda_m", "Guarda del tambor motriz", c.half, c.r_m, 1.0, 0.0, False)
    de_tambor(plan, c, "guarda_c", "Guarda del tambor de cola", -c.half, c.r_c, -1.0, c.viaje,
              True)
