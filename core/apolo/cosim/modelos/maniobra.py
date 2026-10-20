"""Contactor y relé de interfaz: la bobina mueve los contactos (plan V8.3 D1, D7).

Máquina de estados con histéresis sobre la tensión de bobina U (valor eficaz o continua):
  - abierto → cerrando cuando U ≥ U_cierre (85 % de Uc en un contactor, IEC 60947-4-1); cierra
    tras `cierre_ms`; si U cae bajo U_caida antes, vuelve a abierto;
  - cerrado → abriendo cuando U < U_caida (~40 % de Uc, criterio de diseño dentro de la banda de
    la norma); abre tras `apertura_ms` (el inducido ya se soltó: termina de abrir);
  - entre U_caida y U_cierre conserva el estado (un contactor cerrado no cae con 60 % de Uc, uno
    abierto no cierra).

Los contactos (NA y NC, potencia y auxiliares) siguen a `cerrado`: mientras abre siguen
cerrados. La corriente de bobina es la de su placa: en DC R = Uc²/P; en AC la de LLAMADA
mientras no ha cerrado y la de MANTENIMIENTO cerrado (|Z| = Uc²/S).

Señales (D10): `-K1.cerrado`, `-K1.estado`, `-K1.I_bobina_A`.
"""

from __future__ import annotations

from .base import EPS_T, Modelo, ModeloIncompleto, Parametros, magnitud


class Contactor(Modelo):
    tipo = "contactor"

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.Uc = p.num("Uc_V", "tensión asignada de la bobina", positivo=True)
        self.Uc_tipo = p.texto("Uc", "tipo de la bobina", ("DC", "AC", "UC"))
        self.u_cierre = p.num("U_cierre_pct", "tensión de cierre en % de Uc", positivo=True) / 100
        self.u_caida = p.num("U_caida_pct", "tensión de caída en % de Uc", positivo=True) / 100
        if self.u_caida >= self.u_cierre:
            raise ModeloIncompleto(f"{p.quien}: la caída ({self.u_caida:.0%}) tiene que ser menor "
                                   f"que el cierre ({self.u_cierre:.0%})")
        self.t_cierre = p.de_banda("cierre_ms", "tiempo de cierre") / 1000
        self.t_apertura = p.de_banda("apertura_ms", "tiempo de apertura") / 1000
        if p.tiene("bobina_W"):
            s = p.num("bobina_W", "consumo de la bobina", positivo=True)
            self.S_llamada = self.S_mant = s
        elif p.tiene("bobina_VA"):
            va = p.mapa("bobina_VA", "potencia de la bobina en VA")
            try:
                self.S_llamada = float(va["llamada"])
                self.S_mant = float(va["mantenimiento"])
            except (KeyError, TypeError, ValueError):
                raise ModeloIncompleto(f"{p.quien}: bobina_VA lleva {{llamada, mantenimiento}} en VA "
                                       f"(llegó {va})") from None
        else:
            raise ModeloIncompleto(f"{p.quien}: falta el consumo de la bobina («bobina_W» en DC o "
                                   "«bobina_VA: {llamada, mantenimiento}» en AC) en electrico.modelo")
        self.estado = "abierto"
        self.t = 0.0
        self.U = 0.0

    @property
    def cerrado(self) -> bool:
        return self.estado in ("cerrado", "abriendo")

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        u = magnitud((entradas or {}).get("U_bobina_V", 0.0))
        self.U = u
        cierra, cae = u >= self.u_cierre * self.Uc - 1e-9, u < self.u_caida * self.Uc
        if self.estado == "abierto" and cierra:
            self.estado, self.t = "cerrando", 0.0
        elif self.estado == "cerrado" and cae:
            self.estado, self.t = "abriendo", 0.0
        if self.estado == "cerrando":
            if cae:
                self.estado = "abierto"
            else:
                self.t += dt
                if self.t >= self.t_cierre - EPS_T:
                    self.estado = "cerrado"
        elif self.estado == "abriendo":
            self.t += dt
            if self.t >= self.t_apertura - EPS_T:
                self.estado = "abierto"
        return self.salidas()

    @property
    def I_bobina_A(self) -> float:
        s = self.S_mant if self.estado == "cerrado" else self.S_llamada
        return self.U * s / (self.Uc * self.Uc)

    def salidas(self) -> dict:
        return {"cerrado": self.cerrado, "estado": self.estado, "I_bobina_A": self.I_bobina_A}


class Rele(Contactor):
    """Relé de interfaz: el mismo modelo con los umbrales y tiempos de su ficha."""

    tipo = "rele"
