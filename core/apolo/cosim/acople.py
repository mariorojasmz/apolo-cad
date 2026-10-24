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
`Sensor` que detecta con la junta a ± ventana de su punto.
"""

from __future__ import annotations


class AcopleMecanico:
    def __init__(self, integ, motores: list, sensores: list, cilindros=(), reeds=()):
        mj, m = integ.mujoco, integ.m
        self.integ = integ
        act = mj.mjtObj.mjOBJ_ACTUATOR
        self.motores = [(a.designacion, mj.mj_name2id(m, act, a.actuador), integ.juntas[a.junta][1],
                         float(a.signo)) for a in motores]
        self.base = [float(x) for x in m.dof_frictionloss]
        self.atasco: dict[int, float] = {}
        nombres = [s.nombre for s in (integ.snap.sensores or [])]
        self.sensores = [(s.designacion, nombres.index(s.rayo)) for s in sensores]
        self.cilindros = [(c.designacion, mj.mj_name2id(m, act, c.actuador), *integ.juntas[c.junta])
                          for c in cilindros]
        self.reeds = [(r.designacion, integ.juntas[r.junta][0], r.en_mm / 1000.0, r.ventana_mm / 1000.0)
                      for r in reeds]

    def dof(self, junta: str) -> int:
        return self.integ.juntas[junta][1]

    def leer(self) -> tuple[dict, dict]:
        """({motor: (ω, T)} en la salida del reductor, {sensor: detecta}) al final del
        intercambio anterior."""
        d = self.integ.d
        mec = {des: (s * float(d.qvel[dof]), s * float(d.qfrc_actuator[dof]))
               for des, _a, dof, s in self.motores}
        fotos = self.integ.fotos
        det = {des: bool(fotos.estado[k]) for des, k in self.sensores} if fotos else {}
        for des, qa, en, ventana in self.reeds:
            det[des] = abs(float(d.qpos[qa]) - en) <= ventana + 1e-9
        return mec, det

    def lecturas(self) -> dict:
        """{cilindro: (x, v)} de su junta (m, m/s), para la red de aire (D4)."""
        d = self.integ.d
        return {des: (float(d.qpos[qa]), float(d.qvel[dof])) for des, _a, qa, dof in self.cilindros}

    def control(self, comandos: dict, fuerzas: dict | None = None):
        """El `control(d, t)` del `Integrador` para este intercambio."""
        m = self.integ.m
        motores, base, atasco = self.motores, self.base, self.atasco
        cilindros = self.cilindros if fuerzas else ()

        def aplicar(d, _t):
            for des, a, _qa, _dof in cilindros:
                d.ctrl[a] = fuerzas[des]
            con_motor = set()
            for des, a, dof, signo in motores:
                c = comandos[des]
                kv, F = c["kv"], c["forcerange_Nm"]
                m.actuator_gainprm[a, 0] = kv
                m.actuator_biasprm[a, 2] = -kv
                m.actuator_forcerange[a, 0] = -F
                m.actuator_forcerange[a, 1] = F
                d.ctrl[a] = signo * c["ctrl_rad_s"]
                m.dof_frictionloss[dof] = (base[dof] + atasco.get(dof, 0.0)
                                           + (c["friccion_Nm"] if c["k"] == 0.0 else 0.0))
                con_motor.add(dof)
            for dof, par in atasco.items():
                if dof not in con_motor:
                    m.dof_frictionloss[dof] = base[dof] + par

        return aplicar
