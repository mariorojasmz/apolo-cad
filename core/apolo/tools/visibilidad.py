"""Tools MCP de visibilidad: mostrar u ocultar sólidos del documento.

Bloque de `mcp_server.py` movido tal cual, con 4 espacios más de sangría (plan
partir-nucleo-congelado, F1). `mcp_server` llama `registrar` EN EL LUGAR del bloque con
`globals().update(...)`: el orden de `list_tools()` no cambia y cada tool sigue siendo un
atributo de `apolo.mcp_server`. NO importa `apolo.mcp_server` (con `-m` el servidor es
`__main__`: `tests/test_mcp_registro.py`). `_api`: lambdas que buscan el del servidor en
CADA llamada (un test que lo parchea por nombre también llega aquí). Importa lo que nombran
las anotaciones: FastMCP las evalúa.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from apolo.brief import _scene_brief


def registrar(mcp, _api) -> dict[str, Callable]:
    """Registra en `mcp` (el del servidor que corre) las tools de `visibilidad` y las
    devuelve por nombre para que `mcp_server` las re-exporte."""

    @mcp.tool()
    def set_visibility(feature_id: str, visible: bool) -> str:
        """Muestra u oculta un sólido individual (útil para aislar antes de render_view)."""
        payload = _api("POST", f"/api/features/{feature_id}/visibility", json={"visible": visible}).json()
        return json.dumps(_scene_brief(payload), ensure_ascii=False)

    @mcp.tool()
    def set_visibility_bulk(feature_ids: list[str], visible: bool) -> str:
        """Muestra u oculta varios sólidos a la vez (patrón aislar / mostrar todo)."""
        payload = _api("POST", "/api/features/visibility", json={"ids": feature_ids, "visible": visible}).json()
        return json.dumps(_scene_brief(payload), ensure_ascii=False)

    return {f.__name__: f for f in (set_visibility, set_visibility_bulk,)}
