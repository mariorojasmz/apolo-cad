"""BOM de COMPRA por designación (plan puerta-de-publicacion, F6). Un revisor ciego del transportador
de rodillos halló el MISMO artículo en dos líneas («M10x25 DIN 933» 4 + 40: los del tensado y los
de los ejes) y una barra mecanizada como «COMPRA» sin largo porque su nombre citaba la norma de
OTRA pieza («Eje fijo del rodillo Ø17 h6 (topes axiales con anillos DIN 471…)»)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from build123d import Box, Cylinder

from apolo.library.bom import bom_from_scene
from apolo.library.cutlist import hardware_schedule
from apolo.library.designacion_comercial import designacion, es_comercial, norma_del_nombre


@dataclass
class _F:
    name: str
    shape: object = None
    material: str | None = None
    component: str | None = None
    visible: bool = True
    cut_length: float | None = None
    is_guide: bool = False


def _perno(nombre, largo=25.0, r=5.0):
    return _F(nombre, Cylinder(r, largo))


def test_el_mismo_articulo_es_una_linea_con_sus_ubicaciones():
    scene = {f"t{i}": _perno("Perno M10x25 DIN 933 del tensado") for i in range(4)}
    scene |= {f"e{i}": _perno(f"Perno M10x25 DIN 933 del eje ({i + 1})", r=5.01) for i in range(40)}
    scene |= {"b": _perno("Perno M6x16 DIN 933", 16, 3), "c": _perno("Perno M6x16 DIN 933 de la bandeja", 16, 3)}
    filas = {r["descripcion"]: r for r in bom_from_scene(scene, "acero")}
    m10 = filas["Perno M10x25 DIN 933"]
    assert m10["cantidad"] == 44 and m10["longitud_mm"] == 25 and m10["norma"] == "DIN 933"
    assert m10["ubicaciones"] == [{"nombre": "Perno M10x25 DIN 933 del eje", "cantidad": 40},
                                  {"nombre": "Perno M10x25 DIN 933 del tensado", "cantidad": 4}]
    assert filas["Perno M6x16 DIN 933"]["cantidad"] == 2
    assert sum(1 for d in filas if "M10x25" in d) == 1
    cedula = {r["nombre"]: r for r in hardware_schedule(scene)}
    assert cedula["Perno M10x25 DIN 933"]["cantidad"] == 44  # la cédula agrupa igual


def test_un_largo_o_material_distinto_es_otra_linea():
    scene = {"a": _perno("Perno M10x25 DIN 933 del tensado"),
             "b": _perno("Perno M10x30 DIN 933 del tensado", 30),
             "c": _F("Perno M10x25 DIN 933 del eje", Cylinder(5, 25), material="inoxidable")}
    assert len(bom_from_scene(scene, "acero")) == 3


@pytest.mark.parametrize("nombre,desig", [
    ("Perno M10x25 DIN 933 del tensado", "Perno M10x25 DIN 933"),
    ("Tornillo M6x16 DIN 933 tapa del eje hueco (+Y)", "Tornillo M6x16 DIN 933"),
    ("Anillo de retención DIN 471 17x1 del rodamiento", "Anillo de retención DIN 471 17x1"),
    ("Arandela cuña DIN 434 M8 (guarda cabeza +Y, 1)", "Arandela cuña DIN 434 M8"),
    ("Banda PVC 2 capas (grapas)", None),  # sin norma: el nombre puede ser la especificación
])
def test_designacion(nombre, desig):
    assert designacion(nombre) == desig


@pytest.mark.parametrize("nombre", [
    "Eje fijo del rodillo Ø17 h6 (topes axiales con anillos DIN 471 17x1)",
    "Placa para perno DIN 933 M10",
    "Soporte del tensor con perno M12 DIN 933",
    "Eje M10 DIN 933",  # un eje se fabrica aunque su nombre traiga una designación
])
def test_la_norma_de_otra_pieza_no_hace_comercial(nombre):
    assert not es_comercial(nombre) and norma_del_nombre(nombre) == ""


@pytest.mark.parametrize("nombre", ["Perno M10x25 DIN 933", "Anillo DIN 471 17x1",
                                     "Chaveta DIN 6885 A 8x7x40", "Seeger DIN 472-52"])
def test_la_norma_que_la_designa_si(nombre):
    assert es_comercial(nombre) and norma_del_nombre(nombre)


def test_el_eje_que_nombra_anillos_sale_a_medida_con_su_largo():
    eje = _F("Eje fijo del rodillo Ø17 h6 (topes axiales con anillos DIN 471…)", Box(17, 17, 571))
    (fila,) = bom_from_scene({"e": eje}, "acero")
    assert fila["ref"] == "A-MEDIDA" and fila["categoria"] == "a medida"
    assert fila["longitud_mm"] == pytest.approx(571) and fila["norma"] == ""
