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

`resolver_motores` corre en la preparación (datos puros); `ControlMotores`, en el bucle
(con `MotorDatos`, en `dinamica_control.py`: sin el catálogo, para el worker de V8.3).
"""

from __future__ import annotations

import math

import numpy as np

from apolo.library.engineering.motor_induccion import kloss_linealizado
from apolo.physics.dinamica_arrastre import eje_texto
from apolo.physics.dinamica_control import (  # noqa: F401 — re-export (V8.3 F4)
    KV_IDEAL_FACTOR,
    ControlMotores,
    MotorDatos,
    inercia_minima,
)
from apolo.physics.dinamica_cuerpos import normal_arriba, signo_transporte
from apolo.physics.sim import PhysicsError


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
