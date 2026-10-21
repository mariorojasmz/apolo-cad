"""La memoria y el manual como JOB (plan manual-rapido, F2; hallazgo de la ola 5 por MCP).

`calc_report` por MCP sobre la piloto daba «timed out» a los 120 s del httpx y nunca escribía el
PDF. Con `?async=true` el entregable va a su propia cola (`ENTREGABLES_JOBS`), el job devuelve
la ruta del archivo y el MCP lo baja: si tarda más que la espera, el agente recibe el RECIBO y
`get_job` lo guarda en el `path` pedido.
"""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.state import STATE_LOCK


def _mueble() -> Document:
    doc = Document("mueble")
    base = doc.execute("create_box", {"name": "Base madera", "width": 800, "depth": 400,
                                      "height": 20, "position": {"z": 10}})
    tapa = doc.execute("create_box", {"name": "Tapa madera", "width": 800, "depth": 400,
                                      "height": 20, "position": {"z": 500}})
    doc.execute("ground", {"name": "g1", "feature": base})
    doc.execute("fasten", {"name": "u1", "a": base, "b": tapa, "kind": "perno",
                           "size": "M8", "qty": 4})
    return doc


def _esperar(c: TestClient, job_id: str) -> dict:
    for _ in range(10):
        job = c.get(f"/api/jobs/{job_id}", params={"wait_s": 30}).json()
        if job["estado"] in ("ok", "error"):
            return job
    raise AssertionError(f"el job {job_id} no terminó")


def test_la_memoria_por_job_deja_el_mismo_pdf_para_bajar():
    api.DOC = _mueble()
    c = TestClient(api.app)
    r = c.get("/api/calc-report.pdf", params={"async": "true"})
    assert r.status_code == 202, r.text
    job = _esperar(c, r.json()["job_id"])
    assert job["estado"] == "ok" and job["tipo"] == "calc_report"
    res = job["resultado"]
    assert res["tipo"] == "application/pdf" and res["nombre"] == "mueble-memoria-calculo.pdf"
    pdf = c.get(res["archivo"])
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    assert len(pdf.content) == res["bytes"]
    assert 'filename="mueble-memoria-calculo.pdf"' in pdf.headers["content-disposition"]
    assert any(j["id"] == job["id"] for j in c.get("/api/jobs").json()["jobs"])


def test_el_manual_tambien_va_por_job():
    api.DOC = _mueble()
    c = TestClient(api.app)
    r = c.get("/api/assembly-manual.pdf", params={"async": "true", "size_px": 200})
    assert r.status_code == 202
    res = _esperar(c, r.json()["job_id"])["resultado"]
    assert c.get(res["archivo"]).content[:4] == b"%PDF"


def test_un_job_fallido_da_el_mismo_error_que_en_directo():
    api.DOC = Document("vacio")
    c = TestClient(api.app)
    directo = c.get("/api/calc-report.pdf")
    job = _esperar(c, c.get("/api/calc-report.pdf", params={"async": "true"}).json()["job_id"])
    assert directo.status_code == 400
    assert job["estado"] == "error" and job["http_status"] == 400
    assert job["error"] == directo.json()["detail"]


def test_si_cambia_el_proyecto_mientras_espera_no_se_genera():
    api.DOC = _mueble()
    api.PROJECT_ID = 7
    c = TestClient(api.app)
    with STATE_LOCK:   # el job no puede empezar: se encola con el proyecto 7…
        job_id = c.get("/api/calc-report.pdf", params={"async": "true"}).json()["job_id"]
        api.PROJECT_ID = 8   # …y antes de correr se abrió otro
    job = _esperar(c, job_id)
    assert job["estado"] == "error" and job["http_status"] == 409
    assert "era 7, ahora 8" in job["error"]


def test_un_archivo_desconocido_da_404_honesto():
    r = TestClient(api.app).get("/api/archivos/nada")
    assert r.status_code == 404 and "Vuelve a pedir el entregable" in r.json()["detail"]


def test_la_cola_de_entregables_no_retrasa_las_mutaciones(monkeypatch):
    """Una memoria de minutos en su cola: un lote encolado en `JOBS` corre mientras tanto."""
    from apolo.drawing import foto_escena

    api.DOC = _mueble()
    dibujando, seguir = threading.Event(), threading.Event()

    def foto_lenta(ex):
        dibujando.set()
        assert seguir.wait(30)
        return None

    monkeypatch.setattr(foto_escena, "dibujar_foto", foto_lenta)
    c = TestClient(api.app)
    try:
        memoria = c.get("/api/calc-report.pdf", params={"async": "true"}).json()["job_id"]
        assert dibujando.wait(60)
        lote = c.post("/api/commands/batch", params={"async": "true"}, json={"actions": [
            {"type": "create_box", "params": {"name": "Otra", "width": 10, "depth": 10,
                                              "height": 10}}]}).json()["job_id"]
        assert _esperar(c, lote)["estado"] == "ok"
    finally:
        seguir.set()
    assert _esperar(c, memoria)["estado"] == "ok"
