"""Una cámara de cilindro y los caminos de aire que la alimentan o la vacían (plan V8.9 D3).

Cámara politrópica con la temperatura de PARED constante (sin ecuación de energía, D3):

    dp/dt = n / V · (R · T0 · q_m − p · dV/dt)

con n = 1,2 (`N_POLITROPICO`, hipótesis de modelo listada en el resultado), q_m el caudal másico
NETO que entra (ISO 6358-1, `orificio.py`) y V = V_muerto + V_tubos + A · carrera_útil. El volumen
de los tubos entre la válvula y el puerto se suma a la cámara (hipótesis: `HIPOTESIS_TUBOS`).

Un `Camino` es lo que une la cámara con una presión fija en este intercambio: la fuente (la
regulada del FRL, o la de la red sin FRL) por la vía de alimentación de la válvula, o la
atmósfera por la de escape; con la válvula en una posición que no la une, no hay camino. La
conductancia de cada sentido es la de los componentes en serie (`orificio.serie`). Una fuga
(`fuga`, cosim-fallas) es un camino más a la atmósfera.

Puro: sólo `cosim.neumatica`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .orificio import R_AIRE, T0_K, caudal_signado

#: Exponente politrópico de las cámaras (D3: 1,2 por defecto, «hipótesis de modelo»).
N_POLITROPICO = 1.2
HIPOTESIS_N = ("cámaras politrópicas con n = 1,2 y pared a temperatura constante (sin ecuación de "
               "energía: el consumo sale ~4 % bajo la isoterma del catálogo, F0)")
HIPOTESIS_TUBOS = ("el volumen de los tubos entre la válvula y el cilindro se suma a su cámara; los "
                   "tubos no restringen el caudal (la vía más estrecha es la de cada componente)")
_RT0 = R_AIRE * T0_K


@dataclass
class Camino:
    """Una presión fija `p` (Pa absolutos) unida a la cámara. `ida` es la vía (C, b, m) de la
    fuente hacia la cámara y `vuelta` la de la cámara hacia la fuente. `toma` (si la fuente es la
    toma de la máquina) es lo que lleva la cuenta del aire consumido (el FRL o la toma sin él)."""
    p: float
    ida: tuple
    vuelta: tuple
    toma: object = None


def caudal_entrante(caminos, p: float) -> tuple[float, list]:
    """(q_m neto que entra a la cámara a la presión p, [q_m de cada camino]) en kg/s."""
    qs = [caudal_signado(c.ida, c.vuelta, c.p, p) for c in caminos]
    return sum(qs), qs


def dpdt(p: float, V: float, q_m: float, dVdt: float, n: float = N_POLITROPICO) -> float:
    """dp/dt (Pa/s) de una cámara de volumen V (m³) que cambia a dV/dt (m³/s)."""
    return n / V * (_RT0 * q_m - p * dVdt)
