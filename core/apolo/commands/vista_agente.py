"""Vista AGENTE de los schemas publicados (`GET /api/schemas` y `/api/schemas/{type}`).

El enum de un campo `ref` del catálogo trae TODAS sus referencias (las 362 de
`insert_component.component` son 5 KB de los 10 de su schema), y el agente lo paga en contexto
cada vez que consulta el comando (plan mcp-sin-friccion, D3). Esta vista lo cambia, sobre una
COPIA, por cuántas refs son, sus categorías y cómo buscarlas (`get_catalog`). La validación no
cambia: la hace el modelo pydantic en la entrada, con «¿quisiste decir…?».

`command_schemas()` (la del registro) y la vista persona (`vista_persona.py`, que da el
desplegable de la UI) conservan el enum completo.
"""

from __future__ import annotations

import copy

from .registry import command_schemas

#: Un enum más largo que esto, hecho sólo de refs del catálogo, se publica como búsqueda.
MAX_ENUM = 50


def _categorias(refs: list) -> list[str] | None:
    """Las categorías del catálogo de `refs`, o None si alguna no es una ref del catálogo."""
    from apolo.library.catalog import CATALOG

    if not all(isinstance(r, str) and r in CATALOG for r in refs):
        return None
    return sorted({CATALOG[r].category for r in refs})


def _recortar(nodo) -> None:
    if isinstance(nodo, list):
        for v in nodo:
            _recortar(v)
        return
    if not isinstance(nodo, dict):
        return
    refs = nodo.get("enum")
    if isinstance(refs, list) and len(refs) > MAX_ENUM:
        categorias = _categorias(refs)
        if categorias is not None:
            del nodo["enum"]
            ayuda = (f"una de {len(refs)} refs: búscala con get_catalog(category=…, "
                     "names_only=true) en una de las categorías de `x-catalogo`")
            base = nodo.get("description")
            nodo["description"] = f"{base} — {ayuda}" if base else ayuda
            nodo["x-catalogo"] = {"refs": len(refs), "categorias": categorias}
    for v in nodo.values():
        if isinstance(v, (dict, list)):
            _recortar(v)


def schema_agente(entrada: dict) -> dict:
    """Una entrada de `command_schemas()` sin enums gigantes del catálogo (sobre una copia)."""
    e = copy.deepcopy(entrada)
    _recortar(e["schema"])
    return e


def command_schemas_agente(command_type: str | None = None) -> list[dict]:
    """`command_schemas(command_type)` tal como lo lee el agente."""
    return [schema_agente(e) for e in command_schemas(command_type)]
