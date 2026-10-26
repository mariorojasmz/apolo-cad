"""El integrador incremental de la dinámica (V8.2 D9; V8.3 F4, D8 y D11).

`simulate_dynamics` de V8.2 partido en tres, SIN cambiar lo que calcula (un test lo compara
bit a bit con el bucle cerrado de V8.2):
  - `Integrador(snap)`: todo lo de antes del bucle (MjModel, MjData, ids, banda, fotoceldas,
    estacionamiento de los productos, fotograma 0);
  - `intercambio(control=None, fuerzas=None)`: UNA vuelta de intercambio (`nstep` pasos de
    física). `control(d, t)` reemplaza a `ControlMotores.aplicar` (la co-simulación escribe
    ganancia, tope y consigna de cada `<velocity>`); `fuerzas(d, t)` corre DESPUÉS del arrastre
    de la banda, que pone `qfrc_applied` a cero;
  - `salida()`: la salida D9 de V8.2.
`correr()` es el bucle de V8.2: `simulate_dynamics` lo llama tal cual.

Sin OCCT ni el catálogo: importa sólo numpy, MuJoCo (perezoso) y los módulos de datos de la
física, porque corre en el worker de la co-simulación (`tests/test_cosim_worker.py`).
"""

from __future__ import annotations

import math
import time

import numpy as np

from apolo.physics.dinamica_arrastre import ArrastreBanda, eje_texto
from apolo.physics.dinamica_control import ControlMotores
from apolo.physics.dinamica_flujo import Flujo
from apolo.physics.dinamica_nacimiento import Nacimientos
from apolo.physics.sensores import Fotoceldas
from apolo.physics.sim import MM, PhysicsError, _pose_matrix, _require_mujoco

_LIMITE_TOL = (0.5, 0.5)       # grados | mm: «llegó al límite»


def _ids(mujoco, m, tipo, nombres):
    return [mujoco.mj_name2id(m, tipo, n) for n in nombres]


class Integrador:
    """MuJoCo sobre un `DynamicsSnapshot`, avanzado de a un intercambio."""

    def __init__(self, snap):
        if snap.early is not None:
            raise PhysicsError(snap.early.get("mensaje", "nada que simular"))
        mujoco = _require_mujoco()
        try:
            m = mujoco.MjModel.from_xml_string(snap.xml)
        except Exception as exc:  # noqa: BLE001
            raise PhysicsError(f"No se pudo construir el mundo dinámico: {exc}") from exc
        d = mujoco.MjData(m)
        self.mujoco, self.m, self.d, self.snap = mujoco, m, d, snap
        B = mujoco.mjtObj.mjOBJ_BODY
        cuerpos = [c["name"] for c in snap.cuerpos]
        self.bid_cuerpo = dict(zip(cuerpos, _ids(mujoco, m, B, cuerpos)))
        prods = snap.productos
        self.bid_prod = _ids(mujoco, m, B, [p["name"] for p in prods])
        self.qadr = [int(m.jnt_qposadr[m.body_jntadr[b]]) for b in self.bid_prod]
        self.vadr = [int(m.jnt_dofadr[m.body_jntadr[b]]) for b in self.bid_prod]
        #: junta Apolo → (dirección en qpos, dirección en qvel)
        self.juntas = {n: (int(m.jnt_qposadr[i]), int(m.jnt_dofadr[i]))
                       for n, i in ((n, mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, j["mj"]))
                                    for n, j in snap.juntas.items())}
        self.activo = [p["aparece_s"] <= 1e-12 for p in prods]
        for k, p in enumerate(prods):
            if self.activo[k]:
                d.qvel[self.vadr[k]: self.vadr[k] + 3] = p["vel_m_s"]

        self.motores = ControlMotores(mujoco, m, snap.motores)
        self.arrastre = (ArrastreBanda(mujoco, m, d, snap.bandas, [p["name"] for p in prods],
                                       snap.modelo_banda, {n: v[1] for n, v in self.juntas.items()},
                                       snap.gravedad, snap.timestep * snap.nstep)
                         if snap.bandas else None)
        nombre_cuerpo = {b: n for n, b in self.bid_cuerpo.items()}
        nombre_cuerpo.update({b: p["name"] for b, p in zip(self.bid_prod, prods)})
        self.fotos = Fotoceldas(mujoco, m, snap.sensores, nombre_cuerpo) if snap.sensores else None

        self.giro = {n: j["tipo"] != "prismatica" for n, j in snap.juntas.items()}
        self.trazas = {n: {"t": [], "q": [], "qd": [], "par": []} for n in snap.juntas}
        self.en_limite: dict[str, dict] = {}
        self.frames: list[dict] = []
        # los que esperan su hora quedan estacionados lejos (sin colisión ni salida): índices
        # vectorizados, rehechos sólo cuando entra un producto
        self.pendientes = sorted((k for k in range(len(prods)) if not self.activo[k]),
                                 key=lambda k: prods[k]["aparece_s"])
        # los sumideros (F6 de puerta-de-publicacion) RETIRAN el producto que pasa su plano:
        # vuelve a su estacionamiento y sale de los fotogramas; un snapshot sin ellos, igual
        self.sumideros = [(np.asarray(p, float), np.asarray(n, float))
                          for p, n in getattr(snap, "sumideros", None) or []]
        self.retirados: list[int] = []
        self.retiro: dict[int, dict] = {}
        # el balance de producto (plan balance-de-producto D5): sólo con `flujo`; sin él, nada
        conf = getattr(snap, "flujo", None)
        self.flujo = Flujo(conf, prods) if conf else None
        self._bid = np.asarray(self.bid_prod, dtype=int)
        if self.flujo:
            for k, p in enumerate(prods):
                if self.activo[k]:
                    self.flujo.nacio(k, 0.0, (p["x"], p["y"], p["z"]))
        # una caja de la cola nace sólo con su lugar de entrada libre (V8.4): si no, espera
        self.nac = Nacimientos(mujoco, m, self.bid_prod, [p["name"] for p in prods])
        self._estacion: dict = {}
        self._rehacer_estacion()
        mujoco.mj_forward(m, d)
        self.dt_int = snap.timestep * snap.nstep
        self.n_int = max(1, int(round(snap.duracion_s / self.dt_int)))
        self._paso_frame = 1.0 / snap.fps
        self._prox = 0.0
        if self.fotos:
            self.fotos.medir(d, 0.0)
        self._muestra(0.0)
        self._prox += self._paso_frame
        self._t0: float | None = None
        self.hechos = 0

    # ── lo que V8.2 tenía como clausuras ─────────────────────────────────────────────────────

    def q_apolo(self, n):
        """(q, q̇) de la junta en unidades Apolo: grados y rpm, o mm y mm/s."""
        qa, da = self.juntas[n]
        d = self.d
        if self.giro[n]:
            return math.degrees(d.qpos[qa]), d.qvel[da] * 60.0 / (2 * math.pi)
        return d.qpos[qa] / MM, d.qvel[da] / MM

    def _muestra(self, t):
        d, snap = self.d, self.snap
        poses = {c: _pose_matrix(d.xpos[b], d.xquat[b]) for c, b in self.bid_cuerpo.items()}
        for k, b in enumerate(self.bid_prod):
            if self.activo[k]:
                poses[snap.productos[k]["name"]] = _pose_matrix(d.xpos[b], d.xquat[b])
        self.frames.append({"t": round(t, 4), "poses": poses})
        for n in snap.juntas:
            q, qd = self.q_apolo(n)
            tr = self.trazas[n]
            tr["t"].append(round(t, 4))
            tr["q"].append(round(float(q), 4))
            tr["qd"].append(round(float(qd), 4))
            tr["par"].append(round(float(d.qfrc_actuator[self.juntas[n][1]]), 4))
            rango = snap.juntas[n]["rango"]
            if rango and n not in self.en_limite:
                giro = self.giro[n]
                lo, hi = ((math.degrees(rango[0]), math.degrees(rango[1])) if giro
                          else (rango[0] / MM, rango[1] / MM))
                tol = _LIMITE_TOL[0 if giro else 1]
                if q <= lo + tol or q >= hi - tol:
                    self.en_limite[n] = {"junta": n, "limite": round(lo if q <= lo + tol else hi, 3),
                                         "t": round(t, 4)}
        if self.fotos:
            self.fotos.muestrear(t)

    def _rehacer_estacion(self):
        ks, prods = self.pendientes + self.retirados, self.snap.productos
        est = self._estacion
        est["q"] = np.array([self.qadr[k] + i for k in ks for i in range(7)], dtype=int)
        est["qv"] = np.array([c for k in ks for c in (*prods[k]["estacion"], 1.0, 0.0, 0.0, 0.0)])
        est["v"] = np.array([self.vadr[k] + i for k in ks for i in range(6)], dtype=int)

    def _estacionar(self):
        if self.pendientes or self.retirados:
            self.d.qpos[self._estacion["q"]] = self._estacion["qv"]
            self.d.qvel[self._estacion["v"]] = 0.0

    # ── el bucle ─────────────────────────────────────────────────────────────────────────────

    @property
    def t(self) -> float:
        return float(self.d.time)

    def intercambio(self, control=None, fuerzas=None) -> None:
        """Una vuelta de V8.2: productos que entran, consignas, banda, `nstep` pasos, sensores y
        el fotograma si toca."""
        if self._t0 is None:
            self._t0 = time.perf_counter()
        d, m, mujoco, snap = self.d, self.m, self.mujoco, self.snap
        prods = snap.productos
        t = d.time
        if self.pendientes and prods[self.pendientes[0]]["aparece_s"] <= t + 1e-9:
            self._nacer(d, t)
        self._estacionar()
        if control is None:
            self.motores.aplicar(d, t)
        else:
            control(d, t)
        if self.arrastre:
            self.arrastre.aplicar()
        if fuerzas is not None:
            fuerzas(d, t)
        mujoco.mj_step(m, d, nstep=snap.nstep)
        # MuJoCo REINICIA el estado ante una aceleración inválida: se mira su contador
        if d.warning[mujoco.mjtWarning.mjWARN_BADQACC].number or not np.all(np.isfinite(d.qacc)):
            raise PhysicsError(f"La simulación divergió cerca de t = {t:.3f} s: baja 'timestep' o "
                               "revisa productos que nacen dentro de la máquina o solapados")
        if self.sumideros:
            self._retirar(d)
        if self.flujo:
            self.flujo.medir(float(d.time), np.asarray(d.xpos[self._bid], float) / MM)
        if self.fotos:
            self.fotos.medir(d, d.time)
        if d.time >= self._prox - 1e-9:
            self._muestra(d.time)
            while self._prox <= d.time + 1e-9:
                self._prox += self._paso_frame
        self.hechos += 1

    def _nacer(self, d, t) -> None:
        """Los productos a los que les tocó nacen, cada uno sólo con su lugar de entrada libre
        (`dinamica_nacimiento`); el que lo encuentra ocupado espera, y detrás de él las
        siguientes instancias de su MISMO producto (cola FIFO)."""
        prods, nac = self.snap.productos, self.nac
        quedan, trancados, nacieron = [], {}, False
        for i, k in enumerate(self.pendientes):
            p = prods[k]
            if p["aparece_s"] > t + 1e-9:
                quedan += self.pendientes[i:]
                break
            pos = (p["x"] * MM, p["y"] * MM, p["z"] * MM)
            por = trancados.get(p["producto"]) or nac.ocupante(d, k, pos, p["quat"], self.activo)
            if por is not None:
                trancados[p["producto"]] = por
                nac.espera(k, t, por)
                quedan.append(k)
                continue
            self.activo[k] = True
            nacieron = True
            nac.nacio(k, p["aparece_s"], t)
            if self.flujo:
                self.flujo.nacio(k, t, (p["x"], p["y"], p["z"]))
            q, v = self.qadr[k], self.vadr[k]
            d.qpos[q: q + 3] = pos
            d.qpos[q + 3: q + 7] = p["quat"]
            d.qvel[v: v + 6] = (*p["vel_m_s"], 0.0, 0.0, 0.0)
        self.pendientes = quedan
        if nacieron:
            self._rehacer_estacion()

    def _retirar(self, d) -> None:
        """Saca del mundo los productos activos con su centro pasado un sumidero."""
        nuevos = []
        for k, b in enumerate(self.bid_prod):
            if not self.activo[k]:
                continue
            c = np.asarray(d.xpos[b], float)
            i = next((i for i, (p, n) in enumerate(self.sumideros) if float((c - p) @ n) > 0.0), None)
            if i is not None:
                self.activo[k] = False
                self.retiro[k] = {"t": round(float(d.time), 4),
                                  "pos": [round(float(x) / MM, 1) for x in c]}
                nuevos.append(k)
                if self.flujo:
                    self.flujo.retirado(k, float(d.time), i)
        if nuevos:
            self.retirados += nuevos
            self._rehacer_estacion()
            self._estacionar()

    def podar(self) -> None:
        """Olvida la historia (fotogramas, trazas por junta, flancos y muestras de las
        fotoceldas) y conserva la última muestra: la sesión en vivo de V8.4 corre sin límite y
        no acumula. Nada de lo olvidado entra al paso siguiente (sólo a `salida`)."""
        del self.frames[:-1]
        for tr in self.trazas.values():
            for lista in tr.values():
                del lista[:-1]
        if self.fotos:
            self.fotos.podar()

    def correr(self) -> dict:
        """El bucle cerrado de V8.2: todos los intercambios y la salida."""
        for _ in range(self.n_int):
            self.intercambio()
        return self.salida()

    def salida(self) -> dict:
        pared = time.perf_counter() - self._t0 if self._t0 is not None else 0.0
        if self.frames[-1]["t"] < round(self.d.time, 4):
            self._muestra(self.d.time)
        return salida_dinamica(self.snap, self.d, self.frames, self.trazas, self.en_limite,
                               self.fotos, self.arrastre, self.juntas, self.giro, self.activo,
                               self.bid_prod, self.vadr, pared, retiro=self.retiro,
                               nacimientos=(self.nac, self.pendientes),
                               flujo=(self.flujo.salida(float(self.d.time), self.pendientes, self.nac)
                                      if self.flujo else None))


def salida_dinamica(snap, d, frames, trazas, en_limite, fotos, arrastre, juntas, giro, activo,
                    bid_prod, vadr, pared, retiro=None, nacimientos=None, flujo=None) -> dict:
    """La salida D9 de V8.2 (formato del animador de gravedad y de caída, trazas por junta).
    Un producto RETIRADO por un sumidero sale con la posición en que se retiró y `retirado_s`;
    `resumen.productos_retirados` sólo existe si alguno se retiró. Uno que nació TARDE porque su
    lugar de entrada estaba ocupado lleva `nacio_s`; los que no llegaron a nacer por eso van en
    `resumen.productos_sin_nacer`, con su aviso (sólo si los hay: sin espera, la salida de V8.2).
    Con el balance de producto (`flujo`, plan balance-de-producto) va en `flujo`; sin él, nada."""
    prods = snap.productos
    res_prod, caidos = {}, []
    retiro = retiro or {}
    nac, pendientes = nacimientos if nacimientos else (None, [])
    demoradas = nac.demoradas if nac else {}
    sin_nacer = [prods[k]["name"] for k in pendientes if nac and k in nac.esperando]
    avisos = snap.avisos + (nac.avisos(prods, pendientes) if nac else [])
    for k, p in enumerate(prods):
        if k in retiro:
            res_prod[p["name"]] = {"posicion_final_mm": retiro[k]["pos"],
                                   "velocidad_final_mm_s": [0.0, 0.0, 0.0], "cayo": False,
                                   "retirado_s": retiro[k]["t"]}
            continue
        if not activo[k]:
            continue
        pos = [round(float(c) / MM, 1) for c in d.xpos[bid_prod[k]]]
        vel = [round(float(c) / MM, 2) for c in d.qvel[vadr[k]: vadr[k] + 3]]
        medio = max(p["w"], p["d"], p["h"]) / 2
        cayo = pos[2] < medio + 10.0 and p["z"] > medio + 60.0
        res_prod[p["name"]] = {"posicion_final_mm": pos, "velocidad_final_mm_s": vel, "cayo": cayo,
                               **({"nacio_s": demoradas[k]["nacio_s"]} if k in demoradas else {})}
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
            **({"productos_retirados": [prods[k]["name"] for k in sorted(retiro)]}
               if retiro else {}),
            **({"productos_sin_nacer": sin_nacer} if sin_nacer else {}),
        },
        "avisos": avisos,
        **({"flujo": flujo} if flujo is not None else {}),
    }
