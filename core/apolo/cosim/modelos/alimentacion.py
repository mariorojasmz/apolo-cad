"""La red de suministro y la fuente de 24 VDC (plan V8.3 D1, D7, D15).

Red (`tipo: red`): fuente fasorial ideal detrás de su impedancia de cortocircuito. El sistema
decide los polos y sus fasores (D15):
  - 3F: L1 L2 L3 a U/√3 y 0°, −120°, +120° (U es la de línea); 3F+N agrega N en 0;
  - 2F: L1 L2 de una red trifásica sin neutro (L1–L2 = U);
  - 1F+N: L a U y 0°, N en 0.
Zk = Un/(√3·Icc) por fase en los sistemas de fases (IEC 60909-0 con c = 1); en 1F+N la del
lazo U/Icc se reparte mitad en L y mitad en N. R y X salen de `X_R`. Los eventos del mundo
(D12) son acciones: `cortar`, `reconectar`, `perder_fase` / `reponer_fase` (un polo), `caida`
(factor de tensión) y `restaurar`.

Fuente (`tipo: fuente`): salida U_salida_V mientras su entrada esté dentro de rango; al cortar
la entrada sostiene la salida `t_retencion_ms` (D12 `caida_de_red`); al pedirle más de su
límite limita a corriente constante (`modo_limite`: la tensión baja como en una carga
resistiva, U = Un·I_lím/I_pedida) y se recupera sola al bajar la carga.

Señales (D10): `-G1.conectada`, `-G1.U_V`; `-T1.U_V`, `-T1.I_A`, `-T1.limitando`, `-T1.ok`.
"""

from __future__ import annotations

import cmath
import math

from .base import EPS_T, Modelo, ModeloIncompleto, Parametros, magnitud

SISTEMAS = {"1F+N": ("L", "N"), "2F": ("L1", "L2"), "3F": ("L1", "L2", "L3"),
            "3F+N": ("L1", "L2", "L3", "N")}
_ANG = {"L1": 0.0, "L2": -120.0, "L3": 120.0}
MODOS_LIMITE = ("corriente_constante",)


class Red(Modelo):
    tipo = "red"
    ACCIONES = ("cortar", "reconectar", "perder_fase", "reponer_fase", "caida", "restaurar")

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.sistema = p.texto("sistema", "sistema de la red", tuple(SISTEMAS))
        self.Un = p.num("U_V", "tensión nominal (de línea, o fase–neutro en 1F+N)", positivo=True)
        self.f = p.num("f_Hz", "frecuencia", positivo=True)
        icc = p.num("Icc_kA", "corriente de cortocircuito presunta en bornes", positivo=True) * 1000.0
        xr = p.num("X_R", "relación X/R de la red", positivo=True)
        if self.sistema == "1F+N":
            z = self.Un / icc / 2.0
        else:
            z = self.Un / (math.sqrt(3) * icc)
        r = z / math.sqrt(1.0 + xr * xr)
        self.Z = complex(r, r * xr)
        if p.modelo.get("Icc_supuesta"):
            p.hipotesis.append(f"Icc = {icc / 1000:g} kA SUPUESTA en el catálogo: verificar con la distribuidora")
        self.polos = SISTEMAS[self.sistema]
        self.conectada = True
        self.perdidas: set[str] = set()
        self.factor = 1.0

    def fasores(self) -> dict:
        """Fasor (V, complejo) de cada polo activo; un polo perdido o la red cortada, ausente."""
        if not self.conectada:
            return {}
        out: dict = {}
        for polo in self.polos:
            if polo in self.perdidas:
                continue
            if polo == "N":
                out[polo] = 0j
            elif self.sistema == "1F+N":
                out[polo] = complex(self.Un * self.factor, 0.0)
            else:
                out[polo] = cmath.rect(self.Un * self.factor / math.sqrt(3), math.radians(_ANG[polo]))
        return out

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        return self.salidas()

    def salidas(self) -> dict:
        activa = self.conectada and not self.perdidas
        return {"conectada": self.conectada, "U_V": self.Un * self.factor if self.conectada else 0.0,
                "fases_ok": activa, "fasores": self.fasores(), "Z_ohm": self.Z}

    def _accion_cortar(self, _v=None) -> None:
        self.conectada = False

    def _accion_reconectar(self, _v=None) -> None:
        self.conectada = True

    def _accion_perder_fase(self, polo) -> None:
        if polo not in self.polos or polo == "N":
            raise ValueError(f"{self.designacion}: «{polo}» no es una fase de la red {self.sistema} "
                             f"({', '.join(x for x in self.polos if x != 'N')})")
        self.perdidas.add(polo)

    def _accion_reponer_fase(self, polo) -> None:
        """Vuelve una fase perdida (el fin de un `corte_de_fase` con duración, D12)."""
        self.perdidas.discard(polo)

    def _accion_caida(self, factor) -> None:
        factor = float(factor)
        if not 0.0 <= factor <= 1.2:
            raise ValueError(f"{self.designacion}: la caída es un factor de tensión entre 0 y 1,2 (llegó {factor:g})")
        self.factor = factor

    def _accion_restaurar(self, _v=None) -> None:
        self.conectada, self.perdidas, self.factor = True, set(), 1.0


class Fuente(Modelo):
    tipo = "fuente"

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.Un = p.num("U_salida_V", "tensión de salida", positivo=True)
        self.In = p.num("I_salida_A", "corriente de salida asignada", positivo=True)
        self.I_lim = p.num("I_limite_pct", "límite de corriente en % de I_salida", positivo=True) / 100 * self.In
        if self.I_lim < self.In:
            raise ModeloIncompleto(f"{p.quien}: I_limite_pct tiene que ser ≥ 100 %")
        self.modo = p.texto("modo_limite", "comportamiento al llegar al límite", MODOS_LIMITE)
        self.t_ret = p.num("t_retencion_ms", "retención ante un corte de la entrada", minimo=0) / 1000
        self.U_in_min = p.num("U_entrada_min_V", "tensión de entrada mínima", positivo=True)
        self.eta = p.num("eta", "rendimiento", positivo=True, maximo=1)
        self.t_sin_entrada = 0.0
        self.U = 0.0
        self.I = 0.0
        self.limitando = False

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        e = entradas or {}
        if magnitud(e.get("U_entrada_V", 0.0)) >= self.U_in_min:
            self.t_sin_entrada = 0.0
            ok = True
        else:
            self.t_sin_entrada += dt
            ok = self.t_sin_entrada < self.t_ret - EPS_T
        pedida = max(0.0, float(e.get("I_carga_A", 0.0)))  # lo que la carga tomaría a la nominal
        if not ok:
            self.U, self.I, self.limitando = 0.0, 0.0, False
        elif pedida > self.I_lim:
            self.U, self.I, self.limitando = self.Un * self.I_lim / pedida, self.I_lim, True
        else:
            self.U, self.I, self.limitando = self.Un, pedida, False
        return self.salidas()

    @property
    def ok(self) -> bool:
        """DC OK: salida ≥ 90 % de Un (criterio de diseño: el orden del umbral del contacto DC OK
        de la línea)."""
        return self.U >= 0.9 * self.Un

    def salidas(self) -> dict:
        return {"U_V": self.U, "I_A": self.I, "limitando": self.limitando, "ok": self.ok,
                "P_entrada_W": self.U * self.I / self.eta}
