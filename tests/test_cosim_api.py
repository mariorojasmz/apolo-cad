"""La FAT virtual por la API (plan V8.3 D11–D14), de punta a punta sobre la faja de prueba con su
tablero por variador y PLC (`cosim_lazo_banco.faja_variador`) y el programa en el CARRIL
(`add_program`):

  - el escenario «fat» (marcha, cajas contadas por la fotocelda, seta y liberarla) se declara con
    `PUT /api/escenarios/fat`, corre como JOB en su cola (`?async=true` → recibo → `GET
    /api/jobs/{id}`), PASA, queda guardado y vigente, y la puerta lo cuenta en verde;
  - el MISMO escenario con el programa saboteado (sin la seta) sale ROJO: primero probado con
    `test_plc` sin guardarlo (el escenario sigue en verde), después guardado en el carril (el
    resultado queda vencido) y corrido (falla, la puerta da ROJO);
  - `get_simulation` lee la corrida por partes; `test_plc` compila sin correr.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("mujoco")

import apolo.api.main as api  # noqa: E402
from cosim_lazo_banco import FOTO, MECANICA, MOTOR, PROGRAMA, faja_variador  # noqa: E402

SABOTEADO = (PROGRAMA.replace("IF marcha AND seta_ok AND paro AND NOT falla_vfd THEN",
                              "IF marcha AND paro AND NOT falla_vfd THEN")
             .replace("IF NOT paro OR NOT seta_ok OR falla_vfd THEN", "IF NOT paro OR falla_vfd THEN"))
FAT = {
    "duracion_s": 3.0, "descripcion": "marcha, conteo y seta",
    "mecanica": MECANICA, "acoples": {"motores": MOTOR, "sensores": FOTO},
    "acciones": [{"t": 0.0, "accion": "girar", "dispositivo": "-S1", "valor": 1.0},
                 {"t": 0.3, "accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha", "durante_s": 0.2},
                 {"t": 2.2, "accion": "presionar", "dispositivo": "-S0"},
                 {"t": 2.6, "accion": "liberar", "dispositivo": "-S0"}],
    "eventos": [{"t": 0.0, "tipo": "producto", "nombre": "caja", "dims_mm": [150, 120, 100], "masa_kg": 2.0,
                 "cada_s": 0.5, "posicion_mm": [-500, 0, 850.5]}],
    "aserciones": ["-M1.rpm >= 1700 dentro_de 1,5 s desde pulsar -S1",
                   "-K1.cuenta >= 1 al_final",
                   "-K1.%QX0.0 == false dentro_de 0,1 s desde presionar -S0",
                   "-M1.par_Nm == 0 dentro_de 0,5 s desde presionar -S0",
                   "-K1.en_marcha nunca desde liberar -S0"],
}


@pytest.fixture(scope="module")
def maquina():
    doc = faja_variador()
    cid = doc.execute("add_program", {"plc": "-K1", "fuente": PROGRAMA})
    return {"doc": doc, "programa": cid}


@pytest.fixture
def c(maquina, monkeypatch):
    monkeypatch.setattr(api, "DOC", maquina["doc"])
    return TestClient(api.app)


def _job(c: TestClient, job_id: str, limite_s: float = 900) -> dict:
    fin = time.monotonic() + limite_s
    while time.monotonic() < fin:
        job = c.get(f"/api/jobs/{job_id}", params={"wait_s": 30}).json()
        if job["estado"] in ("ok", "error"):
            return job
    raise AssertionError(f"el job {job_id} no terminó en {limite_s} s")


def _puerta_escenarios(c: TestClient) -> dict:
    rep = c.post("/api/delivery-check", json={}).json()
    return {"bloqueantes": [b for b in rep["bloqueantes"] if b["regla"].startswith("escenarios")],
            "avisos": [a for a in rep["avisos"] if a["regla"].startswith("escenarios")],
            "ok": [o for o in rep["resumen"]["chequeos_ok"] if o.startswith("escenarios")]}


def test_la_fat_virtual_pasa_como_job_y_queda_guardada(c, maquina):
    assert c.put("/api/escenarios/fat", json={"escenario": FAT}).json()["avisos"] == []
    r = c.post("/api/cosim/run", params={"async": "true"}, json={"escenario": "fat"})
    assert r.status_code == 202
    job = _job(c, r.json()["job_id"])
    assert job["estado"] == "ok", job.get("error")
    res = job["resultado"]
    assert res["veredicto"] == "pasa", [a for a in res["aserciones"] if not a["pasa"]]
    assert [a["pasa"] for a in res["aserciones"]] == [True] * 5
    assert res["guardado"] is True and res["estado"] == "pasa" and res["escenario"] == "fat"
    assert res["aviso"].startswith("simulación a nivel sistema") and "trazas" not in res
    maquina["simulacion"] = res["simulacion"]
    # guardado con su vigencia y la puerta lo cuenta en verde
    [fila] = c.get("/api/escenarios").json()["escenarios"]
    assert fila["estado"] == "pasa" and "fallidas" not in fila
    p = _puerta_escenarios(c)
    assert p == {"bloqueantes": [], "avisos": [], "ok": ["escenarios (1, vigentes)"]}
    # la corrida por partes
    sim = maquina["simulacion"]
    resumen = c.get(f"/api/cosim/simulaciones/{sim}").json()
    assert "-M1.rpm" in resumen["senales"]["analogicas"] and "-K1.Main.cuenta" in resumen["senales"]["discretas"]
    tr = c.get(f"/api/cosim/simulaciones/{sim}", params={
        "parte": "trazas", "senales": "-K1.%QX0.0,-M1.rpm", "desde_s": 2.0, "hasta_s": 2.5, "limite": 10}).json()
    q = tr["discretas"]["-K1.%QX0.0"]["cambios"]
    assert q[0] == [2.0, True] and q[-1][1] is False and 2.2 < q[-1][0] < 2.3
    assert tr["analogicas"]["t"][0] == 2.0 and len(tr["analogicas"]["t"]) == 10 and tr["analogicas"]["truncado"]
    assert sim in [s["id"] for s in c.get("/api/cosim/simulaciones").json()["simulaciones"]]


def test_el_programa_saboteado_sale_rojo(c, maquina):
    if "simulacion" not in maquina:
        pytest.skip("depende de la corrida verde")
    # test_plc: lo corre sin guardarlo; las aserciones de la seta fallan y el escenario no cambia
    r = c.post("/api/cosim/plc/test", json={"fuente": SABOTEADO, "plc": "-K1", "escenario": "fat"})
    assert r.status_code == 200, r.text
    prueba = r.json()
    assert prueba["compila"] and prueba["veredicto"] == "falla" and prueba["escenario"] == "fat"
    fallidas = [a["asercion"] for a in prueba["aserciones"] if not a["pasa"]]
    assert fallidas == ["-K1.%QX0.0 == false dentro_de 0.1 s desde presionar -S0",
                        "-K1.en_marcha == true nunca desde liberar -S0"]
    assert "-K1.%QX0.0" in prueba["trazas"]["discretas"] and "guardado" not in prueba
    assert c.get("/api/escenarios").json()["escenarios"][0]["estado"] == "pasa"
    # al carril: el resultado verde queda vencido (la máquina cambió) → AMARILLO
    r = c.put(f"/api/commands/{maquina['programa']}", params={"merge": "true"}, json={"params": {"fuente": SABOTEADO}})
    assert r.status_code == 200, r.text
    assert c.get("/api/escenarios").json()["escenarios"][0]["estado"] == "vencido"
    assert [a["regla"] for a in _puerta_escenarios(c)["avisos"]] == ["escenarios · fat"]
    # corrido: falla y la puerta da ROJO
    res = c.post("/api/cosim/run", json={"escenario": "fat"}).json()
    assert res["veredicto"] == "falla" and res["n_fallidas"] == 2 and res["guardado"]
    [fila] = c.get("/api/escenarios").json()["escenarios"]
    assert fila["estado"] == "falla" and len(fila["fallidas"]) == 2
    [rojo] = _puerta_escenarios(c)["bloqueantes"]
    assert rojo["regla"] == "escenarios · fat" and "-K1.%QX0.0 == false" in rojo["detalle"]
    assert c.post("/api/delivery-check", json={}).json()["veredicto"] == "ROJO"


def test_test_plc_compila_sin_correr_y_los_errores_dicen_donde(c):
    ok = c.post("/api/cosim/plc/test", json={"fuente": PROGRAMA, "plc": "-K1"}).json()
    assert ok["compila"] and ok["programas"] == ["Main"] and len(ok["tags"]) == 7 and "veredicto" not in ok
    roto = PROGRAMA.replace("cuenta + 1", "cuenta +")
    linea = next(k for k, s in enumerate(roto.split("\n"), 1) if "cuenta +" in s)
    malo = c.post("/api/cosim/plc/test", json={"fuente": roto, "plc": "-K1"}).json()
    assert not malo["compila"] and malo["errores"][0]["linea"] in (linea, linea + 1)
    assert f"línea {malo['errores'][0]['linea']}, columna" in malo["error"]
    sin_plc = c.post("/api/cosim/plc/test", json={"fuente": PROGRAMA}).json()
    assert sin_plc["compila"] and "aviso_bornes" in sin_plc
    r = c.post("/api/cosim/plc/test", json={"fuente": PROGRAMA, "plc": "-K9"})
    assert r.status_code == 400 and "PLC: -K1" in r.json()["detail"]
    r = c.post("/api/cosim/plc/test", json={"fuente": PROGRAMA, "escenario": "fat"})
    assert r.status_code == 400 and "indica `plc`" in r.json()["detail"]


def test_un_escenario_que_no_existe_o_no_se_puede_correr(c):
    r = c.post("/api/cosim/run", json={"escenario": "fta"})
    assert r.status_code == 404 and "No existe el escenario «fta»" in r.json()["detail"]
    r = c.post("/api/cosim/run", json={"escenario": {"duracion_s": 1}})  # sin acoplar el motor
    assert r.status_code == 400 and "no está acoplado a una junta" in r.json()["detail"]
    assert c.get("/api/cosim/simulaciones/s000").status_code == 404
