"""A qué API habla `mcp_server._api` en ESTE hilo.

El MCP por stdio no fija nada: `actual()` es None y `_api` usa `APOLO_URL`, como siempre. El
chat de la app (plan chat-cliente-igual, D2) corre cada tool con `asyncio.run(mcp.call_tool)`
en su propio hilo y antes la apunta a la API que lo está atendiendo:

    with apuntar(Destino.http("http://127.0.0.1:8000", {"X-Apolo-Documento": token})):
        asyncio.run(mcp.call_tool(nombre, args))

`threading.local`, no ContextVar: lo que un generador de StreamingResponse fija en un `next()`
no llega al siguiente (medido en la F0 del plan). FastMCP corre la tool sync en el hilo que
llama, así que el destino fijado ahí es el que ve `_api`.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import httpx

#: Igual que el cliente del MCP por stdio: bajo los ~180 s del host y sobre los 90 del lote.
TIMEOUT_S = 120


@dataclass(frozen=True)
class Destino:
    """`base_url` nombra el destino en los errores; `abrir()` devuelve el `httpx.Client` ya
    configurado (base_url, timeout, cabeceras) que `_api` usa para UNA petición."""

    base_url: str
    abrir: Callable[[], httpx.Client]

    @classmethod
    def http(cls, base_url: str, cabeceras: dict[str, str] | None = None) -> Destino:
        """Destino loopback del chat: sin proxies del entorno (`trust_env=False`: una variable
        HTTP_PROXY no puede desviar la llamada a la propia API) y con las cabeceras dadas."""
        fijas = dict(cabeceras or {})

        def abrir() -> httpx.Client:
            return httpx.Client(base_url=base_url, timeout=TIMEOUT_S, trust_env=False,
                                headers=fijas)

        return cls(base_url, abrir)


_LOCAL = threading.local()


def actual() -> Destino | None:
    """El destino fijado en este hilo, o None (= el `APOLO_URL` del MCP por stdio)."""
    return getattr(_LOCAL, "destino", None)


@contextlib.contextmanager
def apuntar(destino: Destino) -> Iterator[Destino]:
    """Fija `destino` en este hilo mientras dura el bloque y restaura el anterior al salir,
    también si el bloque lanza (los bloques se pueden anidar)."""
    previo = actual()
    _LOCAL.destino = destino
    try:
        yield destino
    finally:
        _LOCAL.destino = previo
