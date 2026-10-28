"""Pies niveladores PUROS del transportador de rodillos por cadena (plan
`docs/plans/plantilla-rodillos-cadena.md`, F5 — D10). Sin `Document` ni OCCT.

Cada pata lleva un pie nivelador de catálogo (`97_pies_niveladores.yaml`, el mismo que usa
`belt_conveyor.py`): la placa de la pata lleva SOLDADA por debajo la tuerca de la rosca del pie
y el disco apoya en el piso o, con `anclaje`, en una placa de piso aparte con los 2 anclajes de
siempre (el bastidor se nivela, la placa se ancla y el disco se suelda a ella).

Pila desde el piso con el pie a la MITAD de su recorrido (D10): placa de piso (si `anclaje`) →
disco → vástago libre → tuerca soldada → placa de la pata → pata. La pata se acorta lo que mide
la pila, así que el techo de los rodillos sigue en `altura`. El vástago pasa la placa de la pata
por un barreno de paso y sube por dentro del tubo de la pata (hueco).

Recorrido: en la punta alta el vástago tiene que engranar la tuerca entera; en la baja, el disco
toca la tuerca → recorrido = largo del vástago − altura de la tuerca, y se publica como ± la
mitad.

Familia: la menor cuyo `carga_kg` cubre (masa de la máquina + carga) / patas × `IMPACTO`. La
masa sale de `masa_estimada` (catálogo + chapa de las cotas, × `MARGEN_MASA`). Si ninguna la
cubre, la mayor: lo marca el `engineering_check` (`rodillos_cadena_reglas`) y el log sigue
regenerando, como el FS < 1 de la cadena en F4.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .catalog import CATALOG
from .engineering.bolts import clearance_hole_mm

CATEGORIA = "pies_niveladores"
IMPACTO = 1.5              # reparto igual entre patas × 1.5: criterio de diseño (arranques, golpes)
MARGEN_MASA = 1.10         # soldadura, tornillería y pintura que el modelo no pesa
PLACA_PISO = 150.0
PLACA_PISO_T = 10.0
ANCLAJE_D = 14.0           # perno de expansión M12 al piso
ANCLAJE_XY = 50.0          # los 2 anclajes en diagonal, a ±50 mm del centro
RHO = 7.85e-6              # kg/mm³, acero
# F6 (`taller`, revisor ciego de la piloto «rodillos por gravedad»): con los anclajes en ±50 la
# placa de la pata (150 × 150) los TAPA a 26 mm: no entra el taladro para perforar el concreto
# por la placa ni el dado de la tuerca. La placa de piso se alarga en X y los anclajes van FUERA
# de la huella de la placa de la pata, a `ACCESO_ANCLAJE` de su borde: el dado de la tuerca AF 19
# pide 1.5 × 19 / 2 + 5 = 19.3 mm de radio y el porta-brocas SDS-plus del rotomartillo (Ø ≈ 50),
# 25 + 5 de margen → 30 mm (criterio de taller). El canto de la placa, a `BORDE_ANCLAJE` del
# taladro (≥ 1.5 · Ø14 = 21, EN 1993-1-8 tabla 3.3).
ANCLAJE_REF = "ANCLA-EXP-M12"
ACCESO_ANCLAJE = 30.0
BORDE_ANCLAJE = 25.0


def familias() -> list[str]:
    """Los pies del catálogo, de menor a mayor carga."""
    refs = [r for r, c in CATALOG.items() if c.category == CATEGORIA]
    return sorted(refs, key=lambda r: float(CATALOG[r].specs["carga_kg"]))


@dataclass(frozen=True)
class Pies:
    ref: str
    tuerca: str            # la soldada bajo la placa de la pata (rosca del pie)
    rosca: float
    vastago: float         # largo del vástago (`altura` del catálogo)
    disco_d: float
    disco_t: float
    tuerca_t: float
    tuerca_ac: float       # entrecaras
    barreno: float         # paso del vástago por la placa de la pata (ISO 273 media)
    recorrido: float       # total: se nivela ± recorrido/2
    anclaje: bool
    z_disco: float         # cara inferior del disco (0, o sobre la placa de piso)
    z_pie: float           # origen del pie = centro del vástago (`position` del componente)
    z_tuerca: float        # centro de la tuerca
    z_placa: float         # cara inferior de la placa de la pata
    z_pata0: float         # cara superior de la placa = arranque del tubo de la pata
    n: int = 0             # patas
    masa_kg: float = 0.0   # máquina, estimada con margen (`masa_estimada`)
    carga_kg: float = 0.0  # carga con que se eligió (la de la plantilla)
    por_pie_kg: float = 0.0
    capacidad_kg: float = 0.0
    taller: bool = False   # F6: contratuerca del vástago y anclajes fuera de la placa de la pata
    z_contratuerca: float = 0.0  # centro de la contratuerca (sólo con `taller`)

    @property
    def placa_piso(self) -> tuple[float, float]:
        """(X, Y) de la placa de piso: con `taller`, larga en X para los anclajes de afuera."""
        from .rodillos_cadena import PLACA_PATA

        if not self.taller:
            return PLACA_PISO, PLACA_PISO
        return 2.0 * (PLACA_PATA / 2.0 + ACCESO_ANCLAJE + BORDE_ANCLAJE), PLACA_PISO

    @property
    def anclajes(self) -> tuple[tuple[float, float], ...]:
        """(dx, dy) de cada anclaje desde el eje de la pata: en diagonal (v3) o, con `taller`,
        sobre X a `ACCESO_ANCLAJE` por fuera del borde de la placa de la pata."""
        from .rodillos_cadena import PLACA_PATA

        if not self.taller:
            return ((ANCLAJE_XY, ANCLAJE_XY), (-ANCLAJE_XY, -ANCLAJE_XY))
        dx = PLACA_PATA / 2.0 + ACCESO_ANCLAJE
        return ((dx, 0.0), (-dx, 0.0))


def pila(ref: str, anclaje: bool, taller: bool = False) -> Pies:
    """Las cotas de la pila de una pata con el pie `ref` a la mitad de su recorrido. Con
    `taller` (F6) la contratuerca va en el vástago bajo la tuerca soldada: traba la altura y
    ocupa rosca, así que el recorrido es vástago − 2 tuercas."""
    from .rodillos_cadena_motriz import PLACA_PATA_T

    s = CATALOG[ref].specs
    rosca, vastago = float(s["rosca"]), float(s["altura"])
    tuerca = f"TUERCA-M{rosca:g}"
    st = CATALOG[tuerca].specs
    m = float(st["thickness"])
    recorrido = vastago - (2.0 if taller else 1.0) * m
    z_disco = PLACA_PISO_T if anclaje else 0.0
    z_vastago = z_disco + float(s["disco_t"])  # arranque del vástago (cara superior del disco)
    z_contra = z_vastago + recorrido / 2.0     # cara inferior de la contratuerca (con `taller`)
    z_tuerca0 = z_contra + (m if taller else 0.0)
    z_placa = z_tuerca0 + m
    return Pies(
        ref=ref, tuerca=tuerca, rosca=rosca, vastago=vastago, disco_d=float(s["disco_d"]),
        disco_t=float(s["disco_t"]), tuerca_t=m, tuerca_ac=float(st["across_flats"]),
        barreno=clearance_hole_mm(f"M{rosca:g}"), recorrido=recorrido, anclaje=anclaje,
        z_disco=z_disco, z_pie=z_vastago + vastago / 2.0, z_tuerca=z_tuerca0 + m / 2.0,
        z_placa=z_placa, z_pata0=z_placa + PLACA_PATA_T, taller=taller,
        z_contratuerca=z_contra + m / 2.0 if taller else 0.0,
    )


def _area(puntos) -> float:
    return abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                   in zip(puntos, list(puntos[1:]) + list(puntos[:1])))) / 2.0


def _kg(ref: str, largo_mm: float | None = None) -> float:
    c = CATALOG[ref]
    return c.weight * largo_mm / 1000.0 if (c.cuttable and largo_mm is not None) else c.weight


def _guardas_kg(d) -> float:
    """Chapa de las guardas (las cotas de D4/D5 son polígonos: área × espesor)."""
    from . import rodillos_cadena as rc
    from .rodillos_cadena_guardas import GUARDA_T

    g, b, total = d.guardas, d.bandeja, 0.0
    for caja in (g["carter"], g["fija"]):
        for pared in (caja["pared_int"], caja["pared_ext"], *caja["extremos"]):
            total += _area(pared["puntos"]) * abs(pared["y1"] - pared["y0"])
    for tapa in (g["fija"]["tapa"], b["tapa"]):
        total += _area(tapa["puntos"]) * (tapa["x1"] - tapa["x0"])
    ancho = b["y1"] - b["y0"]
    for xa, xb in b["tramos"]:
        total += GUARDA_T * (xb - xa) * (ancho + b["alto_ext"] + (b["alto_int"] or 0.0))
    # guarda de cadenas (chapa + pestaña), separadores y faldón
    fondo = d.y_in_p + rc.SEPARADOR_FONDO - (d.ancho_util / 2.0 - 3.0)
    total += GUARDA_T * d.largo * (fondo + rc.GUARDA_PESTANA)
    total += len(d.separadores) * rc.SEPARADOR_X * rc.SEPARADOR_FONDO * (d.guarda_z - GUARDA_T - d.sep_z0)
    total += GUARDA_T * d.largo * (d.guarda_z - d.sep_z0 + 5.0)
    return total * RHO


def masa_estimada(d, pie: Pies) -> float:
    """kg de la máquina de la `Disposicion` `d` con la pila `pie`, × `MARGEN_MASA`: catálogo
    (peso por ficha o kg/m) y, lo que es a medida, volumen de sus cotas × acero."""
    from . import rodillos_cadena as rc
    from .rodillos_cadena_motriz import BASE_MOTOR_T, OREJA_T, PLACA_PATA_T

    re_, ri = rc.EJE_D / 2.0, d.r_int_tubo
    rodillo = (_kg(d.rodillo, d.ancho_util) + RHO * math.pi * re_**2 * (d.eje_y1 - d.eje_y0)
               + 2.0 * RHO * math.pi * (ri**2 - re_**2) * rc.TAPA_ESPESOR + 2.0 * _kg(rc.TUERCA))
    if d.motriz is not None:  # piñón y buje (brida + cuello)
        rb, rc_, rib = d.d_rodillo / 2.0, rc.CUELLO_BUJE_R, rc.EJE_D / 2.0 + 0.5
        largo = d.y_buje - d.ancho_util / 2.0
        rodillo += _kg(rc.PINON_RODILLO) + RHO * math.pi * (
            (rb**2 - rib**2) * rc.BRIDA_BUJE + (rc_**2 - rib**2) * (largo - rc.BRIDA_BUJE))
    if pie.taller:  # F6: 2 × 6201, tuercas interiores y separadores (las tapas ahuecadas, aparte)
        rs = rc.SEPARADOR_EJE_D / 2.0
        sep = (d.y_in_p - d.y_in_m) - d.ancho_util - 4.0 * float(CATALOG[rc.TUERCA].specs["thickness"])
        rodillo += (2.0 * _kg(rc.RODAMIENTO) + 2.0 * _kg(rc.TUERCA)
                    + RHO * math.pi * (rs**2 - re_**2) * max(sep, 0.0))
    total = len(d.xs) * rodillo + 2.0 * _kg(rc.LARGUERO, d.largo)
    ala = float(CATALOG[rc.LARGUERO].specs["leg"])
    pata = d.z_larguero - ala / 2.0 - pie.z_pata0
    px, py = pie.placa_piso
    por_pata = (_kg(rc.PATA, pata) + RHO * rc.PLACA_PATA**2 * PLACA_PATA_T + _kg(pie.ref)
                + _kg(pie.tuerca) + (RHO * px * py * PLACA_PISO_T if pie.anclaje else 0.0))
    if pie.taller:  # la contratuerca y, con anclaje, los 2 anclajes de expansión
        por_pata += _kg(pie.tuerca) + (len(pie.anclajes) * _kg(ANCLAJE_REF) if pie.anclaje else 0.0)
    ne = len(d.estaciones)
    total += 2 * ne * por_pata + ne * _kg(rc.PATA, d.travesano_largo)
    m = d.motriz
    if m is not None:
        paso = float(CATALOG[rc.CADENA].specs["paso"])
        total += _kg(rc.CADENA, ((len(d.xs) - 1) * d.eslabones_rr + m.eslabones) * paso)
        base = d.guardas["carter"]["base"]
        total += (_kg(m.motor) + _kg(m.pinon)
                  + RHO * (base["x1"] - base["x0"]) * (base["y1"] - base["y0"]) * BASE_MOTOR_T
                  + 2.0 * RHO * _area(m.oreja["puntos"]) * OREJA_T + _guardas_kg(d))
    return total * MARGEN_MASA


def elegir(d, anclaje: bool, taller: bool = False) -> Pies:
    """El pie de cada pata: el menor que lleva (masa + `d.carga_kg`) / patas × `IMPACTO`; si
    ninguno, el mayor (el `engineering_check` lo da en error)."""
    n = 2 * len(d.estaciones)
    out = None
    for ref in familias():
        p = pila(ref, anclaje, taller)
        masa = masa_estimada(d, p)
        por_pie = (masa + d.carga_kg) / n * IMPACTO
        cap = float(CATALOG[ref].specs["carga_kg"])
        out = Pies(**{**p.__dict__, "n": n, "masa_kg": masa, "carga_kg": d.carga_kg,
                      "por_pie_kg": por_pie, "capacidad_kg": cap})
        if por_pie <= cap:
            break
    return out
