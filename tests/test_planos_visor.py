"""«Planos» sin congelar Apolo (plan visor-para-evaluar D6–D12):

  - la lámina por la caché (HLR sobre COPIAS en BinTools, en procesos aparte y fuera de
    `STATE_LOCK`) sale byte a byte igual que la directa, con y sin ocultas, BOM y corte, también
    con las formas ya teseladas;
  - una pasada da visibles y ocultas: «líneas ocultas» y «BOM» no piden otra; el corte sí, una vez;
  - `GET /api/drawing/lamina`: la primera vez es un job (origen visor, con progreso); después, o al
    cambiar una casilla, `lista` al instante; el SVG es el mismo de `GET /api/drawing.svg`;
  - mientras el HLR corre, `STATE_LOCK` está libre (una mutación no espera);
  - el juego de planos lee su conjunto de la caché y avisa su avance; el DWG va por job.
"""

from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.api import planos
from apolo.api.jobs import JobStore, avance
from apolo.doc import Document
from apolo.drawing import compose_sheet, hlr_cache, sheet_to_svg
from apolo.state import STATE_LOCK


def _doc() -> Document:
    doc = Document("planos")
    doc.execute("create_box", {"name": "Base", "width": 800, "depth": 400, "height": 30})
    doc.execute("create_cylinder", {"name": "Eje", "radius": 20, "height": 300,
                                    "position": {"x": 100, "y": 0, "z": 30}})
    doc.execute("create_box", {"name": "Tapa", "width": 300, "depth": 200, "height": 20,
                               "position": {"x": -200, "y": 0, "z": 200}})
    return doc


@pytest.fixture(autouse=True)
def _limpio():
    hlr_cache.vaciar()
    planos.LAMINAS.vaciar()
    yield
    hlr_cache.vaciar()
    planos.LAMINAS.vaciar()


@pytest.mark.parametrize("opts", [{}, {"include_hidden": True}, {"bom": True}, {"section": True},
                                  {"section": True, "include_hidden": True, "bom": True}])
def test_la_lamina_por_la_cache_es_la_misma_que_la_directa(opts):
    doc = _doc()
    for f in doc.scene.values():  # el visor ya las teseló: la copia no lleva malla
        f.shape.tessellate(0.5)
    directa = sheet_to_svg(compose_sheet(doc.scene, project_name="p", **opts))
    p = hlr_cache.pedido(doc.scene, hlr_cache.VISTAS_BASE, ("x", None) if opts.get("section") else None)
    assert p.pasos == 4 + (1 if opts.get("section") else 0)
    p.copiar()  # bytes BinTools: la copia que viaja a los procesos del HLR
    assert [fid for fid, _ in p.copias] == list(p.formas_de) and all(isinstance(b, bytes) for _, b in p.copias)
    avances = []
    p.calcular(lambda h, t, q: avances.append((h, t)))
    assert avances[0] == (0, p.pasos) and avances[-1] == (p.pasos, p.pasos)
    assert hlr_cache.pedido(doc.scene, hlr_cache.VISTAS_BASE).falta is False
    assert sheet_to_svg(compose_sheet(doc.scene, project_name="p", **opts)) == directa


def test_una_pasada_da_las_ocultas_y_el_corte_es_otra(monkeypatch):
    doc = _doc()
    llamadas = []
    original = hlr_cache.Pedido.calcular
    monkeypatch.setattr(hlr_cache.Pedido, "calcular", lambda self, av=None: (llamadas.append(self.pasos), original(self, av))[1])
    api.DOC = doc
    for o in (planos.Opciones(), planos.Opciones(hidden=True), planos.Opciones(bom=True),
              planos.Opciones(hidden=True, bom=True), planos.Opciones()):
        planos.lamina(o)
    assert llamadas == [4]  # una sola pasada de las cuatro vistas
    planos.lamina(planos.Opciones(section=True))
    planos.lamina(planos.Opciones(section=True, hidden=True))
    assert llamadas == [4, 1]  # el corte, una vez


def test_el_hlr_no_toma_state_lock(monkeypatch):
    """Mientras el HLR calcula, otro hilo toma STATE_LOCK sin esperar (una mutación pasa)."""
    doc = _doc()
    api.DOC = doc
    adentro, seguir = threading.Event(), threading.Event()
    original = hlr_cache.Pedido.calcular

    def lento(self, av=None):
        adentro.set()
        assert seguir.wait(30)
        return original(self, av)

    monkeypatch.setattr(hlr_cache.Pedido, "calcular", lento)
    hecho: list = []
    fallo: list = []

    def componer():
        try:
            hecho.append(planos._lamina(planos.Opciones()))
        except BaseException as exc:  # noqa: BLE001 — el test lo muestra
            fallo.append(exc)

    hilo = threading.Thread(target=componer)
    hilo.start()
    assert adentro.wait(30)
    t0 = time.perf_counter()
    with STATE_LOCK:  # el HLR está en curso y el lock está libre
        doc.execute("create_box", {"name": "Mientras", "width": 10, "depth": 10, "height": 10,
                                   "position": {"x": 0, "y": 0, "z": 500}})
    assert time.perf_counter() - t0 < 5
    seguir.set()
    # la vuelta con lo nuevo es otra pasada HLR: con `-n auto` los otros workers la estiran
    # (reloj de pared sólo como red gruesa, CLAUDE.md raíz)
    hilo.join(600)
    assert not hilo.is_alive() and not fallo, fallo
    # el documento cambió durante el HLR: la lámina se compuso con lo nuevo (otra vuelta)
    with STATE_LOCK:
        assert hecho and hecho[0][0] == planos._firma(planos.Opciones(), planos._drawing_meta())


def _esperar(c: TestClient, job: str) -> dict:
    for _ in range(120):
        j = c.get(f"/api/jobs/{job}?wait_s=5").json()
        if j["estado"] in ("ok", "error"):
            return j
    raise AssertionError("el job no terminó")


def test_el_visor_pide_la_lamina_como_job_y_despues_lista():
    api.DOC = _doc()
    c = TestClient(api.app)
    q = "sheet=A3&hidden=false&section=false&bom=false"
    r = c.get(f"/api/drawing/lamina?{q}").json()
    assert r["lista"] is False and r["pasos"] == 4 and "previa" not in r
    job = _esperar(c, r["job_id"])
    assert job["estado"] == "ok" and job["origen"] == "visor"
    svg = c.get(job["resultado"]["svg"])
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg")
    assert svg.content == c.get(f"/api/drawing.svg?{q}").content  # la misma lámina de siempre
    otra = c.get(f"/api/drawing/lamina?{q}").json()
    assert otra == {"lista": True, "svg": job["resultado"]["svg"]}
    ocultas = c.get("/api/drawing/lamina?sheet=A3&hidden=true&section=false&bom=false").json()
    assert ocultas["lista"] is True  # una casilla: sin otra pasada
    corte = c.get("/api/drawing/lamina?sheet=A3&hidden=false&section=true&bom=false").json()
    assert corte["lista"] is False and corte["pasos"] == 1
    assert corte["previa"].startswith("/api/drawing/lamina.svg?k=")  # mientras, la anterior
    assert _esperar(c, corte["job_id"])["estado"] == "ok"
    assert c.get("/api/drawing/lamina.svg?k=nada").status_code == 404


def test_una_lamina_sin_solidos_da_el_400_de_siempre():
    api.DOC = Document("vacio")
    c = TestClient(api.app)
    assert c.get("/api/drawing.svg").status_code == 400


def test_el_job_del_visor_avisa_con_su_origen_y_su_progreso():
    avisos: list[dict] = []
    store = JobStore(al_cambiar_estado=avisos.append)
    puede = threading.Event()

    def trabajo():
        avance({"hechas": 1, "total": 4, "fase": "planta"})
        assert puede.wait(10)
        return {"ok": 1}

    jid = store.submit("lamina_visor", trabajo, origen="visor")
    for _ in range(100):
        if (store.get(jid) or {}).get("progreso"):
            break
        time.sleep(0.02)
    assert store.get(jid)["progreso"] == {"hechas": 1, "total": 4, "fase": "planta"}
    puede.set()
    assert store.get(jid, wait_s=10)["estado"] == "ok"
    assert {"job_id": jid, "estado": "corriendo", "origen": "visor"} in avisos
    # sin origen, el aviso de siempre
    otro = store.submit("lote", lambda: {})
    store.get(otro, wait_s=10)
    assert {"job_id": otro, "estado": "ok"} in avisos
    avance({"hechas": 0, "total": 1, "fase": "x"})  # fuera de un job no hace nada


def test_el_juego_de_planos_lee_el_conjunto_de_la_cache_y_avisa(monkeypatch):
    api.DOC = _doc()
    c = TestClient(api.app)
    pasos = []
    original = hlr_cache.Pedido.calcular
    monkeypatch.setattr(hlr_cache.Pedido, "calcular", lambda self, av=None: (pasos.append(list(self.faltan)), original(self, av))[1])
    vistos = []
    monkeypatch.setattr(planos, "avance", lambda p: vistos.append(p))
    r = c.get("/api/drawingset.pdf?async=true&origen=visor").json()
    job = _esperar(c, r["job_id"])
    assert job["estado"] == "ok" and job["origen"] == "visor"
    assert pasos == [["alzado", "planta", "iso"]]  # el conjunto, fuera del lock
    assert any(v["fase"] == "laminas" for v in vistos)
    assert c.get(job["resultado"]["archivo"]).content.startswith(b"%PDF")


def test_el_dwg_va_por_job_y_sin_oda_se_niega_antes(monkeypatch):
    from apolo.drawing import DwgError, dwg

    api.DOC = _doc()
    c = TestClient(api.app)

    def sin_oda():
        raise DwgError("Falta el conversor de DWG")

    monkeypatch.setattr(dwg, "require_odafc", sin_oda)
    r = c.get("/api/drawingset.dwg?async=true")
    assert r.status_code == 400 and "conversor" in r.json()["detail"]
    monkeypatch.setattr(dwg, "require_odafc", lambda: None)
    import apolo.drawing as drawing

    monkeypatch.setattr(drawing, "sheet_to_dwg", lambda page: b"DWG")
    r = c.get("/api/drawingset.dwg?async=true&origen=visor")
    assert r.status_code == 202
    job = _esperar(c, r.json()["job_id"])
    assert job["estado"] == "ok" and job["resultado"]["tipo"] == "application/zip"


def test_sin_worker_el_hlr_sale_en_el_proceso_y_lo_avisa(monkeypatch, caplog):
    """Si el proceso del HLR no arranca, la misma tarea se resuelve aquí (la lámina no desaparece)."""
    from apolo.drawing import hlr_proceso

    def no_arranca(*a, **k):
        raise OSError("sin procesos")

    doc = _doc()
    directa = sheet_to_svg(compose_sheet(doc.scene, project_name="p"))
    monkeypatch.setattr(hlr_proceso.subprocess, "Popen", no_arranca)
    p = hlr_cache.pedido(doc.scene)
    p.copiar()
    with caplog.at_level("WARNING"):
        p.calcular()
    assert "no arrancó" in caplog.text
    assert sheet_to_svg(compose_sheet(doc.scene, project_name="p")) == directa


def test_el_juego_en_dxf_es_un_zip_con_un_dxf_por_lamina_sin_oda():
    import io
    import zipfile

    api.DOC = _doc()
    c = TestClient(api.app)
    r = c.get("/api/drawingset.dxf?async=true&origen=visor")
    assert r.status_code == 202
    job = _esperar(c, r.json()["job_id"])
    assert job["estado"] == "ok" and job["resultado"]["tipo"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(c.get(job["resultado"]["archivo"]).content))
    nombres = zf.namelist()
    assert nombres and all(n.endswith(".dxf") for n in nombres)
    assert b"SECTION" in zf.read(nombres[0])  # un DXF de verdad
    directo = c.get("/api/drawingset.dxf")  # sin ?async, la respuesta de siempre
    assert directo.status_code == 200 and directo.headers["content-type"] == "application/zip"
