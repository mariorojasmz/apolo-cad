"""El balance de producto de punta a punta por la API (plan balance-de-producto, D7, D10, D11).

La faja de prueba con arranque directo (`cosim_lazo_banco.faja_directo`), su capacidad nominal
declarada (`paquetes_por_minuto`) y un escenario de flujo «al ritmo nominal»:
  - `PUT /api/escenarios/…` guarda el NÚMERO del ritmo, no «nominal»;
  - `POST /api/cosim/run` corre, el compacto trae el balance y su texto, el resultado guardado
    también y `GET /api/escenarios` lo muestra;
  - las dos puertas lo cuentan: la de entrega en verde para el balance y la regla general OK;
  - subir la capacidad deja el escenario por debajo del nominal: SIN_EVALUAR, con la acción.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("mujoco")

import apolo.api.main as api  # noqa: E402
from apolo.services import flujo_producto as FP  # noqa: E402
from cosim_lazo_banco import MECANICA, MOTOR, faja_directo  # noqa: E402

FLUJO = {
    "duracion_s": 8.0, "descripcion": "cajas al ritmo nominal",
    "mecanica": {**MECANICA, "sumideros": [{"nombre": "fin", "punto_mm": [1400, 0, 0], "normal": [1, 0, 0]}]},
    "acoples": {"motores": MOTOR},
    "acciones": [{"t": 0.2, "accion": "pulsar", "dispositivo": "-S2", "durante_s": 0.2}],
    "eventos": [{"t": 0.0, "tipo": "producto", "nombre": "caja", "dims_mm": [150, 120, 100],
                 "masa_kg": 2.0, "posicion_mm": [-500, 0, 850.5]}],
    "flujo": {"ritmo_por_min": "nominal", "plazo_s": 8.0},
    "aserciones": ["flujo.cuadra al_final", "flujo.fin >= 1 al_final"],
}


@pytest.fixture(scope="module")
def doc():
    d = faja_directo()
    d.set_requirements({"paquetes_por_minuto": 20})
    return d


@pytest.fixture
def c(doc, monkeypatch):
    monkeypatch.setattr(api, "DOC", doc)
    return TestClient(api.app)


@pytest.fixture(scope="module")
def corrida(doc):
    api.DOC = doc
    c = TestClient(api.app)
    put = c.put("/api/escenarios/flujo", json={"escenario": FLUJO})
    assert put.status_code == 200, put.text
    run = c.post("/api/cosim/run", json={"escenario": "flujo"})
    assert run.status_code == 200, run.text
    return {"put": put.json(), "run": run.json()}


def test_nominal_se_guarda_como_numero(doc, corrida):
    assert corrida["put"]["flujo"] == {"ritmo_por_min": 20.0, "sumideros": ["fin"]}
    guardado = doc.escenarios["flujo"]["escenario"]
    assert guardado["flujo"]["ritmo_por_min"] == 20
    assert FLUJO["flujo"]["ritmo_por_min"] == "nominal"  # el dict del agente no cambió


def test_la_corrida_trae_el_balance(doc, corrida, c):
    run = corrida["run"]
    assert run["veredicto"] == "pasa", run["aserciones"]
    fl = run["flujo"]
    assert fl["cuadra"] is True and fl["entraron"] >= 2 and fl["por_sumidero"]["fin"] >= 1
    assert fl["balance"].startswith(f"{fl['entraron']} entraron · {fl['por_sumidero']['fin']} fin · 0 trabados")
    assert "senales" not in fl
    assert doc.escenarios["flujo"]["resultado"]["flujo"]["balance"] == fl["balance"]
    fila = next(f for f in c.get("/api/escenarios").json()["escenarios"] if f["nombre"] == "flujo")
    assert fila["balance"] == fl["balance"] and fila["estado"] == "pasa"


def test_las_puertas_lo_cuentan(doc, corrida, c):
    rep = c.post("/api/delivery-check", json={}).json()
    assert "balance de producto al ritmo nominal" in rep["resumen"]["chequeos_ok"]
    assert not [b for b in rep["bloqueantes"] + rep["avisos"] if b["regla"] == "balance de producto"]
    r = FP.evaluar(doc)
    assert r["estado"] == "ok" and r["nominal"] == 20.0, r


def test_subir_la_capacidad_deja_el_escenario_por_debajo(doc, corrida):
    previo = dict(doc.requirements)
    try:
        doc.set_requirements({**previo, "paquetes_por_minuto": 40})
        r = FP.evaluar(doc)
        assert r["estado"] == "falta" and "40/min" in r["detalle"] and "a 20/min" in r["detalle"]
        assert "set_scenario" in r["accion"]
    finally:
        doc.set_requirements(previo)
