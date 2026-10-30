"""Las notas de la cotización que suma una extensión (plan pedidos-de-extensiones, F5: D9, D13),
con la extensión FALSA de `tests/ext_prueba/`:

- la nota de una fuente sale DESPUÉS de las del núcleo y sólo si su fuente cobró una fila; el
  costeo suma `notas: [{texto, fuente, origen}]` sólo si hay;
- una nota mala (vacía, de dos líneas, de más de 300 caracteres, que no es texto) no carga la
  extensión y deshace todo lo que había registrado;
- el peor caso (avisos + tipo de cambio + notas largas de dos fuentes) no pisa el cajetín y lo
  que no cabe sigue en la hoja «NOTAS (continuación)», antes del detalle;
- sin extensiones, el costeo y las hojas de la cotización quedan CONGELADOS (las cifras se
  midieron contra `f3b36bd`: costeo, hojas y PDF byte-idénticos).

El margen de «Fuente» (D10) se midió y se descartó: la medida está en la bitácora del plan.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document

EXTRA = "APOLO_EXTENSIONES_EXTRA"
ORIGEN = "extension:ext-prueba"
META = {"date": "2026-10-25", "revisions": [{"rev": "A", "date": "2026-10-25", "note": "x"}]}


@pytest.fixture
def cargar(extensiones_aisladas, monkeypatch):
    def _cargar(variante: str = "EXTENSION") -> dict:
        monkeypatch.setenv(EXTRA, f"ext_prueba:{variante}")
        (e,) = extensiones_aisladas.cargar()
        return e

    return _cargar


def _mesa() -> Document:
    d = Document("mesa")
    d.execute("create_box", {"name": "Tablero", "width": 400, "depth": 300, "height": 20})
    return d


def _directo() -> Document:
    from tablero_electrico import arranque_directo

    d = Document("tablero")
    d.execute_many(arranque_directo())
    return d


def _vfd() -> Document:
    """El tablero con variador cuyo VFD 3D no está ligado: trae un aviso de cobro."""
    from tablero_electrico import arranque_variador_plc

    d = Document("cot-f4c")
    d.execute("insert_component", {"component": "VFD-2K2-220", "name": "Variador de frecuencia"})
    d.execute_many(arranque_variador_plc())
    return d


def _paginas(d: Document, **kw):
    from apolo.drawing.quote import quotation_pages
    from apolo.services.cobros import costeo

    return quotation_pages(d.scene, project_name=d.name, costeo=costeo(d), meta=META, **kw)


def _textos(pagina) -> list[str]:
    return [lb.text for lb in pagina.labels]


def _notas_resumen(pagina) -> list[str]:
    """Las líneas de las NOTAS del resumen, en orden (x = 18, bajo el rótulo)."""
    from apolo.drawing.quote import _NOTAS_Y

    return [lb.text for lb in pagina.labels if lb.x == 18 and lb.y < _NOTAS_Y]


# ── D9: la nota sale tras las del núcleo, sólo si su fuente cobró ─────────────────────────────

def test_la_nota_sale_tras_las_del_nucleo_solo_si_su_fuente_cobro(cargar):
    from apolo.services.cobros import costeo
    from ext_prueba.costeo import NOTA_CONEXIONADO, NOTA_REVISION

    assert cargar()["cargada"]
    mesa = costeo(_mesa())  # sin tablero, el conexionado no cobra: su nota no sale
    assert mesa["notas"] == [{"texto": NOTA_REVISION, "fuente": "prueba.revision",
                              "origen": ORIGEN}]
    lineas = _notas_resumen(_paginas(_mesa())[0])
    assert lineas[-1] == f"5. {NOTA_REVISION}"  # tras las 4 del núcleo, numerada a continuación
    assert lineas[0].startswith("1. Precios de catálogo REFERENCIALES")
    assert any(ln.startswith("4. Validez de la oferta") for ln in lineas)
    assert not any(NOTA_CONEXIONADO in t for p in _paginas(_mesa()) for t in _textos(p))

    directo = costeo(_directo())
    assert [n["fuente"] for n in directo["notas"]] == ["prueba.revision", "prueba.conexionado"]
    lineas = _notas_resumen(_paginas(_directo())[0])
    assert lineas[-2:] == [f"5. {NOTA_REVISION}", f"6. {NOTA_CONEXIONADO}"]


def test_sin_nota_ni_cobro_no_hay_clave_notas(cargar):
    from apolo.services.cobros import costeo

    assert cargar("COSTEO_CON_FALLAS")["cargada"]  # fuentes sin nota
    data = costeo(_mesa())
    assert "notas" not in data and data["extensiones"] == {"ext-prueba": 1}


def test_las_notas_viajan_en_costing_json(cargar, monkeypatch):
    assert cargar()["cargada"]
    monkeypatch.setattr(api, "DOC", _mesa())
    js = TestClient(api.app).get("/api/costing.json").json()
    assert [n["fuente"] for n in js["notas"]] == ["prueba.revision"]


@pytest.mark.parametrize(("variante", "motivo"), [
    ("NOTA_VACIA", "`nota` es un texto no vacío"),
    ("NOTA_DOS_LINEAS", "`nota` es de una sola línea"),
    ("NOTA_LARGA", "`nota` tiene 301 caracteres (máximo 300)"),
    ("NOTA_NO_TEXTO", "«prueba.conexionado»: `nota` es un texto no vacío, no 42"),
])
def test_una_nota_mala_no_carga_la_extension(cargar, variante, motivo):
    from apolo.commands.registry import REGISTRY
    from apolo.library import costeo_extension, entrega_extension
    from apolo.library.calidad import registro

    e = cargar(variante)
    assert e["cargada"] is False and motivo in e["motivo"], e
    assert costeo_extension.DE_EXTENSION == {} and registro.DE_EXTENSION == {}  # todo o nada
    assert entrega_extension.DE_EXTENSION == {} and "prueba.hola" not in REGISTRY


def test_motivo_nota():
    from apolo.library.costeo_extension import NOTA_MAX, motivo_nota

    assert motivo_nota(None) is None and motivo_nota("x" * NOTA_MAX) is None
    assert motivo_nota("Una línea.\r") and motivo_nota("a b") and motivo_nota("")
    assert motivo_nota(["lista"])


# ── D9: el peor caso no pisa el cajetín y sigue en la hoja de continuación ───────────────────

def _cajas(pagina, dpi: float) -> list[tuple[str, float, float, float, float]]:
    """(texto, x0, x1, y0, y1) en mm de cada etiqueta, renderizada como el PDF a `dpi`."""
    import matplotlib.pyplot as plt

    from apolo.drawing.pdf import _figure

    fig = _figure(pagina)
    fig.set_dpi(dpi)
    try:
        fig.canvas.draw()
        ren = fig.canvas.get_renderer()
        inv = fig.axes[0].transData.inverted()
        out = []
        for lab, art in zip(pagina.labels, fig.axes[0].texts):
            (x0, y0), (x1, y1) = inv.transform(art.get_window_extent(ren).get_points())
            out.append((lab.text, x0, x1, y0, y1))
        return out
    finally:
        plt.close(fig)


def test_el_peor_caso_no_pisa_el_cajetin_y_sigue_en_la_continuacion(cargar):
    from apolo.drawing.notas_cotizacion import PISO, TITULO
    from apolo.drawing.tabla import piso_tabla
    from apolo.drawing.titleblock import TITLE_W
    from ext_prueba.costeo import LARGA_CONEXIONADO, LARGA_REVISION

    assert len(LARGA_REVISION) == len(LARGA_CONEXIONADO) == 300
    assert cargar("COSTEO_NOTAS_LARGAS")["cargada"]
    pages = _paginas(_vfd(), fx=3.7, currency="PEN")
    resumen, avisos, cont, *detalle = pages
    assert avisos.labels[0].text.startswith("AVISOS DE COBRO")  # sigue siendo la hoja 2
    assert cont.labels[0].text == TITULO
    assert detalle and detalle[0].labels[0].text.startswith("DETALLE DE PARTIDAS")
    # el cajetín de cada hoja cuenta la de continuación
    assert all(f"{k}/{len(pages)} A4" in " ".join(_textos(p)) for k, p in enumerate(pages, 1))

    lineas = _notas_resumen(resumen)
    nucleo = ("1. Hay 1 aviso(s) de cobro", "2. Precios de catálogo", "3. Montos convertidos",
              "6. Validez de la oferta")
    assert all(any(ln.startswith(n) for ln in lineas) for n in nucleo)  # el núcleo no se toca
    assert lineas[-1].startswith("Nota") and "en la hoja 3." in lineas[-1]

    # en el resumen, a la izquierda del cajetín y sobre el marco
    W = resumen.width
    x_cajetin = W - 10.0 - TITLE_W
    notas = set(lineas)
    for dpi in (96, 600):
        for texto, _x0, x1, y0, _y1 in _cajas(resumen, dpi):
            if texto in notas:
                assert x1 <= x_cajetin - 1.0 and y0 >= 10.5, (dpi, texto, x1, y0)
    assert min(lb.y for lb in resumen.labels if lb.text in notas) >= PISO
    # en la continuación, sobre el cajetín y su tabla de revisiones, dentro del marco
    piso = piso_tabla(META)
    for texto, _x0, x1, y0, _y1 in _cajas(cont, 600)[1:]:
        if y0 >= piso - 3:  # lo del cajetín queda abajo
            assert x1 <= W - 10.5, texto
    cuerpo = [lb for lb in cont.labels[1:] if lb.x == 18]
    assert cuerpo and min(lb.y for lb in cuerpo) >= piso

    # nada se recorta: cada nota entera, en el resumen o en la continuación
    todo = "".join(lineas + [lb.text for lb in cuerpo]).replace(" ", "")
    for nota in (LARGA_REVISION, LARGA_CONEXIONADO):
        assert nota.replace(" ", "") in todo


def test_las_notas_se_reparten_enteras_y_en_orden():
    from apolo.drawing.notas_cotizacion import hojas_continuacion, repartir

    cortas = ["Nota corta uno.", "Nota corta dos."]
    lineas, resto = repartir(60.0, 297.0, cortas, 5, 3)
    assert lineas == ["5. Nota corta uno.", "6. Nota corta dos."] and resto == []
    larga = "palabra " * 50  # ~ 6 líneas
    lineas, resto = repartir(13.0 + 3.8 * 4, 297.0, ["Una.", larga, "Tres."], 7, 2)
    assert lineas == ["7. Una.", "Notas 8 a 9: siguen en la hoja 2."]  # la 9 no salta a la 8
    assert [n for n, _ in resto] == [8, 9]
    hojas = hojas_continuacion([(n, larga) for n in range(1, 60)], W=297.0, H=210.0,
                               meta_hoja=lambda k, n: {"revisions": [], "sheet_no": k})
    assert len(hojas) > 1 and hojas[0].labels[0].text.endswith(f"(1/{len(hojas)})")


# ── vigencia: sin extensiones, todo congelado ─────────────────────────────────────────────────

def _red(x):
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, dict):
        return {k: _red(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_red(v) for v in x]
    return x


def _sha(x) -> str:
    return hashlib.sha256(json.dumps(_red(x), sort_keys=True, ensure_ascii=False)
                          .encode()).hexdigest()[:16]


def _firma(paginas) -> tuple[str, str]:
    """(la hoja de resumen entera, el texto de las demás sin espacios). Las tablas se congelan
    por su TEXTO: sus anchos y cortes salen de la fuente de matplotlib, que cambia entre versiones
    (3.10 y 3.11 dan otras coordenadas); su geometría la vigila `test_cotizacion_f4c.py`."""
    resto = "".join(lb.text for p in paginas[1:] for lb in p.labels).replace(" ", "")
    return _sha(asdict(paginas[0])), hashlib.sha256(resto.encode()).hexdigest()[:16]


#: (costeo, resumen y resto en USD, resumen y resto en PEN a 3.7); iguales sobre `f3b36bd`.
#: Re-congelado sobre 0afb41c (cotización sin internos): el cajetín de TODAS las hojas dice
#: «Cotización <nº>» en vez de «Plano <nº>» (el número es de la oferta). El costeo es el mismo y,
#: con el cajetín de antes, las cuatro firmas de hojas dan las de antes (medido): sólo cambió eso.
#: Re-congelado sobre 87e9d38 (V8.9, pendiente 10: el cajetín común): cambia sólo la hoja de
#: resumen; comparadas hoja por hoja, las primitivas difieren sólo en el divisor de la fila 2, el
#: diedro y «Genix Apolo CAD». Costeo y texto del resto, iguales.
#: Re-congelado (hallazgos-del-revisor-en-la-puerta F1, D3): la fila a medida de acero de la mesa
#: lleva su norma («ASTM A36 (≈ EN 10025-2 S235JR)»); con ese campo vacío el costeo da el de antes
#: (02d6203896ab7622, medido) y las cuatro firmas de hojas no cambian.
CONGELADO = {
    "mesa": ("ccb97a8cbfa6d5d4", "77c7697d27ae8052", "a3c506d759920e4b", "45e23b1c05f0a787",
             "4f12f6d6e01da90f"),
    "directo": ("846066ca50189fba", "ca27642a0d1ed258", "8fb16ca271802f7c", "78b62346f5c1e8c5",
                "a0525af72a30c84f"),
    # re-congelado sobre aa88ee5: el tablero (b) lleva el PE en estrella (31 → 34 conductores sin
    # tipo en su fila); precios y hoja de resumen, iguales
    "vfd": ("9f96e6125d640e39", "7cd928e7542086ef", "347f6df5a9b8a562", "2b4066d0aa380ecf",
            "056906d39d42d608"),
}


@pytest.mark.parametrize("nombre", sorted(CONGELADO))
def test_sin_extensiones_costeo_y_cotizacion_congelados(nombre):
    from apolo.library import costeo_extension
    from apolo.services.cobros import costeo

    assert costeo_extension.DE_EXTENSION == {}
    d = {"mesa": _mesa, "directo": _directo, "vfd": _vfd}[nombre]()
    data = costeo(d)
    assert "notas" not in data and "extensiones" not in data
    firma = (_sha(data), *_firma(_paginas(d)), *_firma(_paginas(d, fx=3.7, currency="PEN")))
    assert firma == CONGELADO[nombre]
