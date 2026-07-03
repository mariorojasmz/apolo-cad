"""Chapa metálica (V3 bloque #3): pieza plegada tipo bandeja + desplegado (flat
pattern) con bend allowance, exportable a DXF/SVG para corte láser."""
import io
import math

import ezdxf
import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.commands.registry import CommandError
from apolo.doc import Document, DocumentError
from apolo.drawing import sheet_to_dxf, sheet_to_svg
from apolo.library.sheetmetal import bend, flat_pattern, sheet_metal_solid

CUATRO = ["frente", "atras", "izquierda", "derecha"]


# ----------------------------------------------------------------- geometría 3D
def test_placa_sola():
    s = sheet_metal_solid(200, 150, 2, [], 40, 90, 2)
    bb = s.bounding_box()
    assert s.volume == pytest.approx(200 * 150 * 2, rel=1e-3)
    assert bb.size.Z == pytest.approx(2, abs=1e-6)


def test_una_pestana_altura():
    s = sheet_metal_solid(200, 150, 2, ["frente"], 40, 90, 2)
    assert s.bounding_box().size.Z == pytest.approx(42, abs=0.5)  # base 2 + pestaña 40


def test_bandeja_volumen_y_bbox():
    s = sheet_metal_solid(200, 150, 2, CUATRO, 40, 90, 2)
    bb = s.bounding_box()
    assert bb.size.X == pytest.approx(200, abs=0.5)
    assert bb.size.Y == pytest.approx(150, abs=0.5)
    assert bb.size.Z == pytest.approx(42, abs=0.5)
    assert s.volume > 200 * 150 * 2  # base + 4 pestañas


def test_angulo_no_90():
    """Pestaña a 120° (abierta hacia fuera): sólido válido y más ancho en bbox."""
    s = sheet_metal_solid(200, 150, 2, ["frente"], 40, 120, 2)
    assert s.volume > 0
    assert s.bounding_box().size.Y > 150  # la pestaña inclinada sobresale en +Y


def test_radio_grande_invalido():
    with pytest.raises(ValueError):
        sheet_metal_solid(10, 150, 2, ["frente"], 40, 90, 8)


# --------------------------------------------------------- matemática del bend
def test_bend_allowance_exacto():
    ba, ossb, bd = bend(90, 2, 2, 0.4)
    assert ba == pytest.approx(math.radians(90) * (2 + 0.4 * 2))
    assert ossb == pytest.approx((2 + 2) * math.tan(math.radians(45)))
    assert bd == pytest.approx(2 * ossb - ba)


def test_blank_dimensiones_con_ba():
    """El blank desarrollado = dim_base + Σ(altura − BD) por pestaña presente."""
    ba, ossb, bd = bend(90, 2, 2, 0.4)
    m = flat_pattern("C", 200, 150, 2, CUATRO, 40, 90, 2, 0.4)
    tx, ty = m.meta["blank"]
    esperado_x = 200 + 2 * (40 - bd)
    esperado_y = 150 + 2 * (40 - bd)
    assert tx == pytest.approx(esperado_x, abs=0.1)
    assert ty == pytest.approx(esperado_y, abs=0.1)


def test_blank_crece_por_pestana():
    base = flat_pattern("C", 200, 150, 2, [], 40, 90, 2, 0.4).meta["blank"]
    una = flat_pattern("C", 200, 150, 2, ["derecha"], 40, 90, 2, 0.4).meta["blank"]
    _, _, bd = bend(90, 2, 2, 0.4)
    assert base == [200.0, 150.0]
    assert una[0] == pytest.approx(200 + (40 - bd), abs=0.1)  # solo crece en X
    assert una[1] == pytest.approx(150, abs=0.1)


def test_k_factor_aumenta_blank():
    bajo = flat_pattern("C", 200, 150, 2, ["frente"], 40, 90, 2, 0.3).meta["blank"][1]
    alto = flat_pattern("C", 200, 150, 2, ["frente"], 40, 90, 2, 0.5).meta["blank"][1]
    assert alto > bajo  # más K → más BA → blank más largo


# ------------------------------------------------------------------- desplegado
def test_flat_svg_dxf_no_vacios():
    m = flat_pattern("C", 200, 150, 2, CUATRO, 40, 90, 2, 0.4)
    svg = sheet_to_svg(m)
    assert svg.lstrip().startswith("<svg")
    assert "<path" in svg and "stroke-dasharray" in svg  # contorno + líneas de plegado
    dxf = sheet_to_dxf(m)
    doc = ezdxf.read(io.StringIO(dxf.decode("utf-8")))
    layers = {ly.dxf.name for ly in doc.layers}
    assert "CORTE" in layers and "OCULTA" in layers
    msp = doc.modelspace()
    assert len(msp.query("LWPOLYLINE")) >= 1


def test_flat_sin_pestanas_sin_pliegues():
    m = flat_pattern("C", 200, 150, 2, [], 40, 90, 2, 0.4)
    assert m.meta["blank"] == [200.0, 150.0]
    assert not any(ln.kind == "hidden" for ln in m.lines)  # sin líneas de plegado


def test_flat_cuenta_lineas_plegado():
    m = flat_pattern("C", 200, 150, 2, ["frente", "izquierda"], 40, 90, 2, 0.4)
    assert sum(1 for ln in m.lines if ln.kind == "hidden") == 2


# ------------------------------------------------------------- comando / doc
def test_comando_una_feature():
    d = Document()
    cid = d.execute("create_sheet_metal", {"ancho": 200, "fondo": 150, "lados": CUATRO})
    assert len(d.scene) == 1
    assert d.scene[cid].command_id == cid


def test_validaciones_comando():
    d = Document()
    with pytest.raises((CommandError, DocumentError)):
        d.execute("create_sheet_metal", {"ancho": 10, "radio": 20})  # radio ≥ ancho/2
    with pytest.raises((CommandError, DocumentError)):
        d.execute("create_sheet_metal", {"lados": ["frente", "frente"]})  # duplicado
    assert d.commands == []


def test_edicion_parametrica():
    d = Document()
    cid = d.execute("create_sheet_metal", {"ancho": 200, "fondo": 150, "altura_pestana": 40, "lados": ["frente"]})
    z = lambda: d.scene[cid].shape.bounding_box().size.Z
    assert z() == pytest.approx(42, abs=0.5)
    d.edit(cid, {"ancho": 200, "fondo": 150, "altura_pestana": 80, "lados": ["frente"]})
    assert z() == pytest.approx(82, abs=0.5)


# --------------------------------------------------------------------- API
def test_api_create_y_flat():
    api.DOC = Document("sm-api")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_sheet_metal", "params": {
        "ancho": 200, "fondo": 150, "espesor": 2, "altura_pestana": 40, "lados": CUATRO}})
    assert r.status_code == 200
    fid = next(iter(api.DOC.scene))
    rd = client.get(f"/api/sheetmetal/{fid}/flat.dxf")
    assert rd.status_code == 200
    assert b"CORTE" in rd.content
    assert "attachment" in rd.headers.get("content-disposition", "")
    rs = client.get(f"/api/sheetmetal/{fid}/flat.svg")
    assert rs.status_code == 200 and rs.text.lstrip().startswith("<svg")


def test_api_flat_404_y_tipo():
    api.DOC = Document("sm-api2")
    client = TestClient(api.app)
    assert client.get("/api/sheetmetal/nope/flat.dxf").status_code == 404
    client.post("/api/commands", json={"type": "create_box", "params": {"width": 10, "depth": 10, "height": 10}})
    box = next(iter(api.DOC.scene))
    assert client.get(f"/api/sheetmetal/{box}/flat.dxf").status_code == 400


# ---------------------------------------------------- G2: taladros + radiado
def test_taladros_3d_reducen_volumen():
    s0 = sheet_metal_solid(200, 150, 2, CUATRO, 40, 90, 2)
    s1 = sheet_metal_solid(200, 150, 2, CUATRO, 40, 90, 2, holes=[(0, 0, 20), (-60, 40, 10)])
    esperado = math.pi * 10**2 * 2 + math.pi * 5**2 * 2  # 2 cilindros pasantes Ø20 y Ø10
    assert s0.volume - s1.volume == pytest.approx(esperado, rel=0.05)


def test_taladro_fuera_de_base_rechazado():
    d = Document()
    with pytest.raises((CommandError, DocumentError)):
        d.execute("create_sheet_metal", {"ancho": 200, "fondo": 150, "lados": [],
                                         "holes": [{"x": 120, "y": 0, "d": 10}]})
    assert d.commands == []


def test_taladros_en_desplegado():
    m = flat_pattern("C", 200, 150, 2, CUATRO, 40, 90, 2, 0.4, holes=[(0, 0, 20), (-60, 40, 10)])
    cortes = [c for c in m.circles if c.kind == "corte"]
    assert len(cortes) == 2
    # SVG: círculo de corte (trazo rojo); DXF: círculos en capa CORTE
    svg = sheet_to_svg(m)
    assert svg.count("#c0392b") == 2
    dxf = sheet_to_dxf(m)
    doc = ezdxf.read(io.StringIO(dxf.decode("utf-8")))
    circles = list(doc.modelspace().query("CIRCLE"))
    assert len(circles) == 2 and all(c.dxf.layer == "CORTE" for c in circles)


def test_pliegue_radio_grande_no_rompe():
    """Un radio enorme cae al pliegue vivo (fallback), nunca produce sólido inválido."""
    s = sheet_metal_solid(200, 150, 2, ["frente"], 40, 90, 30)
    assert s.volume > 0


def test_api_create_con_taladros_flat():
    api.DOC = Document("sm-holes")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_sheet_metal", "params": {
        "ancho": 200, "fondo": 150, "espesor": 2, "lados": CUATRO,
        "holes": [{"x": -60, "y": 0, "d": 12}, {"x": 60, "y": 0, "d": 12}]}})
    assert r.status_code == 200
    fid = next(iter(api.DOC.scene))
    dxf = client.get(f"/api/sheetmetal/{fid}/flat.dxf").content
    doc = ezdxf.read(io.StringIO(dxf.decode("utf-8")))
    circles = [c for c in doc.modelspace().query("CIRCLE") if c.dxf.layer == "CORTE"]
    assert len(circles) == 2


# =====================================================================
# V5.5 — Chapa avanzada: multi-pliegue, cutouts en pestañas, K por material
# =====================================================================
from apolo.library.sheetmetal import Child, Flap, k_for_material

MARGIN = 15.0


def _flap_c(**kw):
    """Pestaña frente h=40 (perfil base de los tests V5.5). radio=0 en los tests
    3D para volúmenes exactos (sin fillet); los de flat usan r=2 explícito."""
    base = dict(lado="frente", altura=40, angulo=90)
    base.update(kw)
    return Flap(**base)


# ----------------------------------------------------------- 3D multi-pliegue
def test_flaps_simple_equivale_a_lados():
    s_lados = sheet_metal_solid(200, 150, 2, ["frente", "derecha"], 40, 90, 0)
    s_flaps = sheet_metal_solid(200, 150, 2, [], 40, 90, 0, flaps=[
        Flap(lado="frente", altura=40, angulo=90),
        Flap(lado="derecha", altura=40, angulo=90),
    ])
    assert s_flaps.volume == pytest.approx(s_lados.volume, rel=1e-9)
    bb_a, bb_b = s_lados.bounding_box(), s_flaps.bounding_box()
    assert bb_b.size.X == pytest.approx(bb_a.size.X, abs=1e-6)
    assert bb_b.size.Y == pytest.approx(bb_a.size.Y, abs=1e-6)
    assert bb_b.size.Z == pytest.approx(bb_a.size.Z, abs=1e-6)


def test_perfil_c_volumen_y_bbox():
    # base + pestaña + hem interior: el hem NO agranda el bbox en Y
    s = sheet_metal_solid(200, 150, 2, [], 40, 90, 0,
                          flaps=[_flap_c(child=Child(altura=15, direccion="interior"))])
    bb = s.bounding_box()
    assert bb.size.Y == pytest.approx(150, abs=0.5)
    assert bb.size.Z == pytest.approx(43, abs=0.5)  # 2 + 40 + espesor/2 del hem
    # volumen = base + muro + hem - solape esp/2 x esp del codo
    esperado = 200 * 150 * 2 + 200 * 2 * 40 + 200 * 2 * 15 - 200 * 1 * 1
    assert s.volume == pytest.approx(esperado, rel=1e-6)


def test_perfil_z_crece_hacia_fuera():
    s = sheet_metal_solid(200, 150, 2, [], 40, 90, 0,
                          flaps=[_flap_c(child=Child(altura=15, direccion="exterior"))])
    bb = s.bounding_box()
    assert bb.max.Y == pytest.approx(75 + 15 - 1, abs=0.5)  # el hem sale del footprint
    esperado = 200 * 150 * 2 + 200 * 2 * 40 + 200 * 2 * 15 - 200 * 1 * 1
    assert s.volume == pytest.approx(esperado, rel=1e-6)


def test_hole_en_pestana_resta_material():
    s0 = sheet_metal_solid(200, 150, 2, [], 40, 90, 0, flaps=[_flap_c()])
    s1 = sheet_metal_solid(200, 150, 2, [], 40, 90, 0,
                           flaps=[_flap_c(holes=[(0, 10, 8)])])
    assert s0.volume - s1.volume == pytest.approx(math.pi * 16 * 2, rel=1e-4)


def test_cutout_en_pestana_resta_material():
    s0 = sheet_metal_solid(200, 150, 2, [], 40, 90, 0, flaps=[_flap_c()])
    s1 = sheet_metal_solid(200, 150, 2, [], 40, 90, 0,
                           flaps=[_flap_c(cutouts=[(0, 15, 40, 20)])])
    assert s0.volume - s1.volume == pytest.approx(40 * 20 * 2, rel=1e-6)


def test_hole_invade_pliegue_rechazado():
    with pytest.raises(ValueError, match="invade|v v"):
        sheet_metal_solid(200, 150, 2, [], 40, 90, 2,
                          flaps=[_flap_c(holes=[(0, 37, 8)])])  # v+d/2 > 40-ossb=36


def test_cutout_cruza_pliegue_rechazado():
    with pytest.raises(ValueError, match="invade|v v"):
        sheet_metal_solid(200, 150, 2, [], 40, 90, 2,
                          flaps=[_flap_c(cutouts=[(0, 30, 40, 20)])])  # 30+10 > 36


def test_pestana_corta_para_hijo_rechazada():
    with pytest.raises(ValueError, match="no da para su"):
        sheet_metal_solid(200, 150, 2, [], 40, 90, 2,
                          flaps=[Flap(lado="frente", altura=8, angulo=90,
                                      child=Child(altura=15))])


# ----------------------------------------------------- flat: anclas numéricas
def test_blank_perfil_c_anclado():
    flap = Flap(lado="frente", altura=40, angulo=90,
                child=Child(altura=15, direccion="interior"))
    m = flat_pattern("C", 200, 150, 2, [], 40, 90, 2, 0.4, flaps=[flap])
    _, ty = m.meta["blank"]
    assert ty == pytest.approx(197.79646, abs=0.01)  # meta redondea a 2 decimales


def test_linea_pliegue_hijo_anclada():
    flap = Flap(lado="frente", altura=40, angulo=90,
                child=Child(altura=15, direccion="interior"))
    m = flat_pattern("C", 200, 150, 2, [], 40, 90, 2, 0.4, flaps=[flap])
    by1 = MARGIN + 146.0  # 150 - ossb(4) del frente, sin atras
    hidden = [ln for ln in m.lines if ln.kind == "hidden"]
    assert len(hidden) == 2  # pliegue base + pliegue hijo
    ys = sorted(round(ln.y1, 5) for ln in hidden)
    assert ys[0] == pytest.approx(by1, abs=1e-3)
    assert ys[1] == pytest.approx(by1 + 36.39823, abs=1e-3)


def test_hole_padre_e_hijo_anclados():
    flap = Flap(lado="frente", altura=40, angulo=90, holes=[(25, 10, 8)],
                child=Child(altura=15, direccion="interior", holes=[(-30, 5, 6)]))
    m = flat_pattern("C", 200, 150, 2, [], 40, 90, 2, 0.4, flaps=[flap])
    by1 = MARGIN + 146.0
    cx = MARGIN + 100.0  # sin izquierda/derecha: base 200 centrada
    holes = sorted(((c.x, c.y, c.r) for c in m.circles), key=lambda c: c[1])
    assert holes[0][0] == pytest.approx(cx + 25, abs=1e-3)
    assert holes[0][1] == pytest.approx(by1 + 30.39823, abs=1e-3)
    assert holes[0][2] == pytest.approx(4, abs=1e-6)
    assert holes[1][0] == pytest.approx(cx - 30, abs=1e-3)
    assert holes[1][1] == pytest.approx(by1 + 46.79646, abs=1e-3)
    assert holes[1][2] == pytest.approx(3, abs=1e-6)


def test_cutout_flat_anclado():
    # pestaña SIN hijo con cutout v=12, 60x20 -> y en by1+[18.398, 38.398], x en cx+-30
    flap = Flap(lado="frente", altura=40, angulo=90, cutouts=[(0, 12, 60, 20)])
    m = flat_pattern("C", 200, 150, 2, [], 40, 90, 2, 0.4, flaps=[flap])
    by1 = MARGIN + 146.0
    cx = MARGIN + 100.0
    cortes = [p for p in m.polygons if p.kind == "corte"]
    assert len(cortes) == 2  # contorno + cutout
    xs = sorted({round(x, 3) for x, _ in cortes[1].rings[0]})
    ys = sorted({round(y, 3) for _, y in cortes[1].rings[0]})
    assert xs[0] == pytest.approx(cx - 30, abs=1e-3)
    assert xs[-1] == pytest.approx(cx + 30, abs=1e-3)
    assert ys[0] == pytest.approx(by1 + 18.39823, abs=1e-3)
    assert ys[-1] == pytest.approx(by1 + 38.39823, abs=1e-3)


def test_equivalencia_exacta_flat_simple_vs_flaps():
    # retro: la vía clásica y su equivalente en flaps producen EL MISMO flat
    m1 = flat_pattern("X", 200, 150, 2, CUATRO, 40, 90, 2, 0.4, holes=[(10, -20, 8)])
    m2 = flat_pattern("X", 200, 150, 2, [], 40, 90, 2, 0.4, holes=[(10, -20, 8)],
                      flaps=[Flap(lado=s, altura=40, angulo=90) for s in CUATRO])
    assert m1.meta["blank"] == m2.meta["blank"]
    assert [p.rings[0] for p in m1.polygons] == [p.rings[0] for p in m2.polygons]
    assert [(c.x, c.y, c.r) for c in m1.circles] == [(c.x, c.y, c.r) for c in m2.circles]
    l1 = [(ln.x1, ln.y1, ln.x2, ln.y2, ln.kind) for ln in m1.lines]
    l2 = [(ln.x1, ln.y1, ln.x2, ln.y2, ln.kind) for ln in m2.lines]
    assert l1 == l2


def test_cutout_sale_como_lwpolyline_corte():
    flap = Flap(lado="frente", altura=40, angulo=90, cutouts=[(0, 12, 60, 20)])
    m = flat_pattern("C", 200, 150, 2, [], 40, 90, 2, 0.4, flaps=[flap])
    doc = ezdxf.read(io.StringIO(sheet_to_dxf(m).decode("utf-8", errors="ignore")))
    polys = [e for e in doc.modelspace() if e.dxftype() == "LWPOLYLINE"
             and e.dxf.layer == "CORTE"]
    assert len(polys) >= 2  # contorno + cutout


# --------------------------------------------------------------- K por material
def test_k_for_material_tabla():
    assert k_for_material("acero") == 0.40
    assert k_for_material("acero inoxidable") == 0.45
    assert k_for_material("aluminio") == 0.35
    assert k_for_material("unobtainium") == 0.40  # default
    assert k_for_material(None) == 0.40


def test_api_k_por_material_y_override():
    api.DOC = Document("k-test")
    client = TestClient(api.app)
    r = client.post("/api/commands", json={"type": "create_sheet_metal", "params": {
        "name": "Guarda", "ancho": 200, "fondo": 150, "espesor": 2,
        "lados": ["frente"], "altura_pestana": 40, "radio": 2,
    }})
    feat = r.json()["features"][0]
    fid, cid = feat["id"], feat["command_id"]
    # sin k y material acero (default) -> K=0.40
    d1 = client.get(f"/api/sheetmetal/{fid}/flat.svg").text
    assert "K=0.4" in d1 and "K=0.45" not in d1
    # material inox -> K=0.45 (el blank cambia)
    api.DOC.set_material(fid, "acero inoxidable")
    d2 = client.get(f"/api/sheetmetal/{fid}/flat.svg").text
    assert "K=0.45" in d2 and d2 != d1
    # k explícito GANA sobre el material
    r = client.put(f"/api/commands/{cid}", params={"merge": "true"},
                   json={"params": {"k_factor": 0.38}})
    assert r.status_code == 200
    d3 = client.get(f"/api/sheetmetal/{fid}/flat.svg").text
    assert "K=0.38" in d3
