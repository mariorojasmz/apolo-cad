"""La rosca del pie nivelador no se compra dos veces (plan pie-nivelador, F3: D7 con la Bitácora §
F0).

Una unión `perno` entre un pie nivelador y la pieza que lleva su rosca (el buje de soldar, la
placa roscada) declarada «espárrago M10» sin pieza modelada compraba un espárrago que ya viene con
el pie (la mesa inox de 2 m: «Espárrago M10 DIN 267 (unión declarada sin pieza modelada)» ×4). En
los modelos finales de la tanda no aparece sólo porque los modeladores escribieron «incluido (sin
perno)» o usaron `contacto`: por eso los casos son sintéticos.
"""

from __future__ import annotations

import pytest

from apolo.doc import Document
from apolo.library.bom import bom_from_scene
from apolo.library.tornilleria_declarada import _es_pie_nivelador, filas_declaradas

PIE_INOX = "Pie nivelador higiénico M10 del. izq. (compra: Ganter GN 20-75-M10-100)"
NOTA = "espárrago M10 DIN 267 del pie en el buje"


def _bb(d, fid):
    return d.scene[fid].shape.bounding_box()


def _pie_y_buje(d, nombre_pie=PIE_INOX):
    pie = d.execute("create_box", {"name": nombre_pie, "width": 75, "depth": 75, "height": 60})
    z = _bb(d, pie).max.Z
    buje = d.execute("create_box", {"name": "Buje de soldar M10", "width": 30, "depth": 30,
                                    "height": 40, "position": {"z": z + 10}})
    return pie, buje


def _declara(d, a, b, nota=NOTA, size="M10", qty=1, name="pie_buje"):
    d.execute("fasten", {"name": name, "a": a, "b": b, "kind": "perno", "size": size,
                         "qty": qty, "nota": nota})


def test_pie_a_mano_y_su_buje_no_compran_esparrago():
    # antes: la MISMA unión con una pieza que no es pie compra el espárrago (sin largo)
    d = Document("pie-antes")
    taco, buje = _pie_y_buje(d, "Taco de apoyo")
    _declara(d, taco, buje, qty=4)
    (fila,) = filas_declaradas(d.scene, d.fasteners)
    assert fila["descripcion"].startswith("Espárrago M10") and fila["cantidad"] == 4
    # después: con el pie nivelador el vástago ES el fijador
    d = Document("pie-despues")
    pie, buje = _pie_y_buje(d)
    _declara(d, pie, buje, qty=4)
    assert filas_declaradas(d.scene, d.fasteners) == []
    _declara(d, buje, pie, name="buje_pie")  # el orden del par no importa
    assert filas_declaradas(d.scene, d.fasteners) == []


def test_pie_de_catalogo_y_su_placa_no_compran_perno():
    d = Document("pie-catalogo")
    pie = d.execute("insert_component", {"component": "PIE-M10-40"})
    z = _bb(d, pie).max.Z
    placa = d.execute("create_box", {"name": "Placa base de la pata", "width": 60, "depth": 60,
                                     "height": 8, "position": {"z": z - 10}})
    _declara(d, pie, placa, nota="rosca M10 en la placa")
    assert filas_declaradas(d.scene, d.fasteners) == []


def test_los_pernos_de_anclaje_de_otra_metrica_siguen_comprandose():
    d = Document("pie-anclaje")
    pie = d.execute("insert_component", {"component": "PIE-BA-M10-40"})
    z = _bb(d, pie).min.Z
    piso = d.execute("create_box", {"name": "Placa de piso", "width": 300, "depth": 200,
                                    "height": 10, "position": {"z": z - 5}})
    _declara(d, pie, piso, size="M12", qty=2, nota="perno de anclaje M12x40 DIN 933",
             name="pie_piso")
    filas = filas_declaradas(d.scene, d.fasteners)
    assert [(r["ref"], r["longitud_mm"], r["cantidad"]) for r in filas] == [
        ("PERNO-HEX-M12", 40, 2)]


def test_otra_metrica_en_el_nombre_del_pie_sigue_comprando():
    d = Document("pie-m16")
    pie, buje = _pie_y_buje(d, "Pie nivelador (-Y) M16x50 articulado base Ø100")
    _declara(d, pie, buje, size="M12", nota="perno M12x30 DIN 933 de la base")
    filas = filas_declaradas(d.scene, d.fasteners)
    assert [(r["ref"], r["cantidad"]) for r in filas] == [("PERNO-HEX-M12", 1)]


def test_union_perno_comun_sin_pieza_modelada_sigue_comprando_su_perno():
    d = Document("perno-comun")
    a, b = _pie_y_buje(d, "Pie de amigo")  # «pie» que no es un apoyo: una riostra
    _declara(d, a, b, nota="M10x25 DIN 933", qty=2)
    filas = filas_declaradas(d.scene, d.fasteners)
    assert [(r["ref"], r["longitud_mm"], r["cantidad"]) for r in filas] == [
        ("PERNO-HEX-M10", 25, 2)]


def test_la_contratuerca_declarada_se_compra_y_la_modelada_sigue_en_la_bom():
    d = Document("pie-contratuerca")
    pie, buje = _pie_y_buje(d)
    _declara(d, pie, buje, nota="espárrago M10 del pie con contratuerca DIN 934")
    # el espárrago no; la contratuerca que nadie modeló, sí
    assert [(r["ref"], r["cantidad"]) for r in filas_declaradas(d.scene, d.fasteners)] == [
        ("TUERCA-M10", 1)]
    # modelada: deja de ser declarada y la compra su fila de la BOM
    zb = _bb(d, buje).min.Z
    tuerca = d.execute("insert_component", {"component": "TUERCA-M10",
                                            "position": {"z": zb - 2}})
    assert filas_declaradas(d.scene, d.fasteners) == []
    bom = bom_from_scene(d.scene, d.default_material())
    assert [r["cantidad"] for r in bom if r["ref"] == "TUERCA-M10"] == [1]
    assert tuerca in d.scene


@pytest.mark.parametrize("nombre,es,metrica", [
    (PIE_INOX, True, "M10"),
    ("Pie nivelador (-X,-Y) — inox AISI 304, vástago roscado métrico", True, None),
    ("Pie nivelador articulado M12x100 ISO 261, base Ø80, SW19 (compra)", True, "M12"),
    ("Transportador · Pie nivelador (+Y, motriz)", True, None),
    ("Pie articulado nivelador M16", True, "M16"),
    ("Nivelador M8", True, "M8"),
    ("Pie de amigo M10", False, None),
    ("Pata delantera izquierda", False, None),
    ("Placa del pie nivelador M10", False, None),  # la placa no es el pie
    ("Espárrago M10 del pie nivelador", False, None),
])
def test_el_pie_se_reconoce_por_su_rol(nombre, es, metrica):
    d = Document("rol")
    fid = d.execute("create_box", {"name": nombre, "width": 10, "depth": 10, "height": 10})
    assert _es_pie_nivelador(d.scene[fid]) == (es, metrica)


def test_el_pie_de_catalogo_se_reconoce_por_su_ficha_con_cualquier_nombre():
    d = Document("ficha")
    fid = d.execute("insert_component", {"component": "PIE-M12-50", "name": "Apoyo (+X)"})
    assert _es_pie_nivelador(d.scene[fid]) == (True, "M12")
    perno = d.execute("insert_component", {"component": "PERNO-HEX-M10", "length": 25})
    assert _es_pie_nivelador(d.scene[perno]) == (False, None)
