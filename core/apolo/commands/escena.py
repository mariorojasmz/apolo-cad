"""La base de la escena: `Feature`, las definiciones compartidas (instancing) y los helpers
que usan todos los executors (`_require`, `_instanced`, `_orient_axis`, `_resolve_sel`).

Salió de `registry.py` (plan partir-nucleo-congelado, F3) SIN cambiar su código; `registry`
re-exporta cada nombre por IDENTIDAD, para siempre: los blobs de la caché de geometría escritos
antes nombran `apolo.commands.registry.Feature` y cargan por ese re-export. No importa ningún
`exec_*` ni `registry`: es la capa de abajo (`escena` ← `exec_*` ← `registry`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apolo.kernel import place

from .errors import CommandError


@dataclass
class Feature:
    id: str
    name: str
    shape: Any
    command_id: str
    visible: bool = True
    component: str | None = None  # referencia de catálogo (BOM)
    cut_length: float | None = None  # longitud de corte si el componente es cortable
    miter: tuple | None = None  # (α1, α2) grados de inglete por extremo (V5.8); None = recto
    # Instancias: si mesh_key no es None, la geometría canónica (compartida) está
    # en DEFINITIONS[mesh_key] y matrix la coloca en el mundo. El shape sigue
    # siendo el sólido mundial (booleanas, STEP, medidas): la instancia solo
    # optimiza teselado y payload.
    mesh_key: str | None = None
    matrix: list | None = None  # 4x4 por filas (kernel.matrix)
    material: str | None = None  # override explícito de material (set_material)
    group: str | None = None  # DERIVADO: sub-ensamblaje al que pertenece (por command_id)
    is_guide: bool = False  # DERIVADO: boceto-guía (blockout) — fuera de BOM/masa/interferencia/FEA
    # Anclas de conexión con nombre (V6.3b): {name: {"origin":[x,y,z], "axis":[x,y,z]}} en
    # coords MUNDO. Las publican los executors al colocar el componente (chumacera→"centro",
    # NMRV→"bore", faja→"eje_motriz"/"eje_cola"); TODO camino que mueva el shape después
    # (mates, transform_group, insert_project) las transforma. REEMPLAZAR el dict, jamás
    # mutarlo in-place (los checkpoints comparten la referencia por el shallow copy).
    anchors: dict | None = None
    # Ficha de CHAPA plegada (plan lista-de-corte-medida, D3): la deja `create_sheet_metal`
    # (`library/chapa_ficha.ficha_chapa`, datos planos) y la heredan sus copias (patrón, espejo,
    # duplicado); la lista de corte y el desplegado sacan de ella el desarrollo. REEMPLAZAR,
    # jamás mutar (los checkpoints comparten la referencia).
    chapa: dict | None = None

    def make_unique(self) -> None:
        """La geometría dejó de ser la canónica (fillet, taladro…)."""
        self.mesh_key = None
        self.matrix = None


# Geometrías canónicas compartidas (centradas en su origen), por clave de contenido.
# Caché LRU (V6.1, Fix A): la evicción saca la MENOS recientemente usada, y un HIT
# (registro o teselado) la "toca" reinsertándola al final. Así una definición con
# instancias VIVAS que se sigue renderizando no la desaloja un registro nuevo (antes
# era FIFO ciego → se perdía el instancing de piezas en uso). El fallback de
# scene_payload cubre igualmente cualquier desalojo (tesela el shape mundial).
DEFINITIONS: dict[str, Any] = {}
_DEFINITIONS_CAP = 256


def register_definition(key: str, shape: Any) -> None:
    if key in DEFINITIONS:
        DEFINITIONS.pop(key)  # touch: reinsertar al final (más recientemente usada)
    elif len(DEFINITIONS) >= _DEFINITIONS_CAP:
        DEFINITIONS.pop(next(iter(DEFINITIONS)))  # evicta la LRU (la primera)
    DEFINITIONS[key] = shape


def touch_definition(key: str) -> None:
    """Marca una definición como recién usada (la reinserta al final). La llama el
    render en cada HIT para que las definiciones EN USO sobrevivan a la evicción LRU."""
    if key in DEFINITIONS:
        DEFINITIONS[key] = DEFINITIONS.pop(key)


Scene = dict[str, Feature]
Joints = dict[str, dict]


def _ancestors(joints: Joints, link: str):
    seen = set()
    current = link
    while True:
        joint = next((j for j in joints.values() if j["child"] == current), None)
        if joint is None or joint["parent"] in seen:
            return seen
        seen.add(joint["parent"])
        current = joint["parent"]


def _require(scene: Scene, feature_id: str) -> Feature:
    if feature_id not in scene:
        raise CommandError(f"No existe el sólido '{feature_id}' en la escena")
    return scene[feature_id]


def _instanced(scene: Scene, cmd_id: str, name: str, base, key: str, position, rotation, **extra) -> None:
    from apolo.kernel.matrix import compose_place

    register_definition(key, base)
    shape = place(base, position, rotation)
    scene[cmd_id] = Feature(
        cmd_id, name, shape, cmd_id,
        mesh_key=key, matrix=compose_place(position, rotation), **extra,
    )


def _orient_axis(base, axis: str):
    """Reorienta una primitiva creada con eje Z para que su eje quede en X o Y."""
    if axis == "x":
        from build123d import Rotation
        return Rotation(0, 90, 0) * base
    if axis == "y":
        from build123d import Rotation
        return Rotation(-90, 0, 0) * base
    return base


def _resolve_sel(shape, selector, kind: str):
    from apolo.kernel.selectors import SelectorError, resolve_edges, resolve_faces

    try:
        if kind == "edge":
            return resolve_edges(shape, selector.model_dump(exclude_none=True))
        return resolve_faces(shape, selector.model_dump(exclude_none=True))
    except SelectorError as exc:
        raise CommandError(str(exc)) from exc
