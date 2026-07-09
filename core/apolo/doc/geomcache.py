"""Caché de geometría por firma (V6.2a): open frío → open caliente.

Abrir un proyecto reproduce el log completo (replay de comandos + teselado). Esta caché
persiste el ESTADO REGENERADO —la 8-tupla del último comando + las definiciones
canónicas usadas por la escena— indexado por la firma acumulada del log, de modo que un
open posterior REANUDA desde el checkpoint final en vez de replayar todo el log.

DÓNDE VIVE: SOLO en la SQLite local (tabla ``geom_cache`` de ``projects.py``), JAMÁS
dentro del ``.apolo``. Dos razones no negociables:
 1. «La geometría nunca se guarda» — el documento sigue siendo el log puro, portable, de
    KBs; el ``.apolo`` no engorda.
 2. Seguridad: el blob usa pickle (copyreg de build123d) y un ``.apolo`` es un archivo que
    el usuario SUBE → despicklear origen no confiable = RCE. La SQLite es local y propia.
Perder la caché solo cuesta un replay: NUNCA es autoritativa (el ``.apolo`` lo es).

Kill-switch: ``APOLO_GEOM_CACHE=0`` desactiva lectura y escritura (ver ``ProjectStore``).

CONTRATO: ni ``pack`` ni ``unpack`` lanzan NUNCA — ante cualquier fallo devuelven None y
el caller cae a replay frío limpio (mismo blindaje que la caché de checkpoints, V6.1).
"""

from __future__ import annotations

import pickle

# Versión del formato del blob. BUMPEAR A MANO cuando cambie:
#  - la estructura del dict serializado, o la 8-tupla de estado (_copy_state), o
#  - un executor que altere la GEOMETRÍA que produce con los MISMOS params (la firma
#    _cmd_sig no lo detecta: depende solo de params, no del código del executor).
# Un bump invalida todas las cachés viejas → replay frío la primera vez. Documentar aquí:
#  v1 (2026-07-09): formato inicial de V6.2a.
GEOM_CACHE_EPOCH = 1


def _versions() -> dict:
    """Versiones de las libs cuya representación binaria de shapes debe coincidir. Un
    upgrade de build123d/OCP puede cambiar el BinTools o la geometría → caché descartada."""
    import importlib.metadata as md

    def v(name: str) -> str:
        try:
            return md.version(name)
        except Exception:
            return "?"

    return {"build123d": v("build123d"), "ocp": v("cadquery-ocp")}


def pack(doc) -> bytes | None:
    """Serializa el estado regenerado del doc (8-tupla final + definiciones canónicas
    usadas por la escena) con su firma acumulada. NO incluye el log (eso vive en el
    ``.apolo``). Devuelve None ante CUALQUIER fallo — un shape no serializable no debe
    tumbar nada. No muta el documento (pickle copia; el estado se aísla con _copy_state)."""
    try:
        from apolo.commands.registry import DEFINITIONS
        from apolo.doc.document import _copy_state

        if not doc._regen_sigs:
            return None  # documento vacío: nada que cachear
        state = _copy_state(
            (
                doc.scene, doc.variables_raw, doc.joints, doc.mates, doc.constraints,
                doc.fasteners, doc.grounds, doc.groups,
            )
        )
        keys = {f.mesh_key for f in doc.scene.values() if f.mesh_key is not None}
        definitions = {k: DEFINITIONS[k] for k in keys if k in DEFINITIONS}
        return pickle.dumps(
            {
                "epoch": GEOM_CACHE_EPOCH,
                "versions": _versions(),
                "sigs": list(doc._regen_sigs),
                "state": state,
                "definitions": definitions,
            },
            protocol=pickle.HIGHEST_PROTOCOL,
        )
    except Exception:
        return None


def unpack(blob: bytes | None) -> tuple[list, tuple, dict] | None:
    """Valida epoch/versiones + sanidad estructural y devuelve ``(sigs, state,
    definitions)``. Devuelve None ante cualquier mismatch o corrupción — el caller cae a
    replay frío limpio. SOLO se llama sobre blobs de la SQLite propia (nunca del .apolo)."""
    if not blob:
        return None
    try:
        data = pickle.loads(blob)
        if not isinstance(data, dict):
            return None
        if data.get("epoch") != GEOM_CACHE_EPOCH:
            return None
        if data.get("versions") != _versions():
            return None
        sigs = data.get("sigs")
        state = data.get("state")
        definitions = data.get("definitions")
        # sanidad estructural mínima: no confiar en el blob (blindaje V6.1)
        if not (
            isinstance(sigs, list)
            and all(isinstance(s, str) for s in sigs)
            and isinstance(state, tuple)
            and len(state) == 8
            and isinstance(state[0], dict)
            and isinstance(definitions, dict)
        ):
            return None
        return sigs, state, definitions
    except Exception:
        return None
