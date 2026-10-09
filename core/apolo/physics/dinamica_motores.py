"""Accionamientos de la simulación dinámica (V8.2 D3, D7).

- `velocidad`: actuador NATIVO `<velocity>` de MuJoCo. Con `placa`, es el motor de inducción
  + reductor por la rama estable de Kloss linealizada (`library/engineering/motor_induccion`):
  consigna ωs(f)/i, kv = 2·Tk/(sk·ωs)·i²·η y tope ±Tk·i·η. Con `valor` (rpm o mm/s) o
  `v_superficie_m_s` es una fuente de velocidad ideal: kv = 100·J/Δt (la caída de velocidad
  bajo la carga habitual queda < 1 %), salvo `kv`/`par_max` explícitos. V8.0 midió que el
  nativo queda exacto con cualquier intercambio; un par de Kloss en Python oscila desde 4 ms.
- `par`: `<motor>` con par (o fuerza) constante, con rampa opcional desde 0.

Sentido (D7): con `direccion_transporte` el signo de la consigna se calcula para que la
superficie de transporte (la cara superior de la banda o la generatriz superior del rodillo)
avance hacia esa dirección; sin ella, el signo es el del eje de la junta y la salida lo dice.

`resolver_motores` corre en la preparación (datos puros); `ControlMotores`, en el bucle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from apolo.library.engineering.motor_induccion import kloss_linealizado
from apolo.physics.banda import eje_texto
from apolo.physics.dinamica_cuerpos import normal_arriba, signo_transporte
from apolo.physics.sim import PhysicsError

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
    armadura: float = 0.0       # kg·m²: inercia del rotor reflejada (J·i²)
    info: dict = field(default_factory=dict)


def _sentido(m, junta: dict, banda, radio_giro) -> tuple[float, str, bool]:
    """(signo, explicación, inferido) de la consigna según D7. `inferido` = sin
    `direccion_transporte` (la salida lo avisa)."""
    eje = np.asarray(junta["axis"], float)
    eje /= np.linalg.norm(eje)
    if junta["type"] == "prismatica":
        if m.direccion_transporte is None:
            return 1.0, f"sin direccion_transporte: avanza hacia {eje_texto(eje)} (el eje de la junta)", True
        p = float(eje @ np.asarray(m.direccion_transporte))
        if abs(p) < 0.2:
            raise PhysicsError(f"motor de '{m.junta}': direccion_transporte es casi perpendicular al eje")
        return math.copysign(1.0, p), "sentido fijado por direccion_transporte", False
    if banda is not None:
        normal, superficie = np.asarray(banda.n), f"la banda '{banda.pieza}'"
    elif radio_giro is not None:
        normal, superficie = normal_arriba(eje), "la generatriz superior"
    else:
        normal, superficie = None, None
    direccion = m.direccion_transporte
    if direccion is None and banda is not None and banda.signo is not None:
        return banda.signo, f"sentido fijado por la direccion_transporte de {superficie}", False
    if direccion is None:
        if normal is None:
            return 1.0, f"sin direccion_transporte: giro positivo sobre {eje_texto(eje)} (mano derecha)", True
        avance = eje_texto(np.cross(eje, normal))
        return 1.0, f"sin direccion_transporte: {superficie} avanza hacia {avance}", True
    if normal is None:
        normal = normal_arriba(eje)
    s = signo_transporte(eje, normal, direccion)
    if s == 0.0:
        raise PhysicsError(
            f"motor de '{m.junta}': direccion_transporte es casi perpendicular a la marcha "
            f"({eje_texto(np.cross(eje, normal))} con giro positivo)"
        )
    return s, "sentido fijado por direccion_transporte", False


def resolver_motores(pet_motores: list, juntas: dict, incluidas: set, bandas_por_junta: dict,
                     radio_por_junta: dict, inercia_por_junta: dict, timestep: float,
                     fuera: dict) -> list[MotorDatos]:
    """Cada `MotorPeticion` → `MotorDatos` (consigna SI con signo, kv, tope)."""
    out: list[MotorDatos] = []
    disponibles = sorted(incluidas)
    for k, m in enumerate(pet_motores):
        donde = f"motores[{k}]"
        j = juntas.get(m.junta)
        if j is None:
            raise PhysicsError(
                f"{donde}: la junta '{m.junta}' no existe; juntas móviles: {disponibles or 'ninguna'}"
            )
        if j["type"] == "fija":
            raise PhysicsError(f"{donde}: '{m.junta}' es una junta fija: no se mueve")
        if m.junta not in incluidas:
            raise PhysicsError(f"{donde}: la junta '{m.junta}' quedó fuera de la simulación ({fuera.get(m.junta, 'su padre no está sujeto')})")
        giro = j["type"] != "prismatica"
        banda = bandas_por_junta.get(m.junta)
        radio = banda.radio if banda is not None else radio_por_junta.get(m.junta)
        signo, sentido, inferido = _sentido(m, j, banda, radio)
        info: dict = {"sentido": sentido, "inferido": inferido}
        kv, tope, armadura = m.kv, m.par_max, 0.0
        if m.modo == "par":
            consigna = signo * m.valor
        elif m.placa is not None:
            if not giro:
                raise PhysicsError(f"{donde}: 'placa' (motor de inducción) es para juntas de giro")
            try:
                k_ = kloss_linealizado(m.placa, m.reduccion, m.eta, m.frecuencia_hz)
            except ValueError as exc:
                raise PhysicsError(f"{donde}: {exc}") from exc
            consigna = signo * k_["omega_sinc_rad_s"]
            kv = k_["kv"]
            tope = m.par_max or k_["par_max_Nm"]
            armadura = k_["inercia_reflejada_kgm2"]
            info["modelo"] = "motor de inducción + reductor (Kloss linealizado)"
            info["kloss"] = {c: (round(v, 6) if isinstance(v, float) else v) for c, v in k_.items()}
        else:
            if m.v_superficie_m_s is not None:
                if radio is None or not giro:
                    raise PhysicsError(
                        f"{donde}: 'v_superficie_m_s' pide una junta que mueva una banda o un "
                        f"rodillo (de radio conocido); '{m.junta}' no: usa 'valor' en rpm"
                    )
                consigna = signo * m.v_superficie_m_s / radio
            else:
                consigna = signo * (m.valor * 2 * math.pi / 60.0 if giro else m.valor * 0.001)
            if kv is None:
                kv = KV_IDEAL_FACTOR * max(inercia_por_junta.get(m.junta, 0.0), 1e-6) / timestep
                info["modelo"] = "fuente ideal: kv = 100·J/Δt (da 'placa' o 'kv' para un motor real)"
        out.append(MotorDatos(
            nombre=f"a{k}", junta=m.junta, modo=m.modo, consigna=float(consigna),
            kv=float(kv or 0.0), fuerza_max=tope, rampa_s=m.rampa_s, desde_s=m.desde_s,
            armadura=armadura, info=info,
        ))
    return out


def inercia_minima(mot: MotorDatos, timestep: float) -> float:
    """Inercia (o masa) mínima de la junta para que un `<velocity>` CON tope no oscile.

    Saturado, el actuador es un par constante explícito: en un paso cambia la velocidad en
    F·Δt/J, y la banda lineal alrededor de la consigna mide F/kv. Si J < kv·Δt el paso salta
    la banda y el motor oscila entre los dos topes (medido en F1: tambor de 0,07 kg·m² con
    480 N·m de tope a 1 ms; la velocidad media salía 0)."""
    return mot.kv * timestep if (mot.modo == "velocidad" and mot.fuerza_max) else 0.0


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
