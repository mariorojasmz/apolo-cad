"""V6.5e — trabajos asíncronos (jobs): las mutaciones largas no matan la sesión.

Un lote se ENCOLA (`?async=true`) y devuelve un recibo (`job_id`); el resultado se recoge
con `GET /api/jobs/{id}` (long-poll). Sin `?async` todo sigue byte-idéntico: los tests de
batch existentes pasan sin tocarse.
"""

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.api.jobs import JobStore
from apolo.doc.document import Document


def _boxes():
    # A en el origen, B en x=200 → gap = 150 mm (bboxes 50×50×50 centradas)
    return [
        {"type": "create_box", "params": {"name": "A", "width": 50, "depth": 50, "height": 50}},
        {"type": "create_box", "params": {"name": "B", "width": 50, "depth": 50, "height": 50,
                                          "position": {"x": 200, "y": 0, "z": 0}}},
    ]


def _await_job(client, job_id, timeout=15.0):
    """Recoge un job terminado (long-poll). Falla si no termina en `timeout`."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/jobs/{job_id}", params={"wait_s": 5})
        assert r.status_code == 200, r.text
        job = r.json()
        if job["estado"] in ("ok", "error"):
            return job
    raise AssertionError(f"el job {job_id} no terminó en {timeout}s")


def _shape(payload):
    """Proyección comparable de un payload de escena (sin bits volátiles: rev/epoch)."""
    return {
        "total": payload["total_features"],
        "afectados": payload.get("affected_command_ids"),
        "contrato": payload.get("contrato"),
        "solidos": [
            (f["id"], f["name"], f["command_id"], round(f["volume_mm3"], 6), f["bbox"])
            for f in payload["features"]
        ],
    }


# ------------------------------------------------------------------ 1. compatibilidad
def test_sync_and_async_give_equivalent_result():
    """El MISMO lote por camino sync y por async+poll → payload equivalente y misma escena.
    Es la garantía del diseño: el job corre el MISMO closure, solo que fuera de la request."""
    api.DOC = Document("jobs-sync")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", json={"actions": _boxes()})
    assert r.status_code == 200, r.text
    sync_payload, sync_scene = r.json(), len(api.DOC.scene)

    api.DOC = Document("jobs-async")
    r = client.post("/api/commands/batch", params={"async": "true"}, json={"actions": _boxes()})
    assert r.status_code == 202, r.text
    job = _await_job(client, r.json()["job_id"])
    assert job["estado"] == "ok", job
    assert _shape(job["resultado"]) == _shape(sync_payload)
    assert len(api.DOC.scene) == sync_scene == 2


def test_no_async_param_is_byte_identical():
    """Sin `?async` el endpoint responde 200 con el payload de siempre (los clientes
    existentes —UI incluida— ni se enteran de que existen los jobs)."""
    api.DOC = Document("jobs-compat")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", json={"actions": _boxes()})
    assert r.status_code == 200
    assert "job_id" not in r.json()
    assert r.json()["total_features"] == 2


def test_async_contract_ok_travels_in_result():
    api.DOC = Document("jobs-contract-ok")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", params={"async": "true"}, json={
        "actions": _boxes(),
        "expect": [{"tipo": "distancia", "a": "$1", "b": "$2", "min": 100}],
    })
    job = _await_job(client, r.json()["job_id"])
    assert job["estado"] == "ok"
    assert job["resultado"]["contrato"] == {"n_aserciones": 1, "ok": True}


def test_edit_batch_async():
    api.DOC = Document("jobs-edit")
    client = TestClient(api.app)
    client.post("/api/commands/batch", json={"actions": _boxes()})
    r = client.patch("/api/commands/batch", params={"async": "true", "merge": "true"}, json={
        "edits": [{"command_id": "c1", "params": {"width": 80}}]
    })
    assert r.status_code == 202
    job = _await_job(client, r.json()["job_id"])
    assert job["estado"] == "ok" and job["tipo"] == "edit_batch"
    assert api.DOC.commands[0]["params"]["width"] == 80


# ------------------------------------------------------------------ 2. recibo + long-poll
def test_submit_returns_receipt_immediately():
    api.DOC = Document("jobs-receipt")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", params={"async": "true"}, json={"actions": _boxes()})
    assert r.status_code == 202
    body = r.json()
    assert body["estado"] == "encolado" and body["job_id"]
    _await_job(client, body["job_id"])  # no dejar el worker corriendo tras el test


def test_long_poll_wakes_before_deadline():
    """El long-poll despierta al TERMINAR el job, no al vencer wait_s (el camino feliz no
    paga latencia de sondeo)."""
    store = JobStore()
    jid = store.submit("t", lambda: {"ok": 1})
    t0 = time.monotonic()
    job = store.get(jid, wait_s=25)
    assert job["estado"] == "ok" and job["resultado"] == {"ok": 1}
    assert time.monotonic() - t0 < 5  # despertó al terminar, no a los 25 s


def test_long_poll_returns_running_when_budget_expires():
    store = JobStore()
    gate = threading.Event()
    jid = store.submit("t", lambda: (gate.wait(10), {"ok": 1})[1])
    job = store.get(jid, wait_s=0.2)  # el job sigue vivo: vence el plazo, no el job
    assert job["estado"] in ("encolado", "corriendo")
    gate.set()
    assert store.get(jid, wait_s=10)["estado"] == "ok"


# ------------------------------------------------------------------ 3. FIFO determinista
def test_fifo_order_is_deterministic():
    """UN worker → orden determinista (no hay paralelismo que ganar: STATE_LOCK serializa
    igual, y el orden importa: «un lote = UN regenerate»)."""
    store = JobStore()
    seen = []
    gate = threading.Event()
    first = store.submit("t", lambda: (gate.wait(10), seen.append("a"), {})[2])
    second = store.submit("t", lambda: (seen.append("b"), {})[1])
    gate.set()
    store.get(first, wait_s=10)
    store.get(second, wait_s=10)
    assert seen == ["a", "b"]  # el 2.º NO adelanta al 1.º


def test_api_batches_queue_in_order():
    api.DOC = Document("jobs-fifo")
    client = TestClient(api.app)
    ids = [
        client.post(
            "/api/commands/batch",
            params={"async": "true"},
            json={"actions": [{"type": "create_box",
                               "params": {"name": f"P{i}", "width": 10, "depth": 10,
                                          "height": 10, "position": {"x": i * 50}}}]},
        ).json()["job_id"]
        for i in range(3)
    ]
    for jid in ids:
        assert _await_job(client, jid)["estado"] == "ok"
    assert [f.name for f in api.DOC.scene.values()] == ["P0", "P1", "P2"]


# ------------------------------------------------------------------ 4. contrato diferido
def test_deferred_contract_error_leaves_doc_intact():
    """Un contrato incumplido dentro de un job se ve IGUAL que el 400 de hoy, solo que
    diferido: estado=error + http_status 400 y el documento BIT-IDÉNTICO al previo."""
    api.DOC = Document("jobs-contract-fail")
    client = TestClient(api.app)
    client.post("/api/commands", json={
        "type": "create_box", "params": {"name": "C", "width": 50, "depth": 50, "height": 50}})
    commands_before = [c["id"] for c in api.DOC.commands]
    undo_before = len(api.DOC._undo)

    r = client.post("/api/commands/batch", params={"async": "true"}, json={
        "actions": _boxes(),
        "expect": [{"tipo": "distancia", "a": "$1", "b": "$2", "max": 10}],  # 150 > 10 → falla
    })
    job = _await_job(client, r.json()["job_id"])
    assert job["estado"] == "error"
    assert job["http_status"] == 400
    assert "Contrato incumplido" in job["error"] and "medido 150" in job["error"]
    assert job["resultado"] is None
    # el lote entero se revirtió: ni escombro ni entrada de undo fantasma
    assert [c["id"] for c in api.DOC.commands] == commands_before
    assert len(api.DOC.scene) == 1
    assert len(api.DOC._undo) == undo_before


def test_command_error_in_job_is_400():
    api.DOC = Document("jobs-cmderr")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", params={"async": "true"}, json={
        "actions": [{"type": "fillet", "params": {"feature_id": "noexiste", "radius": 2}}]})
    job = _await_job(client, r.json()["job_id"])
    assert job["estado"] == "error" and job["http_status"] == 400


def test_unexpected_error_is_500_and_worker_survives():
    """Una excepción inesperada viaja al job (500 + repr) y NO mata al worker."""
    store = JobStore()
    boom = store.submit("t", lambda: (_ for _ in ()).throw(ValueError("boom")))
    job = store.get(boom, wait_s=10)
    assert job["estado"] == "error" and job["http_status"] == 500
    assert "boom" in job["error"]
    ok = store.submit("t", lambda: {"vivo": True})  # el worker sigue atendiendo
    assert store.get(ok, wait_s=10)["resultado"] == {"vivo": True}


# ------------------------------------------------------------- 4b. carrera de proyecto
def test_queued_job_rejects_project_switch():
    """Un job ENCOLADO no puede mutar el proyecto EQUIVOCADO (auditoría V6.5e): si el
    proyecto activo cambió entre el submit y la ejecución (open_project ganó la carrera
    a un lote esperando detrás de otro), el job muere en 409 y el proyecto nuevo queda
    INTACTO. En el mundo sync esto no podía pasar (la request serializaba tras
    STATE_LOCK); la cola le abría una puerta lateral."""
    api.DOC = Document("proyecto-A")
    old_pid = api.PROJECT_ID
    client = TestClient(api.app)
    gate = threading.Event()
    api.JOBS.submit("bloqueo", lambda: (gate.wait(10), {})[1])  # ocupa el worker

    r = client.post("/api/commands/batch", params={"async": "true"},
                    json={"actions": _boxes()})
    assert r.status_code == 202
    jid = r.json()["job_id"]

    # el usuario abre OTRO proyecto mientras el lote espera en cola (swap como el de
    # open_project: DOC y PROJECT_ID cambian juntos)
    api.DOC = Document("proyecto-B")
    api.PROJECT_ID = (old_pid or 0) + 999
    gate.set()
    try:
        job = _await_job(client, jid)
    finally:
        api.PROJECT_ID = old_pid

    assert job["estado"] == "error"
    assert job["http_status"] == 409
    assert "proyecto activo cambió" in job["error"]
    assert len(api.DOC.scene) == 0  # proyecto-B quedó intacto: el lote de A NO aplicó


def test_queued_job_applies_when_project_unchanged():
    """La guardia no puede dar falsos positivos: sin switch de por medio, el job
    encolado aplica normal (mismo PROJECT_ID al encolar y al ejecutar)."""
    api.DOC = Document("proyecto-quieto")
    client = TestClient(api.app)
    gate = threading.Event()
    api.JOBS.submit("bloqueo", lambda: (gate.wait(10), {})[1])
    r = client.post("/api/commands/batch", params={"async": "true"},
                    json={"actions": _boxes()})
    gate.set()
    job = _await_job(client, r.json()["job_id"])
    assert job["estado"] == "ok"
    assert len(api.DOC.scene) == 2


# ------------------------------------------------------------------ 5. retención / 404
def test_eviction_keeps_last_terminated():
    store = JobStore(retention=3)
    ids = [store.submit("t", lambda: {"n": 1}) for _ in range(5)]
    for jid in ids:
        store.get(jid, wait_s=10)
    assert [store.get(j) for j in ids[:2]] == [None, None]  # los 2 más viejos, desalojados
    assert all(store.get(j)["estado"] == "ok" for j in ids[2:])
    assert len(store.briefs()) == 3


def test_eviction_never_removes_a_live_job():
    """Un job vivo (encolado/corriendo) jamás se desaloja aunque la retención se rebase:
    su dueño todavía espera el resultado. Solo los TERMINADOS entran a la FIFO."""
    store = JobStore(retention=1)
    gate = threading.Event()
    a = store.submit("t", lambda: {"n": "a"})
    b = store.submit("t", lambda: (gate.wait(10), {"n": "b"})[1])  # corre y bloquea la cola
    c = store.submit("t", lambda: {"n": "c"})                      # encolado detrás de b
    assert store.get(a, wait_s=10)["estado"] == "ok"
    # con 3 jobs y retención 1, los VIVOS siguen consultables
    assert store.get(b)["estado"] in ("encolado", "corriendo")
    assert store.get(c)["estado"] == "encolado"

    gate.set()
    # 'c' sobrevivió a las rondas de eviction que corrieron mientras estaba encolado
    assert store.get(c, wait_s=10)["estado"] == "ok"
    assert store.get(a) is None  # el terminado más viejo SÍ se desalojó (la FIFO corrió)
    assert len(store.briefs()) == 1


def test_unknown_job_404_is_honest():
    """El 404 no puede mentir: tras un reload el lote PUDO haber aplicado."""
    client = TestClient(api.app)
    r = client.get("/api/jobs/nohaytal")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert "reinició" in detail  # el servidor pudo reiniciarse
    assert "PUDO haber aplicado" in detail and "autosave" in detail
    assert "verifícalo con get_scene" in detail
    assert "NUNCA reintentes el lote a ciegas" in detail


def test_briefs_omit_the_payload():
    api.DOC = Document("jobs-briefs")
    client = TestClient(api.app)
    r = client.post("/api/commands/batch", params={"async": "true"}, json={"actions": _boxes()})
    jid = r.json()["job_id"]
    _await_job(client, jid)
    jobs = client.get("/api/jobs").json()["jobs"]
    entry = next(j for j in jobs if j["id"] == jid)
    assert "resultado" not in entry  # el payload de escena no se vuelca en la telemetría
    assert entry["tipo"] == "run_batch" and entry["estado"] == "ok"


# ------------------------------------------------------------------ 6. worker lento
def test_slow_job_reports_running_then_ok():
    store = JobStore()
    jid = store.submit("t", lambda: (time.sleep(0.3), {"ok": 1})[1])
    assert store.get(jid)["estado"] in ("encolado", "corriendo")  # sin esperar: aún no está
    assert store.get(jid, wait_s=10)["estado"] == "ok"


def test_result_is_cached_so_asking_again_is_safe():
    """Re-preguntar por un job terminado es SIEMPRE seguro: no re-ejecuta nada."""
    runs = []
    store = JobStore()
    jid = store.submit("t", lambda: (runs.append(1), {"n": len(runs)})[1])
    first = store.get(jid, wait_s=10)
    second = store.get(jid, wait_s=10)
    assert first["resultado"] == second["resultado"] == {"n": 1}
    assert len(runs) == 1


# ------------------------------------------------------------------ 7. cliente fino
pytest.importorskip("mcp")  # el cliente MCP necesita el paquete mcp


class _FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def _fake_api(monkeypatch, polls):
    """Monkeypatchea `_api` del cliente fino: 202 al enviar + `polls` en cada GET."""
    import apolo.mcp_server as mcp_server

    calls = []
    seq = list(polls)

    def fake(method, path, **kwargs):
        calls.append((method, path, kwargs))
        if path.startswith("/api/jobs/"):
            return _FakeResponse(200, seq.pop(0) if len(seq) > 1 else seq[0])
        return _FakeResponse(202, {"job_id": "j1", "estado": "encolado"})

    monkeypatch.setattr(mcp_server, "_api", fake)
    return calls


def test_client_fast_job_returns_todays_payload(monkeypatch):
    import apolo.mcp_server as mcp_server

    calls = _fake_api(monkeypatch, [{"estado": "ok", "resultado": {"features": []}}])
    payload, job_id = mcp_server._submit_and_wait("POST", "/api/commands/batch", {"actions": []})
    assert job_id is None and payload == {"features": []}
    assert calls[0][2]["params"]["async"] == "true"  # el camino seguro NO es opt-in


def test_client_slow_job_returns_receipt(monkeypatch):
    import apolo.mcp_server as mcp_server

    monkeypatch.setattr(mcp_server, "APOLO_MCP_WAIT_S", 0.3)
    _fake_api(monkeypatch, [{"estado": "corriendo"}])
    payload, job_id = mcp_server._submit_and_wait("POST", "/api/commands/batch", {"actions": []})
    assert payload is None and job_id == "j1"  # RECIBO, no error


def test_client_failed_job_raises_like_a_400(monkeypatch):
    import apolo.mcp_server as mcp_server

    _fake_api(monkeypatch, [{"estado": "error", "http_status": 400, "error": "Contrato incumplido"}])
    with pytest.raises(RuntimeError, match=r"Apolo rechazó la operación \(400\): Contrato"):
        mcp_server._submit_and_wait("POST", "/api/commands/batch", {"actions": []})


def test_client_run_batch_returns_receipt_when_slow(monkeypatch):
    """La tool entera (no solo el helper): un lote lento devuelve RECIBO, nunca un error de
    timeout — es el modo de fallo que empujaba al agente a REST crudo."""
    import apolo.mcp_server as mcp_server

    monkeypatch.setattr(mcp_server, "APOLO_MCP_WAIT_S", 0.3)
    _fake_api(monkeypatch, [{"estado": "corriendo"}])
    body = json.loads(mcp_server.run_batch(actions=[]))
    assert body["job"] == "j1" and body["estado"] == "corriendo"
    assert "get_job('j1')" in body["seguir"]


def test_client_edit_batch_returns_receipt_when_slow(monkeypatch):
    import apolo.mcp_server as mcp_server

    monkeypatch.setattr(mcp_server, "APOLO_MCP_WAIT_S", 0.3)
    calls = _fake_api(monkeypatch, [{"estado": "corriendo"}])
    body = json.loads(mcp_server.edit_batch(edits=[]))
    assert body["job"] == "j1"
    assert calls[0][2]["params"] == {"merge": "true", "async": "true"}  # merge NO se pierde


def test_client_get_job_tool_returns_todays_brief(monkeypatch):
    """get_job devuelve lo MISMO que habría devuelto el lote (sólidos + contrato)."""
    import apolo.mcp_server as mcp_server

    resultado = {
        "document": {"name": "t", "variables": [], "can_undo": True, "can_redo": False},
        "features": [{"id": "c1", "name": "A", "visible": True, "bbox": {}, "volume_mm3": 1.0,
                      "component": None, "command_id": "c1"}],
        "total_features": 1,
        "affected_command_ids": ["c1"],
        "contrato": {"n_aserciones": 1, "ok": True},
    }
    _fake_api(monkeypatch, [{"estado": "ok", "resultado": resultado}])
    body = json.loads(mcp_server.get_job("j1"))
    assert body["job"] == "j1"
    assert [s["id"] for s in body["solidos"]] == ["c1"]
    assert body["contrato"] == {"n_aserciones": 1, "ok": True}


def test_client_get_job_tool_propagates_failure(monkeypatch):
    import apolo.mcp_server as mcp_server

    _fake_api(monkeypatch, [{"estado": "error", "http_status": 400, "error": "Contrato incumplido"}])
    with pytest.raises(RuntimeError, match=r"\(400\): Contrato incumplido"):
        mcp_server.get_job("j1")


def test_client_get_job_tool_receipt_while_running(monkeypatch):
    import apolo.mcp_server as mcp_server

    _fake_api(monkeypatch, [{"estado": "corriendo"}])
    body = json.loads(mcp_server.get_job("j1"))
    assert body == {"job": "j1", "estado": "corriendo",
                    "seguir": "llama get_job('j1') para recoger el resultado"}
