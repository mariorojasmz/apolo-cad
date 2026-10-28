"""La lista de corte mide la pieza, no lo que dice su comando (plan lista-de-corte-medida, F1).

El caso que lo motivó es la zanca de la plataforma de mantenimiento (fuera del repo: es una
máquina del negocio): un UPN-120 de `insert_component` girado con `transform` y con las puntas
recortadas por dos `add_joinery` rebaje (cabeza vertical, pie horizontal), que salía «recto,
L 854,1»; y los peldaños de chapa estriada de 3 mm plegada en U, que salían con «espesor» 40.
Aquí, su equivalente mínimo con comandos.
"""

from __future__ import annotations

import pytest

from apolo.doc.document import Document
from apolo.kernel.corte_barra import _CACHE, medir_barras
from apolo.library.chapa_ficha import desplegado
from apolo.library.cutlist import cut_list, cut_list_csv
from apolo.library.cutlist_medida import detalle_corte
from apolo.library.miembro import _largo_exterior

UPN = {"component": "UPN-120", "orientacion": {"largo": "z", "abre_hacia": "+y"}}


def _doc(ref: dict, largo: float = 1200.0) -> tuple[Document, str, str]:
    d = Document("corte")
    ctx = d.execute("create_box", {"name": "Apoyo", "width": 10, "depth": 10, "height": 10,
                                   "position": {"x": 3000}})
    p = d.execute("insert_component", {**ref, "name": "Zanca", "length": largo})
    return d, ctx, p


def _rebaje(d, ctx, p, pos, w, h, prof) -> None:
    d.execute("add_joinery", {"name": "corte", "type": "rebaje", "feature_a": ctx, "feature_b": p,
                              "position": dict(zip("xyz", pos)), "width": w, "height": h,
                              "depth": prof})


def _fila(d, nombre="Zanca") -> dict:
    (fila,) = [r for r in cut_list(d.scene) if r["nombre"] == nombre]
    return fila


def _zanca() -> tuple[Document, str]:
    """UPN girado 50° y cortado: cabeza por un plano VERTICAL, pie por uno HORIZONTAL."""
    d, ctx, p = _doc(UPN)
    d.execute("transform", {"feature": p, "rotate": {"y": 50}})
    bb = d.scene[p].shape.bounding_box()
    _rebaje(d, ctx, p, (bb.max.X - 150 + 500, 0, 0), 1000, 400, 2000)
    _rebaje(d, ctx, p, (0, 0, bb.min.Z + 150 - 500), 2000, 400, 1000)
    return d, p


def test_zanca_girada_y_recortada_da_sus_dos_angulos_y_el_largo_exterior():
    d, p = _zanca()
    fila = _fila(d)
    # el eje sube 40° sobre la horizontal: la cara vertical forma 50° con la sección recta y la
    # horizontal 40°
    assert fila["corte"] == "inglete"
    assert sorted((fila["angulo_1"], fila["angulo_2"])) == [40.0, 50.0]
    (m,) = medir_barras(d.scene[p].shape, (55, 120))
    assert fila["largo_mm"] == pytest.approx(_largo_exterior(d.scene[p].shape, m["eje"]), abs=0.1)
    assert fila["largo_mm"] < 1200 - 100  # las puntas recortadas no se compran como barra entera
    assert (fila["espesor_mm"], fila["ancho_mm"]) == (55.0, 120.0)  # la sección, no 55×100
    assert "L 1200" in fila["aviso"] and "lo medido" in fila["aviso"]  # lo declarado no manda
    assert detalle_corte(fila) in ("∠40°/50°", "∠50°/40°")


def test_la_riostra_de_create_brace_da_lo_que_declara():
    d = Document("riostra")
    a = d.execute("insert_component", {"component": "TUBO-2X2", "name": "Poste (1)",
                                       "length": 1200, "position": {"z": 600}})
    b = d.execute("insert_component", {"component": "TUBO-2X2", "name": "Poste (2)",
                                       "length": 1200, "position": {"x": 1000, "z": 600}})
    r = d.execute("create_brace", {"name": "Riostra", "perfil": "TUBO-1X1",
                                   "a": {"pieza": a, "punto": {"z": 200}},
                                   "b": {"pieza": b, "punto": {"x": 1000, "z": 1000}}})
    f, fila = d.scene[r], _fila(d, "Riostra")
    assert (fila["angulo_1"], fila["angulo_2"]) == f.miter  # el orden y el valor del comando
    assert fila["largo_mm"] == pytest.approx(f.cut_length, abs=0.1)
    assert "aviso" not in fila


def test_un_perfil_a_escuadra_no_cambia():
    d, _ctx, p = _doc(UPN, 1000)
    fila = _fila(d)
    bb = d.scene[p].shape.bounding_box()
    assert fila["corte"] == "recto" and fila["angulo_1"] is fila["angulo_2"] is None
    assert fila["largo_mm"] == round(bb.max.Z - bb.min.Z, 1) == 1000.0
    assert "aviso" not in fila and "extremos" not in fila
    assert detalle_corte(fila) == ""


def test_la_u_de_chapa_da_su_espesor_y_su_desarrollo():
    d = Document("chapa")
    c = d.execute("create_sheet_metal", {"name": "Peldaño", "ancho": 118, "fondo": 600,
                                         "espesor": 3, "lados": ["izquierda", "derecha"],
                                         "altura_pestana": 37, "rotation": {"x": 180}})
    d.execute("pattern_linear", {"feature": c, "count": 3, "spacing": {"x": -250, "z": -180}})
    fila = _fila(d, "Peldaño")
    ficha = d.scene[c].chapa
    blank = sorted(desplegado(ficha, 0.40).meta["blank"])  # el de export_flat_pattern, acero K 0,40
    assert fila["espesor_mm"] == 3.0
    assert [fila["ancho_mm"], fila["largo_mm"]] == pytest.approx(blank, abs=0.05)
    assert fila["ancho_mm"] == pytest.approx(118 + 2 * 37 - 4 * 5 + 3.1416 * (2 + 0.4 * 3), abs=0.1)
    assert fila["pliegues"] == 2 and fila["corte"] == "chapa"
    assert fila["cantidad"] == 3  # las copias del patrón heredan la ficha
    assert detalle_corte(fila) == "desarrollo · 2 pliegues"
    assert "chapa (2 pliegues)" in cut_list_csv([fila])


def test_un_extremo_con_muesca_es_corte_especial():
    d, ctx, p = _doc(UPN, 1000)
    bb = d.scene[p].shape.bounding_box()
    _rebaje(d, ctx, p, (bb.max.X, 0, bb.max.Z), 60, 400, 100)  # escalón en la punta
    fila = _fila(d)
    assert fila["corte"] == "especial"
    assert [e["corte"] for e in fila["extremos"]] == ["especial", "recto"]
    assert detalle_corte(fila) == "∠especial (ver plano)/0°"
    assert "especial (ver plano)" in cut_list_csv([fila])


def test_una_colisa_cerrada_no_es_un_corte_y_dos_planos_son_despunte():
    d, ctx, p = _doc(UPN, 1000)
    bb = d.scene[p].shape.bounding_box()
    _rebaje(d, ctx, p, (0, bb.min.Y + 3, bb.max.Z - 60), 30, 20, 15)  # agujero en el alma
    assert _fila(d)["corte"] == "recto"
    d2, ctx2, t = _doc({"component": "TUBO-2X2"}, 1000)
    d2.execute("transform", {"feature": t, "rotate": {"y": 45}})
    bb = d2.scene[t].shape.bounding_box()
    _rebaje(d2, ctx2, t, (bb.max.X - 60 + 500, 0, 0), 1000, 400, 2000)  # dos cortes enteros
    _rebaje(d2, ctx2, t, (0, 0, bb.max.Z - 60 + 500), 2000, 400, 1000)
    fila = _fila(d2)
    assert fila["corte"] == "despunte"
    assert {"corte": "dos_planos", "angulos": [45.0, 45.0]} in fila["extremos"]


def test_la_medida_se_cachea_por_la_forma_con_su_referencia():
    d, p = _zanca()
    forma = d.scene[p].shape
    primera = medir_barras(forma, (55, 120))
    hit = _CACHE[(id(forma), (55, 120))]
    assert hit[0] is forma and medir_barras(forma, (55, 120)) == primera
    # una sección que no es la de la pieza (otra ficha): no se mide como esa barra
    assert medir_barras(forma, (40, 80)) == [None]
