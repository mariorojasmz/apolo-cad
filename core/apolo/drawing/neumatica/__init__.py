"""El esquema neumático ISO 1219 (plan V8.9 F5, D11): símbolos de ISO 1219-1 (`valvulas`,
`equipos`, `mandos`, sobre el lápiz de `trazo`), el plan de la composición por reglas de
ISO 1219-2 (`circuito`), su dibujo y sus líneas (`composicion`, `rutas`) y la lámina (`lamina`).
Recibe datos puros (`CircuitoAire`); quien lee el documento es `services/neumatica_esquema.py`."""

from .circuito import Aparato, CircuitoAire, Detector
from .lamina import lamina_neumatica

__all__ = ["Aparato", "CircuitoAire", "Detector", "lamina_neumatica"]
