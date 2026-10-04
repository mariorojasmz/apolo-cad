"""El cliente de Anthropic del chat: caché de prompt y ningún final silencioso (plan
chat-cliente-igual, D12 y D13). Las tools las corre quien llama; lo cablea al endpoint la F5a.

Config LEÍDA EN CADA LLAMADA (sin reiniciar la API); los defaults son los de antes a propósito
(modelo, effort y `max_tokens` son D11, los decide Mario): `APOLO_MODEL` (claude-opus-4-8),
`APOLO_MAX_TOKENS` (16000), `APOLO_EFFORT` (sin valor no va `output_config`: rige el default del
modelo) y `APOLO_CHAT_VUELTAS` (20 llamadas por turno).

Caché (D12): se renderiza tools → system → messages. Las tools van tal cual, en el orden en que
llegan (`herramientas.definiciones()` es determinista); un breakpoint en el último bloque de
`system` cachea tools + system y el automático de la petición cubre la conversación, que sólo
crece por el final. El resto se arma una vez por turno: mismos bytes en cada vuelta.

Ningún final silencioso (D13): `max_tokens`, `refusal` (con su categoría), otra razón inesperada
y las vueltas agotadas cierran con un `aviso`; `pause_turn` se reanuda; las tools de una
respuesta que no terminó en `tool_use` NUNCA corren (van al historial como error, para que siga
válido). El último evento es siempre `done` con `uso`.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Generator, Iterator
from dataclasses import dataclass
from typing import Any

MODELO, MAX_TOKENS, VUELTAS = "claude-opus-4-8", 16000, 20  # los dos primeros: D11
ESFUERZOS = ("low", "medium", "high", "xhigh", "max")
#: Los que la referencia de la API documenta con `thinking.display: "updates"` (beta): las notas
#: entre tools llegan como texto. En los demás modelos se omite.
CON_AVANCES = frozenset({"claude-fable-5-1", "claude-mythos-5-1", "claude-fable-5",
                         "claude-opus-5-5", "claude-sonnet-5-5"})
BETA_AVANCES = "thinking-display-updates-2026-08-18"
SIN_CREDENCIAL = ("Falta la variable de entorno ANTHROPIC_API_KEY: el asistente IA no está "
                  "disponible.")
AVISOS = {  # por `stop_reason` (más "vueltas"); el que no está recibe "otro"
    "max_tokens": "La respuesta se cortó porque llegó a su largo máximo: pídeme que continúe.",
    "refusal": "El modelo no siguió con este pedido por sus reglas de seguridad{cat}: "
               "reformúlalo.",
    "model_context_window_exceeded": "La conversación ya es demasiado larga para el modelo: "
                                     "empieza una nueva.",
    "vueltas": "Llegué al tope de {n} pasos sin terminar: pídeme que siga y continúo donde "
               "quedé.",
    "otro": "La respuesta terminó antes de tiempo por un motivo inesperado: vuelve a intentarlo.",
}
NO_CORRIO = {"content": "No se ejecutó: la respuesta terminó antes de cerrar la llamada.",
             "is_error": True}
SIN_RESULTADO = {"content": "La tool no devolvió resultado.", "is_error": True}

#: Corre las tools de UNA respuesta: generador que cede eventos para la UI y RETORNA
#: ({tool_use_id: cuerpo del tool_result}, seguir); `seguir=False` cierra el turno sin otra
#: vuelta (p. ej. tras mostrar una propuesta). Para cortar con un error, lanza `Corte`.
Ejecutor = Callable[[list], Generator[dict, None, tuple[dict, bool]]]


class Corte(Exception):
    """Cierra el turno con un evento `error` y su texto (config inválida, proyecto cambiado…)."""


@dataclass(frozen=True)
class Config:
    modelo: str
    max_tokens: int
    esfuerzo: str | None
    vueltas: int


def _entero(nombre: str, defecto: int) -> int:
    crudo = os.environ.get(nombre, "").strip()
    if crudo and (not crudo.isdigit() or int(crudo) < 1):
        raise Corte(f"{nombre} debe ser un entero positivo (vale «{crudo}»).")
    return int(crudo) if crudo else defecto


def config() -> Config:
    esfuerzo = os.environ.get("APOLO_EFFORT", "").strip() or None
    if esfuerzo not in (None, *ESFUERZOS):
        raise Corte(f"APOLO_EFFORT debe ser uno de {', '.join(ESFUERZOS)} (vale «{esfuerzo}»).")
    return Config(os.environ.get("APOLO_MODEL", "").strip() or MODELO,
                  _entero("APOLO_MAX_TOKENS", MAX_TOKENS), esfuerzo,
                  _entero("APOLO_CHAT_VUELTAS", VUELTAS))


def peticion(cfg: Config, system: str, tools: list[dict]) -> dict:
    """Los kwargs de `messages.stream` salvo `messages`: idénticos en cada vuelta del turno."""
    avances = cfg.modelo in CON_AVANCES
    kw = {"model": cfg.modelo, "max_tokens": cfg.max_tokens,
          "thinking": {"type": "adaptive", **({"display": "updates"} if avances else {})},
          "tools": list(tools),
          "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
          "cache_control": {"type": "ephemeral"}}
    if cfg.esfuerzo:
        kw["output_config"] = {"effort": cfg.esfuerzo}
    if avances:
        kw["betas"] = [BETA_AVANCES]
    return kw


def conversar(convo: list[dict], *, system: str, tools: list[dict], ejecutar: Ejecutor,
              cliente: Any = None) -> Iterator[dict]:
    """Un turno: llama al modelo, corre sus tools con `ejecutar` y repite hasta que termine.
    AGREGA a `convo` cada respuesta y cada lote de resultados (append-only: lo ya mandado es el
    prefijo cacheado). Cede `text`, `progreso`, `aviso`, `error` (más los del ejecutor) y, al
    final, `done` con `uso`: los tokens de todas las llamadas del turno."""
    import anthropic

    uso = dict.fromkeys(("input", "output", "cache_read", "cache_creation"), 0)
    try:
        cfg = config()
        if cliente is None:
            cliente = anthropic.Anthropic()  # la credencial la resuelve el SDK
        if not any(getattr(cliente, a, None) for a in ("api_key", "auth_token", "credentials")):
            raise Corte(SIN_CREDENCIAL)
        yield from _turno(cliente, cfg, peticion(cfg, system, tools), convo, ejecutar, uso)
    except Corte as exc:
        yield {"type": "error", "message": str(exc)}
    except anthropic.APIError as exc:
        yield {"type": "error", "message": f"Error del API de Claude: {exc.message}"}
    yield {"type": "done", "uso": uso}


def _turno(cliente, cfg: Config, kw: dict, convo: list, ejecutar: Ejecutor, uso: dict):
    for _ in range(cfg.vueltas):
        resp = yield from _llamar(cliente, kw, convo)
        for clave, campo in (("input", "input_tokens"), ("output", "output_tokens"),
                             ("cache_read", "cache_read_input_tokens"),
                             ("cache_creation", "cache_creation_input_tokens")):
            uso[clave] += getattr(resp.usage, campo, None) or 0
        convo.append({"role": "assistant", "content": resp.content})
        pedidos = [b for b in resp.content if b.type == "tool_use"]
        if resp.stop_reason == "pause_turn":
            continue  # el API retoma desde este turno del asistente, sin mensaje nuevo
        if resp.stop_reason != "tool_use":
            if pedidos:  # una llamada cortada o rechazada no corre
                convo.append({"role": "user", "content": [_resultado(b, NO_CORRIO)
                                                          for b in pedidos]})
            if resp.stop_reason not in ("end_turn", "stop_sequence"):
                yield _aviso(resp, cfg)
            return
        cuerpos, seguir = yield from ejecutar(pedidos)
        convo.append({"role": "user", "content": [_resultado(b, cuerpos.get(b.id, SIN_RESULTADO))
                                                  for b in pedidos]})
        if not seguir:
            return
    yield {"type": "aviso", "motivo": "vueltas", "mensaje": AVISOS["vueltas"].format(n=cfg.vueltas)}


def _llamar(cliente, kw: dict, convo: list):
    """Una llamada en streaming: cede el texto (y las notas de avance) y retorna el mensaje."""
    abrir = cliente.beta.messages.stream if "betas" in kw else cliente.messages.stream
    with abrir(**kw, messages=convo) as stream:
        for ev in stream:
            if ev.type != "content_block_delta":
                continue
            if ev.delta.type == "text_delta" and ev.delta.text:
                yield {"type": "text", "text": ev.delta.text}
            elif ev.delta.type == "thinking_delta" and ev.delta.thinking and "betas" in kw:
                yield {"type": "progreso", "text": ev.delta.thinking}  # con "updates" = avance
        return stream.get_final_message()


def _resultado(bloque, cuerpo: dict) -> dict:
    return {"type": "tool_result", "tool_use_id": bloque.id, **cuerpo}


def _aviso(resp, cfg: Config) -> dict:
    motivo = resp.stop_reason
    aviso = {"type": "aviso", "motivo": motivo, "mensaje": AVISOS.get(motivo, AVISOS["otro"])}
    if motivo == "max_tokens":
        aviso["max_tokens"] = cfg.max_tokens
    elif motivo == "refusal":
        detalle = getattr(resp, "stop_details", None)
        aviso["categoria"] = getattr(detalle, "category", None)
        aviso["explicacion"] = getattr(detalle, "explanation", None)
        cat = f" (categoría: {aviso['categoria']})" if aviso["categoria"] else ""
        aviso["mensaje"] = AVISOS["refusal"].format(cat=cat)
    return aviso
