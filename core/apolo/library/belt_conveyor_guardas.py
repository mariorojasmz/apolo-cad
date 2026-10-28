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
  pasar la punta de la cama, y las paredes se escotan en las placas de los soportes de la cama;
- F1b (`lado_abierto`): el costado de los operarios lleva, a lo largo de la faja, una guarda
  cubre-ranura a ras de la banda (sin pared: el paquete se toma por ahí) y la guarda en L sólo en
  la cabeza, hasta `ALCANCE` antes de la cuña de entrada del tambor motriz.
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
    """Una guarda lateral por larguero y por TRAMO (v6: se corta en cada empalme). En el costado
    de `lado_abierto` (F1b), la guarda cubre-ranura (`_cubre_ranura`) a lo largo de la faja y la
    guarda en L sólo en la cabeza (`x_pared_de_cabeza`)."""
    from .belt_conveyor_tramos import JUNTA_GUARDA, rail, tramos_guarda

    yb = c.ancho / 2.0 + HOLGURA_BANDA
    z0 = c.rail_top
    tramos = tramos_guarda(c)
    xw = x_pared_de_cabeza(c)
    taller = c.criterio >= 8
    for i, s in ((1, -1.0), (2, 1.0)):
        abierto = c.lado_sin_pared == s
        for k, (x0, x1) in enumerate(tramos, start=1):
            suf = f"guarda{i}" if len(tramos) == 1 else f"guarda{i}_{k}"
            tramo = "" if len(tramos) == 1 else f", {'paño' if taller else 'tramo'} {k}"
            piezas = [(suf, f"Guarda lateral ({i}{tramo})", x0, x1, False)]
            if abierto:
                piezas = [(suf, f"Guarda cubre-ranura ({i}{tramo})", x0,
                           min(x1, xw - JUNTA_GUARDA), True)]
                if x1 > xw:
                    piezas.append((f"guarda{i}_cabeza", f"Guarda lateral de cabeza ({i})",
                                   max(x0, xw + JUNTA_GUARDA), x1, False))
            for sf, nombre, a, b, cubre in piezas:
                if b - a < 1.0:
                    continue
                if cubre:
                    forma = _cubre_ranura(c, s, a, b)
                    nota = ("guarda cubre-ranura atornillada sobre el larguero (tornillos M6 a "
                            "rosca en la pared superior del tubo)")
                else:
                    forma = (caja(a, b, s * yb, s * (yb + CHAPA), z0, z0 + ALTO_PARED)
                             + caja(a, b, s * yb, s * c.y_out, z0, z0 + CHAPA))
                    nota = "ala de la guarda atornillada sobre el larguero"
                qty = math.ceil((b - a) / 600.0) + 1
                if taller:  # F1c (D12, D14): espárragos soldados al larguero, nada adentro
                    from . import belt_conveyor_guardas_taller as gt

                    forma = gt.taladrar_ala(forma, c, s, gt.pernos_ala(a, b, qty))
                    nota = gt.nota_ala(cubre)
                plan.pieza(sf, nombre, forma, material="acero")
                plan.union(f"{sf}_larg", sf, rail(c, i, (a + b) / 2.0), "perno", nota,
                           size="M6", qty=qty)


def x_pared_de_cabeza(c: Cotas) -> float:
    """F1b (D7): desde dónde (X) el costado abierto vuelve a llevar la guarda en L: `ALCANCE`
    antes de donde la banda entra al tambor motriz (su cuña de ENTRADA, arriba). Sin esa pared,
    con el brazo doblado sobre el larguero la mano empuja el borde de la banda hasta la cuña (lo
    midió la puerta en la de 4 m: 4 sondas con el brazo doblado por −Y, 5 por +Y); con ella, como
    la guarda del tambor, la cuña queda a ≥ `ALCANCE` del hueco y la puerta da los 5 peligros
    resguardados. Sin el labio del cubre-ranura, en cambio, se llega a la cuña de cola por la
    ranura (1 sonda por −Y). La cola no lleva pared: arriba la banda SALE del tambor."""
    return c.half - c.r_m - ALCANCE


def _cubre_ranura(c: Cotas, s: float, x0: float, x1: float):
    """F1b (D7): la guarda del costado de los operarios, sin pared (el paquete se toma por ese
    lado). La ranura de `BANDA_A_LARGUERO` entre el borde de la banda y el larguero sigue
    tapada: por ella el brazo bajaba a las cuñas banda ↔ tambor en los extremos de los tambores
    (ISO 13857 tabla 4: por una ranura de más de 20 mm pasa el brazo, pide ≥ 850 mm al peligro).
    Chapa con quiebre: el LABIO sobre la ranura con su cara superior A RAS de la cara de la banda
    (`altura`), a `HOLGURA_BANDA` del borde (e = 3 mm: ISO 13857 tabla 4, e ≤ 4 → sr ≥ 2 mm, sin
    distancia que cumplir) y el ala atornillada sobre el larguero, que sale 2 mm sobre la banda a
    35 mm de su borde. El labio va entre las tapas de extremo de las guardas de los tambores (más
    allá ya cierran ellas) y queda ≥ 1 mm sobre el tope de los tambores (con una banda de menos
    de 4 mm el labio sube lo que pide eso y su unión con el ala: hasta 2 mm sobre la banda)."""
    yb = c.ancho / 2.0 + HOLGURA_BANDA
    ala = caja(x0, x1, s * (c.y_in - 2.0), s * c.y_out, c.rail_top, c.rail_top + CHAPA)
    xa = max(x0, x_de_tambor(c, c.x_tc, c.r_c, -1.0, c.viaje)[1])
    xb = min(x1, x_de_tambor(c, c.half, c.r_m, 1.0, 0.0)[1])
    if xb - xa < 1.0:
        return ala
    z0 = max(c.altura - CHAPA, c.altura - c.t + 1.0)       # 1 mm sobre el tope de los tambores
    z1 = max(c.altura, c.rail_top + 1.0)                    # a ras de la banda, unido al ala
    return ala + caja(xa, xb, s * yb, s * c.y_in, z0, z1)


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
    nota = "pared de la guarda atornillada a la cara interior del larguero"
    if c.criterio >= 8:  # F1c (D12): orejas con su agujero y perno pasante con buje
        from . import belt_conveyor_guardas_taller as gt

        for s in (-1.0, 1.0):
            forma = gt.orejas_tambor(forma, c, s, gt.pernos_tambor(c, xd, inb), z_pared)
        nota = gt.nota_tambor(c)
    plan.pieza(suf, nombre, forma, material="acero")
    from .belt_conveyor_tramos import rail

    for i in (1, 2):
        plan.union(f"{suf}_larg{i}", suf, rail(c, i, xd), "perno", nota, size="M8", qty=2)


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
    from .belt_conveyor_tramos import rail

    piezas = piezas_inferiores(c)
    if not piezas:
        return  # las guardas de los tambores ya se tocan: no queda ranura entre ellas
    z0 = z_retorno(c) - HOLGURA_ALA - CHAPA
    z_top = c.rail_bot + SOLAPE_PARED
    y_borde = c.ancho / 2.0 + 1.0
    taller = c.criterio >= 8
    for i, s in ((1, -1.0), (2, 1.0)):
        for k, (x0, largo) in enumerate(piezas, start=1):
            x1 = x0 + largo
            pared = _escotar(caja(x0, x1, s * (c.y_in - CHAPA), s * c.y_in, z0, z_top), c, s,
                             x0, x1, z_top)
            ala = caja(x0, x1, s * y_borde, s * (c.y_in - CHAPA + 0.5), z0, z0 + CHAPA)
            nota = ("pared de la guarda al alma interior del larguero: perno pasante + tuerca "
                    "por fuera")
            forma = pared + ala
            if taller:  # F1c (D12): sus agujeros y los del larguero, con buje
                from . import belt_conveyor_guardas_taller as gt

                forma = gt.taladrar_inferior(forma, c, s, gt.pernos_inferior(c, i, x0, x1))
                nota = gt.nota_inferior(c)
            suf = f"guarda_inf{i}_{k}"
            nombre = (f"Guarda inferior ({i})" if len(piezas) == 1
                      else f"Guarda inferior ({i}, tramo {k})")
            plan.pieza(suf, nombre, forma, material="acero")
            plan.union(f"{suf}_larg", suf, rail(c, i, (x0 + x1) / 2.0), "perno", nota,
                       size="M6", qty=math.ceil(largo / 600.0) + 1)


def piezas_inferiores(c: Cotas) -> list[tuple[float, float]]:
    """(x0, largo) de cada guarda inferior (iguales a los dos lados): entre las guardas de los
    tambores, cortadas en cada rodillo de retorno y en tramos de ≤ `TRAMO_MAX`."""
    from .belt_conveyor_retorno import media_huella, x_rodillos

    xa = x_de_tambor(c, c.x_tc, c.r_c, -1.0, c.viaje)[0] + 1.0
    xb = x_de_tambor(c, c.half, c.r_m, 1.0, 0.0)[0] - 1.0
    if xb - xa < 50.0:
        return []
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
    return piezas


def de_tambores(plan: Plan, c: Cotas) -> None:
    de_tambor(plan, c, "guarda_m", "Guarda del tambor motriz", c.half, c.r_m, 1.0, 0.0, False)
    de_tambor(plan, c, "guarda_c", "Guarda del tambor de cola", c.x_tc, c.r_c, -1.0, c.viaje,
              True)
