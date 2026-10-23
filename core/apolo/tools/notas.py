"""Las tools MCP de la memoria del agente (notas del proyecto): leer, añadir y corregir o borrar
una nota (F6 de puerta-de-publicacion: las notas viejas que nombraban piezas borradas no se
podían quitar y las largas se cortaban en silencio).

Cliente fino de `GET|POST /api/agent/notes` y `PUT|DELETE /api/agent/notes/{nota}`: las notas
son METADATO del manifest (fuera del log y de la pila de deshacer). Vive fuera de
`mcp_server.py` (congelado por el trinquete de tamaño), que la registra al final con
`registrar(mcp, api)`; NO importa `apolo.mcp_server` (`tests/test_mcp_registro.py`). `api`
busca el `_api` del servidor en CADA llamada, así un test que lo parchea también la ve.
"""

from __future__ import annotations

import json


def registrar(mcp, api) -> None:
    """Registra las tools de notas en `mcp`. `api(method, path, **kw)` es el `_api` del servidor."""

    @mcp.tool()
    def get_agent_notes() -> str:
        """Lee la memoria de sesión del agente (notas del proyecto; la n.º k es notes[k-1])."""
        return json.dumps(api("GET", "/api/agent/notes").json(), ensure_ascii=False)

    @mcp.tool()
    def add_agent_note(text: str) -> str:
        """Añade una nota a la memoria de sesión del agente (tope 30, ≤ 2000 caracteres; persiste
        en el proyecto)."""
        return json.dumps(api("POST", "/api/agent/notes", json={"text": text}).json(),
                          ensure_ascii=False)

    @mcp.tool()
    def edit_agent_note(nota: int, text: str = "", borrar: bool = False) -> str:
        """Corrige o borra la nota número `nota` de la memoria del agente (1 = la primera de
        get_agent_notes; léelas antes: al borrar, las siguientes bajan un número). Con `text`
        la reemplaza (hasta 2000 caracteres); con `borrar=true` la quita, p. ej. una nota
        obsoleta que nombra piezas que ya no existen. Devuelve las notas que quedan."""
        if borrar:
            r = api("DELETE", f"/api/agent/notes/{nota}")
        else:
            r = api("PUT", f"/api/agent/notes/{nota}", json={"text": text})
        return json.dumps(r.json(), ensure_ascii=False)
