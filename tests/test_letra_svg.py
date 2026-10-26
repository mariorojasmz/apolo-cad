"""El SVG escribe la letra del MISMO tamaño que el PDF (plan V8.9, «Últimos cortes y letra del
SVG»). Todo texto de los papeles se mide contra el PDF (`tabla.ancho_mm`); el SVG escribía
`font-size = size` (un em 16 % más grande que los `size × 2,45 pt` del PDF) con Segoe UI. Aquí se
mide el ancho de cada texto en los dos: el del PDF, con el renderizador de matplotlib sobre la
figura que exporta; el del SVG, con la fuente y el `font-size` que dice el propio archivo."""

from __future__ import annotations

import re

import pytest

from apolo.drawing.sheet import Label, SheetModel

TEXTOS = [("Placa soporte del presostato (lado operador) · 1× · Acero inoxidable AISI 304 2B", 3.0),
          ("Genix Apolo CAD", 2.8), ("DESPIECE", 3.6), ("ISO 2768-mK · Ra 1.6", 2.2),
          ("PLANTA DE INSTALACIÓN Y ANCLAJE", 5.0)]
DPI = 720.0


def _lamina() -> SheetModel:
    m = SheetModel(297.0, 210.0)
    for k, (texto, tam) in enumerate(TEXTOS):
        m.labels.append(Label(20.0, 180.0 - 20.0 * k, texto, tam, anchor="start"))
    return m


def _anchos_pdf(m: SheetModel) -> list[float]:
    import matplotlib.pyplot as plt

    from apolo.drawing.pdf import _figure

    fig = _figure(m)
    fig.set_dpi(DPI)  # sin el hinting de pocos dpi (como `tabla.ancho_mm`)
    rend = fig.canvas.get_renderer()
    out = [t.get_window_extent(rend).width / DPI * 25.4 for t in fig.axes[0].texts]
    plt.close(fig)
    return out


def _textos_svg(svg: str) -> tuple[str, list[tuple[float, str]]]:
    familia = re.search(r'<svg [^>]*font-family="([^"]+)"', svg).group(1)
    textos = re.findall(r'<text [^>]*font-size="([0-9.]+)"[^>]*>([^<]*)</text>', svg)
    return familia, [(float(fs), t) for fs, t in textos]


def _ancho_mm(texto: str, em_mm: float, fuente) -> float:
    from matplotlib.backends.backend_agg import RendererAgg

    fp = fuente.copy()
    fp.set_size(em_mm * 72.0 / 25.4)
    w, _, _ = RendererAgg(10, 10, DPI).get_text_width_height_descent(texto, fp, ismath=False)
    return w / DPI * 25.4


def test_el_svg_y_el_pdf_escriben_cada_texto_del_mismo_ancho():
    from xml.sax.saxutils import unescape

    from matplotlib.font_manager import FontProperties, findfont

    from apolo.drawing.svg import sheet_to_svg

    m = _lamina()
    familia, textos = _textos_svg(sheet_to_svg(m))
    primera = familia.split(",")[0].strip()
    fuente = FontProperties(family=primera)
    # la primera fuente del SVG es la que usa el PDF (la de matplotlib por defecto)
    assert findfont(fuente) == findfont(FontProperties())
    assert [unescape(t) for _, t in textos] == [t for t, _ in TEXTOS]
    for (texto, _tam), (em, _), ancho_pdf in zip(TEXTOS, textos, _anchos_pdf(m)):
        ancho_svg = _ancho_mm(texto, em, fuente)
        assert abs(ancho_svg / ancho_pdf - 1.0) < 0.01, (texto, ancho_svg, ancho_pdf)


def test_verdana_de_respaldo_da_la_misma_mayuscula_y_casi_el_mismo_ancho():
    """Donde DejaVu Sans no está instalada (Windows, macOS), el visor usa Verdana: la misma
    altura de mayúscula y casi el mismo ancho (medido sobre los 304 textos del juego de planos
    de la faja testigo: mediana +1,4 %, p95 +4,9 %, máx. +8,5 %, en cifras sueltas)."""
    from matplotlib.font_manager import FontProperties, findfont

    from apolo.drawing.svg import FUENTE_SVG
    from apolo.drawing.tabla import em_mm

    assert [f.strip() for f in FUENTE_SVG.split(",")][:2] == ["DejaVu Sans", "Verdana"]
    try:
        ruta = findfont(FontProperties(family="Verdana"), fallback_to_default=False)
    except ValueError:
        pytest.skip("Verdana no está instalada en esta máquina")
    dejavu = FontProperties()
    verdana = FontProperties(fname=ruta)
    rs = [_ancho_mm(t, em_mm(tam), verdana) / _ancho_mm(t, em_mm(tam), dejavu) for t, tam in TEXTOS]
    assert all(0.97 < r < 1.09 for r in rs), rs
    assert sum(rs) / len(rs) < 1.04, rs

    def mayuscula(fuente) -> float:  # alto de la «H» (sin descendente) a un em de 10 mm
        from matplotlib.backends.backend_agg import RendererAgg

        fp = fuente.copy()
        fp.set_size(10.0 * 72.0 / 25.4)
        _, h, d = RendererAgg(10, 10, DPI).get_text_width_height_descent("H", fp, ismath=False)
        return h - d

    assert abs(mayuscula(verdana) / mayuscula(dejavu) - 1.0) < 0.01
