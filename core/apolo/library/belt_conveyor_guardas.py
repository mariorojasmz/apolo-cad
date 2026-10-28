"""Resguardos de `create_belt_conveyor` (v4–v5), todos de chapa ATORNILLADA (se quitan con
herramienta, ISO 14120):

- guarda lateral en L sobre cada larguero: la pared contiene los paquetes y el ala tapa por
  arriba la ranura entre el borde de la banda y el larguero (3 mm a la banda), por donde se
  llegaba a las cuñas banda ↔ tambor en los extremos de los tambores;
- guarda de cada tambor: bandeja bajo el ramal de retorno, paredes a ras de la cara interior de
  los largueros y tapa de extremo; la de cola lleva además techo sobre el tambor (la cabeza
  descarga por arriba). Llega ≥ 330 mm hacia adentro de la cuña: desde el piso, un brazo no
  alcanza la cuña rodeando la bandeja (850 mm de alcance, ISO 13857);
- v5 (`cierres`): guarda inferior en L bajo la ranura banda ↔ larguero entre las guardas de los
  tambores (`inferiores`); el techo de la guarda de cola cubre el tramo libre de la banda hasta
  pasar la punta de la cama, y las paredes se escotan en las placas de los soportes de la cama.
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
HOLGURA_ALA = 10.0        # v5: del ala de la guarda inferior al ramal de retorno
SOLAPE_PARED = 30.0       # v5: pared de la guarda inferior sobre el alma del larguero (pernos)
TRAMO_MAX = 3000.0        # v5: largo máximo de un tramo de guarda inferior (plegadora de taller)
TECHO_SOBRE_CAMA = 20.0   # v5: el techo de la guarda de cola pasa la punta de la cama (banda apoyada)


def laterales(plan: Plan, c: Cotas) -> None:
    """Una guarda lateral por larguero y por TRAMO (v6: se corta en cada empalme)."""
    from .belt_conveyor_tramos import rail, tramos_guarda

    yb = c.ancho / 2.0 + HOLGURA_BANDA
    z0 = c.rail_top
    tramos = tramos_guarda(c)
    for i, s in ((1, -1.0), (2, 1.0)):
        for k, (x0, x1) in enumerate(tramos, start=1):
            suf = f"guarda{i}" if len(tramos) == 1 else f"guarda{i}_{k}"
            nombre = f"Guarda lateral ({i})" if len(tramos) == 1 else \
                f"Guarda lateral ({i}, tramo {k})"
            pared = caja(x0, x1, s * yb, s * (yb + CHAPA), z0, z0 + ALTO_PARED)
            ala = caja(x0, x1, s * yb, s * c.y_out, z0, z0 + CHAPA)
            plan.pieza(suf, nombre, pared + ala, material="acero")
            plan.union(f"{suf}_larg", suf, rail(c, i, (x0 + x1) / 2.0), "perno",
                       "ala de la guarda atornillada sobre el larguero", size="M6",
                       qty=math.ceil((x1 - x0) / 600.0) + 1)


def z_retorno(c: Cotas) -> float:
    """Cara inferior del ramal de retorno."""
    return min(c.zm - c.r_m, c.zc - c.r_c) - c.t


def x_de_tambor(c: Cotas, xd: float, r: float, sentido: float,
                viaje: float) -> tuple[float, float, float]:
    """(punta hacia adentro, cara interior de la tapa de extremo, cara exterior) de la guarda
    del tambor en `xd` (`sentido` +1: hacia +X)."""
    out = xd + sentido * (r + c.t + viaje + HOLGURA_EXTREMO)
    disponible = (c.largo - c.r_m - c.r_c - c.carrera) / 2.0 - 40.0
    inb = xd - sentido * (r + viaje + max(40.0, min(ALCANCE, disponible)))
    return inb, out, out + sentido * CHAPA


def _escotar(pared, c: Cotas, s: float, x0: float, x1: float, z_top: float):
    """La pared (a ras de la cara interior del larguero, lado `s`) escotada donde bajan las
    placas de los soportes de la cama (con 1 mm de juego), si llega a ellas."""
    from .belt_conveyor_bastidor import x_soportes, z_soportes

    z_sop = z_soportes(c)[0] - 1.0
    if z_top <= z_sop:
        return pared
    x0, x1 = sorted((x0, x1))
    for xs in x_soportes(c):
        if x0 < xs + 31.0 and xs - 31.0 < x1:
            pared = pared - caja(xs - 31.0, xs + 31.0, s * (c.y_in - CHAPA - 1.0),
                                 s * (c.y_in + 1.0), z_sop, z_top + 1.0)
    return pared


def de_tambor(plan: Plan, c: Cotas, suf: str, nombre: str, xd: float, r: float, sentido: float,
              viaje: float, techo: bool) -> None:
    """Caja de chapa alrededor del extremo de un tambor (`sentido` +1: hacia +X). Con los cierres
    de la v5, sus paredes se escotan en las placas de los soportes de la cama (un larguero de poco
    canto las cruzaba) y el techo de la de cola llega hasta pasar la punta de la cama
    (`TECHO_SOBRE_CAMA`): el tramo libre de la banda entre el tambor y la cama (la carrera del
    tensor) quedaba abierto por arriba junto al borde y la mano, empujando la banda, bajaba a la
    cuña de cola por dentro del lazo (medido con el brazo doblado en una faja de 8 m)."""
    zp0 = z_retorno(c) - HOLGURA_RETORNO - CHAPA
    inb, out, xe = x_de_tambor(c, xd, r, sentido, viaje)
    z_pared = min(c.rail_bot + 20.0, c.zm - c.d_m / 2.0 - 6.0, c.zc - c.d_c / 2.0 - 6.0)
    forma = caja(inb, xe, -c.y_in, c.y_in, zp0, zp0 + CHAPA)                       # bandeja
    for s in (-1.0, 1.0):                                                             # paredes
        pared = caja(inb, xe, s * (c.y_in - CHAPA), s * c.y_in, zp0, z_pared)
        forma = forma + (_escotar(pared, c, s, inb, xe, z_pared) if c.cierres else pared)
    forma = forma + caja(out, xe, -c.y_in, c.y_in, zp0, c.rail_top)                  # extremo
    if techo:
        yb = c.ancho / 2.0 + HOLGURA_BANDA
        x_techo = xd - sentido * 5.0
        if c.cierres and sentido < 0:  # el techo es de la de cola
            x_techo = max(x_techo, c.cama_x0 + TECHO_SOBRE_CAMA)
        forma = forma + caja(out, xe, -yb, yb, c.rail_top - 1.0, c.rail_top + CHAPA)
        forma = forma + caja(x_techo, xe, -yb, yb, c.rail_top + CHAPA, c.rail_top + 2.0 * CHAPA)
    plan.pieza(suf, nombre, forma, material="acero")
    from .belt_conveyor_tramos import rail

    for i in (1, 2):
        plan.union(f"{suf}_larg{i}", suf, rail(c, i, xd), "perno",
                   "pared de la guarda atornillada a la cara interior del larguero", size="M8",
                   qty=2)


def inferiores(plan: Plan, c: Cotas) -> None:
    """v5: guarda inferior a cada lado, entre las guardas de los tambores, bajo la ranura de
    `BANDA_A_LARGUERO` entre el borde de la banda y el larguero (abierta por abajo: por ahí el
    brazo DOBLADO entraba al lazo y bajaba la mano a las cuñas de los dos tambores, ISO 13857
    tabla 6; F6 de puerta-de-publicacion). Chapa plegada en L: la pared, atornillada al alma
    interior del larguero con pernos pasantes (tuerca por fuera); el ala, horizontal a
    `HOLGURA_ALA` bajo el ramal de retorno y por FUERA del borde de la banda (no la toca ni la
    estrecha). En tramos de ≤ `TRAMO_MAX` (lo que dobla una plegadora de taller), a 1 mm entre sí;
    la pared se escota donde bajan las placas de los soportes de la cama. v6: se corta en cada
    soporte de rodillo de retorno (el soporte y el rodillo llenan ese hueco); cruza los empalmes
    de una pieza (va atornillada a un solo tramo: se quita antes de separar los tramos)."""
    from .belt_conveyor_retorno import media_huella, x_rodillos
    from .belt_conveyor_tramos import rail

    xa = x_de_tambor(c, -c.half, c.r_c, -1.0, c.viaje)[0] + 1.0
    xb = x_de_tambor(c, c.half, c.r_m, 1.0, 0.0)[0] - 1.0
    if xb - xa < 50.0:
        return  # las guardas de los tambores ya se tocan: no queda ranura entre ellas
    z0 = z_retorno(c) - HOLGURA_ALA - CHAPA
    z_top = c.rail_bot + SOLAPE_PARED
    y_borde = c.ancho / 2.0 + 1.0
    bordes = [xa]
    for x in x_rodillos(c):
        h = media_huella(c)
        bordes += [x - h, x + h]
    bordes.append(xb)
    piezas = []
    for a, b in zip(bordes[::2], bordes[1::2]):
        if b - a < 50.0:
            continue
        n = math.ceil((b - a) / TRAMO_MAX)
        largo = (b - a - (n - 1) * 1.0) / n
        piezas += [(a + (k - 1) * (largo + 1.0), largo) for k in range(1, n + 1)]
    for i, s in ((1, -1.0), (2, 1.0)):
        for k, (x0, largo) in enumerate(piezas, start=1):
            x1 = x0 + largo
            pared = _escotar(caja(x0, x1, s * (c.y_in - CHAPA), s * c.y_in, z0, z_top), c, s,
                             x0, x1, z_top)
            ala = caja(x0, x1, s * y_borde, s * (c.y_in - CHAPA + 0.5), z0, z0 + CHAPA)
            suf = f"guarda_inf{i}_{k}"
            nombre = (f"Guarda inferior ({i})" if len(piezas) == 1
                      else f"Guarda inferior ({i}, tramo {k})")
            plan.pieza(suf, nombre, pared + ala, material="acero")
            plan.union(f"{suf}_larg", suf, rail(c, i, (x0 + x1) / 2.0), "perno",
                       "pared de la guarda al alma interior del larguero: perno pasante + tuerca "
                       "por fuera", size="M6", qty=math.ceil(largo / 600.0) + 1)


def de_tambores(plan: Plan, c: Cotas) -> None:
    de_tambor(plan, c, "guarda_m", "Guarda del tambor motriz", c.half, c.r_m, 1.0, 0.0, False)
    de_tambor(plan, c, "guarda_c", "Guarda del tambor de cola", -c.half, c.r_c, -1.0, c.viaje,
              True)
