"""Plan uniones-que-tocan F1: lo que se declara unido se toca (D1/D1b/D2), el miembro entre dos
piezas cortado a ras (`create_brace`, D3/D3b), el criterio de diseño (D4).

El caso mínimo es el de la plataforma de mantenimiento que lo motivó (fuera del repo: es una
máquina del negocio): dos postes y una riostra TUBO-1X1 girada a mano con `insert_component`,
con los extremos a escuadra, que no llega a ninguno (5 mm) y dos soldaduras declaradas.
"""

from __future__ import annotations

import math

import pytest
from build123d import Box, Cylinder, Pos, Rot

from apolo.doc.document import Document
from apolo.doc.errors import DocumentError
from apolo.kernel.contacto import medir_contacto
from apolo.library.calidad import contacto as ct
from apolo.library.delivery import ROJO, delivery_report
from apolo.services.calidad_contacto import cordones_medidos, uniones_medidas
from apolo.services.delivery_inputs import delivery_inputs

POSTE = 50.8  # TUBO-2X2


# ------------------------------------------------------------------ kernel: la línea de contacto
def test_un_tubo_hueco_a_tope_da_su_perimetro_exterior():
    poste = Box(50, 50, 500)
    tubo = Box(25.4, 25.4, 300) - Box(22, 22, 302)
    r = medir_contacto(poste, Pos(25 + 150, 0, 0) * Rot(0, 90, 0) * tubo)
    assert r["forma"] == "perimetro" and r["dist_mm"] == 0
    assert r["cordon_mm"] == pytest.approx(4 * 25.4, abs=0.2)  # el interior no se suelda
    assert r["total_mm"] == pytest.approx(4 * 25.4 + 4 * 22, abs=0.2)


def test_arista_punto_hueco_y_separadas():
    poste = Box(50, 50, 500)
    tubo = Box(25.4, 25.4, 300) - Box(22, 22, 302)
    girado = Rot(0, 60, 0) * tubo  # extremo a escuadra contra la cara: toca con un canto
    girado = Pos(25 - girado.bounding_box().min.X, 0, 0) * girado
    assert medir_contacto(poste, girado)["forma"] == "arista"
    assert medir_contacto(poste, girado)["cordon_mm"] == 0
    lejos = medir_contacto(poste, Pos(100, 0, 0) * Box(10, 10, 10))
    assert (lejos["forma"], lejos["dist_mm"]) == ("separadas", 70.0)
    # un hueco dentro de la tolerancia (0,1 mm) se cierra: la cara apoyada da su perímetro
    cerca = medir_contacto(Box(50, 50, 10), Pos(0, 0, 10.1) * Box(40, 40, 10))
    assert cerca["forma"] == "perimetro" and cerca["cordon_mm"] == pytest.approx(160, abs=0.5)
    # un redondo tangente a una cara es una línea (se suelda a lo largo), no una arista
    assert medir_contacto(poste, Pos(35, 0, 0) * Cylinder(10, 100))["forma"] == "linea"


# ------------------------------------------------------------------ el caso de la plataforma
def _postes(luz: float = 1000.0) -> tuple[Document, str, str]:
    d = Document("riostra")
    d.execute("set_variable", {"name": "luz", "expression": str(luz)})
    a = d.execute("insert_component", {"component": "TUBO-2X2", "name": "Poste (1)",
                                       "length": 1200, "position": {"z": 600}})
    b = d.execute("insert_component", {"component": "TUBO-2X2", "name": "Poste (2)",
                                       "length": 1200, "position": {"x": "=luz", "z": 600}})
    d.execute("ground", {"name": "g1", "feature": a})
    d.execute("ground", {"name": "g2", "feature": b})
    return d, a, b


def _riostra_a_mano(d: Document, a: str, b: str, luz: float = 1000.0) -> str:
    """Lo que hizo el modelador: un tubo recto girado, 5 mm corto en cada extremo."""
    dx, dz = luz - POSTE, 800.0
    ang = math.degrees(math.atan2(dz, dx))
    largo = math.hypot(dx, dz) - 2 * 5.0 / math.cos(math.radians(ang)) - 25.4 * math.tan(
        math.radians(ang))
    r = d.execute("insert_component", {"component": "TUBO-1X1", "name": "Arriostre lateral",
                                       "length": round(largo, 1), "rotation": {"y": 90 - ang},
                                       "position": {"x": luz / 2, "z": 600}})
    for k, poste in enumerate((a, b)):
        d.execute("fasten", {"name": f"S_arr{k}", "a": r, "b": poste, "kind": "soldadura",
                             "throat_mm": 3, "length_mm": 100})
    return r


def test_la_riostra_girada_a_mano_falla_nombrando_cada_par():
    d, a, b = _postes()
    r = _riostra_a_mano(d, a, b)
    filas = uniones_medidas(d)
    assert all(f["forma"] in ("separadas", "arista", "punto") for f in filas)
    res = ct.contacto_real({"uniones": filas})
    assert res["estado"] == "FALLA"
    assert {m["union"] for m in res["evidencia"]["malas"]} == {"S_arr0", "S_arr1"}
    assert "Arriostre lateral" in res["detalle"] and "create_brace" in res["detalle"]
    assert set(res["piezas"]) == {r, a, b}


def test_la_entrega_la_da_en_rojo_con_el_mensaje_que_guia():
    d, a, b = _postes()
    _riostra_a_mano(d, a, b)
    rep = delivery_report(**delivery_inputs(d, expand=lambda x: x))
    assert rep["veredicto"] == ROJO
    (bl,) = [x for x in rep["bloqueantes"] if x["regla"] == ct.REGLA_ENTREGA]
    assert "S_arr0" in bl["detalle"] and "S_arr1" in bl["detalle"]
    assert "create_brace" in bl["detalle"] and "a ras" in bl["detalle"]


def test_d1b_el_cordon_se_dimensiona_con_lo_medido():
    """La soldadura de la riostra que no toca era «100 mm» declarados: ahora es un error de la
    regla estructural; una que toca se dimensiona con el menor (medido 180 < declarado 1000)."""
    from apolo.services.engineering_rules import structure_rules

    d, a, b = _postes()
    _riostra_a_mano(d, a, b)
    assert cordones_medidos(d) == {"S_arr0": 0.0, "S_arr1": 0.0}
    reglas = {r["regla"]: r for r in structure_rules(d, 0.0, None)}
    assert reglas["soldadura · S_arr0"]["estado"] == "error"
    assert "no se tocan en una línea soldable" in reglas["soldadura · S_arr0"]["detalle"]

    d = Document("cordon")
    lar = d.execute("create_box", {"name": "Larguero", "width": 1000, "depth": 40, "height": 40,
                                   "position": {"z": 520}})
    pata = d.execute("create_box", {"name": "Pata", "width": 50, "depth": 40, "height": 500,
                                    "position": {"z": 250}})
    d.execute("ground", {"name": "g", "feature": pata})
    d.execute("fasten", {"name": "w", "a": lar, "b": pata, "kind": "soldadura",
                         "throat_mm": 3, "length_mm": 1000})
    regla = {r["regla"]: r for r in structure_rules(d, 0.0, None)}["soldadura · w"]
    assert regla["calc"]["entradas"]["longitud"] == "180 mm (medido sobre la línea de contacto)"


def test_el_dimensionado_de_declare_structure_usa_el_cordon_medido():
    from apolo.library.engineering.union_por_defecto import SOLDADURA
    from apolo.services.dimensionado import dimension

    d, a, b = _postes()
    r = _riostra_a_mano(d, a, b)
    # la riostra no toca: 0 → la longitud del criterio (la puerta la marca)
    assert dimension(d, r, a, "soldadura", {})["length_mm"] == SOLDADURA["longitud_mm"]


# ------------------------------------------------------------------ create_brace
def _riostra(d, a, b, **extremos) -> str:
    return d.execute("create_brace", {
        "name": "Riostra lateral", "perfil": "TUBO-1X1",
        "a": {"pieza": a, "punto": {"z": 200}, **extremos.get("a", {})},
        "b": {"pieza": b, "punto": {"x": "=luz", "z": 1000}, **extremos.get("b", {})}})


def test_create_brace_a_tope_toca_y_declara_su_cordon():
    d, a, b = _postes()
    r = _riostra(d, a, b)
    f = d.scene[r]
    assert f.component == "TUBO-1X1"
    alfa = math.atan2(800, 1000)  # el eje va de eje a eje de los postes; la cara es vertical
    assert f.miter == (pytest.approx(math.degrees(alfa), abs=0.1),) * 2
    # el largo exterior: la luz entre caras sobre el eje + la punta de los dos cortes
    luz_eje = (1000 - POSTE) / math.cos(alfa)
    assert f.cut_length == pytest.approx(luz_eje + 25.4 * math.tan(alfa), abs=1.0)
    cordon = 2 * 25.4 + 2 * 25.4 / math.cos(alfa)
    for lado, poste in (("a", a), ("b", b)):
        u = d.fasteners[f"{r}_{lado}"]
        assert (u["a"], u["b"], u["kind"], u["throat_mm"]) == (poste, r, "soldadura", 3.0)
        assert u["length_mm"] == pytest.approx(cordon, abs=0.5)
        inter = f.shape & d.scene[poste].shape
        assert not inter or inter.volume < 1e-3  # a ras: tocar no es chocar
    assert ct.contacto_real({"uniones": uniones_medidas(d)})["estado"] == "OK"
    # la lista de corte lleva su largo (no la caja inclinada) y los ángulos
    from apolo.library.cutlist import cut_list

    (fila,) = [x for x in cut_list(d.scene) if x["nombre"] == "Riostra lateral"]
    assert fila["largo_mm"] == pytest.approx(f.cut_length, abs=0.1)
    assert (fila["espesor_mm"], fila["ancho_mm"]) == (25.4, 25.4)
    assert fila["angulo_1"] == fila["angulo_2"] == f.miter[0]


def test_create_brace_es_parametrico():
    d, a, b = _postes()
    r = _riostra(d, a, b)
    antes = d.scene[r].cut_length
    var = next(c for c in d.commands if c["type"] == "set_variable")
    d.edit(var["id"], {"name": "luz", "expression": "1400"})
    assert d.scene[r].cut_length > antes + 300
    assert ct.contacto_real({"uniones": uniones_medidas(d)})["estado"] == "OK"


def test_create_brace_boca_de_pescado_entre_tubos_redondos():
    d = Document("boca")
    q1 = d.execute("insert_component", {"component": "TUBOR-2", "name": "Poste", "length": 1200,
                                        "position": {"z": 600}})
    q2 = d.execute("insert_component", {"component": "TUBOR-2", "name": "Poste (2)",
                                        "length": 1200, "position": {"x": 800, "z": 600}})
    r = d.execute("create_brace", {
        "name": "Pasamanos", "perfil": "TUBOR-1",
        "a": {"pieza": q1, "punto": {"z": 300}, "union": "boca_de_pescado"},
        "b": {"pieza": q2, "punto": {"x": 800, "z": 900}, "union": "boca_de_pescado"}})
    la, lb = d.fasteners[f"{r}_a"]["length_mm"], d.fasteners[f"{r}_b"]["length_mm"]
    assert la == pytest.approx(lb, abs=0.5) and la > ct.largo_minimo(3.0)
    for q in (q1, q2):
        inter = d.scene[r].shape & d.scene[q].shape
        assert not inter or inter.volume < 1e-3
    assert ct.contacto_real({"uniones": uniones_medidas(d)})["estado"] == "OK"
    with pytest.raises(DocumentError, match="boca_de_pescado"):  # a_tope contra lo redondo
        d.execute("create_brace", {"name": "Otro", "perfil": "TUBOR-1",
                                   "a": {"pieza": q1, "punto": {"z": 700}},
                                   "b": {"pieza": q2, "punto": {"x": 800, "z": 1100}}})


def test_create_brace_inglete_en_un_nodo():
    d, a, b = _postes()
    nodo, pie_a, pie_b = {"x": 500, "z": 1000}, {"z": 400}, {"x": "=luz", "z": 400}
    m1 = d.execute("create_brace", {"name": "Diagonal (1)", "a": {"pieza": a, "punto": pie_a},
                                    "b": {"punto": nodo, "union": "inglete", "hacia": pie_b}})
    m2 = d.execute("create_brace", {"name": "Diagonal (2)",
                                    "a": {"pieza": m1, "punto": nodo, "union": "inglete",
                                          "hacia": pie_a},
                                    "b": {"pieza": b, "punto": pie_b}})
    assert d.scene[m1].miter[1] == pytest.approx(d.scene[m2].miter[0], abs=0.1)
    assert f"{m1}_b" not in d.fasteners  # el vecino todavía no existía: lo declara m2
    assert d.fasteners[f"{m2}_a"]["a"] == m1
    inter = d.scene[m1].shape & d.scene[m2].shape
    assert not inter or inter.volume < 1e-3
    assert ct.contacto_real({"uniones": uniones_medidas(d)})["estado"] == "OK"


def test_create_brace_dice_que_corregir():
    d, a, b = _postes()
    with pytest.raises(DocumentError, match="no toca la pieza"):
        d.execute("create_brace", {"a": {"pieza": a, "punto": {"z": 1500}},  # sobre el poste
                                   "b": {"pieza": b, "punto": {"x": 1000, "z": 200}}})
    with pytest.raises(DocumentError, match="falta `pieza`"):
        d.execute("create_brace", {"a": {"punto": {"z": 200}},
                                   "b": {"pieza": b, "punto": {"x": 1000, "z": 200}}})


# ------------------------------------------------------------------ plantillas y criterio
def test_la_guarda_de_rodillos_suelda_lo_que_toca():
    """create_roller_conveyor v4: la pared interior de la guarda fija se suelda a sus extremos (la
    v3 la declaraba soldada a la exterior, a 77 mm)."""
    d = Document("rodillos")
    d.execute("create_roller_conveyor", {"largo": 1000})
    filas = uniones_medidas(d)
    assert {f["union"] for f in filas if f["union"].startswith("c1_guarda_tr_int")}
    assert ct.malas(filas) == []


def test_el_criterio_de_diseno_manda_a_create_brace():
    from apolo.design.guidelines import design_guidelines

    texto = str(design_guidelines())
    assert "create_brace" in texto and "a ras" in texto
