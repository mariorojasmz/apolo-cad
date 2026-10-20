"""Variador de frecuencia, modelo PROMEDIO (plan V8.3 D1, D7; marco V8 D3).

No se simula la conmutación de los IGBT: el variador entrega una tensión V/f y una frecuencia
que siguen sus rampas, y lo que manda es su programación (el `modelo` de la ref, ajustable en
`add_device`). En cada paso, en este orden:
  1. entradas de 24 V (DI1–DI4, S1/S2) con los umbrales de IEC 61131-2 tipo 1;
  2. red: subtensión con el motor girando más allá de la retención → falla `subtension`; una
     tensión de línea bajo la mitad de las otras → falla `perdida_fase` tras su tiempo;
  3. corriente del motor (la del intercambio anterior): ≥ `I_sobrecorriente` → falla
     `sobrecorriente` en el acto; la imagen I²t de la sobrecarga de placa → falla `sobrecarga`;
  4. rearme (flanco de la DI `rearme` o la acción) borra la falla;
  5. STO: sin 24 V en S1 o S2 durante `STO_reaccion_ms` → sin par (salida a 0, el motor gira
     libre); al volver hace falta una orden de marcha NUEVA (flanco), igual tras una falla;
  6. consigna: frecuencia fija por los bits de las DI, o AI1 escalada a f_min–f_max, o `fija`;
  7. rampa hacia la consigna (o hacia 0 sin marcha) con `acel_s`/`decel_s` de 0 a f_max; con
     I ≥ I_límite la frecuencia BAJA con la rampa de deceleración (no sube);
  8. salida V/f: U = U_V·|f|/f_base hasta f_base, nunca más que la red.

Señales (D10): `-T1.f_Hz` (con signo: negativa = atrás), `-T1.estado`, `-T1.falla`, más
`U_V`, `par_habilitado`, `sto`, `rele_falla`, `limitando`, `I_entrada_A`, `termico_pct`.
"""

from __future__ import annotations

import math

from .base import EPS_T, Modelo, ModeloIncompleto, Parametros, decaimiento, entrada_tipo1

FUNCIONES_DI = ("marcha_adelante", "marcha_atras", "rearme", "f_fija_b0", "f_fija_b1", "ninguna")
CONSIGNAS = ("AI1", "fija")
DIS = ("DI1", "DI2", "DI3", "DI4")
#: Sobrecarga I²t: imagen térmica de primer orden que dispara en θ ≥ 1,1²; τ se calcula para
#: que la sobrecarga de placa (150 % durante 60 s) dispare justo en su tiempo partiendo de
#: régimen nominal (θ = 1); desde frío tarda más (criterio de diseño: la placa dice el punto,
#: no la forma de la curva).
_SOBRECARGA_K2 = 1.1 ** 2


class Variador(Modelo):
    tipo = "variador"
    ACCIONES = ("rearmar",)

    def __init__(self, p: Parametros):
        super().__init__(p)
        n = p.num
        self.In = n("I_salida_A", "corriente de salida asignada", positivo=True)
        self.I_entrada_n = n("I_entrada_A", "corriente de entrada a potencia nominal", positivo=True)
        self.P = n("P_kW", "potencia asignada", positivo=True) * 1000.0
        self.Un = n("U_V", "tensión asignada de salida (la de la red)", positivo=True)
        self.f_min = n("f_min_Hz", "frecuencia mínima", minimo=0)
        self.f_max = n("f_max_Hz", "frecuencia máxima", positivo=True)
        self.f_base = n("f_base_Hz", "frecuencia base del V/f", positivo=True)
        if self.f_min >= self.f_max:
            raise ModeloIncompleto(f"{p.quien}: f_min_Hz ({self.f_min:g}) < f_max_Hz ({self.f_max:g})")
        self.acel = n("acel_s", "rampa de aceleración de 0 a f_max", positivo=True)
        self.decel = n("decel_s", "rampa de deceleración de f_max a 0", positivo=True)
        self.consigna = p.texto("consigna", "origen de la consigna", CONSIGNAS)
        self.AI_max = n("AI1_V_max", "tensión de AI1 a f_max", positivo=True)
        self.f_consigna = n("f_consigna_Hz", "consigna fija", minimo=0)
        self.funcion = {di: p.texto(f"{di}_funcion", f"función de la entrada {di}", FUNCIONES_DI) for di in DIS}
        self.f_fijas = [n(f"f_fija{k}_Hz", f"frecuencia fija {k}", minimo=0) for k in (1, 2, 3)]
        self.I_lim = n("I_limite_pct", "límite de corriente en % de I_salida", positivo=True) / 100 * self.In
        self.I_oc = n("I_sobrecorriente_pct", "falla por sobrecorriente en % de I_salida", positivo=True) / 100 * self.In
        x = n("sobrecarga_pct", "sobrecarga admitida en % de I_salida", positivo=True) / 100
        t = n("sobrecarga_s", "tiempo de la sobrecarga admitida", positivo=True)
        if x * x <= _SOBRECARGA_K2:
            raise ModeloIncompleto(f"{p.quien}: sobrecarga_pct tiene que pasar de 110 %")
        self.tau_sc = t / math.log((x * x - 1.0) / (x * x - _SOBRECARGA_K2))
        self.tiene_sto = p.booleano("STO", "entrada de seguridad STO")
        self.t_sto = n("STO_reaccion_ms", "tiempo de reacción del STO", minimo=0) / 1000 if self.tiene_sto else 0.0
        self.U_min = n("U_min_pct", "subtensión de red en % de U_V", positivo=True) / 100 * self.Un
        self.t_ret = n("t_retencion_ms", "retención ante un hueco de red", minimo=0) / 1000
        self.t_fase = n("t_perdida_fase_s", "tiempo para la falla por pérdida de fase", minimo=0)
        # estado
        self.f = 0.0
        self.falla = ""
        self.di = {di: False for di in DIS}
        self.s = [False, False]
        self.theta = 0.0  # frío
        self.t_sto_abierto = 0.0
        self.sto = False
        self.t_sin_red = 0.0
        self.t_desbalance = 0.0
        self.esperar_flanco = False
        self.rearme_previo = False
        self.limitando = False
        self.U = 0.0
        self.I_entrada = 0.0
        self.sin_red = False

    # ── helpers ──────────────────────────────────────────────────────────────────────────────

    def _di_de(self, funcion: str) -> bool:
        return any(self.di[d] for d in DIS if self.funcion[d] == funcion)

    def _consigna_Hz(self, ai1_v: float) -> float:
        b = (1 if self._di_de("f_fija_b0") else 0) + (2 if self._di_de("f_fija_b1") else 0)
        if b:
            f = self.f_fijas[b - 1]
        elif self.consigna == "AI1":
            frac = min(1.0, max(0.0, ai1_v / self.AI_max))
            f = self.f_min + (self.f_max - self.f_min) * frac
        else:
            f = self.f_consigna
        return min(self.f_max, max(self.f_min, f))

    def _fallar(self, causa: str) -> None:
        if not self.falla:
            self.falla = causa
            self.f = 0.0

    @property
    def par_habilitado(self) -> bool:
        return not self.falla and not self.sto and not self.sin_red and self.f != 0.0

    # ── paso ─────────────────────────────────────────────────────────────────────────────────

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        e = entradas or {}
        for di in DIS:
            self.di[di] = entrada_tipo1(float(e.get(di, 0.0)), self.di[di])
        u_red = e.get("U_red_V", 0.0)
        lineas = [abs(float(u)) for u in u_red] if isinstance(u_red, (list, tuple)) else [abs(float(u_red))]
        U_red = max(lineas)
        I = abs(float(e.get("I_motor_A", 0.0)))
        girando = self.f != 0.0
        # 2. red
        if U_red < self.U_min:
            self.t_sin_red += dt
            if girando and self.t_sin_red >= self.t_ret - EPS_T:
                self._fallar("subtension")
        else:
            self.t_sin_red = 0.0
        self.sin_red = U_red < self.U_min and self.t_sin_red >= self.t_ret - EPS_T
        if len(lineas) == 3 and girando and min(lineas) < 0.5 * U_red:
            self.t_desbalance += dt
            if self.t_desbalance >= self.t_fase - EPS_T:
                self._fallar("perdida_fase")
        else:
            self.t_desbalance = 0.0
        # 3. corriente
        if I >= self.I_oc:
            self._fallar("sobrecorriente")
        x = I / self.In
        self.theta = x * x + (self.theta - x * x) * decaimiento(dt, self.tau_sc)
        if self.theta >= _SOBRECARGA_K2:
            self._fallar("sobrecarga")
        # 4. rearme (flanco)
        rearme = self._di_de("rearme") or bool(e.get("rearmar"))
        if rearme and not self.rearme_previo and self.falla:
            self.falla = ""
            self.esperar_flanco = True
        self.rearme_previo = rearme
        # 5. STO
        if self.tiene_sto:
            self.s = [entrada_tipo1(float(e.get(c, 0.0)), prev) for c, prev in zip(("S1", "S2"), self.s)]
            if all(self.s):
                self.t_sto_abierto = 0.0
                self.sto = False
            else:
                self.t_sto_abierto += dt
                if self.t_sto_abierto >= self.t_sto - EPS_T:
                    if not self.sto:
                        self.esperar_flanco = True
                    self.sto = True
                    self.f = 0.0
        # 6. marcha
        adelante, atras = self._di_de("marcha_adelante"), self._di_de("marcha_atras")
        marcha = adelante != atras
        if self.esperar_flanco and not (adelante or atras):
            self.esperar_flanco = False
        bloqueado = bool(self.falla) or self.sto or self.sin_red or self.esperar_flanco
        objetivo = 0.0
        if marcha and not bloqueado:
            objetivo = self._consigna_Hz(float(e.get("AI1", 0.0))) * (1.0 if adelante else -1.0)
        # 7. rampa
        self.limitando = False
        if bloqueado and (self.falla or self.sto or self.sin_red):
            self.f = 0.0  # salida apagada: el motor gira libre
        else:
            sube, baja = self.f_max / self.acel * dt, self.f_max / self.decel * dt
            if I >= self.I_lim and self.f != 0.0:
                self.limitando = True
                self.f = math.copysign(max(0.0, abs(self.f) - baja), self.f)
            elif objetivo * self.f < 0.0:  # cambio de sentido: primero baja a 0
                self.f = math.copysign(max(0.0, abs(self.f) - baja), self.f)
            elif abs(objetivo) > abs(self.f):
                self.f = math.copysign(min(abs(objetivo), abs(self.f) + sube), objetivo)
            else:
                self.f = math.copysign(max(abs(objetivo), abs(self.f) - baja), self.f) if self.f else 0.0
            if abs(self.f) < 1e-9:
                self.f = 0.0
        # 8. salida
        self.U = min(U_red, self.Un * min(1.0, abs(self.f) / self.f_base)) if self.par_habilitado else 0.0
        self.I_entrada = self.I_entrada_n * (self.U * I) / (self.Un * self.In) if self.par_habilitado else 0.0
        return self.salidas()

    @property
    def estado(self) -> str:
        if self.falla:
            return "falla"
        if self.sto:
            return "sto"
        if self.sin_red:
            return "sin_red"
        if self.limitando:
            return "limitando"
        if self.f == 0.0:
            return "parado"
        return "marcha"

    def salidas(self) -> dict:
        return {"f_Hz": self.f, "U_V": self.U, "estado": self.estado, "falla": self.falla,
                "rele_falla": bool(self.falla), "sto": self.sto, "par_habilitado": self.par_habilitado,
                "limitando": self.limitando, "I_entrada_A": self.I_entrada,
                "termico_pct": 100.0 * self.theta / _SOBRECARGA_K2}

    def _accion_rearmar(self, _valor=None) -> None:
        if self.falla:
            self.falla = ""
            self.esperar_flanco = True
