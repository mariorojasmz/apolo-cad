"""Ejecución de lotes de comandos con referencias '$k'.

Compartido por la API HTTP, el agente en modo autónomo y el servidor MCP:
'$k' (k 1-based) en cualquier campo de id de feature referencia al sólido
creado por la k-ésima acción del mismo lote. '$k_<sufijo>' referencia a su hijo
'{id del comando k}_<sufijo>': las piezas de un compuesto (`layout_tablero` crea
`{cmd}_gabinete`, `{cmd}_d_<designación>`… y ninguna `{cmd}`; `insert_project`, `{cmd}_{orig}`).
Dentro de un conjunto de `fasten` ('$1+$2', '($1+c57)[::2]') cada término '$k' se resuelve.
"""

from __future__ import annotations

import re

from apolo.commands.registry import CommandError
from apolo.doc import Document

# D6 de union-en-perfil-hueco: dos de tres modeladores escribieron '$0' y el lote falló sin
# decirles desde dónde se numera.
DESDE_1 = "los resultados se numeran desde $1 (el primer comando del lote)"
_REF_RE = re.compile(r"\$(\d+)(?:_(.+))?")
# D6 de lo-fijo-que-gira-y-lo-que-cuelga: un CONJUNTO de `fasten` ('$1+$2', '($1+c57)[::2]',
# sintaxis de `exec_uniones.resolver_conjunto`) lleva '$k' como TÉRMINO; cada término se resuelve
# por separado. Sólo en un valor con forma de conjunto (con '+' o entre paréntesis), nunca en una
# expresión ('=…') ni en texto libre (con espacios dentro de un término).
_TERMINO = r"[^\s+()\[\]]+"
_CONJUNTO_RE = re.compile(
    rf"\(?\s*{_TERMINO}(?:\s*\+\s*{_TERMINO})*\s*\)?(?:\[[-\d:\s]*\])?"
)
_REF_EN_CONJUNTO = re.compile(rf"(?<![^\s+(])\$\d+(?:_{_TERMINO})?(?![^\s+)\[])")


def _partes(value) -> tuple[int, str | None] | None:
    """(k, sufijo o None) de una referencia '$k' / '$k_<sufijo>'; None si no es una."""
    m = _REF_RE.fullmatch(value) if isinstance(value, str) else None
    return (int(m[1]), m[2]) if m else None


def es_ref(value) -> bool:
    return _partes(value) is not None


def _refs_en_conjunto(value) -> list[str]:
    """Los '$k' que son términos de un conjunto ('$1+$2'); [] si `value` no es un conjunto.

    '$1_perno1+$3' también calza ENTERO en `_REF_RE` (sufijo «perno1+$3»): es conjunto sólo si
    trae más de un '$k'; si no, sigue siendo la referencia de siempre (un id con '+')."""
    if not isinstance(value, str) or value.startswith("="):
        return []
    s = value.strip()
    if ("+" not in s and not s.startswith("(")) or not _CONJUNTO_RE.fullmatch(s):
        return []
    refs = _REF_EN_CONJUNTO.findall(s)
    return refs if len(refs) > 1 or not es_ref(value) else []


def resolve_refs(value, created: list[str | None]):
    if _refs_en_conjunto(value):
        return _REF_EN_CONJUNTO.sub(lambda m: resolve_refs(m[0], created), value)
    if (partes := _partes(value)) is not None:
        idx = partes[0] - 1
        if idx < 0:
            raise CommandError(f"Referencia '{value}' inválida en el lote: {DESDE_1}.")
        if idx >= len(created) or created[idx] is None:
            raise CommandError(
                f"Referencia '{value}' inválida en el lote ({DESDE_1}; sólo vale una acción "
                f"ANTERIOR: aquí van {len(created)})"
            )
        return created[idx] if partes[1] is None else f"{created[idx]}_{partes[1]}"
    if isinstance(value, list):
        return [resolve_refs(v, created) for v in value]
    if isinstance(value, dict):
        return {k: resolve_refs(v, created) for k, v in value.items()}
    return value


def _refs(value):
    if es_ref(value):
        yield value
    elif terminos := _refs_en_conjunto(value):
        yield from terminos
    elif isinstance(value, list):
        for v in value:
            yield from _refs(v)
    elif isinstance(value, dict):
        for v in value.values():
            yield from _refs(v)


def check_refs(actions: list[dict]) -> None:
    """Revisa los '$k' de un lote ANTES de tocar el documento: '$0' y uno fuera del lote dan
    el error con el total del lote y desde dónde se numera."""
    n = len(actions)
    for i, action in enumerate(actions, start=1):
        for ref in _refs(action.get("params") or {}):
            k = _partes(ref)[0]
            if k == 0:
                raise CommandError(f"Referencia '{ref}' inválida en el lote (acción {i}): {DESDE_1}.")
            if k > n:
                raise CommandError(
                    f"Referencia '{ref}' inválida en el lote (acción {i}): el lote tiene {n} "
                    f"acción(es), $1…${n}; {DESDE_1}."
                )


def execute_batch(doc: Document, actions: list[dict], verify=None) -> list[str]:
    """Ejecuta un lote ATÓMICO resolviendo '$k'. Devuelve los cmd_ids. Delega en
    Document.execute_many → UN solo regenerate y UN solo paso de undo para todo el
    lote (antes: un regenerate por acción, O(N²) en booleanas → timeouts).

    `verify` (V6.5b) = contrato opcional del lote: callback ``(scene, created) -> results``
    que, si alguna aserción falla, revierte todo el lote (ContractError)."""
    check_refs(actions)
    return doc.execute_many(actions, verify=verify)
