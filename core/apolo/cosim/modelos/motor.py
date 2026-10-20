"""Motor de inducción + reductor, del lado eléctrico (plan V8.3 D7, D8).

La curva par–velocidad es Kloss en función de la VELOCIDAD de deslizamiento ω_sl = ωs(f) − ω:

    T = 2·Tk·k / (ω_sl/ω_slk + ω_slk/ω_sl),   k = (Φ/Φn)²,   Φ/Φn = (U/f)/(Un/fn)

con ω_slk = sk·ωs_n constante (V/f: el par máximo y su velocidad de deslizamiento no cambian
con la frecuencia). Así un arranque directo con caída de tensión da k = (U/Un)², el V/f
constante k = 1 en toda su zona y el debilitamiento de campo k = (fn/f)², que es el Tk·(fn/f)²
de V8.2. Sn, sk, Tn y Tk salen de la placa exactamente como en
`library/engineering/motor_induccion.kloss_linealizado` (el test los ata: este paquete no la
importa porque `apolo.library` carga el catálogo y OCCT, y el worker de F4 no debe).

Hacia MuJoCo (D8, en cada intercambio): `actuador(U, f)` da la consigna ωs(f)/i, `kv` = kv_n·k
y el tope ±Tk·k·i·η de la rama estable linealizada, más la fricción del reductor. De vuelta,
`paso` traduce el par en la junta a par y corriente del motor:

    I ≈ I0·φ + (In − I0)·|T|/(Tn·φ)   (zona estable; φ = Φ/Φn)

y en la zona inestable (arranque) interpola hasta Ia·φ a rotor bloqueado.

Señales (D10): `-M1.rpm` y `-M1.par_Nm` (eje del MOTOR), `-M1.I_A`, más `rpm_salida`,
`par_salida_Nm` y `k`.
"""

from __future__ import annotations

import math

from .base import Modelo, ModeloIncompleto, Parametros

#: Fricción del reductor sin tensión (D8, lo decide F2): la pérdida en VACÍO de un reductor
#: (batido de aceite, sellos, rodamientos) como fricción de Coulomb en la junta de salida, el
#: 10 % de su pérdida a plena carga: T_f = 0,1·(1 − η)·Tn·i. Criterio de diseño: las pérdidas
#: de engrane crecen con la carga, así que en vacío queda poco; tomar la de plena carga haría
#: que una parada por inercia terminara antes que en la realidad (del lado inseguro).
FRICCION_VACIO = 0.10

#: Las claves del catálogo → las de la `placa` de V8.2 (`kloss_linealizado`).
_PLACA_V82 = {"P_kW": "potencia_kW", "n_rpm": "rpm", "f_Hz": "frecuencia_hz", "polos": "polos",
              "Tk_Tn": "tk_tn", "J_kgm2": "inercia_rotor_kgm2"}
CONEXIONES = ("triangulo", "estrella")


def placa_v82(modelo: dict) -> dict:
    """El ÚNICO adaptador de las claves del catálogo (`P_kW`, `n_rpm`, `f_Hz`, `Tk_Tn`,
    `J_kgm2`, `polos`) a la `placa` de V8.2 (`potencia_kW`, `rpm`, `frecuencia_hz`, `tk_tn`,
    `inercia_rotor_kgm2`, `polos`). Lo que la placa no trae no se inventa: V8.2 lo supone y lo
    declara como hipótesis."""
    for clave in ("P_kW", "n_rpm"):
        if modelo.get(clave) is None:
            raise ModeloIncompleto(f"placa del motor: falta «{clave}» en electrico.modelo")
    return {v: modelo[k] for k, v in _PLACA_V82.items() if modelo.get(k) is not None}


class Motor(Modelo):
    tipo = "motor"

    def __init__(self, p: Parametros):
        super().__init__(p)
        num = p.num
        self.P = num("P_kW", "potencia de placa", positivo=True) * 1000.0
        U_placa = num("U_V", "tensión de placa en su conexión", positivo=True)
        In_placa = num("In_A", "corriente de placa", positivo=True)
        I0_placa = num("I0_A", "corriente en vacío", positivo=True)
        self.cos_phi = num("cos_phi", "factor de potencia de placa", positivo=True, maximo=1)
        self.eta_motor = num("eta", "rendimiento de placa", positivo=True, maximo=1)
        self.Ia_In = num("Ia_In", "corriente de arranque / In", positivo=True)
        self.Ta_Tn = num("Ta_Tn", "par de arranque / Tn", positivo=True)
        self.Tk_Tn = num("Tk_Tn", "par máximo / Tn", minimo=1.0001)
        self.polos = int(num("polos", "polos", positivo=True))
        self.fn = num("f_Hz", "frecuencia de placa", positivo=True)
        self.nn = num("n_rpm", "velocidad de placa", positivo=True)
        self.J = num("J_kgm2", "inercia del rotor", positivo=True)
        conexion_placa = p.modelo.get("conexion", "triangulo")
        self.conexion = p.texto("conexion", "conexión del motor", CONEXIONES)
        # la tensión del DEVANADO no cambia: en estrella la de línea es √3 veces la de triángulo
        f = {(a, b): 1.0 for a in CONEXIONES for b in CONEXIONES}
        f[("triangulo", "estrella")], f[("estrella", "triangulo")] = math.sqrt(3), 1 / math.sqrt(3)
        escala = f[(conexion_placa, self.conexion)]
        self.Un, self.In, self.I0 = U_placa * escala, In_placa / escala, I0_placa / escala
        if self.I0 >= self.In:
            raise ModeloIncompleto(f"{p.quien}: I0 ({self.I0:g} A) tiene que ser menor que In ({self.In:g} A)")
        self.i = p.ajustado("i", "relación del reductor (ω motor / ω salida)")
        self.eta_red = p.ajustado("eta_reductor", "rendimiento del reductor")
        if not 0 < self.i or not 0 < self.eta_red <= 1:
            raise ModeloIncompleto(f"{p.quien}: i > 0 y 0 < eta_reductor ≤ 1 (llegó {self.i:g}, {self.eta_red:g})")
        self.ns = 120.0 * self.fn / self.polos
        self.sn = (self.ns - self.nn) / self.ns
        if not 0.0 < self.sn < 0.5:
            raise ModeloIncompleto(f"{p.quien}: {self.nn:g} rpm no es coherente con {self.polos} polos "
                                   f"a {self.fn:g} Hz (síncrona {self.ns:g} rpm)")
        lam = self.Tk_Tn
        self.ws_n = 2.0 * math.pi * self.ns / 60.0
        self.Tn = self.P / (2.0 * math.pi * self.nn / 60.0)
        self.Tk = lam * self.Tn
        self.sk = self.sn * (lam + math.sqrt(lam * lam - 1.0))
        self.w_slk = self.sk * self.ws_n
        self.kv_n = 2.0 * self.Tk / (self.sk * self.ws_n) * self.i * self.i * self.eta_red
        self.friccion_Nm = FRICCION_VACIO * (1.0 - self.eta_red) * self.Tn * self.i
        p.hipotesis.append(f"fricción del reductor sin tensión {self.friccion_Nm:.3g} N·m en la salida: "
                           f"{FRICCION_VACIO:.0%} de su pérdida a plena carga (criterio de diseño)")
        self._salidas = {"rpm": 0.0, "par_Nm": 0.0, "I_A": 0.0, "rpm_salida": 0.0,
                         "par_salida_Nm": 0.0, "k": 0.0}

    # ── curva y flujo ────────────────────────────────────────────────────────────────────────

    def flujo(self, U: float, f: float) -> float:
        """Φ/Φn = (U/f)/(Un/fn); 0 sin tensión o sin frecuencia."""
        f = abs(f)
        if U <= 0.0 or f <= 0.0:
            return 0.0
        return (U / f) / (self.Un / self.fn)

    def omega_sinc(self, f: float) -> float:
        """ωs(f) del MOTOR en rad/s, con el signo de f (marcha atrás negativa)."""
        return self.ws_n * f / self.fn

    def par(self, U: float, f: float, rpm: float) -> float:
        """Par del motor (N·m, eje del motor) por Kloss con el flujo real."""
        k = self.flujo(U, f) ** 2
        w_sl = self.omega_sinc(f) - rpm * 2.0 * math.pi / 60.0
        if k == 0.0 or abs(w_sl) < 1e-12:
            return 0.0
        return 2.0 * self.Tk * k / (w_sl / self.w_slk + self.w_slk / w_sl)

    def corriente(self, U: float, f: float, par_Nm: float, rpm: float) -> float:
        """Corriente de línea (A) con el par `par_Nm` del motor a `rpm`."""
        phi = self.flujo(U, f)
        if phi == 0.0:
            return 0.0
        estable = self.I0 * phi + (self.In - self.I0) * abs(par_Nm) / (self.Tn * phi)
        w_sl = abs(self.omega_sinc(f) - rpm * 2.0 * math.pi / 60.0)
        if w_sl <= self.w_slk:
            return estable
        # zona inestable: de la corriente en el par máximo a la de rotor bloqueado (Ia·φ)
        en_tk = self.I0 * phi + (self.In - self.I0) * self.Tk * phi / self.Tn
        bloqueo = self.Ia_In * self.In * phi
        w_bloqueo = abs(self.omega_sinc(f))
        if w_bloqueo <= self.w_slk:
            return en_tk
        frac = min(1.0, (w_sl - self.w_slk) / (w_bloqueo - self.w_slk))
        return en_tk + (bloqueo - en_tk) * frac

    # ── hacia MuJoCo (D8) ────────────────────────────────────────────────────────────────────

    def actuador(self, U: float, f: float) -> dict:
        """Lo que se escribe en el `<velocity>` de MuJoCo en el intercambio: `ctrl` (rad/s en la
        salida), `kv` (N·m·s/rad), `forcerange_Nm` (±) y `friccion_Nm` del reductor."""
        k = self.flujo(U, f) ** 2
        return {"ctrl_rad_s": self.omega_sinc(f) / self.i, "kv": self.kv_n * k,
                "forcerange_Nm": self.Tk * k * self.i * self.eta_red, "friccion_Nm": self.friccion_Nm,
                "k": k}

    # ── de vuelta: par en la junta → par y corriente del motor ───────────────────────────────

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        e = entradas or {}
        U, f = float(e.get("U_V", 0.0)), float(e.get("f_Hz", 0.0))
        w_out = float(e.get("omega_salida_rad_s", 0.0))
        T_out = float(e.get("par_salida_Nm", 0.0))
        rpm = w_out * self.i * 60.0 / (2.0 * math.pi)
        # motorizando el reductor pierde (1 − η) del par del motor; frenando, al revés
        T = T_out / (self.i * self.eta_red) if T_out * w_out >= 0.0 else T_out * self.eta_red / self.i
        I = self.corriente(U, f, T, rpm)
        if int(e.get("fases", 3)) == 2:
            # pérdida de una fase (D15): en marcha sigue con ~√3 de corriente en las otras dos
            # (el par se conserva: cota optimista que F3 revisa con la red fasorial); detenido no
            # arranca, y eso lo da `actuador_fases`
            I *= math.sqrt(3)
        self._salidas = {"rpm": rpm, "par_Nm": T, "I_A": I, "rpm_salida": w_out * 60.0 / (2.0 * math.pi),
                         "par_salida_Nm": T_out, "k": self.flujo(U, f) ** 2}
        return self.salidas()

    def actuador_fases(self, U: float, f: float, fases: int, omega_salida_rad_s: float) -> dict:
        """`actuador` con una fase perdida: un motor detenido (|ω| < 1 % de su ωs) no arranca."""
        a = self.actuador(U, f)
        if fases == 2 and abs(omega_salida_rad_s * self.i) < 0.01 * self.ws_n:
            a.update(kv=0.0, forcerange_Nm=0.0)
        return a

    def salidas(self) -> dict:
        return dict(self._salidas)
