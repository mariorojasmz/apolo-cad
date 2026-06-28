"""Familias de catálogo desde NORMAS: rodamientos ISO 15, tubo HSS cuadrado/rect y
redondo ASTM A500, y perfiles abiertos L (EN 10056) / UPN (DIN 1026) / IPE (EN 10365).
Verifica geometría, conteos y que el peso (kg/m por área de sección) es razonable."""
import math

import pytest

from apolo.library.catalog import CATALOG, build_component, refs_in_category


def test_rodamientos_iso15_completos():
    refs = refs_in_category("rodamientos")
    assert len(refs) == 41
    # una muestra de cada serie con sus dimensiones de contorno ISO 15
    for ref, (d, D, B) in {
        "6000": (10, 26, 8), "6205": (25, 52, 15),
        "6310": (50, 110, 27), "6403": (17, 62, 17),
    }.items():
        c = CATALOG[ref]
        assert (c.specs["d"], c.specs["D"], c.specs["B"]) == (d, D, B)
    shp, cut = build_component("6310")
    assert cut is None and shp.volume > 0


def test_tubo_redondo_hueco_y_cortable():
    refs = refs_in_category("tubos_circulares")
    assert len(refs) == 10
    c = CATALOG["TUBOR-4"]
    assert c.cuttable and c.specs["od"] == 101.6
    shp, cut = build_component("TUBOR-4", 3000)
    assert cut == 3000
    bb = shp.bounding_box()
    assert math.isclose(bb.max.X - bb.min.X, 101.6, abs_tol=0.5)  # Ø exterior
    assert math.isclose(bb.max.Z - bb.min.Z, 3000, abs_tol=0.5)   # extruido en Z
    assert shp.volume < 0.6 * bb.size.X * bb.size.Y * bb.size.Z    # hueco


def test_perfiles_abiertos_presentes_y_construyen():
    refs = set(refs_in_category("perfiles_abiertos"))
    assert len(refs) == 22  # 8 ángulos L + 7 UPN + 7 IPE
    assert {"ANG-50X5", "UPN-120", "IPE-200"} <= refs
    for ref in ("ANG-50X5", "UPN-120", "IPE-200"):
        shp, cut = build_component(ref, 2000)
        assert cut == 2000 and shp.volume > 0


def test_angulo_L_seccion_centrada():
    shp, _ = build_component("ANG-100X10", 1000)
    bb = shp.bounding_box()
    assert math.isclose(bb.max.X - bb.min.X, 100, abs_tol=0.5)  # lado del ángulo
    assert math.isclose(bb.max.Y - bb.min.Y, 100, abs_tol=0.5)


def test_ipe_y_upn_peso_razonable():
    # IPE-200 real ~22.4 kg/m; modelo prismático (sin radios) ~21.4 → tolerancia amplia
    assert 20.0 < CATALOG["IPE-200"].weight < 23.0
    # UPN-80 real ~8.6 kg/m
    assert 8.0 < CATALOG["UPN-80"].weight < 9.5


def test_viga_i_altura_y_ala():
    shp, _ = build_component("IPE-200", 1500)
    bb = shp.bounding_box()
    assert math.isclose(bb.max.Y - bb.min.Y, 200, abs_tol=0.5)  # altura h
    assert math.isclose(bb.max.X - bb.min.X, 100, abs_tol=0.5)  # ancho de ala b


def test_norma_en_specs_de_normalizados():
    """Los normalizados llevan su designación de norma en specs (tornillo DIN 912, bisagra EN 1935)."""
    assert CATALOG["DIN912-M6"].specs.get("norma") == "DIN 912"
    assert CATALOG["BIS-H-75-A"].specs.get("norma") == "EN 1935"


def test_hardware_schedule_expone_norma():
    """La cédula de herraje vuelca el campo `norma` de cada componente normalizado."""
    from apolo.doc import Document
    from apolo.library.cutlist import hardware_schedule

    doc = Document()
    doc.execute("insert_component", {"component": "DIN912-M6", "position": {"x": 0, "y": 0, "z": 0}})
    doc.execute("insert_component", {"component": "BIS-H-75-A", "position": {"x": 100, "y": 0, "z": 0}})
    by_ref = {r["ref"]: r for r in hardware_schedule(doc.scene)}
    assert by_ref["DIN912-M6"]["norma"] == "DIN 912"
    assert by_ref["BIS-H-75-A"]["norma"] == "EN 1935"
