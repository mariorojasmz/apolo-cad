"""Instanciar un PROYECTO dentro de otro (V5.2b): sandbox replay del snapshot.

`insert_project` embebe el .apolo del proyecto origen como ATTACHMENT del documento
anfitrión (snapshot: el .apolo del layout sigue AUTOCONTENIDO y el regenerate es
determinista/offline; la capa API materializa project_id→attachment). Este módulo
reproduce ese snapshot en un Document SANDBOX aislado — pisando las variables con
`overrides` ANTES del único regenerate, así los namespaces de variables quedan
aislados por construcción — y expone el estado resultante para que el executor lo
vuelque en la escena anfitriona con ids prefijados.

Caché por (digest del snapshot, overrides): N instancias de la misma máquina con los
mismos parámetros = 1 replay por proceso. El estado cacheado es READ-ONLY por
contrato: el executor copia cada Feature/dict antes de emitir y nunca muta shapes
in-place (misma garantía que los checkpoints del regenerate incremental).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

MAX_DEPTH = 3  # A→B→C→D permitido; más niveles = error claro (cadenas patológicas)
_depth = 0  # nivel de anidamiento del replay en curso (STATE_LOCK serializa el acceso)
_CACHE: dict[tuple, "SubprojectState"] = {}
_CACHE_CAP = 8  # FIFO, como DEFINITIONS: acota la memoria de shapes OCCT retenidos


class SubprojectError(Exception):
    pass


@dataclass
class SubprojectState:
    """Estado PRÍSTINO del snapshot regenerado, en coordenadas-mundo del origen."""

    scene: dict
    joints: dict
    constraints: dict
    fasteners: dict
    grounds: dict
    groups: dict
    variables: dict[str, str]  # raw del origen (mensajes de error / consulta)
    key_hash: str  # hash corto (digest+overrides) para claves de DEFINITIONS


def build_subproject(data: bytes, overrides: dict | None) -> SubprojectState:
    """Reproduce el snapshot .apolo con los `overrides` de variables aplicados.

    Los overrides llegan ya RESUELTOS a número por el documento anfitrión
    (resolve_params corre antes de validar) y se escriben como literal sobre los
    `set_variable` del log del snapshot. Nombre desconocido → error listando las
    variables disponibles del origen."""
    global _depth

    digest = hashlib.sha256(data).hexdigest()
    key = (
        digest,
        tuple(sorted((str(k), float(v)) for k, v in (overrides or {}).items())),
    )
    hit = _CACHE.get(key)
    if hit is not None:
        return hit
    if _depth >= MAX_DEPTH:
        raise SubprojectError(
            f"Se superó la profundidad máxima de proyectos anidados ({MAX_DEPTH} niveles)"
        )
    from apolo.doc.document import Document, DocumentError

    _depth += 1
    try:
        try:
            doc = Document.from_apolo_bytes(data, regenerate=False)
        except DocumentError as exc:
            raise SubprojectError(f"Snapshot inválido: {exc}") from exc
        _apply_overrides(doc.commands, overrides or {})
        try:
            doc.regenerate()
        except DocumentError as exc:
            raise SubprojectError(f"El proyecto instanciado no regenera: {exc}") from exc
    finally:
        _depth -= 1
    state = SubprojectState(
        scene=doc.scene,
        joints=doc.joints,
        constraints=doc.constraints,
        fasteners=doc.fasteners,
        grounds=doc.grounds,
        groups=doc.groups,
        variables=dict(doc.variables_raw),
        key_hash=hashlib.sha256(repr(key).encode()).hexdigest()[:8],
    )
    if len(_CACHE) >= _CACHE_CAP:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = state
    return state


def _apply_overrides(commands: list[dict], overrides: dict) -> None:
    if not overrides:
        return
    available = [
        c["params"].get("name") for c in commands if c.get("type") == "set_variable"
    ]
    unknown = sorted(set(overrides) - set(available))
    if unknown:
        listado = ", ".join(sorted(v for v in available if v)) or "(ninguna)"
        raise SubprojectError(
            f"El override '{unknown[0]}' no es una variable del proyecto instanciado "
            f"(disponibles: {listado})"
        )
    for cmd in commands:
        if cmd.get("type") == "set_variable" and cmd["params"].get("name") in overrides:
            name = cmd["params"]["name"]
            cmd["params"] = {"name": name, "expression": repr(float(overrides[name]))}
