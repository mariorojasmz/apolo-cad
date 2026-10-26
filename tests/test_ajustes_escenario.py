"""Ajustes de PRUEBA por escenario (plan cotizacion-identificada-y-ajustes-por-escenario D5–D7).

  - D5: `escenario.ajustes = {designación: {campo: valor}}` se valida como en `add_device`
    (designación o campo desconocidos → 400 con la corrección) y vale SÓLO en la co-simulación de
    ese escenario: el snapshot con el ajuste de prueba es el MISMO que el de un documento con ese
    ajuste en su `add_device`, y el documento no cambia;
  - D6: sin `ajustes` el escenario guardado, su hash y la firma del documento son los de antes
    (literal calculado en la base 712a9bd): los resultados guardados siguen vigentes y
    `COSIM_EPOCH` no sube; con `ajustes`, cambiar uno vence sólo ESE resultado;
  - D7: lo que leen el manual y la memoria (`services/electrico`: el modelo y el circuito) sigue
    con el valor del `add_device` aunque un escenario lo pise;
  - integral: un atasco parcial que con `sobrecarga_s` = 1 s de prueba dispara el variador y sin
    él no, por la API, con `ajustes_de_prueba` en la respuesta y en el resultado guardado.
"""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

from apolo.cosim.escenario import EscenarioInvalido, leer_escenario
from apolo.doc.document import Document
from apolo.services import escenario_ajustes as EA
from apolo.services import escenarios as E
from apolo.services.electrico import circuito, modelo
from apolo.services.errors import ServiceError
from tablero_electrico import arranque_variador_plc

#: Un escenario tal como lo guardaba la base (sin `ajustes`): su hash, calculado con el código de
#: 712a9bd, no puede cambiar (D6: un resultado guardado antes de F2 sigue vigente).
ESC_BASE = {"duracion_s": 3.0, "descripcion": "marcha y seta",
            "acoples": {"motores": {"-M1": {"junta": "c1_eje_motriz", "direccion_transporte": [1, 0, 0]}}},
            "acciones": [{"t": 0.3, "accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha",
                          "durante_s": 0.2},
                         {"t": 2.2, "accion": "presionar", "dispositivo": "-S0"}],
            "aserciones": ["-K1.%QX0.0 == false dentro_de 0,1 s desde presionar -S0"]}
HASH_BASE = "417dd2c8c93950bb"  # E.hash_escenario(ESC_BASE) en 712a9bd


@pytest.fixture(scope="module")
def tablero() -> Document:
    doc = Document("tablero-ajustes")
    doc.execute_many(arranque_variador_plc())
    return doc


def _ajustes_vfd(doc) -> dict:
    return dict(next(d for d in modelo(doc).dispositivos if d.designacion == "-T2").ajustes)


# ── D5: la forma y la validación ──────────────────────────────────────────────────────────


def test_la_forma_de_los_ajustes_se_valida_al_leer_el_escenario():
    assert leer_escenario({"duracion_s": 1}).ajustes == {}
    assert leer_escenario({"duracion_s": 1, "ajustes": {"-T2": {"sobrecarga_s": 5}}}).ajustes == {
        "-T2": {"sobrecarga_s": 5}}
    for malo, texto in (({"-T2": 5}, "ajustes.-T2"), ({"-T2": {}}, "al menos un"), ([1], "objeto")):
        with pytest.raises(EscenarioInvalido, match=texto):
            leer_escenario({"duracion_s": 1, "ajustes": malo})
    with pytest.raises(EscenarioInvalido, match="«ajuste»"):
        leer_escenario({"duracion_s": 1, "ajuste": {}})  # ¿quisiste decir «ajustes»?


def test_poner_valida_contra_el_tablero_como_add_device(tablero):
    esc = {"duracion_s": 1}
    with pytest.raises(ServiceError) as e:
        E.poner(tablero, "p", {**esc, "ajustes": {"-T3": {"sobrecarga_s": 5}}})
    assert e.value.status_code == 400 and "«-T3» no es un aparato del tablero" in e.value.detail
    assert "-T2" in e.value.detail  # ¿quisiste decir «-T2»?
    with pytest.raises(ServiceError) as e:
        E.poner(tablero, "p", {**esc, "ajustes": {"-T2": {"sobrecarga": 5}}})
    assert "no tiene el ajuste «sobrecarga»" in e.value.detail and "sobrecarga_s" in e.value.detail
    with pytest.raises(ServiceError) as e:
        E.poner(tablero, "p", {**esc, "ajustes": {"-T2": {"sobrecarga_s": "cinco"}}})
    assert "es un número" in e.value.detail
    with pytest.raises(ServiceError) as e:  # los opcionales del tipo, con su validación
        E.poner(tablero, "p", {**esc, "ajustes": {"-T2": {"STO_categoria": 7}}})
    assert "ISO 13849-1" in e.value.detail
    assert "p" not in tablero.escenarios  # un 400 no deja nada
    puesto = E.poner(tablero, "p", {**esc, "ajustes": {"-T2": {"sobrecarga_s": 5}}})
    assert puesto["nombre"] == "p" and tablero.escenarios["p"]["escenario"]["ajustes"] == {
        "-T2": {"sobrecarga_s": 5}}
    assert _ajustes_vfd(tablero) == {"STO_categoria": 1}  # el documento no cambió
    E.quitar(tablero, "p")


def test_sin_tablero_los_ajustes_se_validan_al_correr():
    doc = Document("sin-tablero")
    puesto = E.poner(doc, "p", {"duracion_s": 1, "ajustes": {"-T2": {"sobrecarga_s": 5}}})
    assert any("todavía no declara tablero" in a for a in puesto["avisos"])


def test_aplicar_pisa_sobre_una_copia_y_lista_el_valor_del_proyecto(tablero):
    me = modelo(tablero)
    antes = copy.deepcopy([d.ajustes for d in me.dispositivos])
    nuevo, usados = EA.aplicar(me, {"-T2": {"sobrecarga_s": 5}, "-M1": {"i": 40}})
    assert usados == [{"dispositivo": "-T2", "ajuste": "sobrecarga_s", "valor": 5, "proyecto": 60},
                      {"dispositivo": "-M1", "ajuste": "i", "valor": 40, "proyecto": 30}]
    por = {d.designacion: d for d in nuevo.dispositivos}
    assert por["-T2"].ajustes == {"STO_categoria": 1, "sobrecarga_s": 5} and por["-M1"].ajustes["i"] == 40
    assert [d.ajustes for d in me.dispositivos] == antes and modelo(tablero) is me
    assert EA.aplicar(me, {}) == (me, [])  # sin ajustes, el MISMO objeto
    assert EA.hipotesis(usados)[0] == ("-T2: sobrecarga_s = 5 es un ajuste de PRUEBA de este "
                                       "escenario (el proyecto: 60); el documento no cambia")
    with pytest.raises(ServiceError, match="fuera|va entre"):
        EA.aplicar(me, {"-M1": {"i": 1000}})  # el rango de la ficha, como en add_device


# ── D6: la firma y la vigencia ────────────────────────────────────────────────────────────


def test_sin_ajustes_el_escenario_y_su_hash_son_los_de_la_base(tablero):
    assert E.hash_escenario(ESC_BASE) == HASH_BASE
    firma = E.firma_documento(tablero)
    E.poner(tablero, "base", ESC_BASE)
    assert tablero.escenarios["base"]["escenario"] == ESC_BASE  # guardado tal cual: sin «ajustes»
    # un resultado guardado con la firma y el hash de antes sigue vigente
    ver = {"veredicto": "pasa", "aserciones": [{"asercion": "x", "pasa": True}]}
    E.guardar_resultado(tablero, "base", E.resultado_compacto(
        ver, {"resumen": {}}, firma=firma, hash_esc=HASH_BASE, simulacion=None))
    assert "ajustes_de_prueba" not in tablero.escenarios["base"]["resultado"]
    assert E.estado(tablero, "base") == {"estado": "pasa"}
    # el MISMO escenario con un ajuste de prueba es otro hash: su resultado vence, el otro no
    E.poner(tablero, "prueba", {**ESC_BASE, "ajustes": {"-T2": {"sobrecarga_s": 5}}})
    h = E.hash_escenario(tablero.escenarios["prueba"]["escenario"])
    assert h != HASH_BASE
    E.guardar_resultado(tablero, "prueba", E.resultado_compacto(
        ver, {"resumen": {}}, firma=firma, hash_esc=h, simulacion=None,
        ajustes=[{"dispositivo": "-T2", "ajuste": "sobrecarga_s", "valor": 5, "proyecto": 60}]))
    assert tablero.escenarios["prueba"]["resultado"]["ajustes_de_prueba"][0]["valor"] == 5
    E.poner(tablero, "prueba", {**ESC_BASE, "ajustes": {"-T2": {"sobrecarga_s": 2}}})
    assert E.estado(tablero, "prueba")["estado"] == "vencido"
    assert E.estado(tablero, "base") == {"estado": "pasa"}
    assert E.firma_documento(tablero) == firma  # ningún ajuste de escenario entra a la firma
    for n in ("base", "prueba"):
        E.quitar(tablero, n)


def test_la_memoria_del_aire_no_toma_de_nominal_un_escenario_con_ajustes_de_prueba():
    """D7: el tiempo de carrera de la memoria es del escenario NOMINAL; uno con ajustes de prueba
    (una presión regulada distinta) cuenta como uno de falla: sólo si no hay otro."""
    from apolo.services.neumatica import lecturas

    def ent(t, ajustes=None):
        return {"escenario": {"eventos": [], **({"ajustes": ajustes} if ajustes else {})},
                "resultado": {"aire": {"medicion": "m", "cilindros": {
                    "-MM1": {"t_avance_s": t, "x_max_mm": 100.0, "v_max_m_s": 0.3}}}}}

    prueba = ent(0.9, {"-QM1": {"p_regulada_bar": 3}})
    assert lecturas({"normal": ent(0.5), "prueba": prueba})["-MM1"]["escenario"] == "normal"
    assert lecturas({"prueba": prueba})["-MM1"]["escenario"] == "prueba"


# ── integral (MuJoCo): el atasco que dispara sólo con el ajuste de prueba ────────────────


@pytest.fixture(scope="module")
def faja():
    pytest.importorskip("mujoco")
    from cosim_lazo_banco import PROGRAMA, faja_variador

    doc = faja_variador()
    doc.execute("add_program", {"plc": "-K1", "fuente": PROGRAMA})
    return doc


def _atasco(ajustes=None) -> dict:
    from cosim_lazo_banco import PAR_PARCIAL_VARIADOR_NM, atasco_parcial, escenario_variador

    esc = escenario_variador(8.0, eventos=[atasco_parcial(1.5, PAR_PARCIAL_VARIADOR_NM)])
    esc["aserciones"] = ["-T2.falla == sobrecarga dentro_de 6,4 s desde atasco"]
    return {**esc, **({"ajustes": ajustes} if ajustes else {})}


def test_el_ajuste_de_prueba_es_el_mismo_snapshot_que_el_del_add_device(faja):
    """El mecanismo: pisar en el escenario = haberlo declarado en el `add_device` (mismos
    dispositivos y red hacia el worker), sin tocar el documento."""
    from cosim_lazo_banco import faja_variador

    from apolo.services.cosim_snapshot import snapshot_cosim

    con_ajuste = faja_variador(sobrecarga_s=1.0)
    a = snapshot_cosim(faja, _atasco({"-T2": {"sobrecarga_s": 1.0}}))
    b = snapshot_cosim(con_ajuste, _atasco())
    assert a.dispositivos == b.dispositivos and a.red == b.red
    assert a.ajustes == [{"dispositivo": "-T2", "ajuste": "sobrecarga_s", "valor": 1.0, "proyecto": 60}]
    assert b.ajustes == [] and a.hipotesis == b.hipotesis + EA.hipotesis(a.ajustes)
    assert "sobrecarga_s" not in _ajustes_vfd(faja)


def test_el_atasco_dispara_solo_con_el_ajuste_de_prueba_y_el_proyecto_queda_intacto(faja, monkeypatch):
    import apolo.api.main as api

    monkeypatch.setattr(api, "DOC", faja)
    c = TestClient(api.app)
    add_device = copy.deepcopy(next(x for x in faja.commands if x["params"].get("designacion") == "-T2"))
    firma = E.firma_documento(faja)
    circ = circuito(faja, "-T2")
    # un ajuste mal escrito: 400 con la corrección, sin guardar nada
    r = c.put("/api/escenarios/atasco_prueba", json={"escenario": _atasco({"-T2": {"sobrecarga": 1}})})
    assert r.status_code == 400 and "sobrecarga_s" in r.json()["detail"]
    assert c.put("/api/escenarios/atasco", json={"escenario": _atasco()}).status_code == 200
    assert c.put("/api/escenarios/atasco_prueba",
                 json={"escenario": _atasco({"-T2": {"sobrecarga_s": 1.0}})}).status_code == 200

    sin = c.post("/api/cosim/run", json={"escenario": "atasco"}).json()
    assert sin["veredicto"] == "falla" and "ajustes_de_prueba" not in sin
    con = c.post("/api/cosim/run", json={"escenario": "atasco_prueba"}).json()
    assert con["veredicto"] == "pasa", con["aserciones"]
    usados = [{"dispositivo": "-T2", "ajuste": "sobrecarga_s", "valor": 1.0, "proyecto": 60}]
    assert con["ajustes_de_prueba"] == usados
    assert any("ajuste de PRUEBA" in h for h in con["hipotesis"])
    guardado = faja.escenarios["atasco_prueba"]["resultado"]
    assert guardado["ajustes_de_prueba"] == usados and guardado["veredicto"] == "pasa"
    assert "ajustes_de_prueba" not in faja.escenarios["atasco"]["resultado"]

    # D7: el documento, el log y lo que leen manual y memoria siguen con el valor del proyecto
    assert next(x for x in faja.commands if x["params"].get("designacion") == "-T2") == add_device
    assert "sobrecarga_s" not in _ajustes_vfd(faja)
    assert circuito(faja, "-T2") == circ
    assert E.firma_documento(faja) == firma
    estados = {f["nombre"]: f["estado"] for f in c.get("/api/escenarios").json()["escenarios"]}
    assert estados == {"atasco": "falla", "atasco_prueba": "pasa"}
    # un inline con el ajuste corre igual y no guarda nada
    inline = c.post("/api/cosim/run", json={"escenario": _atasco({"-T2": {"sobrecarga_s": 1.0}})}).json()
    assert inline["veredicto"] == "pasa" and inline["ajustes_de_prueba"] == usados
