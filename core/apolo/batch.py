"""Ejecución de lotes de comandos con referencias '$k'.

Compartido por la API HTTP, el agente en modo autónomo y el servidor MCP:
'$k' (k 1-based) en cualquier campo de id de feature referencia al sólido
creado por la k-ésima acción del mismo lote.
"""

from __future__ import annotations

from apolo.commands.registry import CommandError
from apolo.doc import Document


def resolve_refs(value, created: list[str | None]):
    if isinstance(value, str) and value.startswith("$") and value[1:].isdigit():
        idx = int(value[1:]) - 1
        if idx < 0 or idx >= len(created) or created[idx] is None:
            raise CommandError(f"Referencia '{value}' inválida en el lote")
        return created[idx]
    if isinstance(value, list):
        return [resolve_refs(v, created) for v in value]
    if isinstance(value, dict):
        return {k: resolve_refs(v, created) for k, v in value.items()}
    return value


def execute_batch(doc: Document, actions: list[dict], verify=None) -> list[str]:
    """Ejecuta un lote ATÓMICO resolviendo '$k'. Devuelve los cmd_ids. Delega en
    Document.execute_many → UN solo regenerate y UN solo paso de undo para todo el
    lote (antes: un regenerate por acción, O(N²) en booleanas → timeouts).

    `verify` (V6.5b) = contrato opcional del lote: callback ``(scene, created) -> results``
    que, si alguna aserción falla, revierte todo el lote (ContractError)."""
    return doc.execute_many(actions, verify=verify)
