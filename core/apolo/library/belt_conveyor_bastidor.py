"""Bastidor de `create_belt_conveyor` (v4): largueros con el paso de los ejes, patas con pie
nivelador, travesaños y la cama de deslizamiento con sus soportes; en la v5, las placas de
cierre de las puntas de los largueros.

Uniones (D: lo que la plantilla toca, lo declara ella):
- patas soldadas bajo los largueros y travesaños soldados entre patas: el marco soldado queda
  FUERA del lazo de la banda;
- la cama y sus soportes van ATORNILLADOS (soportes con placa de extremo a la cara interior del
  larguero): nada soldado abraza la banda, que se cambia de costado quitando pernos;
- pie nivelador roscado en la placa soldada al pie de la pata; el disco del pie es el anclaje.

v6 (plan faja-larga-en-tramos): con `tramo_max` cada larguero y la cama salen por TRAMO
(`belt_conveyor_tramos.py`) y las estaciones de patas incluyen una bajo cada empalme; con el
criterio 6, la placa del soporte de cama va con perno PASANTE que cruza el larguero por un buje
soldado (la tuerca, por fuera: `belt_conveyor_retorno.py` explica por qué no remache) y los
soportes extremos se corren lo que haga falta para que esa tuerca no quede bajo el marco del
tensor o la placa porta-chumacera.
"""

from __future__ import annotations

import math

from build123d import Cylinder, Pos

from apolo.kernel.shapes import place

from .belt_conveyor_cotas import (
    BRACE_REF,
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
from .belt_conveyor_tramos import cama as cama_suf
from .belt_conveyor_tramos import nombre_larguero, pata_de_empalme, rail, tramos_cama
from .catalog import CATALOG, build_component

CIERRE_T = 3.0           # placa de cierre de la punta del larguero (v5)
LLAVE_M8 = 16.0          # v6: radio de la llave de vaso de la tuerca M8 (la de un perno pasante)


def material_de(ref: str) -> str:
    """El material de ficha de una referencia (los tubos son acero ASTM A500)."""
    return str(CATALOG[ref].specs.get("material") or "acero")


def largueros(plan: Plan, c: Cotas) -> None:
    """Dos largueros de tubo a lo largo de X con el paso de los ejes por el ALMA: barreno
    Ø eje + 6 en el motriz y, con tensor, la ranura de su carrera en la cola."""
    from .belt_conveyor_retorno import bujes, pasantes

    zc_rail = c.rail_top - c.rail_h / 2.0
    mat = material_de(c.tubo)
    tramos = c.tramos or ((c.x0, c.x1),)
    for i, s in ((1, -1.0), (2, 1.0)):
        y0, y1 = s * (c.y_in - 1.0), s * (c.y_out + 1.0)
        paso_m = cilindro_y(c.half, c.zm, y0, y1, c.d_m / 2.0 + HOLGURA_EJE)
        if c.uct:
            alto = c.d_c + 2.0 * HOLGURA_EJE
            paso_c = ranura_x(-c.half, c.zc, y0, y1, c.carrera + alto, alto)
        else:
            paso_c = cilindro_y(-c.half, c.zc, y0, y1, c.d_c / 2.0 + HOLGURA_EJE)
        pernos = pasantes(c, i)
        if c.criterio >= 8:  # F1c (D12): también los pasantes de las guardas
            from .belt_conveyor_guardas_taller import pasantes_de_guardas

            pernos = pernos + pasantes_de_guardas(c, i)
        for k, (a, b) in enumerate(tramos, start=1):
            base, cut = build_component(c.tubo, b - a)
            forma = place(base, ((a + b) / 2.0, s * c.rail_y, zc_rail), (0, 90, 0))
            if len(tramos) == 1:
                forma = forma - (paso_m + paso_c)
            elif k == 1:
                forma = forma - paso_c
            elif k == len(tramos):
                forma = forma - paso_m
            forma = bujes(forma, c, s, [p for p in pernos if a < p[0] < b])
            plan.pieza(rail(c, i, (a + b) / 2.0), nombre_larguero(c, i, k), forma, comp=c.tubo,
                       cut=cut, material=mat)


def estaciones(c: Cotas) -> list[float]:
    """X de las estaciones de patas: cola (junto al tensor) y cabeza (bajo el eje motriz)
    numeradas 1 y 2; después, de la cola a la cabeza, la de cada empalme (v6) y las intermedias
    que hagan falta para que ningún vano pase de `VANO_MAX`. Se calculan JUNTAS: las fijas
    primero y las intermedias repartidas en cada vano entre fijas, así ninguna pata cae sobre una
    placa de empalme."""
    fijas = [c.x_leg_t] + [pata_de_empalme(s) for s in c.empalmes] + [c.x_leg_h]
    extra = []
    for a, b in zip(fijas, fijas[1:]):
        vano = b - a
        n = max(1, math.ceil(vano / VANO_MAX - 1e-9))
        extra += [a + k * vano / n for k in range(1, n)]
    return [c.x_leg_t, c.x_leg_h] + sorted(fijas[1:-1] + extra)


def patas(plan: Plan, c: Cotas) -> None:
    """Patas soldadas bajo los largueros (dos por estación), cada una con su placa y pie
    nivelador, y un travesaño soldado entre las dos patas de cada estación. Las 4 primeras son
    las de los extremos (la 4 sostiene la base del motor). Con el criterio 7 (F1b, D8) la placa
    lleva la tuerca del pie soldada por debajo y el vástago su contratuerca
    (`belt_conveyor_pies.py`: por qué no rosca en la placa)."""
    foot = CATALOG[FOOT_REF].params
    disco_t, alt, rosca = float(foot["disco_t"]), float(foot["altura"]), float(foot["rosca"])
    pie7 = _pila7(c)
    z_leg0 = z_pata0(c)
    z_placa = z_leg0 - PLACA_PATA_T
    barreno = pie7.barreno if pie7 else rosca
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
            placa = (caja(x - h, x + h, y - h, y + h, z_placa, z_leg0)  # paso del vástago
                     - Pos(x, y, (z_placa + z_leg0) / 2.0) * Cylinder(barreno / 2.0,
                                                                      PLACA_PATA_T + 2.0))
            plan.pieza(f"placa{n}", f"Placa de la pata ({n})", placa, material="acero")
            plan.pieza(f"foot{n}", f"Pie nivelador ({n})", pie, comp=FOOT_REF,
                       pos=(x, y, disco_t + alt / 2.0), key=f"comp|{FOOT_REF}|std")
            plan.union(f"larg_pata{n}", f"leg{n}", rail(c, 1 if s < 0 else 2, x), "soldadura",
                       "pata soldada bajo el larguero (4 lados)", throat_mm=3,
                       length_mm=round(4 * LEG_W, 1))
            plan.union(f"placa_pata{n}", f"placa{n}", f"leg{n}", "soldadura",
                       "placa soldada al pie de la pata", throat_mm=3,
                       length_mm=round(4 * LEG_W, 1))
            if pie7:
                _tuercas_del_pie(plan, pie7, n, x, y)
            else:
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


def _pila7(c: Cotas):
    """La pila del pie con tuerca soldada y contratuerca (criterio 7), o None antes."""
    from .belt_conveyor_pies import pila

    return pila(FOOT_REF, PLACA_PATA_T) if c.criterio >= 7 else None


def z_pata0(c: Cotas) -> float:
    """Z del arranque del tubo de las patas (cara superior de la placa de la pata)."""
    p = _pila7(c)
    if p is not None:
        return p.z_pata0
    return float(CATALOG[FOOT_REF].params["disco_t"]) + NIVELACION_MM + PLACA_PATA_T


def _tuercas_del_pie(plan: Plan, p, n: int, x: float, y: float) -> None:
    """Criterio 7: tuerca de la rosca del pie soldada bajo la placa de la pata y contratuerca
    del vástago apretada contra ella (las dos de catálogo, DIN 934)."""
    tuerca, _ = build_component(p.tuerca)
    key = f"comp|{p.tuerca}|std"
    plan.pieza(f"tuerca_pie{n}", f"Tuerca soldada del pie ({n})", tuerca, comp=p.tuerca,
               pos=(x, y, p.z_tuerca), key=key)
    plan.pieza(f"contra_pie{n}", f"Contratuerca del pie ({n})", tuerca, comp=p.tuerca,
               pos=(x, y, p.z_contra), key=key)
    plan.union(f"tuerca_placa{n}", f"tuerca_pie{n}", f"placa{n}", "soldadura",
               "tuerca de la rosca del pie soldada bajo la placa", throat_mm=2,
               length_mm=round(2.0 * math.sqrt(3.0) * p.tuerca_ac, 1))
    plan.union(f"pie{n}", f"foot{n}", f"tuerca_pie{n}", "contacto",
               f"vástago M{p.rosca:g} roscado en la tuerca soldada bajo la placa: girarlo nivela "
               f"±{p.recorrido / 2.0:g} mm")
    plan.union(f"contra_pie{n}", f"contra_pie{n}", f"foot{n}", "contacto",
               f"contratuerca M{p.rosca:g} del vástago apretada contra la tuerca soldada (llave de "
               f"boca {p.tuerca_ac:g} desde el costado): traba la altura nivelada")


def x_soportes(c: Cotas) -> list[float]:
    """X de los soportes de la cama: cada ≤ `SOPORTE_PASO`, a 40 mm de las puntas de cada tramo
    de cama. Con el criterio 6 el primero y el último se corren lo necesario para que la tuerca
    de su perno pasante (por la cara exterior del larguero) quede fuera del marco del tensor o de
    la placa porta-chumacera, con sitio para la llave (`LLAVE_M8`)."""
    tramos = tramos_cama(c)
    libre_c, libre_m = (_libres(c) if c.criterio >= 6 else (-math.inf, math.inf))
    out: list[float] = []
    for j, (x0, x1) in enumerate(tramos):
        lo = max(40.0, libre_c - x0) if j == 0 else 40.0
        hi = max(40.0, x1 - libre_m) if j == len(tramos) - 1 else 40.0
        n = max(2, math.ceil((x1 - x0) / SOPORTE_PASO) + 1)
        paso = (x1 - x0 - (lo + hi)) / (n - 1)
        out += [x0 + lo + (k - 1) * paso for k in range(1, n + 1)]
    return out


def _libres(c: Cotas) -> tuple[float, float]:
    """(desde, hasta) la X donde la cara exterior del larguero queda libre de los soportes de
    los ejes (marco del tensor UCT o placa porta-chumacera), más el radio de la llave."""

    def ancho_placa(ref):
        return float(CATALOG[ref].params["size_w"]) + 30.0

    cola = (float(CATALOG[c.uct].params["L"]) / 2.0 if c.uct else ancho_placa(c.chum_c) / 2.0)
    if c.uct and c.criterio >= 8:  # F1c (D11): la placa porta-tensor sale del marco
        from .belt_conveyor_tambores_taller import PLACA_TENSOR_MARGEN

        cola += PLACA_TENSOR_MARGEN
    return (-c.half + cola + LLAVE_M8, c.half - ancho_placa(c.chum_m) / 2.0 - LLAVE_M8)


def pernos_soporte(c: Cotas, x: float) -> list[tuple[float, float]]:
    """(x, z) de los dos pernos pasantes de la placa del soporte de cama en `x` (criterio 6):
    uno sobre otro si el alma del larguero da (el buje entero dentro del hueco del tubo y
    1,2·d0 de la placa al borde), si no lado a lado."""
    from .belt_conveyor_retorno import agujero_perno, limites_buje

    z0, z1 = z_soportes(c)
    lo, hi = limites_buje(c)
    borde = 1.2 * agujero_perno()
    lo, hi = max(lo, z0 + borde), min(hi, z1 - borde)
    zc = (z0 + z1) / 2.0
    if hi - lo >= LEG_W / 2.0:
        zc = min(max(zc, lo + LEG_W / 4.0), hi - LEG_W / 4.0)
        return [(x, zc - LEG_W / 4.0), (x, zc + LEG_W / 4.0)]
    if hi < lo:
        raise ValueError(f"el tubo {c.tubo} no deja pasar el perno pasante del soporte de cama "
                         "con su buje: usa un tubo de más canto")
    z = min(max(zc, lo), hi)
    return [(x - 15.0, z), (x + 15.0, z)]


def z_soportes(c: Cotas) -> tuple[float, float]:
    """(z0, z1) de los soportes de la cama y de sus placas de extremo (bajo la chapa)."""
    z1 = c.cama_top - c.cama_t
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
            plan.union(f"{suf}_sold", suf, rail(c, i, x0), "soldadura",
                       "placa soldada a la punta del tubo (cordón perimetral)", throat_mm=2,
                       length_mm=perimetro)


def cama(plan: Plan, c: Cotas) -> None:
    """Cama de deslizamiento (chapa; una por tramo, con 2 mm de junta en cada empalme)
    atornillada sobre soportes transversales cada ≤ 800 mm; cada soporte es un tubo con placas
    de extremo soldadas, atornilladas a los largueros. Con el criterio 6 (D4), perno PASANTE que
    cruza el larguero por un buje soldado y aprieta por fuera: el tubo es cerrado y la tuerca a
    su cara interior quedaba sin llave; un remache ciego (lo único ciego del catálogo) no se
    desarma, y el soporte se suelta para cambiar la banda."""
    from .belt_conveyor_retorno import nota_pasante, taladrar

    w = c.ancho / 2.0 + 10.0
    top = c.cama_top
    tramos = tramos_cama(c)
    taller = c.criterio >= 8
    sops = x_soportes(c)
    if taller:
        from . import belt_conveyor_cama as ct

        plan.calculos["cama"] = ct.cuenta_cama(c)
    for j, (x0, x1) in enumerate(tramos, start=1):
        cual = "paño" if taller else "tramo"
        nombre = "Cama de deslizamiento" + ("" if len(tramos) == 1 else f" ({cual} {j})")
        forma = caja(x0, x1, -w, w, top - c.cama_t, top)
        if taller:  # F1c (D12): el avellanado de cada tornillo, a ras de la cara de la banda
            forma = ct.avellanar(forma, c, [x for x in sops if x0 < x < x1])
        plan.pieza(cama_suf(c, j), nombre, forma, material="acero")
    largo = 2.0 * (c.y_in - PLACA_SOPORTE_T)
    tubo, cut = build_component(LEG_REF, largo)
    z0, z1 = z_soportes(c)
    pasante = c.criterio >= 6
    for k, x in enumerate(sops, start=1):
        sop = f"sop{k}"
        if taller:  # el tubo con el buje y el paso de los tornillos de la cama (D12)
            plan.pieza(sop, f"Soporte de cama ({k})", ct.soporte(tubo, c, x, z0, z1),
                       comp=LEG_REF, cut=cut, material=material_de(LEG_REF))
        else:
            plan.pieza(sop, f"Soporte de cama ({k})", tubo, comp=LEG_REF, cut=cut,
                       pos=(x, 0.0, (z0 + z1) / 2.0), rot=(90, 0, 0),
                       key=f"comp|{LEG_REF}|{cut}", material=material_de(LEG_REF))
        for lado, s, i in (("m", -1.0, 1), ("p", 1.0, 2)):
            placa = f"{sop}_{lado}"
            forma = caja(x - 30.0, x + 30.0, s * (c.y_in - PLACA_SOPORTE_T), s * c.y_in, z0, z1)
            if pasante:
                forma = taladrar(forma, c, s, pernos_soporte(c, x), PLACA_SOPORTE_T)
            plan.pieza(placa, f"Placa del soporte de cama ({k}, {'−' if s < 0 else '+'}Y)",
                       forma, material="acero")
            plan.union(f"{sop}_{lado}_sold", sop, placa, "soldadura",
                       "placa de extremo soldada al soporte", throat_mm=3,
                       length_mm=round(4 * LEG_W, 1))
            nota = (nota_pasante(c, "placa del soporte atornillada al larguero") if pasante
                    else "placa del soporte atornillada al alma del larguero")
            plan.union(f"{sop}_{lado}_larg", placa, rail(c, i, x), "perno", nota, size="M8",
                       qty=2)
        j = 1 + sum(1 for a, _b in tramos[1:] if x > a)
        plan.union(f"cama_{sop}", cama_suf(c, j), sop, "perno",
                   ct.nota(c) if taller else "cama atornillada al soporte (tornillos avellanados)",
                   size="M6", qty=2)
