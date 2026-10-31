"""La madera, el plástico y el metal que no salen del catálogo se leen bien (plan
puerta-fuera-de-catalogo, F1: D1 y D2 con sus ajustes de la F0).

Los casos «reales» son las piezas de la tanda de 15 máquinas que la F0 puso en el modo 1 (reporte
de la F0, § B), con su nombre REAL y una geometría mínima.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from apolo.doc.document import Document
from apolo.library.apariencia import acabado_de
from apolo.library.bom_compra import norma_de_madera, norma_de_material
from apolo.library.bom_comprable import motivo
from apolo.library.calidad.registro import VERSION_REGISTRO
from apolo.library.engineering.mass import feature_mass
from apolo.library.lint_soldadura import motivo_no_soldable
from apolo.library.madera_clase import GRUPO_DE_ESPECIE, GRUPOS_E010, grupo_e010
from apolo.library.materials import (DEFAULT_DENSITY, _norm, density, es_madera, has_yield,
                                     known_material, resolve_material, yield_strength,
                                     young_modulus)
from apolo.services.calidad_bom import insumo_bom


# ---------------------------------------------------------------- D1: la tabla de materiales

@pytest.mark.parametrize("material, clave, kg_m3", [
    ("contrachapado", "contrachapado", 460), ("triplay de 18 mm", "contrachapado", 460),
    ("terciado estructural", "contrachapado", 460), ("plywood EN 636-2", "contrachapado", 460),
    ("contrachapado fenólico EN 314-2", "contrachapado fenolico", 700),
    ("triplay fenólico 18 mm", "contrachapado fenolico", 700),
    ("tablero fenólico", "contrachapado fenolico", 700),
    ("fenólico 18 mm", "contrachapado fenolico", 700),  # como se vende en Lima
    ("MDF EN 622-5", "mdf", 745), ("OSB/3 EN 300", "osb", 610),
    ("poliuretano", "poliuretano", 1260), ("PU 92 ShA", "poliuretano", 1260),
    ("policarbonato", "policarbonato", 1200), ("PC Makrolon", "policarbonato", 1200),
    ("EPDM 70 ShA", "epdm", 1130), ("caucho EPDM", "epdm", 1130),
    ("latón CW614N", "laton", 8470), ("latón", "laton", 8470), ("laton", "laton", 8470),
    ("CuZn39Pb3", "laton", 8470), ("cobre", "cobre", 8930), ("Cu-ETP", "cobre", 8930),
])
def test_d1_cada_material_nuevo_pesa_lo_suyo(material, clave, kg_m3):
    assert _norm(material) == clave
    assert density(material) == pytest.approx(kg_m3 * 1e-9)
    assert known_material(material) and density(material) != DEFAULT_DENSITY


@pytest.mark.parametrize("material, clave", [
    # el PRODUCTO antes que la especie (ajuste F0 de D1)
    ("contrachapado de copaiba", "contrachapado"), ("triplay de copaiba", "contrachapado"),
    ("triplay fenólico de eucalipto", "contrachapado fenolico"),
    # y la especie antes que el genérico (regla de siempre)
    ("madera copaiba", "copaiba"), ("madera de pino radiata", "radiata"), ("madera", "madera"),
    # el HDF no tiene fuente: no se tabula (el genérico «madera» de siempre, si lo dice)
    ("madera HDF EN 622-5", "madera"), ("HDF", ""),
])
def test_d1_el_producto_va_antes_que_la_especie(material, clave):
    assert _norm(material) == clave


def test_d1_los_tableros_son_madera_y_no_se_sueldan():
    for m in ("contrachapado", "triplay fenólico", "MDF", "OSB"):
        assert es_madera(m), m
        assert motivo_no_soldable(m, "acero") is not None, m
    for m in ("poliuretano", "policarbonato", "EPDM"):
        assert not es_madera(m) and motivo_no_soldable(m, "acero") is not None, m
    assert acabado_de("contrachapado fenolico") == "madera"
    assert acabado_de("epdm") == "caucho" and acabado_de("cobre") == "bronce"


def test_d1_resistencia_con_su_fuente_y_sin_inventar():
    assert (young_modulus("contrachapado"), yield_strength("contrachapado")) == (8131.0, 20.2)
    assert (young_modulus("triplay fenólico"), yield_strength("triplay fenólico")) == (
        10048.0, 40.2)
    assert (young_modulus("MDF"), young_modulus("OSB")) == (1900.0, 3500.0)
    assert (young_modulus("PC"), yield_strength("PC")) == (2400.0, 65.0)
    assert (young_modulus("latón CW614N"), yield_strength("latón CW614N")) == (97000.0, 220.0)
    assert young_modulus("cobre") == 110000.0
    # el Cu-ETP blando no tiene Rp0,2 mínimo; los elastómeros, σy: no se tabulan
    assert not has_yield("cobre") and not has_yield("EPDM") and not has_yield("poliuretano")
    # el E de la copaiba que usa hoy Apolo no cambia: el del grupo E.010 va aparte (F4)
    assert young_modulus("copaiba") == 11000.0
    assert GRUPOS_E010["C"]["e_min"] == 5394.0 and GRUPOS_E010["C"]["fm"] == 9.8


def _f(nombre):
    return SimpleNamespace(name=nombre, material=None, component=None)


@pytest.mark.parametrize("nombre, material", [
    # mesa-inox-2000 (F0, modo 1): el sellador de PU se pesaba como ACERO
    ("Cordón adhesivo-sellador de refuerzo intermedio de repisa (compra: MS/PU apto zona "
     "alimentaria, Sikaflex-11 FC+ o eq., filete 4x4 a ambos flancos)", "poliuretano"),
    # mesa-trabajo-ensamble-1200: el tablero NOMBRA su producto
    ("Repisa inferior (triplay fenólico 18 mm EN 636-2)", "contrachapado fenolico"),
    ("Tablero de trabajo 1200x600x18 contrachapado", "contrachapado"),  # gana a las 3 cotas
    ("Fondo de MDF 18 mm", "mdf"),
    # soporte-paneles-techo-4: el conductor de tierra es de cobre
    ("Conductor de tierra 6 mm2 Cu", "cobre"), ("Tubo de cobre 15x1x500", "cobre"),
    ("Inserto roscado M6 de latón", "laton"), ("Junta de goma EPDM", "epdm"),
    ("Visor de policarbonato 300x200x4", "policarbonato"),
    # lo que sólo MENCIONA el tablero no es el tablero
    ("Tornillo para MDF 4x30", "acero"), ("Bisagra del tablero fenólico", "acero"),
    ("Perilla fenólica del tablero", "acero"), ("Soporte PC del tablero", "acero"),
])
def test_d1_el_rol_nombra_el_material(nombre, material):
    assert resolve_material(_f(nombre), None, "acero") == material


# ---------------------------------------------------------------- D2: la clase de la madera

@pytest.mark.parametrize("material, nombre, norma", [
    ("copaiba, Grupo C (E.010), CH ≤ 22 %", "Peldaño", "E.010 Grupo C"),
    ("madera copaiba grupo C RNE E.010", "Calzo", "E.010 Grupo C"),
    ("madera copaiba", "Peldaño (copaiba, Grupo C (E.010))", "E.010 Grupo C"),
    ("madera", "Repisa (triplay fenólico 18 mm EN 314-2)", "EN 314-2"),
    ("madera", "Tablero de trabajo (triplay fenólico 18 mm EN 636-2)", "EN 636-2"),
    ("madera", "Larguero C24 (EN 338)", "EN 338 C24"),
    # el material gana sobre el nombre
    ("pino radiata C16 (EN 338)", "Repisa (EN 636-2)", "EN 338 C16"),
    # sin la norma, un «grupo C» suelto no es clase; la tornillería del nombre tampoco
    ("madera copaiba grupo C", "Calzo", ""),
    ("madera", "Tablero (con tornillos DIN 7997)", ""),
    ("madera", "Repisa C24", ""),  # una clase en el nombre, sólo junto a su norma
    ("madera copaiba", "Tarugo de copaiba D10x40 brazo-pata ext. (-X)", ""),
])
def test_d2_la_norma_de_la_madera_del_material_o_del_nombre(material, nombre, norma):
    assert norma_de_madera(material, nombre) == norma
    assert norma_de_material(material, nombre, "barra") == norma


def test_d2_la_clase_de_las_especies_sale_sólo_con_fuente():
    assert GRUPO_DE_ESPECIE == {"copaiba": "C"}  # radiata, haya y eucalipto: la escribe quien modela
    assert grupo_e010("Grupo D (E.010)") == "D" and grupo_e010("Grupo C") == ""


def _fila(material, norma):
    return {"ref": "A-MEDIDA", "material": material, "norma": norma, "longitud_mm": 300}


@pytest.mark.parametrize("material, norma, falla, texto", [
    ("madera copaiba", "", True, "Grupo C (E.010)"),     # la sugerencia es la de su especie
    ("copaiba", "E.010 Grupo C", False, ""),
    ("copaiba", "E.010 Grupo D", False, ""),            # más conservador: vale
    ("copaiba", "E.010 Grupo A", True, "Grupo C según E.010"),
    ("contrachapado", "", True, "EN 636-2"),
    ("pino radiata", "", True, "UNE 56544"),
    ("latón", "", True, "CW614N"),
    ("latón CW614N", "CW614N", False, ""),
    ("cobre", "Cu-ETP (CW004A)", False, ""),
    ("acero zincado", "", True, "acero A36"),
])
def test_d2_el_motivo_de_cada_fila(material, norma, falla, texto):
    m = motivo(_fila(material, norma))
    assert bool(m) is falla, m
    assert texto in (m or "")


@pytest.mark.parametrize("material, nombre, norma", [
    ("latón CW614N (EN 12164)", "Inserto", "EN 12164 (CW614N)"),
    ("latón CuZn39Pb3", "Inserto", "CuZn39Pb3"),
    ("latón ASTM B16 C36000", "Buje", "ASTM B16 (C36000)"),
    ("latón", "Inserto roscado M6 para madera tablero FI", ""),
    ("cobre", "Conductor de tierra 6 mm2 Cu", "Cu-ETP (CW004A)"),
    ("cobre", "Barra de cobre Cu-ETP EN 13601", "EN 13601 (Cu-ETP)"),
    ("cobre recocido", "Pletina", ""),  # un cobre calificado sin aleación no se inventa
])
def test_d1_la_norma_del_laton_y_del_cobre(material, nombre, norma):
    assert norma_de_material(material, nombre, "barra") == norma


# ---------------------------------------------------------------- los casos reales en la BOM

def _pieza(d, nombre, material, **kw):
    fid = d.execute("create_box", {"name": nombre, "width": kw.get("w", 100),
                                   "depth": kw.get("p", 50), "height": kw.get("h", 18),
                                   "position": {"x": kw.get("x", 0)}})
    d.set_material(fid, material)
    return fid


def test_real_los_casos_del_modo_1_en_la_bom():
    d = Document("modo 1")
    ok = {
        _pieza(d, "Calzo de apoyo del. izq.", "madera copaiba, Grupo C (E.010), CH ≤ 22 %"),
        _pieza(d, "Repisa inferior (triplay fenólico 18 mm EN 314-2)", "madera", x=200),
        _pieza(d, "Inserto roscado M6 para madera tablero FI", "latón CW614N", x=400, w=10,
               p=10, h=12),
        _pieza(d, "Conductor de tierra 6 mm2 Cu", "cobre", x=600, w=300, p=3, h=3),
    }
    malas = {
        _pieza(d, "Calzo de apoyo del. der.", "madera copaiba", x=800),
        _pieza(d, "Inserto roscado M6 para madera tablero FD", "laton", x=1000, w=10, p=10,
               h=12),
    }
    falla = {c["pieza"] for c in insumo_bom(d)["incompletas"]}
    assert falla == malas and not (falla & ok)


def test_real_el_sellador_de_pu_no_pesa_como_acero():
    d = Document("sellador")
    fid = d.execute("create_box", {
        "name": "Cordón adhesivo-sellador de refuerzo intermedio de repisa (compra: MS/PU apto "
                "zona alimentaria, Sikaflex-11 FC+ o eq., filete 4x4 a ambos flancos)",
        "width": 500, "depth": 4, "height": 4})
    fm = feature_mass(d.scene[fid])
    assert fm["material"] == "poliuretano"
    assert fm["masa_kg"] == pytest.approx(500 * 4 * 4 * 1.26e-6, abs=1e-4)  # 10 g, no 63 g


def test_real_el_contrachapado_de_copaiba_pesa_como_contrachapado():
    d = Document("tablero")
    fid = _pieza(d, "Entrepaño", "contrachapado de copaiba", w=1000, p=400, h=18)
    assert feature_mass(d.scene[fid])["masa_kg"] == pytest.approx(1000 * 400 * 18 * 4.6e-7,
                                                                   rel=1e-3)


def test_el_registro_sube_a_33():
    """La F1 subió el registro a 33; las fases siguientes lo suben más (D10): no baja de 33 y
    el historial la nombra."""
    from apolo.library.calidad.historial_registro import __doc__ as historial
    assert int(VERSION_REGISTRO) >= 33 and "v33 (puerta-fuera-de-catalogo F1" in historial
