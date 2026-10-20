"""Contraste de texto sobre un panel semitransparente (regla de D4 de video-tienda-pulido: el
texto del video se lee con contraste ≥ 4.5:1, el mínimo WCAG AA para texto normal).

El panel del rótulo va sobre el cuadro, que puede ser cualquier cosa (una pieza galvanizada casi
blanca, el fondo oscuro). La regla se cumple contra el PEOR fondo: el panel compuesto sobre blanco
y sobre negro. Puro, sin Pillow.
"""

from __future__ import annotations

Color = tuple[int, int, int]

MINIMO = 4.5
BLANCO: Color = (255, 255, 255)
NEGRO: Color = (0, 0, 0)


def _lineal(c: float) -> float:
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminancia(color) -> float:
    """Luminancia relativa WCAG 2.x de un color sRGB de 0–255."""
    r, g, b = (_lineal(float(x)) for x in color[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b) -> float:
    """Razón de contraste WCAG entre dos colores (1 a 21)."""
    la, lb = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def sobre(panel, opacidad: float, fondo) -> Color:
    """El color del panel con `opacidad` (0–1) compuesto sobre `fondo`."""
    return tuple(round(p * opacidad + f * (1 - opacidad)) for p, f in zip(panel, fondo))


def peor_contraste(texto, panel, opacidad: float, fondos=(BLANCO, NEGRO)) -> float:
    """El contraste más bajo de `texto` sobre el panel compuesto en cada fondo."""
    return min(contraste(texto, sobre(panel, opacidad, f)) for f in fondos)


def opacidad_legible(textos, panel, minima: float = 0.0, objetivo: float = MINIMO) -> float:
    """La menor opacidad del panel (≥ `minima`, en pasos de 0,01) con la que TODOS los `textos`
    llegan a `objetivo` sobre cualquier fondo. 1.0 si ni opaco llegan (el test lo vigila)."""
    paso = max(0, round(minima * 100))
    for centesimas in range(paso, 101):
        a = centesimas / 100
        if all(peor_contraste(t, panel, a) >= objetivo for t in textos):
            return a
    return 1.0
