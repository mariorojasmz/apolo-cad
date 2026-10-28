"""Tramos del bastidor de `create_belt_conveyor` (v6, plan faja-larga-en-tramos D1).

Una faja larga no sale de una barra: el tubo comercial viene en 6 m y una máquina de 10 m tiene
que desarmarse para el transporte. Con `tramo_max` el bastidor se parte en
`N = ceil(largo_bastidor / tramo_max)` tramos IGUALES; cada tramo lleva sus dos largueros, su
cama con sus soportes y sus guardas laterales, y se une al siguiente por un EMPALME:

- en cada punta de larguero del empalme, una placa de empalme soldada (cordón perimetral: además
  cierra el tubo); las dos placas se atornillan entre sí con pernos que pasan POR FUERA del tubo
  (por el ala exterior y por debajo del larguero), así la llave entra desde los dos lados sin
  abrir nada;
- bajo cada empalme, una estación de patas soldada al tramo de la COLA, a `PATA_A_EMPALME` de la
  placa (la pata no cae sobre la placa ni tapa los pernos de abajo): el empalme queda apoyado y
  trabaja a corte, sin voladizo;
- las estaciones se calculan JUNTAS (`belt_conveyor_bastidor.estaciones`): las de los extremos y
  las de los empalmes primero, y las intermedias sólo donde un vano pasa `VANO_MAX`.

Sin `tramo_max` (los logs de antes de la v6) o con un tramo que cubre todo, el bastidor sale en
una pieza, con los mismos sufijos y la misma geometría de siempre (`rail1`, `cama`…).
"""

from __future__ import annotations

import math

from .belt_conveyor_cotas import LEG_W, Cotas
from .belt_conveyor_plan import Plan, caja

EMPALME_T = 10.0         # espesor de cada placa de empalme
EMPALME_ALA = 45.0       # lo que la placa sale del tubo, por fuera y por debajo (pernos fuera)
EMPALME_PERNO = "M12"
PATA_A_EMPALME = 50.0    # de la cara de la placa a la pata del empalme (cabeza del perno + llave)
MARGEN_EXTREMO = 400.0   # del empalme (con su pata) a las patas de los extremos
JUNTA_CAMA = 1.0         # medio hueco entre las chapas de la cama en un empalme
JUNTA_GUARDA = 0.5       # medio hueco entre las guardas laterales en un empalme


def partir(c: Cotas) -> tuple[tuple, tuple]:
    """(tramos, empalmes): el (x0, x1) del tubo de cada tramo de larguero y la X del centro de
    cada empalme. Los tubos son IGUALES: (largo − 2·placa·(N−1)) / N, siempre ≤ `tramo_max`.
    ValueError si un empalme no deja sitio a su estación de patas junto a las de los extremos."""
    largo = c.x1 - c.x0
    if not c.tramo_max:
        return ((c.x0, c.x1),), ()
    n = max(1, math.ceil(largo / c.tramo_max - 1e-9))
    if n == 1:
        return ((c.x0, c.x1),), ()
    tubo = (largo - 2.0 * EMPALME_T * (n - 1)) / n
    tramos = tuple((c.x0 + k * (tubo + 2.0 * EMPALME_T), c.x0 + k * (tubo + 2.0 * EMPALME_T) + tubo)
                   for k in range(n))
    empalmes = tuple(tramos[k][1] + EMPALME_T for k in range(n - 1))
    for s in empalmes:
        if pata_de_empalme(s) - LEG_W / 2.0 - MARGEN_EXTREMO < c.x_leg_t or \
                s + EMPALME_T + MARGEN_EXTREMO > c.x_leg_h:
            raise ValueError(
                f"tramo_max {c.tramo_max:g} mm: con {n} tramos de {tubo:.0f} mm un empalme queda a "
                f"menos de {MARGEN_EXTREMO:g} mm de las patas de un extremo (no cabe su estación "
                f"de patas); usa un tramo_max mayor o déjalo vacío")
    return tramos, empalmes


def pata_de_empalme(s: float) -> float:
    """X de la estación de patas de un empalme: bajo el tramo de la cola, junto a la placa."""
    return s - EMPALME_T - PATA_A_EMPALME - LEG_W / 2.0


def indice(c: Cotas, x: float) -> int:
    """El tramo (1..N) al que pertenece la X `x` (hasta el centro de cada empalme)."""
    return 1 + sum(1 for s in c.empalmes if x > s)


def rail(c: Cotas, i: int, x: float) -> str:
    """Sufijo del larguero `i` (1: −Y, 2: +Y) del tramo que contiene `x`."""
    return f"rail{i}" if c.n_tramos == 1 else f"rail{i}_{indice(c, x)}"


def nombre_larguero(c: Cotas, i: int, k: int) -> str:
    return f"Larguero ({i})" if c.n_tramos == 1 else f"Larguero ({i}, tramo {k})"


def cama(c: Cotas, k: int) -> str:
    """Sufijo de la chapa `k` de la cama (con el criterio 8, un paño; antes, un tramo)."""
    return "cama" if len(tramos_cama(c)) == 1 else f"cama_{k}"


def cortes(x0: float, x1: float, empalmes, junta: float) -> list[tuple[float, float]]:
    """[x0, x1] partido en cada empalme, con un hueco de 2·`junta` centrado en él."""
    puntos = [s for s in empalmes if x0 < s < x1]
    bordes = [x0] + [v for s in puntos for v in (s - junta, s + junta)] + [x1]
    return [(bordes[2 * k], bordes[2 * k + 1]) for k in range(len(bordes) // 2)]


def tramos_cama(c: Cotas) -> list[tuple[float, float]]:
    """Las chapas de la cama: una por tramo; con el criterio 8 (F1c, D13), en paños ≤ 3 m."""
    from .belt_conveyor_taller import con_taller, panos

    t = cortes(c.cama_x0, c.cama_x1, c.empalmes, JUNTA_CAMA)
    return panos(t, JUNTA_CAMA) if con_taller(c) else t


def tramos_guarda(c: Cotas) -> list[tuple[float, float]]:
    """Las guardas laterales: una por tramo; con el criterio 8 (F1c, D13), en paños ≤ 3 m."""
    from .belt_conveyor_taller import con_taller, panos

    t = cortes(c.x0, c.x1, c.empalmes, JUNTA_GUARDA)
    return panos(t, JUNTA_GUARDA) if con_taller(c) else t


def placas_de_empalme(plan: Plan, c: Cotas) -> None:
    """Dos placas por empalme y por lado: cada una soldada a la punta de su tubo (cordón
    perimetral) y atornillada a la otra con pernos que pasan por fuera del tubo."""
    from .fijacion import largo_perno

    perimetro = round(2.0 * (c.rail_t + c.rail_h), 1)
    largo = largo_perno(EMPALME_PERNO, 2.0 * EMPALME_T, estricto=True)
    for k, s in enumerate(c.empalmes, start=1):
        for i, lado in ((1, -1.0), (2, 1.0)):
            sufs = []
            for x0, x1, extremo, tramo in ((s - EMPALME_T, s, "cola", k), (s, s + EMPALME_T,
                                                                           "cabeza", k + 1)):
                suf = f"empalme{k}_{i}_{extremo}"
                forma = caja(x0, x1, lado * c.y_in, lado * (c.y_out + EMPALME_ALA),
                             c.rail_bot - EMPALME_ALA, c.rail_top)
                if c.criterio >= 8:  # F1c (D12): los agujeros de sus pernos, por fuera del tubo
                    forma = _taladrar_empalme(forma, c, lado, x0, x1)
                plan.pieza(suf, f"Placa de empalme del larguero ({i}, empalme {k}, {extremo})",
                           forma, material="acero")
                plan.union(f"{suf}_sold", suf, f"rail{i}_{tramo}", "soldadura",
                           "placa de empalme soldada a la punta del tubo (cordón perimetral)",
                           throat_mm=4, length_mm=perimetro)
                sufs.append(suf)
            plan.union(f"empalme{k}_{i}", sufs[0], sufs[1], "perno",
                       f"placas de empalme atornilladas: {EMPALME_PERNO}x{largo:g} DIN 933 + tuerca, "
                       "por fuera del tubo (ala exterior y bajo el larguero), llave desde los dos "
                       "lados", size=EMPALME_PERNO, qty=3)


def pernos_empalme(c: Cotas, lado: float) -> list[tuple[float, float]]:
    """(y, z) de los 3 pernos de un empalme (criterio 8): dos en el ala exterior y uno bajo el
    larguero, a media ala del tubo y del canto de la placa."""
    zc = c.rail_bot + c.rail_h / 2.0
    ya = lado * (c.y_out + EMPALME_ALA / 2.0)
    return [(ya, zc - c.rail_h / 4.0), (ya, zc + c.rail_h / 4.0),
            (lado * (c.y_in + c.rail_t / 2.0), c.rail_bot - EMPALME_ALA / 2.0)]


def _taladrar_empalme(forma, c: Cotas, lado: float, x0: float, x1: float):
    from build123d import Cylinder, Pos, Rotation

    from .belt_conveyor_taller import paso

    d0 = paso(EMPALME_PERNO)
    for y, z in pernos_empalme(c, lado):
        forma = forma - Pos((x0 + x1) / 2.0, y, z) * Rotation(0, 90, 0) * Cylinder(
            d0 / 2.0, abs(x1 - x0) + 2.0)
    return forma
