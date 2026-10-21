"""Fasores de una fuente de alterna y el desbalance de un juego trifásico (plan V8.3 D15).

La convención es la de `cosim/modelos/alimentacion.Red` y de `library/electrico/tension`: módulo
de FASE = U_línea/√3 con L1 a 0°, L2 a −120° y L3 a +120° (secuencia directa); en 1F+N, L a U y
N en 0. `sentido = −1` invierte la secuencia (la marcha atrás del variador). Los fasores son
valores EFICACES referidos al centro de estrella de su fuente (la tierra de la red de potencia).
"""

from __future__ import annotations

import cmath
import math

_ANG = {"L1": 0.0, "L2": -120.0, "L3": 120.0}
#: a = e^(j120°), el operador de las componentes simétricas.
A = cmath.rect(1.0, math.radians(120.0))


def fasores_nominales(sistema: str, U_V: float, sentido: int = 1) -> dict[str, complex]:
    """{polo: fasor} de una fuente `sistema` de tensión `U_V` (de línea; fase–neutro en 1F+N)."""
    if sistema == "1F+N":
        return {"L": complex(U_V, 0.0), "N": 0j}
    uf = U_V / math.sqrt(3)
    polos = {"2F": ("L1", "L2"), "3F": ("L1", "L2", "L3"), "3F+N": ("L1", "L2", "L3")}[sistema]
    out = {p: cmath.rect(uf, math.radians(_ANG[p] * (1 if sentido >= 0 or p == "L1" else -1)))
           for p in polos}
    if sistema == "3F+N":
        out["N"] = 0j
    return out


def secuencias(vab: complex, vbc: complex, vca: complex) -> tuple[complex, complex]:
    """Componentes directa e inversa (V1, V2) de un juego de tensiones de LÍNEA."""
    v1 = (vab + A * vbc + A * A * vca) / 3.0
    v2 = (vab + A * A * vbc + A * vca) / 3.0
    return v1, v2


def desbalance_pct(vab: complex, vbc: complex, vca: complex) -> float:
    """Desbalance de tensión |V2|/|V1| en % (la definición por componentes simétricas de
    IEC 60034-26 para motores y de IEC 61000-4-30 para la calidad de la red)."""
    v1, v2 = secuencias(vab, vbc, vca)
    return 100.0 * abs(v2) / abs(v1) if abs(v1) > 1e-12 else math.inf
