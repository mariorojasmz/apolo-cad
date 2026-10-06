"""Guardia del documento (F3 del plan `docs/plans/chat-cliente-igual.md`, D3 y D18).

Un cliente que manda `X-Apolo-Documento` (el token que publica `GET /api/health`) sólo muta
ESE documento: con otro activo, 409 sin aplicar nada —ni comando, ni autoguardado, ni aviso
por WebSocket—. La comparación ocurre DENTRO del `STATE_LOCK` de la mutación, así que un
cambio de proyecto entre que la petición llega y que toma el lock tampoco la deja pasar. Sin
cabecera todo queda como estaba. D18: `/api/sketch/solve` resuelve `'=expresión'` y
`POST /api/agent/notes` recorta como lo hacía el chat de la app.
"""

from __future__ import annotations

import importlib.util
import io
import re
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.api import guardia_documento as guardia
from apolo.doc import Document
from apolo.state import STATE_LOCK

RAIZ = Path(__file__).resolve().parents[1]
CABECERA = guardia.CABECERA
CAJA = {"type": "create_box", "params": {"name": "Nueva", "position": {"x": -300}}}
FEA = {"feature_id": "nada", "fixed": {"mode": "cara", "face": "base"}}


def _modelo() -> Document:
    """Variable, dos piezas, una junta, un anclaje, una variante, un estudio y una cadena:
    lo justo para que cada ruta guardada tenga algo que mutar."""
    d = Document("guardia")
    d.execute("set_variable", {"name": "L", "expression": "100"})  # c1
    d.execute("create_box", {"name": "Base", "width": 200, "depth": 200, "height": 20})  # c2
    d.execute("create_box", {"name": "Tapa", "width": 100, "depth": 100, "height": 100,
                             "position": {"z": 60}})  # c3, apoyada en la base
    d.execute("add_joint", {"name": "puerta", "parent": "c2", "child": "c3", "origin": {"x": 150}})
    d.execute("ground", {"name": "g1", "feature": "c2"})
    d.save_configuration("v1", ["L"])
    d.set_motion("existente", [{"t": 0, "values": {"puerta": 0}}, {"t": 1, "values": {"puerta": 10}}])
    d.set_stackup("holgura", [{"nombre": "a", "nominal_mm": 10, "sentido": 1, "tol": {"pm": 0.1}}])
    return d


@pytest.fixture(scope="module")
def step_bytes(tmp_path_factory) -> bytes:
    from build123d import Box

    from apolo.kernel import export_step_file

    ruta = tmp_path_factory.mktemp("guardia") / "caja.step"
    export_step_file([Box(10, 10, 10)], str(ruta))
    return ruta.read_bytes()


#: Cada mutación guardada: las que alcanzan las tools del chat por `_state_or_error` (F0), las
#: de FUERA del embudo y el `async def` de importar (el ContextVar en el bucle de eventos).
RUTAS = {
    "run_command": ("POST", "/api/commands", {"json": CAJA}),
    "edit_command": ("PUT", "/api/commands/c3", {"params": {"merge": "true"},
                                                 "json": {"params": {"width": 80}}}),
    "run_batch": ("POST", "/api/commands/batch", {"json": {"actions": [CAJA]}}),
    "edit_batch": ("PATCH", "/api/commands/batch", {
        "params": {"merge": "true"}, "json": {"edits": [{"command_id": "c3", "params": {"width": 70}}]}}),
    "remove_commands": ("POST", "/api/commands/remove", {"json": {"ids": ["c5"]}}),
    "undo": ("POST", "/api/undo", {}),
    "redo": ("POST", "/api/redo", {}),
    "set_variable": ("POST", "/api/variables", {"json": {"name": "L", "expression": "200"}}),
    "delete_variable": ("DELETE", "/api/variables/L", {}),
    "set_material": ("POST", "/api/features/material", {"json": {"ids": ["c2"], "material": "aluminio"}}),
    "set_color": ("POST", "/api/features/color", {"json": {"ids": ["c2"], "color": "#ff0000"}}),
    "set_vertical": ("POST", "/api/vertical", {"json": {"vertical": "carpinteria"}}),
    "set_visibility": ("POST", "/api/features/c3/visibility", {"json": {"visible": False}}),
    "set_visibility_bulk": ("POST", "/api/features/visibility", {"json": {"ids": ["c3"], "visible": False}}),
    "save_configuration": ("POST", "/api/configurations", {"json": {"name": "v2"}}),
    "apply_configuration": ("POST", "/api/configurations/v1/apply", {}),
    "delete_configuration_column": ("DELETE", "/api/configuration-columns/L", {}),
    "declare_structure": ("POST", "/api/assembly/declare", {}),
    "delete_connection": ("POST", "/api/connections/remove", {"json": {"names": ["g1"]}}),
    "delete_joint": ("DELETE", "/api/joints/puerta", {}),
    "rename_project": ("PATCH", "/api/projects/current", {"json": {"name": "Otro"}}),
    "import_step": ("POST", "/api/import", {"files": "STEP"}),
    # fuera de `_state_or_error`: cada una llama a la guardia a mano
    "add_agent_note": ("POST", "/api/agent/notes", {"json": {"text": "nota"}}),
    "set_motion": ("PUT", "/api/motion", {"json": {"name": "abrir", "keyframes": [
        {"t": 0, "values": {"puerta": 0}}, {"t": 1, "values": {"puerta": 30}}]}}),
    "delete_motion": ("DELETE", "/api/motion", {"json": {"name": "existente"}}),
    "set_requirements": ("PUT", "/api/requirements", {"json": {"fields": {"carga_kg": 20}}}),
    "set_stackup": ("PUT", "/api/stackup", {"json": {"name": "otra", "eslabones": [
        {"nombre": "b", "nominal_mm": 5, "sentido": 1, "tol": {"pm": 0.05}}]}}),
    "delete_stackup": ("DELETE", "/api/stackup", {"json": {"name": "holgura"}}),
    "fea_static": ("POST", "/api/fea/static", {"json": FEA}),
    "fea_static_png": ("POST", "/api/fea/static.png", {"json": FEA}),
    "fea_assembly": ("POST", "/api/fea/assembly", {"json": {"ids": ["nada"]}}),
    "fea_assembly_png": ("POST", "/api/fea/assembly.png", {"json": {"ids": ["nada"]}}),
}


def _preparar(monkeypatch):
    """Modelo nuevo como documento activo + espías del autoguardado y del WebSocket."""
    doc = _modelo()
    monkeypatch.setattr(api, "DOC", doc)
    espias: dict[str, list] = {"autoguardado": [], "aviso": []}
    monkeypatch.setattr(api._autosave_sched, "schedule", lambda: espias["autoguardado"].append(1))

    def avisar(msg=None):  # «el documento cambió»; el estado de un job no cuenta como aviso
        if not (msg and msg.get("type") == "job"):
            espias["aviso"].append(1)

    monkeypatch.setattr(api.WS, "notify_changed", avisar)
    return doc, espias


def _pedir(cliente, ruta, cabecera=None, step=b"", asincrono=False):
    metodo, path, kwargs = RUTAS[ruta]
    if kwargs.get("files") == "STEP":
        kwargs = {"files": {"file": ("caja.step", step, "application/octet-stream")}}
    if asincrono:  # el lote se encola como job (`?async=true`)
        kwargs = {**kwargs, "params": {**kwargs.get("params", {}), "async": "true"}}
    headers = {} if cabecera is None else {CABECERA: cabecera}
    return cliente.request(metodo, path, headers=headers, **kwargs)


def _huella(doc: Document):
    with zipfile.ZipFile(io.BytesIO(doc.to_apolo_bytes())) as z:
        archivos = {n: z.read(n) for n in z.namelist()}  # sin las fechas del zip
    piezas = sorted((f.id, f.name, f.visible) for f in doc.scene.values())
    return archivos, piezas, len(doc._undo), len(doc._redo)


def _ajeno() -> str:
    return guardia.token(Document("otro"))


def _esperar_job(cliente, job_id: str) -> dict:
    limite = time.monotonic() + 30
    while time.monotonic() < limite:
        job = cliente.get(f"/api/jobs/{job_id}", params={"wait_s": 5}).json()
        if job["estado"] in ("ok", "error"):
            return job
    raise AssertionError(f"el job {job_id} no terminó")


def _ocupar_worker() -> threading.Event:
    """El worker de jobs queda esperando: lo que se encole después corre al soltarlo."""
    compuerta = threading.Event()
    api.JOBS.submit("bloqueo", lambda: (compuerta.wait(10), {})[1])
    return compuerta


# ── 409 con un token ajeno, sin aplicar nada ──────────────────────────────────


@pytest.mark.parametrize("ruta", sorted(RUTAS))
def test_un_token_ajeno_da_409_y_no_aplica_nada(monkeypatch, step_bytes, ruta):
    doc, espias = _preparar(monkeypatch)
    antes = _huella(doc)

    r = _pedir(TestClient(api.app), ruta, _ajeno(), step_bytes)

    assert r.status_code == 409, r.text
    assert r.json() == {"detail": guardia.DOCUMENTO_CAMBIO}
    assert api.DOC is doc and _huella(doc) == antes
    assert espias == {"autoguardado": [], "aviso": []}


def test_una_cabecera_vacia_no_apaga_la_guardia(monkeypatch):
    doc, espias = _preparar(monkeypatch)
    antes = _huella(doc)
    assert _pedir(TestClient(api.app), "run_command", "").status_code == 409
    assert _huella(doc) == antes and espias["autoguardado"] == []


# ── con el token correcto, lo mismo que sin cabecera ──────────────────────────


@pytest.mark.parametrize("ruta", sorted(RUTAS))
def test_con_el_token_correcto_hace_lo_mismo_que_sin_cabecera(monkeypatch, step_bytes, ruta):
    """Mismo código, mismo texto de error, mismo documento después, mismos autoguardados y
    avisos: la cabecera correcta no cambia nada y sin ella la API es la de siempre."""
    vistos = []
    for con_token in (False, True):
        doc, espias = _preparar(monkeypatch)
        cliente = TestClient(api.app)
        antes = _huella(doc)
        token = cliente.get("/api/health").json()["documento"] if con_token else None
        r = _pedir(cliente, ruta, token, step_bytes)
        detalle = r.json().get("detail") if r.status_code >= 400 else None
        vistos.append((r.status_code, detalle, _huella(doc), _huella(doc) != antes,
                       len(espias["autoguardado"]), len(espias["aviso"])))
    assert vistos[0] == vistos[1]
    codigo, _, _, muto, _, _ = vistos[0]
    if ruta == "redo":
        assert codigo == 400 and not muto  # nada que rehacer
    elif ruta.startswith("fea_"):
        assert codigo == 404 and not muto  # pasó la guardia y llegó a la preparación
    else:
        assert codigo == 200 and muto, ruta


# ── la comparación ocurre bajo el lock de la mutación ─────────────────────────


@pytest.mark.parametrize("ruta", sorted(RUTAS))
def test_la_guardia_compara_bajo_el_lock(monkeypatch, step_bytes, ruta):
    doc, _ = _preparar(monkeypatch)
    token = guardia.token(doc)
    real, bajo_lock = guardia.token, []
    monkeypatch.setattr(guardia, "token",
                        lambda d: (bajo_lock.append(STATE_LOCK._is_owned()), real(d))[1])
    _pedir(TestClient(api.app), ruta, token, step_bytes)
    assert bajo_lock and all(bajo_lock), bajo_lock


@pytest.mark.parametrize("con_cabecera", [True, False])
def test_un_cambio_de_documento_mientras_espera_el_lock_no_la_deja_pasar(monkeypatch, con_cabecera):
    """La petición llega (el middleware ya leyó la cabecera) y espera el lock; mientras, otro
    documento pasa a ser el activo (el swap de abrir o restaurar ocurre bajo `STATE_LOCK`).
    Con cabecera: 409 y ninguno de los dos cambia. Sin ella, lo de hoy: aplica al nuevo."""
    doc, espias = _preparar(monkeypatch)
    cliente = TestClient(api.app)
    token = cliente.get("/api/health").json()["documento"] if con_cabecera else None
    antes, nuevo, respuestas = _huella(doc), Document("abierto-mientras-tanto"), []

    hilo = threading.Thread(target=lambda: respuestas.append(_pedir(cliente, "run_command", token)))
    with STATE_LOCK:
        hilo.start()
        hilo.join(0.5)
        assert hilo.is_alive()  # espera el lock con la cabecera ya leída
        api.DOC = nuevo
    hilo.join(30)

    assert _huella(doc) == antes
    if con_cabecera:
        assert respuestas[0].status_code == 409 and nuevo.commands == []
        assert espias == {"autoguardado": [], "aviso": []}
    else:
        assert respuestas[0].status_code == 200 and len(nuevo.scene) == 1


# ── el job encolado ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("ruta", ["run_batch", "edit_batch"])
def test_un_job_con_token_ajeno_no_se_aplica(monkeypatch, ruta):
    doc, espias = _preparar(monkeypatch)
    cliente = TestClient(api.app)
    antes = _huella(doc)
    r = _pedir(cliente, ruta, _ajeno(), asincrono=True)
    assert r.status_code == 202
    job = _esperar_job(cliente, r.json()["job_id"])
    assert job["estado"] == "error" and job["http_status"] == 409
    assert job["error"] == guardia.DOCUMENTO_CAMBIO
    assert _huella(doc) == antes and espias == {"autoguardado": [], "aviso": []}


@pytest.mark.parametrize("con_cabecera", [True, False])
def test_un_job_encolado_no_cae_en_la_revision_restaurada(monkeypatch, con_cabecera):
    """Restaurar una revisión conserva el id de proyecto: la guardia por proyecto del job lo
    deja pasar (aplica sobre lo restaurado). La del documento, no: el job lo pidió para
    OTRO objeto `Document`."""
    doc, _ = _preparar(monkeypatch)
    cliente = TestClient(api.app)
    token = cliente.get("/api/health").json()["documento"] if con_cabecera else None
    compuerta = _ocupar_worker()
    r = _pedir(cliente, "run_batch", token, asincrono=True)
    restaurado = Document("revision-restaurada")
    api.DOC = restaurado  # mismo PROJECT_ID, documento nuevo (restore_revision)
    compuerta.set()
    job = _esperar_job(cliente, r.json()["job_id"])

    assert doc.scene.keys() == {"c2", "c3"}
    if con_cabecera:
        assert job["http_status"] == 409 and job["error"] == guardia.DOCUMENTO_CAMBIO
        assert restaurado.commands == []
    else:
        assert job["estado"] == "ok" and len(restaurado.scene) == 1


def test_el_job_compara_bajo_el_lock_y_aplica_con_el_token_correcto(monkeypatch):
    doc, _ = _preparar(monkeypatch)
    cliente = TestClient(api.app)
    token = cliente.get("/api/health").json()["documento"]
    real, bajo_lock = guardia.token, []
    monkeypatch.setattr(guardia, "token",
                        lambda d: (bajo_lock.append(STATE_LOCK._is_owned()), real(d))[1])
    r = _pedir(cliente, "run_batch", token, asincrono=True)
    job = _esperar_job(cliente, r.json()["job_id"])
    assert job["estado"] == "ok" and "Nueva" in {f.name for f in doc.scene.values()}
    assert bajo_lock and all(bajo_lock)


# ── el token: por objeto Document, publicado en /api/health ───────────────────


def test_health_publica_el_token_del_documento_activo(monkeypatch):
    doc, _ = _preparar(monkeypatch)
    salud = TestClient(api.app).get("/api/health").json()
    assert salud["documento"] == guardia.token(doc)
    assert re.fullmatch(r"[0-9a-f]{16}", salud["documento"])


def test_el_token_cambia_con_el_documento_y_no_con_sus_ediciones(monkeypatch, tmp_path):
    from apolo.projects import ProjectStore

    monkeypatch.setattr(api, "STORE", ProjectStore(tmp_path / "guardia.db"))
    doc = _modelo()
    monkeypatch.setattr(api, "DOC", doc)
    monkeypatch.setattr(api, "PROJECT_ID", api.STORE.create(doc))
    pid, cliente = api.PROJECT_ID, TestClient(api.app)

    def token() -> str:
        return cliente.get("/api/health").json()["documento"]

    vistos = [token()]
    for metodo, path, kw in (("POST", "/api/commands", {"json": CAJA}), ("POST", "/api/undo", {}),
                             ("PATCH", "/api/projects/current", {"json": {"name": "Renombrado"}}),
                             ("POST", "/api/configurations/v1/apply", {})):
        assert cliente.request(metodo, path, **kw).status_code == 200
        assert token() == vistos[0], f"{metodo} {path} cambió el token"
    rev = cliente.post("/api/revisions", json={"note": "r1"}).json()["id"]
    assert cliente.post(f"/api/revisions/{rev}/restore").status_code == 200
    vistos.append(token())
    assert api.PROJECT_ID == pid  # mismo proyecto, documento nuevo
    assert cliente.post(f"/api/projects/{pid}/open").status_code == 200  # el mismo, reabierto
    vistos.append(token())
    assert cliente.post("/api/project/new", json={"name": "Dos"}).status_code == 200
    vistos.append(token())
    assert cliente.post("/api/projects", json={"name": "Tres"}).status_code == 200
    vistos.append(token())
    subido = cliente.post("/api/project/open",
                          files={"file": ("p.apolo", doc.to_apolo_bytes(), "application/zip")})
    assert subido.status_code == 200
    vistos.append(token())

    assert len(set(vistos)) == len(vistos), vistos
    viejo = cliente.post("/api/commands", json=CAJA, headers={CABECERA: vistos[0]})
    assert viejo.status_code == 409 and len(api.DOC.scene) == 2


def test_el_token_vale_por_objeto_y_se_va_con_el():
    import gc

    a, b = Document("a"), Document("a")
    assert guardia.token(a) == guardia.token(a) != guardia.token(b)
    n = len(guardia._TOKENS)
    del a, b
    gc.collect()
    assert len(guardia._TOKENS) <= n - 2  # sin `id()` crudo: un documento nuevo no lo hereda


def test_el_texto_del_409_cumple_el_estandar():
    spec = importlib.util.spec_from_file_location("_pistas_gate", RAIZ / "tests" / "test_pistas.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    assert gate.faltas(guardia.DOCUMENTO_CAMBIO) == []


# ── D18: los endpoints igualan lo que el chat hacía mejor ─────────────────────


def _rectangulo(ancho, alto) -> dict:
    lados = [("l1", "a", "b"), ("l2", "b", "c"), ("l3", "c", "d"), ("l4", "d", "a")]
    return {
        "points": {"a": [0, 0], "b": [100, 0], "c": [100, 50], "d": [0, 50]},
        "entities": [{"type": "line", "id": i, "from": p, "to": q} for i, p, q in lados],
        "constraints": [
            {"type": "fix", "point": "a"}, {"type": "horizontal", "entity": "l1"},
            {"type": "vertical", "entity": "l2"}, {"type": "horizontal", "entity": "l3"},
            {"type": "vertical", "entity": "l4"},
            {"type": "length", "entity": "l1", "value": ancho},
            {"type": "length", "entity": "l2", "value": alto},
        ],
    }


def test_el_croquis_resuelve_expresiones_con_las_variables_del_proyecto(monkeypatch):
    from apolo.kernel.sketch_solver import solve_sketch

    doc = Document("croquis")
    doc.execute("set_variable", {"name": "ancho", "expression": "120"})
    doc.execute("set_variable", {"name": "alto", "expression": "=ancho/4"})
    monkeypatch.setattr(api, "DOC", doc)
    cliente = TestClient(api.app)

    r = cliente.post("/api/sketch/solve", json={"sketch": _rectangulo("=ancho", "=alto")})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["points"]["c"] == [120.0, 30.0]
    # sin expresiones, la misma respuesta que el solver a secas
    plano = _rectangulo(120, 30)
    assert cliente.post("/api/sketch/solve", json={"sketch": plano}).json() == solve_sketch(plano)
    malo = cliente.post("/api/sketch/solve", json={"sketch": _rectangulo("=largo", 30)})
    assert malo.status_code == 400 and malo.json()["detail"] == "Variable 'largo' no definida"
    assert doc.commands and len(doc.commands) == 2  # probar el croquis no toca el proyecto


def test_la_nota_se_recorta_como_en_el_chat(monkeypatch):
    doc, _ = _preparar(monkeypatch)
    cliente = TestClient(api.app)
    notas = cliente.post("/api/agent/notes", json={"text": "  " + "x" * 600 + " \n"}).json()["notes"]
    assert notas == ["x" * 500]
    for i in range(35):
        cliente.post("/api/agent/notes", json={"text": f" nota {i} "})
    assert doc.agent_notes == [f"nota {i}" for i in range(5, 35)]  # tope de 30, las últimas
