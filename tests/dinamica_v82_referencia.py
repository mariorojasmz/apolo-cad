"""El bucle CERRADO de `simulate_dynamics` de V8.2, copiado tal cual de `physics/dinamica.py`
antes de V8.3 F4 (git `7d1ba5a`): la referencia contra la que `test_cosim_stepper.py` compara el
`Integrador` bit a bit. No se edita: si V8.2 cambia a propósito, se cambia también aquí y se
dice en el commit.
"""

from __future__ import annotations

import math
import time

import numpy as np

from apolo.physics.dinamica_arrastre import ArrastreBanda, eje_texto
from apolo.physics.dinamica_control import ControlMotores
from apolo.physics.sensores import Fotoceldas
from apolo.physics.sim import MM, PhysicsError, _pose_matrix, _require_mujoco

_LIMITE_TOL = (0.5, 0.5)       # grados | mm: «llegó al límite»


def _ids(mujoco, m, tipo, nombres):
    return [mujoco.mj_name2id(m, tipo, n) for n in nombres]


def simulate_dynamics_v82(snap) -> dict:
    """FASE MuJoCo (bajo PHYSICS_LOCK): integra el snapshot y arma la salida D9. No toca OCCT."""
    if snap.early is not None:
        return snap.early
    mujoco = _require_mujoco()
    try:
        m = mujoco.MjModel.from_xml_string(snap.xml)
    except Exception as exc:  # noqa: BLE001
        raise PhysicsError(f"No se pudo construir el mundo dinámico: {exc}") from exc
    d = mujoco.MjData(m)
    B = mujoco.mjtObj.mjOBJ_BODY
    cuerpos = [c["name"] for c in snap.cuerpos]
    bid_cuerpo = dict(zip(cuerpos, _ids(mujoco, m, B, cuerpos)))
    prods = snap.productos
    bid_prod = _ids(mujoco, m, B, [p["name"] for p in prods])
    qadr = [int(m.jnt_qposadr[m.body_jntadr[b]]) for b in bid_prod]
    vadr = [int(m.jnt_dofadr[m.body_jntadr[b]]) for b in bid_prod]
    juntas = {n: (int(m.jnt_qposadr[i]), int(m.jnt_dofadr[i]))
              for n, i in ((n, mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, j["mj"]))
                           for n, j in snap.juntas.items())}
    activo = [p["aparece_s"] <= 1e-12 for p in prods]
    for k, p in enumerate(prods):
        if activo[k]:
            d.qvel[vadr[k]: vadr[k] + 3] = p["vel_m_s"]

    motores = ControlMotores(mujoco, m, snap.motores)
    arrastre = (ArrastreBanda(mujoco, m, d, snap.bandas, [p["name"] for p in prods],
                              snap.modelo_banda, {n: v[1] for n, v in juntas.items()}, snap.gravedad,
                              snap.timestep * snap.nstep)
                if snap.bandas else None)
    nombre_cuerpo = {b: n for n, b in bid_cuerpo.items()}
    nombre_cuerpo.update({b: p["name"] for b, p in zip(bid_prod, prods)})
    fotos = Fotoceldas(mujoco, m, snap.sensores, nombre_cuerpo) if snap.sensores else None

    giro = {n: j["tipo"] != "prismatica" for n, j in snap.juntas.items()}
    trazas = {n: {"t": [], "q": [], "qd": [], "par": []} for n in snap.juntas}
    en_limite: dict[str, dict] = {}
    frames: list[dict] = []

    def q_apolo(n):
        qa, da = juntas[n]
        if giro[n]:
            return math.degrees(d.qpos[qa]), d.qvel[da] * 60.0 / (2 * math.pi)
        return d.qpos[qa] / MM, d.qvel[da] / MM

    def muestra(t):
        poses = {c: _pose_matrix(d.xpos[b], d.xquat[b]) for c, b in bid_cuerpo.items()}
        for k, b in enumerate(bid_prod):
            if activo[k]:
                poses[prods[k]["name"]] = _pose_matrix(d.xpos[b], d.xquat[b])
        frames.append({"t": round(t, 4), "poses": poses})
        for n in snap.juntas:
            q, qd = q_apolo(n)
            tr = trazas[n]
            tr["t"].append(round(t, 4))
            tr["q"].append(round(float(q), 4))
            tr["qd"].append(round(float(qd), 4))
            tr["par"].append(round(float(d.qfrc_actuator[juntas[n][1]]), 4))
            rango = snap.juntas[n]["rango"]
            if rango and n not in en_limite:
                lo, hi = ((math.degrees(rango[0]), math.degrees(rango[1])) if giro[n]
                          else (rango[0] / MM, rango[1] / MM))
                tol = _LIMITE_TOL[0 if giro[n] else 1]
                if q <= lo + tol or q >= hi - tol:
                    en_limite[n] = {"junta": n, "limite": round(lo if q <= lo + tol else hi, 3),
                                    "t": round(t, 4)}
        if fotos:
            fotos.muestrear(t)

    # los que esperan su hora quedan estacionados lejos (sin colisión ni salida): índices
    # vectorizados, rehechos sólo cuando entra un producto
    pendientes = sorted((k for k in range(len(prods)) if not activo[k]),
                        key=lambda k: prods[k]["aparece_s"])
    estacion: dict = {}

    def rehacer_estacion():
        ks = pendientes
        estacion["q"] = np.array([qadr[k] + i for k in ks for i in range(7)], dtype=int)
        estacion["qv"] = np.array([c for k in ks for c in (*prods[k]["estacion"], 1.0, 0.0, 0.0, 0.0)])
        estacion["v"] = np.array([vadr[k] + i for k in ks for i in range(6)], dtype=int)

    def estacionar():
        if pendientes:
            d.qpos[estacion["q"]] = estacion["qv"]
            d.qvel[estacion["v"]] = 0.0

    rehacer_estacion()
    mujoco.mj_forward(m, d)
    dt_int = snap.timestep * snap.nstep
    n_int = max(1, int(round(snap.duracion_s / dt_int)))
    paso_frame = 1.0 / snap.fps
    prox = 0.0
    if fotos:
        fotos.medir(d, 0.0)
    muestra(0.0)
    prox += paso_frame
    t0 = time.perf_counter()
    for _ in range(n_int):
        t = d.time
        if pendientes and prods[pendientes[0]]["aparece_s"] <= t + 1e-9:
            while pendientes and prods[pendientes[0]]["aparece_s"] <= t + 1e-9:
                k = pendientes.pop(0)
                p = prods[k]
                activo[k] = True
                d.qpos[qadr[k]: qadr[k] + 3] = (p["x"] * MM, p["y"] * MM, p["z"] * MM)
                d.qpos[qadr[k] + 3: qadr[k] + 7] = p["quat"]
                d.qvel[vadr[k]: vadr[k] + 6] = (*p["vel_m_s"], 0.0, 0.0, 0.0)
            rehacer_estacion()
        estacionar()
        motores.aplicar(d, t)
        if arrastre:
            arrastre.aplicar()
        mujoco.mj_step(m, d, nstep=snap.nstep)
        # MuJoCo REINICIA el estado ante una aceleración inválida: se mira su contador
        if d.warning[mujoco.mjtWarning.mjWARN_BADQACC].number or not np.all(np.isfinite(d.qacc)):
            raise PhysicsError(f"La simulación divergió cerca de t = {t:.3f} s: baja 'timestep' o "
                               "revisa productos que nacen dentro de la máquina o solapados")
        if fotos:
            fotos.medir(d, d.time)
        if d.time >= prox - 1e-9:
            muestra(d.time)
            while prox <= d.time + 1e-9:
                prox += paso_frame
    pared = time.perf_counter() - t0
    if frames[-1]["t"] < round(d.time, 4):
        muestra(d.time)
    return _salida(snap, d, frames, trazas, en_limite, fotos, arrastre, juntas, giro, activo,
                   bid_prod, vadr, pared)


def _salida(snap, d, frames, trazas, en_limite, fotos, arrastre, juntas, giro, activo, bid_prod,
            vadr, pared) -> dict:
    prods = snap.productos
    res_prod, caidos = {}, []
    for k, p in enumerate(prods):
        if not activo[k]:
            continue
        pos = [round(float(c) / MM, 1) for c in d.xpos[bid_prod[k]]]
        vel = [round(float(c) / MM, 2) for c in d.qvel[vadr[k]: vadr[k] + 3]]
        medio = max(p["w"], p["d"], p["h"]) / 2
        cayo = pos[2] < medio + 10.0 and p["z"] > medio + 60.0
        res_prod[p["name"]] = {"posicion_final_mm": pos, "velocidad_final_mm_s": vel, "cayo": cayo}
        if cayo:
            caidos.append(p["name"])
    res_juntas = {}
    for n in juntas:
        tr = trazas[n]
        res_juntas[n] = {"q_final": tr["q"][-1], ("velocidad_final_rpm" if giro[n] else
                                                  "velocidad_final_mm_s"): tr["qd"][-1],
                         "par_final": tr["par"][-1]}
    res_bandas = []
    for k, b in enumerate(snap.bandas):
        vb = arrastre.v_banda(k) if arrastre else 0.0
        hacia = eje_texto(np.asarray(b.e) * (1 if vb >= 0 else -1)) if abs(vb) > 1e-4 else "detenida"
        res_bandas.append({"pieza": b.pieza, "junta": b.junta, "radio_mm": round(b.radio / MM, 2),
                           "avanza_con_giro_positivo": b.avanza, "avanza_hacia": hacia,
                           "v_final_m_s": round(abs(vb), 5)})
    unidades = {n: ({"q": "grados", "qd": "rpm", "par": "N·m"} if giro[n]
                    else {"q": "mm", "qd": "mm/s", "par": "N"}) for n in juntas}
    return {
        "frames": frames,
        "piezas": snap.piezas,
        "cuerpos": snap.cuerpos,
        "productos": [{c: v for c, v in p.items() if c not in ("vel_m_s", "estacion", "quat")}
                      for p in prods],
        "juntas": {n: {**trazas[n], "unidades": unidades[n], "tipo": snap.juntas[n]["tipo"]}
                   for n in juntas},
        "sensores": fotos.salida() if fotos else {},
        "motores": [{"junta": mo.junta, "modo": mo.modo, "consigna": round(mo.consigna, 6),
                     "kv": round(mo.kv, 4), "tope": mo.fuerza_max, **mo.info} for mo in snap.motores],
        "resumen": {
            "duracion_s": round(float(d.time), 4), "timestep_s": snap.timestep,
            "intercambio_s": snap.timestep * snap.nstep, "fps": snap.fps,
            "t_pared_s": round(pared, 3),
            "factor_tiempo_real": round(float(d.time) / pared, 2) if pared > 0 else None,
            "juntas": res_juntas, "bandas": res_bandas, "productos": res_prod,
            "productos_caidos": caidos, "juntas_en_limite": list(en_limite.values()),
        },
        "avisos": snap.avisos,
    }
