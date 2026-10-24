"""El FRL y la válvula de corte en la co-simulación (plan V8.9 D3, D7).

**FRL (filtro-regulador).** La toma de la máquina es una fuente IDEAL a la presión de red que
declara el escenario (`condiciones.presion_red_bar`; el compresor y la red de planta no se
modelan, D3). El FRL la regula: aguas abajo hay una fuente a min(p_red, p_regulada) detrás de su
conductancia (C, b) de ficha, en serie con lo que sigue (`orificio.serie`). `p_regulada_bar` es
un AJUSTE (lo fija el instalador: `add_device.ajustes`). Señales (D7): `-AZ1.p_bar` (la regulada
que entrega, manométrica), `-AZ1.Q_Nl_min` (el caudal medio del último intercambio, NL/min ANR)
y `-AZ1.consumo_NL` (acumulado). El regulador se supone de alivio y sin antirretorno: con la
toma sin aire (`corte_de_aire`) la línea se descarga por ella (`HIPOTESIS_FRL`).

**Válvula de corte con escape** (ISO 4414): abierta une 1→2; cerrada bloquea 1 y descarga 2→3
(con escape) o bloquea 2 (sin escape). Manual en el catálogo: `abrir` / `cerrar` como acciones
del escenario (arranca ABIERTA: la máquina en servicio, como el seccionador). Señal:
`-QM1.abierta`.

Puro: `cosim.modelos.base`.
"""

from __future__ import annotations

from ..modelos.base import Modelo, ModeloIncompleto, Parametros
from .orificio import M_ELIPTICO, P_ATM_PA, anr_l

_BAR = 1e5
HIPOTESIS_FRL = ("regulador de alivio sin antirretorno: sin aire en la toma, la línea aguas abajo "
                 "se descarga por ella")


def via(p: Parametros, clave: str, que: str) -> tuple:
    """(C, b, m) de un bloque de caudal ISO 6358 de la ficha plana (`services/cosim_aire`)."""
    c = p.mapa(clave, que)
    try:
        C, b = float(c["C"]), float(c["b"])
        m = float(c.get("m", M_ELIPTICO))
    except (KeyError, TypeError, ValueError):
        raise ModeloIncompleto(f"{p.quien}: «{clave}» ({que}) es {{C, b, m}} de ISO 6358 (llegó {c})") from None
    if not C > 0 or not 0 <= b < 1:
        raise ModeloIncompleto(f"{p.quien}: «{clave}» con C > 0 y b en [0, 1) (llegó C = {C:g}, b = {b:g})")
    return (C, b, m)


class Toma:
    """La cuenta del aire que entrega una toma (el FRL o la entrada sin él). Se cuenta el NETO de
    cada intercambio, y si sale negativo (una cámara comprimida devuelve aire a la línea, que el
    regulador alivia) cuenta cero: cerca del equilibrio el caudal de ISO 6358 va y viene en
    cantidades ínfimas entre sub-pasos, y sumar sólo lo que entra inventaría un consumo."""

    def __init__(self):
        self.masa = 0.0          # kg netos en el intercambio en curso
        self.total = 0.0         # kg desde t = 0
        self.Q_Nl_min = 0.0

    def acumular(self, kg: float) -> None:
        self.masa += kg

    def cerrar(self, dt: float) -> None:
        neto = max(self.masa, 0.0)
        self.total += neto
        self.Q_Nl_min = anr_l(neto) / dt * 60.0
        self.masa = 0.0


class Frl(Modelo):
    tipo = "frl"

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.p_regulada = p.ajustado("p_regulada_bar", "presión de salida que fija el instalador") * _BAR + P_ATM_PA
        self.via = via(p, "caudal", "caudal ISO 6358 de entrada a salida")
        self.toma = Toma()
        self.p_red = P_ATM_PA    # la pone la red de aire en cada intercambio

    @property
    def p_salida(self) -> float:
        return min(self.p_red, self.p_regulada)

    def salidas(self) -> dict:
        return {"p_bar": (self.p_salida - P_ATM_PA) / _BAR, "Q_Nl_min": float(self.toma.Q_Nl_min),
                "consumo_NL": anr_l(self.toma.total)}

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        return self.salidas()


class ValvulaCorte(Modelo):
    tipo = "valvula_corte"
    ACCIONES = ("abrir", "cerrar")

    def __init__(self, p: Parametros):
        super().__init__(p)
        acc = p.texto("accionamiento", "qué la acciona", ("electrico", "neumatico", "manual", "mecanico"))
        if acc != "manual":
            raise ModeloIncompleto(f"{p.quien}: la co-simulación de V8.9 simula la válvula de corte MANUAL "
                                   f"(llegó «{acc}»)")
        self.con_escape = p.booleano("con_escape", "si descarga aguas abajo al cerrar")
        self.via = via(p, "caudal", "caudal ISO 6358 de 1 a 2")
        self.abierta = True

    def _accion_abrir(self, _v=None) -> None:
        self.abierta = True

    def _accion_cerrar(self, _v=None) -> None:
        self.abierta = False

    def salidas(self) -> dict:
        return {"abierta": self.abierta}

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        return self.salidas()
