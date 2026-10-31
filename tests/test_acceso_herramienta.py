"""¿Entra la llave? (plan acceso-de-herramienta, F1): tabla de herramientas, reconocimiento
del fijador por su geometría y chequeo con fantasmas — tuerca libre, tuerca bajo un ala (el
caso del piloto: M12 a 2.5 mm del ala del UPN) y tuerca junto a un piñón."""

import math

import pytest
from build123d import Pos, Rot

from apolo.doc import Document
from apolo.library.acceso_herramienta import es_tornilleria_de_llave, tool_access_report
from apolo.library.builders import hex_bolt, hex_nut, socket_cap
from apolo.library.catalog import CATALOG
from apolo.library.fijadores_geom import reconocer_fijador
from apolo.library.herramientas import brazo_allen, llave_para

# M12 DIN 934: s = 18, m = 10 → esquinas a 10.39 mm del eje; copa Ø25 (12.5 desde el eje)


def _base(doc: Document) -> None:
    """Placa de asiento (cara superior en z = 0), eje roscado vertical y tuerca M12 asentada
    (z 0..10, eje Z en el origen)."""
    doc.execute("create_box", {"name": "Placa de asiento", "width": 120, "depth": 120,
                               "height": 10, "position": {"z": -5}})
    doc.execute("create_cylinder", {"name": "Eje roscado", "radius": 6, "height": 60,
                                    "position": {"z": 10}})
    doc.execute("insert_component", {"component": "TUERCA-M12", "name": "Tuerca del eje",
                                     "position": {"z": 5}})


def _acceso(doc: Document) -> dict:
    rep = tool_access_report(doc.scene, catalog=CATALOG)
    assert rep is not None
    return rep


# ------------------------------------------------------------------ tabla (D1)
def test_tabla_de_llaves():
    ll = llave_para(18)
    assert ll.copa_d == 25.0 and ll.pared_copa == 3.5     # 12.5 desde el eje (plan, origen)
    assert ll.anillo_d == pytest.approx(1.5 * 18, abs=1)  # D1: anillo ≈ 1.5·s
    mid = llave_para(14.5)                                 # entre 13 y 16: interpola
    assert llave_para(13).copa_d < mid.copa_d < llave_para(16).copa_d
    assert llave_para(3) is None and llave_para(80) is None  # fuera de tabla: no extrapola
    assert brazo_allen(10) == 50.0 and brazo_allen(1) is None


# ------------------------------------------------------------------ reconocimiento
@pytest.mark.parametrize("rot", [(0, 0, 0), (90, 0, 0), (0, 90, 17), (33, -61, 12)])
def test_reconoce_tuerca_rotada(rot):
    nut = Pos(10, -20, 30) * Rot(*rot) * hex_nut(12, 18, 10)()
    fj = reconocer_fijador(nut.solids()[0])
    assert fj is not None and fj.tipo == "tuerca"
    assert fj.s == pytest.approx(18, abs=0.01) and fj.altura == pytest.approx(10, abs=0.01)
    # el eje pasa por el centro de la tuerca
    c = nut.center()
    d = [c.X - fj.base[0], c.Y - fj.base[1], c.Z - fj.base[2]]
    proy = sum(d[i] * fj.eje[i] for i in range(3))
    perp = math.sqrt(max(0.0, sum(x * x for x in d) - proy * proy))
    assert perp < 0.01 and proy == pytest.approx(5.0, abs=0.01)


def test_reconoce_cabeza_hex_mirando_afuera():
    bolt = Rot(180, 0, 0) * hex_bolt(12, 18, 7.5)(40)  # cabeza hacia −Z, vástago hacia +Z
    fj = reconocer_fijador(bolt.solids()[0])
    assert fj.tipo == "cabeza_hex" and fj.s == pytest.approx(18, abs=0.01)
    assert fj.eje[2] == pytest.approx(-1.0) and fj.altura == pytest.approx(7.5, abs=0.01)
    assert fj.base[2] == pytest.approx(0.0, abs=0.01)  # asiento = cara inferior de la cabeza


def test_reconoce_allen_y_descarta_lo_sin_hexagono():
    fj = reconocer_fijador(socket_cap(12)(40).solids()[0])
    assert fj.tipo == "allen" and fj.s == pytest.approx(10, abs=0.01)
    assert fj.eje[2] == pytest.approx(1.0) and fj.base[2] == pytest.approx(12.0, abs=0.01)
    from build123d import Box, Cylinder

    assert reconocer_fijador(Cylinder(6, 40)) is None
    assert reconocer_fijador(Box(18, 18, 10)) is None


def test_candidatos_por_catalogo_y_nombre():
    doc = Document()
    doc.execute("create_cylinder", {"name": "Perno de anclaje", "radius": 6, "height": 50})
    doc.execute("create_box", {"name": "Placa", "width": 50, "depth": 50, "height": 5})
    perno, placa = doc.scene.values()
    assert es_tornilleria_de_llave(perno, CATALOG)
    assert not es_tornilleria_de_llave(placa, CATALOG)
    # sin tornillería de llave: None (la puerta de entrega no cambia)
    vacio = Document()
    vacio.execute("create_box", {"name": "Placa", "width": 50, "depth": 50, "height": 5})
    assert tool_access_report(vacio.scene, catalog=CATALOG) is None
    # el perno a medida sin hexágono se DECLARA no evaluado, nunca verde
    rep = tool_access_report(doc.scene, catalog=CATALOG)
    assert rep["evaluados"] == 0 and rep["no_evaluados"][0]["nombre"] == "Perno de anclaje"


# ------------------------------------------------------------------ chequeo (D2/D3)
def test_tuerca_libre_entra_la_copa():
    doc = Document()
    _base(doc)
    rep = _acceso(doc)
    assert rep["evaluados"] == 1 and rep["ok"] == 1, rep
    assert not rep["sin_herramienta"] and not rep["solo_boca"]


def test_tuerca_bajo_un_ala_no_entra_ninguna_llave():
    """El piloto: el ala del UPN corre paralela al eje a 11.5 mm (2.5 mm de las esquinas
    de la tuerca) y sale hacia afuera — ni copa (12.5), ni anillo, ni boca."""
    doc = Document()
    _base(doc)
    doc.execute("create_box", {"name": "Ala del perfil", "width": 8, "depth": 120,
                               "height": 50, "position": {"x": 11.5 + 4, "z": 25}})
    rep = _acceso(doc)
    assert rep["ok"] == 0 and len(rep["sin_herramienta"]) == 1, rep
    e = rep["sin_herramienta"][0]
    assert e["nombre"] == "Tuerca del eje" and e["llave_mm"] == 18.0
    assert e["bloquean"] == ["Ala del perfil"]


def test_ala_con_holgura_deja_entrar_la_copa():
    doc = Document()
    _base(doc)
    doc.execute("create_box", {"name": "Ala del perfil", "width": 8, "depth": 120,
                               "height": 50, "position": {"x": 14.0 + 4, "z": 25}})
    assert _acceso(doc)["ok"] == 1


def test_tuerca_junto_a_un_pinon():
    """Un piñón vecino (sólido que GIRA: cuenta igual, se arma parado) con la punta de sus
    dientes a 0.4 mm de las esquinas de la tuerca: no entra nada. Alejado, entra la copa."""
    r_tip = 67.3 / 2.0

    def con_pinon(holgura):
        doc = Document()
        _base(doc)
        doc.execute("insert_component", {"component": "PINON-ASA40-1-Z15", "name": "Piñón",
                                         "position": {"x": 10.39 + holgura + r_tip, "z": 5}})
        return _acceso(doc)

    cerca = con_pinon(0.4)
    assert len(cerca["sin_herramienta"]) == 1, cerca
    assert cerca["sin_herramienta"][0]["bloquean"] == ["Piñón"]
    assert con_pinon(30.0)["ok"] == 1


def test_solo_boca_es_aviso():
    """Un pasador fino a 12 mm del eje, en la dirección de una cara: tapa la copa y el
    anillo, pero la abertura de la boca lo esquiva → sólo boca."""
    doc = Document()
    _base(doc)
    a = math.radians(30.0)  # normal de una cara del hexágono (RegularPolygon: vértice a 0°)
    doc.execute("create_cylinder", {"name": "Pasador", "radius": 1.0, "height": 40,
                                    "position": {"x": 12 * math.cos(a), "y": 12 * math.sin(a),
                                                 "z": 20}})
    rep = _acceso(doc)
    assert rep["ok"] == 0 and len(rep["solo_boca"]) == 1, rep
    assert rep["solo_boca"][0]["bloquean"] == ["Pasador"]


def test_cabeza_de_perno_bajo_un_ala():
    """Lo mismo vale para la CABEZA de un perno (join_bolted, DIN 933): mira afuera."""
    doc = Document()
    doc.execute("create_box", {"name": "Placa de asiento", "width": 120, "depth": 120,
                               "height": 10, "position": {"z": -5}})
    doc.execute("insert_component", {"component": "PERNO-HEX-M12", "name": "Perno",
                                     "position": {"z": 0}})
    assert _acceso(doc)["ok"] == 1
    doc.execute("create_box", {"name": "Ala del perfil", "width": 8, "depth": 120,
                               "height": 50, "position": {"x": 11.5 + 4, "z": 25}})
    rep = _acceso(doc)
    assert [e["tipo"] for e in rep["sin_herramienta"]] == ["cabeza_hex"], rep
