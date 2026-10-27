"""Piezas de forma comunes de los aparatos de tablero (plan aparatos-de-tablero-realistas, D2–D4):
el perfil escalonado, el alojamiento de un borne con su tornillo, la placa de datos, el clip del
riel DIN y las ranuras de ventilación. Las usan los builders de `builders_aparatos.py`.

MARCO (el de la caja del catálogo eléctrico, `ficha_tablero.APOYO_POR_FAMILIA`): centrado en la
envolvente `w` × `d` × `h`; X a lo largo del riel, −Y apoya en el riel o la placa (+Y hacia el
operador), Z arriba. Regla de todas las piezas (D2): NADA sale de la envolvente; el cuerpo la toca
en sus seis caras (o la pieza que la toca es un detalle que llega justo a ella, como la palanca de
un ITM) y lo demás se talla hacia adentro. Así el bbox es exactamente el de la caja y la colocación,
el ruteo y el calentamiento no se mueven.

Cada cota es una fracción de las medidas de la ficha, con un tope en mm donde el detalle tiene un
tamaño propio (un tornillo M3,5 no crece con el aparato); ninguna coordenada es fija. Lo que se
SUMA al cuerpo entra `_SOLAPE` en él (regla de `library/CLAUDE.md`: las partes de un sólido
solapan); lo que se resta asoma `_SOLAPE` fuera de la cara que corta.
"""

from __future__ import annotations

from build123d import Box, Cylinder, Plane, Polygon, Pos, Rotation, extrude

_SOLAPE = 0.5


def caja(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float):
    """Caja alineada por sus límites."""
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def prisma_yz(puntos: list[tuple[float, float]], ancho: float):
    """El perfil `puntos` [(y, z)…] del plano YZ extruido `ancho` centrado en X."""
    perfil = Plane.YZ * Polygon(*puntos, align=None)
    return extrude(perfil, amount=ancho / 2, both=True)


def cilindro_y(x: float, y0: float, y1: float, z: float, d: float):
    """Cilindro Ø`d` de eje Y entre `y0` e `y1`."""
    return Pos(x, (y0 + y1) / 2, z) * (Rotation(90, 0, 0) * Cylinder(d / 2, y1 - y0))


def perfil_modular(w: float, d: float, h: float, *, hombro: float, nariz: float, frente: float):
    """El perfil DIN 43880 de un aparato modular (ITM, fuente): el cuerpo de alto `h` hasta el
    HOMBRO (`hombro` = la y de su cara frontal) y la NARIZ de alto `nariz` hasta `frente`."""
    pts = [(-d / 2, -h / 2), (hombro, -h / 2), (hombro, -nariz / 2), (frente, -nariz / 2),
           (frente, nariz / 2), (hombro, nariz / 2), (hombro, h / 2), (-d / 2, h / 2)]
    return prisma_yz(pts, w)


def bornes_en_hombro(xs, y_cara: float, z_centro: float, alto: float, ancho: float,
                     *, d_tornillo: float):
    """(cortes, tornillos) de una fila de bornes en una cara frontal (`y_cara`): un alojamiento
    `ancho` × `alto` por borne centrado en `z_centro`, con su tornillo de cabeza 1 mm por debajo
    de la cara. La boca del conductor (en la cara de arriba o de abajo) no se talla: no se ve
    desde la puerta y duplicaba las caras del aparato (D3)."""
    prof = min(8.0, 0.9 * alto)
    cortes, tornillos = [], []
    for x in xs:
        cortes.append(caja(x - ancho / 2, x + ancho / 2, y_cara - prof, y_cara + _SOLAPE,
                           z_centro - alto / 2, z_centro + alto / 2))
        tornillos.append(cilindro_y(x, y_cara - prof - _SOLAPE, y_cara - 1.0, z_centro, d_tornillo))
    return cortes, tornillos


def placa_de_datos(x0: float, x1: float, z0: float, z1: float, y_cara: float):
    """(corte, placa) de la placa de datos en una cara frontal (`y_cara`): un rebaje de 0,6 mm
    y la placa de 0,5 que queda 0,1 por debajo de la cara (no coplanar con el cuerpo)."""
    corte = caja(x0, x1, y_cara - 0.6, y_cara + _SOLAPE, z0, z1)
    placa = caja(x0 + 0.2, x1 - 0.2, y_cara - 0.6 - _SOLAPE, y_cara - 0.1, z0 + 0.2, z1 - 0.2)
    return corte, placa


def clip_din(w: float, d: float, h: float):
    """(corte, lengüeta) del clip del riel DIN en la cara de abajo, junto al respaldo: la
    lengüeta que se tira con el destornillador llega justo a la cara (z = −h/2)."""
    ancho = min(w - 1.6, max(0.5 * w, 3.0))
    fondo = min(8.0, 0.18 * d)
    alto = min(3.0, 0.06 * h)
    y0 = -d / 2 + min(4.0, 0.08 * d)
    corte = caja(-ancho / 2, ancho / 2, y0, y0 + fondo, -h / 2 - _SOLAPE, -h / 2 + alto)
    lengueta = caja(-ancho / 2 + 0.4, ancho / 2 - 0.4, y0 + 0.4, y0 + fondo - 0.4, -h / 2,
                    -h / 2 + alto + _SOLAPE)
    return corte, lengueta


def ranuras(x0: float, x1: float, y0: float, y1: float, z_cara: float, *, paso: float = 4.0,
            ancho: float = 1.8, prof: float = 2.0, maximo: int = 6):
    """Ranuras de ventilación a lo largo de X en la cara de ARRIBA (`z_cara`), repartidas entre
    `y0` e `y1` cada `paso` (más separadas si no entran `maximo`: cada ranura son cinco caras
    que se teselan). Sin lugar para una, ninguna. Abajo no van: no se ven (D3)."""
    if y1 - y0 < paso or x1 - x0 < 4:
        return []
    n = min(maximo, int((y1 - y0) // paso))
    paso = (y1 - y0) / n
    z = (z_cara - prof, z_cara + _SOLAPE)
    return [caja(x0, x1, y0 + paso * (k + 0.5) - ancho / 2, y0 + paso * (k + 0.5) + ancho / 2, *z)
            for k in range(n)]


def centros(n: int, ancho: float) -> list[float]:
    """Los centros en X de `n` pasos iguales a lo ancho de `ancho` (centrado)."""
    paso = ancho / n
    return [-ancho / 2 + paso * (k + 0.5) for k in range(n)]


def tallar(cuerpo, cortes: list):
    """El cuerpo menos todos los `cortes` en UNA operación de OCCT."""
    return cuerpo.cut(*cortes) if cortes else cuerpo
