"""Banco del acople del aire (plan V8.9 F3, D3/D4): los casos de la F0 y sus dos integraciones.

  - `referencia_fina(caso)`: el MISMO modelo de cámaras (ISO 6358-1 + politrópica,
    `cosim/neumatica`) con un pistón RÍGIDO integrado aparte a paso fino (10 µs), Coulomb con
    adherencia y tope duro: la «referencia fina» de la F0;
  - `acoplado(caso)`: lo que hace la co-simulación (D4): una junta `slide` de MuJoCo con su tope,
    `frictionloss` y un `<motor>`, física a 1 ms e intercambio de 2 ms, las cámaras en 8 sub-pasos
    de 0,25 ms con la posición extrapolada (`Cilindro.intercambio`) y la fuerza media al motor.
Los dos devuelven el tiempo de carrera (el primer cruce de carrera − 1 mm, interpolado) y el aire
consumido del avance (NL ANR) hasta `t_fin`.

Los prototipos de la F0 quedaron en otra máquina: esto los rehace desde su bitácora (los casos y
la forma del acople). Ø80 no está en el catálogo: los casos son sintéticos.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from apolo.cosim.modelos.base import Parametros
from apolo.cosim.neumatica.camara import Camino, caudal_entrante, dpdt
from apolo.cosim.neumatica.cilindro import Cilindro
from apolo.cosim.neumatica.componentes import Toma
from apolo.cosim.neumatica.orificio import P_ATM_PA, anr_l

BAR = 1e5


@dataclass
class Caso:
    nombre: str
    D_mm: float
    d_mm: float
    carrera_mm: float
    masa_kg: float               # masa móvil (pistón + vástago + carga)
    C_alim: float                # C de la vía de alimentación (dm³/(s·bar))
    C_esc: float                 # C de la vía de escape
    V_muerto_cm3: float = 8.0
    p_bar: float = 6.0           # manométrica
    b: float = 0.3
    friccion_pct: float = 10.0
    t_fin: float = 1.5
    extra: dict = field(default_factory=dict)


#: Los casos de la F0 (Bitácora § 2), con los extremos que pide el plan (Riesgos).
CASOS = [
    Caso("Ø32 s300, C 0,8", 32, 12, 300, 1.0, 0.8, 0.8),
    Caso("Ø32 s300, escape 0,15", 32, 12, 300, 1.0, 0.8, 0.15, t_fin=2.5),
    Caso("Ø50 s200, C 1,2", 50, 20, 200, 2.0, 1.2, 1.2),
    Caso("Ø32, 2 cm³ muertos, 0,3 kg", 32, 12, 300, 0.3, 0.8, 0.8, V_muerto_cm3=2.0),
    Caso("Ø80/25 s500, C 3, 5 kg", 80, 25, 500, 5.0, 3.0, 3.0, t_fin=2.0),
]


def cilindro(c: Caso) -> Cilindro:
    p = Parametros("-MM1", "SINTETICO", {
        "tipo": "cilindro", "efecto": "doble", "D_mm": c.D_mm, "d_mm": c.d_mm, "carrera_mm": c.carrera_mm,
        "V_muerto_A_cm3": c.V_muerto_cm3, "V_muerto_B_cm3": c.V_muerto_cm3, "masa_movil_base_kg": c.masa_kg,
        "friccion_pct": c.friccion_pct})
    return Cilindro(p)


def caminos(c: Caso, toma) -> tuple[list, list]:
    """Avance: A a la fuente por la alimentación, B a la atmósfera por el escape."""
    p_src = c.p_bar * BAR + P_ATM_PA
    alim, esc = (c.C_alim, c.b, 0.5), (c.C_esc, c.b, 0.5)
    return [Camino(p_src, alim, alim, toma)], [Camino(P_ATM_PA, esc, esc)]


def _cruce(ts, xs, nivel) -> float | None:
    for k in range(1, len(xs)):
        if xs[k] >= nivel > xs[k - 1]:
            return ts[k - 1] + (nivel - xs[k - 1]) / (xs[k] - xs[k - 1]) * (ts[k] - ts[k - 1])
    return None


def referencia_fina(c: Caso, h: float = 1e-5) -> dict:
    cil = cilindro(c)
    toma = Toma()
    cA, cB = caminos(c, toma)
    p_src = cA[0].p
    Ff = cil.sellos_N(p_src)
    L = cil.carrera
    pA, pB = P_ATM_PA, p_src     # en reposo: retraído, B con la red
    x = v = 0.0
    masa = 0.0
    ts, xs = [0.0], [0.0]
    n = int(round(c.t_fin / h))
    vmax = 0.0
    for k in range(n):
        VA, VB = cil.volumenes(x)
        qA, qs = caudal_entrante(cA, pA)
        qB, _ = caudal_entrante(cB, pB)
        masa += qs[0] * h
        pA += h * dpdt(pA, VA, qA, cil.A * v)
        pB += h * dpdt(pB, VB, qB, -cil.A_anular * v)
        F = cil.fuerza(pA, pB)
        if v == 0.0 and abs(F) <= Ff:
            acc = 0.0
        else:
            sgn = math.copysign(1.0, v) if v != 0.0 else math.copysign(1.0, F)
            acc = (F - Ff * sgn) / c.masa_kg
        v_n = v + h * acc
        if v != 0.0 and v_n * v < 0.0:   # Coulomb: se detiene, no invierte en el paso
            v_n = 0.0
        x += h * v_n
        v = v_n
        if x >= L:
            x, v = L, min(v, 0.0)
        elif x <= 0.0:
            x, v = 0.0, max(v, 0.0)
        vmax = max(vmax, v)
        if (k + 1) % 50 == 0:
            ts.append((k + 1) * h)
            xs.append(x)
    return {"t_carrera": _cruce(ts, xs, L - 1e-3), "consumo_NL": anr_l(masa), "v_max": vmax}


def _xml(c: Caso, Ff: float) -> str:
    L = c.carrera_mm / 1000.0
    return ('<mujoco><option timestep="0.001" integrator="implicitfast" gravity="0 0 0"/>'
            '<worldbody><body name="p"><inertial pos="0 0 0" mass="%.6f" diaginertia="1e-4 1e-4 1e-4"/>'
            '<joint name="j" type="slide" axis="1 0 0" limited="true" range="0 %.6f" solreflimit="0.004 1" '
            'frictionloss="%.6g"/><geom type="box" size=".01 .01 .01" contype="0" conaffinity="0"/></body>'
            '</worldbody><actuator><motor name="a" joint="j" gear="1" ctrllimited="false" '
            'forcelimited="false"/></actuator></mujoco>') % (c.masa_kg, L, Ff)


def acoplado(c: Caso, nstep: int = 2, timestep: float = 1e-3) -> dict:
    import mujoco

    cil = cilindro(c)
    toma = Toma()
    cA, cB = caminos(c, toma)
    Ff = cil.sellos_N(cA[0].p)
    m = mujoco.MjModel.from_xml_string(_xml(c, Ff))
    d = mujoco.MjData(m)
    cil.pA, cil.pB = P_ATM_PA, cA[0].p
    dt = timestep * nstep
    ts, xs = [0.0], [0.0]
    vmax = 0.0
    for _ in range(int(round(c.t_fin / dt))):
        F = cil.intercambio(dt, float(d.qpos[0]), float(d.qvel[0]), cA, cB)
        toma.cerrar(dt)
        d.ctrl[0] = F
        mujoco.mj_step(m, d, nstep=nstep)
        ts.append(float(d.time))
        xs.append(float(d.qpos[0]))
        vmax = max(vmax, float(d.qvel[0]))
    return {"t_carrera": _cruce(ts, xs, cil.carrera - 1e-3), "consumo_NL": anr_l(toma.total), "v_max": vmax}
