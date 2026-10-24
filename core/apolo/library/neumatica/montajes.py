"""Cotas de los accesorios de montaje de ISO 15552 (plan V8.9 D5, F2): la brida delantera o
trasera y los pies, por Ø de pistón. PURO: sólo datos y la biblioteca estándar.

Fuente: Flowtech, hoja «ISO15552 Cylinder Mountings» (TS3017, tablas FA y LB), transcrita tal
cual para Ø32–63. Las letras son las de la hoja; lo que significa cada una sale de su dibujo:

- Brida FA (MF1 delantera / MF2 trasera, la MISMA pieza): placa `BE` (ancho) × `BC` (alto) ×
  `BB` (espesor) con un agujero central Ø`BA` (centra el cuello de la tapa y deja pasar el
  vástago) y 4 agujeros Ø`BP` para la máquina en un rectángulo `BF` (a lo ancho) × `BD` (a lo
  alto). La brida se atornilla a la tapa por los 4 agujeros del cuadro TG del cilindro.
- Pie LB (MS1, uno por tapa): escuadra de chapa `AT`; el eje del cilindro queda a `AH` de la
  base; ancho `AE`; 2 agujeros Ø`AP` a `AF` entre sí, a `AG` de la cara de la tapa; `AD` = del
  agujero al borde exterior (`AA` = `AC` + 2·`AD`, `AC` = largo del cuerpo + 2·`AG`).

El perno de la máquina sale del agujero por ISO 273 (`perno_por_agujero`): Ø7 → M6 (serie
basta), Ø9 → M8 (serie media). Lo que la hoja NO da (el cuello de la tapa, la rosca de los 4
tornillos de la tapa) va en la ficha de cada ref con su `a_confirmar`.
"""

from __future__ import annotations

from dataclasses import dataclass

FUENTE = "Flowtech TS3017 «ISO15552 Cylinder Mountings», tablas FA (brida) y LB (pie)"


@dataclass(frozen=True)
class Brida:
    BA: float  # Ø del agujero central
    BB: float  # espesor
    BC: float  # alto
    BD: float  # entre agujeros, a lo alto
    BE: float  # ancho
    BF: float  # entre agujeros, a lo ancho
    BP: float  # Ø de los agujeros de la máquina


@dataclass(frozen=True)
class Pie:
    AD: float  # del agujero al borde exterior
    AE: float  # ancho
    AF: float  # entre los dos agujeros
    AG: float  # de la cara de la tapa al agujero
    AH: float  # altura del eje sobre la base
    AP: float  # Ø de los agujeros
    AT: float  # espesor de la chapa


#: Tabla FA de TS3017 (Ø32, 40, 50, 63)
BRIDAS: dict[int, Brida] = {
    32: Brida(BA=30.5, BB=10, BC=50, BD=32, BE=80, BF=64, BP=7),
    40: Brida(BA=35.5, BB=10, BC=55, BD=36, BE=90, BF=72, BP=9),
    50: Brida(BA=40.5, BB=12, BC=68, BD=45, BE=108, BF=90, BP=9),
    63: Brida(BA=45.5, BB=12, BC=78, BD=50, BE=120, BF=100, BP=9),
}

#: Tabla LB de TS3017 (Ø32, 40, 50, 63)
PIES: dict[int, Pie] = {
    32: Pie(AD=8, AE=47, AF=32, AG=24, AH=32, AP=7, AT=3),
    40: Pie(AD=9, AE=53, AF=36, AG=28, AH=36, AP=9, AT=3),
    50: Pie(AD=10, AE=65, AF=45, AG=32, AH=45, AP=9, AT=3),
    63: Pie(AD=12, AE=75, AF=50, AG=32, AH=50, AP=9, AT=3),
}

#: ISO 273 (agujero de paso): serie fina / media / basta por métrica
_ISO273 = {"M5": (5.3, 5.5, 5.8), "M6": (6.4, 6.6, 7.0), "M8": (8.4, 9.0, 10.0),
           "M10": (10.5, 11.0, 12.0), "M12": (13.0, 13.5, 14.5)}


def perno_por_agujero(d_agujero: float) -> str:
    """La métrica del perno que pasa por un agujero de paso de ISO 273 (cualquier serie)."""
    for metrica, serie in _ISO273.items():
        if any(abs(d_agujero - s) < 0.05 for s in serie):
            return metrica
    raise ValueError(f"Ø{d_agujero:g} no es un agujero de paso de ISO 273 (M5–M12)")


def brida(D: int) -> Brida:
    if D not in BRIDAS:
        raise ValueError(f"no hay brida ISO 15552 para Ø{D} en la tabla ({sorted(BRIDAS)})")
    return BRIDAS[D]


def pie(D: int) -> Pie:
    if D not in PIES:
        raise ValueError(f"no hay pie ISO 15552 para Ø{D} en la tabla ({sorted(PIES)})")
    return PIES[D]
