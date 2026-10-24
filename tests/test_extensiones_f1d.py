"""Los puntos que sumó la F1d del plan nucleo-abierto-extensiones-privadas, con la extensión FALSA
de `tests/ext_prueba/` (que los usa todos):

- la FACHADA del documento (`extensiones_api.mutar_documento`, `leer_documento`, `leer_ext`,
  `poner_ext`): una ruta de la extensión muta con undo, autosave, guardia del documento, sólo
  lectura y job, lee bajo el lock y guarda sus datos en la clave `ext` del manifest, sin importar
  `apolo.state` ni `apolo.api`;
- los ítems de la PUERTA de publicación de una extensión (`Extension.puerta`): entran al registro
  vigente, a la ruta de la puerta y a `version_registro`; lo que no cumple no carga;
- el motor de LÁMINAS en `extensiones_api.MODULOS`: una extensión compone y exporta una lámina.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.api.guardia_documento import CABECERA, CabeceraDocumento
from apolo.doc import Document
from apolo.projects import ProjectStore

EXTRA = "APOLO_EXTENSIONES_EXTRA"


@pytest.fixture
def con_prueba(extensiones_aisladas, monkeypatch):
    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION")
    assert extensiones_aisladas.cargar()[0]["cargada"]
    return extensiones_aisladas


@pytest.fixture
def clientes(con_prueba, monkeypatch, tmp_path):
    """(cliente de las rutas de la extensión, cliente de la API del núcleo, almacén, id): un
    proyecto vacío abierto por la API sobre un almacén temporal. Las rutas de la extensión van en
    una app aparte con el middleware de la guardia (la de `main` se armó sin extensiones)."""
    app = FastAPI()
    app.add_middleware(CabeceraDocumento)
    for router in con_prueba.routers():
        app.include_router(router)
    store = ProjectStore(tmp_path / "f1d.db")
    pid = store.create(Document("f1d"))
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(api, "PROJECT_ID", None)
    monkeypatch.setattr(api, "DOC", Document("antes"))
    nucleo = TestClient(api.app)
    assert nucleo.post(f"/api/projects/{pid}/open").status_code == 200
    return TestClient(app), nucleo, store, pid


def _manifest(data: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return json.loads(z.read("manifest.json"))


def _tipos(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return [c["type"] for c in json.loads(z.read("commands.json"))]


# ── la fachada del documento ─────────────────────────────────────────────────────────────────

def test_mutar_deja_undo_y_autosave_y_la_respuesta_de_siempre(clientes):
    ext, nucleo, store, pid = clientes
    r = ext.post("/api/prueba/caja", params={"lado": 30})
    assert r.status_code == 200, r.text
    assert r.json() == {"piezas": 1, "affected_command_ids": ["c1"]}  # `armar` + los afectados
    assert [f.name for f in api.DOC.scene.values()] == ["Hola"]
    assert ext.get("/api/prueba/piezas").json() == {"piezas": ["Hola"]}
    api._flush_autosave(force=True)
    assert _tipos(store.load_bytes(pid)) == ["prueba.hola"]
    assert nucleo.post("/api/undo").status_code == 200  # el undo de la fachada es el de siempre
    assert api.DOC.scene == {} and api.DOC.commands == []


def test_mutar_como_job_da_recibo_y_aplica(clientes):
    ext, nucleo, _store, _pid = clientes
    r = ext.post("/api/prueba/caja", params={"lado": 10, "async": "true"})
    assert r.status_code == 202, r.text
    job = nucleo.get(f"/api/jobs/{r.json()['job_id']}", params={"wait_s": 30}).json()
    assert job["estado"] == "ok", job
    assert job["resultado"]["piezas"] == 1 and len(api.DOC.commands) == 1


def test_un_error_de_dominio_es_400_y_no_deja_nada(clientes):
    ext, _nucleo, _store, _pid = clientes
    r = ext.post("/api/prueba/caja", params={"lado": -5})
    assert r.status_code == 400 and api.DOC.commands == []
    assert not api.DOC._undo


def test_la_guardia_del_documento_y_el_solo_lectura_dan_409(clientes):
    ext, nucleo, _store, _pid = clientes
    token = nucleo.get("/api/health").json()["documento"]
    r = ext.post("/api/prueba/caja", headers={CABECERA: "otro-documento"})
    assert r.status_code == 409 and api.DOC.commands == []
    assert ext.put("/api/prueba/nota", json={"a": 1}, headers={CABECERA: "x"}).status_code == 409
    assert ext.post("/api/prueba/caja", headers={CABECERA: token}).status_code == 200
    api.DOC.solo_lectura = {"extensiones": ["zeta"], "aviso": "Este proyecto usa la extensión «zeta»"}
    r = ext.post("/api/prueba/caja")
    assert r.status_code == 409 and "zeta" in r.json()["detail"] and len(api.DOC.commands) == 1
    assert ext.put("/api/prueba/nota", json={"a": 1}).status_code == 409 and api.DOC.ext == {}


def test_sus_datos_van_al_manifest_y_vuelven(clientes):
    ext, nucleo, store, pid = clientes
    assert ext.get("/api/prueba/nota").json() == {"nota": None}
    nota = {"lado": "izquierdo", "cotas": [1, 2.5]}
    assert ext.put("/api/prueba/nota", json=nota).json() == {"nota": nota}
    assert ext.get("/api/prueba/nota").json() == {"nota": nota}
    api._flush_autosave(force=True)
    assert _manifest(store.load_bytes(pid))["ext"] == {"ext-prueba": nota}
    assert nucleo.post(f"/api/projects/{pid}/open").status_code == 200  # reabrir: sigue ahí
    assert ext.get("/api/prueba/nota").json() == {"nota": nota}
    assert ext.put("/api/prueba/nota", json=None).json() == {"nota": None}  # None la borra
    assert api.DOC.ext == {}


def test_poner_ext_solo_escribe_la_de_una_extension_cargada(clientes):
    from fastapi import HTTPException

    from apolo.extensiones_api import leer_documento, poner_ext

    with pytest.raises(HTTPException) as exc:
        poner_ext("zeta", {"a": 1})
    assert exc.value.status_code == 400 and "no es una extensión cargada" in exc.value.detail
    with pytest.raises(HTTPException) as exc:
        poner_ext("ext-prueba", {"a": [object()]})
    assert exc.value.status_code == 400 and "JSON plano" in exc.value.detail

    def roto(doc):
        doc.edit("c99", {})

    with pytest.raises(HTTPException) as exc:
        leer_documento(roto)
    assert exc.value.status_code == 400


def test_la_fachada_es_la_misma_funcion_que_la_api():
    from apolo import extensiones_api
    from apolo.api import fachada

    for nombre in ("leer_documento", "mutar_documento", "leer_ext", "poner_ext", "proyecto_activo"):
        assert getattr(extensiones_api, nombre) is getattr(fachada, nombre)


# ── los ítems de la puerta de publicación ────────────────────────────────────────────────────

def _mesa() -> Document:
    d = Document("mesa")
    d.execute("create_box", {"name": "Tablero", "width": 400, "depth": 300, "height": 20})
    return d


def _puerta_por_la_ruta(monkeypatch) -> dict:
    """La ruta entera (`POST /api/puerta-publicacion`) sin MuJoCo: la gravedad no corre (es
    SIN_EVALUAR, como en `test_puerta_publicacion`); lo que se mira aquí es el registro."""
    from fastapi import HTTPException

    from apolo.api.routers import validation

    def sin_mujoco(_body, **_kw):
        raise HTTPException(status_code=400, detail="sin MuJoCo en este test")

    monkeypatch.setattr(validation, "_stability", sin_mujoco)
    r = TestClient(api.app).post("/api/puerta-publicacion")
    assert r.status_code == 200, r.text
    return r.json()


def test_sin_extensiones_el_registro_y_su_version_son_los_de_siempre():
    from apolo.library.calidad import registro as R

    assert R.DE_EXTENSION == {} and R.vigente() == R.REGISTRO
    assert R.version() == R.version(R.vigente()) == R.VERSION_REGISTRO


def test_los_items_de_la_extension_entran_a_la_ruta_y_a_la_version(con_prueba, monkeypatch):
    from apolo.extensiones_api import poner_ext
    from apolo.library.calidad import registro as R
    from ext_prueba import puerta

    assert R.DE_EXTENSION == {"ext-prueba": (1, (puerta.SIEMPRE, puerta.NOTA))}
    assert R.vigente()[-2:] == (puerta.SIEMPRE, puerta.NOTA)
    assert R.version(R.vigente()) == R.VERSION_REGISTRO + "+ext-prueba.1"
    assert R.version() == R.VERSION_REGISTRO  # el registro del núcleo solo no la nombra
    monkeypatch.setattr(api, "DOC", _mesa())
    out = _puerta_por_la_ruta(monkeypatch)
    items = {i["id"]: i for i in out["items"]}
    assert out["version_registro"] == R.VERSION_REGISTRO + "+ext-prueba.1"
    assert items["prueba.siempre"]["estado"] == "OK" and items["prueba.siempre"]["familia"] == "proceso"
    assert items["prueba.nota_ok"]["estado"] == "OK"
    assert items["prueba.nota_ok"]["evidencia"]["origen"] == "prueba.origen.nota"
    antes = out["firma"]
    poner_ext("ext-prueba", {"falla": True})  # su fuente lee la clave `ext` del manifest
    out = _puerta_por_la_ruta(monkeypatch)
    items = {i["id"]: i for i in out["items"]}
    assert items["prueba.nota_ok"]["estado"] == "FALLA" and out["aprobado"] is False
    assert out["firma"] != antes  # los datos de la extensión entran a la firma del modelo


def test_la_version_de_la_puerta_de_la_extension_sube_la_del_registro(extensiones_aisladas,
                                                                      monkeypatch):
    from apolo.library.calidad import registro as R

    monkeypatch.setenv(EXTRA, "ext_prueba:PUERTA_V2")
    assert extensiones_aisladas.cargar()[0]["cargada"]
    assert R.version(R.vigente()) == R.VERSION_REGISTRO + "+ext-prueba.2"


def test_sin_ext_la_firma_del_modelo_es_la_historica():
    from apolo.services import puerta_publicacion as pp

    d = _mesa()
    base = pp.firma(d)
    assert pp.firma_modelo(d.commands, {}) == pp.firma_modelo(d.commands, {"ext": {}})
    d.ext["zeta"] = {"a": 1}
    assert pp.firma(d) != base
    del d.ext["zeta"]
    assert pp.firma(d) == base


@pytest.mark.parametrize(("extra", "motivo"), [
    ("ext_prueba:PUERTA_SIN_PREFIJO", "no lleva el prefijo «prueba.»"),
    ("ext_prueba:PUERTA_FAMILIA", "familia «inventada»"),
    ("ext_prueba:PUERTA_REPETIDA", "ya existe"),
    ("ext_prueba:PUERTA_NO_ENTRADA", "no es Entrada ni Fuente"),
])
def test_una_puerta_que_no_cumple_no_carga_la_extension(extensiones_aisladas, monkeypatch, extra,
                                                       motivo):
    from apolo.commands.registry import REGISTRY
    from apolo.library.calidad import registro as R

    monkeypatch.setenv(EXTRA, extra)
    (e,) = extensiones_aisladas.cargar()
    assert e["cargada"] is False and motivo in e["motivo"], e
    assert R.DE_EXTENSION == {} and "prueba.hola" not in REGISTRY  # todo o nada


def test_al_salir_el_registro_de_la_puerta_queda_como_estaba(monkeypatch):
    from apolo import extensiones
    from apolo.library.calidad import registro as R

    monkeypatch.delenv("APOLO_EXTENSIONES", raising=False)
    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION")
    with extensiones.aislado():
        assert extensiones.cargar()[0]["cargada"] and R.DE_EXTENSION
    assert R.DE_EXTENSION == {} and R.vigente() == R.REGISTRO
