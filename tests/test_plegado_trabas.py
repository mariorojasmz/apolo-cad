"""La posición de USO del plegable se traba (plan plegables-en-la-puerta, F3: D5 y D6 con su F0).

Dos fixtures sintéticas:
- la SILLA de `test_plegado_posiciones` (asiento raíz, pata con su bisagra en Y que pliega
  hacia «-»): su apertura («+») la frena un calzo o un pasador tope del asiento;
- una RODILLA (el compás de una mesa plegable o el tirante de una escalera): pata con su junta
  (el grado), brazo inferior con su junta en P, brazo superior con la rodilla en K y el lazo que
  cierra en Q, sobre el bastidor raíz (`distancia` + `punto_coincidente`, D4). La rodilla queda
  `e` mm sobre la recta PQ (2,25° entre brazos con e = 4,81) y una pletina tope, fija al brazo
  inferior, frena al superior bajo la rodilla. Plegar («+») mueve P hacia Q y la rodilla pasa al
  otro lado de la recta; abrir («-») lo limita el lazo (el tirante).
"""

from __future__ import annotations

import math

import pytest
from test_plegado_posiciones import GUARDADO, USO, _plegable, _silla

import apolo.services.puerta_publicacion as pp
from apolo.doc import Document
from apolo.doc.errors import DocumentError
from apolo.library.calidad.item import FALLA, NO_APLICA, OK, SIN_EVALUAR
from apolo.library.calidad.registro import VERSION_REGISTRO, evaluar
from apolo.library.calidad.trabas import REGLA_PESO, TOL_VOL_MM3, juzgar, traba
from apolo.services.calidad_trabas import trabas

Y = {"x": 0, "y": 1, "z": 0}
_PORQUE = "la persona sentada carga la tijera cerrada: EN 12520 § 5.3, criterio del cliente"


# ------------------------------------------------------------------ la silla y sus topes
def _calzo(doc, ids, gap: float, lado: float = -1.0, pasador: bool = False) -> str:
    """Un calzo del asiento junto a la cara de la pata (x = -200 o -170), bajo la bisagra, a
    `gap` mm. `lado` -1: del lado hacia el que abre (+); +1: del otro."""
    cara = -200.0 if lado < 0 else -170.0
    if pasador:  # un pasador tope Ø10 en Y, a 70 mm bajo la bisagra
        return doc.execute("create_cylinder", {
            "name": "Pasador tope", "radius": 5, "height": 40,
            "position": {"x": cara + lado * (gap + 5), "y": 0, "z": 340}, "rotation": {"x": 90}})
    return doc.execute("create_box", {
        "name": "Calzo de apertura", "width": 15, "depth": 30, "height": 70,
        "position": {"x": cara + lado * (gap + 7.5), "y": 0, "z": 365}})


def _estudio(doc, trabas_uso: list[dict]) -> None:
    doc.set_motion("plegado", [{**USO, "trabas": trabas_uso}, GUARDADO])


def _fila(doc, k: int = 0) -> dict:
    return trabas(doc)["trabas"][k]


@pytest.mark.parametrize("gap, pasador, estado, texto", [
    (0.0, False, OK, "crece"),
    (0.12, True, OK, "a 0.12 mm"),           # el pasador de la escalera de 7
    (2.0, False, FALLA, "deja juego"),         # la prueba aún lo alcanza, pero hay 2 mm
])
def test_el_tope_que_bloquea_a_menos_de_medio_milimetro(gap, pasador, estado, texto):
    doc, ids = _silla()
    _plegable(doc)
    tope = _calzo(doc, ids, gap, pasador=pasador)
    _estudio(doc, [{"grado": "j_pata", "sentido": "+", "tipo": "tope", "piezas": [tope]}])
    fila = _fila(doc)
    e, m = juzgar(fila)
    assert e == estado and texto in m, (m, fila["medida"])
    (par,) = fila["medida"]["pares"]
    assert {par["a"], par["b"]} == {tope, ids["pata"]} and par["dist_mm"] == pytest.approx(gap, abs=1e-3)
    assert par["comun_prueba_mm3"] - par["comun_uso_mm3"] > TOL_VOL_MM3


def test_el_tope_del_otro_lado_no_bloquea():
    doc, ids = _silla()
    _plegable(doc)
    tope = _calzo(doc, ids, 0.0, lado=1.0)  # del lado hacia el que la pata se aleja al abrir
    _estudio(doc, [{"grado": "j_pata", "sentido": "+", "tipo": "tope", "piezas": [tope]}])
    e, m = juzgar(_fila(doc))
    assert e == FALLA and "no está en ese sentido" in m, m


def test_un_tope_lejos_no_es_tope():
    doc, ids = _silla()
    _plegable(doc)
    tope = _calzo(doc, ids, 30.0)
    _estudio(doc, [{"grado": "j_pata", "sentido": "+", "tipo": "tope", "piezas": [tope]}])
    e, m = juzgar(_fila(doc))
    assert e == FALLA and "no hay tope" in m, m


# ------------------------------------------------------------------ retenida y peso
def _gancho(doc, gap_reten: float | None) -> list[str]:
    gancho = doc.execute("create_box", {"name": "Gancho del tirante", "width": 40, "depth": 6,
                                        "height": 6, "position": {"x": 100, "y": 0, "z": 600}})
    if gap_reten is None:
        return [gancho]
    reten = doc.execute("create_cylinder", {
        "name": "Pasador de aletas DIN 94", "radius": 1.5, "height": 20,
        "position": {"x": 100, "y": 0, "z": 604.5 + gap_reten}, "rotation": {"x": 90}})
    return [gancho, reten]


@pytest.mark.parametrize("gap, estado, texto", [
    (None, FALLA, "sin retén"),
    (0.0, OK, "pasador de aletas"),
    (3.0, FALLA, "no retiene"),
])
def test_el_gancho_con_y_sin_reten(gap, estado, texto):
    doc, _ids = _silla()
    _plegable(doc)
    piezas = _gancho(doc, gap)
    _estudio(doc, [{"grado": "j_pata", "sentido": "-", "tipo": "retenida", "piezas": piezas}])
    e, m = juzgar(_fila(doc))
    assert e == estado and texto in m, m


def _silla_trabada(doc, ids, abrir: dict | None = None) -> None:
    tope = _calzo(doc, ids, 0.12, pasador=True)
    lista = [{"grado": "j_pata", "sentido": "+", "tipo": "tope", "piezas": [tope],
              "nota": "pasador tope de apertura"},
             {"grado": "j_pata", "sentido": "-", "tipo": "peso", "piezas": [ids["pata"]],
              "nota": "la persona sentada la mantiene abierta"}]
    if abrir is not None:
        lista[0] = abrir
    _estudio(doc, lista)


def test_el_peso_es_aviso_y_justificado_por_escrito_pasa():
    doc, ids = _silla()
    _plegable(doc)
    _silla_trabada(doc, ids)
    ins = {"trabas": trabas(doc)}
    r = traba(ins)
    assert r["estado"] == SIN_EVALUAR and REGLA_PESO in r["detalle"], r["detalle"]
    assert r["evidencia"]["avisos"] == [{"regla": REGLA_PESO, "piezas": [ids["pata"]]}]
    js = [{"regla": REGLA_PESO, "pieza": ids["pata"], "porque": _PORQUE}]
    r = traba({**ins, "justificadas": js})
    assert r["estado"] == OK and r["evidencia"]["justificadas"], r["detalle"]
    assert {(s["sentido"], s["estado"]) for s in r["evidencia"]["sentidos"]} == {("+", OK), ("-", OK)}


def test_un_grado_sin_traba_en_un_sentido_falla():
    doc, ids = _silla()
    _plegable(doc)
    tope = _calzo(doc, ids, 0.0)
    _estudio(doc, [{"grado": "j_pata", "sentido": "+", "tipo": "tope", "piezas": [tope]}])
    r = traba({"trabas": trabas(doc)})
    assert r["estado"] == FALLA and "j_pata «-»: sin traba declarada" in r["detalle"], r["detalle"]
    # sin ninguna traba (el fotograma de siempre): los dos sentidos
    doc.set_motion("plegado", [USO, GUARDADO])
    r = traba({"trabas": trabas(doc)})
    assert r["estado"] == FALLA and "2 sentido(s)" in r["detalle"], r["detalle"]


# ------------------------------------------------------------------ el fotograma
def test_set_motion_acepta_trabas_solo_en_el_uso_y_las_valida():
    doc, ids = _silla()
    t = {"grado": "j_pata", "sentido": "+", "tipo": "tope", "piezas": [ids["asiento"]],
         "nota": " calzo "}
    doc.set_motion("plegado", [{**USO, "trabas": [t]}, GUARDADO])
    assert doc.motion["plegado"][0]["trabas"] == [{**t, "nota": "calzo"}]
    doc.set_motion("solo_junta", [{**USO, "trabas": [{"junta": "j_pata", "sentido": "-",
                                                       "tipo": "peso"}]}, GUARDADO])
    assert doc.motion["solo_junta"][0]["trabas"] == [
        {"junta": "j_pata", "sentido": "-", "tipo": "peso", "piezas": []}]
    malos = [
        ([{**GUARDADO, "trabas": [t]}, USO], "sólo en el fotograma"),
        ([{"t": 0, "values": {"j_pata": 0}, "trabas": [t]}], "sólo en el fotograma"),
        ([{**USO, "trabas": [{**t, "sentido": "abre"}]}], "sentido"),
        ([{**USO, "trabas": [{**t, "tipo": "cerrojo"}]}], "tipo"),
        ([{**USO, "trabas": [{**t, "grado": "j_nada"}]}], "no existe"),
        ([{**USO, "trabas": [{**t, "piezas": ["c999"]}]}], "no existen"),
        ([{**USO, "trabas": [{**t, "piezas": []}]}], "nombra sus piezas"),
        ([{**USO, "trabas": [{**t, "fuerza": 3}]}], "no reconocida"),
        ([{**USO, "trabas": [{"sentido": "+", "tipo": "peso"}]}], "grado"),
        ([{**USO, "trabas": {"grado": "j_pata"}}], "lista"),
    ]
    for kfs, texto in malos:
        with pytest.raises(DocumentError, match=texto):
            doc.set_motion("x", kfs)
    assert "x" not in doc.motion


def test_el_fotograma_viejo_sin_trabas_abre_igual_y_las_trabas_viajan():
    doc, ids = _silla()
    doc.set_motion("viejo", [{"t": 0, "values": {"j_pata": 0}}, {"t": 1, "values": {"j_pata": -10}}])
    _silla_trabada(doc, ids)
    doc2 = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert doc2.motion == doc.motion and "trabas" not in doc2.motion["viejo"][0]
    assert [t["tipo"] for t in doc2.motion["plegado"][0]["trabas"]] == ["tope", "peso"]


# ------------------------------------------------------------------ la rodilla (D6)
P = (0.0, 500.0)
Q = (490.0, 500.0)
XK = 245.0


def _e(grados: float) -> float:
    """La altura de la rodilla sobre PQ que da `grados` entre brazos (180° − ∠PKQ)."""
    return XK * math.tan(math.radians(grados / 2))


def _rodilla(grados: float = 2.25, gap_tope: float = 0.0) -> tuple[Document, dict]:
    e = _e(grados)
    k = {"x": XK, "y": 0, "z": P[1] + e}
    q = {"x": Q[0], "y": 0, "z": Q[1]}
    doc = Document("rodilla")
    bas = doc.execute("create_box", {"name": "Bastidor", "width": 40, "depth": 40, "height": 600,
                                     "position": {"x": 520, "z": 300}})
    pata = doc.execute("create_box", {"name": "Pata", "width": 30, "depth": 10, "height": 600,
                                      "position": {"z": 300}})
    inf = doc.execute("create_box", {"name": "Brazo inferior", "width": XK, "depth": 8,
                                     "height": 20, "position": {"x": XK / 2, "y": 20, "z": 500}})
    sup = doc.execute("create_box", {"name": "Brazo superior", "width": Q[0] - XK, "depth": 8,
                                     "height": 20, "position": {"x": (XK + Q[0]) / 2, "y": 30,
                                                                "z": 500}})
    tope = doc.execute("create_box", {"name": "Pletina tope", "width": 45, "depth": 8,
                                      "height": 10, "position": {"x": 277.5, "y": 30,
                                                                 "z": 485 - gap_tope}})
    doc.execute("add_joint", {"name": "j_pata", "type": "giratoria", "parent": bas,
                              "child": pata, "origin": {"x": 0, "y": 0, "z": 0}, "axis": Y,
                              "lower": -90, "upper": 90})
    doc.execute("add_joint", {"name": "j_brazo", "type": "giratoria", "parent": pata,
                              "child": inf, "origin": {"x": P[0], "y": 0, "z": P[1]}, "axis": Y})
    doc.execute("add_joint", {"name": "j_rod", "type": "giratoria", "parent": inf, "child": sup,
                              "origin": k, "axis": Y})
    doc.execute("add_joint", {"name": "j_tope", "type": "fija", "parent": inf, "child": tope,
                              "origin": k, "axis": Y})
    doc.execute_many([
        {"type": "add_constraint", "params": {"name": "lazo_d", "tipo": "distancia",
                                              "joint": "j_brazo", "anchor": k, "point": q,
                                              "value": math.hypot(Q[0] - XK, e), "axis": Y}},
        {"type": "add_constraint", "params": {"name": "lazo_q", "tipo": "punto_coincidente",
                                              "joint": "j_rod", "anchor": q, "point": q,
                                              "axis": Y}},
    ])
    return doc, {"bastidor": bas, "pata": pata, "inf": inf, "sup": sup, "tope": tope}


def _guardado(doc, pata: float = 30.0) -> dict:
    """La pose plegada con la rodilla del OTRO lado de la recta (la que el estudio declara: el
    solver solo seguiría doblándola del lado de uso)."""
    from apolo.assembly.constraints import _residual, solve_constraints

    for semilla in range(10, 180, 10):
        v = solve_constraints(doc.joints, doc.constraints,
                              {"j_pata": pata, "j_brazo": semilla, "j_rod": -2 * semilla})
        if max(_residual(doc.joints, v, c) for c in doc.constraints.values()) < 1e-3 \
                and v["j_rod"] < 0:
            return {k: round(x, 4) for k, x in v.items()}
    raise AssertionError("no hay pose plegada")


def _trabas_rodilla(doc, ids, sobre: dict | None = None, abrir: dict | None = None):
    uso = {"t": 0, "values": {"j_pata": 0, "j_brazo": 0, "j_rod": 0}, "posicion": "uso",
           "trabas": [sobre or {"grado": "j_pata", "sentido": "+", "tipo": "sobre_centro",
                                "junta": "j_rod", "piezas": [ids["tope"]]},
                      abrir or {"grado": "j_pata", "sentido": "-", "tipo": "tirante"}]}
    doc.set_motion("plegado", [uso, {"t": 1, "values": _guardado(doc), "posicion": "guardado"}])


def test_la_rodilla_sobre_el_centro_con_su_tope_y_el_tirante_traban_el_uso():
    doc, ids = _rodilla(2.25)
    _plegable(doc)
    _trabas_rodilla(doc, ids)
    ins = trabas(doc)
    assert ins["grados"] == [{"grado": "j_pata", "pliega": "+", "lazos": ["lazo_q"]}]
    sobre, tirante = ins["trabas"]
    (z,) = sobre["medida"]["lazos"]
    assert z["angulo_deg"] == pytest.approx(2.25, abs=0.01) and z["lado_guardado"] == -z["lado_uso"]
    assert juzgar(sobre)[0] == OK, juzgar(sobre)
    assert juzgar(tirante)[0] == OK and tirante["medida"]["residuo_prueba_mm"] > 0.5
    assert tirante["medida"]["metodo"] == "rodilla" and tirante["medida"]["hasta"] == -0.5
    r = traba({"trabas": ins})
    assert r["estado"] == OK, r["detalle"]


@pytest.mark.parametrize("grados, gap, texto", [
    (0.0, 0.0, "el sobre-centro pide ≥ 2°"),    # la escalera de 3 y la mesa de 1,2 m
    (1.5, 0.0, "el sobre-centro pide ≥ 2°"),
    (2.25, 2.0, "deja juego"),                  # el tope de la rodilla a 2 mm
])
def test_la_rodilla_que_no_traba_falla(grados, gap, texto):
    doc, ids = _rodilla(grados, gap_tope=gap)
    _plegable(doc)
    _trabas_rodilla(doc, ids)
    sobre = trabas(doc)["trabas"][0]
    e, m = juzgar(sobre)
    assert e == FALLA and texto in m, m


def test_el_sobre_centro_traba_solo_el_sentido_en_que_pliega():
    doc, ids = _rodilla()
    _plegable(doc)
    _trabas_rodilla(doc, ids, sobre={"grado": "j_pata", "sentido": "-", "tipo": "sobre_centro",
                                     "piezas": [ids["tope"]]},
                    abrir={"grado": "j_pata", "sentido": "+", "tipo": "tirante"})
    sobre, tirante = trabas(doc)["trabas"]
    assert "pliega hacia «+»" in juzgar(sobre)[1]
    e, m = juzgar(tirante)  # al plegar el lazo cierra: el tirante no limita ese sentido
    assert e == FALLA and "sigue cerrando" in m, m


def test_una_traba_en_una_junta_del_lazo_no_es_un_grado():
    doc, ids = _rodilla()
    _plegable(doc)
    _trabas_rodilla(doc, ids, sobre={"grado": "j_rod", "sentido": "+", "tipo": "sobre_centro",
                                     "piezas": [ids["tope"]]})
    r = traba({"trabas": trabas(doc)})
    (ign,) = [t for t in r["evidencia"]["trabas"] if t["estado"] == "ignorada"]
    assert "la resuelve un lazo" in ign["motivo"]
    assert r["estado"] == FALLA and "j_pata «+»: sin traba declarada" in r["detalle"], r["detalle"]


# ------------------------------------------------------------------ la puerta
def test_los_umbrales_son_los_de_la_prueba_de_pose_y_el_criterio_de_d6():
    import apolo.library.calidad.trabas as T
    from apolo.services.calidad_movimiento import PASO
    from apolo.services.calidad_movimiento import TOL_VOL_MM3 as TOL_POSE

    assert T.TOL_VOL_MM3 == TOL_POSE and PASO == 3.0
    assert T.SOBRE_CENTRO_MIN_DEG == 2.0 and "CRITERIO DE DISEÑO" in T.__doc__ + open(
        T.__file__, encoding="utf-8").read()


def test_la_puerta_publica_plegado_traba_solo_con_el_requisito():
    doc, ids = _silla()
    _silla_trabada(doc, ids)

    def item():
        ins = pp.reunir(doc, expand=lambda x: x, gravedad={"resultado": None, "motivo": ""},
                        sobrantes=False)
        r = evaluar(ins)
        assert r["version_registro"] == VERSION_REGISTRO == "44"
        return next(i for i in r["items"] if i["id"] == "plegado.traba")

    assert item()["estado"] == NO_APLICA
    _plegable(doc)
    assert item()["estado"] == SIN_EVALUAR  # el peso sin justificar
    pp.poner_justificadas(doc, [{"regla": REGLA_PESO, "pieza": ids["pata"], "porque": _PORQUE}])
    it = item()
    assert it["estado"] == OK, it["detalle"]
