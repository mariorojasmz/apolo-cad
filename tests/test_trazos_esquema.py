"""Trazos de esquema en los exportadores de láminas (plan puntos-de-extension-entregables, F2):
`simbolo` (trazo negro, sin relleno) y `simbolo_lleno` (negro relleno: el punto de unión) en
`Line`, `Circle` y `Polygon`, con el grosor de `drawing/esquema.py`, en SVG, PDF y DXF. Lo que ya
existía no cambia de aspecto: las firmas de una lámina con TODOS los estilos de antes quedan
congeladas aquí (sacadas del código anterior a la F2)."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from apolo.drawing.dxf import sheet_to_dxf
from apolo.drawing.esquema import (
    D_UNION_MM,
    GROSOR_SIMBOLO_MM,
    LLENO,
    SIMBOLO,
    circulo,
    conductor,
    poligono,
    punto_union,
)
from apolo.drawing.pdf import _figure
from apolo.drawing.sheet import Arc, Circle, Label, Line, Polygon, SheetModel
from apolo.drawing.svg import sheet_to_svg

RAIZ = Path(__file__).resolve().parents[1]


def _lamina_de_antes() -> SheetModel:
    """Una lámina con cada estilo que existía antes de la F2 (y un `kind` desconocido)."""
    m = SheetModel(297.0, 210.0)
    m.rect(10, 10, 277, 190)
    for i, kind in enumerate(("visible", "hidden", "frame", "dim", "center", "inventado")):
        m.lines.append(Line(20, 30 + 10 * i, 120, 35 + 10 * i, kind))
    m.labels += [Label(150, 100, "Rótulo", 3.2), Label(150, 110, "Girado", 2.6, "start", 90.0)]
    m.circles += [Circle(200, 50, 3.2, "globo"), Circle(210, 50, 5.0, "dim"),
                  Circle(220, 50, 2.0, "corte")]
    m.arcs.append(Arc(230, 80, 4.0, 0.0, 270.0))
    m.polygons += [Polygon([[(40, 140), (80, 140), (80, 170), (40, 170)]]),
                   Polygon([[(100, 140), (140, 140), (140, 170)], [(120, 150), (130, 150), (130, 155)]],
                           "corte", "acero")]
    return m


def _firma_svg(m: SheetModel) -> str:
    return hashlib.sha256(sheet_to_svg(m).encode("utf-8")).hexdigest()


def _artistas_pdf(m: SheetModel) -> list:
    """Lo que dibuja la figura del PDF: tipo, colores, grosor y estilo de cada artista."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import to_hex

    fig = _figure(m)
    ax = fig.axes[0]
    out = []
    for p in ax.patches:
        out.append([type(p).__name__, to_hex(p.get_facecolor(), keep_alpha=True),
                    to_hex(p.get_edgecolor(), keep_alpha=True), round(p.get_linewidth(), 4),
                    p.get_fill(), p.get_hatch() or ""])
    for c in ax.collections:
        out.append([type(c).__name__, [to_hex(x) for x in c.get_colors()],
                    [round(w, 4) for w in c.get_linewidths()], len(c.get_segments())])
    out += [["Text", t.get_text(), round(t.get_fontsize(), 3)] for t in ax.texts]
    plt.close(fig)
    return out


def _firma_pdf(m: SheetModel) -> str:
    return hashlib.sha256(json.dumps(_artistas_pdf(m)).encode("utf-8")).hexdigest()


def _entidades_dxf(m: SheetModel) -> list:
    import ezdxf

    doc = ezdxf.read(io.StringIO(sheet_to_dxf(m).decode("utf-8")))
    capas = sorted((ly.dxf.name, ly.dxf.color, ly.dxf.linetype, ly.dxf.lineweight)
                   for ly in doc.layers)
    out: list = [["capas", capas]]
    for e in doc.modelspace():
        fila = [e.dxftype(), e.dxf.layer]
        for k in ("start", "end", "center", "insert"):
            if e.dxf.hasattr(k):
                fila.append([round(v, 3) for v in e.dxf.get(k)])
        if e.dxftype() == "HATCH":
            fila += [e.dxf.pattern_name, e.dxf.solid_fill]
        out.append(fila)
    return out


def _firma_dxf(m: SheetModel) -> str:
    return hashlib.sha256(json.dumps(_entidades_dxf(m)).encode("utf-8")).hexdigest()


# firmas del código ANTERIOR a la F2 (sacadas en 72f7c01): si cambian, cambió el aspecto de una
# lámina mecánica que no usa los trazos nuevos
FIRMA_SVG = "b95b95ff73f031d9433cb5276c990ce1f54ed2f673b973c8462d4b2e42a3569f"
FIRMA_PDF = "06194a2ca4cf365eb082198cbd067b4ac1a40aab3b7659bd4ae9763694b56f00"
FIRMA_DXF = "dcfb72ae2b56c2d7db7dd9da965ed9eec5fc3094485c7a9e5395e9fd21a7385d"


def test_lo_de_antes_no_cambia_de_aspecto():
    m = _lamina_de_antes()
    assert _firma_svg(m) == FIRMA_SVG
    assert _firma_pdf(m) == FIRMA_PDF
    assert _firma_dxf(m) == FIRMA_DXF


def _lamina_de_esquema() -> SheetModel:
    m = SheetModel(297.0, 210.0)
    conductor(m, 20, 100, 120, 100)
    circulo(m, 60, 80, 10.0)
    punto_union(m, 40, 100)
    poligono(m, [(80, 90), (90, 90), (90, 110), (80, 110)])
    poligono(m, [(100, 100), (104, 101.6), (104, 98.4)], lleno=True)
    return m


def test_svg_dibuja_el_simbolo_sin_relleno_y_la_union_rellena():
    svg = sheet_to_svg(_lamina_de_esquema())
    trazo = f'stroke="#16181d" stroke-width="{GROSOR_SIMBOLO_MM:g}"'
    assert f'<line x1="20.00" y1="110.00" x2="120.00" y2="110.00" {trazo}' in svg
    assert f'<circle cx="60.00" cy="130.00" r="10.00" fill="none" {trazo}/>' in svg
    assert f'<circle cx="40.00" cy="110.00" r="{D_UNION_MM / 2:.2f}" fill="#16181d" {trazo}/>' in svg
    caminos = [ln for ln in svg.splitlines() if ln.startswith("<path") and trazo in ln]
    assert [('fill="none"' in c, 'fill="#16181d"' in c) for c in caminos] == [(True, False),
                                                                           (False, True)]
    assert "#3a5e9c" not in svg and "#ccd5e3" not in svg  # ni el azul de los globos ni el gris


def test_pdf_dibuja_negro_con_el_grosor_en_puntos():
    artistas = _artistas_pdf(_lamina_de_esquema())
    grosor = round(GROSOR_SIMBOLO_MM * 72 / 25.4, 4)
    parches = [a for a in artistas if a[0] in ("PathPatch", "Circle")]
    assert sorted((a[0], a[1], a[2], a[3]) for a in parches) == sorted([
        ("PathPatch", "#00000000", "#16181dff", grosor),   # contorno sin relleno
        ("PathPatch", "#16181dff", "#16181dff", grosor),   # flecha llena
        ("Circle", "#00000000", "#16181dff", grosor),      # círculo de símbolo
        ("Circle", "#16181dff", "#16181dff", grosor),      # punto de unión
    ])
    lineas = [a for a in artistas if a[0] == "LineCollection"]
    assert lineas == [["LineCollection", ["#16181d"], [grosor], 1]]


def test_dxf_pone_el_esquema_en_su_capa_con_relleno_solido():
    entidades = _entidades_dxf(_lamina_de_esquema())
    capas = {c[0]: list(c[1:]) for c in entidades[0][1]}
    assert capas["ESQUEMA"] == [7, "CONTINUOUS", 35]
    resto = entidades[1:]
    assert {e[1] for e in resto} == {"ESQUEMA"}
    # 1 línea, 2 círculos, 2 contornos y 2 rellenos sólidos (el punto de unión y la flecha)
    assert sorted(e[0] for e in resto) == ["CIRCLE", "CIRCLE", "HATCH", "HATCH", "LINE",
                                           "LWPOLYLINE", "LWPOLYLINE"]
    assert all(e[-2:] == ["SOLID", 1] for e in resto if e[0] == "HATCH")


def test_una_lamina_mecanica_no_crea_la_capa_del_esquema():
    capas = [c[0] for c in _entidades_dxf(_lamina_de_antes())[0][1]]
    assert "ESQUEMA" not in capas


# firmas de la lámina de esquema de la F2 sacadas ANTES de sumar el trazo cortado (V8.9 F5, sobre
# ec8d294): un estilo nuevo no cambia una lámina de esquema que no lo usa
FIRMA_ESQUEMA_SVG = "059fcd504306f4e042b068ee2cce230c15316cb63d665e1931ee2a360d49e134"
FIRMA_ESQUEMA_PDF = "f1694ea03541bad472b29fa9801b4cae6972a3475cff3fef4ca3cb281960ba0c"
FIRMA_ESQUEMA_DXF = "ade921a69a98604efe878eec1ff6eb984757b85b32371f9e64aa27cfda2d47cc"


def test_el_trazo_cortado_no_cambia_una_lamina_de_esquema_que_no_lo_usa():
    m = _lamina_de_esquema()
    assert (_firma_svg(m), _firma_pdf(m), _firma_dxf(m)) == (
        FIRMA_ESQUEMA_SVG, FIRMA_ESQUEMA_PDF, FIRMA_ESQUEMA_DXF)


def test_el_trazo_cortado_en_los_tres_exportadores():
    """V8.9 F5: la línea de pilotaje (ISO 1219-1) con el grosor del esquema y trazos 12·d/3·d
    (ISO 128-20 tipo 02)."""
    import ezdxf

    from apolo.drawing.esquema import PILOTAJE, TIPO_LINEA_DXF, pilotaje, trazos_mm

    m = SheetModel(297.0, 210.0)
    pilotaje(m, 20, 100, 120, 100)
    trazo, hueco = trazos_mm()
    assert (trazo, hueco) == pytest.approx((12 * GROSOR_SIMBOLO_MM, 3 * GROSOR_SIMBOLO_MM))
    assert m.lines[0].kind == PILOTAJE
    svg = sheet_to_svg(m)
    assert f'stroke-width="{GROSOR_SIMBOLO_MM:g}" stroke-dasharray="{trazo:g},{hueco:g}"' in svg
    linea = [a for a in _artistas_pdf(m) if a[0] == "LineCollection"]
    assert linea == [["LineCollection", ["#16181d"], [round(GROSOR_SIMBOLO_MM * 72 / 25.4, 4)], 1]]
    fig = _figure(m)
    estilo = fig.axes[0].collections[0].get_linestyle()[0]
    import matplotlib.pyplot as plt

    plt.close(fig)
    assert estilo[1] is not None and len(estilo[1]) == 2  # un patrón de trazo y hueco
    doc = ezdxf.read(io.StringIO(sheet_to_dxf(m).decode("utf-8")))
    (e,) = list(doc.modelspace())
    assert e.dxf.layer == "ESQUEMA" and e.dxf.linetype == TIPO_LINEA_DXF
    assert TIPO_LINEA_DXF in doc.linetypes
    assert TIPO_LINEA_DXF not in ezdxf.read(io.StringIO(sheet_to_dxf(_lamina_de_esquema()).decode())).linetypes


def test_los_estilos_y_el_poligono_corto():
    assert (SIMBOLO, LLENO) == ("simbolo", "simbolo_lleno")
    with pytest.raises(ValueError, match="3 puntos"):
        poligono(SheetModel(10, 10), [(0, 0), (1, 1)])


def test_la_lamina_del_muestrario_es_la_que_dibuja_la_extension_falsa():
    """El panel ancho del muestrario de la UI muestra la lámina de `tests/ext_prueba/esquema.py`
    tal como la exporta el núcleo; si cambia el exportador o la lámina, se regenera con
    `python -B tests/ext_prueba/esquema.py`."""
    from ext_prueba import esquema

    archivo = RAIZ / "ui" / "src" / "diseno" / "muestrario" / "lamina-prueba.svg"
    assert archivo.read_text(encoding="utf-8") == esquema.svg() + "\n"
    assert esquema.pdf().startswith(b"%PDF")
    assert b"ESQUEMA" in esquema.dxf()
