"""El EJE de una junta de giro, trabado (plan hallazgos-del-revisor-en-la-puerta, D8 y F5): un perno
o pasador coaxial (± 1 mm) con una junta `giratoria`/`continua` que toca sus dos cuerpos cumple
`union.retencion` sólo trabado (tuerca autoblocante, contratuerca, pasador de aletas o anillo de
retención) y si no es un tirafondo ni un tornillo de madera. Un perno que no es eje de junta no
cambia de veredicto."""

from pathlib import Path

import pytest

from apolo.doc import Document
from apolo.library import ejes_giro as E
from apolo.library.calidad.agarre import controlar_agarre, evaluar_perno
from apolo.library.calidad.item import FALLA, OK
from apolo.services.calidad_ejes_giro import marcar_ejes
from apolo.services.calidad_pernos import _Escena, insumos_pernos


def _medir(doc):
    esc = _Escena(doc.scene)
    pernos = insumos_pernos(doc, escena=esc)
    return pernos, marcar_ejes(doc, pernos, esc)


def _retencion(doc):
    pernos, pasadores = _medir(doc)
    return {i.id: i for i in controlar_agarre(pernos, pasadores)}["agarre.retencion"]


def _placas(doc, ta=10.0, tb=8.0):
    a = doc.execute("create_box", {"name": "Brazo fijo", "width": 120, "depth": 80, "height": ta,
                                   "position": {"z": ta / 2}})
    b = doc.execute("create_box", {"name": "Brazo que gira", "width": 120, "depth": 80,
                                   "height": tb, "position": {"z": ta + tb / 2}})
    return a, b


def _junta_en_el_perno(doc, a, b, desplazar=0.0, tipo="giratoria"):
    """La junta padre `a` → hijo `b` sobre el eje del (único) perno, corrida `desplazar` mm."""
    (p,) = insumos_pernos(doc)
    o = p["eje"]["asiento"]
    doc.execute("add_joint", {"name": "pivote", "type": tipo, "parent": a, "child": b,
                              "origin": {"x": o[0] + desplazar, "y": o[1], "z": o[2]},
                              "axis": {"x": 0, "y": 0, "z": 1}})


def _pivote(tuerca: str | None = None) -> tuple[Document, str]:
    doc = Document("pivote")
    a, b = _placas(doc)
    params = {"a": a, "b": b, "size": "M10", "count": 1}
    if tuerca:
        params["tuerca"] = tuerca
    doc.execute("join_bolted", params)
    _junta_en_el_perno(doc, a, b)
    return doc, b


# ── los casos de la F5 ───────────────────────────────────────────────────────────────────


def test_pivote_con_tuerca_simple_din934_falla():
    doc, _ = _pivote()
    (p,), pasadores = _medir(doc)
    assert p["giro"] == {"junta": "pivote"} and pasadores == []
    e, txt, nums = evaluar_perno(p)["retencion"]
    assert e == FALLA and "junta pivote" in txt and "DIN 985" in txt, txt
    assert nums["eje_de_giro"] == "pivote" and "traba" not in nums
    it = _retencion(doc)
    assert it.estado == FALLA and it.piezas == [p["fid"]]
    assert it.evidencia["ejes_de_giro"] == 1


def test_pivote_con_join_bolted_din985_pasa():
    doc, _ = _pivote("din985")
    (p,), _ = _medir(doc)
    assert p["giro"] == {"junta": "pivote"}
    assert [t.get("autoblocante") for t in p["tramos"] if t["rol"] == "tuerca"] == [True]
    e, txt, nums = evaluar_perno(p)["retencion"]
    assert e == OK and nums["traba"] == "autoblocante" and "autoblocante" in txt, txt
    assert _retencion(doc).estado == OK


def _perno_a_mano(doc, tuercas_z: list[float]):
    """Brazo fijo (z 0–20) y el que gira (20–30), PERNO-HEX-M10 ×50 con asiento en z = 30 y sus
    TUERCA-M10 (8 de alto) centradas en `tuercas_z`."""
    a, b = _placas(doc, 20, 10)
    doc.execute("insert_component", {"component": "PERNO-HEX-M10", "position": {"z": 30}})
    for z in tuercas_z:
        doc.execute("insert_component", {"component": "TUERCA-M10", "position": {"z": z}})
    return a, b


def test_contratuerca_a_tope_traba_el_pivote():
    doc = Document("contratuerca")
    a, b = _perno_a_mano(doc, [-4, -12])
    _junta_en_el_perno(doc, a, b)
    (p,), _ = _medir(doc)
    e, txt, nums = evaluar_perno(p)["retencion"]
    assert e == OK and nums["traba"] == "contratuerca", txt

    sola = Document("una-tuerca")
    a, b = _perno_a_mano(sola, [-4])
    _junta_en_el_perno(sola, a, b)
    assert _retencion(sola).estado == FALLA


def test_dos_tuercas_separadas_no_son_contratuerca():
    doc = Document("separadas")
    a, b = _perno_a_mano(doc, [-4, -15])  # 3 mm entre las dos
    _junta_en_el_perno(doc, a, b)
    assert _retencion(doc).estado == FALLA


def test_tirafondo_como_eje_falla():
    """La silla plegable (ronda 1, ALTA): un tirafondo DIN 571 en la testa hacía de eje."""
    doc = Document("silla")
    a = doc.execute("create_box", {"name": "Pata", "width": 120, "depth": 80, "height": 60,
                                   "position": {"z": 30}})
    b = doc.execute("create_box", {"name": "Tijera", "width": 120, "depth": 80, "height": 10,
                                   "position": {"z": 65}})
    doc.set_material(a, "copaiba")
    doc.set_material(b, "copaiba")
    doc.execute("join_bolted", {"a": a, "b": b, "size": "M8", "count": 1})
    (p,) = insumos_pernos(doc)
    assert p["madera_screw"], p["ref"]
    _junta_en_el_perno(doc, a, b)
    (p,), _ = _medir(doc)
    e, txt, _n = evaluar_perno(p)["retencion"]
    assert e == FALLA and "tirafondo" in txt, txt


def test_un_perno_que_no_es_eje_de_junta_no_cambia():
    """La misma unión DIN 934 sin junta, con la junta corrida 5 mm y con una junta FIJA: el
    veredicto de siempre (OK) y el insumo sin `giro`."""
    base = Document("sin-junta")
    a, b = _placas(base)
    base.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 1})
    (p0,), _ = _medir(base)
    ref = evaluar_perno(p0)["retencion"]
    assert ref[0] == OK and "giro" not in p0

    for desplazar, tipo in ((5.0, "giratoria"), (0.0, "fija")):
        doc = Document("otra")
        a, b = _placas(doc)
        doc.execute("join_bolted", {"a": a, "b": b, "size": "M10", "count": 1})
        _junta_en_el_perno(doc, a, b, desplazar=desplazar, tipo=tipo)
        (p,), _ = _medir(doc)
        assert "giro" not in p
        assert evaluar_perno(p)["retencion"] == ref


def test_un_perno_coaxial_que_no_toca_el_cuerpo_que_gira_no_es_su_eje():
    """El perno que entra en la punta de un eje FIJO comparte la recta del rodillo, pero el tubo
    (radio ≫ d) no lo abraza: el rodillo gira en sus rodamientos, no en el perno."""
    doc = Document("rodillo")
    a, b = _placas(doc, 20, 10)
    doc.execute("insert_component", {"component": "PERNO-HEX-M10", "position": {"z": 30}})
    doc.execute("insert_component", {"component": "TUERCA-M10", "position": {"z": -4}})
    tubo = doc.execute("create_box", {"name": "Tubo del rodillo", "width": 10, "depth": 10,
                                      "height": 30, "position": {"x": 40, "z": 15}})
    doc.execute("add_joint", {"name": "rodillo", "type": "continua", "parent": a, "child": tubo,
                              "origin": {"x": 0, "y": 0, "z": 0}, "axis": {"x": 0, "y": 0, "z": 1}})
    (p,), _ = _medir(doc)
    assert "giro" not in p and evaluar_perno(p)["retencion"][0] == OK


def _pasador(doc, reten: bool):
    a, b = _placas(doc, 20, 10)
    for f in (a, b):
        doc.execute("drill_hole", {"feature": f, "position": {"z": 30}, "axis": "-z",
                                   "diameter": 10.5})
    pin = doc.execute("create_cylinder", {"name": "Pasador Ø10 del pivote", "radius": 5,
                                          "height": 44, "position": {"z": 15}})
    if reten:  # el pasador de aletas cruza el pasador bajo el brazo fijo
        doc.execute("create_box", {"name": "Pasador de aletas DIN 94 2,5x20", "width": 20,
                                   "depth": 2.5, "height": 2.5, "position": {"z": -4}})
    doc.execute("add_joint", {"name": "pivote", "type": "giratoria", "parent": a, "child": b,
                              "origin": {"x": 0, "y": 0, "z": 0}, "axis": {"x": 0, "y": 0, "z": 1}})
    return pin


@pytest.mark.parametrize(("reten", "estado"), [(False, FALLA), (True, OK)])
def test_pasador_eje_pide_su_reten(reten, estado):
    doc = Document("pasador")
    pin = _pasador(doc, reten)
    pernos, pasadores = _medir(doc)
    assert pernos == [] and [p["fid"] for p in pasadores] == [pin]
    it = _retencion(doc)
    assert it.estado == estado, it.evidencia
    if reten:
        assert pasadores[0]["retenes"][0]["tipo"] == "pasador de aletas"


# ── las reglas de nombre (anclas y guardas) ──────────────────────────────────────────────


@pytest.mark.parametrize(("texto", "es"), [
    ("Tuerca autoblocante DIN 985 M8 pivote del. (+Y)", True),  # el nombre real de la escalera
    ("tuerca autoblocante DIN 985 / ISO 10511", True),          # la ficha de catálogo
    ("Tuerca M10 ISO 7040", True),
    ("Tuerca hexagonal DIN 934 M8", False),
    ("tuerca hexagonal DIN 934", False),
])
def test_autoblocante_por_ficha_o_nombre(texto, es):
    assert bool(E.ES_AUTOBLOCANTE.search(texto)) is es


@pytest.mark.parametrize(("nombre", "tipo"), [
    ("Pasador de aletas DIN 94 2,5x20", "pasador de aletas"),
    ("Escalera · Pasador de aletas (2)", "pasador de aletas"),
    ("Anillo de retención DIN 471 Ø10", "anillo de retención"),
    ("Seeger Ø12", "anillo de retención"),
    ("Placa del pasador de aletas", None),                    # sólo lo menciona
    ("Pasador tope ISO 8734 Ø4x10 codo (+Y)", None),          # un pasador cilíndrico, no un retén
    ("Pasador DIN 94 2x16", "pasador de aletas"),
    ("Seguro DIN 6799 Ø8", "anillo de retención"),
    ("Eje del rodillo (con anillos DIN 471)", None),          # un eje que nombra sus anillos
])
def test_reten_por_rol(nombre, tipo):
    assert E.tipo_reten(nombre) == tipo


def test_tirafondo_y_pasador_por_rol():
    assert E.es_tirafondo("Tirafondo DIN 571 8x60 eje de la tijera")
    assert E.es_tirafondo("Tornillo para madera Ø8 DIN 571")
    assert not E.es_tirafondo("Tornillo peldaño del. (+Y) a")  # el catálogo lo dice, no el nombre
    assert E.es_pasador("Pasador tope ISO 8734 Ø4x10 codo (+Y)")
    assert E.es_pasador("Bulón Ø12 del brazo")
    assert not E.es_pasador("Pasador de aletas DIN 94")
    assert not E.es_pasador("Placa del pasador")


def test_coaxial_y_traba_puros():
    assert E.coaxial((0.5, 0.5, 10), (0, 0, -1), (0, 0, 0), (0, 0, 1))
    assert not E.coaxial((1.5, 0, 10), (0, 0, 1), (0, 0, 0), (0, 0, 1))
    assert not E.coaxial((0, 0, 10), (0, 0.1, 1), (0, 0, 0), (0, 0, 1))  # 5,7° fuera de eje
    assert E.traba([{"t0": 0, "t1": 8}, {"t0": 8.5, "t1": 16.5}], [])[0] == "contratuerca"
    assert E.traba([{"t0": 0, "t1": 8}, {"t0": 10, "t1": 18}], []) is None
    assert E.traba([], [{"tipo": "anillo de retención", "nombre": "x"}])[0] == "reten"


# ── el modelo real: la escalera de tijera (sus pivotes ya llevan DIN 985) ───────────────


def _escalera() -> Document:
    """El `.apolo` final del piloto, fuera del repo público: en un repo hermano del checkout
    (`<repos>/*/maquinas/escalera-tijera-3/`). Sin él, el test se salta."""
    nombre = "escalera-tijera-3"
    raiz = Path.home() / "source" / "repos"
    hallados = sorted(raiz.glob(f"*/maquinas/{nombre}/{nombre}.apolo")) if raiz.exists() else []
    if not hallados:
        pytest.skip(f"sin el .apolo real de {nombre} (fuera del repo)")
    return Document.from_apolo_bytes(hallados[0].read_bytes())


def test_escalera_real_pivotes_trabados_y_con_din934_fallan():
    doc = _escalera()
    pernos, _ = _medir(doc)
    ejes = {p["fid"]: p["giro"]["junta"] for p in pernos if p.get("giro")}
    # los pivotes del tirante en los largueros delanteros y los dos codos (los traseros cierran
    # el lazo de la tijera: sin junta en el árbol, no se ven)
    assert ejes == {"c57": "j_tirante_p", "c58": "j_tirante_n", "c502": "j_codo_p",
                    "c503": "j_codo_n"}, ejes
    assert all(evaluar_perno(p)["retencion"][0] == OK for p in pernos if p.get("giro"))
    assert _retencion(doc).estado == OK

    doc = _escalera()
    doc.scene["c522"].name = "Tuerca hexagonal DIN 934 M8 pivote del. (+Y)"  # la ronda 1
    it = _retencion(doc)
    assert it.estado == FALLA and it.piezas == ["c57"], it.evidencia
