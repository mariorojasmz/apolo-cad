"""El JobStore avisa cuando un job corre y cuando termina (D10 / F5a de `docs/plans/modo-visor.md`).

La UI quiere mostrar «el agente está trabajando…» mientras un lote del MCP corre en el worker.
`JobStore` recibe un callback opcional (`al_cambiar_estado`) que llama con
`{"job_id", "estado": "corriendo" | "ok" | "error"}`; la API lo cablea a
`WS.notify_changed({"type": "job", …})`. Reglas que se fijan aquí:
  - el callback corre SIN el `_cv` del store (lock hoja: nunca código externo con él sostenido);
  - un callback que lanza no mata el worker ni cambia el resultado del job;
  - sin callback, todo como antes.
"""

from __future__ import annotations

import threading

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.api.jobs import JobStore
from apolo.doc.document import Document

_ESPERA_S = 10.0


class _Espia:
    """Callback que anota cada aviso y avisa cuando llega el estado terminal de un job."""

    def __init__(self, al_avisar=None) -> None:
        self.avisos: list[dict] = []
        self.terminal = threading.Event()
        self._al_avisar = al_avisar

    def __call__(self, cambio: dict) -> None:
        self.avisos.append(dict(cambio))
        if self._al_avisar is not None:
            self._al_avisar(cambio)
        if cambio["estado"] in ("ok", "error"):
            self.terminal.set()


def test_avisa_corriendo_y_luego_ok():
    espia = _Espia()
    store = JobStore(al_cambiar_estado=espia)
    jid = store.submit("t", lambda: {"ok": 1})
    assert espia.terminal.wait(_ESPERA_S)
    assert espia.avisos == [{"job_id": jid, "estado": "corriendo"},
                            {"job_id": jid, "estado": "ok"}]
    assert store.get(jid)["resultado"] == {"ok": 1}


def test_avisa_error_cuando_el_closure_lanza():
    espia = _Espia()
    store = JobStore(al_cambiar_estado=espia)
    jid = store.submit("t", lambda: (_ for _ in ()).throw(ValueError("boom")))
    assert espia.terminal.wait(_ESPERA_S)
    assert espia.avisos == [{"job_id": jid, "estado": "corriendo"},
                            {"job_id": jid, "estado": "error"}]
    job = store.get(jid)
    assert job["estado"] == "error" and job["http_status"] == 500 and "boom" in job["error"]


def test_el_aviso_se_llama_sin_el_lock_del_store():
    """Desde OTRO hilo (el `_cv` es reentrante: el mismo hilo entraría aunque lo tuviera),
    `get` responde al instante dentro del callback. Si el aviso corriera con `_cv`
    sostenido, ese hilo se quedaría bloqueado hasta el timeout. Y el job ya está escrito:
    lo que lee el hilo es el estado que se avisa."""
    store: JobStore
    vistos: list[tuple[str, str | None, bool]] = []

    def leer_desde_otro_hilo(cambio: dict) -> None:
        leido: list[dict | None] = []
        hilo = threading.Thread(target=lambda: leido.append(store.get(cambio["job_id"])))
        hilo.start()
        hilo.join(timeout=2.0)
        estado = leido[0]["estado"] if leido and leido[0] else None
        vistos.append((cambio["estado"], estado, hilo.is_alive()))

    espia = _Espia(al_avisar=leer_desde_otro_hilo)
    store = JobStore(al_cambiar_estado=espia)
    store.submit("t", lambda: {"ok": 1})
    assert espia.terminal.wait(_ESPERA_S)
    # (estado avisado, estado leído desde otro hilo, ¿el hilo quedó bloqueado?)
    assert vistos == [("corriendo", "corriendo", False), ("ok", "ok", False)]


@pytest.mark.parametrize("excepcion", [RuntimeError, SystemExit])
def test_un_aviso_que_lanza_no_mata_el_worker_ni_cambia_el_resultado(excepcion):
    llamadas: list[str] = []

    def roto(cambio: dict) -> None:
        llamadas.append(cambio["estado"])
        raise excepcion("aviso roto")

    store = JobStore(al_cambiar_estado=roto)
    primero = store.submit("t", lambda: {"n": 1})
    segundo = store.submit("t", lambda: {"n": 2})  # corre sólo si el worker sobrevivió
    assert store.get(primero, wait_s=_ESPERA_S)["resultado"] == {"n": 1}
    job = store.get(segundo, wait_s=_ESPERA_S)
    assert job["estado"] == "ok" and job["resultado"] == {"n": 2}
    assert llamadas[:3] == ["corriendo", "ok", "corriendo"]


def test_sin_aviso_todo_funciona_como_antes():
    store = JobStore()
    ok = store.submit("t", lambda: {"n": 1})
    malo = store.submit("t", lambda: (_ for _ in ()).throw(ValueError("x")))
    assert store.get(ok, wait_s=_ESPERA_S)["estado"] == "ok"
    assert store.get(malo, wait_s=_ESPERA_S)["estado"] == "error"


# ------------------------------------------------------------- cableado de la API
def _espiar_ws(monkeypatch, job_id_de):
    """Anota lo que la API manda por WS; `terminal` se prende con el fin del job vigilado."""
    mensajes: list[dict | None] = []
    terminal = threading.Event()

    def notify_changed(msg=None):
        mensajes.append(msg)
        if (msg and msg.get("type") == "job" and msg.get("job_id") == job_id_de()
                and msg.get("estado") in ("ok", "error")):
            terminal.set()

    monkeypatch.setattr(api.WS, "notify_changed", notify_changed)
    return mensajes, terminal


def test_la_api_avisa_el_job_por_websocket(monkeypatch):
    vigilado: list[str] = []
    mensajes, terminal = _espiar_ws(monkeypatch, lambda: vigilado[0] if vigilado else None)
    gate = threading.Event()
    vigilado.append(api.JOBS.submit("t", lambda: (gate.wait(_ESPERA_S), {"ok": 1})[1]))
    gate.set()
    assert terminal.wait(_ESPERA_S)
    jid = vigilado[0]
    propios = [m for m in mensajes if m and m.get("job_id") == jid]
    assert propios == [{"type": "job", "job_id": jid, "estado": "corriendo"},
                       {"type": "job", "job_id": jid, "estado": "ok"}]


def test_un_lote_asincrono_avisa_corriendo_cambio_y_fin_en_orden(monkeypatch):
    """El lote del MCP (`?async=true`): corriendo → «el documento cambió» → ok. El fin llega
    DESPUÉS del aviso de escena, así la UI cierra «trabajando…» con el modelo ya nuevo."""
    api.DOC = Document("jobs-aviso")
    vigilado: list[str] = []
    mensajes, terminal = _espiar_ws(monkeypatch, lambda: vigilado[0] if vigilado else None)
    r = TestClient(api.app).post(
        "/api/commands/batch", params={"async": "true"},
        json={"actions": [{"type": "create_box",
                           "params": {"name": "A", "width": 50, "depth": 50, "height": 50}}]},
    )
    assert r.status_code == 202, r.text
    vigilado.append(r.json()["job_id"])
    if any(m and m.get("job_id") == vigilado[0] and m.get("estado") in ("ok", "error")
           for m in mensajes):
        terminal.set()  # terminó antes de que supiéramos su id
    assert terminal.wait(_ESPERA_S)
    jid = vigilado[0]
    secuencia = [m["estado"] if m and m.get("type") == "job" else "documento"
                 for m in mensajes if m is None or m.get("job_id") == jid]
    assert secuencia == ["corriendo", "documento", "ok"]
    assert len(api.DOC.scene) == 1
