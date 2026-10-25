"""Builders del armado interior de un tablero (plan V8.5, D9): el riel DIN y la canaleta
ranurada. Módulo propio: `builders.py` está congelado por el trinquete de tamaño.

Los dos son CORTABLES a lo largo de Z (como los perfiles: «rotar 90° sobre Y → a lo largo de
X»), con la sección en XY centrada en su caja: X = ancho, Y = alto (lo que sale de la placa:
−Y es la cara que apoya en la placa de montaje, `tablero.apoyo` por familia).

- `din_rail`: riel sombrero TH35 de EN 60715 (35 mm entre bordes, 7,5 o 15 de alto). El alma
  central de 27 mm apoya en la placa; las alas de 35 quedan arriba, donde engancha el aparato.
  Sin los agujeros alargados del perforado (no cambian ningún entregable).
- `canaleta`: canaleta de PVC con su tapa puesta, como tubo rectangular de pared `pared`; las
  ranuras de los dedos no se modelan (el llenado usa `tablero.canaleta.seccion_util_mm2`).
- `panel_puerta` (plan plc-en-el-lazo, D12): un aparato de PUERTA que va en un recorte, como el
  panel de operador: el MARCO (`width` × `height`, `marco` de espesor) queda delante de la puerta
  y el CUERPO (`cuerpo_ancho` × `cuerpo_alto`), menor que el recorte, atraviesa la chapa. Marco
  de la caja del catálogo eléctrico (X ancho, Y fondo, Z alto, centrada): −Y apoya en la puerta
  (lo de detrás) y el marco va en +Y, hacia el operador. No es cortable.
"""

from __future__ import annotations

from build123d import Box, Pos

#: Ancho entre bordes del riel sombrero (EN 60715) y ancho del alma que apoya en la placa.
TH35_ANCHO = 35.0
TH35_ALMA = 27.0
_SOLAPE = 0.5


def din_rail(alto: float, espesor: float = 1.0):
    """Riel TH35 × `alto` (7,5 o 15) de chapa de `espesor`, sección en XY, cortable en Z."""
    if alto not in (7.5, 15, 15.0):
        raise ValueError(f"Riel DIN: alto {alto} fuera de EN 60715 (TH35: 7,5 o 15 mm)")
    if not 0.5 <= espesor <= 2.0:
        raise ValueError(f"Riel DIN: espesor {espesor} fuera de rango (0,5–2 mm)")

    def build(length):
        y0 = -alto / 2.0
        alma = Pos(0, y0 + espesor / 2.0, 0) * Box(TH35_ALMA, espesor, length)
        ala = (TH35_ANCHO - TH35_ALMA) / 2.0 + espesor  # cada ala, desde la cara de la pared
        x_pared = TH35_ALMA / 2.0 - espesor / 2.0
        x_ala = TH35_ANCHO / 2.0 - ala / 2.0
        pieza = alma
        for s in (-1, 1):
            pared = Pos(s * x_pared, 0, 0) * Box(espesor, alto, length)
            borde = Pos(s * x_ala, alto / 2.0 - espesor / 2.0, 0) * Box(ala, espesor, length)
            pieza = pieza + pared + borde
        return pieza

    return build


def canaleta(ancho: float, alto: float, pared: float = 1.5):
    """Canaleta `ancho` × `alto` con tapa, pared `pared` (PVC), sección en XY, cortable en Z."""
    if not (10 <= ancho <= 150 and 10 <= alto <= 150):
        raise ValueError(f"Canaleta: sección {ancho}×{alto} fuera de la serie (10–150 mm)")
    if not 0.5 <= pared < min(ancho, alto) / 4.0:
        raise ValueError(f"Canaleta: pared {pared} no cabe en {ancho}×{alto}")

    def build(length):
        exterior = Box(ancho, alto, length)
        interior = Box(ancho - 2 * pared, alto - 2 * pared, length + 2 * _SOLAPE)
        return exterior - interior

    return build


def panel_puerta(width: float, depth: float, height: float, cuerpo_ancho: float, cuerpo_alto: float,
                 marco: float):
    """Marco `width` × `height` × `marco` en +Y y cuerpo `cuerpo_ancho` × `cuerpo_alto` hasta −Y,
    centrado en su caja `width` × `depth` × `height` (un solo sólido: solapan `_SOLAPE`)."""
    if not (0 < cuerpo_ancho < width and 0 < cuerpo_alto < height):
        raise ValueError(f"Panel de puerta: el cuerpo {cuerpo_ancho}×{cuerpo_alto} tiene que ser menor que "
                         f"el marco {width}×{height}")
    if not 0 < marco < depth:
        raise ValueError(f"Panel de puerta: el marco de {marco} mm no cabe en el fondo de {depth} mm")
    largo = depth - marco + _SOLAPE
    frente = Pos(0, depth / 2.0 - marco / 2.0, 0) * Box(width, marco, height)
    cuerpo = Pos(0, -depth / 2.0 + largo / 2.0, 0) * Box(cuerpo_ancho, largo, cuerpo_alto)
    pieza = frente + cuerpo
    return lambda _length=None: pieza


BUILDERS = {"din_rail": din_rail, "canaleta": canaleta, "panel_puerta": panel_puerta}
