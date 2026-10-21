"""Las E/S del PLC compacto: el hardware que rodea al programa (plan V8.3 D1, D4, D7).

El programa (ST compilado, `apolo.plc`) corre en el planificador (F4); este modelo es lo que
hay entre los bornes y su imagen de proceso:
  - entradas digitales tipo 1 (IEC 61131-2: ON ≥ 15 V, OFF ≤ 5 V, entre medio conserva) con el
    filtro de entrada `DI_filtro_ms`: un cambio cuenta sólo si dura el filtro entero;
  - entradas analógicas 0–10 V → 0–27648 (`AI_escala`, D4, como S7), saturadas en el rango;
  - salidas a transistor con su retardo de conmutación (`DO_retardo_ms`);
  - alimentación: bajo `U_alim_min_V` (IEC 61131-2: 24 VDC − 15 %) el PLC no corre y las
    salidas caen.

Direcciones IEC (D4): el borne `I0.0` es `%IX0.0`, el `Q0.0` es `%QX0.0` y la analógica `AIk`
es `%IWk`. Señales (D10): `-A1.%IX0.0`, `-A1.%QX0.0`, `-A1.%IW0` y `-A1.alimentado`.
"""

from __future__ import annotations

from .base import EPS_T, Modelo, ModeloIncompleto, Parametros, entrada_tipo1


def bornes_digitales(prefijo: str, n: int) -> list[str]:
    """«I0.0 … I0.7, I1.0 …»: 8 bits por byte, como los bornes del catálogo."""
    return [f"{prefijo}{k // 8}.{k % 8}" for k in range(n)]


def direccion_iec(borne: str) -> str:
    """Borne del PLC → dirección IEC directa (D4): I0.0 → %IX0.0, Q0.0 → %QX0.0, AI0 → %IW0."""
    if borne.startswith("AI"):
        return f"%IW{borne[2:]}"
    if borne[:1] in ("I", "Q"):
        return f"%{borne[0]}X{borne[1:]}"
    raise ValueError(f"«{borne}» no es una E/S del PLC")


class PlcES(Modelo):
    tipo = "plc"

    def __init__(self, p: Parametros):
        super().__init__(p)
        n_di = int(p.num("DI", "entradas digitales", minimo=0))
        n_do = int(p.num("DO", "salidas digitales", minimo=0))
        n_ai = int(p.num("AI", "entradas analógicas", minimo=0))
        self.filtro = p.num("DI_filtro_ms", "filtro de las entradas digitales", minimo=0) / 1000
        self.retardo = p.num("DO_retardo_ms", "retardo de conmutación de las salidas", minimo=0) / 1000
        self.U_min = p.num("U_alim_min_V", "alimentación mínima", positivo=True)
        self.escala = int(p.num("AI_escala", "cuenta de la analógica a fondo de escala", positivo=True))
        self.DO_A = p.num("DO_A", "corriente máxima por salida", positivo=True)
        rango = p.modelo.get("AI_V")
        if not (isinstance(rango, (list, tuple)) and len(rango) == 2):
            raise ModeloIncompleto(f"{p.quien}: falta «AI_V» (rango de las analógicas, [0, 10]) en electrico.modelo")
        self.AI_lo, self.AI_hi = float(rango[0]), float(rango[1])
        self.DI = bornes_digitales("I", n_di)
        self.DO = bornes_digitales("Q", n_do)
        self.AI = [f"AI{k}" for k in range(n_ai)]
        self.crudo = {b: False for b in self.DI}       # el nivel en el borne (tipo 1)
        self.imagen = {b: False for b in self.DI}      # lo que lee el programa (filtrado)
        self.t_cambio = {b: 0.0 for b in self.DI}
        self.analog = {b: 0 for b in self.AI}
        self.salida = {b: False for b in self.DO}
        self.t_salida = {b: 0.0 for b in self.DO}
        self.alimentado = False
        #: las direcciones IEC de cada borne, una vez (las salidas se piden en cada intercambio)
        self._dir = {b: direccion_iec(b) for b in self.DI + self.AI + self.DO}

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        """`entradas`: la tensión de cada borne respecto de su común («I0.0»: 24.0, «AI0»: 5.0), la
        alimentación «L+» (V) y `salidas` {«Q0.0»: bool} que pide el programa."""
        e = entradas or {}
        self.alimentado = float(e.get("L+", 0.0)) >= self.U_min
        for b in self.DI:
            self.crudo[b] = entrada_tipo1(float(e.get(b, 0.0)), self.crudo[b])
            if self.crudo[b] != self.imagen[b]:
                self.t_cambio[b] += dt
                if self.t_cambio[b] >= self.filtro - EPS_T:
                    self.imagen[b], self.t_cambio[b] = self.crudo[b], 0.0
            else:
                self.t_cambio[b] = 0.0
        for b in self.AI:
            u = min(self.AI_hi, max(self.AI_lo, float(e.get(b, 0.0))))
            self.analog[b] = int(round((u - self.AI_lo) / (self.AI_hi - self.AI_lo) * self.escala))
        pedidas = e.get("salidas") or {}
        for b in self.DO:
            quiere = bool(pedidas.get(b, False)) and self.alimentado
            if quiere != self.salida[b]:
                self.t_salida[b] += dt
                if self.t_salida[b] >= self.retardo - EPS_T:
                    self.salida[b], self.t_salida[b] = quiere, 0.0
            else:
                self.t_salida[b] = 0.0
        return self.salidas()

    def salidas(self) -> dict:
        d = self._dir
        out: dict = {"alimentado": self.alimentado}
        for tabla in (self.imagen, self.analog, self.salida):
            for b, v in tabla.items():
                out[d[b]] = v
        return out
