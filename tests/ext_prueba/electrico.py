"""La lectura eléctrica de la extensión falsa (plan puntos-de-extension-entregables, D1): todo sale
de módulos de `extensiones_api.MODULOS` con los nombres que declara (el gate de imports de
`test_extensiones_api.py` lo exige). Es lo que haría una extensión de entregables eléctricos: el
modelo, sus redes, el catálogo, la R y la X de cada conductor y los largos del tablero y del campo.
"""

from __future__ import annotations

from apolo.cosim.red.conductores import TEMPERATURA_DEFECTO_C, reactancia, resistencia
from apolo.library.catalog import CATALOG
from apolo.library.electrico.redes import analizar
from apolo.services.cables_campo import largos as largos_campo
from apolo.services.cables_campo import recorridos
from apolo.services.electrico import modelo
from apolo.services.tablero import largos as largos_tablero
from apolo.services.tablero import ruteos


def resumen(doc) -> dict:
    """Cifras del tablero leídas por la superficie: bajo el lock del llamador."""
    m = modelo(doc)
    r = x = 0.0
    for c in m.conductores:
        if c.seccion_mm2 and c.largo_m:
            r += resistencia(c.seccion_mm2, c.largo_m, TEMPERATURA_DEFECTO_C)
            x += reactancia(c.largo_m)
    tableros = ruteos(doc, m)
    return {"dispositivos": len(m.dispositivos), "conductores": len(m.conductores),
            "redes": len(analizar(m).redes) if m.dispositivos else 0,
            "en_catalogo": sum(1 for d in m.dispositivos if d.ref in CATALOG),
            "r_ohm": round(r, 6), "x_ohm": round(x, 6), "tableros": len(tableros),
            "largos_tablero": len(largos_tablero(tableros)),
            "cables_campo": len(largos_campo(recorridos(doc, m, tableros)))}
