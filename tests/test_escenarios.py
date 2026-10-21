"""Los escenarios de prueba como metadato del documento (plan V8.3 D12) y su regla en la puerta
de entrega (D14), sin correr la co-simulación (eso es `test_cosim_api.py`):

  - `set_scenario` valida el escenario y sus aserciones (un 400 con la corrección) y avisa de los
    dispositivos que el tablero no tiene; viaja en el `.apolo` y no entra al log ni al undo;
  - VIGENCIA: el resultado guarda la firma del documento (log + materiales) y el hash del
    escenario; cambiar la máquina o el escenario lo VENCE, un color no;
  - la regla «escenarios»: ROJO si uno falla vigente, AMARILLO si hay sin correr, vencidos o sin
    aserciones, VERDE si todos pasan y están vigentes; sin escenarios, la puerta de siempre.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tablero_electrico import arranque_variador_plc

import apolo.api.main as api
from apolo.doc.document import Document
from apolo.library.delivery import delivery_report
from apolo.services import escenarios as E
from apolo.services.errors import ServiceError

ESC = {
    "duracion_s": 3, "descripcion": "marcha y seta",
    "acciones": [{"t": 0.3, "accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha", "durante_s": 0.2},
                 {"t": 2.2, "accion": "presionar", "dispositivo": "-S0"}],
    "acoples": {"motores": {"-M1": {"junta": "c1_eje_motriz"}}},
    "aserciones": ["-M1.rpm >= 1700 dentro_de 2 s desde pulsar -S1",
                   "-M1.par_Nm == 0 dentro_de 0,5 s desde presionar -S0"],
}


def _doc() -> Document:
    doc = Document("escenarios")
    doc.execute_many(arranque_variador_plc())
    return doc


def _resultado(doc, nombre, veredicto="pasa"):
    """Lo que dejaría una corrida: el compacto con la firma y el hash de AHORA."""
    filas = [{"asercion": "-M1.rpm >= 1700 dentro_de 2 s desde pulsar -S1", "pasa": veredicto == "pasa",
              "detalle": "golden"}]
    ver = {"veredicto": veredicto, "aserciones": filas, "n_fallidas": int(veredicto != "pasa")}
    res = {"resumen": {"huella": "h", "duracion_s": 3.0, "factor_tiempo_real": 1.5}}
    compacto = E.resultado_compacto(ver, res, firma=E.firma_documento(doc),
                                    hash_esc=E.hash_escenario(doc.escenarios[nombre]["escenario"]),
                                    simulacion="s1")
    assert E.guardar_resultado(doc, nombre, compacto)


def _estado(doc, nombre):
    return E.estado(doc, nombre)["estado"]


def test_poner_valida_y_avisa_lo_que_el_tablero_no_tiene():
    doc = _doc()
    out = E.poner(doc, "marcha", ESC)
    assert out["estado"] == "sin_correr" and out["n_aserciones"] == 2 and out["avisos"] == []
    assert out["aserciones"][1] == "-M1.par_Nm == 0 dentro_de 0.5 s desde presionar -S0"
    otro = E.poner(doc, "raro", {**ESC, "acciones": [{"t": 1, "accion": "pulsar", "dispositivo": "-S7"}],
                                 "aserciones": ["-Q9.disparado nunca"]})
    assert otro["avisos"] == ["el tablero no tiene -Q9", "el tablero no tiene -S7"]
    assert E.poner(Document("vacío"), "x", {"duracion_s": 1})["avisos"][0].startswith("el documento todavía no")
    with pytest.raises(ServiceError) as e:
        E.poner(doc, "malo", {**ESC, "aserciones": ["-M1.rpm >= 1700 dentro_de 2 s desde pulsar -S9"]})
    assert e.value.status_code == 400 and "¿Quisiste decir «pulsar -S1»?" in e.value.detail
    with pytest.raises(ServiceError, match="nombre de 1 a 60"):
        E.poner(doc, "a/b", ESC)
    with pytest.raises(ServiceError) as e:
        E.quitar(doc, "marca")
    assert e.value.status_code == 404 and "marcha" in e.value.detail


def test_el_escenario_viaja_en_el_apolo_y_no_toca_el_log_ni_el_undo():
    doc = _doc()
    log, pila = list(doc.commands), len(doc._undo)
    E.poner(doc, "marcha", ESC)
    _resultado(doc, "marcha")
    assert doc.commands == log and len(doc._undo) == pila
    vuelta = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert vuelta.escenarios == doc.escenarios and _estado(vuelta, "marcha") == "pasa"


def test_la_vigencia_vence_al_cambiar_la_maquina_o_el_escenario():
    doc = _doc()
    E.poner(doc, "marcha", ESC)
    assert _estado(doc, "marcha") == "sin_correr"
    _resultado(doc, "marcha")
    assert _estado(doc, "marcha") == "pasa"
    # la máquina cambia (un comando del carril también: el log entero cuenta)
    cid = doc.execute("add_device", {"ref": "PILOTO-24V-VERDE", "designacion": "-P9"})
    st = E.estado(doc, "marcha")
    assert st == {"estado": "vencido", "motivo": "la máquina cambió desde que se corrió", "ultimo": "pasa"}
    doc.undo()
    assert _estado(doc, "marcha") == "pasa"  # el mismo log: vuelve a estar vigente
    doc.redo()
    _resultado(doc, "marcha")
    assert _estado(doc, "marcha") == "pasa"
    # un color no cambia la máquina; un material (la masa) sí
    doc.colors["x"] = "#ff0000"
    assert _estado(doc, "marcha") == "pasa"
    doc.materials["x"] = "aluminio"
    assert _estado(doc, "marcha") == "vencido"
    doc.materials.clear()
    # el escenario cambia: vencido; volver a poner el MISMO no lo vence
    E.poner(doc, "marcha", {**ESC, "duracion_s": 4})
    assert E.estado(doc, "marcha")["motivo"] == "el escenario cambió desde que se corrió"
    E.poner(doc, "marcha", ESC)
    assert _estado(doc, "marcha") == "pasa" and cid


def _puerta(escenarios):
    return delivery_report(n_solidos=0, interferencias=[], soundness={"has_ground": True, "floating": []},
                           lints=[], integridad=[], suprimidos=[], poses=None, escenarios=escenarios)


def test_la_regla_escenarios_de_la_puerta():
    doc = _doc()
    assert E.reglas_escenarios(doc) is None
    base = _puerta(None)
    assert base["veredicto"] == "VERDE" and not any("escenarios" in c for c in base["resumen"]["chequeos_ok"])
    E.poner(doc, "marcha", ESC)
    E.poner(doc, "seta", ESC)
    E.poner(doc, "nada", {"duracion_s": 1})
    # sin correr → AMARILLO
    rep = _puerta(E.reglas_escenarios(doc))
    assert rep["veredicto"] == "AMARILLO" and [a["regla"] for a in rep["avisos"]] == [
        "escenarios · marcha", "escenarios · seta", "escenarios · nada"]
    assert "sin correr" in rep["avisos"][0]["detalle"]
    # todos pasan y vigentes → VERDE
    E.quitar(doc, "nada")
    _resultado(doc, "marcha")
    _resultado(doc, "seta")
    rep = _puerta(E.reglas_escenarios(doc))
    assert rep["veredicto"] == "VERDE" and "escenarios (2, vigentes)" in rep["resumen"]["chequeos_ok"]
    # uno falla → ROJO, con la aserción que falló
    _resultado(doc, "seta", "falla")
    rep = _puerta(E.reglas_escenarios(doc))
    assert rep["veredicto"] == "ROJO" and rep["bloqueantes"][0]["regla"] == "escenarios · seta"
    assert "-M1.rpm >= 1700" in rep["bloqueantes"][0]["detalle"]
    # la máquina cambia: el que fallaba queda VENCIDO (AMARILLO), no rojo
    doc.execute("add_device", {"ref": "PILOTO-24V-VERDE", "designacion": "-P9"})
    rep = _puerta(E.reglas_escenarios(doc))
    assert rep["veredicto"] == "AMARILLO" and "el último dio «falla»" in rep["avisos"][1]["detalle"]
    # un escenario sin aserciones no prueba nada: AMARILLO aunque haya corrido
    E.poner(doc, "nada", {"duracion_s": 1})
    _resultado(doc, "nada", "sin_aserciones")
    filas = {f["escenario"]: f for f in E.reglas_escenarios(doc)}
    assert filas["nada"]["estado"] == "aviso" and "no prueba nada" in filas["nada"]["detalle"]


# ── por la API ──────────────────────────────────────────────────────────────────────────────


def test_los_escenarios_por_la_api(monkeypatch):
    doc = _doc()
    monkeypatch.setattr(api, "DOC", doc)
    c = TestClient(api.app)
    r = c.put("/api/escenarios/marcha", json={"escenario": ESC})
    assert r.status_code == 200 and r.json()["estado"] == "sin_correr"
    assert c.put("/api/escenarios/mala", json={"escenario": {"duracion": 2}}).status_code == 400
    lista = c.get("/api/escenarios").json()
    assert [f["nombre"] for f in lista["escenarios"]] == ["marcha"]
    assert lista["escenarios"][0] == {"nombre": "marcha", "estado": "sin_correr",
                                      "descripcion": "marcha y seta", "duracion_s": 3, "n_aserciones": 2}
    uno = c.get("/api/escenarios", params={"nombre": "marcha"}).json()
    assert uno["escenario"] == ESC and uno["estado"] == "sin_correr"
    assert c.get("/api/escenarios", params={"nombre": "marca"}).status_code == 404
    # la puerta lo cuenta: sin correr → aviso
    rep = c.post("/api/delivery-check", json={}).json()
    assert any(a["regla"] == "escenarios · marcha" for a in rep["avisos"])
    assert c.delete("/api/escenarios/marcha").json()["escenarios"] == []
    assert c.delete("/api/escenarios/marcha").status_code == 404
