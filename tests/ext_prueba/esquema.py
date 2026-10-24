"""Una lámina de ESQUEMA de la extensión falsa con los trazos del núcleo (plan
puntos-de-extension-entregables, F2): `drawing.esquema` da el círculo y el polígono de símbolo y el
punto de unión; el núcleo no sabe de símbolos, así que los de aquí son de prueba (una extensión
real dibuja los suyos). La misma lámina, en SVG, es la que muestra el panel ancho del muestrario
de la UI (`ui/src/diseno/muestrario/lamina-prueba.svg`; `python -B tests/ext_prueba/esquema.py`
la regenera y `tests/test_trazos_esquema.py` exige que esté al día)."""

from __future__ import annotations

from apolo.drawing.dxf import sheet_to_dxf
from apolo.drawing.esquema import circulo, conductor, poligono, punto_union
from apolo.drawing.pdf import sheet_to_pdf
from apolo.drawing.sheet import MARGIN, SHEETS, Label, SheetModel
from apolo.drawing.svg import sheet_to_svg

FASES = ("L1", "L2", "L3")
PASO = 8.0  # mm entre fases


def _protector(m: SheetModel, x: float, y: float) -> None:
    """Un rectángulo de símbolo sobre la línea (un fusible de prueba) de y a y − 12."""
    conductor(m, x, y, x, y - 2)
    poligono(m, [(x - 1.6, y - 2), (x + 1.6, y - 2), (x + 1.6, y - 10), (x - 1.6, y - 10)])
    conductor(m, x, y - 2, x, y - 10)
    conductor(m, x, y - 10, x, y - 12)


def _contacto(m: SheetModel, x: float, y: float) -> None:
    """Un contacto abierto de prueba de y a y − 12: dos tramos y la lengüeta inclinada."""
    conductor(m, x, y, x, y - 4)
    conductor(m, x, y - 8, x, y - 12)
    conductor(m, x, y - 8, x - 3, y - 3.4)


def lamina() -> SheetModel:
    """A4 apaisada: tres fases con sus derivaciones (puntos de unión), un protector y un contacto
    por fase, la flecha del relé térmico y el motor."""
    W, H = SHEETS["A4"]
    m = SheetModel(W, H)
    m.rect(MARGIN, MARGIN, W - 2 * MARGIN, H - 2 * MARGIN)
    m.labels.append(Label(MARGIN + 6, H - MARGIN - 9, "ESQUEMA DE PRUEBA · POTENCIA", 4.0,
                          anchor="start"))

    y_bus, x0, x1 = 150.0, 40.0, 250.0
    for i, fase in enumerate(FASES):
        y = y_bus - i * PASO
        conductor(m, x0, y, x1, y)
        m.labels.append(Label(x0 - 3, y - 1.2, fase, 3.0, anchor="end"))

    # dos salidas: la segunda sólo deriva (un punto de unión por fase en cada salida)
    for k, xs in enumerate((90.0, 190.0)):
        base = y_bus - 2 * PASO - 10
        for i in range(3):
            x = xs + (i - 1) * PASO
            y = y_bus - i * PASO
            punto_union(m, x, y)
            conductor(m, x, y, x, base)
            _protector(m, x, base)
            _contacto(m, x, base - 12)
            conductor(m, x, base - 24, x, base - 40)
        m.labels += [Label(xs + 2 * PASO, base - 7, f"-F{k + 1}", 3.0, anchor="start"),
                     Label(xs + 2 * PASO, base - 19, f"-Q{k + 1}", 3.0, anchor="start")]
        # relé térmico: un rectángulo que abarca las tres fases y su flecha llena
        yr = base - 30
        poligono(m, [(xs - 12, yr + 3), (xs + 12, yr + 3), (xs + 12, yr - 3), (xs - 12, yr - 3)])
        poligono(m, [(xs + 13, yr), (xs + 17, yr + 1.6), (xs + 17, yr - 1.6)], lleno=True)
        conductor(m, xs + 17, yr, xs + 21, yr)
        m.labels.append(Label(xs + 23, yr - 1.2, f"-B{k + 1}", 3.0, anchor="start"))
        # el motor: las tres fases llegan a su círculo
        ym = base - 52
        for i in range(3):
            x = xs + (i - 1) * PASO
            conductor(m, x, base - 40, xs + (i - 1) * 4.0, ym + 8.9)
        circulo(m, xs, ym, 10.0)
        m.labels += [Label(xs, ym + 0.6, "M", 4.0), Label(xs, ym - 4.6, "3~", 3.0),
                     Label(xs + 13, ym - 1.2, f"-M{k + 1}", 3.0, anchor="start")]
    return m


def svg() -> str:
    return sheet_to_svg(lamina())


def pdf() -> bytes:
    return sheet_to_pdf(lamina())


def dxf() -> bytes:
    return sheet_to_dxf(lamina())


if __name__ == "__main__":  # regenera la lámina del muestrario de la UI
    from pathlib import Path

    destino = (Path(__file__).resolve().parents[2] / "ui" / "src" / "diseno" / "muestrario"
               / "lamina-prueba.svg")
    destino.write_text(svg() + "\n", encoding="utf-8", newline="\n")
    print(destino)
