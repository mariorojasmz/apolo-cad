"""El entregable en archivo de una extensión, en directo y como JOB (plan pedidos-de-extensiones,
D6 y D13 del job), con la extensión FALSA (`tests/ext_prueba/rutas.py`, `/api/prueba/informe.txt`).

`fachada.entregable_documento(extraer, componer, tipo=, asincrono=)`: `extraer(doc)` bajo
`STATE_LOCK` (revalida el proyecto si el pedido esperó en cola), `componer(datos)` FUERA de todo
lock; sin `async`, la `Response` con su `Content-Disposition`; con él, 202 + recibo en la cola de
entregables del núcleo y el archivo se baja de `archivo`. Del lado MCP, la tool de la extensión
(`prueba_informe`) lo pide con `pedir_entregable` y `get_job` lo guarda.
"""

from __future__ import annotations

import asyncio
import json
import threading

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.state import STATE_LOCK

EXTRA = "APOLO_EXTENSIONES_EXTRA"
RUTA = "/api/prueba/informe.txt"


@pytest.fixture
def con_prueba(extensiones_aisladas, monkeypatch):
    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION")
    assert extensiones_aisladas.cargar()[0]["cargada"]
    return extensiones_aisladas


@pytest.fixture
def clientes(con_prueba, monkeypatch):
    """(rutas de la extensión, API del núcleo) sobre una «mesa» abierta como proyecto 7. Las rutas
    de la extensión van en una app aparte (la de `main` se armó sin extensiones); los jobs y los
    archivos son del núcleo, en el mismo proceso."""
    app = FastAPI()
    for router in con_prueba.routers():
        app.include_router(router)
    doc = Document("mesa")
    doc.execute("create_box", {"name": "Tablero", "width": 400, "depth": 300, "height": 20})
    doc.execute("create_box", {"name": "Pata", "width": 30, "depth": 30, "height": 700})
    monkeypatch.setattr(api, "DOC", doc)
    monkeypatch.setattr(api, "PROJECT_ID", 7)
    return TestClient(app), TestClient(api.app)


def _esperar(c: TestClient, job_id: str) -> dict:
    for _ in range(10):
        job = c.get(f"/api/jobs/{job_id}", params={"wait_s": 30}).json()
        if job["estado"] in ("ok", "error"):
            return job
    raise AssertionError(f"el job {job_id} no terminó")


INFORME = b"Informe de mesa\nPata\nTablero\n"


def test_esta_en_la_superficie_sin_subir_el_contrato():
    from apolo import extensiones, extensiones_api
    from apolo.api import fachada

    assert extensiones_api.entregable_documento is fachada.entregable_documento
    assert extensiones.CONTRATO_EXTENSIONES == 1


def test_en_directo_da_el_archivo_con_su_nombre(clientes):
    ext, _ = clientes
    r = ext.get(RUTA)
    assert r.status_code == 200 and r.content == INFORME
    assert r.headers["content-type"].startswith("text/plain")
    assert r.headers["content-disposition"] == 'attachment; filename="mesa-informe.txt"'


def test_como_job_da_recibo_y_el_archivo_se_baja(clientes):
    ext, nucleo = clientes
    r = ext.get(RUTA, params={"async": "true"})
    assert r.status_code == 202 and r.json()["estado"] == "encolado"
    job = _esperar(nucleo, r.json()["job_id"])
    assert job["estado"] == "ok" and job["tipo"] == "prueba.informe"
    res = job["resultado"]
    assert set(res) == {"archivo", "bytes", "tipo", "nombre"}
    assert res["nombre"] == "mesa-informe.txt" and res["bytes"] == len(INFORME)
    assert res["tipo"].startswith("text/plain")
    archivo = nucleo.get(res["archivo"])
    assert archivo.status_code == 200 and archivo.content == INFORME
    assert 'filename="mesa-informe.txt"' in archivo.headers["content-disposition"]


def test_si_se_abre_otro_proyecto_mientras_espera_no_se_genera(clientes, monkeypatch):
    import ext_prueba.rutas as rutas

    ext, nucleo = clientes
    llamadas = []
    monkeypatch.setattr(rutas, "_extraer", lambda doc: llamadas.append("extraer"))
    monkeypatch.setattr(rutas, "_componer", lambda datos: llamadas.append("componer"))
    with STATE_LOCK:  # el job no puede empezar: se encola con el proyecto 7…
        job_id = ext.get(RUTA, params={"async": "true"}).json()["job_id"]
        api.PROJECT_ID = 8  # …y antes de correr se abrió otro
    job = _esperar(nucleo, job_id)
    assert job["estado"] == "error" and job["http_status"] == 409
    assert "era 7, ahora 8" in job["error"] and "no se generó" in job["error"]
    assert llamadas == []


class _Vigia:
    """`STATE_LOCK` de la fachada, contado: cuántas veces está tomado AHORA por ella."""

    def __init__(self):
        self.dentro = 0

    def __enter__(self):
        STATE_LOCK.acquire()
        self.dentro += 1
        return self

    def __exit__(self, *exc):
        self.dentro -= 1
        STATE_LOCK.release()


def _libre_desde_otro_hilo() -> bool:
    """`STATE_LOCK` libre de VERDAD: otro hilo lo toma sin esperar (un RLock del hilo que compone
    no lo dejaría)."""
    out = []

    def probar():
        ok = STATE_LOCK.acquire(blocking=False)
        out.append(ok)
        if ok:
            STATE_LOCK.release()

    hilo = threading.Thread(target=probar)
    hilo.start()
    hilo.join(10)
    return out == [True]


@pytest.mark.parametrize("asincrono", [False, True])
def test_componer_corre_con_el_lock_libre_y_extraer_bajo_el_lock(clientes, monkeypatch, asincrono):
    import ext_prueba.rutas as rutas
    from apolo.api import fachada

    ext, nucleo = clientes
    vigia = _Vigia()
    monkeypatch.setattr(fachada, "STATE_LOCK", vigia)
    vistos = {}
    extraer, componer = rutas._extraer, rutas._componer

    def extraer_vigilado(doc):
        vistos["extraer"] = (vigia.dentro, _libre_desde_otro_hilo())
        return extraer(doc)

    def componer_vigilado(datos):
        if vigia.dentro or not _libre_desde_otro_hilo():
            raise AssertionError("componer corrió con STATE_LOCK tomado")
        vistos["componer"] = True
        return componer(datos)

    monkeypatch.setattr(rutas, "_extraer", extraer_vigilado)
    monkeypatch.setattr(rutas, "_componer", componer_vigilado)
    if asincrono:
        job = _esperar(nucleo, ext.get(RUTA, params={"async": "true"}).json()["job_id"])
        assert job["estado"] == "ok", job
        assert nucleo.get(job["resultado"]["archivo"]).content == INFORME
    else:
        assert ext.get(RUTA).content == INFORME
    assert vistos == {"extraer": (1, False), "componer": True}


def test_un_error_de_dominio_es_400_en_directo_y_en_el_job(clientes):
    ext, nucleo = clientes
    api.DOC = Document("vacia")
    directo = ext.get(RUTA)
    assert directo.status_code == 400
    assert directo.json()["detail"] == "No hay piezas que informar: el modelo está vacío."
    job = _esperar(nucleo, ext.get(RUTA, params={"async": "true"}).json()["job_id"])
    assert job["estado"] == "error" and job["http_status"] == 400
    assert job["error"] == directo.json()["detail"]


def test_un_error_de_dominio_al_componer_tambien_es_400(clientes, monkeypatch):
    import ext_prueba.rutas as rutas
    from apolo.extensiones_api import CommandError

    def componer(datos):
        raise CommandError("La plantilla del informe no admite tantas piezas.")

    monkeypatch.setattr(rutas, "_componer", componer)
    r = clientes[0].get(RUTA)
    assert r.status_code == 400 and r.json()["detail"].startswith("La plantilla")


def test_una_http_exception_de_la_extension_pasa_tal_cual(clientes, monkeypatch):
    import ext_prueba.rutas as rutas

    def componer(datos):
        raise HTTPException(status_code=422, detail="falta el logo del cliente")

    monkeypatch.setattr(rutas, "_componer", componer)
    ext, nucleo = clientes
    r = ext.get(RUTA)
    assert r.status_code == 422 and r.json()["detail"] == "falta el logo del cliente"
    job = _esperar(nucleo, ext.get(RUTA, params={"async": "true"}).json()["job_id"])
    assert job["http_status"] == 422 and job["error"] == "falta el logo del cliente"


def test_un_nombre_que_no_cabe_en_la_cabecera_no_se_recorta_en_silencio():
    from apolo.api import fachada

    for malo in ("", 'con"comilla.txt', "salto\n.txt", "€uro.txt", None):
        with pytest.raises(ValueError, match="nombre de archivo inválido"):
            fachada._nombre(malo)
    assert fachada._nombre("Puerta añil-memoria.pdf") == "Puerta añil-memoria.pdf"


# ── la tool de la extensión: pedir_entregable + get_job ──────────────────────────────────────

@pytest.fixture
def mcp_server():
    """El servidor MCP del núcleo, importado ANTES de cargar la extensión: al importarse registra
    en SU `mcp` las tools de las extensiones cargadas, y las dejaría ahí para el resto del
    proceso (el golden y el conteo del núcleo las verían)."""
    pytest.importorskip("mcp")
    import apolo.mcp_server as mod

    return mod


@pytest.fixture
def mcp_con_tool(mcp_server, clientes, con_prueba, monkeypatch):
    """Una tool de la extensión registrada como lo hace el MCP (con sus `globals()`), y su
    `_api` contra los dos clientes de prueba (la ruta de la extensión y los jobs y archivos del
    núcleo)."""
    from apolo.tools.fastmcp_limpio import FastMCPLimpio

    ext, nucleo = clientes

    def api_de_prueba(metodo, ruta, **kw):
        cliente = ext if ruta.startswith("/api/prueba/") else nucleo
        r = cliente.request(metodo, ruta, params=kw.get("params"), json=kw.get("json"))
        if r.status_code >= 400:
            raise mcp_server._reject(r.status_code, r.json().get("detail", r.text))
        return r

    monkeypatch.setattr(mcp_server, "_api", api_de_prueba)
    mcp = FastMCPLimpio("prueba")
    assert "prueba_informe" in con_prueba.registrar_tools(mcp, vars(mcp_server))
    return mcp, mcp_server


def _texto(out) -> str:
    bloques = out[0] if isinstance(out, tuple) else out
    return bloques[0].text


def test_la_tool_guarda_el_archivo_cuando_el_job_termina_a_tiempo(mcp_con_tool, tmp_path):
    mcp, _ = mcp_con_tool
    destino = tmp_path / "informe.txt"
    out = json.loads(_texto(asyncio.run(mcp.call_tool("prueba_informe", {"path": str(destino)}))))
    assert out == {"ok": True, "path": str(destino), "bytes": len(INFORME)}
    assert destino.read_bytes() == INFORME


def test_si_tarda_la_tool_da_recibo_y_get_job_guarda_el_archivo(mcp_con_tool, tmp_path,
                                                                 monkeypatch):
    mcp, mcp_server = mcp_con_tool
    monkeypatch.setattr(mcp_server, "APOLO_MCP_WAIT_S", 0.0)  # recibo sin esperar
    destino = tmp_path / "sub" / "informe.txt"
    destino.parent.mkdir()
    recibo = json.loads(_texto(asyncio.run(mcp.call_tool("prueba_informe",
                                                         {"path": str(destino)}))))
    assert set(recibo) == {"job", "estado", "seguir"} and str(destino) in recibo["seguir"]
    assert not destino.exists()
    out = json.loads(mcp_server.get_job(recibo["job"], wait_s=30))
    assert out == {"ok": True, "path": str(destino), "bytes": len(INFORME), "job": recibo["job"]}
    assert destino.read_bytes() == INFORME
