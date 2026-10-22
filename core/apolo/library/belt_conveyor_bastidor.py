"""Bastidor de `create_belt_conveyor` (v4): largueros con el paso de los ejes, patas con pie
nivelador, travesaños y la cama de deslizamiento con sus soportes; en la v5, las placas de
cierre de las puntas de los largueros.

Uniones (D: lo que la plantilla toca, lo declara ella):
- patas soldadas bajo los largueros y travesaños soldados entre patas: el marco soldado queda
  FUERA del lazo de la banda;
- la cama y sus soportes van ATORNILLADOS (soportes con placa de extremo a la cara interior del
  larguero): nada soldado abraza la banda, que se cambia de costado quitando pernos;
- pie nivelador roscado en la placa soldada al pie de la pata; el disco del pie es el anclaje.
"""

from __future__ import annotations

import math

from build123d import Cylinder, Pos

from apolo.kernel.shapes import place

from .belt_conveyor_cotas import (
    BRACE_REF,
    CAMA_T,
    FOOT_REF,
    HOLGURA_EJE,
    LEG_REF,
    LEG_W,
    NIVELACION_MM,
    PLACA_PATA,
    PLACA_PATA_T,
    PLACA_SOPORTE_T,
    SOPORTE_PASO,
    VANO_MAX,
    Cotas,
)
from .belt_conveyor_plan import Plan, caja, cilindro_y, ranura_x
from .catalog import CATALOG, build_component

CIERRE_T = 3.0           # placa de cierre de la punta del larguero (v5)


def material_de(ref: str) -> str:
    """El material de ficha de una referencia (los tubos son acero ASTM A500)."""
    return str(CATALOG[ref].specs.get("material") or "acero")


def largueros(plan: Plan, c: Cotas) -> None:
    """Dos largueros de tubo a lo largo de X con el paso de los ejes por el ALMA: barreno
    Ø eje + 6 en el motriz y, con tensor, la ranura de su carrera en la cola."""
    largo = c.x1 - c.x0
    base, cut = build_component(c.tubo, largo)
    xc, zc_rail = (c.x0 + c.x1) / 2.0, c.rail_top - c.rail_h / 2.0
    mat = material_de(c.tubo)
    for i, s in ((1, -1.0), (2, 1.0)):
        y0, y1 = s * (c.y_in - 1.0), s * (c.y_out + 1.0)
        pasos = cilindro_y(c.half, c.zm, y0, y1, c.d_m / 2.0 + HOLGURA_EJE)
        if c.uct:
            alto = c.d_c + 2.0 * HOLGURA_EJE
            pasos = pasos + ranura_x(-c.half, c.zc, y0, y1, c.carrera + alto, alto)
        else:
            pasos = pasos + cilindro_y(-c.half, c.zc, y0, y1, c.d_c / 2.0 + HOLGURA_EJE)
        forma = place(base, (xc, s * c.rail_y, zc_rail), (0, 90, 0)) - pasos
        plan.pieza(f"rail{i}", f"Larguero ({i})", forma, comp=c.tubo, cut=cut, material=mat)


def estaciones(c: Cotas) -> list[float]:
    """X de las estaciones de patas: cola (junto al tensor) y cabeza (bajo el eje motriz)
    numeradas 1 y 2, y las intermedias que hagan falta para que ningún vano pase de
    `VANO_MAX` (numeradas desde 3, de la cola a la cabeza)."""
    vano = c.x_leg_h - c.x_leg_t
    n = max(1, math.ceil(vano / VANO_MAX - 1e-9))
    return [c.x_leg_t, c.x_leg_h] + [c.x_leg_t + k * vano / n for k in range(1, n)]


def patas(plan: Plan, c: Cotas) -> None:
    """Patas soldadas bajo los largueros (dos por estación), cada una con su placa y pie
    nivelador, y un travesaño soldado entre las dos patas de cada estación. Las 4 primeras son
    las de los extremos (la 4 sostiene la base del motor)."""
    foot = CATALOG[FOOT_REF].params
    disco_t, alt, rosca = float(foot["disco_t"]), float(foot["altura"]), float(foot["rosca"])
    z_placa = disco_t + NIVELACION_MM
    z_leg0 = z_placa + PLACA_PATA_T
    leg_len = c.rail_bot - z_leg0
    leg, leg_cut = build_component(LEG_REF, leg_len)
    pie, _ = build_component(FOOT_REF)
    mat = material_de(LEG_REF)
    n = 1
    for x in estaciones(c):
        for s in (-1.0, 1.0):
            y = s * c.leg_y
            plan.pieza(f"leg{n}", f"Pata ({n})", leg, comp=LEG_REF, cut=leg_cut,
                       pos=(x, y, z_leg0 + leg_len / 2.0), key=f"comp|{LEG_REF}|{leg_cut}",
                       material=mat)
            h = PLACA_PATA / 2.0
            placa = (caja(x - h, x + h, y - h, y + h, z_placa, z_leg0)  # rosca del pie
                     - Pos(x, y, (z_placa + z_leg0) / 2.0) * Cylinder(rosca / 2.0,
                                                                      PLACA_PATA_T + 2.0))
            plan.pieza(f"placa{n}", f"Placa de la pata ({n})", placa, material="acero")
            plan.pieza(f"foot{n}", f"Pie nivelador ({n})", pie, comp=FOOT_REF,
                       pos=(x, y, disco_t + alt / 2.0), key=f"comp|{FOOT_REF}|std")
            rail = "rail1" if s < 0 else "rail2"
            plan.union(f"larg_pata{n}", f"leg{n}", rail, "soldadura",
                       "pata soldada bajo el larguero (4 lados)", throat_mm=3,
                       length_mm=round(4 * LEG_W, 1))
            plan.union(f"placa_pata{n}", f"placa{n}", f"leg{n}", "soldadura",
                       "placa soldada al pie de la pata", throat_mm=3,
                       length_mm=round(4 * LEG_W, 1))
            plan.union(f"pie{n}", f"foot{n}", f"placa{n}", "contacto",
                       f"vástago M{rosca:g} roscado en la placa: girarlo nivela "
                       f"±{NIVELACION_MM:g} mm")
            plan.anclaje(f"piso{n}", f"foot{n}", "disco del pie nivelador apoyado en el piso")
            n += 1
    largo = 2.0 * c.y_in
    trav, cut = build_component(BRACE_REF, largo)
    z_b = round(0.35 * c.rail_bot, 1)
    for i, x in enumerate(estaciones(c), start=1):
        plan.pieza(f"brace{i}", f"Travesaño ({i})", trav, comp=BRACE_REF, cut=cut,
                   pos=(x, 0.0, z_b), rot=(90, 0, 0), key=f"comp|{BRACE_REF}|{cut}",
                   material=material_de(BRACE_REF))
        for j, k in ((1, 2 * i - 1), (2, 2 * i)):
            plan.union(f"trav{i}_pata{j}", f"brace{i}", f"leg{k}", "soldadura",
                       "travesaño soldado entre las patas", throat_mm=3,
                       length_mm=round(4 * LEG_W, 1))


def x_soportes(c: Cotas) -> list[float]:
    """X de los soportes de la cama: cada ≤ `SOPORTE_PASO`, a 40 mm de las puntas de la cama."""
    x0, x1 = c.cama_x0, c.cama_x1
    n = max(2, math.ceil((x1 - x0) / SOPORTE_PASO) + 1)
    paso = (x1 - x0 - 2.0 * 40.0) / (n - 1)
    return [x0 + 40.0 + (k - 1) * paso for k in range(1, n + 1)]


def z_soportes(c: Cotas) -> tuple[float, float]:
    """(z0, z1) de los soportes de la cama y de sus placas de extremo (bajo la chapa)."""
    z1 = c.cama_top - CAMA_T
    return z1 - LEG_W, z1


def placas_de_cierre(plan: Plan, c: Cotas) -> None:
    """v5: placa de chapa SOLDADA en cada punta de los largueros (cordón perimetral): el tubo
    abierto dejaba entrar el brazo por adentro hasta la ranura del tensor y la cuña de cola (F6
    de puerta-de-publicacion). Es estructura, no resguardo: detrás no hay nada que mantener."""
    perimetro = round(2.0 * (c.rail_t + c.rail_h), 1)
    for i, s in ((1, -1.0), (2, 1.0)):
        for x0, lado in ((c.x0 - CIERRE_T, "cola"), (c.x1, "cabeza")):
            suf = f"cierre{i}_{lado}"
            plan.pieza(suf, f"Placa de cierre del larguero ({i}, {lado})",
                       caja(x0, x0 + CIERRE_T, s * c.y_in, s * c.y_out, c.rail_bot, c.rail_top),
                       material="acero")
            plan.union(f"{suf}_sold", suf, f"rail{i}", "soldadura",
                       "placa soldada a la punta del tubo (cordón perimetral)", throat_mm=2,
                       length_mm=perimetro)


def cama(plan: Plan, c: Cotas) -> None:
    """Cama de deslizamiento (chapa) atornillada sobre soportes transversales cada ≤ 800 mm;
    cada soporte es un tubo con placas de extremo soldadas, atornilladas a los largueros."""
    x0, x1 = c.cama_x0, c.cama_x1
    w = c.ancho / 2.0 + 10.0
    top = c.cama_top
    plan.pieza("cama", "Cama de deslizamiento", caja(x0, x1, -w, w, top - CAMA_T, top),
               material="acero")
    largo = 2.0 * (c.y_in - PLACA_SOPORTE_T)
    tubo, cut = build_component(LEG_REF, largo)
    z0, z1 = z_soportes(c)
    for k, x in enumerate(x_soportes(c), start=1):
        sop = f"sop{k}"
        plan.pieza(sop, f"Soporte de cama ({k})", tubo, comp=LEG_REF, cut=cut,
                   pos=(x, 0.0, (z0 + z1) / 2.0), rot=(90, 0, 0), key=f"comp|{LEG_REF}|{cut}",
                   material=material_de(LEG_REF))
        for lado, s, rail in (("m", -1.0, "rail1"), ("p", 1.0, "rail2")):
            placa = f"{sop}_{lado}"
            plan.pieza(placa, f"Placa del soporte de cama ({k}, {'−' if s < 0 else '+'}Y)",
                       caja(x - 30.0, x + 30.0, s * (c.y_in - PLACA_SOPORTE_T), s * c.y_in, z0, z1),
                       material="acero")
            plan.union(f"{sop}_{lado}_sold", sop, placa, "soldadura",
                       "placa de extremo soldada al soporte", throat_mm=3,
                       length_mm=round(4 * LEG_W, 1))
            plan.union(f"{sop}_{lado}_larg", placa, rail, "perno",
                       "placa del soporte atornillada al alma del larguero", size="M8", qty=2)
        plan.union(f"cama_{sop}", "cama", sop, "perno",
                   "cama atornillada al soporte (tornillos avellanados)", size="M6", qty=2)
