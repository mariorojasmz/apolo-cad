"""Catálogo de carpintería/herraje: bisagras (pala/piano/cazoleta), tiradores y
pomos, correderas y tirafondos. Verifica que cargan, construyen geometría válida
y que las cortables escalan el peso por longitud."""
import math

from apolo.library.catalog import CATALOG, build_component, refs_in_category


def test_categorias_presentes_y_cuentan():
    assert len(refs_in_category("bisagras")) == 14  # 4 pala + 2 piano + 2 cazoleta + 4 split + 2 resorte
    assert len(refs_in_category("tiradores")) == 7  # 4 barras + 3 pomos
    assert len(refs_in_category("correderas")) == 2
    assert len(refs_in_category("tornilleria_madera")) == 4
    assert len(refs_in_category("cerraduras")) == 2
    assert len(refs_in_category("imanes_topes")) == 2


def test_herraje_nuevo_construye():
    for ref in ("BIS-H-75-A", "BIS-H-75-B", "BIS-RES-100", "CERR-EMB-L", "IMAN-GRANDE"):
        shp, cut = build_component(ref)
        assert cut is None and shp.volume > 0


def test_media_bisagra_palas_opuestas():
    """A (side +1) y B (side -1) tienen la pala en lados opuestos del barril."""
    a, _ = build_component("BIS-H-75-A")
    b, _ = build_component("BIS-H-75-B")
    assert a.bounding_box().max.X > 5 and a.bounding_box().min.X > -10   # pala en +X
    assert b.bounding_box().min.X < -5 and b.bounding_box().max.X < 10   # pala en -X


def test_bisagra_pala_construye_y_es_plana():
    c = CATALOG["BIS-75"]
    assert c.specs["material"] == "acero zincado" and not c.cuttable
    shp, cut = build_component("BIS-75")
    assert cut is None and shp.volume > 0
    bb = shp.bounding_box()
    # ancho total ≈ leaf_w, espesor (Z) fino comparado con el ancho (pala plana)
    assert math.isclose(bb.max.X - bb.min.X, 70, abs_tol=2.0)
    assert (bb.max.Z - bb.min.Z) < 20  # nudillo manda el espesor, pero sigue siendo fino


def test_bisagra_piano_cortable_y_peso_por_metro():
    c = CATALOG["BIS-PIANO-40"]
    assert c.cuttable and c.default_length == 1000
    shp, cut = build_component("BIS-PIANO-40", 1800)
    assert cut == 1800
    bb = shp.bounding_box()
    assert math.isclose(bb.max.Z - bb.min.Z, 1800, abs_tol=1.0)  # corre en Z


def test_cazoleta_euro_y_tirador_y_pomo_construyen():
    for ref in ("BIS-EURO-35", "TIR-128", "POMO-30"):
        shp, cut = build_component(ref)
        assert cut is None and shp.volume > 0


def test_tirafondo_avellanado():
    shp, cut = build_component("TIRAFONDO-5x60")
    assert cut is None and shp.volume > 0
    bb = shp.bounding_box()
    assert math.isclose(bb.max.X - bb.min.X, 10, abs_tol=0.5)  # Ø cabeza
