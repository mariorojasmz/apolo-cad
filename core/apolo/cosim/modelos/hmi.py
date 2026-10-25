"""Panel de operador (plan plc-en-el-lazo, D12): la pantalla táctil de la puerta del tablero.

Para la co-simulación es lo que la red le ve: se ENCIENDE con la tensión de su alimentación
(L+ → M) ≥ `U_min_V` de su ficha y se apaga por debajo. Lo que dibuja y lo que escribe al PLC
no es del núcleo (una extensión de la UI pinta la pantalla, F1d2, y escribe variables con la
acción `escribir`, D10); el modelo publica su resolución en `pantalla_px` para que la UI arme
la textura del tamaño de la ficha. Su consumo no carga la red de mando: como la alimentación de
un PLC, la carga de 24 VDC va sin modelo de consumo (`services/cosim_red`, hipótesis declarada).

Señal (D10): `-P1.encendida`.

Falla (cosim-fallas D2), `apagada`: la pantalla no enciende aunque tenga tensión (la fuente
interna o la retroiluminación muertas); reparada, vuelve a encender si hay tensión.

`SOLO_ALIMENTACION`: el tablero (`cosim/tablero.py`) le pasa sólo `U_alim_V`, la tensión de su
carga de alimentación; no mueve contactos ni lee entradas.
"""

from __future__ import annotations

from .base import Modelo, ModeloIncompleto, Parametros


class Hmi(Modelo):
    tipo = "hmi"
    FALLAS = {"apagada": ""}
    #: el tablero le pasa sólo la tensión de su alimentación (`U_alim_V`)
    SOLO_ALIMENTACION = True
    apagada = False

    def __init__(self, p: Parametros):
        super().__init__(p)
        self.U_min = p.num("U_min_V", "tensión mínima de alimentación con que enciende", positivo=True)
        ancho = p.num("ancho_px", "resolución horizontal de la pantalla", positivo=True)
        alto = p.num("alto_px", "resolución vertical de la pantalla", positivo=True)
        if not (ancho.is_integer() and alto.is_integer()):
            raise ModeloIncompleto(f"{p.quien}: la resolución va en píxeles enteros (llegó {ancho:g}×{alto:g})")
        #: [ancho, alto] en píxeles: la tabla del `inicio` de la sesión viva (`vivo_fotograma.py`)
        self.pantalla_px = (int(ancho), int(alto))
        self.encendida = False

    def paso(self, dt: float, entradas: dict | None = None) -> dict:
        u = float((entradas or {}).get("U_alim_V", 0.0))
        self.encendida = u >= self.U_min - 1e-9 and not self.apagada
        return self.salidas()

    def _falla_apagada(self, _v=None) -> None:
        self.apagada = True
        self.encendida = False

    def _reparar_apagada(self, _v=None) -> None:
        self.apagada = False

    def salidas(self) -> dict:
        return {"encendida": self.encendida}
