"""La máquina andando CON PRODUCTO (plan fabrica-de-publicaciones, ajuste D10):
`services/marcha_ejemplo.py`, la marcha automática de un transportador (producto, peso y
velocidad de los requisitos o los de ejemplo, duración según el largo) y su prueba de verdad
sobre una `create_belt_conveyor` chica (MuJoCo). Quien la usa para el video (`marcha.json` o la
automática, y el paso `guion` de la fábrica) es la fábrica de publicaciones, que vive fuera del
núcleo y prueba esa parte con ella.
"""

from __future__ import annotations

import pytest

from apolo.doc.document import Document
from apolo.services import marcha_ejemplo as me


@pytest.fixture(scope="module")
def faja():
    doc = Document("faja-ejemplo")
    doc.execute("create_belt_conveyor", {"largo": 2000, "ancho_banda": 500, "altura": 800})
    return doc


# ------------------------------------------------------------------ la automática
def test_sin_requisitos_usa_la_caja_de_ejemplo_y_lo_dice(faja):
    m = me.armar(faja, extra_s=2.0)
    cajas = m.escenario["productos"]
    assert {tuple(c["dims_mm"]) for c in cajas} == {me.PRODUCTO_DEFECTO}
    assert {c["masa_kg"] for c in cajas} == {me.MASA_DEFECTO_KG}
    assert m.escenario["motores"][0]["v_superficie_m_s"] == me.VELOCIDAD_DEFECTO_M_S
    assert set(m.asumido) >= {"largo_paquete_mm", "peso_paquete_kg", "velocidad_m_s"}
    # de la cola a la cabeza motriz: la junta virtual de la faja y la dirección hacia ella
    mot = m.escenario["motores"][0]
    assert mot["junta"] == "c1_eje_motriz"
    assert "bandas" not in m.escenario  # la de create_belt_conveyor se detecta sola
    # varias cajas ya sobre la banda desde el primer cuadro + la alimentación por la cola
    quietas = [c for c in cajas if "cada_s" not in c]
    serie = [c for c in cajas if "cada_s" in c]
    assert len(quietas) >= 2 and len(serie) == 1
    eje = [round(x) for x in mot["direccion_transporte"]]
    k = eje.index(1) if 1 in eje else eje.index(-1)
    avance = [c["posicion_mm"][k] * eje[k] for c in quietas]
    assert avance == sorted(avance) and serie[0]["posicion_mm"] == quietas[0]["posicion_mm"]
    assert m.escenario["duracion_s"] == pytest.approx(m.duracion_s + 2.0)


def test_los_requisitos_mandan_producto_peso_y_velocidad(faja, monkeypatch):
    monkeypatch.setattr(faja, "requirements", {
        "largo_paquete_mm": 400, "ancho_paquete_mm": 350, "alto_paquete_mm": 250,
        "peso_paquete_kg": 12, "velocidad_m_s": 0.5, "paquetes_por_minuto": 10})
    m = me.armar(faja)
    caja = m.escenario["productos"][0]
    assert caja["dims_mm"] == [400.0, 350.0, 250.0] and caja["masa_kg"] == 12.0
    assert m.escenario["motores"][0]["v_superficie_m_s"] == 0.5
    serie = next(c for c in m.escenario["productos"] if "cada_s" in c)
    assert serie["cada_s"] == pytest.approx(6.0)  # 10 por minuto
    assert m.asumido == []


def test_un_producto_mas_ancho_que_la_banda_se_recorta(faja, monkeypatch):
    monkeypatch.setattr(faja, "requirements", {"ancho_paquete_mm": 900})
    m = me.armar(faja)
    assert m.escenario["productos"][0]["dims_mm"][1] <= 0.9 * 500 + 1
    assert any("recortado" in a for a in m.asumido)


def test_la_marcha_crece_con_el_largo_y_baja_con_la_velocidad():
    corto, largo = me.duracion_marcha(2000, 0.3), me.duracion_marcha(8000, 0.3)
    assert me.MARCHA_MIN_S <= corto < largo <= me.MARCHA_MAX_S
    assert me.duracion_marcha(8000, 0.6) < largo
    assert me.duracion_marcha(500_000, 0.1) == me.MARCHA_MAX_S


def test_la_automatica_simula_y_las_cajas_avanzan(faja):
    pytest.importorskip("mujoco")
    m = me.armar(faja, extra_s=0.0)
    esc = dict(m.escenario, duracion_s=2.0)  # corta: basta con ver que avanzan
    r = me.probar(faja, esc)
    assert r["avance_mm"] >= 300 and r["productos"] >= 2
    # D13: la faja que dibujará el visor sale de la sección de la banda y es fiel al modelo
    assert [(f["pieza"], f["origen"]) for f in r["fidelidad"]] == [("c1_banda", "seccion")]


def test_sin_banda_no_hay_marcha_y_dice_por_que():
    doc = Document("mesa")
    doc.execute("create_box", {"name": "Tablero", "width": 500, "depth": 400, "height": 30})
    with pytest.raises(me.SinMarcha, match="rodillos sin juntas"):
        me.armar(doc)


def test_una_banda_a_mano_sin_junta_motriz_lo_dice():
    doc = Document("banda-a-mano")
    doc.execute("create_box", {"name": "Banda PVC 2 mm", "width": 2000, "depth": 500, "height": 4})
    with pytest.raises(me.SinMarcha, match="junta de giro motriz"):
        me.armar(doc)


def test_una_simulacion_donde_nada_avanza_no_vale(faja):
    pytest.importorskip("mujoco")
    quieta = {"duracion_s": 0.5, "productos": [
        {"nombre": "caja", "dims_mm": [200, 200, 100], "posicion_mm": [0, 0, 860]}]}
    with pytest.raises(me.SinMarcha, match="no avanzan"):
        me.probar(faja, quieta)
    assert me.probar(faja, quieta, minimo_mm=None)["productos"] == 1  # a mano: basta con simular


# ------------------------------------------------------------------ marcha.json o la automática


# ------------------------------------------------------------------ el paso guion de la fábrica


INFIEL = ("la banda «c51» la cinta animada atraviesa «Guarda motriz (1)» (c210) 38 mm más que "
          "el modelo")
