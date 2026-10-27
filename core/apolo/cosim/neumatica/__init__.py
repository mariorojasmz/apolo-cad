"""La co-simulación del aire (plan V8.9 D3, D4, D6, D8): puro, sin OCCT ni MuJoCo.

  - `orificio`: el caudal de ISO 6358-1 y la aproximación de los componentes en serie;
  - `camara`: la cámara politrópica y los caminos de aire que la unen a una presión fija;
  - `cilindro`: el cilindro de doble efecto y su acople con MuJoCo por sub-pasos (D4);
  - `valvula`: qué vías une una válvula en cada posición (5/2, 5/3, 3/2, ISO 5599-3);
  - `componentes`: el FRL (la toma regulada) y la válvula de corte con escape;
  - `red`: la topología del circuito (tubos y puertos) y su paso en cada intercambio;
  - `bloqueo`: el bloqueo de vástago por resorte (su cámara de liberación y la sujeción a la junta).

Los modelos de aire (`MODELOS_AIRE`, por `neumatico.modelo.tipo`) son `Modelo` de la
co-simulación: el tablero los arma con la ficha neumática (`modelo["aire"]`) y viven en
`Tablero.modelos` (señales, acciones y fallas como cualquier aparato). La electroválvula es un
modelo ELÉCTRICO (`modelos/electrovalvula.py`, tipo `electrovalvula`): sus bobinas son cargas del
mando y aquí sólo se lee su posición.
"""

from __future__ import annotations

from ..modelos.base import Parametros
from .bloqueo import BloqueoVastago
from .cilindro import Cilindro
from .componentes import Frl, ValvulaCorte

#: `neumatico.modelo.tipo` → modelo de la co-simulación. Los que no están (regulador de caudal,
#: silenciador) son ORIFICIOS en el camino del aire, sin estado: los lee la red.
MODELOS_AIRE = {m.tipo: m for m in (Cilindro, Frl, ValvulaCorte, BloqueoVastago)}


def crear_modelo_aire(designacion: str, ref: str, aire: dict, ajustes: dict | None = None):
    """El modelo de aire de un dispositivo (None si su tipo no tiene estado propio)."""
    clase = MODELOS_AIRE.get((aire or {}).get("tipo"))
    if clase is None:
        return None
    return clase(Parametros(designacion, ref, aire, ajustes))


__all__ = ["MODELOS_AIRE", "BloqueoVastago", "Cilindro", "Frl", "ValvulaCorte", "crear_modelo_aire"]
