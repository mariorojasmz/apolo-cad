"""El caudal de un orificio neumático por ISO 6358-1:2013 (plan V8.9 D3), en SI.

    q_m = C · ρ0 · p1 · √(T0/T1) · φ,   φ = 1                                si p2/p1 ≤ b (sónico)
                                         φ = [1 − ((p2/p1 − b)/(1 − b))²]^m   si b < p2/p1 ≤ 1

con el aire de referencia ANR de ISO 8778:2003 (T0 = 293,15 K, p_ANR = 100 kPa, ρ0 = 1,185 kg/m³).
Es la MISMA fórmula de `library/neumatica/iso6358.py` (la del cálculo de la memoria), copiada
aquí porque `cosim` no importa `apolo.library` (su `__init__` carga OCP: `tests/test_capas_cosim.py`);
`tests/test_neumatica_cosim.py` ata las dos. La temperatura aguas arriba se toma T1 = T0 (pared
a temperatura constante, D3): √(T0/T1) = 1.

Componentes EN SERIE (válvula + regulador de caudal + silenciador, o FRL + corte + válvula): la
norma trae su método en ISO 6358-3; aquí se usa la APROXIMACIÓN 1/C² = Σ 1/Cᵢ² (la del prototipo
de la F0) con el `b` y el `m` de la vía más restrictiva (menor C), y quien la usa la DECLARA como
hipótesis (`HIPOTESIS_SERIE`): todas las fichas del catálogo traen hoy b = 0,3.

Puro: sólo `math`.
"""

from __future__ import annotations

import math

#: Aire de referencia ANR (ISO 8778:2003): 20 °C y 100 kPa.
T0_K = 293.15
P_ANR_PA = 1.0e5
RHO0 = 1.185
#: Aire como gas ideal (aire seco): R = 287,05 J/(kg·K).
R_AIRE = 287.05
#: Atmósfera estándar a nivel del mar (ISO 2533): la presión ambiente que se SUPONE (hipótesis
#: del resultado, `HIPOTESIS_ATM`).
P_ATM_PA = 101325.0
#: Índice subsónico cuando la ficha no lo trae (forma elíptica de ISO 6358:1989).
M_ELIPTICO = 0.5
#: b de una tobera IDEAL (k = 1,4): (2/(k+1))^(k/(k−1)) = 0,528 — el de una fuga sin ficha.
B_TOBERA = (2.0 / 2.4) ** (1.4 / 0.4)
#: C en dm³/(s·bar) → m³/(s·Pa).
_C_SI = 1e-3 / 1e5

HIPOTESIS_SERIE = ("componentes en serie por 1/C² = Σ 1/Cᵢ² con el b y el m de la vía más "
                   "restrictiva: aproximación del prototipo de la F0 (ISO 6358-3 trae el método de "
                   "la norma)")
HIPOTESIS_ATM = "presión ambiente 1,01325 bar (atmósfera estándar ISO 2533)"


def phi(r: float, b: float, m: float = M_ELIPTICO) -> float:
    """Factor de caudal de ISO 6358-1:2013 para r = p2/p1 (0 ≤ r ≤ 1)."""
    if r <= b:
        return 1.0
    if r >= 1.0:
        return 0.0
    x = (r - b) / (1.0 - b)
    return (1.0 - x * x) ** m


def caudal(via: tuple, p1: float, p2: float) -> float:
    """Caudal másico (kg/s) de p1 a p2 (Pa absolutos) por la vía (C, b, m); 0 si p1 ≤ p2."""
    if p1 <= p2:
        return 0.0
    C, b, m = via
    return C * _C_SI * RHO0 * p1 * phi(p2 / p1, b, m)


def caudal_signado(ida: tuple, vuelta: tuple, pa: float, pb: float) -> float:
    """Caudal másico de a hacia b (kg/s, negativo si va de b hacia a): `ida` es la vía de a→b y
    `vuelta` la de b→a (distintas en un regulador de caudal unidireccional)."""
    if pa >= pb:
        return caudal(ida, pa, pb)
    return -caudal(vuelta, pb, pa)


def serie(vias) -> tuple:
    """(C, b, m) equivalente de vías EN SERIE (ver la hipótesis del módulo)."""
    vias = list(vias)
    if len(vias) == 1:
        return tuple(vias[0])
    C = 1.0 / math.sqrt(sum(1.0 / (v[0] * v[0]) for v in vias))
    dominante = min(vias, key=lambda v: v[0])
    return (C, dominante[1], dominante[2])


def anr_l(masa_kg: float) -> float:
    """Masa de aire → litros normales ANR (ISO 8778)."""
    return masa_kg / RHO0 * 1000.0
