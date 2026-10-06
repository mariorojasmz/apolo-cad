"""Los eventos del chat de la app y su formato SSE (plan chat-cliente-igual, F5a).

Es el protocolo que lee `ui/src/chat/sse.ts::validar()`; un tipo nuevo va en los DOS lados y
`tests/test_chat_http.py` compara `TIPOS` con los `case` de ese archivo:

- `text {text}` y `progreso {text}`: los cede `modelo.conversar` (texto y nota de avance);
- `tool {name, etiqueta}`: corre una tool; `etiqueta` es el chip para la persona;
- `actions {actions, executed}`: tarjetas `[{type, params, reason}]`; `executed=False` =
  propuesta pendiente de Aceptar/Rechazar, `True` = lote que el modo auto ya aplicó;
- `aviso {motivo, mensaje}` (de `modelo`), `error {message}` y `done {uso}`, siempre el último.

Una línea `data: <json>` y una vacía por evento; `json.dumps` escapa los saltos de línea, así
que un evento nunca se parte en dos.
"""

from __future__ import annotations

import json

from . import herramientas

TIPOS = ("text", "progreso", "tool", "actions", "aviso", "error", "done")
_USO = ("input", "output", "cache_read", "cache_creation")


def sse(evento: dict) -> str:
    """El evento como lo manda `POST /api/agent/chat`."""
    return f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"


def tool(nombre: str) -> dict:
    return {"type": "tool", "name": nombre, "etiqueta": herramientas.etiqueta(nombre)}


def acciones(actions: list[dict], *, ejecutadas: bool) -> dict:
    """Tarjetas en la forma de la UI (`ChatAction`): sin `reason` va vacío, nunca ausente."""
    tarjetas = [{"type": a.get("type"), "params": a.get("params") or {},
                 "reason": a.get("reason") or ""} for a in actions]
    return {"type": "actions", "actions": tarjetas, "executed": ejecutadas}


def error(mensaje: str) -> dict:
    return {"type": "error", "message": mensaje}


def fin(uso: dict | None = None) -> dict:
    """`done` para un turno que terminó sin llamar al modelo (uso en cero)."""
    return {"type": "done", "uso": uso or dict.fromkeys(_USO, 0)}
