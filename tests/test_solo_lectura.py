"""Proyecto que necesita una extensión AUSENTE → SÓLO LECTURA (D4 del plan
nucleo-abierto-extensiones-privadas, F1b), con la extensión falsa `tests/ext_prueba/`:

- se crea un proyecto CON `prueba.*` (comando `prueba.hola` y ref `prueba.caja`) y se abre SIN la
  extensión: queda marcado (`document.solo_lectura`, `GET /api/health`, el briefing), se ve lo
  que regenera y lo de la extensión queda suprimido;
- toda mutación da 409 con el texto de D4 (las cuatro puertas, deshacer/rehacer, variables,
  `remove_commands` de lo suprimido, color, material; también como job y por el MCP) y
  `Document` sin la API lanza en `_snapshot()`;
- el autosave no lo reescribe: el `.apolo` queda byte a byte;
- `duplicate` copia el log tal cual (la copia también abre en sólo lectura), `insert_project` de
  un proyecto así se rechaza al crear y el anfitrión que ya lo tenía abre en sólo lectura;
  restaurar una revisión sobre él o restaurar una revisión así da 409;
- con la extensión cargada otra vez, el mismo proyecto abre editable; un proyecto sin comandos
  de extensión sigue exactamente igual.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo import extensiones
from apolo.doc import Document, DocumentError, solo_lectura, subproject
from apolo.projects import ProjectStore

EXTRA = "APOLO_EXTENSIONES_EXTRA"
AVISO = ("Este proyecto usa la extensión «prueba», que no está instalada: puedes verlo, no "
         "editarlo.")


def _con_prueba(fn):
    """Corre `fn()` con la extensión falsa cargada y devuelve lo que dé; al salir el núcleo
    queda como estaba. La caché de `insert_project` se vacía: en un proceso real las extensiones
    se cargan UNA vez al arrancar y un replay cacheado con la extensión nunca se mezcla con uno sin
    ella (aquí sí, por eso se limpia)."""
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("APOLO_EXTENSIONES", raising=False)
        mp.setenv(EXTRA, "ext_prueba:EXTENSION")
        with extensiones.aislado():
            assert extensiones.cargar()[0]["cargada"]
            try:
                return fn()
            finally:
                subproject._CACHE.clear()


def _modelo_con_prueba() -> bytes:
    d = Document("con extensión")
    d.execute("set_variable", {"name": "L", "expression": "100"})  # c1
    d.execute("create_box", {"name": "Base", "width": "=L", "depth": 100, "height": 10})  # c2
    d.execute("prueba.hola", {"name": "Hola", "lado": 30})  # c3
    d.execute("insert_component", {"component": "prueba.caja"})  # c4
    return d.to_apolo_bytes()


@pytest.fixture(scope="module")
def con_prueba_bytes() -> bytes:
    return _con_prueba(_modelo_con_prueba)


@pytest.fixture(scope="module")
def anfitrion_bytes(con_prueba_bytes) -> bytes:
    """Un layout que insertó el proyecto con `prueba.*` (cuando la extensión estaba)."""
    def armar():
        d = Document("layout")
        d.execute("create_box", {"name": "Piso", "width": 500, "depth": 500, "height": 5,
                                 "position": {"x": 2000}})
        d.execute("insert_project", {"attachment": d.add_attachment(con_prueba_bytes),
                                     "name": "Sub"})
        return d.to_apolo_bytes()

    return _con_prueba(armar)


def _comandos(data: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return json.loads(z.read("commands.json"))


@pytest.fixture
def abierto(monkeypatch, tmp_path, con_prueba_bytes):
    """El proyecto con `prueba.*` guardado en un almacén temporal y abierto por la API SIN la
    extensión. Devuelve (cliente, id, espía del autoguardado)."""
    store = ProjectStore(tmp_path / "solo_lectura.db")
    pid = store.create(Document("x"))
    store.save_raw(pid, "con extensión", 2, con_prueba_bytes)
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(api, "PROJECT_ID", None)
    monkeypatch.setattr(api, "DOC", Document("antes"))
    cliente = TestClient(api.app)
    r = cliente.post(f"/api/projects/{pid}/open")
    assert r.status_code == 200, r.text
    return cliente, pid, r.json()


# ── detección (pura) ─────────────────────────────────────────────────────────────────────────

def test_detecta_el_prefijo_ausente_y_no_la_deriva_vieja():
    log = [{"id": "c1", "type": "create_box", "params": {}},
           {"id": "c2", "type": "pro.cable", "params": {}},
           {"id": "c3", "type": "insert_component", "params": {"component": "zeta.motor"}},
           {"id": "c4", "type": "insert_component", "params": {"component": "REMACHE-3.2"}},
           {"id": "c5", "type": "comando_viejo", "params": {}},  # deriva sin prefijo: no cuenta
           {"id": "c6", "type": "Raro.Tipo", "params": {}}]  # mayúsculas: no es un prefijo
    assert solo_lectura.faltantes(log) == {"pro", "zeta"}
    marca = solo_lectura.detectar(log)
    assert marca == {"extensiones": ["pro", "zeta"], "aviso": (
        "Este proyecto usa las extensiones «pro» y «zeta», que no están instaladas: puedes verlo, "
        "no editarlo.")}
    assert solo_lectura.detectar(log[:1] + log[3:5]) is None


def test_detecta_dentro_de_los_proyectos_insertados(anfitrion_bytes):
    d = Document.from_apolo_bytes(anfitrion_bytes, regenerate=False)
    assert solo_lectura.detectar(d.commands, d.attachments)["extensiones"] == ["prueba"]
    assert solo_lectura.detectar(d.commands, {}) is None  # sin el adjunto no hay qué mirar


# ── Document sin la API ──────────────────────────────────────────────────────────────────────

def test_sin_la_extension_abre_aun_estricto_y_se_ve_lo_que_regenera(con_prueba_bytes):
    d = Document.from_apolo_bytes(con_prueba_bytes)  # estricto: la marca obliga a tolerar
    assert d.solo_lectura == {"extensiones": ["prueba"], "aviso": AVISO}
    assert [f.name for f in d.scene.values()] == ["Base"]
    assert [s["command_id"] for s in d.regen_suppressed] == ["c3", "c4"]
    assert [c["id"] for c in d.commands] == ["c1", "c2", "c3", "c4"]  # el log, intacto


def test_document_bloquea_toda_mutacion_del_log(con_prueba_bytes):
    d = Document.from_apolo_bytes(con_prueba_bytes)
    antes = d.to_apolo_bytes()
    intentos = [
        lambda: d.execute("create_box", {"name": "Otra"}),
        lambda: d.execute_many([{"type": "create_box", "params": {}}]),
        lambda: d.edit("c2", {"height": 20}, merge=True),
        lambda: d.edit_many([{"command_id": "c2", "params": {"height": 20}}], merge=True),
        lambda: d.remove_commands(["c3", "c4"]),  # lo suprimido: hoy se perdía
        lambda: d.execute("set_variable", {"name": "L", "expression": "200"}),
    ]
    for intento in intentos:
        with pytest.raises(DocumentError, match="no está instalada"):
            intento()
    assert d.to_apolo_bytes() == antes and len(d._undo) == 0


def test_un_proyecto_sin_extensiones_no_se_marca():
    d = Document("núcleo")
    d.execute("create_box", {"name": "Caja"})
    otra = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert otra.solo_lectura is None and d.solo_lectura is None
    otra.execute("create_box", {"name": "Otra"})  # editable como siempre


def test_un_comando_desconocido_sin_prefijo_sigue_el_camino_tolerante():
    d = Document("deriva")
    d.execute("create_box", {"name": "Caja"})
    d.commands.append({"id": "c9", "type": "comando_que_ya_no_existe", "params": {}})
    otra = Document.from_apolo_bytes(d.to_apolo_bytes(), tolerant=True)
    assert otra.solo_lectura is None and otra.regen_suppressed[0]["command_id"] == "c9"
    otra.remove_commands(["c9"])  # la deriva vieja se limpia como antes


# ── la API ───────────────────────────────────────────────────────────────────────────────────

def test_abre_marcado_con_la_escena_visible(abierto):
    cliente, pid, payload = abierto
    assert payload["document"]["solo_lectura"] == {"extensiones": ["prueba"], "aviso": AVISO}
    assert [f["name"] for f in payload["features"]] == ["Base"]
    assert payload["briefing"]["salud"]["solo_lectura"]["extensiones"] == ["prueba"]
    salud = cliente.get("/api/health").json()
    assert salud["solo_lectura"]["aviso"] == AVISO
    assert cliente.get("/api/scene").json()["document"]["solo_lectura"]["aviso"] == AVISO


#: Cada puerta que muta el documento: todas dan 409 con el aviso, sin tocar nada.
RUTAS = {
    "run_command": ("POST", "/api/commands", {"json": {"type": "create_box", "params": {}}}),
    "edit_command": ("PUT", "/api/commands/c2", {"params": {"merge": "true"},
                                                 "json": {"params": {"height": 20}}}),
    "run_batch": ("POST", "/api/commands/batch", {"json": {"actions": [
        {"type": "create_box", "params": {}}]}}),
    "edit_batch": ("PATCH", "/api/commands/batch", {"params": {"merge": "true"}, "json": {
        "edits": [{"command_id": "c2", "params": {"height": 20}}]}}),
    "remove_commands": ("POST", "/api/commands/remove", {"json": {"ids": ["c3", "c4"]}}),
    "undo": ("POST", "/api/undo", {}),
    "redo": ("POST", "/api/redo", {}),
    "set_variable": ("POST", "/api/variables", {"json": {"name": "L", "expression": "200"}}),
    "delete_variable": ("DELETE", "/api/variables/L", {}),
    "set_color": ("POST", "/api/features/color", {"json": {"ids": ["c2"], "color": "#ff0000"}}),
    "set_material": ("POST", "/api/features/material", {"json": {"ids": ["c2"],
                                                                 "material": "aluminio"}}),
    "set_visibility": ("POST", "/api/features/c2/visibility", {"json": {"visible": False}}),
    "rename_project": ("PATCH", "/api/projects/current", {"json": {"name": "Otro"}}),
    "save_configuration": ("POST", "/api/configurations", {"json": {"name": "v", "variables": ["L"]}}),
    "add_agent_note": ("POST", "/api/agent/notes", {"json": {"text": "nota"}}),
    "set_requirements": ("PUT", "/api/requirements", {"json": {"fields": {"carga_kg": 20}}}),
}


@pytest.mark.parametrize("ruta", sorted(RUTAS))
def test_toda_mutacion_da_409_con_el_aviso_y_el_apolo_queda_byte_a_byte(abierto, con_prueba_bytes,
                                                                        ruta):
    cliente, pid, _ = abierto
    metodo, path, kwargs = RUTAS[ruta]
    r = cliente.request(metodo, path, **kwargs)
    assert r.status_code == 409, r.text
    assert r.json() == {"detail": AVISO}
    api._flush_autosave(force=True)
    assert api.STORE.load_bytes(pid) == con_prueba_bytes
    assert [c["id"] for c in api.DOC.commands] == ["c1", "c2", "c3", "c4"]


def test_como_job_tambien_da_409(abierto):
    cliente, _, _ = abierto
    r = cliente.post("/api/commands", params={"async": "true"},
                     json={"type": "create_box", "params": {}})
    assert r.status_code == 202
    job = cliente.get(f"/api/jobs/{r.json()['job_id']}", params={"wait_s": 20}).json()
    assert job["estado"] == "error" and job["http_status"] == 409 and job["error"] == AVISO


def test_el_mcp_recibe_el_409_como_rechazo_con_el_mismo_texto(abierto):
    pytest.importorskip("mcp")
    from apolo import mcp_server

    cliente, _, _ = abierto
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(mcp_server, "_api", lambda m, p, **k: _o_rechazo(mcp_server, cliente, m, p, **k))
        with pytest.raises(RuntimeError) as run:
            mcp_server.run_command("create_box", {"name": "Otra"})
        with pytest.raises(RuntimeError) as lote:
            mcp_server.edit_batch([{"command_id": "c2", "params": {"height": 20}}])
    for exc in (run, lote):
        assert str(exc.value) == f"Apolo rechazó la operación (409): {AVISO}"
    assert [c["id"] for c in api.DOC.commands] == ["c1", "c2", "c3", "c4"]


def _o_rechazo(mcp_server, cliente, method, path, **kwargs):
    """El `_api` del MCP contra la API en proceso (mismo manejo de errores que el real)."""
    r = cliente.request(method, path, **kwargs)
    if r.status_code >= 400:
        raise mcp_server._reject(r.status_code, r.json().get("detail"))
    return r


def test_el_autosave_no_escribe_un_documento_en_solo_lectura(abierto, con_prueba_bytes):
    _, pid, _ = abierto
    api.DOC.agent_notes.append("cambio en memoria que no debe llegar al disco")
    api._autosave_sched._dirty = True
    api._flush_autosave(force=True)
    assert api.STORE.load_bytes(pid) == con_prueba_bytes
    assert api.AUTOSAVE_ERROR is None


def test_el_arranque_y_la_subida_tambien_lo_marcan(monkeypatch, tmp_path, con_prueba_bytes):
    db = tmp_path / "arranque.db"
    store = ProjectStore(db)
    pid = store.create(Document("x"))
    store.save_raw(pid, "con extensión", 2, con_prueba_bytes)
    monkeypatch.setenv("APOLO_PROJECT", str(pid))
    api.initialize_store(str(db))
    assert api.DOC.solo_lectura["extensiones"] == ["prueba"] and api.PROJECT_ID == pid
    subido = TestClient(api.app).post(
        "/api/project/open", files={"file": ("p.apolo", con_prueba_bytes, "application/zip")})
    assert subido.status_code == 200 and subido.json()["document"]["solo_lectura"]
    assert _comandos(api.STORE.load_bytes(api.PROJECT_ID)) == _comandos(con_prueba_bytes)


def test_duplicar_copia_el_log_tal_cual_y_la_copia_tambien_es_de_solo_lectura(abierto,
                                                                               con_prueba_bytes):
    cliente, pid, _ = abierto
    r = cliente.post(f"/api/projects/{pid}/duplicate")
    assert r.status_code == 200, r.text  # antes: 500 (carga estricta)
    nuevo = r.json()["id"]
    assert _comandos(api.STORE.load_bytes(nuevo)) == _comandos(con_prueba_bytes)
    abierta = cliente.post(f"/api/projects/{nuevo}/open").json()
    assert abierta["document"]["solo_lectura"]["extensiones"] == ["prueba"]
    assert cliente.post("/api/projects/9999/duplicate").status_code == 404


def test_las_revisiones_no_restauran_sobre_el_ni_lo_restauran(abierto, con_prueba_bytes):
    cliente, pid, _ = abierto
    rev = cliente.post("/api/revisions", json={"note": "foto"})  # guardar una foto sí
    assert rev.status_code == 200
    r = cliente.post(f"/api/revisions/{rev.json()['id']}/restore")
    assert r.status_code == 409 and "no restaurar una revisión sobre él" in r.json()["detail"]
    assert api.STORE.load_bytes(pid) == con_prueba_bytes
    # la revisión con la extensión no se restaura sobre un proyecto editable
    limpio = Document("limpio")
    otro = api.STORE.create(limpio)
    with api.STORE._conn() as con:
        con.execute("UPDATE revisions SET project_id=? WHERE id=?", (otro, rev.json()["id"]))
    r = cliente.post(f"/api/revisions/{rev.json()['id']}/restore")
    assert r.status_code == 409
    assert r.json()["detail"].startswith("Esta revisión usa la extensión «prueba»")


def test_insertar_un_proyecto_que_usa_la_extension_se_rechaza_al_crear(abierto):
    cliente, pid, _ = abierto
    assert cliente.post("/api/project/new", json={"name": "Layout"}).status_code == 200
    r = cliente.post("/api/commands", json={"type": "insert_project",
                                            "params": {"project_id": pid, "name": "Sub"}})
    assert r.status_code == 400
    assert ("El proyecto insertado usa la extensión «prueba», que no está instalada: no se puede "
            "insertar ni regenerar aquí.") in r.json()["detail"]
    assert api.DOC.commands == [] and api.DOC.solo_lectura is None


def test_el_anfitrion_que_ya_lo_tenia_abre_entero_en_solo_lectura(anfitrion_bytes):
    d = Document.from_apolo_bytes(anfitrion_bytes)
    assert d.solo_lectura["extensiones"] == ["prueba"]
    assert [f.name for f in d.scene.values()] == ["Piso"]
    assert "El proyecto insertado usa la extensión «prueba»" in d.regen_suppressed[0]["error"]
    with pytest.raises(DocumentError, match="no está instalada"):
        d.remove_commands(["c2"])  # el sub-ensamblaje no se pierde


def test_con_la_extension_instalada_el_mismo_proyecto_abre_editable(abierto, con_prueba_bytes):
    cliente, pid, _ = abierto

    def reabrir():
        r = cliente.post(f"/api/projects/{pid}/open")
        assert r.status_code == 200
        assert "solo_lectura" not in r.json()["document"]
        assert {f["name"] for f in r.json()["features"]} >= {"Base", "Hola"}
        assert cliente.get("/api/health").json()["solo_lectura"] is None
        assert cliente.post("/api/commands", json={"type": "prueba.hola",
                                                   "params": {"lado": 10}}).status_code == 200
        return len(api.DOC.commands)

    assert _con_prueba(reabrir) == 5


def test_un_proyecto_sin_extensiones_sigue_exactamente_igual(monkeypatch):
    monkeypatch.setattr(api, "DOC", Document("núcleo"))
    cliente = TestClient(api.app)
    r = cliente.post("/api/commands", json={"type": "create_box", "params": {}})
    assert r.status_code == 200 and "solo_lectura" not in r.json()["document"]
    assert cliente.get("/api/health").json()["solo_lectura"] is None
