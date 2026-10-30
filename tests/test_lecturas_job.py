"""Las lecturas largas de validación (F3 del plan maquinas-grandes, D4 y D5).

D4: `/api/checks` corre sólo las `partes` pedidas; sin el campo, la respuesta es la de siempre
(byte a byte: la misma que pidiendo todas). D5: `/api/checks` y `/api/delivery-check` con
`?async=true` van como job a `COSIM_JOBS` y una lectura IDÉNTICA en curso (misma ruta, cuerpo,
proyecto, documento y firma del modelo) devuelve el job que ya corre en vez de encolar otro.
"""

from __future__ import annotations

import json
import threading

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.api.jobs import JobStore
from apolo.api.routers import chequeos
from apolo.doc import Document
from apolo.state import STATE_LOCK
from apolo.tools import validacion


def _mueble() -> Document:
    doc = Document("mueble")
    base = doc.execute("create_box", {"name": "Base", "width": 800, "depth": 400,
                                      "height": 20, "position": {"z": 10}})
    tapa = doc.execute("create_box", {"name": "Tapa", "width": 800, "depth": 400,
                                      "height": 20, "position": {"z": 500}})
    doc.execute("create_box", {"name": "Choque", "width": 100, "depth": 100,
                               "height": 100, "position": {"z": 500}})
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "u1", "a": base, "b": tapa, "kind": "perno",
                           "size": "M8", "qty": 4})
    return doc


CARGA = {"carga_kg": 15, "largo_paquete_mm": 300, "velocidad_m_s": 0.5}


def _esperar(c: TestClient, job_id: str) -> dict:
    for _ in range(10):
        job = c.get(f"/api/jobs/{job_id}", params={"wait_s": 30}).json()
        if job["estado"] in ("ok", "error"):
            return job
    raise AssertionError(f"el job {job_id} no terminó")


# ------------------------------------------------------------------------ D4: partes


@pytest.mark.parametrize("extra", [{}, CARGA, {**CARGA, "resumen": True},
                                   {"grupo": "unión apernada", "solo_fallas": True}])
def test_sin_partes_es_byte_identico_a_pedirlas_todas(extra):
    api.DOC = _mueble()
    c = TestClient(api.app)
    sin = c.post("/api/checks", json=extra)
    todas = c.post("/api/checks", json={**extra, "partes": list(chequeos.PARTES)})
    assert sin.status_code == todas.status_code == 200
    assert sin.content == todas.content
    claves = list(sin.json())
    assert claves[:3] == ["interferencias", "ingenieria", "estructura"]
    assert claves[3:] == (["conteo"] if extra.get("resumen") else [])


def test_sin_carga_la_ingenieria_sigue_saliendo_null_si_se_pide():
    api.DOC = _mueble()
    out = TestClient(api.app).post("/api/checks", json={"partes": ["ingenieria"]}).json()
    assert out == {"ingenieria": None}


def test_la_interferencia_sola_no_corre_reglas_ni_lints(monkeypatch):
    api.DOC = _mueble()
    c = TestClient(api.app)
    completo = c.post("/api/checks", json={}).json()

    def prohibido(*a, **k):
        raise AssertionError("no se pidió")

    monkeypatch.setattr(chequeos, "structure_rules", prohibido)
    monkeypatch.setattr(chequeos, "_lints", prohibido)
    monkeypatch.setattr(chequeos, "requirement_inputs", prohibido)
    out = c.post("/api/checks", json={"partes": ["interferencias"]}).json()
    assert list(out) == ["interferencias"]
    assert out["interferencias"] == completo["interferencias"]
    assert out["interferencias"]["interferencias"], "el mueble tiene un choque a propósito"


def test_la_ingenieria_no_corre_la_interferencia(monkeypatch):
    api.DOC = _mueble()
    c = TestClient(api.app)
    completo = c.post("/api/checks", json={**CARGA, "resumen": True}).json()
    monkeypatch.setattr(chequeos, "interference_report",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no se pidió")))
    out = c.post("/api/checks", json={**CARGA, "resumen": True,
                                      "partes": validacion.PARTES_INGENIERIA}).json()
    assert list(out) == ["ingenieria", "estructura", "conteo"]
    assert out == {k: completo[k] for k in ("ingenieria", "estructura", "conteo")}


def test_estructura_y_lints_por_separado_suman_la_estructura_de_siempre():
    api.DOC = _mueble()
    c = TestClient(api.app)
    completo = c.post("/api/checks", json=CARGA).json()["estructura"]
    sola = c.post("/api/checks", json={**CARGA, "partes": ["estructura"]}).json()["estructura"]
    lints = c.post("/api/checks", json={**CARGA, "partes": ["lints"]}).json()
    assert list(lints) == ["estructura"]
    assert sola + lints["estructura"] == completo


@pytest.mark.parametrize("partes", [["interferencia"], [], ["lints", "nada"]])
def test_partes_invalidas_dan_400_con_las_validas(partes):
    api.DOC = _mueble()
    r = TestClient(api.app).post("/api/checks", json={"partes": partes})
    assert r.status_code == 400
    assert "interferencias, ingenieria, estructura, lints" in r.json()["detail"]


# ------------------------------------------------------------------------ D5: job


def test_checks_por_job_dan_lo_mismo_que_en_directo():
    api.DOC = _mueble()
    c = TestClient(api.app)
    cuerpo = {"partes": ["interferencias"], "interference_ids": ["c3"]}
    directo = c.post("/api/checks", json=cuerpo).json()
    r = c.post("/api/checks", params={"async": "true"}, json=cuerpo)
    assert r.status_code == 202 and r.json()["estado"] == "encolado"
    job = _esperar(c, r.json()["job_id"])
    assert job["estado"] == "ok" and job["tipo"] == "checks:interferencias"
    assert job["resultado"] == directo
    assert validacion.de_job(job) == directo["interferencias"]


def test_sin_partes_el_job_es_de_tipo_checks():
    api.DOC = _mueble()
    c = TestClient(api.app)
    job = _esperar(c, c.post("/api/checks", params={"async": "true"}, json={}).json()["job_id"])
    assert job["tipo"] == "checks" and validacion.de_job(job) is None
    assert list(job["resultado"]) == ["interferencias", "ingenieria", "estructura"]


def test_la_puerta_de_entrega_por_job_da_el_mismo_semaforo():
    api.DOC = _mueble()
    c = TestClient(api.app)
    directo = c.post("/api/delivery-check", json={}).json()
    job = _esperar(c, c.post("/api/delivery-check", params={"async": "true"},
                             json={}).json()["job_id"])
    assert job["estado"] == "ok" and job["tipo"] == "delivery_check"
    directo.pop("tiempos_s")
    res = dict(job["resultado"])
    assert set(res.pop("tiempos_s")) == {"total", "por_regla"}
    assert res == directo
    assert validacion.de_job(job) == job["resultado"]


def test_si_cambia_el_proyecto_mientras_espera_la_lectura_da_409():
    api.DOC = _mueble()
    api.PROJECT_ID = 7
    c = TestClient(api.app)
    with STATE_LOCK:  # el job no puede empezar; el 202 llega igual (la clave no espera el lock)
        r = c.post("/api/delivery-check", params={"async": "true"}, json={})
        assert r.status_code == 202
        api.PROJECT_ID = 8
    job = _esperar(c, r.json()["job_id"])
    assert job["estado"] == "error" and job["http_status"] == 409


@pytest.fixture
def lectura_trabada(monkeypatch):
    """`_checks` y `_delivery` esperan un Event: el job queda CORRIENDO hasta soltarlo."""
    soltar = threading.Event()
    corriendo = threading.Event()
    reales = (chequeos._checks, chequeos._delivery)

    def trabar(real):
        def envuelta(*a, **k):
            corriendo.set()
            assert soltar.wait(60), "nadie soltó la lectura"
            return real(*a, **k)
        return envuelta

    monkeypatch.setattr(chequeos, "_checks", trabar(reales[0]))
    monkeypatch.setattr(chequeos, "_delivery", trabar(reales[1]))
    yield soltar, corriendo
    soltar.set()


def test_una_lectura_identica_en_curso_devuelve_el_mismo_job(lectura_trabada):
    soltar, corriendo = lectura_trabada
    api.DOC = _mueble()
    c = TestClient(api.app)
    try:
        a = c.post("/api/delivery-check", params={"async": "true"}, json={}).json()
        assert corriendo.wait(30)
        b = c.post("/api/delivery-check", params={"async": "true"}, json={}).json()
        assert b == {"job_id": a["job_id"], "estado": "corriendo", "repetida": True}
        # con STATE_LOCK tomado por otro hilo (una lectura que lo sostiene) también deduplica
        with STATE_LOCK:
            assert c.post("/api/delivery-check", params={"async": "true"},
                          json={}).json()["job_id"] == a["job_id"]
        otro_cuerpo = c.post("/api/delivery-check", params={"async": "true"},
                             json={"con_gravedad": True}).json()
        otra_ruta = c.post("/api/checks", params={"async": "true"}, json={}).json()
        assert len({a["job_id"], otro_cuerpo["job_id"], otra_ruta["job_id"]}) == 3
        assert "repetida" not in otro_cuerpo and "repetida" not in otra_ruta
        api.DOC.execute("set_variable", {"name": "L", "expression": "100"})  # otra firma → otro job
        otra_firma = c.post("/api/delivery-check", params={"async": "true"}, json={}).json()
        assert otra_firma["job_id"] != a["job_id"]
    finally:
        soltar.set()
    for jid in (a["job_id"], otra_firma["job_id"], otra_ruta["job_id"]):
        assert _esperar(c, jid)["estado"] == "ok"
    assert _esperar(c, otro_cuerpo["job_id"])["estado"] in ("ok", "error")  # sin MuJoCo: error
    # terminado, la misma lectura vuelve a calcular (no es una caché)
    nuevo = c.post("/api/checks", params={"async": "true"}, json={}).json()
    assert nuevo["job_id"] != otra_ruta["job_id"] and _esperar(c, nuevo["job_id"])


def test_otro_proyecto_con_el_mismo_modelo_no_se_une(lectura_trabada):
    soltar, corriendo = lectura_trabada
    api.DOC = _mueble()
    api.PROJECT_ID = 7
    c = TestClient(api.app)
    try:
        a = c.post("/api/checks", params={"async": "true"}, json={}).json()
        assert corriendo.wait(30)
        api.PROJECT_ID = 8
        b = c.post("/api/checks", params={"async": "true"}, json={}).json()
        assert b["job_id"] != a["job_id"]
    finally:
        soltar.set()
    assert _esperar(c, a["job_id"])["http_status"] == 409
    assert _esperar(c, b["job_id"])["estado"] == "ok"


# ------------------------------------------------------------------------ JobStore


def test_submit_unico_une_lo_en_curso_y_suelta_al_terminar():
    store = JobStore()
    soltar = threading.Event()
    a, nuevo_a = store.submit_unico("t", lambda: soltar.wait(30) and {"n": 1}, "k")
    b, nuevo_b = store.submit_unico("t", lambda: {"n": 2}, "k")
    c, nuevo_c = store.submit_unico("t", lambda: {"n": 3}, "otra")
    assert (nuevo_a, nuevo_b, nuevo_c) == (True, False, True) and a == b != c
    soltar.set()
    assert store.get(a, wait_s=10)["resultado"] == {"n": 1}
    assert store.get(c, wait_s=10)["resultado"] == {"n": 3}
    d, nuevo_d = store.submit_unico("t", lambda: {"n": 4}, "k")
    assert nuevo_d and d != a and store.get(d, wait_s=10)["resultado"] == {"n": 4}
    assert store._por_clave == {} and store._clave_de == {}


def test_un_job_fallido_tambien_suelta_su_clave():
    store = JobStore()
    a, _ = store.submit_unico("t", lambda: 1 / 0, "k")
    assert store.get(a, wait_s=10)["estado"] == "error"
    b, nuevo = store.submit_unico("t", lambda: {}, "k")
    assert nuevo and b != a


def test_de_job_reconoce_cada_lectura_por_su_tipo():
    res = {"interferencias": {"n": 1}, "ingenieria": [1], "estructura": [2], "conteo": {}}
    assert validacion.de_job({"tipo": "checks:interferencias", "resultado": res}) == {"n": 1}
    assert validacion.de_job({"tipo": "checks:ingenieria,estructura,lints", "resultado": res}) == {
        "ingenieria": [1], "estructura": [2], "conteo": {}}
    assert validacion.de_job({"tipo": "delivery_check", "resultado": {"veredicto": "VERDE"}}) == {
        "veredicto": "VERDE"}
    assert validacion.de_job({"tipo": "edit_batch", "resultado": res}) is None
    assert json.dumps(validacion.de_ingenieria({"ingenieria": None, "estructura": []})) == \
        '{"ingenieria": null, "estructura": []}'
