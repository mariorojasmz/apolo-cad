"""Los accionamientos en el bucle de la dinámica (V8.2 D3), sin OCCT ni el catálogo.

`MotorDatos` (lo que `dinamica_motores.resolver_motores` hornea en la preparación) y
`ControlMotores` (escribe `ctrl` en cada intercambio). Viven aparte porque
`dinamica_motores.py` importa `library.engineering` (y con él el catálogo y OCP), y el worker
de la co-simulación no debe cargarlos (V8.3 D11, `tests/test_cosim_worker.py`). Allí se
re-exportan; el modelo de cada modo está en su docstring.
"""

from __future__ import annotations

from dataclasses import dataclass, field

KV_IDEAL_FACTOR = 100.0


@dataclass
class MotorDatos:
    nombre: str                 # actuador MJCF
    junta: str                  # nombre Apolo
    modo: str                   # velocidad | par
    consigna: float             # rad/s | m/s | N·m | N, con signo
    kv: float = 0.0
    fuerza_max: float | None = None
    rampa_s: float = 0.0
    desde_s: float = 0.0
    armadura: float = 0.0       # kg·m² (kg en una prismática): inercia del rotor reflejada (J·i²·gear²)
    info: dict = field(default_factory=dict)
    #: plan motor-a-eje-lineal D2: el `gear` del actuador = 1/r de la transmisión a una junta
    #: prismática (consigna, kv y tope quedan en el EJE: rad/s, N·m·s/rad, N·m); 1 sin ella
    gear: float = 1.0


def inercia_minima(mot: MotorDatos, timestep: float) -> float:
    """Inercia (o masa) mínima de la junta para que un `<velocity>` CON tope no oscile.

    Saturado, el actuador es un par constante explícito: en un paso cambia la velocidad en
    F·Δt/J, y la banda lineal alrededor de la consigna mide F/kv. Si J < kv·Δt el paso salta
    la banda y el motor oscila entre los dos topes (medido en F1: tambor de 0,07 kg·m² con
    480 N·m de tope a 1 ms; la velocidad media salía 0). Con transmisión la ganancia en la
    junta es kv·gear² (el mínimo, en kg)."""
    return mot.kv * mot.gear ** 2 * timestep if (mot.modo == "velocidad" and mot.fuerza_max) else 0.0


class ControlMotores:
    """Escribe `ctrl` en cada intercambio: rampa, arranque diferido y el motor apagado (un
    `<velocity>` con consigna 0 FRENA: apagado es ganancia 0)."""

    def __init__(self, mujoco, m, motores: list[MotorDatos]):
        self.m = m
        self.motores = motores
        self.ids = [mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_ACTUATOR, x.nombre) for x in motores]
        self.encendido = [None] * len(motores)

    def aplicar(self, d, t: float) -> None:
        for k, mot in enumerate(self.motores):
            a = self.ids[k]
            on = t >= mot.desde_s - 1e-12
            if mot.modo == "velocidad" and on != self.encendido[k]:
                self.m.actuator_gainprm[a, 0] = mot.kv if on else 0.0
                self.m.actuator_biasprm[a, 2] = -mot.kv if on else 0.0
            self.encendido[k] = on
            if not on:
                d.ctrl[a] = 0.0
                continue
            f = 1.0 if mot.rampa_s <= 0 else min(1.0, (t - mot.desde_s) / mot.rampa_s)
            d.ctrl[a] = mot.consigna * f
