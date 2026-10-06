"""El chat de la app como un cliente más de la API (plan chat-cliente-igual F5a, D2–D8).

Un turno (`abrir`) es lo que haría Claude Code por MCP, pero desde un hilo de la propia API:
lee al empezar el token del documento abierto (`GET /api/health` → `documento`, como cualquier
cliente) y corre cada tool del catálogo con `herramientas.ejecutar` contra la URL loopback que
lo atendió, con `X-Apolo-Documento: <token>`. Así una mutación que llega cuando ya hay otro
documento abierto da 409 en el servidor, bajo su lock, sin aplicar nada (D3), y aquí corta el
turno (`modelo.Corte`). Antes de cada tanda de tools se relee el token: si se abrió otro
proyecto, el turno se corta también sin gastar más vueltas leyendo un proyecto ajeno.

- Ningún lock del servidor: nada de aquí importa `apolo.state` ni `apolo.api` (D4a, gate en
  `tests/test_chat_http.py`); el documento sólo se toca por HTTP, como lo toca la UI.
- `CUPO` (D4b): a lo sumo `APOLO_CHAT_MAX` turnos a la vez (4); el siguiente es `Lleno` → 429.
  Cada turno ocupa un hilo del threadpool de la API mientras espera al modelo o a sus propias
  peticiones, que necesitan OTRO hilo: el tope deja siempre hilos libres para ellas.
- Nunca `anyio.from_thread` (D4c): las tools corren con el `asyncio.run` privado de
  `herramientas.ejecutar`, en el hilo del turno.
- Mismas tools y mismo `system` en los dos modos (D6, caché D12): el modo viaja como un bloque
  más del ÚLTIMO mensaje de la persona (append-only), nunca en `messages[0]`. En propuesta, lo
  que muta devuelve `is_error` sin llamar a la API (`herramientas.ejecutar`).
- `propose_commands` (D7) se ensaya con `preview(actions, data=true)` por HTTP y, si pasa,
  sale como tarjetas pendientes (`actions`). Los 53 schemas no van embebidos (D8): el modelo
  los pide con `get_command_schemas`.
- En modo auto, la escena de la UI se refresca por el WebSocket que dispara cada mutación de
  la API; además un `run_command`/`run_batch` aplicado sale como tarjetas `executed=True`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from collections.abc import Iterator
from typing import Any

from apolo.design.instrucciones import system_prompt_chat
from apolo.tools.destino import Destino

from . import eventos, herramientas, modelo
from .herramientas import AUTONOMO, PROPONER, PROPUESTA

log = logging.getLogger(__name__)

#: La cabecera de la guardia del documento (= `apolo.api.guardia_documento.CABECERA`; el
#: chat no importa la API: lo compara un test).
CABECERA = "X-Apolo-Documento"
#: Turnos a la vez por defecto (`APOLO_CHAT_MAX`) y el máximo que se acepta: la mitad de las
#: 40 fichas del threadpool de la API, para que sus propias peticiones siempre tengan hilo.
CHAT_MAX, CHAT_MAX_TOPE = 4, 20

LLENO = ("El asistente ya atiende varias conversaciones a la vez: espera a que termine una y "
         "vuelve a intentarlo.")
PROYECTO_CAMBIO = ("Se abrió otro proyecto o se restauró una revisión mientras trabajaba: me "
                   "detuve sin aplicar nada más.")
SIN_PROYECTO = "No pude leer el proyecto abierto: revisa que el servidor siga en marcha."
FALLO = "El asistente falló por un error interno: vuelve a intentarlo."

#: El modo de ESTE turno, para el modelo (no lo lee la persona). Las reglas de la app
#: (`design/instrucciones.py::REGLAS_CHAT`) dicen qué hacer en cada uno.
RECORDATORIO = {
    PROPUESTA: ("<system-reminder>Modo de este turno: PROPUESTA. Lo que cambia el documento no "
                "se ejecuta (devuelve un error): propón esos cambios con propose_commands."
                "</system-reminder>"),
    AUTONOMO: ("<system-reminder>Modo de este turno: AUTO. La persona activó el modo auto: "
               "aplica los cambios tú, verifica, corrige si hace falta y al final resume qué "
               "construiste y qué validaste.</system-reminder>"),
}

_RECHAZO_409 = re.compile(r"rechazó la operación \(409\)")  # `mcp_server._reject` (golden)
_LOTES = ("run_command", "run_batch")


class Lleno(Exception):
    """No hay lugar para otro turno a la vez (D4b): la API responde 429."""


def tope() -> int:
    """`APOLO_CHAT_MAX`, leído en cada turno (sin reiniciar la API)."""
    crudo = os.environ.get("APOLO_CHAT_MAX", "").strip()
    if not crudo:
        return CHAT_MAX
    if not crudo.isdigit() or not 1 <= int(crudo) <= CHAT_MAX_TOPE:
        raise ValueError(f"APOLO_CHAT_MAX debe ser un entero entre 1 y {CHAT_MAX_TOPE} "
                         f"(vale «{crudo}»).")
    return int(crudo)


class Cupo:
    """Contador de turnos en curso con lock HOJA (con él tomado no se toma otro lock)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._activos = 0

    @property
    def activos(self) -> int:
        return self._activos

    def tomar(self) -> None:
        maximo = tope()
        with self._lock:
            if self._activos >= maximo:
                raise Lleno(LLENO)
            self._activos += 1

    def soltar(self) -> None:
        with self._lock:
            self._activos -= 1


CUPO = Cupo()


# ------------------------------------------------------------------- destino
def url_interna(servidor: Any) -> str:
    """La URL loopback de la API que atiende este turno: `APOLO_URL_INTERNA` si está, si no el
    socket que recibió la petición (`request.scope["server"]`, `(host, puerto)`)."""
    fija = os.environ.get("APOLO_URL_INTERNA", "").strip()
    if fija:
        return fija.rstrip("/")
    if not servidor or servidor[1] is None:
        raise ValueError("No sé en qué dirección atiende la API: define APOLO_URL_INTERNA.")
    host, puerto = str(servidor[0]), int(servidor[1])
    host = {"0.0.0.0": "127.0.0.1", "": "127.0.0.1", "::": "::1"}.get(host, host)
    return f"http://[{host}]:{puerto}" if ":" in host else f"http://{host}:{puerto}"


def conectar(base_url: str, cabeceras: dict[str, str] | None = None) -> Destino:
    """El destino de las peticiones del turno (los tests lo sustituyen por un TestClient)."""
    return Destino.http(base_url, cabeceras)


def leer_token(destino: Destino) -> str:
    """El token del documento abierto, como lo lee cualquier cliente: `GET /api/health`."""
    with destino.abrir() as cliente:
        respuesta = cliente.get("/api/health")
        respuesta.raise_for_status()
        return str(respuesta.json()["documento"])


def _vigente(destino: Destino, token: str) -> bool:
    """¿Sigue abierto el documento del turno? Si no se puede leer, se sigue: la guardia del
    servidor protege igual las mutaciones (esto sólo ahorra vueltas sobre un proyecto ajeno)."""
    try:
        return leer_token(destino) == token
    except Exception:
        return True


# ----------------------------------------------------------- historial y modo
def preparar(messages: list[dict], modo: str) -> list[dict]:
    """La conversación que recibe el modelo: el historial TAL CUAL y, en el último mensaje de
    la persona, un bloque más con el modo del turno (D6). Lo anterior no cambia ni un byte."""
    convo = [{"role": m["role"], "content": m["content"]} for m in messages]
    recordatorio = {"type": "text", "text": RECORDATORIO[modo]}
    if convo and convo[-1]["role"] == "user":
        ultimo = convo[-1]["content"]
        if isinstance(ultimo, list):
            bloques = list(ultimo)
        else:
            bloques = [{"type": "text", "text": ultimo}] if str(ultimo).strip() else []
        convo[-1] = {"role": "user", "content": [*bloques, recordatorio]}
    else:
        convo.append({"role": "user", "content": [recordatorio]})
    return convo


# ------------------------------------------------------------------- las tools
def _error(texto: str) -> dict:
    return {"content": [{"type": "text", "text": texto}], "is_error": True}


def _texto(cuerpo: dict) -> str:
    return " ".join(b.get("text", "") for b in cuerpo.get("content", []) if b.get("type") == "text")


def _correr(nombre: str, entrada: Any, destino: Destino, modo: str) -> dict:
    """Una tool del catálogo; un fallo inesperado vuelve como error, nunca tumba el turno."""
    try:
        return herramientas.ejecutar(nombre, entrada if isinstance(entrada, dict) else {},
                                     destino, modo)
    except Exception as exc:
        log.exception("tool %s del chat", nombre)
        return _error(f"La tool {nombre} falló: {type(exc).__name__}: {exc}")


def _documento_cambio(cuerpo: dict) -> bool:
    """La API rechazó con 409: la guardia del documento o la del job (el proyecto cambió)."""
    return bool(cuerpo.get("is_error")) and bool(_RECHAZO_409.search(_texto(cuerpo)))


def _proponer(entrada: Any, destino: Destino, modo: str) -> tuple[dict, list[dict] | None]:
    """D7: ensaya el lote en seco (`preview(data=true)`, una lectura) y devuelve el cuerpo del
    tool_result y las tarjetas a mostrar (None = la propuesta no pasó y no se muestra)."""
    actions = (entrada or {}).get("actions") if isinstance(entrada, dict) else None
    if (not isinstance(actions, list) or not actions
            or not all(isinstance(a, dict) and isinstance(a.get("type"), str) for a in actions)):
        return _error("propose_commands necesita actions: una lista no vacía de "
                      "{type, params, reason}."), None
    lote = [{"type": a["type"], "params": a.get("params") or {}} for a in actions]
    ensayo = _correr("preview", {"actions": lote, "data": True}, destino, modo)
    if ensayo.get("is_error"):
        return _error("La propuesta falló al ensayarla en seco sobre una copia del documento "
                      "y no se mostró: corrígela y vuelve a proponer. " + _texto(ensayo)), None
    return {"content": [{"type": "text", "text": (
        "Propuesta mostrada a la persona como tarjetas; queda pendiente de que la acepte. "
        "Ensayo en seco: " + _texto(ensayo))}]}, actions


def _aplicado(nombre: str, entrada: Any, cuerpo: dict) -> list[dict] | None:
    """El lote que el modo auto acaba de aplicar, para mostrarlo como tarjetas (None si no
    hubo lote, falló o quedó encolado: un recibo de job todavía no aplicó nada)."""
    if nombre not in _LOTES or cuerpo.get("is_error") or not isinstance(entrada, dict):
        return None
    try:
        salida = json.loads(_texto(cuerpo))
    except ValueError:
        salida = None
    if isinstance(salida, dict) and "job" in salida and "seguir" in salida:
        return None
    if nombre == "run_command":
        return [{"type": entrada.get("type"), "params": entrada.get("params")}]
    lote = entrada.get("actions")
    return [a for a in lote if isinstance(a, dict)] if isinstance(lote, list) else None


def ejecutor(destino: Destino, modo: str, token: str) -> modelo.Ejecutor:
    """Corre las tools de UNA respuesta (protocolo de `modelo.Ejecutor`): cede `tool` y
    `actions` para la UI y retorna los cuerpos de los tool_result; una propuesta mostrada
    cierra el turno (`seguir=False`) y un proyecto cambiado lo corta (`modelo.Corte`)."""

    def ejecutar(pedidos: list):
        if not _vigente(destino, token):
            raise modelo.Corte(PROYECTO_CAMBIO)
        cuerpos: dict[str, dict] = {}
        seguir = True
        for b in pedidos:
            yield eventos.tool(b.name)
            if b.name == PROPONER:
                cuerpo, tarjetas = _proponer(b.input, destino, modo)
                if tarjetas is not None:
                    yield eventos.acciones(tarjetas, ejecutadas=False)
                    seguir = False
            else:
                cuerpo = _correr(b.name, b.input, destino, modo)
                if _documento_cambio(cuerpo):
                    raise modelo.Corte(PROYECTO_CAMBIO)
                lote = _aplicado(b.name, b.input, cuerpo)
                if lote:
                    yield eventos.acciones(lote, ejecutadas=True)
            cuerpos[b.id] = cuerpo
        return cuerpos, seguir

    return ejecutar


# --------------------------------------------------------------------- el turno
def turno(convo: list[dict], modo: str, destino: Destino, token: str,
          cliente: Any = None) -> Iterator[dict]:
    """Los eventos de un turno sobre `convo` (que crece append-only): `modelo.conversar` con
    las tools del catálogo, la guía única y el ejecutor de arriba."""
    yield from modelo.conversar(convo, system=system_prompt_chat(),
                                tools=herramientas.definiciones(),
                                ejecutar=ejecutor(destino, modo, token), cliente=cliente)


def abrir(messages: list[dict], *, auto: bool, base_url: str, cliente: Any = None) -> Iterator[str]:
    """Reserva un lugar en `CUPO` (o lanza `Lleno`) y devuelve el stream SSE del turno.

    El generador sale CEBADO (ya entró a su `try`): desde aquí el lugar se libera en su
    `finally` cuando termina, cuando el cliente corta y Starlette lo cierra o lo suelta, y
    aunque nadie llegue a iterarlo (cerrar o recolectar un generador sin empezar no corre
    su `finally`; uno cebado sí)."""
    CUPO.tomar()
    flujo = _flujo(messages, AUTONOMO if auto else PROPUESTA, base_url, cliente)
    next(flujo)  # no puede fallar: el primer paso es el `yield` dentro del try
    return flujo


def _flujo(messages: list[dict], modo: str, base_url: str, cliente: Any) -> Iterator[str]:
    try:
        yield ""  # cebado (lo consume `abrir`)
        try:
            token = leer_token(conectar(base_url))
        except Exception as exc:
            yield eventos.sse(eventos.error(f"{SIN_PROYECTO} ({type(exc).__name__}: {exc})"))
            yield eventos.sse(eventos.fin())
            return
        destino = conectar(base_url, {CABECERA: token})
        try:
            for ev in turno(preparar(messages, modo), modo, destino, token, cliente):
                yield eventos.sse(ev)
        except Exception:
            log.exception("turno del chat")
            yield eventos.sse(eventos.error(FALLO))
            yield eventos.sse(eventos.fin())
    finally:
        CUPO.soltar()
