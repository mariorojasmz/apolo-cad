"""La cotización no imprime internos (plan cotizacion-identificada-y-ajustes-por-escenario,
§ Cotización sin internos), con la extensión FALSA de `tests/ext_prueba/`:

- la «Ref» de una fila de extensión es el `rotulo` de su `FuenteCosteo` (validado al cargar como
  el de `IdentificacionCosteo`); sin él, el id como antes;
- el cajetín de las hojas de la cotización dice «Cotización <nº>», no «Plano <nº>», y un título
  largo se parte en dos renglones en vez de cortarse a 34 (el de los planos no cambia);
- el producto de los requisitos sale legible («paqueteria» → «paquetería»); sin él, no hay línea.

Sin extensiones, sin `comercial` y sin `producto`, lo congela `test_cotizacion_notas.py`.
"""

from __future__ import annotations

import pytest

from apolo.doc import Document

EXTRA = "APOLO_EXTENSIONES_EXTRA"
META = {"date": "2026-10-25", "revisions": []}


@pytest.fixture
def cargar(extensiones_aisladas, monkeypatch):
    def _cargar(*variantes: str) -> list[dict]:
        monkeypatch.setenv(EXTRA, ",".join(f"ext_prueba:{v}" for v in variantes))
        return extensiones_aisladas.cargar()

    return _cargar


def _doc(nombre: str = "faja 4m") -> Document:
    d = Document(nombre)
    d.execute("create_box", {"name": "Tablero", "width": 400, "depth": 300, "height": 20})
    return d


def _paginas(d: Document, requirements: dict | None = None):
    from apolo.drawing.quote import quotation_pages
    from apolo.services.cobros import costeo
    from apolo.services.identificacion import identificacion

    return quotation_pages(d.scene, project_name=d.name, costeo=costeo(d), meta=META,
                           identificacion=identificacion(d), requirements=requirements)


def _textos(pagina) -> list[str]:
    return [lb.text for lb in pagina.labels]


def _cajetin_titulo(pagina) -> list:
    """Las etiquetas de la fila del título del cajetín (y entre 30 y 40 mm sobre su base)."""
    from apolo.drawing.titleblock import TITLE_W

    x0 = pagina.width - 10.0 - TITLE_W
    return [lb for lb in pagina.labels if lb.x == x0 + 2 and 40.0 <= lb.y <= 50.0]


# ── la «Ref» de una fila de extensión ───────────────────────────────────────────────────────

def test_la_ref_es_el_rotulo_de_la_fuente_y_sin_el_el_id(cargar):
    from ext_prueba.costeo import ROTULO_FUENTE

    from apolo.services.cobros import costeo

    (e,) = cargar("COSTEO_FUENTE_CON_ROTULO")
    assert e["cargada"], e
    d = _doc()
    filas = {r["ref"]: r for r in costeo(d)["rows"] if r["ref"].startswith("prueba.")}
    # el `ref` sigue siendo el id (con él se cuenta quién cobró); el rótulo va aparte
    assert filas["prueba.revision"]["rotulo"] == ROTULO_FUENTE
    assert "rotulo" not in filas["prueba.marcha"]
    detalle = " ".join(t for p in _paginas(d)[1:] for t in _textos(p))
    assert ROTULO_FUENTE in detalle and "prueba.revision" not in detalle
    assert "prueba.marcha" in detalle  # sin `rotulo`, el id como antes
    # la nota de la fuente sigue saliendo (cobró: se cuenta por el id)
    from ext_prueba.costeo import NOTA_REVISION

    assert any(NOTA_REVISION in t for t in _textos(_paginas(d)[0]))


@pytest.mark.parametrize(("variante", "motivo"), [
    ("FUENTE_ROTULO_DOS_LINEAS", "`rotulo` es de una sola línea"),
    ("FUENTE_ROTULO_LARGO", "`rotulo` tiene 61 caracteres (máximo 60)"),
    ("FUENTE_ROTULO_VACIO", "`rotulo` es un texto no vacío"),
])
def test_un_rotulo_de_fuente_malo_no_carga(cargar, variante, motivo):
    from apolo.library import costeo_extension

    (e,) = cargar(variante)
    assert e["cargada"] is False, e
    assert "la fuente de costeo «prueba.revision»" in e["motivo"] and motivo in e["motivo"], e
    assert costeo_extension.DE_EXTENSION == {}


# ── el cajetín de la cotización ─────────────────────────────────────────────────────────────

def test_el_cajetin_dice_cotizacion_en_todas_las_hojas():
    paginas = _paginas(_doc())
    assert len(paginas) >= 2
    for p in paginas:
        textos = _textos(p)
        assert "Cotización COT-001" in textos, textos
        assert not any(t.startswith("Plano ") for t in textos)
    # un título corto: un renglón al tamaño de siempre
    (titulo,) = _cajetin_titulo(paginas[0])
    assert titulo.text == "faja 4m" and titulo.size == 4.0


def test_un_titulo_largo_va_en_dos_renglones_sin_cortarse_ni_pisar_el_numero():
    from apolo.drawing.tabla import ancho_mm
    from apolo.services.identificacion import poner_comercial

    d = _doc()
    largo = "TRANSPORTADOR DE BANDA PARA PAQUETERÍA CON TABLERO Y VARIADOR DE FRECUENCIA"
    assert len(largo) <= 80
    poner_comercial(d, {"titulo": largo, "numero": "COT-2026-0153-LIMA-NORTE-REV-B"})
    for p in _paginas(d):
        renglones = _cajetin_titulo(p)
        assert len(renglones) == 2, [lb.text for lb in renglones]
        assert " ".join(lb.text for lb in renglones) == largo  # nada recortado
        numero = next(lb for lb in p.labels if lb.text == "Cotización COT-2026-0153-LIMA-NORTE-REV-B")
        tope = numero.x - ancho_mm(numero.text, numero.size)
        for lb in renglones:
            assert lb.size < 4.0 and lb.x + ancho_mm(lb.text, lb.size) < tope
        assert renglones[0].y - renglones[1].y >= 3.4  # no se montan


def test_el_cajetin_de_un_plano_no_cambia():
    from apolo.drawing.sheet import SheetModel
    from apolo.drawing.titleblock import draw_title_block

    m = SheetModel(297.0, 210.0)
    largo = "Transportador de banda para paquetería con tablero y variador"
    draw_title_block(m, {"project": largo, "drawing_no": "P-12"})
    textos = _textos(m)
    assert "Plano P-12" in textos and largo[:34] in textos  # como siempre: un renglón a 34


# ── el producto, legible ────────────────────────────────────────────────────────────────────

def test_producto_legible():
    from apolo.library.requisitos import producto_legible

    assert producto_legible("paqueteria") == "paquetería"
    assert producto_legible(" Paquetería ") == "paquetería"
    assert producto_legible("cajas_de_carton") == "cajas de cartón"
    assert producto_legible("Cajas de fruta") == "Cajas de fruta"  # sin etiqueta: tal cual
    assert producto_legible(" sacos ") == "sacos"


def test_la_hoja_dice_el_producto_legible_y_sin_el_no_hay_linea():
    d = _doc()
    textos = _textos(_paginas(d, {"producto": "paqueteria"})[0])
    assert "Producto: paquetería" in textos
    assert not any("paqueteria" in t for t in textos)
    textos = _textos(_paginas(d, {"producto": "Cajas de fruta"})[0])
    assert "Producto: Cajas de fruta" in textos
    for req in ({}, {"producto": ""}, {"producto": "   "}, {"carga_kg": 15.0}):
        textos = _textos(_paginas(d, req)[0])
        assert not any(t.startswith(("Producto:", "Alcance:")) for t in textos), req


def test_un_producto_largo_va_en_dos_renglones_como_mucho():
    d = _doc()
    largo = "cajas de cartón corrugado de 5 a 15 kg con etiqueta de código de barras " * 3
    resumen = _paginas(d, {"producto": largo})[0]
    lineas = [lb for lb in resumen.labels if lb.size == 3.0 and lb.x in (16, 18)
              and lb.y > resumen.height - 60 and not lb.text.startswith("DESGLOSE")]
    assert lineas[0].text.startswith("Producto: cajas de cartón")
    assert len(lineas) == 2 and lineas[1].text.endswith("…")
    ys = {lb.text: lb.y for lb in resumen.labels}
    assert lineas[1].y > ys["DESGLOSE POR CATEGORÍA"]
