"""El DXF escribe la letra del MISMO tamaño que el PDF (plan V8.9, «Letra del DXF»). En DXF el
`height` de un TEXT es la altura de la MAYÚSCULA; `dxf.py` escribía `height = size`, y el PDF
escribe a un em de `size × 2,45 pt` (mayúscula 0,630·size mm): la letra del DXF salía 1,59× la del
PDF, en la fuente del estilo `Standard` (txt.shx) y toda alineada a la izquierda. Aquí se dibuja
cada TEXT como lo hace un visor (`ezdxf.addons.text2path`, con DejaVu Sans, la fuente que nombra
el estilo) y se compara con la tinta y la caja del mismo texto en la figura del PDF."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from apolo.drawing.sheet import Label, SheetModel

TEXTOS = [("Placa soporte del presostato (lado operador) · 1× · Acero inoxidable AISI 304 2B", 3.0, "start"),
          ("Genix Apolo CAD", 2.8, "middle"), ("DESPIECE", 3.6, "end"),
          ("ISO 2768-mK · Ra 1.6", 2.2, "middle"), ("PLANTA DE INSTALACIÓN Y ANCLAJE", 5.0, "start")]


def _lamina() -> SheetModel:
    m = SheetModel(297.0, 210.0)
    for k, (texto, tam, ancla) in enumerate(TEXTOS):
        m.labels.append(Label(150.0, 180.0 - 20.0 * k, texto, tam, anchor=ancla))
    return m


def _fuente_pdf() -> str:
    from matplotlib.font_manager import FontProperties, findfont

    return findfont(FontProperties())


def test_la_cifra_de_la_mayuscula_es_la_de_la_fuente_del_pdf():
    from fontTools.pens.boundsPen import BoundsPen
    from fontTools.ttLib import TTFont

    from apolo.drawing.tabla import FUENTE_DXF, MAYUSCULA_EM, em_mm, mayuscula_mm

    ruta = _fuente_pdf()
    assert Path(ruta).name == FUENTE_DXF
    f = TTFont(ruta)
    glifos = f.getGlyphSet()
    pen = BoundsPen(glifos)
    glifos[f.getBestCmap()[ord("H")]].draw(pen)
    assert pen.bounds[3] / f["head"].unitsPerEm == pytest.approx(MAYUSCULA_EM, abs=1e-9)
    assert mayuscula_mm(3.0) == pytest.approx(em_mm(3.0) * MAYUSCULA_EM)
    assert mayuscula_mm(1.0) == pytest.approx(0.630, abs=5e-4)


def _textos_dxf(m: SheetModel, monkeypatch) -> list[tuple]:
    """(entidad, caja de su tinta) de cada TEXT, dibujado con la fuente que nombra su estilo."""
    import ezdxf
    from ezdxf import path as ezpath
    from ezdxf.addons import text2path
    from ezdxf.fonts import fonts

    from apolo.drawing.dxf import sheet_to_dxf

    ruta = _fuente_pdf()  # el visor tiene DejaVu Sans (la que pide el estilo), sin fallback
    monkeypatch.setattr(text2path, "get_font", lambda _cara: fonts.sideload_ttf(ruta, 1.0))
    doc = ezdxf.read(io.StringIO(sheet_to_dxf(m).decode("utf-8")))
    out = []
    for e in doc.modelspace().query("TEXT"):
        assert e.font_name() == Path(ruta).name
        caja = ezpath.bbox([text2path.make_path_from_entity(e)], fast=False)
        out.append((e, caja))
    return out


def _textos_pdf(m: SheetModel) -> list[tuple]:
    """(tinta ancho×alto en mm, caja del texto en mm de la hoja) de cada texto del PDF."""
    import matplotlib.pyplot as plt
    from matplotlib.font_manager import FontProperties
    from matplotlib.textpath import TextPath

    from apolo.drawing.pdf import _figure

    fig = _figure(m)
    fig.set_dpi(720.0)
    rend = fig.canvas.get_renderer()
    ax = fig.axes[0]
    out = []
    for t in ax.texts:
        tinta = TextPath((0, 0), t.get_text(), size=t.get_fontsize(), prop=FontProperties()).get_extents()
        caja = t.get_window_extent(rend).transformed(ax.transData.inverted())
        out.append(((tinta.width * 25.4 / 72, tinta.height * 25.4 / 72), caja))
    plt.close(fig)
    return out


def test_la_mayuscula_el_ancho_y_el_anclaje_del_dxf_son_los_del_pdf(monkeypatch):
    from apolo.drawing.tabla import ancho_mm, em_mm

    m = _lamina()
    dxf, pdf = _textos_dxf(m, monkeypatch), _textos_pdf(m)
    assert [e.dxf.text for e, _ in dxf] == [t for t, _, _ in TEXTOS]
    for (texto, tam, ancla), (e, tinta_dxf), ((ancho_pdf, alto_pdf), caja_pdf) in zip(TEXTOS, dxf, pdf):
        assert e.dxf.style == "APOLO" and e.dxf.get("valign", 0) == 0  # sobre la línea base
        # la misma mayúscula (la tinta del mismo texto en la misma fuente: alto y ancho)
        assert tinta_dxf.size.y / alto_pdf == pytest.approx(1.0, abs=0.02), (texto, "alto")
        assert tinta_dxf.size.x / ancho_pdf == pytest.approx(1.0, abs=0.02), (texto, "ancho")
        # el mismo anclaje: el borde (o el centro) que fija el PDF, a menos de un décimo de em
        lado = {"start": (tinta_dxf.extmin.x, caja_pdf.x0), "end": (tinta_dxf.extmax.x, caja_pdf.x1),
                "middle": (tinta_dxf.center.x, (caja_pdf.x0 + caja_pdf.x1) / 2)}[ancla]
        assert lado[0] == pytest.approx(lado[1], abs=0.1 * em_mm(tam)), (texto, ancla)
        # y cabe en su celda: en alto, dentro de la caja del renglón del PDF; en ancho, en lo que
        # mide `tabla.ancho_mm` (con lo que se dimensionan las celdas). El visor no aplica el
        # kerning del PDF: el texto largo sale ~1 % más ancho, dentro de la holgura del 2 %
        assert caja_pdf.y0 <= tinta_dxf.extmin.y and tinta_dxf.extmax.y <= caja_pdf.y1, texto
        assert tinta_dxf.size.x <= ancho_mm(texto, tam), texto


def test_el_dwg_convierte_el_mismo_dxf(monkeypatch):
    """El DWG es el DXF convertido por ODA (`dwg.sheet_to_dwg`): hereda la letra sin más."""
    import ezdxf

    from apolo.drawing import dwg
    from apolo.drawing.tabla import mayuscula_mm

    recibido = []
    monkeypatch.setattr(dwg, "dxf_to_dwg_bytes", lambda datos, version: recibido.append(datos) or b"")
    dwg.sheet_to_dwg(_lamina())
    doc = ezdxf.read(io.StringIO(recibido[0].decode("utf-8")))
    alturas = [round(e.dxf.height, 6) for e in doc.modelspace().query("TEXT")]
    assert alturas == [round(mayuscula_mm(tam), 6) for _, tam, _ in TEXTOS]


def test_una_lamina_sin_textos_no_crea_el_estilo():
    import ezdxf

    from apolo.drawing.dxf import sheet_to_dxf

    doc = ezdxf.read(io.StringIO(sheet_to_dxf(SheetModel(297.0, 210.0)).decode("utf-8")))
    assert "APOLO" not in doc.styles
