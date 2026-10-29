"""Los puntos de la SALIDA de un motorreductor (plan puerta-sin-sobrediseno, F3b punto 6): donde
un eje que gira entra o sale de su caja gira el cubo del reductor (el eje hueco).

Por cada par motorreductor ↔ eje de `library/seguridad/transmision_rigida.pares_salida`: rayos
paralelos al eje a `radio + 3 mm` de su línea (el cubo, no el eje), en cuatro lados, contra los
sólidos del MOTORREDUCTOR solo; la cara de la caja es el último cruce hacia cada lado y el punto
queda 1 mm afuera. Así la cara es la REAL (no la caja del motor, que con la carcasa del motor
cruzada al eje sobresale del reductor). Sin cruce en un lado (el rayo no toca la caja) no hay
punto de ese lado.

Lee shapes: el llamador sostiene `STATE_LOCK`. Sin `Document`.
"""

from __future__ import annotations

from apolo.library.seguridad.transmision_rigida import (
    PUNTO_FUERA_MM,
    RADIO_EXTRA_MM,
    pares_salida,
    peligro_salida,
)


def _puntos(tr, redondo, caja_motor, caja_eje=None) -> list[tuple]:
    """Los puntos de la salida. Un lado cuenta sólo si lo que gira SALE de la caja por esa cara
    (`caja_eje` pasa de ella hacia afuera): el eje macizo de un motorreductor coaxial sale por la
    caja reductora y no por la tapa del ventilador (plantilla-rodillos-cadena E19: 27 sondas
    juzgaban la tapa cerrada del ventilador); el eje hueco pasante sale por las dos."""
    k = redondo.eje
    otros = [a for a in range(3) if a != k]
    largo = caja_motor[1][k] - caja_motor[0][k] + 40.0
    rad = redondo.radio + RADIO_EXTRA_MM
    out = []
    for a in otros:
        for s in (1.0, -1.0):
            base = list(redondo.centro)
            base[a] += s * rad
            for sentido in (1.0, -1.0):  # hacia +k y hacia −k, desde más allá de la caja
                o = list(base)
                o[k] = (caja_motor[0][k] - 20.0) if sentido > 0 else (caja_motor[1][k] + 20.0)
                d = [0.0, 0.0, 0.0]
                d[k] = sentido
                cruces = tr.todos(tuple(o), tuple(d), largo)
                if not cruces:
                    continue
                t = cruces[0][0]  # el primer cruce desde afuera = la cara de ese lado
                cara = o[k] + sentido * t
                if caja_eje is not None and (
                        caja_eje[0][k] > cara - PUNTO_FUERA_MM if sentido > 0
                        else caja_eje[1][k] < cara + PUNTO_FUERA_MM):
                    continue  # por esta cara no sale nada que gire
                q = list(o)
                q[k] = o[k] + sentido * (t - PUNTO_FUERA_MM)
                out.append(tuple(q))
    return out


def peligros_de_salida(dc: dict, cuerpos: list[set[str]]) -> list[dict]:
    """Los peligros de salida de motorreductor (con sus objetivos) de los cuerpos que giran."""
    from .calidad_sondas import Trazador

    piezas, out = dc["piezas"], []
    for motor, eje, cuerpo in pares_salida(piezas, cuerpos):
        tr = Trazador({motor: dc["solidos"].get(motor, [])})
        puntos = _puntos(tr, piezas[eje].redondo, piezas[motor].caja, piezas[eje].caja)
        if puntos:
            out.append(peligro_salida(motor, eje, cuerpo, puntos, piezas))
    return out
