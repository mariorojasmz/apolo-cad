"""Acceso de herramienta en la PUERTA DE ENTREGA (plan acceso-de-herramienta, F2 / D3):
ninguna llave libre = ROJO; sólo la boca = AVISO; sin tornillería, la puerta EXACTAMENTE igual."""

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.library.delivery import AMARILLO, ROJO, VERDE, delivery_report
from apolo.services.delivery_inputs import delivery_inputs


def _reporte(**kw):
    base = dict(n_solidos=10, interferencias=[],
                soundness={"has_ground": True, "floating": [], "isolated": []},
                lints=[], integridad=[], suprimidos=[], poses=None, gravedad=None)
    base.update(kw)
    return delivery_report(**base)


def _acc(**kw):
    rep = {"evaluados": 1, "ok": 0, "sin_herramienta": [], "solo_boca": [], "no_evaluados": [],
           "ms": 3}
    rep.update(kw)
    return rep


_TUERCA = {"id": "c9", "nombre": "Tuerca del eje (-Y)", "tipo": "tuerca", "llave_mm": 18.0,
           "bloquean": ["Larguero (-Y)"]}


# ------------------------------------------------------------------ agregador puro
def test_sin_acceso_la_puerta_no_cambia():
    rep = _reporte()
    assert rep == _reporte(acceso_herramienta=None)
    assert "acceso" not in str(rep)  # ni en ok ni en no_aplica: como si no existiera


def test_ninguna_llave_es_rojo():
    rep = _reporte(acceso_herramienta=_acc(sin_herramienta=[_TUERCA]))
    assert rep["veredicto"] == ROJO
    b = rep["bloqueantes"][0]
    assert b["regla"] == "acceso de herramienta · la llave no entra"
    assert b["piezas"] == ["c9"]  # nombre_de por defecto = identidad
    assert "Larguero (-Y)" in b["detalle"] and "llave 18 mm" in b["detalle"]


def test_solo_boca_es_amarillo_y_libre_es_verde():
    rep = _reporte(acceso_herramienta=_acc(solo_boca=[_TUERCA]))
    assert rep["veredicto"] == AMARILLO
    assert rep["avisos"][0]["regla"] == "acceso de herramienta · sólo llave de boca"
    ok = _reporte(acceso_herramienta=_acc(evaluados=40, ok=40))
    assert ok["veredicto"] == VERDE
    assert "acceso de herramienta (40 fijador(es))" in ok["resumen"]["chequeos_ok"]


def test_no_evaluados_se_declaran_no_cuentan_verde():
    rep = _reporte(acceso_herramienta=_acc(
        evaluados=0, no_evaluados=[{"id": "c3", "nombre": "Perno", "motivo": "x"}]))
    assert rep["veredicto"] == VERDE  # no bloquea, pero tampoco figura como chequeo ok
    assert not any("acceso" in x for x in rep["resumen"]["chequeos_ok"])
    assert any(x.startswith("acceso de herramienta: 1 fijador") for x in rep["no_aplica"])


# ------------------------------------------------------------------ servicio (doc → kwargs)
def _tuerca_bajo_ala(doc: Document) -> None:
    doc.execute("create_box", {"name": "Placa de asiento", "width": 120, "depth": 120,
                               "height": 10, "position": {"z": -5}})
    doc.execute("create_cylinder", {"name": "Eje roscado", "radius": 6, "height": 60,
                                    "position": {"z": 10}})
    doc.execute("insert_component", {"component": "TUERCA-M12", "name": "Tuerca del eje",
                                     "position": {"z": 5}})
    doc.execute("create_box", {"name": "Ala del perfil", "width": 8, "depth": 120,
                               "height": 50, "position": {"x": 15.5, "z": 25}})


def test_sin_tornilleria_los_kwargs_de_siempre():
    d = Document("sin tornillería")
    d.execute("create_box", {"name": "Base", "width": 100, "depth": 100, "height": 10})
    entradas = delivery_inputs(d, expand=lambda v: [])
    assert "acceso_herramienta" not in entradas
    assert delivery_report(**entradas) == delivery_report(**entradas, acceso_herramienta=None)


def test_servicio_tuerca_bajo_ala_es_rojo_con_nombres():
    d = Document("tuerca bajo ala")
    _tuerca_bajo_ala(d)
    entradas = delivery_inputs(d, expand=lambda v: [])
    rep = delivery_report(**entradas)
    b = next(x for x in rep["bloqueantes"] if x["regla"].startswith("acceso de herramienta"))
    nut = next(f for f in d.scene.values() if f.name == "Tuerca del eje")
    assert b["piezas"] == [f"Tuerca del eje ({nut.id})"]
    assert "Ala del perfil" in b["detalle"]


@pytest.fixture()
def client():
    api.DOC = Document("acceso-test")
    return TestClient(api.app)


def test_endpoint_delivery_check_lleva_el_acceso(client):
    acciones = [
        {"type": "create_box", "params": {"name": "Placa de asiento", "width": 120,
                                          "depth": 120, "height": 10,
                                          "position": {"z": -5}}},
        {"type": "create_cylinder", "params": {"name": "Eje roscado", "radius": 6,
                                               "height": 60, "position": {"z": 10}}},
        {"type": "insert_component", "params": {"component": "TUERCA-M12",
                                                "name": "Tuerca del eje",
                                                "position": {"z": 5}}},
    ]
    assert client.post("/api/commands/batch", json={"actions": acciones}).status_code == 200
    rep = client.post("/api/delivery-check", json={}).json()
    assert "acceso de herramienta (1 fijador(es))" in rep["resumen"]["chequeos_ok"], rep
