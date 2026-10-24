"""El tablero en cada intercambio: los modelos de F2 sobre las dos redes de F3 (plan V8.3 D8, D9).

`Tablero(red, dispositivos)` arma las redes del formato plano y un modelo por aparato; `paso(dt)`
avanza el lado eléctrico UN intercambio (2 ms), en este orden:
  1. potencia: la red con `Red.salidas()` (fasores y Zk), la salida de cada variador como fuente
     ideal con la U y f de su paso anterior, y las cargas de potencia que dejó el paso anterior;
  2. las fuentes de continua (24 V, los 10 V del variador) con la tensión de su entrada y la
     corriente que pide el mando (`pedidas()` ANTES del paso: F3);
  3. el mando, con esas tensiones;
  4. cada modelo con sus tensiones y corrientes: bobinas, pilotos, protecciones (la corriente de
     sus contactos en las dos redes), mandos, E/S del PLC, sensores, los modelos con
     `BORNES_ENTRADA` (el relé de seguridad: lee esas entradas y mueve sus contactos con
     `actuadores()`), variadores y motores;
  5. lo que queda para el paso que viene: la carga de cada motor (D8: EN MARCHA = potencia que
     sale de su curva; DETENIDO en la red = impedancia de rotor bloqueado, F3), la de la entrada
     de cada fuente y variador, y el COMANDO de cada motor hacia MuJoCo (`comandos`).
Los estados de los modelos mueven los contactos del paso siguiente (`estados()`). Lo mecánico
llega de afuera: `mec[motor] = (ω, T)` en la salida del reductor y `detecta[sensor]`.

Puro: de `apolo` sólo `cosim` (sin MuJoCo ni OCCT).
"""

from __future__ import annotations

import cmath
import math

import numpy as np

from .modelos import (
    Contactor,
    Fuente,
    Fusible,
    Guardamotor,
    Itm,
    Motor,
    Piloto,
    PlcES,
    Red,
    ReleTermico,
    Sensor,
    Variador,
    crear_modelo,
)
from .modelos.electrovalvula import Electrovalvula
from .modelos.mandos import _Mando
from .neumatica import crear_modelo_aire
from .neumatica.red import RedAire
from .red import armar, fasores_nominales
from .red.mna import R_OFF

SQ3 = math.sqrt(3.0)
#: Factor de potencia de un motor a rotor bloqueado (el arranque directo): criterio de diseño,
#: dentro del 0,3–0,5 habitual de las fichas de motores IEC de baja potencia.
FP_ROTOR_BLOQUEADO = 0.4
#: Factor de potencia de desplazamiento de la entrada de un variador (puente de diodos): ~1,
#: criterio de diseño (las armónicas no se emulan, D1).
FP_VARIADOR = 1.0
#: Un motor gira (carga de potencia) desde el 1 % de su velocidad síncrona; por debajo está
#: detenido (rotor bloqueado), igual que `Motor.actuador_fases`.
FRACCION_EN_MARCHA = 0.01
#: La red de potencia se re-resuelve sólo si cambió un contacto, una fuente o una falla, o si una
#: carga o un fasor se movió más que esto (relativo): con el motor en régimen su S casi no se
#: mueve y la fasorial (punto fijo sobre la LU) es lo más caro del lado eléctrico. Determinista:
#: la decisión depende sólo de los números del paso.
TOL_POTENCIA = 1e-3


class Tablero:
    def __init__(self, red: dict, dispositivos: list, aire: dict | None = None):
        self.entrada = red
        self.redes = armar(red)
        self.mando_red, self.pot_red = self.redes.mando, self.redes.potencia
        self.modelos: dict = {}
        for d in dispositivos:
            m = crear_modelo(d.designacion, d.ref, d.modelo, d.ajustes, cantidad=d.cantidad)
            if m is None and (d.modelo or {}).get("aire"):  # V8.9: cilindro, FRL, corte (por su ficha de aire)
                m = crear_modelo_aire(d.designacion, d.ref, d.modelo["aire"], d.ajustes)
            if m is not None:
                self.modelos[d.designacion] = m
        #: el circuito de aire (V8.9 D3): None sin aire, y así el tablero de siempre
        self.aire = RedAire(aire, dispositivos, self.modelos) if aire else None
        self.hipotesis = list(self.redes.hipotesis) + [
            f"{des}: {h}" for des, m in self.modelos.items() for h in m.hipotesis] + (
            [f"aire: {h}" for h in self.aire.hipotesis] if self.aire else [])
        self.avisos = list(self.redes.avisos)
        self._indexar()
        self.mec: dict = {}            # motor → (ω_salida rad/s, par en la salida N·m)
        self.detecta: dict = {}        # sensor → bool (el rayo de MuJoCo)
        self.plc_salidas: dict = {des: {} for des, *_ in self.plcs}
        self.comandos: dict = {}
        self.cargas_pot: dict = {}
        self.pot = self.mando = None
        self._usados: dict = {}        # variador → (U, f) de su salida en este paso
        self._firma_pot = None
        self.resoluciones_potencia = 0
        self._motor_de: dict = {}      # variador → el motor que alimenta
        for des, m, *_ in self.motores:
            self.comandos[des] = m.actuador(0.0, 0.0)

    # ── índice de lo que lee cada modelo ────────────────────────────────────────────────────

    def _carga(self, des: str, tipo: str | None = None, borne: str | None = None) -> str | None:
        for c in self.entrada.get("cargas", ()):
            if c.get("dispositivo") == des and (tipo is None or c.get("tipo") == tipo) and (
                    borne is None or c["bornes"][0] == f"{des}:{borne}"):
                return c["id"]
        return None

    def _ramas_proteccion(self, des: str) -> list:
        out = []
        for r in self.entrada.get("ramas", ()):
            if r.get("dispositivo") == des and r.get("tipo") == "contacto" and r.get("contacto") == "proteccion":
                for red in (self.pot_red, self.mando_red):
                    if red is not None and r["id"] in red._de_rama:
                        out.append((red is self.pot_red, r["id"]))
        return out

    def _indexar(self) -> None:
        fuentes: dict = {}
        for f in self.entrada.get("fuentes", ()):
            fuentes.setdefault(f.get("dispositivo"), []).append(f["id"])
        self.contactores, self.pilotos, self.protecciones, self.mandos = [], [], [], []
        self.fuentes_dc, self.redes_ac, self.plcs, self.sensores, self.variadores = [], [], [], [], []
        self.motores, self.logicos, self.valvulas = [], [], []
        for des, m in self.modelos.items():
            fs = fuentes.get(des, [])
            if isinstance(m, Contactor):
                cid = self._carga(des, "bobina")
                self.contactores.append((des, m, cid, self._en_potencia(cid)))
            elif isinstance(m, Piloto):
                self.pilotos.append((des, m, self._carga(des, "piloto")))
            elif isinstance(m, (Itm, Guardamotor, ReleTermico, Fusible)):
                self.protecciones.append((des, m, self._ramas_proteccion(des)))
            elif isinstance(m, Fuente):
                self.fuentes_dc.append((des, m, fs[0] if fs else des, self._carga(des, "alimentacion")))
            elif isinstance(m, Red):
                self.redes_ac.append((des, m, fs[0] if fs else des))
            elif isinstance(m, PlcES):
                bornes = {b: self._carga(des, "entrada", b) for b in m.DI + m.AI}
                self.plcs.append((des, m, bornes, self._carga(des, "alimentacion", "L+")))
            elif isinstance(m, Sensor):
                self.sensores.append((des, m, self._carga(des, "alimentacion")))
            elif isinstance(m, Variador):
                ent = {b: self._carga(des, "entrada", b) for b in ("DI1", "DI2", "DI3", "DI4", "S1", "S2", "AI1")}
                ac = [f["id"] for f in self.entrada.get("fuentes", ()) if f.get("dispositivo") == des and f["tipo"] == "AC"]
                dc = [f for f in self.entrada.get("fuentes", ()) if f.get("dispositivo") == des and f["tipo"] == "DC"]
                self.variadores.append((des, m, ent, self._carga(des, "alimentacion"),
                                        ac[0] if ac else None, (dc[0]["id"], float(dc[0]["U_V"])) if dc else None))
            elif isinstance(m, Motor):
                self.motores.append((des, m, self._carga(des, "motor")))
            elif isinstance(m, Electrovalvula):  # V8.9 D6: una o dos bobinas, sin rama propia
                self.valvulas.append((des, m, {lado: self._carga(des, "bobina", borne)
                                               for lado, borne in m.BOBINAS.items()}))
            elif getattr(m, "BORNES_ENTRADA", None):  # lee entradas y mueve contactos (relé de seguridad)
                bornes = {b: self._carga(des, "entrada", b) for b in m.BORNES_ENTRADA}
                self.logicos.append((des, m, bornes, self._carga(des, "alimentacion")))
            elif isinstance(m, _Mando):
                self.mandos.append((des, m))
        self._red_ids = {fid: m for _, m, fid in self.redes_ac}
        self._donde: dict = {}
        for c in self.entrada.get("cargas", ()):
            for clave, red in (("m", self.mando_red), ("p", self.pot_red)):
                if red is not None and c["id"] in red._carga_idx:
                    self._donde[c["id"]] = clave
        self._prefijos = {des: des + "." for des in self.modelos}
        self._vfd_salida = {fid: des for des, _, _, _, fid, _ in self.variadores if fid}
        # las tensiones de TODAS las cargas del mando salen de un solo producto por paso
        self._um: dict = {}
        ia, ib = [], []
        for c in self.entrada.get("cargas", ()):
            if self._donde.get(c["id"]) == "m":
                self._um[c["id"]] = len(ia)
                ia.append(self.mando_red._ix(c["bornes"][0]))
                ib.append(self.mando_red._ix(c["bornes"][1]))
        self._ia_m, self._ib_m = np.array(ia, dtype=np.int64), np.array(ib, dtype=np.int64)
        self._Um: list = [0.0] * len(ia)
        # los nombres de los actuadores, una vez
        self._k_bobina = [(f"{des}.bobina", m) for des, m, *_ in self.contactores]
        self._k_prot = [(des, f"{des}.", m) for des, m, _ in self.protecciones]
        self._k_plc = [(m, [(b, f"{des}.{b}") for b in m.DO]) for des, m, *_ in self.plcs]
        self._k_sensor = [(f"{des}.señal", m) for des, m, _ in self.sensores]
        self._k_vfd = [(f"{des}.rele_falla", m) for des, m, *_ in self.variadores]
        self._k_mando = [(f"{des}.", f"{des}.potenciometro", m) for des, m in self.mandos] + [
            (f"{des}.", None, m) for des, m, *_ in self.logicos]
        # las cargas que un modelo con falla saca de la red (bobina cortada, lámpara fundida):
        # (¿abre ahora?, carga, en la potencia también); una electroválvula, por bobina
        self._con_carga = [(lambda m=m: m.abre_su_carga, cid, False) for _d, m, cid, _p in self.contactores if cid] + [
            (lambda m=m: m.abre_su_carga, cid, True) for _d, m, cid in self.pilotos if cid] + [
            (lambda m=m, lado=lado: m.abre_bobina(lado), cid, True)
            for _d, m, cids in self.valvulas for lado, cid in cids.items() if cid]
        self._abiertas: set = set()
        self._cargas_mando: dict = {}

    def _en_potencia(self, cid: str | None) -> bool:
        return bool(cid and self.pot_red is not None and cid in self.pot_red._carga_idx)

    # ── lecturas de las redes ───────────────────────────────────────────────────────────────

    def lee(self, cid: str | None) -> dict:
        """{"U_V", …} de una carga en la red donde esté (en la de potencia, sin corrientes:
        `tension_carga`); 0 si no está cableada."""
        donde = self._donde.get(cid)
        if donde == "m" and self.mando is not None:
            return self.mando.carga(cid)
        if donde == "p" and self.pot is not None:
            return self.pot.tension_carga(cid)
        return {"U_V": 0.0, "I_A": 0.0, "fases": 0}

    def U(self, cid: str | None) -> float:
        """La tensión de una carga (del primer borne al segundo en el mando)."""
        j = self._um.get(cid)
        if j is not None:
            return self._Um[j]
        if self._donde.get(cid) == "p" and self.pot is not None:
            return float(self.pot.tension_carga(cid)["U_V"])
        return 0.0

    def ramas_de(self, rama: str) -> list:
        """(red, id) de las ramas de un `cable_cortado`: el id exacto o los hilos de un cable
        («-W1» → «-W1.1», «-W1.2»…). Una unión ideal (sin largo) no está en ninguna red."""
        out = []
        for red in (self.mando_red, self.pot_red):
            if red is None:
                continue
            for rid in red._de_rama:
                if (rid == rama or rid.startswith(rama + ".") or rid.startswith(rama + "#")) and red._de_rama[rid]:
                    out.append((red, rid))
        return out

    def red(self, des: str | None) -> Red:
        if des is None:
            if len(self.redes_ac) != 1:
                raise ValueError(f"hay {len(self.redes_ac)} redes de suministro: di cuál («red»: "
                                 f"{', '.join(d for d, *_ in self.redes_ac) or 'ninguna'})")
            return self.redes_ac[0][1]
        m = self.modelos.get(des)
        if not isinstance(m, Red):
            raise ValueError(f"«{des}» no es una red de suministro del tablero")
        return m

    # ── estados → contactos ─────────────────────────────────────────────────────────────────

    def estados(self) -> dict:
        out: dict = {k: m.cerrado for k, m in self._k_bobina}
        for des, pref, m in self._k_prot:
            if isinstance(m, ReleTermico):
                out[pref + "disparo"] = m.disparado
            elif isinstance(m, Fusible):
                for k, f in enumerate(m.fundido):
                    out[f"{des}.{k + 1}.cerrado"] = not f
                out[pref + "cerrado"] = not any(m.fundido)
            else:
                out[pref + "cerrado"] = m.cerrado
        for pref, k_pot, m in self._k_mando:
            for a, v in m.actuadores().items():
                out[pref + a] = v
            if getattr(m, "potenciometro", None) is not None:
                out[k_pot] = m.potenciometro
        for m, claves in self._k_plc:
            for b, k in claves:
                out[k] = m.salida[b]
        for k, m in self._k_sensor:
            out[k] = m.activo
        for k, m in self._k_vfd:
            out[k] = bool(m.falla)
        return out

    # ── el intercambio ──────────────────────────────────────────────────────────────────────

    def paso(self, dt: float) -> None:
        est = self.estados()
        self._usados = {des: (m.U, m.f) for des, m, *_ in self.variadores}
        if self.pot_red is not None:
            fuentes = {fid: m.salidas() for _, m, fid in self.redes_ac}
            for des, _m, _e, _a, fid, _dc in self.variadores:
                if fid is not None:
                    U, f = self._usados[des]
                    fuentes[fid] = {"fasores": fasores_nominales("3F", U, 1 if f >= 0 else -1)}
            firma = self._firma_potencia(est, fuentes)
            if self.pot is None or not self._igual(firma, self._firma_pot):
                self.pot = self.pot_red.paso(est, fuentes, self.cargas_pot)
                self._firma_pot = firma
                self.resoluciones_potencia += 1
        self._cargas_que_abren()
        fuentes_dc: dict = {}
        cm = self._cargas_mando or None
        pedidas = self.mando_red.pedidas(est, cm) if self.mando_red is not None else {}
        for _des, m, fid, cid in self.fuentes_dc:
            m.paso(dt, {"U_entrada_V": self.U(cid), "I_carga_A": pedidas.get(fid, 0.0)})
            fuentes_dc[fid] = m.U
            if self._en_potencia(cid):
                self.cargas_pot[cid] = {"S": complex(m.salidas()["P_entrada_W"], 0.0)}
        vivas = {des: self._lineas(cid) for des, _m, _e, cid, _f, _dc in self.variadores}
        for des, m, _e, _a, _f, dc in self.variadores:
            if dc is not None:  # los 10 V del potenciómetro: con la red de su entrada en rango
                fuentes_dc[dc[0]] = dc[1] if max(vivas[des], default=0.0) >= m.U_min else 0.0
        if self.mando_red is not None:
            self.mando = self.mando_red.paso(est, fuentes_dc, cm)
            v = self.mando.v
            self._Um = (v[self._ia_m] - v[self._ib_m]).tolist()
        self._aparatos(dt, vivas)
        self._motores(dt)

    def _cargas_que_abren(self) -> None:
        """Una bobina cortada o una lámpara fundida (cosim-fallas D2) sale de la red: en el mando,
        R_off en su lugar; en la potencia, con su próxima carga (`_aparatos`). Al repararse vuelve
        la de la entrada (un override vacío es la carga original)."""
        for abre_ahora, cid, en_pot in self._con_carga:
            abre = abre_ahora()
            if abre == (cid in self._abiertas):
                continue
            (self._abiertas.add if abre else self._abiertas.discard)(cid)
            ov = {"R_ohm": R_OFF} if abre else {}
            if self._donde.get(cid) == "m":
                self._cargas_mando[cid] = ov
            elif self._donde.get(cid) == "p" and en_pot:  # el contactor lo pone `_aparatos`
                self.cargas_pot[cid] = ov

    def _firma_potencia(self, est: dict, fuentes: dict) -> tuple:
        """(lo discreto, los números) de lo que entra a la red de potencia en este paso."""
        red = self.pot_red
        disc = [red._valores(est), tuple(sorted(red._cortadas)), tuple(red._cortos),  # sin orden de set
                red.firma_pegados()]
        nums: list = []
        for fid, e in fuentes.items():
            fas = e.get("fasores", {})
            disc.append((fid, tuple(fas)))
            nums += fas.values()
            if "Z_ohm" in e:
                nums.append(e["Z_ohm"])
        for cid, ov in self.cargas_pot.items():
            disc.append((cid, ov.get("modo"), ov.get("R_ohm")))
            nums.append(complex(ov.get("S", ov.get("S_VA", 0.0))))
        return tuple(disc), nums

    @staticmethod
    def _igual(a: tuple, b: tuple | None) -> bool:
        """Misma topología y ningún número movido más que `TOL_POTENCIA` (relativo, piso 1)."""
        if b is None or a[0] != b[0] or len(a[1]) != len(b[1]):
            return False
        return all(abs(x - y) <= TOL_POTENCIA * max(abs(y), 1.0) for x, y in zip(a[1], b[1]))

    def _lineas(self, cid: str | None) -> list[float]:
        c = self.lee(cid)
        return list(c.get("U_lineas_vivas_V") or [c["U_V"]])

    def _corriente(self, en_potencia: bool, rid: str) -> float:
        res = self.pot if en_potencia else self.mando
        return abs(res.corriente(rid)) if res is not None else 0.0

    def _aparatos(self, dt: float, vivas: dict) -> None:
        for _des, m, cid, en_pot in self.contactores:
            m.paso(dt, {"U_bobina_V": abs(self.U(cid))})
            if en_pot:
                self.cargas_pot[cid] = {"S_VA": m.S_mant if m.estado == "cerrado" else m.S_llamada,
                                        **({"R_ohm": R_OFF} if m.abre_su_carga else {})}
        for _des, m, cid in self.pilotos:
            m.paso(dt, {"U_V": abs(self.U(cid))})
        for _des, m, cids in self.valvulas:
            m.paso(dt, {f"U_{lado}": abs(self.U(cid)) for lado, cid in cids.items()})
        for _des, m, ramas in self.protecciones:
            m.paso(dt, {"I_A": [self._corriente(p, rid) for p, rid in ramas]})
        for _des, m in self.mandos:
            m.paso(dt, {})
        for des, m, bornes, alim in self.plcs:
            e = {b: self.U(cid) for b, cid in bornes.items()}
            e["L+"] = self.U(alim)
            e["salidas"] = self.plc_salidas.get(des, {})
            m.paso(dt, e)
        for des, m, alim in self.sensores:
            m.paso(dt, {"detecta": self.detecta.get(des, False), "U_alim_V": self.U(alim)})
        for _des, m, bornes, alim in self.logicos:
            m.paso(dt, {**{b: self.U(cid) for b, cid in bornes.items()}, "U_alim_V": self.U(alim)})
        for des, m, ent, alim, _fid, _dc in self.variadores:
            e = {b: self.U(cid) for b, cid in ent.items()}
            motor = self._motor_de.get(des)  # el que alimentó en el paso anterior
            e["U_red_V"] = vivas[des]
            e["I_motor_A"] = self.modelos[motor].salidas()["I_A"] if motor else 0.0
            m.paso(dt, e)
            if self._en_potencia(alim):
                U_red = max(vivas[des], default=0.0)
                s = SQ3 * U_red * m.I_entrada
                self.cargas_pot[alim] = {"S": complex(s * FP_VARIADOR, s * math.sqrt(1 - FP_VARIADOR ** 2))}

    def _motores(self, dt: float) -> None:
        self._motor_de.clear()
        for des, m, cid in self.motores:
            c = self.lee(cid) if self._en_potencia(cid) else {"U_V": 0.0, "fases": 0}
            fid = self.pot.fuente_de_carga(cid) if self._en_potencia(cid) else None
            U, fases = float(c["U_V"]), int(c["fases"])
            if fid in self._red_ids:
                f = self._red_ids[fid].f
            elif fid in self._vfd_salida:
                vfd = self._vfd_salida[fid]
                f = self._usados[vfd][1]
                self._motor_de[vfd] = des
            else:
                f = 0.0
            if fases < 2:
                U = 0.0
            w, T = self.mec.get(des, (0.0, 0.0))
            n_fases = 2 if fases == 2 else 3
            s = m.paso(dt, {"U_V": U, "f_Hz": f, "omega_salida_rad_s": w, "par_salida_Nm": T, "fases": n_fases})
            self.comandos[des] = m.actuador_fases(U, f, n_fases, w)
            if not self._en_potencia(cid):
                continue
            detenido = abs(s["rpm"]) < FRACCION_EN_MARCHA * m.ns
            if detenido and (fid is None or fid in self._red_ids):
                # rotor bloqueado a la tensión de la red: una impedancia (la caída de tensión del
                # arranque directo sale sola); con la salida de un variador, su curva (V/f)
                S = SQ3 * m.Un * m.Ia_In * m.In * cmath.rect(1.0, math.acos(FP_ROTOR_BLOQUEADO))
                self.cargas_pot[cid] = {"S": S, "modo": "impedancia"}
            else:
                I3 = m.corriente(U, f, s["par_Nm"], s["rpm"])
                S = SQ3 * U * I3 * cmath.rect(1.0, math.acos(m.cos_phi))
                self.cargas_pot[cid] = {"S": S, "modo": "potencia"}

    # ── señales (D10) ───────────────────────────────────────────────────────────────────────

    def senales(self) -> dict:
        out: dict = {}
        for m in self.modelos.values():
            out.update(m.senales())
        return out

    def salidas_por_prefijo(self) -> list[tuple[str, dict]]:
        """[(«-K1.», salidas del modelo)]: lo que las trazas recorren en cada intercambio sin armar
        un dict con todos los nombres de D10."""
        return [(self._prefijos[des], m.publicadas()) for des, m in self.modelos.items()]

    def senales_red(self, extra: set) -> dict:
        """Corriente de cada conductor («-W1.1.I_A») y las tensiones de borne pedidas
        («-K1:A1.U_V»): analógicas, se muestrean a la tasa de las trazas."""
        out: dict = {}
        for res in (self.mando, self.pot):
            if res is None:
                continue
            for n, v in res.senales().items():
                if n.endswith(".I_A") or n in extra:
                    out[n] = v
        return out
