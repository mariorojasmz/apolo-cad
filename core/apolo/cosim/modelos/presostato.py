"""El presostato: un contacto que lee la presión de SU línea de aire (plan V8.9 F8, D2).

Eléctricamente es un contacto conmutado sin bobina (en el catálogo, 11 común, 12 NC y 14 NA):
sus caminos los mueve el actuador «señal» (`-BP1.señal`), como la salida de un sensor; el
tablero lo indexa por `LEE_PRESION`, sin rama propia, y el PLC lo lee como cualquier entrada.
La presión la da la red de aire (`cosim/neumatica/red.RedAire.presion_bar`): la de la línea
donde está su puerto 1, manométrica, al empezar cada intercambio.

Conmuta con histéresis, como un presostato mecánico (el fuelle contra el muelle):
  - el NA cierra (`activo`) cuando la presión llega a `p_conmuta_bar` (al subir);
  - vuelve a abrir cuando baja de `p_conmuta_bar − histeresis_bar`;
  - entre los dos umbrales conserva su estado.
`p_conmuta_bar` es un AJUSTE (lo fija el instalador con el tornillo del muelle) dentro del
rango de la ficha neumática; `histeresis_bar` es fijo, de la ficha. Las dos llegan en
`modelo["aire"]`, la ficha `neumatico:` plana que arma el snapshot (`services/cosim_aire.py`).
Sin aire en su línea (corte de aire, o sin tubo) lee la atmósfera: el NA abre. Determinista:
conmuta en el intercambio en que lee la presión que cruza el umbral (`HIPOTESIS`).

Señales: `-BP1.activo` (el NA cerrado) y `-BP1.p_bar` (la presión que lee).
Falla (cosim-fallas D2): `pegado` (el microrruptor soldado o el fuelle trabado): el contacto queda
como está, o como se pida (true = NA cerrado), lea lo que lea; `p_bar` sigue siendo la presión.
"""

from __future__ import annotations

from .base import Modelo, ModeloIncompleto, Parametros, RecolectorAjustes

HIPOTESIS = ("el contacto conmuta en el intercambio en que la presión que lee cruza el umbral "
             "(sin el tiempo de respuesta del microrruptor)")


class Presostato(Modelo):
    tipo = "presostato"
    #: el tablero le da la presión de su línea (`Tablero._aparatos`), no una tensión
    LEE_PRESION = True
    FALLAS = {"pegado": "bool?"}
    pegado: bool | None = None

    def __init__(self, p: Parametros):
        super().__init__(p)
        aire = p.mapa("aire", "la ficha neumática del presostato (la arma el snapshot desde `neumatico:`)")
        a = (RecolectorAjustes if isinstance(p, RecolectorAjustes) else Parametros)(
            p.designacion, p.ref, aire, p.ajustes)
        if isinstance(p, RecolectorAjustes):
            a.faltan = p.faltan  # los ajustes que faltan se juntan con los del modelo (V8.3 F6)
        self.p_on = a.ajustado("p_conmuta_bar", "presión de conmutación que fija el instalador")
        self.histeresis = a.num("histeresis_bar", "histéresis entre conmutación y reposición", positivo=True)
        if self.histeresis >= self.p_on:
            raise ModeloIncompleto(f"{p.quien}: la histéresis ({self.histeresis:g} bar) tiene que ser menor que "
                                   f"la presión de conmutación ({self.p_on:g} bar): si no, nunca repone")
        self.p_off = self.p_on - self.histeresis
        self.hipotesis.append(HIPOTESIS)
        self.p_bar = 0.0
        self.activo = False

    def iniciar(self, p_bar: float | None) -> None:
        """El estado al empezar: la máquina ya con aire (como las cámaras de la red de aire)."""
        self.p_bar = float(p_bar or 0.0)
        self.activo = self.p_bar >= self.p_on - 1e-9

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        self.p_bar = float((entradas or {}).get("p_bar") or 0.0)
        if self.pegado is not None:
            self.activo = self.pegado
        elif self.p_bar >= self.p_on - 1e-9:
            self.activo = True
        elif self.p_bar < self.p_off:
            self.activo = False
        return self.salidas()

    def _falla_pegado(self, valor=None) -> None:
        self.pegado = self._bool(valor, f"{self.designacion}: el presostato pegado", defecto=self.activo)
        self.activo = self.pegado

    def _reparar_pegado(self, _v=None) -> None:
        self.pegado = None

    def salidas(self) -> dict:
        return {"activo": self.activo, "p_bar": self.p_bar}
