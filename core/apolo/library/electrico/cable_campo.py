"""Recorrido y largo de un cable de CAMPO (plan V8.5 F4): del prensaestopas del tablero, por los
pasos de `add_cable.por`, hasta el aparato del otro extremo.

PURO (sin OCCT, catálogo ni `Document`): recibe los extremos ya resueltos y los pasos como puntos
o cajas del mundo; `services/cables_campo.py` los arma desde el documento al LEER (como el ruteo
de F2: no se cachea en la geometría, D12) y mide los choques con lo que gira.

**Tramos del recorrido**, en orden de `desde` a `hasta` (cada cifra en `CriterioCampo`, «criterio
de diseño», sale en el resultado):
1. Un extremo en un TABLERO armado arranca en la cara interior del pasacables, donde el ruteo de F2
   deja los hilos (`ruteo.prensaestopas`), atraviesa la pared y sale RECTO por la normal de la
   cara `salida_recta_mm` (el prensaestopas y el tramo antes de doblar).
2. Un PUNTO de paso se toma tal cual.
3. Una PIEZA de paso (la estructura a la que va sujeto): entra por el punto de su caja más
   cercano al punto anterior y sale por el más cercano al siguiente (el siguiente punto, o el
   centro de la caja que sigue). Un cable que corre a lo largo de un larguero lo recorre.
4. Un extremo en un APARATO con pieza llega al punto de su caja más cercano al anterior, más la
   reserva de conexión (`reserva_campo_mm`: entrar por su prensaestopas a la caja de bornes,
   pelar y rehacer).
5. El largo del cable = lo de DENTRO de cada tablero (el hilo más largo del ruteo, que ya trae su
   reserva en el borne) + el recorrido de afuera + la reserva de cada aparato de campo.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

Punto3 = tuple[float, float, float]
Caja3 = tuple[Punto3, Punto3]  # (mín, máx)
EPS = 1e-6


@dataclass(frozen=True)
class CriterioCampo:
    """Las cifras del recorrido de campo (todas «criterio de diseño»)."""
    salida_recta_mm: float = 50.0    # recto desde la cara del pasacables antes de doblar
    reserva_campo_mm: float = 300.0  # en el aparato de campo: prensaestopas → bornes, pelado, rehacer
    holgura_giro_mm: float = 10.0    # lo mínimo entre el cable y lo que gira (vibra, se comba)

    def supuestos(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Fijo:
    """Puntos que el recorrido toma tal cual: un punto de paso o la salida de un tablero."""
    puntos: tuple[Punto3, ...]
    nombre: str = ""


@dataclass(frozen=True)
class Caja:
    """Una pieza del recorrido (paso o aparato del extremo): su caja en el mundo."""
    caja: Caja3
    nombre: str = ""

    @property
    def centro(self) -> Punto3:
        lo, hi = self.caja
        return tuple((lo[i] + hi[i]) / 2 for i in range(3))


def acercar(caja: Caja3, p: Punto3) -> Punto3:
    """El punto de la caja más cercano a `p` (el mismo si está dentro)."""
    lo, hi = caja
    return tuple(min(max(p[i], lo[i]), hi[i]) for i in range(3))


def salida_tablero(interior: Punto3, normal: Punto3, pared_mm: float, crit: CriterioCampo) -> Fijo:
    """La salida de un tablero (regla 1): la cara interior del pasacables, la exterior y el tramo
    recto, todo sobre la `normal` (unitaria, hacia afuera) de la cara."""
    fuera = tuple(interior[i] + normal[i] * pared_mm for i in range(3))
    recto = tuple(fuera[i] + normal[i] * crit.salida_recta_mm for i in range(3))
    return Fijo((interior, fuera, recto), "salida del tablero")


def _objetivo(item) -> Punto3:
    return item.puntos[0] if isinstance(item, Fijo) else item.centro


def recorrido(items: list) -> tuple[Punto3, ...]:
    """La polilínea de `items` (`Fijo` o `Caja`, en orden) por las reglas 2–4."""
    pts: list[Punto3] = []

    def poner(p: Punto3) -> None:
        if not pts or math.dist(pts[-1], p) > EPS:
            pts.append(tuple(float(x) for x in p))

    for i, it in enumerate(items):
        if isinstance(it, Fijo):
            for p in it.puntos:
                poner(p)
            continue
        siguiente = _objetivo(items[i + 1]) if i + 1 < len(items) else None
        previo = pts[-1] if pts else siguiente
        if previo is None:  # una caja sola: su centro (no hay recorrido)
            poner(it.centro)
            continue
        poner(acercar(it.caja, previo))
        poner(acercar(it.caja, siguiente if siguiente is not None else previo))
    return tuple(pts)


def largo(polilinea: tuple[Punto3, ...]) -> float:
    return sum(math.dist(a, b) for a, b in zip(polilinea, polilinea[1:]))


@dataclass(frozen=True)
class Tramo:
    """Un tramo recto de la polilínea (índice desde 1, como lo lee el agente)."""
    n: int
    a: Punto3
    b: Punto3


def tramos(polilinea: tuple[Punto3, ...]) -> tuple[Tramo, ...]:
    return tuple(Tramo(i + 1, a, b) for i, (a, b) in enumerate(zip(polilinea, polilinea[1:])))
