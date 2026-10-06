"""El chat de la app como cliente HTTP de la API (plan chat-cliente-igual F5a, D2–D8).

Todo contra la API REAL (TestClient prestado sin entrar: sin lifespan ni SQLite) y un cliente
de Anthropic FALSO con respuestas guionadas: nunca se llama a la API de Anthropic. Las fronteras
que se leen del código (capas D4, cabecera, URL loopback, textos) viven en
`test_chat_http_capas.py`; la tortura con uvicorn real (varios chats a la vez, cupo, corte del
cliente), en `test_chat_http_tortura.py`.
"""

from __future__ import annotations

import asyncio
import gc
import io
import json
import re
import zipfile
from pathlib import Path
from types import SimpleNamespace as NS

import anthropic
import httpx
import pytest

pytest.importorskip("mcp")  # las tools del chat son las del MCP

from fastapi.testclient import TestClient  # noqa: E402

import apolo.api.main as api  # noqa: E402
from apolo import mcp_server  # noqa: E402
from apolo.agent import chat, eventos, herramientas  # noqa: E402
from apolo.api import guardia_documento  # noqa: E402
from apolo.api.ws import WS  # noqa: E402
from apolo.doc import Document  # noqa: E402
from apolo.state import STATE_LOCK  # noqa: E402
from apolo.tools.destino import Destino  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
CAJA = {"type": "create_box", "params": {"name": "Caja", "width": 50, "depth": 40, "height": 30},
        "reason": "una caja de prueba"}


# --------------------------------------------------------- el modelo falso
def _tool(id_, nombre, entrada=None):
    return NS(type="tool_use", id=id_, name=nombre, input=entrada or {})


def _resp(stop, contenido=(), textos=()):
    uso = NS(input_tokens=10, output_tokens=5, cache_read_input_tokens=0,
             cache_creation_input_tokens=0)
    deltas = [NS(type="content_block_delta", index=0, delta=NS(type="text_delta", text=t))
              for t in textos]
    return NS(stop_reason=stop, content=list(contenido), usage=uso, stop_details=None), deltas


class _Stream:
    def __init__(self, mensaje, deltas):
        self._mensaje, self._deltas = mensaje, deltas

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._deltas)

    def get_final_message(self):
        return self._mensaje


class Modelo:
    """`messages.stream` sin red: guarda los kwargs de cada llamada (los bytes que mandaría el
    SDK) y si el hilo que llama tenía `STATE_LOCK`."""

    def __init__(self, respuestas):
        self.api_key, self.auth_token, self.credentials = "falsa", None, None
        self._respuestas = list(respuestas)
        self.llamadas: list[str] = []
        self.con_lock: list[bool] = []
        self.messages = NS(stream=self._abrir)
        self.beta = NS(messages=NS(stream=self._abrir))

    def _abrir(self, **kw):
        self.con_lock.append(STATE_LOCK._is_owned())
        self.llamadas.append(json.dumps(kw, default=vars, ensure_ascii=False))
        return _Stream(*self._respuestas.pop(0))

    def kw(self, i: int) -> dict:
        return json.loads(self.llamadas[i])


@pytest.fixture(autouse=True)
def _sin_fugas_del_cupo():
    """Un turno que no soltó su lugar es un bug (y dejaría en 429 a los tests siguientes)."""
    yield
    fugas = chat.CUPO.activos
    chat.CUPO._activos = 0
    assert fugas == 0, f"{fugas} turno(s) del chat sin soltar el cupo"


# ------------------------------------------------------ la API real por HTTP
class _SinLifespan:
    """Presta un TestClient sin entrar (entrar correría el lifespan: la SQLite real)."""

    def __init__(self, cliente):
        self._cliente = cliente

    def __enter__(self):
        return self._cliente

    def __exit__(self, *exc):
        return False


@pytest.fixture
def mundo(monkeypatch):
    """Documento con una pieza, la API real como destino del chat (cada petición anotada:
    método, ruta, cabecera de la guardia, si el hilo tenía `STATE_LOCK`) y espías del
    autoguardado y del WebSocket. `mundo.al_pedir(req)` corre antes de cada petición."""
    doc = Document("chat-http")
    doc.execute("create_box", {"name": "Base", "width": 100, "depth": 100, "height": 20})
    monkeypatch.setattr(api, "DOC", doc)
    monkeypatch.setattr(mcp_server, "APOLO_URL", "http://127.0.0.1:9")  # nada se escapa
    m = NS(doc=doc, pedidos=[], bases=[], guardados=[], avisos=[], jobs=[],
           al_pedir=lambda req: None)
    monkeypatch.setattr(api._autosave_sched, "schedule", lambda: m.guardados.append(1))

    def avisar(msg=None):  # `avisos` = «el documento cambió»; el estado de un job va aparte
        (m.jobs if msg and msg.get("type") == "job" else m.avisos).append(msg)

    monkeypatch.setattr(WS, "notify_changed", avisar)

    def anotar(req: httpx.Request) -> None:
        m.al_pedir(req)
        m.pedidos.append((req.method, req.url.path, req.headers.get(chat.CABECERA),
                          STATE_LOCK._is_owned()))

    def conectar(base_url, cabeceras=None):
        m.bases.append(base_url)
        cliente = TestClient(api.app, headers=dict(cabeceras or {}), raise_server_exceptions=False)
        cliente.event_hooks = {"request": [anotar]}
        return Destino(base_url, lambda: _SinLifespan(cliente))

    monkeypatch.setattr(chat, "conectar", conectar)
    m.token = lambda: guardia_documento.token(api.DOC)
    return m


def _turno(m, respuestas, modo="propuesta", texto="hola"):
    """Corre un turno a nivel de `chat.turno` (sin endpoint): eventos, modelo y conversación."""
    modelo_falso = Modelo(respuestas)
    convo = chat.preparar([{"role": "user", "content": texto}], modo)
    token = m.token()
    destino = chat.conectar("http://chat.test", {chat.CABECERA: token})
    evs = list(chat.turno(convo, modo, destino, token, cliente=modelo_falso))
    return evs, modelo_falso, convo


def _huella(doc: Document):
    with zipfile.ZipFile(io.BytesIO(doc.to_apolo_bytes())) as z:
        archivos = {n: z.read(n) for n in z.namelist()}
    return archivos, sorted(f.id for f in doc.scene.values()), len(doc._undo), len(doc._redo)


# -------------------------------------------- lo que la UI entiende (sse.ts)
def _casos_de_la_ui() -> set[str]:
    fuente = (RAIZ / "ui" / "src" / "chat" / "sse.ts").read_text(encoding="utf-8")
    cuerpo = fuente[fuente.index("export function validar"):fuente.index("export function crearLectorSse")]
    return set(re.findall(r'case "(\w+)":', cuerpo))


_CAMPOS_UI = {"text": {"text": str}, "progreso": {"text": str}, "tool": {"name": str, "etiqueta": str},
              "actions": {"actions": list, "executed": bool}, "aviso": {"mensaje": str},
              "error": {"message": str}, "done": {"uso": dict}}


def _para_la_ui(evs: list[dict]) -> None:
    """Cada evento es de un tipo que `validar()` conoce y trae sus campos; `done`, al final."""
    for ev in evs:
        assert ev["type"] in _CAMPOS_UI, ev
        for campo, tipo in _CAMPOS_UI[ev["type"]].items():
            assert isinstance(ev.get(campo), tipo), (campo, ev)
        if ev["type"] == "tool":
            assert ev["etiqueta"].strip()
        if ev["type"] == "actions":
            assert all({"type", "params", "reason"} <= set(a) for a in ev["actions"])
    assert evs[-1]["type"] == "done" and [e["type"] for e in evs].count("done") == 1


def _sse(texto: str) -> list[dict]:
    return [json.loads(b[len("data: "):]) for b in texto.split("\n\n") if b.startswith("data: ")]


def test_los_tipos_de_evento_son_los_que_la_ui_entiende():
    assert set(eventos.TIPOS) == _casos_de_la_ui() == set(_CAMPOS_UI)
    linea = eventos.sse({"type": "text", "text": "dos\nlíneas"})
    assert linea.startswith("data: ") and linea.endswith("\n\n") and linea.count("\n") == 2
    assert _sse(linea) == [{"type": "text", "text": "dos\nlíneas"}]
    assert eventos.tool("get_scene") == {"type": "tool", "name": "get_scene",
                                         "etiqueta": "Leyendo el modelo"}


# ------------------------------------------------------------ D6: el modo
def test_el_modo_va_en_el_ultimo_turno_y_el_historial_no_cambia():
    historial = [{"role": "user", "content": "hazme una mesa"},
                 {"role": "assistant", "content": "¿De qué largo?"},
                 {"role": "user", "content": "de 2 m"}]
    for modo in ("propuesta", "autonomo"):
        convo = chat.preparar(historial, modo)
        assert convo[:-1] == historial[:-1]  # lo anterior, byte a byte
        assert convo[-1] == {"role": "user", "content": [
            {"type": "text", "text": "de 2 m"}, {"type": "text", "text": chat.RECORDATORIO[modo]}]}
    assert "activó el modo auto" in chat.RECORDATORIO["autonomo"]  # lo que pide REGLAS_CHAT
    assert historial[-1] == {"role": "user", "content": "de 2 m"}  # no muta la entrada
    vacio = chat.preparar([{"role": "user", "content": "  "}], "propuesta")
    assert vacio[-1]["content"] == [{"type": "text", "text": chat.RECORDATORIO["propuesta"]}]
    sin_turno = chat.preparar([{"role": "assistant", "content": "hola"}], "autonomo")
    assert sin_turno[-1]["role"] == "user" and len(sin_turno) == 2


def test_mismos_bytes_de_tools_y_system_en_los_dos_modos(mundo):
    kws = {}
    for modo in ("propuesta", "autonomo"):
        _, falso, _ = _turno(mundo, [_resp("end_turn", textos=["listo"])], modo)
        kws[modo] = falso.kw(0)
    fijos = {modo: json.dumps({k: v for k, v in kw.items() if k != "messages"}, ensure_ascii=False)
             for modo, kw in kws.items()}
    assert fijos["propuesta"] == fijos["autonomo"]
    assert kws["propuesta"]["tools"] == herramientas.definiciones()
    assert kws["propuesta"]["system"][0]["text"] == chat.system_prompt_chat()
    # D8: sin los 53 schemas embebidos (el chat viejo mandaba 152 876 bytes de tools)
    assert len(json.dumps(kws["propuesta"]["tools"], ensure_ascii=False).encode()) < 60_000
    m_p, m_a = kws["propuesta"]["messages"], kws["autonomo"]["messages"]
    assert m_p[0]["content"][0] == m_a[0]["content"][0]  # sólo cambia el bloque del modo


# ------------------------------------------ toda tool_use con su tool_result
def test_cada_tool_use_recibe_su_tool_result_y_los_eventos_sirven_a_la_ui(mundo):
    evs, falso, convo = _turno(mundo, [
        _resp("tool_use", [_tool("a1", "get_scene", {"summary": True}),
                           _tool("a2", "run_command", CAJA),
                           _tool("a3", "no_existe"),
                           _tool("a4", "get_command_schemas", {"command_type": "create_box"})]),
        _resp("tool_use", [_tool("b1", "propose_commands", {"actions": [CAJA]})]),
    ])
    pedidos = [b for msg in convo if msg["role"] == "assistant" for b in msg["content"]
               if getattr(b, "type", None) == "tool_use"]
    resultados = [r for msg in convo if msg["role"] == "user" and isinstance(msg["content"], list)
                  for r in msg["content"] if r.get("type") == "tool_result"]
    assert [b.id for b in pedidos] == [r["tool_use_id"] for r in resultados] == [
        "a1", "a2", "a3", "a4", "b1"]
    errores = {r["tool_use_id"] for r in resultados if r.get("is_error")}
    assert errores == {"a2", "a3"}  # mutación en propuesta y tool desconocida
    assert len(falso.llamadas) == 2  # la propuesta cierra el turno
    _para_la_ui(evs)
    assert [e["name"] for e in evs if e["type"] == "tool"] == [
        "get_scene", "run_command", "no_existe", "get_command_schemas", "propose_commands"]
    (tarjetas,) = [e for e in evs if e["type"] == "actions"]
    assert tarjetas == {"type": "actions", "actions": [CAJA], "executed": False}


# --------------------------------------------- modo propuesta (D6) y D7
def test_en_propuesta_lo_que_muta_no_llega_a_la_api(mundo):
    antes = _huella(mundo.doc)
    evs, _, convo = _turno(mundo, [
        _resp("tool_use", [_tool("t1", "run_command", CAJA),
                           _tool("t2", "set_variable", {"name": "L", "expression": "100"}),
                           _tool("t3", "run_batch", {"actions": [CAJA]}),
                           _tool("t4", "undo")]),
        _resp("end_turn", textos=["no pude"]),
    ])
    resultados = convo[2]["content"]
    assert all(r["is_error"] and "Modo propuesta" in r["content"][0]["text"] for r in resultados)
    assert {p[0] for p in mundo.pedidos} == {"GET"}  # sólo el token de la guardia
    assert _huella(mundo.doc) == antes and mundo.guardados == [] and mundo.avisos == []
    _para_la_ui(evs)


def test_una_propuesta_se_ensaya_en_seco_antes_de_mostrarse(mundo):
    mala = {"type": "create_box", "params": {"ancho": 10}, "reason": "clave inventada"}
    evs, falso, convo = _turno(mundo, [
        _resp("tool_use", [_tool("t1", "propose_commands", {"actions": [mala]})]),
        _resp("tool_use", [_tool("t2", "propose_commands", {"actions": []})]),
        _resp("tool_use", [_tool("t3", "propose_commands", {"actions": [CAJA]})]),
    ])
    r1, r2, r3 = (convo[i]["content"][0] for i in (2, 4, 6))
    assert r1["is_error"] and "rechazó la operación (400)" in r1["content"][0]["text"]
    assert r2["is_error"] and "lista no vacía" in r2["content"][0]["text"]
    assert not r3.get("is_error") and "pendiente" in r3["content"][0]["text"]
    assert "fantasmas" in r3["content"][0]["text"]  # el ensayo vuelve al modelo
    ensayos = [p for p in mundo.pedidos if p[1] == "/api/commands/preview"]
    assert len(ensayos) == 2  # la lista vacía no llega a la API
    assert [e["actions"] for e in evs if e["type"] == "actions"] == [[CAJA]]
    assert len(falso.llamadas) == 3 and len(mundo.doc.scene) == 1  # nada se aplicó


def test_la_propuesta_usa_dollar_k_y_las_variables_del_mismo_lote(mundo):
    """Lo que validaba `validate_actions` del chat viejo: '$k' y una variable definida en el
    mismo lote pasan el ensayo (ahora el del servidor, el mismo que corre al aceptar)."""
    lote = [{"type": "set_variable", "params": {"name": "L", "expression": "200"}, "reason": "largo"},
            {**CAJA, "params": {**CAJA["params"], "width": "=L/2"}},
            {"type": "pattern_linear", "params": {"feature": "$2", "count": 3, "spacing": {"x": 150}},
             "reason": "copias"}]
    evs, _, convo = _turno(mundo, [_resp("tool_use", [_tool("t1", "propose_commands",
                                                            {"actions": lote})])])
    assert not convo[2]["content"][0].get("is_error"), convo[2]["content"][0]
    assert [e["actions"] for e in evs if e["type"] == "actions"] == [lote]
    assert len(mundo.doc.scene) == 1 and not mundo.doc.variables_resolved  # nada se aplicó


# ------------------------------------------------- modo auto por HTTP
def test_en_auto_se_aplica_por_http_y_la_ui_se_entera(mundo):
    token = mundo.token()
    evs, _, convo = _turno(mundo, [
        _resp("tool_use", [_tool("t1", "run_command", CAJA)]),
        _resp("tool_use", [_tool("t2", "run_batch", {"actions": [CAJA, CAJA]})]),
        _resp("end_turn", textos=["listo"]),
    ], modo="autonomo")
    assert len(mundo.doc.scene) == 4
    assert not any(r.get("is_error") for msg in convo[2::2] for r in msg["content"])
    mutaciones = [p for p in mundo.pedidos if p[0] == "POST"]
    assert [p[1] for p in mutaciones] == ["/api/commands", "/api/commands/batch"]
    assert all(p[2] == token for p in mutaciones)  # con la cabecera de la guardia
    assert mundo.guardados and len(mundo.avisos) == 2  # autoguardado y WebSocket → la UI refresca
    lotes = [e for e in evs if e["type"] == "actions"]
    assert [(len(e["actions"]), e["executed"]) for e in lotes] == [(1, True), (2, True)]
    _para_la_ui(evs)


def test_en_auto_anota_y_deshace_por_http(mundo):
    """Lo que el chat viejo hacía con `save_note` y `undo_last` (y sus ganchos de autoguardado
    y aviso) lo hacen ahora `add_agent_note` y `undo` contra la API, con la cabecera."""
    token = mundo.token()
    evs, _, convo = _turno(mundo, [
        _resp("tool_use", [_tool("t1", "run_command", CAJA),
                           _tool("t2", "add_agent_note", {"text": "  nota  "}),
                           _tool("t3", "undo")]),
        _resp("end_turn", textos=["listo"]),
    ], modo="autonomo")
    assert not any(r.get("is_error") for r in convo[2]["content"]), convo[2]["content"]
    assert len(mundo.doc.scene) == 1 and mundo.doc.agent_notes == ["nota"]  # creó, anotó, deshizo
    mutaciones = [p for p in mundo.pedidos if p[0] == "POST"]
    assert len(mutaciones) == 3 and all(p[2] == token for p in mutaciones)
    assert len(mundo.guardados) == 3  # cada mutación se autoguarda
    assert len(mundo.avisos) == 2  # el lote y el undo avisan; la nota no cambia la escena
    _para_la_ui(evs)


# ---------------------------------- proyecto cambiado a mitad del turno
@pytest.mark.parametrize("tool, entrada, ruta", [
    ("run_command", CAJA, "/api/commands"),                       # el embudo
    ("run_batch", {"actions": [CAJA]}, "/api/commands/batch"),    # el job
    ("add_agent_note", {"text": "nota"}, "/api/agent/notes"),     # fuera del embudo
])
def test_proyecto_cambiado_da_409_y_corta_el_turno_sin_aplicar(mundo, tool, entrada, ruta):
    viejo, nuevo = mundo.doc, Document("otro")
    huellas = _huella(viejo), _huella(nuevo)

    def abrir_otro(req):  # la persona abre otro proyecto justo antes de que llegue la mutación
        if req.method == "POST" and req.url.path == ruta:
            api.DOC = nuevo

    mundo.al_pedir = abrir_otro
    evs, falso, _ = _turno(mundo, [_resp("tool_use", [_tool("t1", tool, entrada)]),
                                   _resp("end_turn", textos=["no debería llegar"])],
                           modo="autonomo")
    assert [e["type"] for e in evs] == ["tool", "error", "done"]
    assert evs[1]["message"] == chat.PROYECTO_CAMBIO
    assert len(falso.llamadas) == 1  # ninguna vuelta más
    assert (_huella(viejo), _huella(nuevo)) == huellas  # ni el viejo ni el nuevo cambiaron
    assert mundo.guardados == [] and mundo.avisos == []


def test_proyecto_cambiado_entre_tandas_corta_antes_de_correrlas(mundo):
    nuevo = Document("otro")

    def abrir_otro(req):
        if req.url.path == "/api/scene/summary":
            api.DOC = nuevo

    mundo.al_pedir = abrir_otro
    evs, falso, _ = _turno(mundo, [
        _resp("tool_use", [_tool("t1", "get_scene", {"summary": True})]),
        _resp("tool_use", [_tool("t2", "run_command", CAJA)]),
    ], modo="autonomo")
    assert [e["type"] for e in evs] == ["tool", "error", "done"]
    assert evs[1]["message"] == chat.PROYECTO_CAMBIO
    assert not [p for p in mundo.pedidos if p[0] == "POST"] and not nuevo.scene


# ------------------------------------------------------------ el endpoint
def _chat(cliente, auto=False, texto="hola"):
    return cliente.post("/api/agent/chat",
                        json={"messages": [{"role": "user", "content": texto}], "auto": auto})


@pytest.fixture
def sin_config(monkeypatch):
    monkeypatch.delenv("APOLO_CHAT_MAX", raising=False)
    monkeypatch.delenv("APOLO_URL_INTERNA", raising=False)


def test_el_endpoint_corre_el_chat_http_sin_state_lock(mundo, sin_config, monkeypatch):
    falso = Modelo([_resp("tool_use", [_tool("t1", "run_command", CAJA)]),
                    _resp("end_turn", textos=["listo"])])
    monkeypatch.setattr(anthropic, "Anthropic", lambda: falso)
    al_abrir = []
    abrir = chat.abrir
    monkeypatch.setattr(chat, "abrir", lambda *a, **k: al_abrir.append(STATE_LOCK._is_owned())
                        or abrir(*a, **k))

    r = _chat(TestClient(api.app), auto=True)

    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    evs = _sse(r.text)
    _para_la_ui(evs)
    assert evs[0] == eventos.tool("run_command") and len(mundo.doc.scene) == 2
    assert evs[-1]["uso"]["input"] == 20
    assert mundo.bases[0] == "http://testserver:80"  # el socket que atendió la petición
    assert al_abrir == [False] and set(falso.con_lock) == {False}
    assert mundo.pedidos and not any(p[3] for p in mundo.pedidos), "HTTP con STATE_LOCK tomado"
    assert chat.CUPO.activos == 0


def test_cupo_lleno_da_429_y_se_libera(mundo, sin_config, monkeypatch):
    monkeypatch.setattr(anthropic, "Anthropic", lambda: Modelo([_resp("end_turn")]))
    monkeypatch.setenv("APOLO_CHAT_MAX", "1")
    cliente = TestClient(api.app)
    chat.CUPO.tomar()  # otro chat en curso
    try:
        r = _chat(cliente)
        assert r.status_code == 429 and r.json()["detail"] == chat.LLENO
    finally:
        chat.CUPO.soltar()
    assert _chat(cliente).status_code == 200 and chat.CUPO.activos == 0
    for malo in ("0", "muchos", str(chat.CHAT_MAX_TOPE + 1)):
        monkeypatch.setenv("APOLO_CHAT_MAX", malo)
        r = _chat(cliente)
        assert r.status_code == 500 and "APOLO_CHAT_MAX" in r.json()["detail"]
    assert chat.CUPO.activos == 0


def test_el_cupo_se_libera_aunque_el_cliente_corte(mundo):
    def abrir():
        return chat.abrir([{"role": "user", "content": "hola"}], auto=False,
                          base_url="http://chat.test",
                          cliente=Modelo([_resp("end_turn", textos=["uno", "dos", "tres"])]))

    flujo = abrir()
    assert chat.CUPO.activos == 1
    assert _sse(next(flujo)) == [{"type": "text", "text": "uno"}]
    flujo.close()  # el cliente cortó a mitad: Starlette suelta el generador
    assert chat.CUPO.activos == 0

    flujo = abrir()  # nadie llegó a iterarlo
    del flujo
    gc.collect()
    assert chat.CUPO.activos == 0

    evs = _sse("".join(abrir()))  # terminado normal
    assert evs[-1]["type"] == "done" and chat.CUPO.activos == 0


def test_el_sse_cierra_el_turno_cuando_el_envio_falla(mundo):
    """Starlette no cierra el generador: tras un corte quedaba colgado de la excepción (ciclo
    de referencias) y el cupo, ocupado hasta que pasara el GC. `_SseDelTurno` lo cierra."""
    from apolo.api.routers.core import _SseDelTurno

    flujo = chat.abrir([{"role": "user", "content": "hola"}], auto=False, base_url="http://chat.test",
                       cliente=Modelo([_resp("end_turn", textos=["uno", "dos"])]))

    async def send(mensaje):
        if mensaje["type"] == "http.response.body" and mensaje.get("body"):
            raise OSError("el cliente cortó")

    with pytest.raises(OSError) as corte:
        asyncio.run(_SseDelTurno(flujo, media_type="text/event-stream").stream_response(send))
    assert chat.CUPO.activos == 0, "el turno sigue abierto mientras viva la excepción"
    del corte


def test_sin_api_el_turno_avisa_sin_llamar_al_modelo(monkeypatch):
    def caida(req):
        raise httpx.ConnectError("rechazada", request=req)

    monkeypatch.setattr(chat, "conectar", lambda base, cab=None: Destino(base, lambda: httpx.Client(
        base_url=base, transport=httpx.MockTransport(caida))))
    falso = Modelo([])
    evs = _sse("".join(chat.abrir([{"role": "user", "content": "hola"}], auto=True,
                                  base_url="http://127.0.0.1:9", cliente=falso)))
    assert [e["type"] for e in evs] == ["error", "done"]
    assert evs[0]["message"].startswith(chat.SIN_PROYECTO)
    assert falso.llamadas == [] and chat.CUPO.activos == 0
