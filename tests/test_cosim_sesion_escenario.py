"""De la sesión en vivo a la prueba (plan V8.4 F4, D10): `POST /api/cosim/vivo/escenario`.

  - la cola de cajas: el escenario guardado tiene las instancias que tuvo la SESIÓN (su pool sale
    de la duración del escenario de base), recortada o extendida a la duración de la sesión;
  - guardar → correr por lote → la MISMA huella que la sesión (que se reproduce aquí con `Vivo`,
    el paso compartido de F1), con una sesión más larga que su base y una más corta;
  - las aserciones sugeridas pasan sobre su propia corrida y, aceptadas con `PUT
    /api/escenarios`, dan «pasa» por lote;
  - errores: otra firma del documento, escenario de base borrado o cambiado, nombre ocupado,
    sesión que no está en memoria, más de 60 s sin `hasta_s`;
  - de punta a punta: el `fin` del WebSocket trae la `sesion` y guardarla sin más da la huella
    de la sesión.
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("mujoco")

import apolo.api.main as api  # noqa: E402
from apolo.api.sims import SESIONES_GRABADAS  # noqa: E402
from apolo.cosim.escenario import leer_escenario  # noqa: E402
from apolo.cosim.sugeridas import candidatas, sugerir  # noqa: E402
from apolo.cosim.veredicto import Lector  # noqa: E402
from apolo.cosim.vivo import Vivo, escenario_vivo  # noqa: E402
from apolo.services import escenarios as E  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from apolo.services.errors import ServiceError  # noqa: E402
from apolo.services.sesion_viva import escenario_de_sesion, fijar_cola  # noqa: E402
from cosim_lazo_banco import PROGRAMA, escenario_variador, faja_variador  # noqa: E402

CAJA = {"t": 0.0, "tipo": "producto", "nombre": "caja", "dims_mm": [150, 120, 100], "masa_kg": 2.0,
        "cada_s": 0.5, "posicion_mm": [-500, 0, 850.5]}
#: la sesión: potenciómetro a fondo, marcha a 0,3 s y la seta a 2,5 s (k = intercambios de 2 ms)
PLAN = {0: [{"girar": "-S1", "valor": 1.0}],
        150: [{"accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha", "durante_s": 0.2}],
        1250: [{"presionar": "-S0"}]}


def _base(duracion_s: float) -> dict:
    esc = escenario_variador(duracion_s)
    esc["acciones"] = []
    esc["eventos"] = [dict(CAJA)]
    return esc


# ── la cola de cajas (puro) ─────────────────────────────────────────────────────────────────


def test_la_cola_queda_con_las_cajas_que_tuvo_la_sesion():
    esc = {"duracion_s": 2.0, "eventos": [
        dict(CAJA),                                                        # hasta el final
        {**CAJA, "nombre": "fija", "cantidad": 10},                          # 10 pedidas
        {**CAJA, "nombre": "tarde", "t": 2.5, "cada_s": None},              # nace tras la base
        {"t": 1.0, "tipo": "atasco", "junta": "j", "par_Nm": 5}]}
    cola = fijar_cola(esc, 2.0)
    assert [(c["nombre"], c["cantidad"]) for c in cola] == [("caja", 5), ("fija", 5)]
    assert [e.get("nombre", e["tipo"]) for e in esc["eventos"]] == ["caja", "fija", "atasco"]


def test_el_escenario_de_la_sesion_recorta_y_dice_por_que_no():
    vivo = escenario_vivo(_base(2.0))
    grab = [{"t": 0.0, "accion": "girar", "dispositivo": "-S1", "valor": 1.0},
            {"t": 2.5, "accion": "presionar", "dispositivo": "-S0"}]
    out = escenario_de_sesion(vivo, grab, 3.0, base="marcha")
    assert out["duracion_s"] == 3.0 and out["n_acciones"] == 2 and not out["recortada"]
    assert out["escenario"]["eventos"][0]["cantidad"] == 5  # el pool de la base (2 s), no el de 3 s
    assert "«marcha»" in out["escenario"]["descripcion"]
    tramo = escenario_de_sesion(vivo, grab, 3.0, base="marcha", hasta_s=1.0)
    assert tramo["recortada"] and tramo["n_acciones"] == 1 and tramo["escenario"]["duracion_s"] == 1.0
    with pytest.raises(ServiceError, match="hasta_s"):
        escenario_de_sesion(vivo, grab, 75.0, base="marcha")
    with pytest.raises(ServiceError, match="no avanzó"):
        escenario_de_sesion(vivo, [], 0.0, base="marcha")
    with pytest.raises(ServiceError, match="dispositivo"):  # lo valida la lectura del escenario
        escenario_de_sesion(vivo, [{"t": 1.0, "accion": "pulsar"}], 3.0, base="marcha")


# ── las aserciones sugeridas (puro) ─────────────────────────────────────────────────────────


def test_las_sugeridas_salen_de_lo_que_paso_y_pasan():
    esc = leer_escenario({"duracion_s": 4.0, "acciones": [
        {"t": 1.0, "accion": "pulsar", "dispositivo": "-S1"},
        {"t": 3.0, "accion": "presionar", "dispositivo": "-S0"}]})
    t = [k * 0.1 for k in range(41)]
    rpm = [0.0 if x < 1.0 else min(1750.0, (x - 1.0) * 1750.0) if x < 3.0 else max(0.0, 1750.0 - (x - 3.0) * 2000)
           for x in t]
    par = [0.0 if x < 1.0 else 12.0 if x < 3.05 else 0.0 for x in t]
    res = {"resumen": {"duracion_s": 4.0},
           "trazas": {"analogicas": {"t": t, "senales": {"-M1.rpm": rpm, "-M1.par_Nm": par}},
                      "discretas": {"-Q1.disparado": [[0.0, False], [3.4, True]],
                                    "-K1.Main.cuenta": [[0.0, 0], [1.5, 1], [2.5, 2]],
                                    "-K1.Main.timer_ms": [[0.0, 0], [1.5, 300]]}},
           "final": {"-K1.Main.cuenta": 2},
           "eventos": [{"t": 1.0, "accion": "pulsar", "dispositivo": "-S1"},
                       {"t": 3.0, "accion": "presionar", "dispositivo": "-S0"}]}
    textos = [s["asercion"] for s in sugerir(esc, res)]
    assert textos == [
        "-M1.rpm >= 1570 dentro_de 1.3 s desde pulsar -S1",      # 90 % de 1750 a 0,9 s: ×1,25 + 0,1
        "-M1.par_Nm == 0 dentro_de 0.3 s desde presionar -S0",
        "-M1.rpm <= 175 dentro_de 1.1 s desde presionar -S0",     # 10 % de lo que le quedaba
        "-Q1.disparado dentro_de 0.6 s desde presionar -S0",
        "-K1.Main.cuenta == 2 al_final"]  # el temporizador no es un contador
    # sin la seta en la corrida, nada se ancla a ella
    sin_seta = {**res, "eventos": res["eventos"][:1]}
    assert not any("presionar" in s["asercion"] for s in sugerir(esc, sin_seta))
    assert len(candidatas(esc, Lector(sin_seta))) < len(textos)


def test_una_candidata_que_no_pasa_no_se_sugiere(monkeypatch):
    import apolo.cosim.sugeridas as S

    esc = leer_escenario({"duracion_s": 1.0})
    res = {"resumen": {"duracion_s": 1.0}, "final": {"-M1.rpm": 10.0},
           "trazas": {"analogicas": {"t": [0.0, 1.0], "senales": {"-M1.rpm": [0.0, 10.0]}}}}
    monkeypatch.setattr(S, "candidatas", lambda e, lec: ["-M1.rpm >= 5 al_final", "-M1.rpm >= 99 al_final",
                                                         "-M1.rpm >= 1 dentro_de 1 s desde pulsar -S9"])
    assert [s["asercion"] for s in sugerir(esc, res)] == ["-M1.rpm >= 5 al_final"]


# ── por la API ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def maquina():
    doc = faja_variador()
    doc.execute("add_program", {"plc": "-K1", "fuente": PROGRAMA})
    return doc


@pytest.fixture
def c(maquina, monkeypatch):
    monkeypatch.setattr(api, "DOC", maquina)
    maquina.escenarios.clear()
    cli = TestClient(api.app)
    return cli


def _vivo(doc, base: dict, duracion_s: float) -> tuple[list, str]:
    """La sesión, de golpe y con trazas (F1): (grabación, huella de lo que se vio)."""
    v = Vivo(snapshot_cosim(doc, escenario_vivo(base)), trazas=True)
    n = round(duracion_s / v.dt)
    while v.k < n:
        for msg in PLAN.get(v.k, []):
            assert v.recibir(msg) is None
        v.avanzar(min([k for k in PLAN if k > v.k] + [n]) - v.k)
        v.respuestas()
    return v.grabacion, v.cerrar_lote()


def _cuerpo(doc, base_nombre: str, grab: list, duracion_s: float, **extra) -> dict:
    return {"grabacion": grab, "duracion_s": duracion_s, "base": base_nombre,
            "firma": E.firma_documento(doc),
            "hash_base": E.hash_escenario(doc.escenarios[base_nombre]["escenario"]), **extra}


@pytest.mark.parametrize("dur_base,dur_sesion", [(2.0, 3.0), (4.0, 3.0)])
def test_guardar_y_correr_por_lote_da_las_trazas_de_la_sesion(c, maquina, dur_base, dur_sesion):
    base = _base(dur_base)
    assert c.put("/api/escenarios/base", json={"escenario": base}).status_code == 200
    grab, h_sesion = _vivo(maquina, base, dur_sesion)
    r = c.post("/api/cosim/vivo/escenario", json={"nombre": "arranque", **_cuerpo(maquina, "base", grab, dur_sesion)})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["huella"] == h_sesion  # las mismas trazas que la sesión
    assert out["guardado"] and out["estado"] == "sin_aserciones" and out["duracion_s"] == dur_sesion
    assert out["cola"] == [{"nombre": "caja", "cantidad": int(dur_base / 0.5) + 1, "desde_s": 0.0, "cada_s": 0.5}]
    guardado = maquina.escenarios["arranque"]["escenario"]
    assert guardado == out["escenario"] and "aserciones" not in guardado  # propone, no impone
    # correrlo otra vez por lote (el camino de simulate) da la misma huella
    corrida = c.post("/api/cosim/run", json={"escenario": "arranque"}).json()
    assert corrida["resumen"]["huella"] == h_sesion
    sugeridas = [s["asercion"] for s in out["aserciones_sugeridas"]]
    assert any(s.startswith("-M1.rpm >= ") and s.endswith("desde pulsar -S1") for s in sugeridas)
    assert any(s.startswith("-M1.par_Nm == 0 ") and s.endswith("desde presionar -S0") for s in sugeridas)
    # aceptarlas con set_scenario: la prueba pasa
    aceptado = {**guardado, "aserciones": sugeridas}
    assert c.put("/api/escenarios/arranque", json={"escenario": aceptado}).status_code == 200
    ver = c.post("/api/cosim/run", json={"escenario": "arranque"}).json()
    assert ver["veredicto"] == "pasa", json.dumps(ver["aserciones"], ensure_ascii=False)
    assert ver["resumen"]["huella"] == h_sesion


def test_lo_que_ya_no_reproduce_se_rechaza(c, maquina):
    base = _base(1.0)
    assert c.put("/api/escenarios/base", json={"escenario": base}).status_code == 200
    grab = [{"t": 0.0, "accion": "girar", "dispositivo": "-S1", "valor": 1.0}]
    cuerpo = _cuerpo(maquina, "base", grab, 0.5)

    def guardar(**cambios):
        return c.post("/api/cosim/vivo/escenario", json={"nombre": "x", **cuerpo, **cambios})

    r = guardar(firma="otra")
    assert r.status_code == 409 and "otro modelo" in r.json()["detail"]
    r = guardar(base="no-hay")
    assert r.status_code == 404 and "«no-hay»" in r.json()["detail"] and "base" in r.json()["detail"]
    r = guardar(hash_base="otro")
    assert r.status_code == 409 and "cambió desde la sesión" in r.json()["detail"]
    r = guardar(nombre="base")
    assert r.status_code == 409 and "reemplazar" in r.json()["detail"]
    r = guardar(duracion_s=90.0)
    assert r.status_code == 400 and "hasta_s" in r.json()["detail"]
    assert set(maquina.escenarios) == {"base"}  # nada se guardó
    r = c.post("/api/cosim/vivo/escenario", json={"nombre": "x", "sesion": "vnohay"})
    assert r.status_code == 404 and "vnohay" in r.json()["detail"]


def test_de_punta_a_punta_el_fin_trae_la_sesion_y_se_guarda_sin_mas(c, maquina):
    base = _base(1.0)
    assert c.put("/api/escenarios/base", json={"escenario": base}).status_code == 200
    token = c.get("/api/health").json()["documento"]
    with c.websocket_connect(f"/api/cosim/vivo?documento={token}&escenario=base&ritmo=0&max_s=1.2") as ws:
        assert ws.receive_json()["tipo"] == "inicio"
        ws.send_json({"girar": "-S1", "valor": 1.0})
        ws.send_json({"pulsar": "-S1", "actuador": "marcha", "durante_s": 0.2})
        while True:
            m = ws.receive()
            if m.get("text") and json.loads(m["text"])["tipo"] == "fin":
                fin = json.loads(m["text"])
                break
    assert fin["sesion"] and fin["base"] == "base" and fin["firma"] and fin["hash_base"]
    assert fin["escenario"]["eventos"][0]["cantidad"] == 3  # el pool de la base (1 s, cada 0,5 s)
    assert SESIONES_GRABADAS.get(fin["sesion"])["grabacion"] == fin["grabacion"]
    out = c.post("/api/cosim/vivo/escenario", json={"nombre": "vivo"}).json()  # la última sesión
    assert out["sesion"] == fin["sesion"] and out["guardado"] and out["escenario"] == fin["escenario"]
    # la sesión reproducida con sus horas grabadas da la huella del lote
    v = Vivo(snapshot_cosim(maquina, escenario_vivo(copy.deepcopy(base))), trazas=True)
    por_k = {}
    for g in fin["grabacion"]:
        por_k.setdefault(round(g["t"] / v.dt), []).append({k: x for k, x in g.items() if k != "t"})
    n = round(fin["t"] / v.dt)
    while v.k < n:
        for msg in por_k.get(v.k, []):
            v.recibir(msg)
        v.avanzar(min([k for k in por_k if k > v.k] + [n]) - v.k)
        v.respuestas()
    assert v.cerrar_lote() == out["huella"]
