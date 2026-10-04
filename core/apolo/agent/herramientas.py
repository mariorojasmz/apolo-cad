"""Las tools del chat de la app SON las del MCP (plan chat-cliente-igual, D1, D4, D5).

- `definiciones()`: lo que recibe el modelo, generado de `mcp.list_tools()` en el orden de
  `tools/catalogo.py::CHAT` (fijo: prefijo de caché estable, D12), sin los params ocultos y
  sin `title` (ruido de FastMCP), más `propose_commands`, la única tool propia del chat (D7).
  No depende del modo: las MISMAS definiciones en propuesta y en autónomo (D6).
- `ejecutar()`: corre UNA tool con `mcp.call_tool` —la misma validación, conversión y texto de
  error que ve Claude Code por stdio— apuntada al destino del chat (`tools/destino.py`), en el
  hilo que llama y con un `asyncio.run` privado (D4c: nunca `anyio.from_thread`). Devuelve el
  cuerpo del `tool_result` de Anthropic. El MODO lo hace cumplir el código, no el prompt: en
  propuesta, una tool que muta no corre.

`apolo.mcp_server` se importa perezoso y UNA vez (D4d): FastMCP configura el logger RAÍZ al
construirse (`basicConfig`: INFO + RichHandler, y httpx empezaría a loguear cada request de la
API); se restauran nivel y handlers (spike 4 de la F0). Nada de aquí importa `apolo.state` ni
`apolo.api`: las tools son clientes HTTP, no tocan el documento.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import sys
import threading
from typing import Any

from apolo.tools import catalogo
from apolo.tools.destino import Destino, apuntar

PROPONER = "propose_commands"
ETIQUETA_PROPONER = "Preparando una propuesta"
PROPUESTA, AUTONOMO = "propuesta", "autonomo"
MODOS = (PROPUESTA, AUTONOMO)

#: La declaración de la tool propia del chat. Su ejecución (validarla en seco con
#: `preview(actions, data=true)` por HTTP y mostrar las tarjetas) la hace el chat (F5a).
_PROPONER_DEF: dict = {
    "name": PROPONER,
    "description": (
        "Propone a la persona un lote ORDENADO de comandos CAD como tarjetas de acción: NO se "
        "ejecuta nada hasta que la persona lo acepte. Mismo formato que run_batch "
        "([{type, params, reason}, …]; los parámetros de cada comando, con "
        "get_command_schemas(command_type)). '$k' (1-indexado) referencia la pieza creada por "
        "la k-ésima acción del lote. Antes de mostrarse se ensaya en seco sobre una copia del "
        "documento: si una acción falla recibes el error para corregir y volver a proponer. "
        "Manda TODO el lote en una sola llamada."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "actions": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "description": "Tipo de comando"},
                        "params": {"type": "object",
                                   "description": "Parámetros según el schema del comando"},
                        "reason": {"type": "string",
                                   "description": "Por qué, en una frase, para la persona"},
                    },
                    "required": ["type", "params", "reason"],
                },
            }
        },
        "required": ["actions"],
    },
}

_IMPORTANDO = threading.Lock()
_LISTO = False


def _mcp():
    """El `FastMCP` de `apolo.mcp_server`, importado la primera vez sin dejar el logger raíz
    reconfigurado. El lock evita que dos hilos del chat restauren a destiempo."""
    global _LISTO
    if not _LISTO:
        with _IMPORTANDO:
            if not _LISTO:
                raiz = logging.getLogger()
                nivel, previos = raiz.level, raiz.handlers[:]
                try:
                    importlib.import_module("apolo.mcp_server")
                finally:
                    raiz.handlers[:] = previos
                    raiz.setLevel(nivel)
                _LISTO = True
    return sys.modules["apolo.mcp_server"].mcp


# ------------------------------------------------------------------ definiciones
def _sin_title(nodo: Any) -> Any:
    """Copia de un nodo de JSON Schema sin la palabra clave `title`. Recorre sólo posiciones
    de schema: un PARÁMETRO llamado `title` (clave de `properties`) se conserva."""
    if isinstance(nodo, list):
        return [_sin_title(v) for v in nodo]
    if not isinstance(nodo, dict):
        return nodo
    out: dict = {}
    for clave, valor in nodo.items():
        if clave == "title":
            continue
        if clave == "properties" and isinstance(valor, dict):
            out[clave] = {k: _sin_title(v) for k, v in valor.items()}
        elif clave in ("items", "additionalProperties", "anyOf", "oneOf", "allOf"):
            out[clave] = _sin_title(valor)
        else:  # default, required, type…: datos, se copian tal cual (sin compartir referencias)
            out[clave] = _copia(valor)
    return out


def _copia(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {k: _copia(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_copia(v) for v in valor]
    return valor


def _input_schema(schema: dict, ocultar: tuple[str, ...]) -> dict:
    """El inputSchema de FastMCP sin `title` y sin los params ocultos. Nunca muta el original:
    es el mismo dict que sirve `list_tools()` a los clientes MCP."""
    limpio = _sin_title(schema)
    props = limpio.get("properties", {})
    for p in ocultar:
        props.pop(p, None)
    if "required" in limpio:
        limpio["required"] = [r for r in limpio["required"] if r not in ocultar]
    return limpio


def definiciones() -> list[dict]:
    """Las tools del chat en formato Anthropic ({name, description, input_schema}), en el
    orden del catálogo y con `propose_commands` al final. Deterministas byte a byte."""
    por_nombre = {t.name: t for t in asyncio.run(_mcp().list_tools())}
    out = []
    for nombre, en_chat in catalogo.CHAT.items():
        tool = por_nombre.get(nombre)
        if tool is None:
            raise RuntimeError(f"tools/catalogo.py nombra «{nombre}», que no es una tool del MCP")
        out.append({
            "name": nombre,
            "description": tool.description or "",  # el docstring tal cual lo ve un cliente MCP
            "input_schema": _input_schema(tool.inputSchema, en_chat.ocultar),
        })
    out.append(_copia(_PROPONER_DEF))
    return out


def etiqueta(nombre: str) -> str:
    """El rótulo del chip de la UI mientras corre la tool (el nombre crudo si no se conoce)."""
    if nombre == PROPONER:
        return ETIQUETA_PROPONER
    en_chat = catalogo.CHAT.get(nombre)
    return en_chat.etiqueta if en_chat else nombre


# --------------------------------------------------------------------- ejecutar
def _error(texto: str) -> dict:
    return {"content": [{"type": "text", "text": texto}], "is_error": True}


def _bloque(b: Any) -> dict | None:
    """Un bloque de contenido MCP → bloque de Anthropic (None = texto vacío, se descarta)."""
    if b.type == "text":
        return {"type": "text", "text": b.text} if b.text else None
    if b.type == "image":  # el MCP ya lo trae en base64
        return {"type": "image",
                "source": {"type": "base64", "media_type": b.mimeType, "data": b.data}}
    return {"type": "text", "text": f"[contenido «{b.type}» que el chat no muestra]"}


def ejecutar(nombre: str, entrada: dict | None, destino: Destino, modo: str) -> dict:
    """Corre la tool `nombre` contra `destino` y devuelve el cuerpo de su `tool_result`:
    `{"content": [bloques]}` y, si falló, `"is_error": True` con el MISMO texto que recibe un
    cliente MCP (`str(ToolError)`). Una tool fuera del catálogo, una que muta en modo propuesta
    o un param oculto devuelven `is_error` SIN llamar a la API.

    Corre en el hilo que llama (que no debe tener un event loop corriendo). `propose_commands`
    no pasa por aquí: la atiende el chat."""
    if modo not in MODOS:
        raise ValueError(f"modo desconocido: {modo!r} (usa {PROPUESTA!r} o {AUTONOMO!r})")
    if nombre == PROPONER:
        raise ValueError("propose_commands la atiende el chat, no el MCP")
    en_chat = catalogo.CHAT.get(nombre)
    if en_chat is None:
        motivo = catalogo.FUERA_DEL_CHAT.get(nombre)
        if motivo:
            return _error(f"«{nombre}» no está disponible en el chat: {motivo}.")
        return _error(f"tool desconocida: {nombre}")
    if en_chat.muta and modo == PROPUESTA:
        return _error(
            f"Modo propuesta: «{nombre}» cambia el documento y aquí no se ejecuta. Propón el "
            "cambio con propose_commands; la persona decide si lo aplica."
        )
    entrada = dict(entrada or {})
    vetados = sorted(set(entrada) & set(en_chat.ocultar))
    if vetados:
        return _error(
            f"«{nombre}»: {', '.join(vetados)} no está disponible en el chat (escribiría un "
            "archivo en el servidor). Repite la llamada sin ese parámetro."
        )
    mcp = _mcp()
    from mcp.server.fastmcp.exceptions import ToolError

    with apuntar(destino):
        try:
            salida = asyncio.run(mcp.call_tool(nombre, entrada))
        except ToolError as exc:
            return _error(str(exc))
    # con outputSchema FastMCP devuelve (contenido, estructurado); render_view y preview, la lista
    bloques = salida[0] if isinstance(salida, tuple) else salida
    contenido = [c for c in (_bloque(b) for b in bloques) if c is not None]
    return {"content": contenido or [{"type": "text", "text": "(la tool no devolvió nada)"}]}
