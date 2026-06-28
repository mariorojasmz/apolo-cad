"""F12 Planos pro: callouts de taladros, cotas por sólido, corte A-A, globos + BOM."""
import math

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.drawing import compose_sheet
from apolo.drawing.projection import project_views, section_projection, view_center, world_to_view
from apolo.drawing.svg import sheet_to_svg
from apolo.library.bom import bom_from_scene


def _placa(doc: Document) -> str:
    """Placa 120x80x15 centrada con 4 taladros Ø9 y uno central Ø24, todos pasantes."""
    cid = doc.execute("create_box", {"name": "placa", "width": 120, "depth": 80, "height": 15})
    for x, y in ((-40, -20), (40, -20), (-40, 20), (40, 20)):
        doc.execute(
            "drill_hole",
            {"feature": cid, "position": {"x": x, "y": y, "z": -7.5}, "axis": "z", "diameter": 9, "depth": 0},
        )
    doc.execute(
        "drill_hole",
        {"feature": cid, "position": {"x": 0, "y": 0, "z": -7.5}, "axis": "z", "diameter": 24, "depth": 0},
    )
    return cid


# --------------------------------------------------------------- proyección
def test_circle_detection_exact():
    doc = Document()
    _placa(doc)
    planta = project_views(doc.scene, ["planta"])["planta"]
    radii = sorted(round(c[2], 2) for c in planta.circles)
    assert radii == [4.5, 4.5, 4.5, 4.5, 12.0]
    big = next(c for c in planta.circles if c[2] > 10)
    assert big[0] == pytest.approx(0, abs=1e-6) and big[1] == pytest.approx(0, abs=1e-6)


def test_world_to_view_mapping():
    doc = Document()
    doc.execute("create_box", {"name": "c", "width": 100, "depth": 60, "height": 40})
    c3 = view_center(doc.scene)
    assert world_to_view("planta", (10, 20, 0), c3) == pytest.approx((10, 20))
    assert world_to_view("lateral", (0, 20, 15), c3) == pytest.approx((20, 15))
    assert world_to_view("alzado", (10, 0, 15), c3) == pytest.approx((10, 15))


def test_section_projection_rings():
    doc = Document()
    _placa(doc)
    proj, polygons, cut, axis = section_projection(doc.scene)
    assert cut == pytest.approx(0)
    assert axis == "x"
    assert proj.visible, "el corte debe tener aristas proyectadas"
    # el plano x=0 pasa por el eje del Ø24: la sección son dos rectángulos limpios
    assert len(polygons) == 2
    for rings, _material in polygons:  # ahora cada polígono lleva su material
        assert len(rings) == 1  # sin agujeros interiores
        ys = [p[0] for p in rings[0]]
        zs = [p[1] for p in rings[0]]
        assert max(zs) - min(zs) == pytest.approx(15, abs=1e-3)
        assert max(ys) - min(ys) == pytest.approx(28, abs=1e-3)  # 40 - 12 de radio


# ------------------------------------------------------------------- lámina
def test_hole_callouts_grouped():
    doc = Document()
    _placa(doc)
    model = compose_sheet(doc.scene)
    callouts = {l.text for l in model.labels if "Ø" in l.text}
    assert "4×Ø9" in callouts
    assert "Ø24" in callouts


def test_dims_features_label():
    doc = Document()
    cid = _placa(doc)
    model = compose_sheet(doc.scene, dims_features=[cid])
    assert any(l.text == "placa 120" for l in model.labels)


def test_section_sheet_has_cut_and_trace():
    doc = Document()
    _placa(doc)
    model = compose_sheet(doc.scene, section=True)
    assert any(l.text == "CORTE A-A" for l in model.labels)
    assert len(model.polygons) == 2
    # ≥2 marcas "A": las 2 de la traza en planta (+ las de la rejilla de zonas A–D del marco)
    assert sum(1 for l in model.labels if l.text == "A") >= 2
    assert not any("ISOMÉTRICA" in l.text for l in model.labels)  # el corte la sustituye


def test_bom_sheet_table_and_balloons():
    doc = Document()
    _placa(doc)
    doc.execute("insert_component", {"component": "PATA-REG", "position": {"x": 100, "y": 0, "z": 0}})
    doc.execute("insert_component", {"component": "PATA-REG", "position": {"x": -100, "y": 0, "z": 0}})
    rows = bom_from_scene(doc.scene)
    assert all(r["_rep"] in doc.scene for r in rows)
    pata = next(r for r in rows if r["ref"] != "A-MEDIDA")
    assert pata["cantidad"] == 2

    model = compose_sheet(doc.scene, bom=True)
    assert any(l.text == "LISTA DE MATERIALES" for l in model.labels)
    globos = [c for c in model.circles if c.kind == "globo"]
    assert len(globos) == len(rows)  # un globo por fila
    assert not any(l.text == "PERFIL" for l in model.labels)  # la tabla sustituye al perfil
    # globos en FILA por encima de la planta → no invaden el rótulo/cotas que van debajo
    planta_y = next(l.y for l in model.labels if l.text == "PLANTA")
    assert globos and all(g.y > planta_y for g in globos)


def test_svg_renders_polygons_and_circles():
    doc = Document()
    _placa(doc)
    doc.execute("insert_component", {"component": "PATA-REG", "position": {"x": 100, "y": 0, "z": 0}})
    svg = sheet_to_svg(compose_sheet(doc.scene, section=True, bom=True))
    assert 'fill-rule="evenodd"' in svg  # caras de corte
    assert "<circle" in svg  # globos
    assert "CORTE A-A" in svg


# --------------------------------------------------------------- despiece acotado
def test_cutlist_sheet_table_LxAxE():
    """Tabla DESPIECE con la medida L×A×E de CADA tabla; tablas idénticas colapsan a una fila."""
    from apolo.library.cutlist import cut_list

    doc = Document()
    doc.execute("create_box", {"name": "larguero A", "width": 100, "depth": 18, "height": 2000})
    doc.execute("create_box", {"name": "larguero B", "width": 100, "depth": 18, "height": 2000, "position": {"x": 200}})
    doc.execute("create_box", {"name": "travesano", "width": 400, "depth": 18, "height": 100, "position": {"z": 500}})
    rows = cut_list(doc.scene)
    assert len(rows) == 2  # los 2 largueros idénticos = 1 fila (Cant 2); el travesaño = otra

    model = compose_sheet(doc.scene, cutlist=True)
    texts = [l.text for l in model.labels]
    assert "DESPIECE" in texts and not any(t == "LISTA DE MATERIALES" for t in texts)
    assert any("L×A×E" in t for t in texts)              # cabecera con dimensiones
    assert any("×" in t and "2000" in t for t in texts)  # celda L×A×E del larguero
    assert any(t == "2" for t in texts)                  # cantidad agrupada
    globos = [c for c in model.circles if c.kind == "globo"]
    assert len(globos) == len(rows)                       # un globo por fila, sobre el alzado


def test_bom_path_unaffected_by_refactor():
    """El camino bom=True sigue dando LISTA DE MATERIALES y NO la tabla DESPIECE."""
    doc = Document()
    _placa(doc)
    texts = [l.text for l in compose_sheet(doc.scene, bom=True).labels]
    assert "LISTA DE MATERIALES" in texts and "DESPIECE" not in texts


def test_hardware_table_on_conjunto():
    """hardware=True añade la CÉDULA DE HERRAJE bajo el DESPIECE en la lámina del conjunto."""
    doc = Document()
    doc.execute("create_box", {"name": "tabla madera", "width": 300, "depth": 18, "height": 1200})
    doc.execute("insert_component", {"component": "BIS-H-75-A", "position": {"x": 0, "y": 0, "z": 0}})
    texts = [l.text for l in compose_sheet(doc.scene, cutlist=True, hardware=True).labels]
    assert "DESPIECE" in texts and "CÉDULA DE HERRAJE" in texts
    assert any("BIS-H-75-A" in t for t in texts)  # el herraje aparece en la cédula del conjunto
    # sin hardware no aparece la cédula
    assert "CÉDULA DE HERRAJE" not in [l.text for l in compose_sheet(doc.scene, cutlist=True).labels]


def test_hardware_table_shows_norma_column():
    """La CÉDULA DE HERRAJE lleva columna Norma con la designación del normalizado (EN 1935 / DIN 912)."""
    doc = Document()
    doc.execute("create_box", {"name": "tabla madera", "width": 300, "depth": 18, "height": 1200})
    doc.execute("insert_component", {"component": "BIS-H-75-A", "position": {"x": 0, "y": 0, "z": 0}})
    doc.execute("insert_component", {"component": "DIN912-M6", "position": {"x": 50, "y": 0, "z": 0}})
    texts = [l.text for l in compose_sheet(doc.scene, cutlist=True, hardware=True).labels]
    assert "Norma" in texts          # cabecera de la columna nueva
    assert "EN 1935" in texts        # norma de la bisagra
    assert "DIN 912" in texts        # norma del tornillo


def test_auto_dims_holes_position():
    """auto_dims acota SOLO la posición de cada agujero (sin listar ids), además del Ø ya rotulado."""
    doc = Document()
    _placa(doc)  # placa 120×80×15 con 4 Ø9 + 1 Ø24 pasantes
    base = compose_sheet(doc.scene)
    auto = compose_sheet(doc.scene, auto_dims=True)
    base_txt = [l.text for l in base.labels]
    auto_txt = [l.text for l in auto.labels]
    # "100" = posición X del agujero derecho desde el borde izq (solo aparece con auto_dims)
    assert "100" not in base_txt and "100" in auto_txt
    n_base = sum(1 for l in base.lines if l.kind == "dim")
    n_auto = sum(1 for l in auto.lines if l.kind == "dim")
    assert n_auto > n_base  # las escaleras de posición añaden cotas


def test_member_detail_renders_with_mortise_dims():
    """member_detail dibuja el detalle de una tabla con la posición de su herraje, y reemplaza la planta."""
    doc = Document()
    lid = doc.execute("create_box", {"name": "larguero", "width": 100, "depth": 18, "height": 2000})
    hid = doc.execute("create_box", {"name": "bisagra", "width": 30, "depth": 10, "height": 70, "position": {"x": 70}})
    model = compose_sheet(doc.scene, cutlist=True,
                          member_detail={"member": lid, "locate": [hid], "name": "larguero"})
    texts = [l.text for l in model.labels]
    assert any(t.startswith("DETALLE") for t in texts)   # se dibujó el detalle de la pieza
    assert "PLANTA" not in texts                          # la planta se reemplaza por el detalle
    assert any("bisagra" in t for t in texts)            # cota de posición del herraje (baseline)
    assert model.meta["member_detail"] is True


# ----------------------------------------------------------------- API HTTP
def test_drawing_endpoint_with_options():
    api.DOC = Document()
    cid = _placa(api.DOC)
    client = TestClient(api.app)
    r = client.get(f"/api/drawing.svg?section=true&bom=true&dims={cid}")
    assert r.status_code == 200
    assert "CORTE A-A" in r.text and "LISTA DE MATERIALES" in r.text and "placa 120" in r.text
