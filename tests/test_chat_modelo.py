"""El cliente de Anthropic del chat (plan chat-cliente-igual F7: D12 caché, D13 ningún final
silencioso) contra un cliente FALSO que guarda los kwargs de cada llamada serializados en el
momento de llamar (los bytes que mandaría el SDK). Nunca se llama a la API real.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import anthropic
import pytest

from apolo.agent import modelo
from apolo.design.instrucciones import system_prompt_chat

# El SDK 0.x habla `httpx`; el 1.x, su fork API-compatible `httpx2`, y rechaza un cliente de
# `httpx` (guía de upgrade 0.x → 1.x). El pin no tiene tope: el transporte falso sigue al SDK.
if int(anthropic.__version__.split(".")[0]) >= 1:
    import httpx2 as httpx
else:
    import httpx

RAIZ = Path(__file__).resolve().parents[1]
SYSTEM = system_prompt_chat()
TOOLS = [
    {"name": "get_scene", "description": "lee", "input_schema": {"type": "object", "properties": {}}},
    {"name": "run_batch", "description": "muta",
     "input_schema": {"type": "object", "properties": {"actions": {"type": "array"}}}},
]


@pytest.fixture(autouse=True)
def _entorno_limpio(monkeypatch):
    for var in ("APOLO_MODEL", "APOLO_MAX_TOKENS", "APOLO_EFFORT", "APOLO_CHAT_VUELTAS"):
        monkeypatch.delenv(var, raising=False)


# ------------------------------------------------------------------ el cliente falso
def _texto(t):
    return NS(type="content_block_delta", index=0, delta=NS(type="text_delta", text=t))


def _avance(t):
    return NS(type="content_block_delta", index=0, delta=NS(type="thinking_delta", thinking=t))


def _uso(i=10, o=5, leidos=None, escritos=None):
    return NS(input_tokens=i, output_tokens=o, cache_read_input_tokens=leidos,
              cache_creation_input_tokens=escritos)


def _tool(id_, nombre="get_scene", entrada=None):
    return NS(type="tool_use", id=id_, name=nombre, input=entrada or {})


def _resp(stop, contenido=(), eventos=(), uso=None, detalles=None):
    mensaje = NS(stop_reason=stop, content=list(contenido), usage=uso or _uso(),
                 stop_details=detalles)
    return mensaje, list(eventos)


class _Stream:
    def __init__(self, mensaje, eventos):
        self._mensaje, self._eventos = mensaje, eventos

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._eventos)

    def get_final_message(self):
        return self._mensaje


class _Cliente:
    """`messages.stream` y `beta.messages.stream` del SDK, sin red."""

    def __init__(self, respuestas, api_key="falsa"):
        self.api_key, self.auth_token, self.credentials = api_key, None, None
        self._respuestas = list(respuestas)
        self.llamadas: list[tuple[str, str]] = []  # (endpoint, kwargs en JSON al llamar)
        self.messages = NS(stream=lambda **kw: self._abrir("messages", kw))
        self.beta = NS(messages=NS(stream=lambda **kw: self._abrir("beta", kw)))

    def _abrir(self, donde, kw):
        self.llamadas.append((donde, json.dumps(kw, default=vars, ensure_ascii=False)))
        r = self._respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return _Stream(*r)

    def kw(self, i):
        return json.loads(self.llamadas[i][1])


def _ejecutor(corridas, seguir=True, omitir=()):
    """Ejecutor de prueba: anota qué corrió, cede un evento y responde cada tool."""

    def ejecutar(pedidos):
        corridas.append([b.id for b in pedidos])
        yield {"type": "tool", "name": pedidos[0].name}
        cuerpos = {b.id: {"content": [{"type": "text", "text": f"ok {b.id}"}]}
                   for b in pedidos if b.id not in omitir}
        return cuerpos, seguir

    return ejecutar


def _correr(respuestas=(), ejecutar=None, cliente=None):
    cliente = cliente or _Cliente(respuestas)
    convo = [{"role": "user", "content": "hola"}]
    corridas: list = []
    eventos = list(modelo.conversar(convo, system=SYSTEM, tools=TOOLS, cliente=cliente,
                                    ejecutar=ejecutar or _ejecutor(corridas)))
    return eventos, cliente, convo, corridas


def _tipos(eventos):
    return [e["type"] for e in eventos]


# ------------------------------------------------------------------------- D12 caché
def test_cache_en_el_ultimo_bloque_de_system_y_automatico_para_la_conversacion():
    eventos, c, _, _ = _correr([_resp("end_turn", [NS(type="text", text="listo")],
                                      [_texto("lis"), _texto("to")])])
    assert _tipos(eventos) == ["text", "text", "done"]
    assert [c.llamadas[0][0]] == ["messages"]
    kw = c.kw(0)
    assert kw["system"] == [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
    assert kw["cache_control"] == {"type": "ephemeral"}  # el automático de la petición
    assert kw["tools"] == TOOLS  # tal cual y en el mismo orden
    assert list(kw) == ["model", "max_tokens", "thinking", "tools", "system", "cache_control",
                        "messages"]  # la conversación, al final (después de los breakpoints fijos)
    assert c.llamadas[0][1].count('"cache_control"') == 2  # ≤ 4 breakpoints por petición


def test_mismos_bytes_en_cada_vuelta_y_la_conversacion_solo_crece():
    def respuestas():
        return [_resp("tool_use", [_tool("t1")]),
                _resp("tool_use", [NS(type="text", text="sigo"), _tool("t2"), _tool("t3")]),
                _resp("end_turn", [NS(type="text", text="fin")])]

    _, c, convo, corridas = _correr(respuestas())
    assert corridas == [["t1"], ["t2", "t3"]]
    fijos = {json.dumps({k: v for k, v in c.kw(i).items() if k != "messages"}, ensure_ascii=False)
             for i in range(3)}
    assert len(fijos) == 1  # tools, system, modelo y config: idénticos en las 3 vueltas
    m = [c.kw(i)["messages"] for i in range(3)]
    assert m[1][: len(m[0])] == m[0] and m[2][: len(m[1])] == m[1]  # append-only
    assert [x["role"] for x in convo] == ["user", "assistant", "user", "assistant", "user",
                                          "assistant"]
    assert [r["tool_use_id"] for r in convo[4]["content"]] == ["t2", "t3"]
    # otro turno igual manda los mismos bytes: nada volátil (hora, ids, orden de un set)
    _, c2, _, _ = _correr(respuestas())
    assert c2.llamadas == c.llamadas


# ------------------------------------------------- config leída en cada llamada (D11)
def test_modelo_y_limites_se_leen_en_cada_llamada(monkeypatch):
    _, c, _, _ = _correr([_resp("end_turn")])
    kw = c.kw(0)
    assert kw["model"] == modelo.MODELO == "claude-opus-4-8"  # D11: el default no cambia en F7
    assert kw["max_tokens"] == modelo.MAX_TOKENS == 16000
    assert "output_config" not in kw  # sin APOLO_EFFORT rige el default del modelo

    monkeypatch.setenv("APOLO_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("APOLO_MAX_TOKENS", "64000")
    _, c, _, _ = _correr([_resp("end_turn")])
    assert (c.kw(0)["model"], c.kw(0)["max_tokens"]) == ("claude-sonnet-5", 64000)

    monkeypatch.setenv("APOLO_MODEL", "claude-opus-4-7")
    monkeypatch.setenv("APOLO_EFFORT", "high")
    _, c, _, _ = _correr([_resp("end_turn")])
    assert c.kw(0)["model"] == "claude-opus-4-7"
    assert c.kw(0)["output_config"] == {"effort": "high"}


@pytest.mark.parametrize("var, valor", [
    ("APOLO_MAX_TOKENS", "mucho"), ("APOLO_MAX_TOKENS", "0"), ("APOLO_CHAT_VUELTAS", "-3"),
    ("APOLO_EFFORT", "turbo"),
])
def test_config_invalida_cierra_con_error_sin_llamar(monkeypatch, var, valor):
    monkeypatch.setenv(var, valor)
    eventos, c, _, _ = _correr()
    assert _tipos(eventos) == ["error", "done"] and var in eventos[0]["message"]
    assert c.llamadas == []


def test_notas_de_avance_solo_en_los_modelos_que_las_documentan(monkeypatch):
    evs = [_avance("Leo el resumen por grupo."), _avance(""), _texto("Hola")]
    eventos, c, _, _ = _correr([_resp("end_turn", eventos=evs)])  # default: claude-opus-4-8
    assert "claude-opus-4-8" not in modelo.CON_AVANCES
    assert c.llamadas[0][0] == "messages" and "betas" not in c.kw(0)
    assert c.kw(0)["thinking"] == {"type": "adaptive"}
    assert _tipos(eventos) == ["text", "done"]  # el pensamiento no se muestra como avance

    monkeypatch.setenv("APOLO_MODEL", "claude-opus-5-5")
    eventos, c, _, _ = _correr([_resp("end_turn", eventos=evs)])
    assert c.llamadas[0][0] == "beta"
    assert c.kw(0)["betas"] == ["thinking-display-updates-2026-08-18"]
    assert c.kw(0)["thinking"] == {"type": "adaptive", "display": "updates"}
    assert eventos[:2] == [{"type": "progreso", "text": "Leo el resumen por grupo."},
                           {"type": "text", "text": "Hola"}]


# ------------------------------------------------- D13 ningún final silencioso
@pytest.mark.parametrize("motivo", ["max_tokens", "refusal", "model_context_window_exceeded",
                                    "motivo_que_no_existe_aun"])
def test_un_final_que_no_es_tool_use_avisa_y_no_corre_sus_tools(motivo):
    detalles = NS(type="refusal", category="cyber", explanation="x") if motivo == "refusal" else None
    respuesta = _resp(motivo, [NS(type="text", text="a medias"),
                               _tool("t1", "run_batch", {"actions": []})], detalles=detalles)
    eventos, c, convo, corridas = _correr([respuesta])
    assert corridas == []  # la tool de una respuesta cortada NUNCA corre
    assert len(c.llamadas) == 1
    assert _tipos(eventos) == ["aviso", "done"]
    assert eventos[0]["motivo"] == motivo and eventos[0]["mensaje"]
    esperado = modelo.AVISOS.get(motivo, modelo.AVISOS["otro"])
    if motivo != "refusal":
        assert eventos[0]["mensaje"] == esperado
    # el historial sigue válido: el tool_use cortado tiene su resultado (de error)
    (r,) = convo[-1]["content"]
    assert convo[-1]["role"] == "user" and r["tool_use_id"] == "t1" and r["is_error"] is True


def test_max_tokens_dice_el_limite():
    eventos, _, _, _ = _correr([_resp("max_tokens")])
    assert eventos[0]["max_tokens"] == 16000


def test_rechazo_lleva_su_categoria():
    detalles = NS(type="refusal", category="cyber", explanation="parece un ataque")
    eventos, _, _, _ = _correr([_resp("refusal", detalles=detalles)])
    aviso = eventos[0]
    assert (aviso["categoria"], aviso["explicacion"]) == ("cyber", "parece un ataque")
    assert "(categoría: cyber)" in aviso["mensaje"]

    eventos, _, _, _ = _correr([_resp("refusal", detalles=None)])  # categoría desconocida
    assert eventos[0]["categoria"] is None and "categoría" not in eventos[0]["mensaje"]


def test_pause_turn_se_reanuda_sin_mensaje_nuevo():
    pausa = NS(type="server_tool_use", id="s1", name="web_search", input={"query": "x"})
    eventos, c, convo, corridas = _correr([_resp("pause_turn", [pausa]),
                                           _resp("end_turn", [NS(type="text", text="listo")])])
    assert "aviso" not in _tipos(eventos) and corridas == []
    m2 = c.kw(1)["messages"]
    assert len(m2) == 2 and m2[-1]["role"] == "assistant" and m2[-1]["content"][0]["id"] == "s1"
    assert [x["role"] for x in convo] == ["user", "assistant", "assistant"]


def test_vueltas_agotadas_avisan(monkeypatch):
    monkeypatch.setenv("APOLO_CHAT_VUELTAS", "3")
    eventos, c, convo, corridas = _correr([_resp("tool_use", [_tool(f"t{i}")]) for i in range(5)])
    assert len(c.llamadas) == 3 and len(corridas) == 3
    assert eventos[-2] == {"type": "aviso", "motivo": "vueltas",
                           "mensaje": modelo.AVISOS["vueltas"].format(n=3)}
    assert "3 pasos" in eventos[-2]["mensaje"]
    assert convo[-1]["role"] == "user"  # cada tool_use quedó respondido

    monkeypatch.delenv("APOLO_CHAT_VUELTAS")
    _, c, _, _ = _correr([_resp("tool_use", [_tool(f"t{i}")]) for i in range(25)])
    assert len(c.llamadas) == modelo.VUELTAS == 20


def test_uso_suma_todas_las_llamadas_del_turno():
    eventos, _, _, _ = _correr([
        _resp("tool_use", [_tool("t1")], uso=_uso(100, 7, None, 900)),
        _resp("end_turn", uso=_uso(5, 3, 900, 12)),
    ])
    assert eventos[-1] == {"type": "done", "uso": {"input": 105, "output": 10, "cache_read": 900,
                                                   "cache_creation": 912}}


# ------------------------------------------------------------------- el ejecutor
def test_el_ejecutor_cede_sus_eventos_y_toda_tool_tiene_resultado():
    corridas: list = []
    eventos, c, convo, _ = _correr(
        [_resp("tool_use", [_tool("t1"), _tool("t2")]), _resp("end_turn")],
        ejecutar=_ejecutor(corridas, omitir={"t2"}),
    )
    assert _tipos(eventos) == ["tool", "done"]
    r1, r2 = convo[2]["content"]
    assert r1 == {"type": "tool_result", "tool_use_id": "t1",
                  "content": [{"type": "text", "text": "ok t1"}]}
    assert r2["tool_use_id"] == "t2" and r2["is_error"] is True  # sin respuesta → error, no 400
    assert len(c.llamadas) == 2


def test_seguir_false_cierra_el_turno_sin_otra_vuelta():
    corridas: list = []
    eventos, c, convo, _ = _correr([_resp("tool_use", [_tool("t1", "propose_commands")])],
                                   ejecutar=_ejecutor(corridas, seguir=False))
    assert len(c.llamadas) == 1 and _tipos(eventos) == ["tool", "done"]
    assert convo[-1]["content"][0]["tool_use_id"] == "t1"


def test_corte_del_ejecutor_cierra_con_error():
    def ejecutar(pedidos):
        yield {"type": "tool", "name": pedidos[0].name}
        raise modelo.Corte("Se abrió otro proyecto: no apliqué nada.")

    eventos, c, _, _ = _correr([_resp("tool_use", [_tool("t1")], uso=_uso(4, 2)),
                                _resp("end_turn")], ejecutar=ejecutar)
    assert _tipos(eventos) == ["tool", "error", "done"] and len(c.llamadas) == 1
    assert eventos[1]["message"] == "Se abrió otro proyecto: no apliqué nada."
    assert eventos[2]["uso"]["input"] == 4  # el uso de lo que sí se llamó


# ------------------------------------------------------------------- credenciales
def test_sin_credencial_el_mensaje_de_siempre_y_ninguna_llamada():
    eventos, c, _, _ = _correr(cliente=_Cliente([], api_key=None))
    assert eventos[0] == {"type": "error", "message": modelo.SIN_CREDENCIAL}
    assert eventos[0]["message"].startswith("Falta la variable de entorno ANTHROPIC_API_KEY")
    assert c.llamadas == []


def test_el_cliente_lo_arma_el_sdk_sin_argumentos(monkeypatch):
    """La credencial la resuelve el SDK (variable, token o perfil): no se lee el entorno aquí."""
    armados = []

    def fabrica(*a, **k):
        armados.append((a, k))
        return _Cliente([_resp("end_turn")])

    monkeypatch.setattr(anthropic, "Anthropic", fabrica)
    eventos = list(modelo.conversar([{"role": "user", "content": "hola"}], system=SYSTEM,
                                    tools=TOOLS, ejecutar=_ejecutor([])))
    assert armados == [((), {})] and _tipos(eventos) == ["done"]


def test_credencial_rechazada_conserva_el_mensaje_de_hoy():
    req = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    error = anthropic.AuthenticationError("invalid x-api-key", response=httpx.Response(401, request=req),
                                          body=None)
    eventos, _, _, _ = _correr([error])
    assert eventos == [{"type": "error", "message": "Error del API de Claude: invalid x-api-key"},
                       {"type": "done", "uso": dict.fromkeys(
                           ("input", "output", "cache_read", "cache_creation"), 0)}]


# --------------------------------------------- el SDK instalado, con transporte falso
def _sse(*eventos) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in eventos).encode()


def _respuesta_sse(stop, delta_extra=None):
    """Un pensamiento con nota de avance, un texto y el cierre con `stop`, como lo manda el API."""
    uso = {"input_tokens": 30, "output_tokens": 1, "cache_read_input_tokens": 1200,
           "cache_creation_input_tokens": 40}
    return _sse(
        {"type": "message_start", "message": {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "m", "content": [],
            "stop_reason": None, "stop_sequence": None, "usage": uso}},
        {"type": "content_block_start", "index": 0,
         "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "thinking_delta", "thinking": "Leo el modelo."}},
        {"type": "content_block_delta", "index": 0,
         "delta": {"type": "signature_delta", "signature": "firma"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Hola"}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None,
                                            **(delta_extra or {})},
         "usage": {"output_tokens": 9}},
        {"type": "message_stop"},
    )


@pytest.mark.parametrize("modelo_env, beta", [
    (None, None), ("claude-opus-5-5", "thinking-display-updates-2026-08-18"),
])
def test_contra_el_sdk_instalado(monkeypatch, modelo_env, beta):
    """El SDK real acepta los kwargs y manda los bytes de D12; `stop_details` y `usage` se leen
    de sus objetos. Todo por `httpx.MockTransport`: ninguna petición sale de la máquina."""
    if modelo_env:
        monkeypatch.setenv("APOLO_MODEL", modelo_env)
    pedidos = []

    def responder(req):
        pedidos.append(req)
        detalles = {"stop_details": {"type": "refusal", "category": "cyber", "explanation": None}}
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=_respuesta_sse("refusal", detalles))

    cliente = anthropic.Anthropic(api_key="falsa", max_retries=0,
                                  http_client=httpx.Client(transport=httpx.MockTransport(responder)))
    eventos, _, convo, corridas = _correr(cliente=cliente)

    (req,) = pedidos
    cuerpo = json.loads(req.content)
    assert req.url.path == "/v1/messages" and req.headers.get("anthropic-beta") == beta
    assert req.url.params.get("beta") == ("true" if beta else None)  # el endpoint beta del SDK
    assert cuerpo["system"][-1]["cache_control"] == {"type": "ephemeral"}
    assert cuerpo["cache_control"] == {"type": "ephemeral"} and cuerpo["tools"] == TOOLS
    assert cuerpo["thinking"] == ({"type": "adaptive", "display": "updates"} if beta
                                  else {"type": "adaptive"})
    avances = [{"type": "progreso", "text": "Leo el modelo."}] if beta else []
    assert eventos[:-2] == avances + [{"type": "text", "text": "Hola"}]
    assert eventos[-2]["motivo"] == "refusal" and eventos[-2]["categoria"] == "cyber"
    assert eventos[-1]["uso"] == {"input": 30, "output": 9, "cache_read": 1200,
                                  "cache_creation": 40}
    assert corridas == [] and convo[-1]["role"] == "assistant"


# ------------------------------------------------------------------- gates
def test_los_avisos_cumplen_el_estandar_de_texto():
    """`faltas()` de test_pistas: tuteo neutro, una frase, sin jerga ni identificadores."""
    spec = importlib.util.spec_from_file_location("_pistas_gate", RAIZ / "tests" / "test_pistas.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    textos = [t for k, t in modelo.AVISOS.items() if k not in ("refusal", "vueltas")]
    textos += [modelo.AVISOS["refusal"].format(cat=""),
               modelo.AVISOS["refusal"].format(cat=" (categoría: cyber)"),
               modelo.AVISOS["vueltas"].format(n=20)]
    for texto in textos:
        assert gate.faltas(texto) == [], f"«{texto}»: {gate.faltas(texto)}"


def test_modelo_es_un_cliente_puro():
    """No importa nada de apolo: ni estado ni documento (D4a); `anthropic`, perezoso."""
    arbol = ast.parse((RAIZ / "core" / "apolo" / "agent" / "modelo.py").read_text(encoding="utf-8"))
    mods = {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    mods |= {("." * n.level) + (n.module or "") for n in ast.walk(arbol)
             if isinstance(n, ast.ImportFrom)}
    assert not {m for m in mods if m.startswith(("apolo", "."))}
    de_arriba = {a.name for n in arbol.body if isinstance(n, ast.Import) for a in n.names}
    assert "anthropic" not in de_arriba
