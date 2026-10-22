"""La cotización sin cobros callados (plan V8.1, § F4c, D-c1 a D-c5), tras la re-verificación por
MCP de la copia 77 (§ Bitácora F4b):

  - D-c1: `quotation`, `get_costing` y el PDF dicen lo que se cobra dos veces (dispositivo sin
    ligar a su pieza 3D) con el monto en riesgo y la llamada que lo arregla, y los cables 3D que
    no se cobran; no se descuenta nada solo;
  - D-c2: un cable 3D sin add_cable que lo cubra es un aviso del ERC y su fila lo dice; su largo
    en la BOM es el del RECORRIDO, no la mayor cota del bbox; `add_cable.piezas` lo liga;
  - D-c3: una pieza de rol eléctrico sin ref (la clavija) sale «sin precio», no por peso;
  - D-c4: ningún texto de las tablas del PDF se sale de su celda ni se corta;
  - D-c5: un perno con su tuerca fundidos en UN sólido son dos hexágonos (el falso ROJO de los
    24 M10 de las garruchas).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from build123d import Box, Cylinder, Plane, Pos, RegularPolygon, extrude
from fastapi.testclient import TestClient
from tablero_electrico import arranque_variador_plc

import apolo.api.main as api
from apolo.commands.electrico import prefijar
from apolo.doc.document import Document
from apolo.drawing.quote import quotation_pages
from apolo.drawing.tabla import ancho_mm, partir
from apolo.library.acceso_herramienta import tool_access_report
from apolo.library.catalog import CATALOG
from apolo.library.costing import CABLE_3D, CABLE_3D_SIN_CUBRIR, costed_bom
from apolo.library.fijadores_geom import reconocer_fijadores
from apolo.library.piezas_electricas import es_rol_electrico, firma_cable, recorrido_mm
from apolo.services.cobros import avisos_cobro, cables_sin_cubrir, costeo
from apolo.services.electrico import chequeo
from apolo.tools.entregable import avisos_de_cobro

CABLE_L = "Cable alimentación 4x4 mm2 220V 3F+T (tablero -> toma)"


def _cable_en_l(doc: Document, nombre: str = CABLE_L, r: float = 7.0) -> str:
    """Un cable 3D que baja 300 mm y corre 500 mm, como los de la 77 (cada tramo se pasa un radio
    en el codo): recorrido 800; la mayor cota del bbox, 500 + r."""
    code = (f"r = {r}\n"
            "a = Pos(0, 0, (300 - r) / 2) * Cylinder(r, 300 + r)\n"
            "b = Pos((500 - r) / 2, 0, 0) * Rotation(0, 90, 0) * Cylinder(r, 500 + r)\n"
            "result = a + b")
    return doc.execute("run_script", {"name": nombre, "code": code})


def _doc_tablero(vfd_3d: bool = True) -> tuple[Document, str | None]:
    d = Document("cot-f4c")
    vfd = (d.execute("insert_component", {"component": "VFD-2K2-220", "name": "Variador de frecuencia"})
           if vfd_3d else None)
    d.execute_many(arranque_variador_plc())
    return d, vfd


def _cmd(doc, tipo, designacion):
    return next(c["id"] for c in doc.commands
                if c["type"] == tipo and c["params"].get("designacion") == designacion)


# ------------------------------------------------------------------ D-c1
def test_el_costeo_dice_el_doble_cobro_con_su_monto_y_su_arreglo():
    d, vfd = _doc_tablero()
    data = costeo(d)
    [aviso] = data["avisos"]
    t2 = _cmd(d, "add_device", "-T2")
    assert aviso["tipo"] == "pieza sin ligar" and aviso["monto_en_riesgo_usd"] == 280.0
    assert data["monto_en_riesgo_usd"] == 280.0
    assert f"edit_command('{t2}', {{\"pieza\": \"{vfd}\"}})" in aviso["arreglo"]
    assert "dos veces" in aviso["detalle"] and "-T2" in aviso["detalle"]
    # no se descuenta solo: el VFD sigue cobrado dos veces
    assert sum(r["cantidad"] for r in data["rows"] if r["ref"] == "VFD-2K2-220") == 2
    # ligado: sin avisos y el dict de siempre (sin claves nuevas)
    d.edit(t2, {"pieza": vfd}, merge=True)
    limpio = costeo(d)
    assert "avisos" not in limpio and "monto_en_riesgo_usd" not in limpio


def test_get_costing_y_quote_pdf_llevan_los_avisos(monkeypatch):
    d, _ = _doc_tablero()
    monkeypatch.setattr(api, "DOC", d)
    client = TestClient(api.app)
    js = client.get("/api/costing.json").json()
    assert js["monto_en_riesgo_usd"] == 280.0 and js["avisos"][0]["tipo"] == "pieza sin ligar"
    r = client.get("/api/quote.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    cab = json.loads(r.headers["X-Apolo-Avisos"])
    assert cab["monto_en_riesgo_usd"] == 280.0 and cab["avisos"] == js["avisos"]
    # la tool `quotation` del MCP los devuelve tal cual
    assert avisos_de_cobro(SimpleNamespace(headers=r.headers)) == cab
    assert avisos_de_cobro(SimpleNamespace(headers={})) == {}
    # sin nada dudoso: sin cabecera
    sano = Document("sano")
    sano.execute("create_box", {"name": "Placa", "width": 100, "depth": 100, "height": 10})
    monkeypatch.setattr(api, "DOC", sano)
    assert "X-Apolo-Avisos" not in client.get("/api/quote.pdf").headers
    assert "avisos" not in client.get("/api/costing.json").json()


def test_el_pdf_tiene_la_hoja_de_avisos_y_el_resumen_lo_dice():
    d, _ = _doc_tablero()
    pages = quotation_pages(d.scene, costeo=costeo(d))
    textos = [lb.text for lb in pages[0].labels]
    assert "ATENCIÓN — AVISOS DE COBRO (hoja 2)" in textos and "280.00 USD" in textos
    assert any("aviso(s) de cobro" in t for t in textos)
    assert pages[1].labels[0].text.startswith("AVISOS DE COBRO")
    sin = quotation_pages(d.scene)  # sin el costeo del documento: lo de siempre, sin hoja de avisos
    assert not any(lb.text.startswith("AVISOS DE COBRO") for p in sin for lb in p.labels)


# ------------------------------------------------------------------ D-c2
def test_el_largo_de_un_cable_3d_es_su_recorrido():
    d = Document("cable")
    _cable_en_l(d)
    [f] = d.scene.values()
    assert recorrido_mm(f.shape) == pytest.approx(800, abs=10)  # bbox mayor: 507
    [fila] = costed_bom(d.scene)
    assert fila["longitud_mm"] == pytest.approx(800, abs=10)
    # una caja recta: el recorrido es su largo
    caja = Document("caja")
    caja.execute("create_box", {"name": "Cable motor 4x2.5 mm2", "width": 2000, "depth": 10, "height": 10})
    assert costed_bom(caja.scene)[0]["longitud_mm"] == pytest.approx(2000)


@pytest.mark.parametrize("nombre,firma", [
    ("Cable motor 4x2.5 mm2 apantallado (variador -> motor)", (4, 2.5)),
    ("Cable setas 4x1 mm2: tablero -> seta cabeza (-Y)", (4, 1.0)),
    ("Cable 5G1,5 a la botonera", (5, 1.5)),
    ("Cable botonera 7×1 mm²", (7, 1.0)),
    ("Cable de mando", None),
    ("Cable 80x40x3", None),
])
def test_firma_del_cable_por_su_nombre(nombre, firma):
    assert firma_cable(nombre) == firma


def test_un_cable_3d_sin_add_cable_avisa_en_el_erc_y_en_su_fila():
    d, _ = _doc_tablero(vfd_3d=False)
    cab = _cable_en_l(d)
    [fid] = [k for k, f in d.scene.items() if f.command_id == cab]
    [regla] = [r for r in chequeo(d)["reglas"] if r["regla"] == "cable 3D sin cobrar"]
    assert regla["estado"] == "aviso" and regla["elementos"] == [fid]
    assert "no se cobra: declara add_cable" in regla["detalle"] and "lígalo" in regla["detalle"]
    assert "recorrido ≈ 0.80 m" in regla["detalle"]
    [fila] = [r for r in costeo(d)["rows"] if r["descripcion"] == CABLE_L]
    assert fila["costo_fuente"].startswith(CABLE_3D_SIN_CUBRIR) and fila["costo_ud_usd"] is None
    [aviso] = [a for a in avisos_cobro(d) if a["tipo"] == "cable 3D sin cobrar"]
    assert aviso["monto_en_riesgo_usd"] is None and f'piezas=["{fid}"]' in aviso["arreglo"]


def test_lo_cubre_el_add_cable_que_lo_liga_o_el_de_su_misma_firma():
    d, _ = _doc_tablero(vfd_3d=False)
    cab = _cable_en_l(d)
    motor = _cable_en_l(d, "Cable motor 4x1.5 mm2 (variador -> motor)", r=5)  # -W1 es CABLE-4G1.5
    assert [c["nombre"] for c in cables_sin_cubrir(d)] == [CABLE_L]  # el del motor lo cubre -W1
    d.execute("add_cable", {"designacion": "-W9", "ref": "CABLE-5G1", "largo_m": 1, "piezas": [cab]})
    assert cables_sin_cubrir(d) == []
    assert not [r for r in chequeo(d)["reglas"] if r["regla"] == "cable 3D sin cobrar"]
    filas = {r["descripcion"]: r for r in costeo(d)["rows"]}
    assert filas[CABLE_L]["costo_fuente"].startswith(CABLE_3D)
    assert not filas[CABLE_L]["costo_fuente"].startswith(CABLE_3D_SIN_CUBRIR)
    # un tramo es de un solo cable; una pieza que no existe, con sugerencia
    with pytest.raises(Exception, match="ya la liga -W9"):
        d.execute("add_cable", {"designacion": "-W8", "ref": "CABLE-5G1", "piezas": [cab]})
    with pytest.raises(Exception, match="no existe"):
        d.execute("add_cable", {"designacion": "-W8", "ref": "CABLE-5G1", "piezas": ["c999"]})
    assert motor


def test_insert_project_prefija_las_piezas_del_cable():
    p = prefijar("add_cable", {"designacion": "-W1", "ref": "CABLE-5G1", "piezas": ["c4", "c7"]},
                 "Faja1", "c20")
    assert p["piezas"] == ["c20_c4", "c20_c7"] and p["designacion"] == "=Faja1-W1"


# ------------------------------------------------------------------ D-c3
@pytest.mark.parametrize("nombre,electrico", [
    ("Clavija industrial 3P+T 32A IP44", True),
    ("Faja · Clavija industrial 3P+T 16A", True),
    ("Prensaestopa M20", True),
    ("Tomacorriente industrial 32A", True),
    ("Canaleta ranurada 40x40", True),
    ("Toma industrial 220V 3F", True),
    ("Puerta · Hoja clavija 1", False),
    ("Clavija de madera Ø8", False),
    ("Toma de fuerza del reductor", False),
    ("Canaleta de desagüe", False),
    ("Placa base A36", False),
])
def test_rol_electrico_por_nombre(nombre, electrico):
    assert es_rol_electrico(nombre) is electrico


def test_la_clavija_sin_ref_sale_sin_precio_no_por_peso():
    d = Document("clavija")
    d.execute("create_box", {"name": "Clavija industrial 3P+T 32A IP44", "width": 70, "depth": 110,
                             "height": 70})
    [fila] = costed_bom(d.scene)
    assert fila["material"] == "acero" and fila["peso_unitario_kg"] == pytest.approx(4.23, abs=0.01)
    assert fila["costo_ud_usd"] is None and fila["costo_total_usd"] is None
    assert fila["costo_fuente"].startswith("sin precio: pieza eléctrica sin ref de catálogo")
    assert "como acero" in fila["costo_fuente"]


# ------------------------------------------------------------------ D-c4
def _grilla(model):
    """Celdas de la tabla de una hoja, leídas de sus líneas: (xs, ys, x0, x1, y0, y1)."""
    H = model.height
    top = H - 30.0
    hz = [ln for ln in model.lines if abs(ln.y1 - ln.y2) < 1e-9 and abs(ln.y1 - top) < 1e-6]
    x0 = min(min(ln.x1, ln.x2) for ln in hz)
    x1 = max(max(ln.x1, ln.x2) for ln in hz)
    filas = sorted({round(ln.y1, 4) for ln in model.lines if abs(ln.y1 - ln.y2) < 1e-9
                    and abs(min(ln.x1, ln.x2) - x0) < 1e-6 and abs(max(ln.x1, ln.x2) - x1) < 1e-6})
    y0 = filas[0]
    cols = sorted({round(ln.x1, 4) for ln in model.lines if abs(ln.x1 - ln.x2) < 1e-9
                   and x0 - 1e-3 <= ln.x1 <= x1 + 1e-3 and min(ln.y1, ln.y2) >= y0 - 1e-3
                   and max(ln.y1, ln.y2) <= top + 1e-3})
    return cols, filas, x0, x1, y0, top


def _textos_fuera_de_su_celda(model) -> list[str]:
    """Renderiza la hoja (matplotlib, como el PDF) y devuelve los textos de la tabla cuya caja no
    cabe en la celda donde está su ancla."""
    import matplotlib.pyplot as plt

    from apolo.drawing.pdf import _figure

    cols, filas, x0, x1, y0, top = _grilla(model)
    fig = _figure(model)
    fig.set_dpi(600)  # el PDF es vectorial: medir sin el hinting de pocos dpi
    try:
        fig.canvas.draw()
        ren = fig.canvas.get_renderer()
        ax = fig.axes[0]
        inv = ax.transData.inverted()
        malos = []
        for lab, art in zip(model.labels, ax.texts):
            if not (x0 < lab.x < x1 and y0 < lab.y < top):
                continue
            (bx0, by0), (bx1, by1) = inv.transform(art.get_window_extent(ren).get_points())
            if lab.anchor == "end":  # ancla en el borde derecho de su celda (menos el relleno)
                cb = min(c for c in cols if c >= lab.x)
                ca = max(c for c in cols if c < cb)
            else:
                ca = max(c for c in cols if c <= lab.x)
                cb = min(c for c in cols if c > ca)
            fa = max(f for f in filas if f <= lab.y)
            fb = min(f for f in filas if f > lab.y)
            tol = 0.05
            if bx0 < ca - tol or bx1 > cb + tol or by0 < fa - tol or by1 > fb + tol:
                malos.append(f"{lab.text!r}: [{bx0:.2f},{bx1:.2f}]×[{by0:.2f},{by1:.2f}] "
                             f"fuera de [{ca:.2f},{cb:.2f}]×[{fa:.2f},{fb:.2f}]")
        return malos
    finally:
        plt.close(fig)


def _doc_largo() -> Document:
    d, _ = _doc_tablero()
    d.execute("insert_component", {"component": "COLSON-5X2-PU-45-A-FT", "name": "Garrucha (+Y, 1)"})
    _cable_en_l(d, "Cable setas 4x1 mm2: seta cabeza (+Y) -> seta cola (+Y), por el ala inferior del C")
    d.execute("create_box", {"name": "Clavija industrial 3P+T 32A IP44", "width": 70, "depth": 110,
                             "height": 70})
    return d


def test_ningun_texto_de_las_tablas_del_pdf_sale_de_su_celda():
    d = _doc_largo()
    data = costeo(d)
    pages = quotation_pages(d.scene, costeo=data,
                            meta={"revisions": [{"rev": "A", "date": "2026-10-21", "note": "Cotización"}]})
    assert len(pages) >= 3  # resumen + avisos + detalle
    for k, page in enumerate(pages[1:], start=2):
        assert _textos_fuera_de_su_celda(page) == [], f"hoja {k}"
    # nada se recorta: cada ref, descripción y fuente entera está en el PDF
    todo = "".join(lb.text for p in pages[1:] for lb in p.labels).replace(" ", "")
    for r in data["rows"]:
        for campo in ("ref", "descripcion", "costo_fuente"):
            assert str(r[campo]).replace(" ", "") in todo, (campo, r[campo])
    for a in data["avisos"]:
        assert a["arreglo"].replace(" ", "") in todo


def test_partir_no_recorta_y_cabe():
    texto = "COLSON-5X2-PU-45-A-FT cable modelado en 3D: se compra por metro (add_cable) × 2.5"
    lineas = partir(texto, 20.0, 2.6)
    assert all(ancho_mm(ln, 2.6) <= 20.0 for ln in lineas)
    assert "".join(lineas).replace(" ", "") == texto.replace(" ", "")
    assert lineas[0].endswith("-")  # la ref larga se parte tras un guión, no a media sílaba


# ------------------------------------------------------------------ D-c5
def _juego_m10(z_garrucha: float = 100.0, placa: float = 8.0):
    """El juego de la faja 77 (c1229): vástago + cabeza bajo la placa de la garrucha + tuerca
    sobre la placa base, fundidos en UN sólido."""
    h, tp, tb = z_garrucha, 4.0, placa
    z0, z1 = h - tp - 1, h + tb + 10
    shank = Pos(0, 0, (z0 + z1) / 2) * Cylinder(5, z1 - z0)
    head = Pos(0, 0, h - tp - 3.2) * extrude(Plane.XY * RegularPolygon(9.24, 6), 3.2, both=True)
    nut = Pos(0, 0, h + tb + 4) * extrude(Plane.XY * RegularPolygon(9.24, 6), 4, both=True)
    return shank + head + nut


def test_perno_y_tuerca_fundidos_son_dos_hexagonos():
    juego = _juego_m10()
    fjs = reconocer_fijadores(juego.solids()[0])
    assert sorted(f.tipo for f in fjs) == ["cabeza_hex", "tuerca"]
    cabeza = next(f for f in fjs if f.tipo == "cabeza_hex")
    assert cabeza.eje[2] == pytest.approx(-1.0)  # la cabeza mira al piso, bajo la garrucha
    assert cabeza.base[2] == pytest.approx(96.0, abs=0.01) and cabeza.altura == pytest.approx(6.4, abs=0.01)
    tuerca = next(f for f in fjs if f.tipo == "tuerca")
    caras = sorted([tuerca.base[2], tuerca.base[2] + tuerca.altura * tuerca.eje[2]])
    assert caras == pytest.approx([108.0, 116.0], abs=0.01)  # sobre la placa base (z 100..108)


def test_las_garruchas_de_la_77_ya_no_dan_rojo():
    escena = {
        "c1": SimpleNamespace(name="Placa de la garrucha", component=None, is_guide=False,
                              shape=Pos(0, 0, 98) * Box(140, 120, 4)),
        "c2": SimpleNamespace(name="Placa base garrucha A36", component=None, is_guide=False,
                              shape=Pos(0, 0, 104) * Box(160, 140, 8)),
        "c3": SimpleNamespace(name="Pernos M10×25 + tuercas de garruchas", component=None,
                              is_guide=False, shape=Pos(95.3 / 2, 76.2 / 2, 0) * _juego_m10()),
    }
    rep = tool_access_report(escena, catalog=CATALOG)
    assert rep["sin_herramienta"] == [] and rep["evaluados"] == 2 and rep["ok"] == 2
