"""Modelos de dispositivo de la co-simulación: uno por `electrico.modelo.tipo` (plan V8.3 D7).

`crear_modelo(designacion, ref, modelo, ajustes)` instancia el de una ref del tablero con el
`modelo` de su ficha y los `ajustes` de su `add_device`; una ref sin `tipo` es pasiva (borne,
conductor, gabinete, contactos auxiliares que siguen a su aparato) y da None. Un parámetro que
falta es `ModeloIncompleto` con qué completar y dónde: nunca un valor inventado.

Cada modelo avanza con `paso(dt, entradas) -> salidas` y expone `senales()` con los nombres de
D10. Puro y sin MuJoCo ni OCCT: no importa nada de `apolo` fuera de este paquete
(`tests/test_capas_cosim.py`); el worker de F4 lo carga sin la geometría.
"""

from __future__ import annotations

from .alimentacion import Fuente, Red
from .base import Modelo, ModeloIncompleto, Parametros, entrada_tipo1
from .maniobra import Contactor, Rele
from .mandos import Piloto, Pulsador, Selector, Seccionador, Sensor, Seta
from .motor import Motor, placa_v82
from .plc_es import PlcES, direccion_iec
from .protecciones import Fusible, Guardamotor, Itm, ReleTermico
from .variador import Variador

#: tipo → clase. `library/electrico/ficha.TIPOS_MODELO` valida el YAML con la misma lista.
MODELOS: dict[str, type[Modelo]] = {m.tipo: m for m in (
    Red, Fuente, Seccionador, Itm, Guardamotor, ReleTermico, Fusible, Contactor, Rele, PlcES,
    Variador, Motor, Pulsador, Seta, Selector, Piloto, Sensor)}


def crear_modelo(designacion: str, ref: str, modelo: dict | None, ajustes: dict | None = None,
                 *, cantidad: int = 1) -> Modelo | None:
    """El modelo de un dispositivo, o None si la ref es pasiva (sin `tipo`). `cantidad` = las
    unidades de una bornera (un portafusible de n bornes son n cartuchos)."""
    tipo = (modelo or {}).get("tipo")
    if tipo is None:
        return None
    clase = MODELOS.get(tipo)
    if clase is None:
        raise ModeloIncompleto(f"{designacion} ({ref}): no hay modelo para el tipo «{tipo}»; "
                               f"tipos: {', '.join(sorted(MODELOS))}")
    p = Parametros(designacion, ref, modelo, ajustes)
    return clase(p, cantidad) if clase is Fusible else clase(p)


__all__ = ["MODELOS", "Contactor", "Fuente", "Fusible", "Guardamotor", "Itm", "Modelo",
           "ModeloIncompleto", "Motor", "Parametros", "Piloto", "PlcES", "Pulsador", "Red", "Rele",
           "ReleTermico", "Seccionador", "Selector", "Sensor", "Seta", "Variador", "crear_modelo",
           "direccion_iec", "entrada_tipo1", "placa_v82"]
