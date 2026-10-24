"""El cilindro neumático de doble efecto en la co-simulación (plan V8.9 D3, D4, D7).

Lo que hace el aire (`intercambio`) y lo que publica (D7: `-MM1.x_mm`, `-MM1.v_m_s`,
`-MM1.pA_bar`, `-MM1.pB_bar` manométricos, `-MM1.F_N`). La mecánica es de MuJoCo: el vástago es
la junta prismática de `create_pneumatic_cylinder` y la fuerza llega por un `<motor>` sobre ella.

**El acople (D4, medido en la F0).** En cada intercambio (2 ms) las dos cámaras avanzan en
`SUB_PASOS` = 8 sub-pasos de 0,25 ms (Euler explícito) con la posición del pistón EXTRAPOLADA de
la última lectura de MuJoCo, x(τ) = x + v·τ + ½·a·τ² (a de los dos últimos intercambios), y a
MuJoCo va la fuerza MEDIA de esos sub-pasos. Integrar las cámaras una vez por intercambio oscila
con volumen muerto chico (+2,3 % de carrera, +10 % de consumo) y la rigidez linealizada en el
actuador se volvió inestable (Alternativas del plan).

**El pistón**: F = pA·A − pB·A_anular − p_atm·a_vástago. La fricción de los sellos NO va aquí: es
Coulomb en la junta (`frictionloss`, implícita en MuJoCo: la lección del atasco de V8.3), con la
`friccion_N` de la ficha o la `friccion_pct` de la fuerza teórica de avance a la presión de
trabajo, declarada como hipótesis. El fin de carrera es el tope de la junta: la posición
extrapolada se recorta a [0, carrera] (la amortiguación se VERIFICA, no se simula: D3, D9).

Sólo doble efecto en esta versión (el catálogo no trae simple efecto con muelle).
Puro: `cosim.modelos.base` y `cosim.neumatica`.
"""

from __future__ import annotations

import math

from ..modelos.base import Modelo, ModeloIncompleto, Parametros
from .camara import N_POLITROPICO, caudal_entrante, dpdt
from .orificio import P_ATM_PA

#: Sub-pasos de las cámaras por intercambio (D4: 8 de 0,25 ms en uno de 2 ms).
SUB_PASOS = 8
_BAR = 1e5


class Cilindro(Modelo):
    tipo = "cilindro"

    def __init__(self, p: Parametros):
        super().__init__(p)
        efecto = p.texto("efecto", "doble efecto o simple efecto con muelle", ("doble", "simple_muelle"))
        if efecto != "doble":
            raise ModeloIncompleto(f"{p.quien}: la co-simulación de V8.9 simula cilindros de DOBLE efecto "
                                   "(el de simple efecto con muelle necesita la fuerza del muelle en su ficha)")
        D = p.num("D_mm", "Ø del pistón", positivo=True) / 1000.0
        d = p.num("d_mm", "Ø del vástago", positivo=True) / 1000.0
        self.A = math.pi * D * D / 4.0
        self.a_vastago = math.pi * d * d / 4.0
        self.A_anular = self.A - self.a_vastago
        self.carrera = p.num("carrera_mm", "carrera (la de la junta del cilindro en 3D)", positivo=True) / 1000.0
        self.V0_A = p.num("V_muerto_A_cm3", "volumen muerto de la cámara A", minimo=0.0) * 1e-6
        self.V0_B = p.num("V_muerto_B_cm3", "volumen muerto de la cámara B", minimo=0.0) * 1e-6
        self.masa_base = p.num("masa_movil_base_kg", "masa móvil en carrera 0", positivo=True)
        self.friccion_N = p.num("friccion_N", "fricción de los sellos", minimo=0.0) if p.tiene("friccion_N") else None
        self.friccion_pct = (p.num("friccion_pct", "fricción en % de la fuerza teórica", minimo=0.0)
                             if self.friccion_N is None else None)
        if self.friccion_N is None and self.friccion_pct is None:
            raise ModeloIncompleto(f"{p.quien}: la ficha declara `friccion_N` o `friccion_pct` (D3)")
        self.n = N_POLITROPICO
        self.pA = self.pB = P_ATM_PA
        self.x = self.v = self.F = 0.0
        self._v_previa: float | None = None
        self.V_tubo_A = self.V_tubo_B = 0.0   # los pone la red de aire (D3)

    def sellos_N(self, p_trabajo_Pa: float) -> float:
        """La fricción de Coulomb de los sellos en la junta (N), con su hipótesis la primera vez."""
        if self.friccion_N is not None:
            return self.friccion_N
        F = self.friccion_pct / 100.0 * max(p_trabajo_Pa - P_ATM_PA, 0.0) * self.A
        texto = (f"fricción de los sellos = {self.friccion_pct:g} % de la fuerza teórica de avance a "
                 f"{(p_trabajo_Pa - P_ATM_PA) / _BAR:g} bar = {F:.1f} N (Coulomb en la junta)")
        if texto not in self.hipotesis:
            self.hipotesis.append(texto)
        return F

    def fuerza(self, pA: float, pB: float) -> float:
        return pA * self.A - pB * self.A_anular - P_ATM_PA * self.a_vastago

    def volumenes(self, x: float) -> tuple[float, float]:
        return (self.V0_A + self.V_tubo_A + self.A * x,
                self.V0_B + self.V_tubo_B + self.A_anular * (self.carrera - x))

    def intercambio(self, dt: float, x: float, v: float, caminos_A: list, caminos_B: list,
                    n_sub: int = SUB_PASOS) -> float:
        """Avanza las cámaras un intercambio desde la lectura (x, v) de MuJoCo (m, m/s) y
        devuelve la fuerza MEDIA (N) para el intercambio que viene. El aire que entra desde la
        toma se anota en `camino.toma.acumular(kg)`."""
        a = 0.0 if self._v_previa is None else (v - self._v_previa) / dt
        self._v_previa = v
        self.x, self.v = x, v
        h = dt / n_sub
        L = self.carrera
        pA, pB = self.pA, self.pB
        suma = 0.0
        tomas: list = [c.toma for c in caminos_A] + [c.toma for c in caminos_B]
        masas = [0.0] * len(tomas)
        for i in range(n_sub):
            tau = i * h
            xi = x + v * tau + 0.5 * a * tau * tau
            vi = v + a * tau
            if xi <= 0.0:
                xi, vi = 0.0, max(vi, 0.0)
            elif xi >= L:
                xi, vi = L, min(vi, 0.0)
            VA, VB = self.volumenes(xi)
            qA, qsA = caudal_entrante(caminos_A, pA)
            qB, qsB = caudal_entrante(caminos_B, pB)
            pA = max(pA + h * dpdt(pA, VA, qA, self.A * vi, self.n), 1.0)
            pB = max(pB + h * dpdt(pB, VB, qB, -self.A_anular * vi, self.n), 1.0)
            for k, q in enumerate(qsA + qsB):
                masas[k] += q * h
            suma += self.fuerza(pA, pB)
        for k, t in enumerate(tomas):
            if t is not None:
                t.acumular(masas[k])   # neto (la toma lo cierra ≥ 0 por intercambio)
        self.pA, self.pB = pA, pB
        self.F = suma / n_sub
        return self.F

    def salidas(self) -> dict:
        return {"x_mm": self.x * 1000.0, "v_m_s": float(self.v), "pA_bar": (self.pA - P_ATM_PA) / _BAR,
                "pB_bar": (self.pB - P_ATM_PA) / _BAR, "F_N": float(self.F)}

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        """El cilindro no avanza con el tablero: lo mueve `intercambio` (la red de aire)."""
        return self.salidas()
