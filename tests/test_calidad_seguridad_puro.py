"""Puerta de publicación F3 — lo PURO de la seguridad y la reparabilidad (plan
puerta-de-publicacion, D4/D5): tabla 4 de ISO 13857, veredicto de una sonda, qué gira, guardas
con herramienta y piezas de desgaste. Sin OCCT: datos armados a mano."""

from __future__ import annotations

import math

import pytest

from apolo.library import reparabilidad as R
from apolo.library.seguridad import guardas as G
from apolo.library.seguridad.iso13857 import ALCANCE_BRAZO_MM, sr_requerida
from apolo.library.seguridad.modelo import Pieza, redondo_de_caja
from apolo.library.seguridad.peligros import giratorias, peligros_mecanicos, resultado_peligro
from apolo.library.seguridad.sondas import desplazamientos, direcciones, origen, veredicto


def _p(i, nombre, rol="", cat=None, caja=((0, 0, 0), (10, 10, 10)), anclada=False):
    return Pieza(i, nombre, rol, cat, None, caja, redondo_de_caja(caja), anclada)


# ------------------------------------------------------------------ ISO 13857
def test_tabla4_ranura():
    assert sr_requerida(4) == 2 and sr_requerida(6) == 10 and sr_requerida(8) == 20
    assert sr_requerida(10) == 80 and sr_requerida(12) == 100 and sr_requerida(20) == 120
    assert sr_requerida(None) == ALCANCE_BRAZO_MM == 850


def test_direcciones_unitarias_y_deterministas():
    a, b = direcciones(64), direcciones(64)
    assert a == b and len(a) == 64
    assert all(abs(math.sqrt(sum(c * c for c in d)) - 1) < 1e-9 for d in a)
    assert sum(1 for d in a if d[2] > 0) == 32  # mitad arriba, mitad abajo
    off = desplazamientos(20, (0, 0, 1))
    assert len(off) == 6 and all(abs(math.hypot(o[0], o[1]) - 10) < 1e-9 and o[2] == 0
                                 for o in off)


def test_origen_desde_abajo_arranca_en_el_piso():
    caja = ((0, 0, 0), (1000, 500, 800))
    o = origen((500, 250, 600), (0, 0, 1), caja, 0.0)  # sube: viene del piso
    assert o["origen"][2] == pytest.approx(0) and o["t_objetivo"] == pytest.approx(600)
    assert o["extra"] == pytest.approx(250)  # el brazo entra por el costado hasta el centro
    o = origen((500, 250, 600), (0, 0, -1), caja, 0.0)  # baja: viene de arriba
    assert o["origen"][2] == pytest.approx(850) and o["t_contorno"] == pytest.approx(50)


def test_veredicto():
    libre = lambda ancho: [None] * 6  # noqa: E731
    assert veredicto(None, 0, 0, libre)["alcanza"] is False  # rayo bloqueado
    lejos = veredicto(1000, 50, 0, libre)
    assert lejos["alcanza"] is False and lejos["motivo"] == "fuera de alcance"
    brazo = veredicto(300, 50, 0, libre)
    assert brazo["alcanza"] and brazo["sr_requerida_mm"] == 850 and brazo["profundidad_mm"] == 250

    def ranura_9(ancho):  # el haz de 10 no pasa (se estrecha en t=200); el de 8 sí
        return [None] * 6 if ancho <= 8 else [200.0] + [None] * 5

    v = veredicto(250, 0, 0, ranura_9)  # 50 mm detrás de una abertura < 10 → exige 80
    assert v["alcanza"] and v["sr_requerida_mm"] == 80 and v["sr_mm"] == 50
    v = veredicto(400, 0, 0, ranura_9)  # 200 mm detrás: la mano no llega
    assert not v["alcanza"]


# ------------------------------------------------------------------ qué gira
def test_giratorias_eje_fijo_y_propagacion():
    piezas = {
        "larg": _p("larg", "Larguero (+Y)", "estructura"),
        "eje": _p("eje", "Eje del rodillo", "eje"),
        "tubo": _p("tubo", "Tubo del rodillo", "gira"),
        "buje": _p("buje", "Buje del piñón", "gira"),
        "motriz": _p("motriz", "Eje motriz Ø25 h7", "eje"),
        "tapa": _p("tapa", "Tapa-cubo del tambor motriz", "guarda"),
        "cola": _p("cola", "Eje fijo de cola Ø25 g6", "eje"),
    }
    uniones = [{"a": "eje", "b": "larg", "kind": "perno"},       # eje atornillado: fijo
               {"a": "tubo", "b": "buje", "kind": "soldadura"},
               {"a": "tubo", "b": "larg", "kind": "contacto"},
               {"a": "motriz", "b": "tapa", "kind": "soldadura"}]
    juntas = [{"type": "continua", "parent": "larg", "child": "motriz"}]
    gira = giratorias(piezas, juntas, uniones)
    assert gira == {"tubo", "buje", "motriz", "tapa"}  # ni el eje atornillado ni el «fijo»


def test_soldadura_no_propaga_a_la_estructura():
    piezas = {"t": _p("t", "Tambor motriz", "gira"), "l": _p("l", "Larguero", "estructura")}
    assert giratorias(piezas, [], [{"a": "t", "b": "l", "kind": "soldadura"}]) == {"t"}


def test_transmision_agrupa_cadena_y_pinones_que_se_tocan():
    caja_a, caja_b = ((0, 0, 0), (60, 20, 60)), ((300, 0, 0), (360, 20, 60))
    piezas = {
        "a": _p("a", "Piñón A", "gira", "transmision", caja_a),
        "b": _p("b", "Piñón B", "gira", "transmision", caja_b),
        "c": _p("c", "Cadena motriz", "flexible", "transmision", ((0, 0, 0), (360, 20, 60))),
    }
    gira = giratorias(piezas, [], [])
    pel = peligros_mecanicos(piezas, [], [], gira, {})
    trans = [p for p in pel if p["id"].startswith("transmision:")]
    assert len(trans) == 1 and set(trans[0]["piezas"]) == {"a", "b", "c"}
    assert trans[0]["tipo"] == "atrapamiento" and len(trans[0]["objetivos"]) == 3


def test_resultado_sin_objetivos_es_sin_evaluar():
    r = resultado_peligro({"id": "x", "objetivos": [], "motivo": "sin arco"}, [], 0.0)
    assert r["estado"] == "SIN_EVALUAR" and r["motivo"] == "sin arco"


# ------------------------------------------------------------------ guardas
def _guarda(kind, otra_rol="estructura"):
    piezas = {"g": _p("g", "Guarda del tambor", "guarda"), "e": _p("e", "Larguero", otra_rol),
              "p": _p("p", "Perno M8 DIN 933", "perno")}
    uniones = [{"a": "g", "b": "p", "kind": "contacto"}]  # el herraje no cuenta
    if kind:
        uniones.append({"a": "g", "b": "e", "kind": kind})
    return piezas, uniones


@pytest.mark.parametrize("kind,estado,motivo", [
    ("perno", "OK", "atornillada"),
    ("soldadura", "FALLA", "soldada"),
    ("contacto", "FALLA", "apoyada"),
    (None, "FALLA", "sin unión"),
])
def test_guarda_con_herramienta(kind, estado, motivo):
    piezas, uniones = _guarda(kind)
    g = G.revisar_guardas(piezas, uniones, set())["guardas"][0]
    assert g["estado"] == estado and motivo in g["motivo"]


def test_guarda_unida_a_lo_que_gira_y_guarda_que_gira():
    piezas, uniones = _guarda("perno")
    piezas["t"] = _p("t", "Tambor motriz", "gira")
    piezas["c"] = _p("c", "Tapa-cubo del tambor", "guarda")
    uniones.append({"a": "g", "b": "t", "kind": "perno"})
    r = G.revisar_guardas(piezas, uniones, {"t", "c"})
    assert r["guardas"][0]["estado"] == "FALLA" and "se mueve" in r["guardas"][0]["motivo"]
    assert r["excluidas_por_girar"] == ["c"]


def test_guarda_con_orejas_soldadas_y_atornilladas_es_ok():
    piezas, _ = _guarda(None)
    piezas["o"] = _p("o", "Oreja de guarda", "")
    uniones = [{"a": "o", "b": "g", "kind": "soldadura"}, {"a": "o", "b": "e", "kind": "perno"}]
    g = G.revisar_guardas(piezas, uniones, set())["guardas"][0]
    assert g["estado"] == "OK" and g["ids"] == ["g", "o"]


# ------------------------------------------------------------------ reparabilidad
def test_clases_de_desgaste():
    assert R.desgaste(_p("1", "Banda PVC 2 capas", "flexible")) == "banda"
    assert R.desgaste(_p("2", "Cadena", "flexible", "transmision")) == "cadena"
    assert R.desgaste(_p("3", "Rodamiento 6205", "rodamiento", "rodamientos")) == "rodamiento"
    assert R.desgaste(_p("4", "Tapa porta-rodamiento del tambor", "rodamiento")) is None
    assert R.desgaste(_p("5", "Chumacera motriz (+Y)", "chumacera", "chumaceras")) == "chumacera"
    assert R.desgaste(_p("6", "Motorreductor", "equipo", "motorreductores")) == "motorreductor"
    assert R.desgaste(_p("7", "Piñón doble-simple", "gira", "transmision")) == "piñón"
    assert R.desgaste(_p("8", "Tubo del rodillo (2)", "gira", "tubos_circulares")) == "rodillo"
    assert R.desgaste(_p("9", "Larguero", "estructura")) is None


def test_rodamiento_soldado_al_bastidor_falla():
    piezas = {"r": _p("r", "Chumacera motriz", "chumacera", "chumaceras"),
              "l": _p("l", "Larguero", "estructura"),
              "p": _p("p", "Pata", "estructura", anclada=True)}
    uniones = [{"a": "l", "b": "p", "kind": "soldadura"}, {"a": "r", "b": "l", "kind": "perno"}]
    assert R.item_sin_soldadura(piezas, uniones, "x")["estado"] == "OK"
    uniones[1]["kind"] = "soldadura"
    it = R.item_sin_soldadura(piezas, uniones, "x")
    assert it["estado"] == "FALLA" and it["piezas"] == ["r"]
    assert it["evidencia"]["soldadas"][0]["soldadura"] == ["r", "l"]


def test_pinon_soldado_a_su_rodillo_es_una_unidad():
    piezas = {"pi": _p("pi", "Piñón", "gira", "transmision"), "t": _p("t", "Tubo del rodillo", "gira"),
              "l": _p("l", "Larguero", "estructura")}
    uniones = [{"a": "pi", "b": "t", "kind": "soldadura"}, {"a": "t", "b": "l", "kind": "contacto"}]
    assert R.item_sin_soldadura(piezas, uniones, "x")["estado"] == "OK"
    assert R.unidad("pi", uniones) == {"pi", "t"}


def test_camino_libre_y_banda_montable():
    marco = {"l", "p"}
    barr = {(0, 0, 1): ["l", "g"], (0, 1, 0): ["g"]}
    assert R.camino_libre(barr, {"x"}, marco) == {"libre": True, "direccion": [0, 1, 0],
                                                  "aparta": ["g"]}
    r = R.camino_libre({(0, 0, 1): ["l"]}, {"x"}, marco)
    assert not r["libre"] and r["bloqueos"] == {"[0, 0, 1]": ["l"]}
    assert R.banda_montable({"+Y": [], "-Y": ["l"]})["lado"] == "+Y"
    assert not R.banda_montable({"+Y": ["l"], "-Y": ["l"]})["montable"]
    assert R.empalme_mecanico(_p("b", "Banda PVC con empalme mecánico (grapas)", "flexible"))


def test_rodillo_portante_liso_no_es_peligro():
    """Falsa alarma de la calibración (rodillos-cadena-2m): sin esto, el fondo de cada rodillo
    portante salía FALLA. El rodillo liso sobre eje fijo es zona de trabajo; su peligro es la
    transmisión que lo mueve."""
    piezas = {"eje": _p("eje", "Eje del rodillo", "eje"),
              "l": _p("l", "Larguero (+Y)", "estructura"),
              "tubo": _p("tubo", "Tubo del rodillo", "gira", "tubos_circulares",
                         ((0, -250, 700), (50, 250, 750)))}
    uniones = [{"a": "eje", "b": "l", "kind": "perno"}, {"a": "tubo", "b": "eje", "kind": "contacto"}]
    gira = giratorias(piezas, [], uniones)
    assert gira == {"tubo"} and peligros_mecanicos(piezas, [], uniones, gira, {}) == []
