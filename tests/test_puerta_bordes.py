"""Puerta de publicación F6 — distancia al BORDE y PASO de los agujeros de perno (EN 1993-1-8,
tabla 3.3): la medida en la geometría (`library/borde_agujero.py`), el control puro
(`library/calidad/bordes.py`), la fuente mecánica sobre un documento y el criterio 5 de
`join_bolted`, que no deja un agujero bajo el mínimo. Un revisor ciego halló agujeros a 1,5 mm del
canto de una placa de tensor y a 3 mm del extremo de un larguero que nadie miraba."""

import pytest
from build123d import Box, Cylinder, Pos, Rot

from apolo.commands.registry import CommandError
from apolo.doc import Document
from apolo.doc.errors import DocumentError
from apolo.kernel.rayo import Rayos
from apolo.library.borde_agujero import medir_borde
from apolo.library.calidad.bordes import controlar_bordes
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR
from apolo.services.calidad_bordes import insumos_bordes
from apolo.services.calidad_pernos import _Escena, insumos_pernos

Z = (0.0, 0.0, 1.0)


def _placa(x_agujero: float, *, y: float = 0.0, ancho_y: float = 60.0):
    """Placa 100 × `ancho_y` × 5 (z ∈ [0, 5]) con un paso Ø11 en (x, y)."""
    return Pos(0, 0, 2.5) * Box(100, ancho_y, 5) - Pos(x_agujero, y, 2.5) * Cylinder(5.5, 20)


def _medir(solido, x, y=0.0, t0=10.0, t1=15.0, **kw):
    return medir_borde(Rayos(solido), (x, y, -10.0), Z, t0, t1, 10.0, **kw)


# ── la medida ───────────────────────────────────────────────────────────────────────────


def test_agujero_cerca_del_canto_de_una_placa():
    r = _medir(_placa(-42.0), -42.0)
    assert r["estado"] == "medido" and r["forma"] == "redondo"
    assert r["d0"] == pytest.approx(11.0) and r["e"] == pytest.approx(8.0, abs=0.1)
    assert r["e_min"] == pytest.approx(13.2) and not r["cumple"]


def test_agujero_al_centro_cumple():
    r = _medir(_placa(0.0), 0.0)
    assert r["e"] == pytest.approx(30.0, abs=0.1) and r["cumple"]


def test_extremo_de_un_tubo_es_canto_y_su_esquina_no():
    tubo = Box(400, 40, 80) - Box(400, 34, 74)  # pared +Y en y ∈ [17, 20]
    cerca = tubo - Pos(192, 20, 0) * Rot(90, 0, 0) * Cylinder(5.5, 20)
    r = medir_borde(Rayos(cerca), (192, 30, 0), (0, -1, 0), 10, 13, 10)
    assert r["e"] == pytest.approx(8.0, abs=0.1) and not r["cumple"]  # a 8 mm de la punta
    esquina = tubo - Pos(100, 20, 30) * Rot(90, 0, 0) * Cylinder(5.5, 20)
    r = medir_borde(Rayos(esquina), (100, 30, 30), (0, -1, 0), 10, 13, 10)
    assert r["estado"] == "medido" and r["e"] is None and r["cumple"]  # la pared sigue


def test_talon_de_un_angulo_no_es_canto():
    ang = Pos(25, 0, 2.5) * Box(50, 200, 5) + Pos(2.5, 0, 25) * Box(5, 200, 50)
    ang = ang - Pos(12, 0, 0) * Cylinder(5.5, 30)
    r = _medir(ang, 12.0)
    assert r["cumple"] and r["e"] == pytest.approx(38.0, abs=0.1)  # el canto es la punta del ala


def test_ranura_pide_un_borde_mayor():
    placa = Pos(0, 0, 2.5) * Box(300, 60, 5) - Pos(0, 23, 2.5) * (
        Box(139, 11, 10) + Pos(-69.5, 0, 0) * Cylinder(5.5, 10) + Pos(69.5, 0, 0) * Cylinder(5.5, 10))
    r = _medir(placa, 0.0, 23.0)
    assert r["forma"] == "ranura" and r["e_min"] == pytest.approx(16.5)
    assert r["e"] == pytest.approx(7.0, abs=0.1) and not r["cumple"]


def test_arandela_y_perno_sin_agujero_no_se_juzgan():
    arandela = Cylinder(10, 2) - Cylinder(5.5, 2)
    assert _medir(arandela, 0.0, t0=9.0, t1=11.0)["estado"] == "anillo"
    maciza = Pos(0, 0, 2.5) * Box(100, 60, 5)
    assert _medir(maciza, 0.0)["estado"] == "sin_agujero"
    # roscada (el control de agarre la lee así): la pared es el Ø nominal
    r = _medir(maciza, -44.0, roscado=True)
    assert r["estado"] == "medido" and r["e"] == pytest.approx(6.0, abs=0.1)


def test_eje_cruzado_por_un_perno_no_es_una_chapa():
    eje = Rot(90, 0, 0) * Cylinder(12.5, 400) - Pos(0, 0, 0) * Cylinder(6.5, 60)
    r = medir_borde(Rayos(eje), (0, 0, -30), Z, 17.5, 42.5, 12.0)
    assert r["estado"] == "medido" and r["e"] is None  # la superficie del eje no es canto


def test_el_borde_de_otro_agujero_es_paso_no_canto():
    placa = _placa(0.0) - Pos(14, 0, 2.5) * Cylinder(5.5, 20)
    sin_otro = _medir(placa, 0.0)
    assert not sin_otro["cumple"]  # el otro agujero visto como canto
    con_otro = _medir(placa, 0.0, otros=[((14.0, 0.0, 0.0), Z, 5.5)])
    assert con_otro["cumple"]


# ── el control puro ────────────────────────────────────────────────────────────────────


def test_control_falla_con_la_evidencia():
    ag = [{"perno": "p1", "pieza": "a", "nombre": "Placa del tensor", "estado": "medido",
           "d0": 11.0, "forma": "redondo", "e": 7.0, "e_min": 13.2, "cumple": False},
          {"perno": "p2", "pieza": "a", "nombre": "Placa del tensor", "estado": "medido",
           "d0": 11.0, "forma": "redondo", "e": 20.0, "e_min": 13.2, "cumple": True}]
    pasos = [{"pieza": "a", "nombre": "Placa del tensor", "pernos": ["p1", "p2"], "p": 20.0,
              "p_min": 24.2, "d0": 11.0, "cumple": False}]
    dist, paso = controlar_bordes(ag, pasos)
    assert dist.estado == FALLA and "e = 7.0 mm < 13.2 mm" in dist.detalle
    assert dist.evidencia["casos"][0]["e_requerido_mm"] == 13.2 and dist.piezas == ["a", "p1"]
    assert paso.estado == FALLA and paso.evidencia["casos"][0]["p_mm"] == 20.0


def test_control_sin_nada_que_ver():
    assert controlar_bordes([], [])[0].estado == NO_APLICA
    solo_catalogo = [{"perno": "p", "pieza": "c", "estado": "de_catalogo", "motivo": "x"}]
    assert controlar_bordes(solo_catalogo, [])[0].estado == NO_APLICA
    ciego = [{"perno": "p", "pieza": "c", "estado": "sin_agujero", "motivo": "macizo"}]
    assert controlar_bordes(ciego, [])[0].estado == SIN_EVALUAR


# ── sobre un documento ─────────────────────────────────────────────────────────────────


def _placas_con_muesca(doc):
    """Dos placas 120 × 80 apiladas; la de arriba lleva una muesca desde su canto +Y que deja
    el agujero de x = +45 a 6 mm del canto (la caja de la placa no cambia)."""
    a = doc.execute("create_box", {"name": "Placa base", "width": 120, "depth": 80, "height": 8,
                                   "position": {"z": 4}})
    b = doc.execute("create_box", {"name": "Placa del tensor", "width": 120, "depth": 80,
                                   "height": 6, "position": {"z": 11}})
    muesca = doc.execute("create_box", {"width": 30, "depth": 34, "height": 20,
                                        "position": {"x": 45, "y": 23, "z": 11}})
    b = doc.execute("boolean_op", {"operation": "cut", "target": b, "tools": [muesca]})
    return a, b


def test_join_bolted_criterio_5_no_taladra_bajo_el_minimo():
    doc = Document("muesca")
    a, b = _placas_con_muesca(doc)
    with pytest.raises((CommandError, DocumentError), match=r"agujero 2 de la unión queda a "
                       r"e = 6 mm del canto de «.*» \(EN 1993-1-8 pide ≥ 13\.2 mm"):
        doc.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 2})
    # sin la muesca la misma unión pasa
    ok = Document("sin-muesca")
    a2 = ok.execute("create_box", {"width": 120, "depth": 80, "height": 8, "position": {"z": 4}})
    b2 = ok.execute("create_box", {"width": 120, "depth": 80, "height": 6, "position": {"z": 11}})
    cid = ok.execute("join_bolted", {"a": a2, "b": b2, "size": "M10", "count": 2})
    assert next(c for c in ok.commands if c["id"] == cid)["params"]["criterio"] == 5


def test_la_puerta_ve_el_agujero_de_un_log_viejo():
    """El criterio 4 (log guardado) taladra igual: la puerta lo marca con sus números."""
    doc = Document("muesca-4")
    a, b = _placas_con_muesca(doc)
    doc.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 2, "criterio": 4})
    esc = _Escena(doc.scene)
    pernos = insumos_pernos(doc, escena=esc)
    agujeros, pasos = insumos_bordes(doc, pernos, esc)
    dist, paso = controlar_bordes(agujeros, pasos)
    assert dist.estado == FALLA and dist.evidencia["fallan"] == 1
    caso = dist.evidencia["casos"][0]
    assert caso["pieza"] == b and caso["e_mm"] == pytest.approx(6.0, abs=0.1)
    assert paso.estado == OK  # 90 mm entre los dos


def test_la_fuente_mecanica_publica_el_item_general():
    from apolo.library.calidad import registro
    from apolo.services.calidad_mecanica import items_funcion_mecanica

    doc = Document("muesca-fuente")
    a, b = _placas_con_muesca(doc)
    doc.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 2, "criterio": 4})
    items = items_funcion_mecanica(doc, reglas=[])
    insumos = {"hechos": {"elementos": {"tornilleria": {"perno": 2}}},
               "fuentes": {"mecanica": items}}
    r = registro.evaluar(insumos, registro=[e for e in registro.REGISTRO
                                            if getattr(e, "clave", "") == "mecanica"])
    it = next(i for i in r["items"] if i["id"] == "union.distancia_al_borde")
    assert it["estado"] == FALLA and it["familia"] == "estructura"
