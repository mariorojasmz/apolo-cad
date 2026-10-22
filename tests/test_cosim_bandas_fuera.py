"""Un escenario sobre una banda que no avanza (plan V8.3 F6, defecto 1, el grave).

En la faja 73 la banda hecha a mano quedaba FUERA de la dinámica (unida por fijadores al tambor)
y `simulate(escenario=…)` no lo decía: las cajas no viajaban y seta y atasco daban verde TRIVIAL.
Aquí, sobre la faja de prueba con su tambor motriz en una junta REAL (como una faja hecha a mano)
y sin la detección automática de la banda (`auto_bandas: false`):

  - sin `mecanica.bandas`, un escenario con cajas encima o con una aserción sobre la banda es
    ERROR accionable (400) que dice qué declarar, con el ejemplo listo;
  - con la banda declarada con su junta motriz, corre y pasa como hoy, y TODOS los avisos de la
    preparación de la dinámica llegan al resultado del escenario y a `get_simulation`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("mujoco")

import apolo.api.main as api  # noqa: E402
from apolo.cosim.escenario import leer_escenario  # noqa: E402
from apolo.services.cosim_bandas import bandas_quietas  # noqa: E402
from cosim_lazo_banco import FOTO, PROGRAMA, escenario_variador, faja_variador  # noqa: E402

JUNTA = "eje_motriz"
MOTOR = {"-M1": {"junta": JUNTA, "direccion_transporte": [1, 0, 0]}}
A_MANO = {"con_autodeteccion": True, "auto_bandas": False}
BANDAS = [{"pieza": "c1_banda", "junta_motriz": JUNTA, "direccion_transporte": [1, 0, 0]}]


@pytest.fixture(scope="module")
def doc():
    """La faja de prueba con el tambor motriz en una junta continua real y el programa en el carril."""
    d = faja_variador()
    a = d.scene["c1_tambor_motriz"].anchors["eje_motriz"]
    o, e = a["origin"], a["axis"]
    d.execute("add_joint", {"name": JUNTA, "type": "continua", "parent": "c1_rail1",
                            "child": "c1_tambor_motriz", "origin": {"x": o[0], "y": o[1], "z": o[2]},
                            "axis": {"x": e[0], "y": e[1], "z": e[2]}})
    d.execute("add_program", {"plc": "-K1", "fuente": PROGRAMA})
    return d


@pytest.fixture
def c(doc, monkeypatch):
    monkeypatch.setattr(api, "DOC", doc)
    return TestClient(api.app)


def _escenario(mecanica: dict, aserciones: list, *, cajas: bool = True) -> dict:
    esc = escenario_variador(2.0, cajas=cajas)
    esc.update(mecanica=mecanica, acoples={"motores": MOTOR, "sensores": FOTO}, aserciones=aserciones)
    return esc


def test_sin_bandas_las_cajas_sobre_la_banda_quieta_son_error_accionable(c):
    r = c.put("/api/escenarios/a_mano", json={"escenario": _escenario(A_MANO, ["-K1.cuenta >= 0 al_final"])})
    assert r.status_code == 200
    r = c.post("/api/cosim/run", json={"escenario": "a_mano"})
    assert r.status_code == 400, r.text
    det = r.json()["detail"]
    assert det.startswith("mecánica: 'c1_banda' («Faja de banda · Banda») no avanza en esta simulación")
    assert "es estática (sujeta al bastidor)" in det and "el escenario pone caja encima" in det
    assert "verde sin que nada se mueva" in det
    assert ('`mecanica.bandas` del escenario, p. ej. {"mecanica": {"bandas": [{"pieza": "c1_banda", '
            '"junta_motriz": "eje_motriz"}]}}') in det
    assert c.get("/api/escenarios").json()["escenarios"][0]["estado"] == "sin_correr"


def test_sin_bandas_una_asercion_sobre_la_banda_quieta_tambien(c):
    esc = _escenario(A_MANO, ["c1_banda.v_m_s >= 0,3 dentro_de 1,5 s desde pulsar -S1"], cajas=False)
    r = c.post("/api/cosim/run", json={"escenario": esc})
    assert r.status_code == 400
    assert "la aserción «c1_banda.v_m_s >= 0.3 dentro_de 1.5 s desde pulsar -S1» la mira" in r.json()["detail"]


def test_con_la_banda_declarada_pasa_y_los_avisos_de_la_mecanica_llegan(c):
    esc = _escenario({**A_MANO, "bandas": BANDAS}, [
        "c1_banda.v_m_s >= 0,3 dentro_de 1,5 s desde pulsar -S1 y se mantiene 0,2 s",
        "caja_0.x_mm > -450 al_final",
        "-M1.rpm >= 1700 dentro_de 1,5 s desde pulsar -S1"])
    assert c.put("/api/escenarios/a_mano", json={"escenario": esc}).status_code == 200
    r = c.post("/api/cosim/run", json={"escenario": "a_mano"})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["veredicto"] == "pasa", [a for a in res["aserciones"] if not a["pasa"]]
    mec = [a for a in res["avisos"] if a.startswith("mecánica: ")]
    assert any(a.startswith("mecánica: La banda 'c1_banda' avanza hacia") for a in mec), res["avisos"]
    resumen = c.get(f"/api/cosim/simulaciones/{res['simulacion']}").json()
    assert [a for a in resumen["avisos"] if a.startswith("mecánica: ")] == mec


def test_la_banda_fuera_por_fijadores_dice_por_que_y_que_declarar(doc):
    """El caso de la 73: el aviso «queda FUERA… unida por fijadores» de la dinámica pasa al error."""
    fuera = ("'c1_banda' queda FUERA de la simulación: está unida por fijadores a la pieza móvil "
             "'c1_tambor_motriz' pero no por una junta: declárala con add_joint(arrastrar=true) o una junta 'fija'")
    dyn = SimpleNamespace(bandas=[], avisos=[fuera], cuerpos=[])
    esc = leer_escenario(_escenario(A_MANO, []))
    det = bandas_quietas(doc.scene, esc, dyn)
    assert "— está unida por fijadores a la pieza móvil 'c1_tambor_motriz'" in det
    assert '"junta_motriz": "eje_motriz"' in det
    # una caja fuera de la huella de la banda no la toca: sin aserciones sobre ella, no es error
    esc = leer_escenario({**_escenario(A_MANO, [], cajas=False), "eventos": [
        {"t": 0, "tipo": "producto", "nombre": "lejos", "dims_mm": [100, 100, 100], "posicion_mm": [0, 2000, 900]}]})
    assert bandas_quietas(doc.scene, esc, dyn) is None


def test_la_banda_quieta_se_rechaza_antes_de_preparar_la_dinamica(doc, monkeypatch):
    """F6b, defecto 3: el rechazo no espera los cascos (22 s en la 73); lo da la PREVISIÓN de
    las bandas (`cosim_bandas.prever`) con la misma lógica pura de la dinámica."""
    from apolo.services.cosim_bandas import prever
    from apolo.services.cosim_snapshot import snapshot_cosim
    from apolo.services.errors import ServiceError

    class Preparo(Exception):
        pass

    def preparar(*a, **k):
        raise Preparo

    monkeypatch.setattr("apolo.physics.dinamica.prepare_dynamics", preparar)
    sin_auto = {"auto_bandas": False}
    with pytest.raises(ServiceError) as e:
        snapshot_cosim(doc, _escenario(sin_auto, ["-K1.cuenta >= 0 al_final"]))
    det = e.value.detail
    assert det.startswith("mecánica: 'c1_banda' («Faja de banda · Banda») no avanza en esta simulación")
    assert "el escenario pone caja encima" in det and '"junta_motriz": "eje_motriz"' in det
    # sin tierra declarada la junta del tambor queda fuera: la previsión lo dice igual que la
    # dinámica (la faja v4 ancla sus pies; aquí se le quitan los anclajes)
    con_bandas = {**sin_auto, "bandas": BANDAS}
    with monkeypatch.context() as m,             pytest.raises(ServiceError, match="su junta motriz 'eje_motriz' quedó fuera"):
        m.setattr(doc, "grounds", {})
        snapshot_cosim(doc, _escenario(con_bandas, ["-K1.cuenta >= 0 al_final"]))
    # con autodetección no se puede prever barato: decide la dinámica (el chequeo de después)
    assert prever(doc.scene, doc.joints, doc.fasteners, doc.grounds, {**A_MANO, "duracion_s": 1}) is None
    # con el riel a tierra y la banda declarada la previsión no objeta: llega a preparar la dinámica
    doc.execute("ground", {"name": "piso", "feature": "c1_rail1"})
    try:
        p = prever(doc.scene, doc.joints, doc.fasteners, doc.grounds, {**con_bandas, "duracion_s": 1})
        assert [b.pieza for b in p.bandas] == ["c1_banda"] and p.cuerpos[0]["junta"] == JUNTA
        with pytest.raises(Preparo):
            snapshot_cosim(doc, _escenario(con_bandas, ["-K1.cuenta >= 0 al_final"]))
    finally:
        doc.undo()
