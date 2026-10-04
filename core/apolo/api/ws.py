"""WebSocket de la API: los clientes conectados y el aviso de «el documento cambió».

Movido tal cual desde `main.py` (F5b del plan `docs/plans/partir-api-main.md`); la ruta
`/ws` sigue en `main`. `notify_changed` es thread-safe (`run_coroutine_threadsafe` sobre el
loop que captura el arranque): lo llaman las mutaciones, el autosave (Timer) y los jobs.
Notificar sólo DESPUÉS de construir el payload.
"""

from __future__ import annotations

import asyncio

from fastapi import WebSocket


class WsManager:
    def __init__(self) -> None:
        self.clients: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.clients:
            self.clients.remove(ws)

    async def _safe_send(self, ws: WebSocket, payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except Exception:
            self.disconnect(ws)  # cliente muerto: se desecha, no se reintenta

    def notify_changed(self, msg: dict | None = None) -> None:
        if not self.loop:
            return
        payload = msg or {"type": "document_changed"}
        for ws in list(self.clients):
            try:
                asyncio.run_coroutine_threadsafe(self._safe_send(ws, payload), self.loop)
            except Exception:
                self.disconnect(ws)  # ni siquiera se pudo programar el envío


WS = WsManager()
