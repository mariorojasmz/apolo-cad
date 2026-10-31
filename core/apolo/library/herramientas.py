"""Tabla de HERRAMIENTAS de apriete por entrecaras (plan acceso-de-herramienta, D1).

El chequeo de acceso (`acceso_herramienta.py`) arma un sólido FANTASMA por herramienta
alrededor de cada tuerca o cabeza; sus medidas salen de AQUÍ, no de constantes sueltas.

Fuente: envolventes de referencia de catálogo comercial, redondeadas HACIA ARRIBA y del orden
de los máximos que fijan ISO 2725-1 / DIN 3124 (copas de 1/2″; 3/8″ bajo s = 13), DIN 3113
(llaves combinadas: anillo y boca) e ISO 2936 (llaves Allen en L). Son REFERENCIALES: una
herramienta concreta puede ser más delgada; el chequeo pide la herramienta corriente del
taller, no la de pared mínima. Columnas (mm):

- `copa_d`: Ø exterior de la copa (vaso) — la pared es (copa_d − s)/2.
- `anillo_d`: Ø exterior de la cabeza de anillo de la combinada (≈ 1.5·s, D1).
- `boca_b`: ancho exterior de la cabeza de boca (llave abierta).
- `espesor`: grosor de la cabeza (anillo y boca) a lo largo del eje del perno.

La llave Allen y el destornillador (Torx, Pozidriv, Phillips, ranura) van con su fuente junto a
su tabla (plan puerta-fuera-de-catalogo D4): ISO 2936 (brazo corto l2), ISO 8764-2 (hoja PH/PZ);
lo que no tiene norma (Torx, la mano) va como criterio de diseño, escrito como tal.
"""

from __future__ import annotations

from dataclasses import dataclass

# Largo libre que la copa necesita MÁS ALLÁ de la tuerca (D1: «altura + 15 mm hacia afuera»).
LARGO_LIBRE_COPA_MM = 15.0
# Giro mínimo de una llave de boca o del mango del anillo: ±15° (con volteo, la cabeza a 15°
# cubre la tuerca cada 30°). La herramienta debe poder BARRER ese ángulo, no sólo calzar.
GIRO_MIN_GRADOS = 15.0

# s → (copa_d, anillo_d, boca_b, espesor)
_LLAVES: dict[float, tuple[float, float, float, float]] = {
    5.5: (9.0, 9.5, 15.0, 4.0),
    7.0: (11.0, 12.0, 18.0, 5.0),
    8.0: (12.5, 13.5, 20.0, 5.5),
    10.0: (15.5, 16.5, 24.0, 6.5),
    13.0: (19.0, 20.5, 31.0, 7.5),
    16.0: (22.5, 24.5, 37.0, 8.5),
    17.0: (24.0, 26.0, 39.0, 9.0),
    18.0: (25.0, 27.5, 41.0, 9.5),
    19.0: (26.0, 29.0, 43.0, 10.0),
    21.0: (29.0, 32.0, 47.0, 11.0),
    24.0: (33.0, 36.0, 53.0, 12.0),
    27.0: (37.0, 40.5, 59.0, 13.0),
    30.0: (41.0, 45.0, 65.0, 14.0),
    36.0: (49.0, 54.0, 77.0, 16.0),
    41.0: (55.0, 61.0, 87.0, 18.0),
    46.0: (62.0, 69.0, 97.0, 20.0),
}

# llave Allen (entrecaras) → largo del brazo CORTO de la L (el que entra al hueco): l2 de ISO
# 2936:2014 Tabla 1 (plan puerta-fuera-de-catalogo D4; antes, una envolvente de catálogo menor)
_ALLEN: dict[float, float] = {
    2.0: 18.0, 2.5: 20.5, 3.0: 23.0, 4.0: 29.0, 5.0: 33.0, 6.0: 38.0, 8.0: 44.0,
    10.0: 50.0, 12.0: 57.0, 14.0: 70.0, 17.0: 80.0, 19.0: 89.0, 22.0: 102.0,
}
# llave Allen del tornillo de cabeza cilíndrica ISO 4762 / DIN 912 por su Ø nominal (s de la
# norma): para la cabeza Allen que el nombre declara y la geometría no modela (el hueco)
ALLEN_ISO4762: dict[float, float] = {
    3.0: 2.5, 4.0: 3.0, 5.0: 4.0, 6.0: 5.0, 8.0: 6.0, 10.0: 8.0, 12.0: 10.0, 14.0: 12.0,
    16.0: 14.0, 20.0: 17.0, 24.0: 19.0,
}

# DESTORNILLADOR (Torx, Pozidriv, Phillips, ranura): hoja + mango y mano EN LÍNEA con el eje del
# tornillo (plan puerta-fuera-de-catalogo D4). Largo de la hoja PH/PZ: ISO 8764-2:2004 Tabla 1
# (serie A 25 mm, «de bolsillo»; serie B por número de punta). Torx no tiene largo normalizado
# (ISO 10664 sólo fija la impronta) y la mano tampoco: CRITERIO DE DISEÑO, el de la punta PH/PZ
# del mismo tamaño y un mango corriente Ø 28–38 mm con la mano alrededor.
MANO_D_MM = 40.0   # criterio de diseño: mango + mano que lo envuelve
MANO_L_MM = 100.0  # criterio de diseño: lo que ocupan el mango y el puño en línea con el eje
# n.º de punta → (Ø de la hoja: criterio de diseño, envolvente de catálogo; serie A; serie B)
_HOJA: dict[int, tuple[float, float | None, float]] = {
    0: (3.0, 25.0, 60.0), 1: (4.5, 25.0, 75.0), 2: (6.0, 25.0, 100.0), 3: (8.0, None, 150.0),
    4: (10.0, None, 200.0),
}
PUNTA_RANURA_MM = 10.0  # criterio de diseño: la hoja plana barre al girar un disco del Ø de la cabeza


@dataclass(frozen=True)
class Destornillador:
    """Envolvente coaxial de un destornillador: tramos (radio, z0, z1) desde la cabeza."""

    nombre: str
    tramos: tuple[tuple[float, float, float], ...]


def numero_de_punta(huella: str, d: float, tamano: int | None = None) -> int:
    """El n.º de punta PH/PZ (o su equivalente para Torx y ranura): el del nombre si lo dice
    («PZ2»; Torx: TX ≤ 15 → 1, ≤ 30 → 2, ≤ 45 → 3); si no, por el Ø del tornillo (ISO 4757 /
    fabricantes: Ø ≤ 3,5 → 1, ≤ 5 → 2, ≤ 8 → 3, más → 4)."""
    if tamano is not None:
        if huella == "TX":
            return 1 if tamano <= 15 else 2 if tamano <= 30 else 3 if tamano <= 45 else 4
        if huella in ("PZ", "PH") and tamano in _HOJA:
            return tamano
    return 1 if d <= 3.5 else 2 if d <= 5.0 else 3 if d <= 8.0 else 4


def destornilladores(huella: str, d: float, cabeza_d: float, tamano: int | None = None,
                     holgura: float = 1.0) -> list[Destornillador]:
    """Los destornilladores que pueden apretar la impronta (basta UNO libre): hoja larga (serie
    B) y de bolsillo (serie A), cada uno con su mano en línea. `holgura`: desde la cara de la
    cabeza (la de `acceso_herramienta.HOLGURA_ASIENTO_MM`)."""
    n = numero_de_punta(huella, d, tamano)
    hoja_d, serie_a, serie_b = _HOJA[n]
    out = []
    for serie, largo in (("B", serie_b), ("A", serie_a)):
        if largo is None:
            continue
        tramos = []
        z = holgura
        if huella == "ranura":  # la punta plana gira: barre el Ø de la cabeza
            tramos.append((cabeza_d / 2.0, z, z + PUNTA_RANURA_MM))
            z += PUNTA_RANURA_MM
        tramos.append((hoja_d / 2.0, z, holgura + largo))
        tramos.append((MANO_D_MM / 2.0, holgura + largo, holgura + largo + MANO_L_MM))
        out.append(Destornillador(f"destornillador {huella} n.º {n} (serie {serie}, hoja "
                                  f"{largo:g} mm)", tuple(tramos)))
    return out


@dataclass(frozen=True)
class Remachadora:
    """Envolvente de la remachadora manual de un remache ciego (plan union-en-perfil-hueco):
    la NARIZ apoya en la cabeza y, detrás, el cabezal con las mordazas. Criterio de diseño:
    remachadora de palanca corriente (nariz Ø 10–14 mm; cabezal Ø ≈ 30 mm), redondeado arriba.
    Se arma coaxial al remache, desde su cabeza hacia afuera (no gira: no barre)."""

    nariz_d: float = 16.0
    nariz_largo: float = 25.0
    cabezal_d: float = 32.0
    largo: float = 120.0


REMACHADORA = Remachadora()


@dataclass(frozen=True)
class Llave:
    """Envolventes de las herramientas para un entrecaras `s` (mm)."""

    s: float
    copa_d: float
    anillo_d: float
    boca_b: float
    espesor: float

    @property
    def pared_copa(self) -> float:
        return (self.copa_d - self.s) / 2.0


def _interp(tabla: dict, s: float):
    """Fila de `tabla` para `s`: exacta (±0.25 mm), interpolada entre vecinas o None fuera
    del rango tabulado (un fijador fuera de rango no se evalúa: no se extrapola)."""
    claves = sorted(tabla)
    for k in claves:
        if abs(k - s) <= 0.25:
            return tabla[k]
    if s < claves[0] or s > claves[-1]:
        return None
    hi = next(k for k in claves if k > s)
    lo = max(k for k in claves if k < s)
    f = (s - lo) / (hi - lo)
    a, b = tabla[lo], tabla[hi]
    if isinstance(a, tuple):
        return tuple(x + f * (y - x) for x, y in zip(a, b, strict=True))
    return a + f * (b - a)


def llave_para(s: float) -> Llave | None:
    """Herramientas para una tuerca o cabeza hexagonal de entrecaras `s`; None fuera de tabla."""
    fila = _interp(_LLAVES, float(s))
    if fila is None:
        return None
    return Llave(float(s), *fila)


def brazo_allen(s: float) -> float | None:
    """Largo del brazo corto de la llave Allen de entrecaras `s`; None fuera de tabla."""
    return _interp(_ALLEN, float(s))
