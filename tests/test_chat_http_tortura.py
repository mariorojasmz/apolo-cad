"""Tortura del chat HTTP contra uvicorn REAL (plan chat-cliente-igual F5a, D4b y riesgos).

El chat ocupa un hilo del threadpool de la API mientras espera al modelo y a sus propias
peticiones, que necesitan OTRO hilo del mismo servidor. Con TestClient eso no se ve (cada
petición anidada trae su propio bucle); aquí corre un uvicorn de verdad, en un puerto libre
que elige el sistema (nunca :8000/:8001/:8012), sin lifespan (sin SQLite) y con el cliente de
Anthropic FALSO de `test_chat_http.py`: nunca se llama a la API de Anthropic.

- varios chats a la vez (el tope por defecto) que leen, ensayan y mutan contra el mismo
  servidor: sin deadlock, el servidor sigue atendiendo a otros y los de más reciben 429;
- `APOLO_CHAT_MAX=1` → el segundo recibe 429 y, al terminar el primero, el lugar se libera;
- el cliente corta el stream a mitad del turno → el turno se detiene y el lugar se libera.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import anthropic
import httpx
import pytest

pytest.importorskip("mcp")
uvicorn = pytest.importorskip("uvicorn")

import apolo.api.main as api  # noqa: E402
from apolo import mcp_server  # noqa: E402
from apolo.agent import chat  # noqa: E402
from apolo.doc import Document  # noqa: E402

pytestmark = pytest.mark.torture

_spec = importlib.util.spec_from_file_location(
    "_chat_http_base", Path(__file__).with_name("test_chat_http.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)
Modelo, _resp, _tool, _sse, _para_la_ui, CAJA = (
    base.Modelo, base._resp, base._tool, base._sse, base._para_la_ui, base.CAJA)

ESPERA = 120  # s: más que esto es un deadlock


@contextmanager
def _uvicorn():
    """La API en un hilo, sobre un socket ya abierto en un puerto libre (sin carrera)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    puerto = sock.getsockname()[1]
    assert puerto >= 8020, puerto  # lejos de :8000 (Mario), :8001 (Docker) y :8012
    servidor = uvicorn.Server(uvicorn.Config(api.app, lifespan="off", log_level="warning",
                                             log_config=None))  # sin tocar el logging del proceso
    hilo = threading.Thread(target=servidor.run, kwargs={"sockets": [sock]}, daemon=True)
    hilo.start()
    limite = time.monotonic() + 30
    while not servidor.started:
        assert hilo.is_alive() and time.monotonic() < limite, "uvicorn no arrancó"
        time.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{puerto}"
    finally:
        servidor.should_exit = True
        hilo.join(30)
        sock.close()


@pytest.fixture
def api_real(monkeypatch):
    doc = Document("tortura-chat")
    doc.execute("create_box", {"name": "Base", "width": 100, "depth": 100, "height": 20})
    monkeypatch.setattr(api, "DOC", doc)
    monkeypatch.setattr(api._autosave_sched, "schedule", lambda: None)
    monkeypatch.setattr(mcp_server, "APOLO_URL", "http://127.0.0.1:9")  # nada fuera del destino
    for var in ("APOLO_CHAT_MAX", "APOLO_URL_INTERNA"):
        monkeypatch.delenv(var, raising=False)
    with _uvicorn() as url:
        yield doc, url
    assert chat.CUPO.activos == 0


class Retenido(Modelo):
    """El modelo falso que, en su primera llamada, avisa que entró y espera la `puerta`."""

    def __init__(self, respuestas, entraron: list, puerta: threading.Event):
        super().__init__(respuestas)
        self._entraron, self._puerta = entraron, puerta

    def _abrir(self, **kw):
        if not self.llamadas:
            self._entraron.append(1)
            assert self._puerta.wait(ESPERA), "nadie abrió la puerta"
        return super()._abrir(**kw)


def _guion(i: int) -> list:
    """Lee, ensaya, muta por el embudo y por el job, y termina: todo por HTTP."""
    caja = {**CAJA, "params": {**CAJA["params"], "name": f"Caja {i}"}}
    return [
        _resp("tool_use", [_tool(f"{i}a", "get_scene", {"summary": True}),
                           _tool(f"{i}b", "get_command_schemas", {"command_type": "create_box"}),
                           _tool(f"{i}c", "preview", {"actions": [caja], "data": True})]),
        _resp("tool_use", [_tool(f"{i}d", "run_command", caja)]),
        _resp("tool_use", [_tool(f"{i}e", "run_batch", {"actions": [caja, caja]})]),
        _resp("end_turn", textos=[f"listo {i}"]),
    ]


def _postear(url: str, auto: bool = True) -> httpx.Response:
    return httpx.post(f"{url}/api/agent/chat", timeout=ESPERA,
                      json={"messages": [{"role": "user", "content": "hola"}], "auto": auto})


def _esperar(condicion, que: str, segundos: float = 30) -> None:
    limite = time.monotonic() + segundos
    while not condicion():
        assert time.monotonic() < limite, f"no pasó: {que}"
        time.sleep(0.02)


def test_varios_chats_a_la_vez_sin_deadlock_y_los_de_mas_reciben_429(api_real, monkeypatch):
    doc, url = api_real
    n = chat.CHAT_MAX
    entraron, puerta, numeros = [], threading.Event(), iter(range(n))
    monkeypatch.setattr(anthropic, "Anthropic",
                        lambda: Retenido(_guion(next(numeros)), entraron, puerta))
    respuestas: list = [None] * n

    def correr(k):
        respuestas[k] = _postear(url)

    hilos = [threading.Thread(target=correr, args=(k,)) for k in range(n)]
    for h in hilos:
        h.start()
    _esperar(lambda: len(entraron) == n, "los chats llegaran al modelo")
    # los n ocupan su hilo a la vez: los de más no entran y la API sigue atendiendo
    for _ in range(3):
        r = _postear(url)
        assert r.status_code == 429 and r.json()["detail"] == chat.LLENO
    t0 = time.monotonic()
    assert httpx.get(f"{url}/api/scene/summary", timeout=10).status_code == 200
    assert time.monotonic() - t0 < 10, "el threadpool quedó sin hilos"
    puerta.set()
    for h in hilos:
        h.join(ESPERA)
    assert not any(h.is_alive() for h in hilos), "deadlock: un chat no terminó"
    for r in respuestas:
        assert r.status_code == 200
        evs = _sse(r.text)
        _para_la_ui(evs)
        assert not [e for e in evs if e["type"] in ("error", "aviso")], evs
        assert sum(e["type"] == "tool" for e in evs) == 5
    assert len(doc.scene) == 1 + 3 * n  # cada chat: una caja por el embudo y dos por el job
    _esperar(lambda: chat.CUPO.activos == 0, "se liberara el cupo")


def test_con_apolo_chat_max_1_el_segundo_recibe_429(api_real, monkeypatch):
    _, url = api_real
    monkeypatch.setenv("APOLO_CHAT_MAX", "1")
    entraron, puerta = [], threading.Event()
    monkeypatch.setattr(anthropic, "Anthropic", lambda: Retenido(
        [_resp("end_turn", textos=["primero"])], entraron, puerta))
    primero: list = []
    hilo = threading.Thread(target=lambda: primero.append(_postear(url, auto=False)))
    hilo.start()
    _esperar(lambda: entraron, "el primero llegara al modelo")

    segundo = _postear(url)
    assert segundo.status_code == 429 and segundo.json()["detail"] == chat.LLENO

    puerta.set()
    hilo.join(ESPERA)
    assert primero[0].status_code == 200 and _sse(primero[0].text)[-1]["type"] == "done"
    _esperar(lambda: chat.CUPO.activos == 0, "se liberara el cupo")
    monkeypatch.setattr(anthropic, "Anthropic", lambda: Modelo([_resp("end_turn", textos=["ok"])]))
    assert _postear(url).status_code == 200  # el lugar volvió


class _Cortado(Modelo):
    """Emite «uno», espera la `puerta` y recién entonces «dos»: el cliente corta entre medio."""

    def __init__(self, puerta: threading.Event):
        super().__init__([_resp("tool_use", [_tool("t1", "get_scene", {"summary": True})]),
                          _resp("end_turn", textos=["fin"])])
        self._puerta = puerta

    def _abrir(self, **kw):
        stream = super()._abrir(**kw)
        if len(self.llamadas) == 1:
            uno, dos = _resp("end_turn", textos=["uno", "dos"])[1]

            def deltas():
                yield uno
                assert self._puerta.wait(ESPERA)
                yield dos

            stream._deltas = deltas()  # `_Stream.__iter__` itera esto
        return stream


def test_el_cliente_corta_y_el_turno_se_detiene_liberando_el_cupo(api_real, monkeypatch):
    _, url = api_real
    puerta = threading.Event()
    falso = _Cortado(puerta)
    monkeypatch.setattr(anthropic, "Anthropic", lambda: falso)
    with httpx.Client(timeout=ESPERA) as cliente, cliente.stream(
            "POST", f"{url}/api/agent/chat",
            json={"messages": [{"role": "user", "content": "hola"}], "auto": False}) as r:
        primera = next(l for l in r.iter_lines() if l.startswith("data: "))
    assert json.loads(primera[len("data: "):]) == {"type": "text", "text": "uno"}
    assert chat.CUPO.activos == 1
    time.sleep(1)  # que uvicorn vea la desconexión antes de soltar al modelo
    puerta.set()
    _esperar(lambda: chat.CUPO.activos == 0, "el corte liberara el cupo")
    assert len(falso.llamadas) == 1, "el turno siguió después del corte"
