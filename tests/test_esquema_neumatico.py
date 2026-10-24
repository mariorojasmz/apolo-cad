"""La lámina del esquema neumático ISO 1219 (plan V8.9 F5, D11).

- El caso canónico (un empujador: FRL + válvula de corte con escape + 5/2 monoestable +
  reguladores de caudal + silenciadores + cilindro de doble efecto con detectores), armado con
  `add_device`/`add_tubo` en el carril, sale en SVG, PDF y DXF sin solapes de texto
  (`scripts/_check_overlaps.py`), sin rótulos sobre los símbolos ni símbolos encimados, con la
  designación de cada aparato y cada bobina referida a su borne del tablero.
- Dos cilindros (5/3 de centro cerrado + 5/2 biestable) en el orden del ciclo declarado.
- Sin aire, un 400 que dice qué falta; las opciones mal escritas, con su corrección.
- La ruta de la API (`POST /api/drawing/spec` con `esquema: "neumatico"`) y el DWG por ODA.

El catálogo todavía no trae regulador de caudal, silenciador ni presostato (D16 los pide; la
F1a no los sumó): los tests los inyectan como refs de PRUEBA con el mismo loader del catálogo.
"""

from __future__ import annotations

import importlib.util
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apolo.doc.document import Document
from apolo.drawing.dxf import sheet_to_dxf
from apolo.drawing.esquema import PILOTAJE
from apolo.drawing.pdf import sheet_to_pdf
from apolo.drawing.svg import sheet_to_svg
from apolo.library.catalog import CATALOG
from apolo.library.loader import _component_from_item
from apolo.services import neumatica_esquema as NE
from apolo.services.errors import ServiceError

RAIZ = Path(__file__).resolve().parents[1]


def _overlaps():
    spec = importlib.util.spec_from_file_location("_check_overlaps", RAIZ / "scripts" / "_check_overlaps.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CAUDAL = {"C": 1.2, "b": 0.3}
FUENTE = "ref de PRUEBA (tests/test_esquema_neumatico.py): sin ficha"
PRUEBA = [
    {"ref": "PRUEBA-REG-CAUDAL", "name": "Regulador de caudal de prueba", "builder": "box",
     "params": {"width": 20, "depth": 20, "height": 40}, "weight": 0.05, "specs": {"cost": 5},
     "neumatico": {"funcion": "RZ", "simbolo": "regulador_caudal", "fuente": FUENTE,
                   "puertos": [{"id": "1", "rol": "entrada", "rosca": "G1/8"},
                               {"id": "2", "rol": "salida", "rosca": "G1/8"}],
                   "modelo": {"tipo": "regulador_caudal", "caudal": CAUDAL, "C_regulado": [0.01, 1.2],
                              "p_max_bar": 10}}},
    {"ref": "PRUEBA-SILENCIADOR", "name": "Silenciador de prueba", "builder": "box",
     "params": {"width": 10, "depth": 10, "height": 20}, "weight": 0.01, "specs": {"cost": 2},
     "neumatico": {"funcion": "RZ", "simbolo": "silenciador", "fuente": FUENTE,
                   "puertos": [{"id": "1", "rol": "entrada", "rosca": "G1/8"}],
                   "modelo": {"tipo": "silenciador", "caudal": CAUDAL}}},
    {"ref": "PRUEBA-PRESOSTATO", "name": "Presostato de prueba", "builder": "box",
     "params": {"width": 30, "depth": 30, "height": 50}, "weight": 0.1, "specs": {"cost": 20},
     "neumatico": {"funcion": "BP", "simbolo": "presostato", "fuente": FUENTE,
                   "puertos": [{"id": "1", "rol": "entrada", "rosca": "G1/8"}],
                   "modelo": {"tipo": "presostato", "p_conmuta_bar": [1, 10], "histeresis_bar": 0.5,
                              "p_max_bar": 10}}},
]


@pytest.fixture
def refs(monkeypatch):
    for item in PRUEBA:
        monkeypatch.setitem(CATALOG, item["ref"], _component_from_item(item, "aire_comprimido"))


def dev(ref: str, des: str, **p) -> dict:
    return {"type": "add_device", "params": {"ref": ref, "designacion": des, **p}}


def tubo(desde: str, hasta: str, ref: str = "TUBO-PU-6") -> dict:
    return {"type": "add_tubo", "params": {"desde": desde, "hasta": hasta, "ref": ref}}


def wire(*puntos: str) -> dict:
    return {"type": "add_wire", "params": {"puntos": list(puntos)}}


def canonico() -> list[dict]:
    """El empujador de D17 en el carril: aire, la bobina y los dos detectores cableados a la
    bornera del tablero."""
    return [
        dev("FR-G14", "-AZ1", ajustes={"p_regulada_bar": 6}),
        dev("CORTE-ESC-G14", "-QM1"),
        dev("VAL-52-MONO-G18", "-QM2", ubicacion="+CAMPO"),
        dev("PRUEBA-REG-CAUDAL", "-RZ1"),
        dev("PRUEBA-REG-CAUDAL", "-RZ2"),
        dev("PRUEBA-SILENCIADOR", "-RZ3"),
        dev("PRUEBA-SILENCIADOR", "-RZ4"),
        dev("PRUEBA-SILENCIADOR", "-RZ5"),
        dev("CIL-ISO15552-32", "-MM1", servicio={"carrera_mm": 300}),
        dev("SENS-IND-M18-PNP", "-BG1", ubicacion="+CAMPO"),
        dev("SENS-IND-M18-PNP", "-BG2", ubicacion="+CAMPO"),
        {"type": "add_device", "params": {"ref": "BORNE-PASO-2.5", "designacion": "-X1",
                                          "ubicacion": "+TAB1", "cantidad": 6}},
        tubo("-AZ1:2", "-QM1:1", "TUBO-PU-8"),
        tubo("-QM1:2", "-QM2:1", "TUBO-PU-8"),
        tubo("-QM2:4", "-RZ1:1"),
        tubo("-RZ1:2", "-MM1:A"),
        tubo("-QM2:2", "-RZ2:1"),
        tubo("-RZ2:2", "-MM1:B"),
        tubo("-QM2:5", "-RZ3:1"),
        tubo("-QM2:3", "-RZ4:1"),
        tubo("-QM1:3", "-RZ5:1"),
        wire("-QM2:A1", "-X1:1"),
        wire("-BG1:BK", "-X1:2"),
        wire("-BG2:BK", "-X1:3"),
    ]


DETECTORES = {"detectores": {"-BG1": {"cilindro": "-MM1", "en": "atras"},
                             "-BG2": {"cilindro": "-MM1", "en": "adelante"}}}


@pytest.fixture
def empujador(refs) -> Document:
    d = Document("Empujador")
    d.execute_many(canonico())
    return d


def dos_cilindros() -> list[dict]:
    return [
        dev("FR-G12", "-AZ1", ajustes={"p_regulada_bar": 6}),
        dev("CORTE-ESC-G12", "-QM1"),
        dev("VAL-53-CC-G18", "-QM2"),
        dev("VAL-52-BI-G18", "-QM3"),
        dev("CIL-ISO15552-50", "-MM1", servicio={"carrera_mm": 200}),
        dev("CIL-ISO15552-32", "-MM2", servicio={"carrera_mm": 100}),
        dev("PRUEBA-PRESOSTATO", "-BP1", ajustes={"p_conmuta_bar": 4}),
        tubo("-AZ1:2", "-QM1:1", "TUBO-PU-10"),
        tubo("-QM1:2", "-QM2:1", "TUBO-PU-8"),
        tubo("-QM2:1", "-QM3:1", "TUBO-PU-8"),
        tubo("-QM3:1", "-BP1:1", "TUBO-PU-4"),
        tubo("-QM2:4", "-MM1:A"),
        tubo("-QM2:2", "-MM1:B"),
        tubo("-QM3:4", "-MM2:A"),
        tubo("-QM3:2", "-MM2:B"),
    ]


# ── comprobaciones de la lámina ──────────────────────────────────────────────────────────────


def _caja_texto(lab):
    return _overlaps()._bbox(lab)


def _area(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return ix * iy


def _segmentos(m):
    """Los trazos del esquema como segmentos (líneas, bordes de polígono, caja de un círculo)."""
    from apolo.drawing.esquema import ESTILOS

    out = [((ln.x1, ln.y1), (ln.x2, ln.y2)) for ln in m.lines if ln.kind in ESTILOS]
    for p in m.polygons:
        if p.kind in ESTILOS:
            r = p.rings[0]
            out += list(zip(r, r[1:] + r[:1]))
    for c in m.circles:
        if c.kind in ESTILOS:
            q = [(c.x - c.r, c.y - c.r), (c.x + c.r, c.y - c.r), (c.x + c.r, c.y + c.r), (c.x - c.r, c.y + c.r)]
            out += list(zip(q, q[1:] + q[:1]))
    return out


def _cruza(seg, caja) -> bool:
    """¿El segmento entra en la caja? (Liang-Barsky)"""
    (x1, y1), (x2, y2) = seg
    x0, y0, xa, ya = caja
    dx, dy = x2 - x1, y2 - y1
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x1 - x0), (dx, xa - x1), (-dy, y1 - y0), (dy, ya - y1)):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            t0 = max(t0, t)
        else:
            t1 = min(t1, t)
        if t0 > t1:
            return False
    return True


def _sin_solapes(m) -> None:
    ov = _overlaps()
    assert ov.overlaps(m) == []  # texto sobre texto (el detector del repo)
    segs = _segmentos(m)
    for lab in m.labels:  # ningún rótulo sobre un trazo del esquema
        x0, y0, x1, y1 = ov._bbox(lab)
        caja = (x0 + 0.2, y0 + 0.2, x1 - 0.2, y1 - 0.2)
        assert not any(_cruza(s, caja) for s in segs), f"«{lab.text}» pisa un trazo del esquema"
    meta = m.meta["esquema_neumatico"]
    cajas, colgados = meta["simbolos"], meta["colgados"]
    nombres = sorted(cajas)
    for i, a in enumerate(nombres):  # ni dos símbolos encimados (salvo el silenciador en su escape)
        for b in nombres[i + 1:]:
            if colgados.get(a) == b or colgados.get(b) == a:
                continue
            assert _area(cajas[a], cajas[b]) < 0.5, f"{a} y {b} se pisan"
    W, H = m.width, m.height
    for lab in m.labels:  # todo dentro del marco
        x0, y0, x1, y1 = ov._bbox(lab)
        assert 10 <= x0 and x1 <= W - 10 and 10 <= y0 and y1 <= H - 10, lab.text


def _textos(m) -> list[str]:
    return [lab.text for lab in m.labels]


# ── el caso canónico ─────────────────────────────────────────────────────────────────────────


def test_el_empujador_sale_en_tres_formatos_sin_solapes(empujador):
    m = NE.lamina(empujador, DETECTORES)
    _sin_solapes(m)
    meta = m.meta["esquema_neumatico"]
    assert meta["avisos"] == [] and meta["formato"] == "A3" and meta["columnas"] == ["-MM1"]
    textos = _textos(m)
    for des in ("-AZ1", "-QM1", "-QM2", "-RZ1", "-RZ2", "-RZ3", "-RZ4", "-RZ5", "-MM1", "-BG1", "-BG2"):
        assert des in textos, des
    # P3: la bobina y los detectores, referidos a su BORNE del tablero (la bornera), no a una lámina
    assert "A1: +TAB1-X1:1" in textos
    assert "+TAB1-X1:2" in textos and "+TAB1-X1:3" in textos
    assert "p = 6 bar" in textos and "Ø32/12 c300" in textos and "5/2 monoestable" in textos
    # la línea de pilotaje del regulador de presión y las envolventes van a trazos
    assert any(ln.kind == PILOTAJE for ln in m.lines)

    svg = sheet_to_svg(m)
    assert svg.startswith("<svg") and "-QM2" in svg and "stroke-dasharray" in svg
    assert sheet_to_pdf(m).startswith(b"%PDF")
    import ezdxf

    dxf = ezdxf.read(io.StringIO(sheet_to_dxf(m).decode("utf-8")))
    assert "ESQUEMA" in dxf.layers and "APOLO_TRAZOS" in dxf.linetypes
    tipos = {e.dxftype() for e in dxf.modelspace()}
    assert {"LINE", "CIRCLE", "HATCH", "TEXT"} <= tipos


def test_el_empujador_coloca_las_filas_por_ISO_1219_2(empujador):
    """El aire sube: fuente y FRL abajo, válvula al medio, reguladores, cilindro arriba; la
    válvula bajo su cilindro y los silenciadores colgados de sus escapes."""
    cajas = NE.lamina(empujador, DETECTORES).meta["esquema_neumatico"]["simbolos"]

    def cy(d):
        return (cajas[d][1] + cajas[d][3]) / 2

    def cx(d):
        return (cajas[d][0] + cajas[d][2]) / 2

    assert cy("-AZ1") < cy("-QM1") < cy("-QM2") < cy("-RZ1") < cy("-MM1") < cy("-BG1")
    assert cajas["-QM2"][0] < cx("-MM1") < cajas["-QM2"][2]  # la válvula bajo su cilindro
    assert cajas["-RZ3"][3] <= cajas["-QM2"][1] + 8.5 and cajas["-RZ4"][3] <= cajas["-QM2"][1] + 8.5
    assert cajas["-RZ5"][1] < cajas["-QM1"][1]  # el escape de la de corte, también silenciado
    assert cx("-BG1") < cx("-BG2")  # atrás a la izquierda (vástago a la derecha)


def test_sin_cablear_lo_dice(refs):
    d = Document("x")
    d.execute_many([c for c in canonico() if c["type"] != "add_wire"])
    textos = _textos(NE.lamina(d, DETECTORES))
    assert "A1: sin cablear" in textos and textos.count("sin cablear") == 2


# ── dos cilindros ────────────────────────────────────────────────────────────────────────────


def test_dos_cilindros_en_el_orden_del_ciclo(refs):
    d = Document("Dos cilindros")
    d.execute_many(dos_cilindros())
    m = NE.lamina(d, {"ciclo": ["-MM2", "-MM1"]})
    _sin_solapes(m)
    meta = m.meta["esquema_neumatico"]
    assert meta["columnas"] == ["-MM2", "-MM1", "-BP1"] and meta["avisos"] == []
    cajas = meta["simbolos"]
    assert cajas["-MM2"][0] < cajas["-MM1"][0]
    assert cajas["-QM3"][0] < cajas["-QM2"][0]  # cada válvula bajo su cilindro
    textos = _textos(m)
    assert "5/3 centro cerrado" in textos and "5/2 biestable" in textos
    assert "14A1: sin cablear" in textos and "12A1: sin cablear" in textos
    # sin ciclo, el orden de designación
    sin = NE.lamina(d).meta["esquema_neumatico"]["columnas"]
    assert sin == ["-MM1", "-MM2", "-BP1"]
    # el colector une la de corte con las dos válvulas y el presostato: derivaciones con punto
    llenos = [c for c in m.circles if c.kind == "simbolo_lleno"]
    assert len(llenos) >= 2
    for fmt in (sheet_to_svg, sheet_to_pdf, sheet_to_dxf):
        assert fmt(m)


def test_muchos_cilindros_agrandan_la_hoja(refs):
    cmds = [dev("FR-G14", "-AZ1", ajustes={"p_regulada_bar": 6}), dev("CORTE-ESC-G14", "-QM1"),
            tubo("-AZ1:2", "-QM1:1")]
    for k in range(1, 5):
        cmds += [dev("VAL-52-MONO-G18", f"-QM{k + 1}"), dev("CIL-ISO15552-32", f"-MM{k}"),
                 tubo("-QM1:2", f"-QM{k + 1}:1"), tubo(f"-QM{k + 1}:4", f"-MM{k}:A"),
                 tubo(f"-QM{k + 1}:2", f"-MM{k}:B")]
    d = Document("cuatro")
    d.execute_many(cmds)
    m = NE.lamina(d)
    assert m.meta["esquema_neumatico"]["formato"] == "A2"
    _sin_solapes(m)


# ── errores accionables ──────────────────────────────────────────────────────────────────────


def test_sin_aire_un_400_que_dice_que_falta():
    with pytest.raises(ServiceError) as e:
        NE.lamina(Document("vacio"))
    assert e.value.status_code == 400
    assert "no tiene circuito de aire" in e.value.detail and "add_tubo" in e.value.detail


@pytest.mark.parametrize("opciones, texto", [
    ({"ciclo": ["-MM9"]}, "-MM9; cilindros: -MM1"),
    ({"ciclo": "-MM1"}, "lista de cilindros"),
    ({"orden": []}, "claves no reconocidas orden"),
    ({"detectores": {"-BG9": {"cilindro": "-MM1"}}}, "-BG9 no existe"),
    ({"detectores": {"-BG1": {"cilindro": "-QM2"}}}, "«-QM2» no es un cilindro"),
    ({"detectores": {"-BG1": {"cilindro": "-MM1", "en": "medio"}}}, "«atras»"),
])
def test_opciones_mal_escritas(empujador, opciones, texto):
    with pytest.raises(ServiceError) as e:
        NE.lamina(empujador, opciones)
    assert texto in e.value.detail


# ── la API ───────────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client():
    from apolo.api import main as api

    return api, TestClient(api.app)


def test_la_ruta_de_los_planos_da_la_lamina(client, empujador):
    api, c = client
    api.DOC = empujador
    r = c.post("/api/drawing/spec", json={"esquema": "neumatico", "format": "svg", **{"neumatica": DETECTORES}})
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg")
    assert "A1: +TAB1-X1:1" in r.text
    r = c.post("/api/drawing/spec", json={"esquema": "neumatico", "format": "dxf"})
    assert r.status_code == 200 and b"APOLO_TRAZOS" in r.content
    r = c.post("/api/drawing/spec", json={"esquema": "neumatico"})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_la_ruta_sin_aire_y_con_un_esquema_que_no_existe(client):
    api, c = client
    api.DOC = Document("vacio")
    r = c.post("/api/drawing/spec", json={"esquema": "neumatico", "format": "svg"})
    assert r.status_code == 400 and "no tiene circuito de aire" in r.json()["detail"]
    r = c.post("/api/drawing/spec", json={"esquema": "electrico"})
    assert r.status_code == 400 and "esquemas: neumatico" in r.json()["detail"]


def test_dwg_por_oda_o_su_400(client, empujador):
    from apolo.drawing import dwg

    api, c = client
    api.DOC = empujador
    r = c.post("/api/drawing/spec", json={"esquema": "neumatico", "format": "dwg"})
    if dwg.disponible().get("disponible"):
        assert r.status_code == 200 and r.content[:4] == b"AC10"
    else:
        assert r.status_code == 400 and "ODA" in r.json()["detail"]
