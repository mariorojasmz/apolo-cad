"""Guardia del documento: una mutación que trae `X-Apolo-Documento` sólo se aplica sobre ESE
documento (D3 del plan `docs/plans/chat-cliente-igual.md`).

Cada objeto `Document` recibe un token propio la primera vez que se pide (`token`). Abrir o
crear un proyecto, subir un `.apolo` y restaurar una revisión crean un `Document` NUEVO →
token nuevo; editar, deshacer, renombrar o aplicar una variante no lo cambian. `GET
/api/health` lo publica en `documento`. El token vive en un `WeakKeyDictionary` (identidad del
objeto, se va con él): un `id()` crudo se recicla y un documento nuevo heredaría el token de
uno recolectado.

Un cliente que trabaja por turnos (el chat de la app) lee el token al empezar y lo manda en
cada petición. `CabeceraDocumento` (middleware ASGI que registra `main`) deja el valor en un
ContextVar mientras dura la petición; `verificar(doc)` lo compara con el token del documento
activo y, si difiere, lanza 409 SIN aplicar nada. Se llama DENTRO del `STATE_LOCK` de la
mutación y antes de tocar nada —`_state_or_error`, el job de `_sync_or_job` y cada mutación
fuera de ese embudo—: como todo cambio de documento activo también ocurre bajo `STATE_LOCK`,
comparar y mutar en la misma adquisición no deja ventana (sin TOCTOU). Sin cabecera, nada
cambia. Un job corre en el hilo del worker, donde el ContextVar de la petición no llega:
`_sync_or_job` captura `esperado()` al encolar y lo vuelve a fijar con `esperando(...)`.

Hoja de `apolo.api` (gate de capas en `tests/test_api_sesion.py`): no importa nada de la API;
quien verifica le pasa el documento activo (`common._verificar_documento`).
"""

from __future__ import annotations

import secrets
import threading
import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from fastapi import HTTPException

#: La cabecera opcional con el token del documento sobre el que el cliente quiere actuar.
CABECERA = "X-Apolo-Documento"
_CABECERA_ASGI = CABECERA.lower().encode("latin-1")  # ASGI entrega los nombres en minúsculas

#: El `detail` del 409 (lo lee el agente y, en el chat, la persona).
DOCUMENTO_CAMBIO = ("El proyecto abierto cambió (se abrió otro o se restauró una revisión) y no "
                    "se aplicó nada: revísalo antes de seguir.")

_ESPERADO: ContextVar[str | None] = ContextVar("apolo_documento_esperado", default=None)
_TOKENS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_LOCK = threading.Lock()  # HOJA: con él tomado no se adquiere ningún otro lock


def token(doc) -> str:
    """El token de `doc`: estable mientras viva ese objeto, distinto para cualquier otro."""
    with _LOCK:
        valor = _TOKENS.get(doc)
        if valor is None:
            valor = _TOKENS[doc] = secrets.token_hex(8)
        return valor


def esperado() -> str | None:
    """El token que la petición en curso trae en `X-Apolo-Documento` (None = sin cabecera)."""
    return _ESPERADO.get()


@contextmanager
def esperando(valor: str | None) -> Iterator[None]:
    """Fija el token esperado mientras dura el bloque (el job lo re-fija en el worker)."""
    marca = _ESPERADO.set(valor)
    try:
        yield
    finally:
        _ESPERADO.reset(marca)


def verificar(doc) -> None:
    """409 si la petición trae un token y no es el de `doc`. Llamar BAJO `STATE_LOCK`, en la
    misma adquisición que la mutación y antes de tocar nada."""
    valor = _ESPERADO.get()
    if valor is not None and valor != token(doc):
        raise HTTPException(status_code=409, detail=DOCUMENTO_CAMBIO)


class CabeceraDocumento:
    """Middleware ASGI puro: copia `X-Apolo-Documento` al ContextVar de la petición. No
    rechaza nada (eso pasa bajo el lock, en `verificar`) ni toca la respuesta: sin la cabecera
    la petición pasa tal cual. El valor llega a los endpoints `def` (el threadpool copia el
    contexto) y a cada `next()` de un `StreamingResponse` (medido en la F0 del plan)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        valor = None
        if scope["type"] == "http":
            valor = next((v.decode("latin-1") for k, v in scope.get("headers") or ()
                          if k == _CABECERA_ASGI), None)
        if valor is None:
            await self.app(scope, receive, send)
            return
        with esperando(valor):
            await self.app(scope, receive, send)
