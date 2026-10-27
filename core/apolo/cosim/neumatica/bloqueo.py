"""El bloqueo de vástago en la co-simulación (plan bloqueo-de-vastago D4, D5).

Una unidad de sujeción por RESORTE que el aire libera (ficha `neumatico:` de tipo
`bloqueo_vastago`, plana en `modelo["aire"]`; `cilindro` lo agrega `services/cosim_aire.py` desde
el `servicio.bloqueo` del cilindro que muerde).

**La cámara de liberación** es de volumen FIJO (`V_liberacion_cm3` de la ficha + los tubos de su
línea) y avanza con la MISMA politrópica, los mismos caminos de ISO 6358 y los mismos sub-pasos
que una cámara del cilindro (`camara.py`, D4 de V8.9): la 3/2 que la libera la une a la
alimentación (energizada) o al escape por su vía 3 y lo que cuelgue de ella (en reposo). El
retardo del bloqueo sale de ese escape, no de una cifra de ficha (ninguna la publica).

**La sujeción**: F(p) = F_ret · (1 − p / p_lib), recortada a [0, F_ret], con p manométrica y p_lib
la presión mínima de liberación: el muelle contra el pistón de liberación, lineal entre las dos
cifras de la ficha (`HIPOTESIS_RECTA`). Las mordazas entran cuando la presión lleva
`t_mecanico_ms` por debajo de p_lib (`HIPOTESIS_MECANICO`) y salen en el acto al volver.

**A MuJoCo** va como fricción de Coulomb en la junta del vástago (`frenos()` → `dof_frictionloss`
en `AcopleMecanico.control`, sobre la de los sellos): la lección del atasco de V8.3 (un par
explícito vibra en v = 0). Con la fuerza neumática bajo F la junta se traba; encima, desliza.

Señales: `p_bar`, `F_N` (la sujeción que aplica), `bloqueado` (mordazas cerradas), `desliza`
(bloqueado y |F neumática| > F + sellos) y `sobrerrecorrido_mm` (lo que anduvo el vástago desde que
mordió por última vez: el dato que la ficha pide medir en la puesta en marcha).

Puro: `cosim.modelos.base` y `cosim.neumatica`.
"""

from __future__ import annotations

from ..modelos.base import Modelo, ModeloIncompleto, Parametros
from .camara import N_POLITROPICO, caudal_entrante, dpdt
from .orificio import P_ATM_PA

_BAR = 1e5
HIPOTESIS_RECTA = ("bloqueo de vástago: sujeción F = F_ret·(1 − p/p_lib) entre 0 y la presión mínima de "
                   "liberación (el muelle contra el pistón, lineal: la ficha sólo da los dos extremos)")
HIPOTESIS_MECANICO = "bloqueo de vástago: las mordazas cierran {t:g} ms después de que la liberación baja de p_lib"


class BloqueoVastago(Modelo):
    tipo = "bloqueo_vastago"

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.F_ret = p.num("F_retencion_N", "fuerza de retención estática", positivo=True)
        self.p_lib = p.num("p_liberacion_min_bar", "presión mínima de liberación", positivo=True)
        self.V = p.num("V_liberacion_cm3", "volumen de la cámara de liberación", positivo=True) * 1e-6
        self.t_mec = p.num("t_mecanico_ms", "retardo de las mordazas", minimo=0.0) / 1000.0
        if not p.booleano("normalmente_bloqueado", "si bloquea sin presión"):
            raise ModeloIncompleto(f"{p.quien}: la co-simulación simula bloqueos POR RESORTE (normalmente "
                                   "bloqueados): uno que bloquea con aire no es un bloqueo de seguridad")
        if not p.tiene("cilindro"):
            raise ModeloIncompleto(f"{p.quien}: ningún cilindro lo declara; pon en el servicio de su cilindro "
                                   f'{{"bloqueo": "{p.designacion}"}} (plan bloqueo-de-vastago D2)')
        self.cilindro = str(p.modelo["cilindro"])
        self.hipotesis += [HIPOTESIS_RECTA, HIPOTESIS_MECANICO.format(t=self.t_mec * 1000.0),
                           "bloqueo de vástago: la sujeción es fricción seca en la junta del vástago (la de MuJoCo, "
                           "endurecida a 2 ms y d = 0,9995 mientras muerde: `cosim/acople.py`)"]
        self.V_tubo = 0.0          # lo pone la red de aire
        self.p = P_ATM_PA
        self.F = 0.0
        self.bloqueado = False
        self.desliza = False
        self._bajo_s = 0.0         # tiempo con la liberación bajo p_lib
        self._x_mordida: float | None = None
        self.sobrerrecorrido = 0.0

    def iniciar(self, p_Pa: float) -> None:
        """La máquina ya con aire: la presión de lo que su válvula en reposo le une; si muerde,
        muerde desde el principio (sin el retardo)."""
        self.p = p_Pa
        self.F = self.sujecion(p_Pa)
        self.bloqueado = self.F > 0.0
        self._bajo_s = self.t_mec if self.bloqueado else 0.0

    def sujecion(self, p_Pa: float) -> float:
        g = (p_Pa - P_ATM_PA) / _BAR
        return self.F_ret * min(max(1.0 - g / self.p_lib, 0.0), 1.0)

    def intercambio(self, dt: float, caminos: list, x: float, F_cil: float, sellos_N: float,
                    n_sub: int = 8) -> float:
        """Avanza la cámara de liberación un intercambio y devuelve la sujeción (N) que va a la
        junta en el intercambio que viene. `x` es la posición del vástago (m), `F_cil` la fuerza
        neumática media del cilindro en este intercambio y `sellos_N` su fricción."""
        h = dt / n_sub
        p, V = self.p, self.V + self.V_tubo
        masas = [0.0] * len(caminos)
        for _ in range(n_sub):
            q, qs = caudal_entrante(caminos, p)
            p = max(p + h * dpdt(p, V, q, 0.0, N_POLITROPICO), 1.0)
            for k, qi in enumerate(qs):
                masas[k] += qi * h
        for k, c in enumerate(caminos):
            if c.toma is not None:
                c.toma.acumular(masas[k])
        self.p = p
        F = self.sujecion(p)
        if F > 0.0:
            self._bajo_s += dt
        else:
            self._bajo_s = 0.0
        cerrado = F > 0.0 and self._bajo_s >= self.t_mec - 1e-12
        if cerrado and not self.bloqueado:
            self._x_mordida = x
        self.bloqueado = cerrado
        self.F = F if cerrado else 0.0
        if cerrado and self._x_mordida is not None:
            self.sobrerrecorrido = abs(x - self._x_mordida) * 1000.0
        self.desliza = cerrado and abs(F_cil) > self.F + sellos_N
        return self.F

    def salidas(self) -> dict:
        return {"p_bar": (self.p - P_ATM_PA) / _BAR + 0.0, "F_N": float(self.F), "bloqueado": self.bloqueado,
                "desliza": self.desliza, "sobrerrecorrido_mm": float(self.sobrerrecorrido)}

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        """No avanza con el tablero: lo mueve `intercambio` (la red de aire)."""
        return self.salidas()
