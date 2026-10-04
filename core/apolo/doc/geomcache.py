"""Caché de geometría por firma (V6.2a): open frío → open caliente.

Abrir un proyecto reproduce el log completo (replay de comandos + teselado). Esta caché
persiste el ESTADO REGENERADO —el ``RegenState`` del último comando, guardado POR NOMBRE
de campo, + las definiciones canónicas usadas por la escena— indexado por la firma
acumulada del log, de modo que un
open posterior REANUDA desde el checkpoint final en vez de replayar todo el log.

DÓNDE VIVE: SOLO en la SQLite local (tabla ``geom_cache`` de ``projects.py``), JAMÁS
dentro del ``.apolo``. Dos razones no negociables:
 1. «La geometría nunca se guarda» — el documento sigue siendo el log puro, portable, de
    KBs; el ``.apolo`` no engorda.
 2. Seguridad: el blob usa pickle y un ``.apolo`` es un archivo que el usuario SUBE →
    despicklear origen no confiable = RCE. La SQLite es local y propia.
Perder la caché solo cuesta un replay: NUNCA es autoritativa (el ``.apolo`` lo es).

SERIALIZACIÓN de shapes: los shapes van como bytes de BinTools (``serialize_shape`` sobre
el ``TopoDS_Shape`` crudo), NO picklando el wrapper de build123d. El wrapper puede llevar
estado build123d (``joints``/``children``) que NO round-trip-ea por pickle (revienta al
deserializar en ciertas piezas); el BinTools del TopoDS crudo sí es fiable. Al restaurar,
el shape se re-envuelve por su tipo TopoDS (Solid/Compound/…): las operaciones de Apolo
(volumen/bbox/teselado/booleanas) son de ``Shape``, la subclase primitiva no importa.

Kill-switch: ``APOLO_GEOM_CACHE=0`` desactiva lectura y escritura (ver ``ProjectStore``).

CONTRATO: ni ``pack`` ni ``unpack`` lanzan NUNCA — ante cualquier fallo devuelven None y
el caller cae a replay frío limpio (mismo blindaje que la caché de checkpoints, V6.1).
"""

from __future__ import annotations

import pickle

from apolo.commands.state import RegenState

# Versión del formato del blob. BUMPEAR A MANO cuando cambie:
#  - la estructura del dict serializado, o los campos de `RegenState` (commands/state.py), o
#  - la GEOMETRÍA con los MISMOS params por algo que no se acota a ciertos comandos (kernel,
#    builders, catálogo, `Feature`). UN executor cambiado NO es bump: sube su `version` (D9/D10).
# Un bump invalida todas las cachés viejas → replay frío la primera vez. Documentar aquí:
#  v1 (2026-07-09): formato inicial de V6.2a.
#  v2 (2026-07-09): shapes por BinTools crudo (antes: pickle del wrapper build123d, frágil).
#  v3 (2026-07-09): V6.3b — Feature.anchors nuevo campo; un ckpt viejo restauraría Features
#    SIN anclas mientras el replay frío las tendría → invalidar (el open re-puebla).
#  v4 (2026-10-03): bump ATRASADO — desde v3 cambiaron salidas de executors con los MISMOS
#    params sin bumpear (V6.3d anclas en copias/world_move, V6.5b/c join_bolted: tuerca DIN
#    934 + largo de perno con filetes, V6.8-D arrastre de juntas, V6.8-E snap cara-a-cara,
#    V7.2b…) → un open caliente podía servir geometría vieja. Desde aquí `_versions()`
#    incluye la versión del paquete Apolo: un upgrade de PyPI invalida solo; el bump manual
#    sigue haciendo falta para cambios de executor DENTRO de una misma versión (checkout).
#  v5 (2026-10-03): el estado del checkpoint deja de ser la 8-tupla posicional y pasa a
#    `RegenState`, guardado en el blob como dict POR NOMBRE (`to_plain`/`from_plain`): un
#    blob v4 trae la tupla y no se puede leer → replay frío la primera vez (plan
#    estado-regen-y-params-estrictos, D2).
GEOM_CACHE_EPOCH = 5


def _apolo_version() -> str:
    """Versión del paquete Apolo: metadata de la distribución instalada (``apolo-cad``,
    autoritativa en un wheel de PyPI) → ``apolo.__version__`` (checkout sin instalar) →
    «?». Nunca lanza: una versión ilegible solo cuesta un replay, jamás un error."""
    import importlib.metadata as md

    try:
        return md.version("apolo-cad")
    except Exception:
        pass
    try:
        import apolo

        return str(apolo.__version__)
    except Exception:
        return "?"


def _versions() -> dict:
    """Versiones cuya representación binaria/geometría debe coincidir. Un upgrade de
    build123d/OCP puede cambiar el BinTools o la geometría; uno de Apolo, la salida de
    los executors con los mismos params → en ambos casos la caché se descarta."""
    import importlib.metadata as md

    def v(name: str) -> str:
        try:
            return md.version(name)
        except Exception:
            return "?"

    return {"build123d": v("build123d"), "ocp": v("cadquery-ocp"), "apolo": _apolo_version()}


def _serialize_robust(shape) -> bytes | None:
    """Serializa un ``TopoDS_Shape`` a bytes que GARANTIZADO deserializan. BinTools es
    caprichoso por-shape: ``serialize_shape`` siempre da bytes, pero ``deserialize_shape``
    revienta (``BinTools_ShapeSet::ReadGeometry`` / ``NCollection_IndexedMap`` fuera de
    rango) para ciertos shapes — y CUÁLES depende del shape: unos round-trip-ean crudos y
    otros solo tras una copia profunda (``BRepBuilderAPI_Copy`` aplana las refs de
    geometría), pero la copia ROMPE a los primeros. Por eso: intenta crudo, VERIFICA
    deserializando (el fallo salta al LEER, no al escribir); si falla, intenta la copia y
    verifica; si ninguno round-trip-ea, None → pack entero cae y se replaya en frío."""
    from build123d.persistence import deserialize_shape, serialize_shape

    def _ok(candidate) -> bytes | None:
        blob = serialize_shape(candidate)
        if blob is None:
            return None
        try:
            deserialize_shape(blob)  # el fallo de BinTools ocurre al LEER, no al escribir
        except Exception:
            return None
        return blob

    blob = _ok(shape)
    if blob is not None:
        return blob
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy

    copier = BRepBuilderAPI_Copy(shape)
    copier.Perform(shape)
    return _ok(copier.Shape())


def _wrap_topods(topods):
    """Envuelve un ``TopoDS_Shape`` crudo en el tipo de build123d que corresponde a su
    ShapeType (Solid/Compound/…). Todas las ops de Apolo son de ``Shape``, así que la
    subclase PRIMITIVA original (Box/Cylinder) no importa — solo la familia topológica."""
    import build123d as bd
    from OCP.TopAbs import (
        TopAbs_COMPOUND, TopAbs_COMPSOLID, TopAbs_EDGE, TopAbs_FACE, TopAbs_SHELL,
        TopAbs_SOLID, TopAbs_VERTEX, TopAbs_WIRE,
    )

    cls = {
        TopAbs_COMPOUND: bd.Compound, TopAbs_COMPSOLID: bd.Compound,
        TopAbs_SOLID: bd.Solid, TopAbs_SHELL: bd.Shell, TopAbs_FACE: bd.Face,
        TopAbs_WIRE: bd.Wire, TopAbs_EDGE: bd.Edge, TopAbs_VERTEX: bd.Vertex,
    }.get(topods.ShapeType(), bd.Shape)
    return cls(topods)


def pack(doc) -> bytes | None:
    """Serializa el estado regenerado del doc (``RegenState`` POR NOMBRE + definiciones
    canónicas usadas por la escena) con su firma. Los shapes van como bytes de BinTools
    (crudos), NO picklando el wrapper. NO incluye el log (vive en el ``.apolo``). Devuelve
    None ante CUALQUIER fallo. No muta el documento (se picklea una COPIA de los Features
    con ``shape=None``).

    V6.2e: empaca el checkpoint ORGÁNICO del ÚLTIMO comando (``_regen_ckpts[len-1]``, capturado
    DENTRO del bucle de regenerate, ANTES de la finalización: solve_mates/assign_groups), NO el
    estado post-finalización. Sembrar un ckpt post-mates desplazaría la geometría base → la cola
    (caso prefijo o un comando nuevo tras el open) ejecutaría contra shapes ya movidos por los
    mates y los selectores sensibles a posición (near/cara/center_in) diferirían del replay frío.
    Fix 4: un doc con comandos SUPRIMIDOS (carga tolerante) NO se cachea (el warm posterior
    reportaría suppressed=[] enmascarando el chip y podría servir una escena sin la pieza)."""
    try:
        from apolo.commands.registry import DEFINITIONS

        if not doc._regen_sigs:
            return None  # documento vacío: nada que cachear
        if getattr(doc, "regen_suppressed", None):
            return None  # Fix 4: doc tolerante con comandos rotos → jamás cachear
        ckpt = doc._regen_ckpts.get(len(doc.commands) - 1)  # Fix 3: ckpt ORGÁNICO (pre-mates)
        if ckpt is None:
            return None  # sin ckpt del último comando (ckpts purgados) → replay frío
        state = ckpt.copy()  # aísla ANTES de vaciar shapes (no corromper el ckpt del doc)
        scene = state.scene  # dict fid -> Feature (COPIAS: shape compartido, seguro de vaciar)
        scene_shapes: dict[str, bytes] = {}
        for fid, feat in scene.items():
            blob = _serialize_robust(feat.shape.wrapped)
            if blob is None:  # serialize_shape devuelve None ante fallo (no lanza)
                return None
            scene_shapes[fid] = blob
            feat.shape = None  # el Feature se picklea SIN el wrapper frágil
        keys = {f.mesh_key for f in scene.values() if f.mesh_key is not None}
        definitions: dict[str, bytes] = {}
        for k in keys:
            if k in DEFINITIONS:
                blob = _serialize_robust(DEFINITIONS[k].wrapped)
                if blob is not None:
                    definitions[k] = blob
        return pickle.dumps(
            {
                "epoch": GEOM_CACHE_EPOCH,
                "versions": _versions(),
                "sigs": list(doc._regen_sigs),
                "state": state.to_plain(),  # {campo: dict}; Features con shape=None
                "scene_shapes": scene_shapes,  # fid -> bytes (BinTools del TopoDS crudo)
                "definitions": definitions,    # mesh_key -> bytes
            },
            protocol=pickle.HIGHEST_PROTOCOL,
        )
    except Exception:
        return None


def unpack(blob: bytes | None) -> tuple[list, RegenState, dict] | None:
    """Valida epoch/versiones + sanidad estructural, reconstruye los shapes (BinTools) y
    devuelve ``(sigs, state, definitions)``. Devuelve None ante cualquier mismatch o
    corrupción. SOLO se llama sobre blobs de la SQLite propia (nunca del .apolo)."""
    if not blob:
        return None
    try:
        from build123d.persistence import deserialize_shape

        data = pickle.loads(blob)  # el state NO lleva shapes → pickle no toca BinTools aquí
        if not isinstance(data, dict):
            return None
        if data.get("epoch") != GEOM_CACHE_EPOCH:
            return None
        if data.get("versions") != _versions():
            return None
        sigs = data.get("sigs")
        scene_shapes = data.get("scene_shapes")
        definitions = data.get("definitions")
        if not (
            isinstance(sigs, list)
            and all(isinstance(s, str) for s in sigs)
            and isinstance(scene_shapes, dict)
            and isinstance(definitions, dict)
        ):
            return None
        state = RegenState.from_plain(data.get("state"))  # otro formato → ValueError → None
        scene = state.scene
        for fid, feat in scene.items():
            raw = scene_shapes.get(fid)
            if raw is None:  # falta el shape de una feature → caché inservible
                return None
            feat.shape = _wrap_topods(deserialize_shape(raw))
        defs = {k: _wrap_topods(deserialize_shape(b)) for k, b in definitions.items()}
        return sigs, state, defs
    except Exception:
        return None
