"""El pivote que CIERRA un lazo cuenta como eje en `movimiento.coherente` (plan
plegables-en-la-puerta, F2 / D4 y su F0). Fixture sintética equivalente al compás de la mesa
plegable de 1,8 m: tablero raíz, pata con su junta, compás de dos brazos con rodilla y el buje
del tablero en Q, empernado al brazo superior. Sin el lazo declarado falla como «alojamiento
arrastrado» (como hoy); declarado con `distancia` + `punto_coincidente`, es bisagra; un lazo que
no cierra, sin `axis` o que cierra sobre una pieza que se mueve sale SIN_EVALUAR, nunca OK."""

from __future__ import annotations

import pytest
from test_defectos_sembrados import _id, brida_cara_a_cara
from test_movimiento_coherente import _base

from apolo.doc import Document
from apolo.library.calidad.item import FALLA, OK, SIN_EVALUAR
from apolo.library.calidad.movimiento import coherente, juzgar
from apolo.services.calidad_movimiento import movimiento

Y = {"x": 0, "y": 1, "z": 0}
K = {"x": 200, "y": 0, "z": 400}  # la rodilla
Q = {"x": 200, "y": 0, "z": 650}  # el pivote que cierra el lazo (el buje del tablero)


def _compas(buje_se_mueve: bool = False, lim: float = 180.0) -> tuple[Document, dict]:
    """Pata (bisagra H en el tablero, x = 0) → brazo inferior (P, z = 400) → brazo superior
    (K) → buje en Q, soldado al tablero y empernado al brazo superior. Ejes en Y."""
    doc = Document("compas")
    tab = doc.execute("create_box", {"name": "Tablero", "width": 1000, "depth": 100,
                                     "height": 20, "position": {"x": 300, "z": 710}})
    pata = doc.execute("create_box", {"name": "Pata", "width": 30, "depth": 20, "height": 700,
                                      "position": {"z": 350}})
    inf = doc.execute("create_box", {"name": "Brazo inferior del compás", "width": 220,
                                     "depth": 8, "height": 20,
                                     "position": {"x": 100, "y": 14, "z": 400}})
    sup = doc.execute("create_box", {"name": "Brazo superior del compás", "width": 20,
                                     "depth": 8, "height": 270,
                                     "position": {"x": 200, "y": 22, "z": 525}})
    for f, x, z in ((inf, 0, 400), (inf, 200, 400), (sup, 200, 400), (sup, 200, 650)):
        doc.execute("drill_hole", {"feature": f, "position": {"x": x, "y": 40, "z": z},
                                   "axis": "-y", "diameter": 8.5})
    buje = doc.execute("create_cylinder", {"name": "Buje separador", "radius": 4.2, "height": 20,
                                           "position": {"x": 200, "y": 36, "z": 650},
                                           "rotation": {"x": 90}})
    doc.execute("fasten", {"name": "buje_tablero", "a": buje, "b": tab, "kind": "soldadura"})
    doc.execute("fasten", {"name": "perno_q", "a": sup, "b": buje, "kind": "perno", "size": "M8"})
    doc.execute("add_joint", {"name": "j_pata", "type": "giratoria", "parent": tab,
                              "child": pata, "origin": {"x": 0, "y": 0, "z": 700}, "axis": Y,
                              "lower": -100, "upper": 0})
    doc.execute("add_joint", {"name": "j_inf", "type": "giratoria", "parent": pata, "child": inf,
                              "origin": {"x": 0, "y": 0, "z": 400}, "axis": Y,
                              "lower": -lim, "upper": lim})
    doc.execute("add_joint", {"name": "j_rod", "type": "giratoria", "parent": inf, "child": sup,
                              "origin": K, "axis": Y, "lower": -lim, "upper": lim})
    if buje_se_mueve:  # la escalera: el lazo cierra sobre una pieza que mueve otra junta
        doc.execute("add_joint", {"name": "j_otra", "type": "giratoria", "parent": tab,
                                  "child": buje, "origin": {"x": 600, "y": 0, "z": 700},
                                  "axis": Y})
    return doc, {"tablero": tab, "pata": pata, "inf": inf, "sup": sup, "buje": buje}


def _lazo(doc, distancia: float = 250.0, axis: bool = True) -> None:
    eje = {"axis": Y} if axis else {}
    doc.execute_many([
        {"type": "add_constraint", "params": {"name": "lazo_d", "tipo": "distancia",
                                              "joint": "j_inf", "anchor": K, "point": Q,
                                              "value": distancia, **eje}},
        {"type": "add_constraint", "params": {"name": "lazo_q", "tipo": "punto_coincidente",
                                              "joint": "j_rod", "anchor": Q, "point": Q, **eje}},
    ])


def _caso(doc, ids) -> dict:
    (c,) = [c for c in movimiento(doc)["casos"] if {c["a"], c["b"]} == {ids["sup"], ids["buje"]}]
    return c


def test_sin_el_lazo_el_buje_falla_como_hoy():
    doc, ids = _compas()
    c = _caso(doc, ids)
    assert "lazo" not in c and c["coaxial_mueve"] == [ids["sup"]] and c["quietas"] == [ids["buje"]]
    e, m = juzgar(c)
    assert e == FALLA and m.startswith("alojamiento arrastrado"), m


def test_con_el_lazo_declarado_el_buje_es_bisagra():
    doc, ids = _compas()
    _lazo(doc)
    ins = movimiento(doc)
    (c,) = ins["casos"]
    assert c["lazo"]["estado"] == OK and c["lazo"]["pivote"] == "lazo_q"
    assert c["lazo"]["restricciones"] == ["lazo_d", "lazo_q"] and c["lazo"]["motores"] == ["j_pata"]
    (pose,) = c["lazo"]["poses"]
    assert pose["junta"] == "j_pata" and pose["valor"] == -3.0 and pose["residuo_mm"] <= 0.5
    e, m = juzgar(c)
    assert e == OK and m.startswith("bisagra del lazo"), m
    r = coherente({"movimiento": ins})
    assert r["estado"] == OK and r["evidencia"]["lazos"][0]["estado"] == OK


def test_un_lazo_imposible_sale_sin_evaluar():
    """La distancia declarada no es la de la rodilla al pivote: el lazo no cierra en diseño."""
    doc, ids = _compas()
    _lazo(doc, distancia=400.0)
    c = _caso(doc, ids)
    e, m = juzgar(c)
    assert e == SIN_EVALUAR and "no cierra en la pose de diseño" in m, m
    assert coherente({"movimiento": movimiento(doc)})["estado"] == SIN_EVALUAR


def test_un_lazo_que_no_se_mueve_sin_romper_no_es_ok():
    """Los límites del compás (±0,1°) no dejan seguir a la pata 3°: el solver no cierra el
    lazo en la pose de prueba y esa pose sale SIN_EVALUAR (nunca OK)."""
    doc, ids = _compas(lim=0.1)
    _lazo(doc)
    e, m = juzgar(_caso(doc, ids))
    assert e == SIN_EVALUAR and "no vuelve a cerrar" in m, m


def test_sin_axis_el_pivote_sale_sin_evaluar():
    """El comando no exige `axis` (log viejo); la puerta lo pide: sin él, SIN_EVALUAR."""
    doc, ids = _compas()
    _lazo(doc, axis=False)
    e, m = juzgar(_caso(doc, ids))
    assert e == SIN_EVALUAR and "no declara el eje" in m, m


def test_el_lazo_que_cierra_sobre_una_pieza_que_se_mueve_sale_sin_evaluar():
    doc, ids = _compas(buje_se_mueve=True)
    _lazo(doc)
    e, m = juzgar(_caso(doc, ids))
    assert e == SIN_EVALUAR and "pieza raíz" in m and "j_otra" in m, m


@pytest.mark.parametrize("con_lazo", [False, True])
def test_la_chumacera_arrastrada_sigue_fallando(con_lazo):
    """Un lazo declarado en otra parte no tapa el alojamiento arrastrado de verdad."""
    doc = _base()
    brida_cara_a_cara(doc)
    if con_lazo:  # un `punto_coincidente` sobre la junta de la brida, lejos de la chumacera
        jn = next(n for n, j in doc.joints.items() if j.get("type") in ("giratoria", "continua"))
        lejos = {"x": 5000, "y": 0, "z": 0}
        doc.execute("add_constraint", {"name": "lazo_lejos", "tipo": "punto_coincidente",
                                       "joint": jn, "anchor": lejos, "point": lejos, "axis": Y})
        assert list(doc.constraints) == ["lazo_lejos"]
    (c,) = [c for c in movimiento(doc)["casos"]
            if _id(doc, "Chumacera de brida") in (c["a"], c["b"])]
    assert "lazo" not in c
    e, m = juzgar(c)
    assert e == FALLA and m.startswith("alojamiento arrastrado"), m
