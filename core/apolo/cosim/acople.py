"""El acople eléctrico ↔ mecánico en cada intercambio (plan V8.3 D8).

Hacia MuJoCo, por motor (lo calcula `Motor.actuador_fases` con la U y la f de sus bornes):
  - `ctrl = ωs(f)/i` con el signo de marcha de la junta (D7);
  - ganancia del `<velocity>`: `kv` de V8.2 × k, con k = (Φ/Φn)² (la pendiente de Kloss escala
    con el flujo; F0 corrigió el (U/Un)² del borrador);
  - `forcerange = ±Tk·k·i·η` (sin tensión k = 0: el eje queda libre);
  - fricción de la junta = la de la petición + la del reductor SIN tensión (F2: 10 % de su
    pérdida a plena carga, sólo con k = 0) + la de un `atasco`.
De vuelta: ω y el par del actuador (`qfrc_actuator`) en la salida del reductor, y el estado de
cada fotocelda. Co-simular exige motor POR PLACA: con la fuente ideal de V8.2 el MJCF sale con
`forcelimited="false"` y el tope no se podría escribir (lo garantiza el snapshot).

El `atasco` es fricción seca en la junta (`dof_frictionloss`, implícita en MuJoCo), no un par
explícito en `qfrc_applied`: retenido un intercambio, un par que se opone a ω cambia de signo
cerca de ω = 0 y la junta vibra en vez de trabarse.

Cilindros (V8.9 D4): la posición y la velocidad de su junta prismática van a la red de aire
(`lecturas`) y su fuerza MEDIA vuelve al `<motor>` de la junta; la fricción de los sellos ya está
en el MJCF (`frictionloss` de la junta, la pone el snapshot). Un detector magnético (D8) es un
`Sensor` que detecta con la junta a ± ventana de su punto. El bloqueo de vástago (plan
bloqueo-de-vastago D4) suma su sujeción a esa fricción, como el atasco del motor: `frenos`
({cilindro: N}) sólo con bloqueos; sin ellos la fricción de la junta no se toca. Mientras muerde,
la restricción de fricción de esa junta se ENDURECE (`SOLREF_BLOQUEO`, `SOLIMP_BLOQUEO`): con la de
MuJoCo por defecto (20 ms, d 0,95) la fricción seca es blanda y el vástago bajo la retención se
arrastraba a ~40 mm/s (medido en el banco del bloqueo); al soltar vuelve la de la junta.

Motor a una junta PRISMÁTICA (plan motor-a-eje-lineal D2): el actuador vive en el eje de salida y
MuJoCo lo lleva a la junta con su `gear` (= 1/r, leído del modelo: una sola fuente). ω = gear·v y
T = F/gear vuelven al modelo del motor como en una junta de giro; la fricción del reductor sin
tensión y un `atasco` (N·m en el eje) llegan a la junta como F = T·gear. Una transmisión
IRREVERSIBLE (D5) retiene la junta sin tensión con fricción seca igual al tope nominal del motor,
endurecida como el bloqueo (si no, la carga se arrastra). Sin transmisión gear = 1: lo de siempre.
"""

from __future__ import annotations


#: La restricción de fricción de la junta de un vástago mordido por su bloqueo (criterio de
#: simulación, plan bloqueo-de-vastago D4): constante de tiempo 2 ms (≥ 2·Δt de 1 ms) y amortiguamiento
#: crítico; impedancia 0,9995 (el arrastre residual escala con 1 − d: < 0,1 mm/s bajo la retención).
SOLREF_BLOQUEO = (0.002, 1.0)
SOLIMP_BLOQUEO = (0.9995, 0.9995, 0.001, 0.5, 2.0)


class AcopleMecanico:
    def __init__(self, integ, motores: list, sensores: list, cilindros=(), reeds=()):
        mj, m = integ.mujoco, integ.m
        self.integ = integ
        act = mj.mjtObj.mjOBJ_ACTUATOR
        topes = {md.nombre: md.fuerza_max or 0.0 for md in (getattr(integ.snap, "motores", None) or [])}
        self.motores = []
        for a in motores:
            ia = mj.mj_name2id(m, act, a.actuador)
            gear = float(m.actuator_gear[ia, 0])
            # D5: la retención de una transmisión irreversible, en la junta (N), sólo sin tensión
            reten = topes.get(a.actuador, 0.0) * gear if getattr(a, "irreversible", False) else 0.0
            self.motores.append((a.designacion, ia, integ.juntas[a.junta][1], float(a.signo), gear, reten))
        self.gear_dof = {dof: g for _d, _a, dof, _s, g, _r in self.motores if g != 1.0}
        self.base = [float(x) for x in m.dof_frictionloss]
        self.base_solref = [tuple(float(v) for v in r) for r in m.dof_solref]
        self.base_solimp = [tuple(float(v) for v in r) for r in m.dof_solimp]
        self.solref_bloqueo = (max(SOLREF_BLOQUEO[0], 2.0 * float(m.opt.timestep)), SOLREF_BLOQUEO[1])
        self.atasco: dict[int, float] = {}
        nombres = [s.nombre for s in (integ.snap.sensores or [])]
        self.sensores = [(s.designacion, nombres.index(s.rayo)) for s in sensores]
        self.cilindros = [(c.designacion, mj.mj_name2id(m, act, c.actuador), *integ.juntas[c.junta])
                          for c in cilindros]
        self.reeds = [(r.designacion, integ.juntas[r.junta][0], r.en_mm / 1000.0, r.ventana_mm / 1000.0)
                      for r in reeds]

    def dof(self, junta: str) -> int:
        return self.integ.juntas[junta][1]

    def friccion_de(self, junta: str, par_Nm: float) -> float:
        """La fricción seca en la junta de un par en el eje (`atasco`): en una prismática movida
        por un motor con transmisión, F = T·gear (N); si no, el número tal cual."""
        return par_Nm * self.gear_dof.get(self.dof(junta), 1.0)

    def leer(self) -> tuple[dict, dict]:
        """({motor: (ω, T)} en la salida del reductor, {sensor: detecta}) al final del
        intercambio anterior."""
        d = self.integ.d
        mec = {des: (s * float(d.qvel[dof]) * g, s * float(d.qfrc_actuator[dof]) / g)
               for des, _a, dof, s, g, _r in self.motores}
        fotos = self.integ.fotos
        det = {des: bool(fotos.estado[k]) for des, k in self.sensores} if fotos else {}
        for des, qa, en, ventana in self.reeds:
            det[des] = abs(float(d.qpos[qa]) - en) <= ventana + 1e-9
        return mec, det

    def lecturas(self) -> dict:
        """{cilindro: (x, v)} de su junta (m, m/s), para la red de aire (D4)."""
        d = self.integ.d
        return {des: (float(d.qpos[qa]), float(d.qvel[dof])) for des, _a, qa, dof in self.cilindros}

    def control(self, comandos: dict, fuerzas: dict | None = None, frenos: dict | None = None):
        """El `control(d, t)` del `Integrador` para este intercambio."""
        m = self.integ.m
        motores, base, atasco = self.motores, self.base, self.atasco
        cilindros = self.cilindros if fuerzas else ()
        frenos = frenos or None

        def aplicar(d, _t):
            for des, a, _qa, dof in cilindros:
                d.ctrl[a] = fuerzas[des]
                if frenos is not None and des in frenos:  # la sujeción del bloqueo: fricción seca
                    F = frenos[des]
                    m.dof_frictionloss[dof] = base[dof] + F
                    m.dof_solref[dof] = self.solref_bloqueo if F > 0.0 else self.base_solref[dof]
                    m.dof_solimp[dof] = SOLIMP_BLOQUEO if F > 0.0 else self.base_solimp[dof]
            con_motor = set()
            for des, a, dof, signo, gear, reten in motores:
                c = comandos[des]
                kv, F = c["kv"], c["forcerange_Nm"]
                m.actuator_gainprm[a, 0] = kv
                m.actuator_biasprm[a, 2] = -kv
                m.actuator_forcerange[a, 0] = -F
                m.actuator_forcerange[a, 1] = F
                d.ctrl[a] = signo * c["ctrl_rad_s"]
                suelto = c["k"] == 0.0
                m.dof_frictionloss[dof] = (base[dof] + atasco.get(dof, 0.0)
                                           + (c["friccion_Nm"] * gear if suelto else 0.0))
                if reten:  # D5: sin tensión el sinfín no se deja arrastrar (sólo irreversibles)
                    if suelto:
                        m.dof_frictionloss[dof] += reten
                    m.dof_solref[dof] = self.solref_bloqueo if suelto else self.base_solref[dof]
                    m.dof_solimp[dof] = SOLIMP_BLOQUEO if suelto else self.base_solimp[dof]
                con_motor.add(dof)
            for dof, par in atasco.items():
                if dof not in con_motor:
                    m.dof_frictionloss[dof] = base[dof] + par

        return aplicar
