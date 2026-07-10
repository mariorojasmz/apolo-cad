"""Registro de comandos: validación, ejecución y schemas.

Cada comando declara su modelo de parámetros (pydantic) y un ejecutor que
muta la escena. El documento reproduce el log de comandos en orden para
regenerar la escena completa.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from apolo.kernel import (
    boolean_op,
    linear_copy,
    make_box,
    make_cylinder,
    make_structural_profile,
    move_rotated_about_center,
    place,
)

from .expressions import ExpressionError, resolve_all, resolve_params
from .models import (
    AddConstraintParams,
    AddJointParams,
    AddJoineryParams,
    AddMateParams,
    AddRailConstraintParams,
    AttachParams,
    BooleanOpParams,
    BoundarySurfaceParams,
    CenterInParams,
    ChamferParams,
    CreateBeltConveyorParams,
    CreateBoxParams,
    CreateConveyorParams,
    CreateCylinderParams,
    CreateExtrudePolyParams,
    CreateFrameParams,
    CreateRevolveParams,
    CreateRobotArmParams,
    CreateDriveRollerParams,
    CreateTakeUpParams,
    CreateWeldmentParams,
    CreateStructuralProfileParams,
    CreateGroupParams,
    DeleteFacesParams,
    DeleteParams,
    DistributeParams,
    DuplicateParams,
    DrillHoleParams,
    FastenParams,
    FillSurfaceParams,
    FilletParams,
    GroundParams,
    ImportStepParams,
    InsertComponentParams,
    InsertProjectParams,
    MirrorParams,
    PatternCircularParams,
    PatternGroupParams,
    PatternLinearParams,
    PushFaceParams,
    RunScriptParams,
    SetVariableParams,
    SheetMetalParams,
    ShellParams,
    SketchExtrudeParams,
    SketchLoftParams,
    SketchRevolveParams,
    SketchSweepParams,
    ThickenParams,
    TransformGroupParams,
    TransformParams,
)


class CommandError(Exception):
    pass


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


def _exec_create_box(scene: Scene, cmd_id: str, p: CreateBoxParams) -> None:
    key = f"box|{p.width:g}|{p.depth:g}|{p.height:g}"
    _instanced(scene, cmd_id, p.name, make_box(p.width, p.depth, p.height), key,
               p.position.tuple(), p.rotation.tuple())


def _exec_create_cylinder(scene: Scene, cmd_id: str, p: CreateCylinderParams) -> None:
    key = f"cyl|{p.radius:g}|{p.height:g}|{p.axis}"
    _instanced(scene, cmd_id, p.name, _orient_axis(make_cylinder(p.radius, p.height), p.axis), key,
               p.position.tuple(), p.rotation.tuple())


def _exec_create_profile(scene: Scene, cmd_id: str, p: CreateStructuralProfileParams) -> None:
    try:
        base = make_structural_profile(p.profile, p.length)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
    key = f"prof|{p.profile}|{p.length:g}"
    _instanced(scene, cmd_id, p.name, base, key, p.position.tuple(), p.rotation.tuple())


def _exec_boolean(scene: Scene, cmd_id: str, p: BooleanOpParams) -> None:
    target = _require(scene, p.target)
    tools = [_require(scene, t) for t in p.tools]
    if p.target in p.tools:
        raise CommandError("El objetivo no puede ser también herramienta")
    result = boolean_op(p.operation, target.shape, [t.shape for t in tools])
    if result is None or (hasattr(result, "volume") and result.volume <= 0):
        raise CommandError("La operación booleana produjo un sólido vacío")
    del scene[p.target]
    for t in p.tools:
        del scene[t]
    scene[cmd_id] = Feature(cmd_id, p.name, result, cmd_id)


def _world_move(feat: Feature, translate, rotate) -> None:
    """Aplica la transformación mundial al shape y, si la feature es una
    instancia, compone también su matriz (W = T·T(c)·R·T(-c))."""
    if feat.matrix is not None:
        from apolo.kernel.matrix import multiply, rotation_about_center, translation

        bb = feat.shape.bounding_box()
        center = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
        w = translation(*translate)
        if any(rotate):
            w = multiply(w, rotation_about_center(center, rotate))
        feat.matrix = multiply(w, feat.matrix)
    feat.shape = move_rotated_about_center(feat.shape, translate, rotate)


def _exec_transform(scene: Scene, cmd_id: str, p: TransformParams) -> None:
    feat = _require(scene, p.feature)
    _world_move(feat, p.translate.tuple(), p.rotate.tuple())


def _bbox_center(shape):
    bb = shape.bounding_box()
    return ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)


def _exec_center_in(scene: Scene, cmd_id: str, p: CenterInParams) -> None:
    """Centra `feature` dentro de `into` en los ejes pedidos (mueve en sitio). Se reevalúa
    al regenerar → si `into` cambia, el sólido se recentra solo."""
    if p.feature == p.into:
        raise CommandError("Un sólido no puede centrarse dentro de sí mismo")
    feat = _require(scene, p.feature)
    cont = _require(scene, p.into)
    fc = _bbox_center(feat.shape)
    cc = _bbox_center(cont.shape)
    idx = {"x": 0, "y": 1, "z": 2}
    t = [0.0, 0.0, 0.0]
    for ax in p.axes:
        i = idx[ax]
        t[i] = cc[i] - fc[i]
    _world_move(feat, tuple(t), (0, 0, 0))


def _exec_distribute(scene: Scene, cmd_id: str, p: DistributeParams) -> None:
    """Reparte los `features` con centros equiespaciados de `start` a `end` en `axis`
    (mueve cada uno en sitio). Colocación por intención, no por coordenadas calculadas."""
    feats = [_require(scene, fid) for fid in p.features]
    n = len(feats)
    if n < 2:
        raise CommandError("distribute necesita al menos 2 sólidos")
    i_ax = {"x": 0, "y": 1, "z": 2}[p.axis]
    span = p.end - p.start
    for i, feat in enumerate(feats):
        target = p.start + span * i / (n - 1)
        c = _bbox_center(feat.shape)[i_ax]
        t = [0.0, 0.0, 0.0]
        t[i_ax] = target - c
        _world_move(feat, tuple(t), (0, 0, 0))


def _exec_pattern(scene: Scene, cmd_id: str, p: PatternLinearParams) -> None:
    from apolo.kernel.matrix import multiply, translation

    feat = _require(scene, p.feature)
    if p.spacing.tuple() == (0, 0, 0):
        raise CommandError("La separación del patrón no puede ser cero")
    sx, sy, sz = p.spacing.tuple()
    for i in range(1, p.count):
        copy = linear_copy(feat.shape, i, p.spacing.tuple())
        fid = f"{cmd_id}_{i}"
        matrix = (
            multiply(translation(sx * i, sy * i, sz * i), feat.matrix)
            if feat.matrix is not None
            else None
        )
        scene[fid] = Feature(
            fid, f"{feat.name} ({i + 1})", copy, cmd_id,
            component=feat.component, cut_length=feat.cut_length,
            mesh_key=feat.mesh_key if matrix is not None else None, matrix=matrix,
        )


_PATTERN_GROUP_MAX = 2000  # tope de sólidos generados por pattern_group (protege OCCT)


def _exec_pattern_group(scene: Scene, joints, mates, cmd_id: str, p: PatternGroupParams) -> None:
    """Arraya todas las features del comando `source` en línea (count/spacing) y opcional
    rejilla (count2/spacing2). Bloquea si la fuente está referenciada por juntas/mates."""
    from apolo.kernel.matrix import multiply, translation

    src = [f for f in scene.values() if f.command_id == p.source]
    if not src:
        raise CommandError(f"El comando '{p.source}' no creó ninguna geometría que arrayar")
    src_ids = {f.id for f in src}
    for jt in joints.values():
        if jt["parent"] in src_ids or jt["child"] in src_ids:
            raise CommandError(
                f"pattern_group no puede arrayar '{p.source}': la junta '{jt['name']}' lo "
                "referencia. Arraya solo geometría (sin juntas/mates en la fuente)."
            )
    for mt in mates.values():
        if mt["feature_a"] in src_ids or mt["feature_b"] in src_ids:
            raise CommandError(
                f"pattern_group no puede arrayar '{p.source}': el mate '{mt['name']}' lo "
                "referencia. Arraya solo geometría (sin juntas/mates en la fuente)."
            )
    s1, s2 = p.spacing.tuple(), p.spacing2.tuple()
    if p.count > 1 and s1 == (0, 0, 0):
        raise CommandError("La separación (eje 1) del patrón no puede ser cero")
    if p.count2 > 1 and s2 == (0, 0, 0):
        raise CommandError("La separación (eje 2) del patrón no puede ser cero")
    total = (p.count * p.count2 - 1) * len(src)
    if total > _PATTERN_GROUP_MAX:
        raise CommandError(
            f"pattern_group generaría {total} sólidos (tope {_PATTERN_GROUP_MAX}); "
            "reduce count/count2 o usa una fuente más pequeña"
        )
    for i in range(p.count):
        for k in range(p.count2):
            if i == 0 and k == 0:
                continue  # la instancia original ya existe en la escena
            off = (s1[0] * i + s2[0] * k, s1[1] * i + s2[1] * k, s1[2] * i + s2[2] * k)
            for feat in src:
                copy = linear_copy(feat.shape, 1, off)
                suffix = (
                    feat.id[len(p.source) + 1:] if feat.id.startswith(p.source + "_") else feat.id
                )
                fid = f"{cmd_id}_{i}_{k}_{suffix}"
                matrix = (
                    multiply(translation(*off), feat.matrix) if feat.matrix is not None else None
                )
                scene[fid] = Feature(
                    fid, f"{feat.name} ({i + 1},{k + 1})", copy, cmd_id,
                    component=feat.component, cut_length=feat.cut_length,
                    mesh_key=feat.mesh_key if matrix is not None else None, matrix=matrix,
                )


def _exec_delete(scene: Scene, cmd_id: str, p: DeleteParams) -> None:
    _require(scene, p.feature)
    del scene[p.feature]


def _exec_duplicate(scene: Scene, cmd_id: str, p: DuplicateParams) -> None:
    from apolo.kernel.matrix import multiply, translation

    feat = _require(scene, p.feature)
    off = p.offset.tuple()
    copy = linear_copy(feat.shape, 1, off)  # clona y traslada por el desfase
    matrix = (
        multiply(translation(*off), feat.matrix) if feat.matrix is not None else None
    )
    scene[cmd_id] = Feature(
        cmd_id, f"{feat.name} (copia)", copy, cmd_id,
        component=feat.component, cut_length=feat.cut_length,
        mesh_key=feat.mesh_key if matrix is not None else None, matrix=matrix,
    )


def _exec_set_variable(variables: dict, cmd_id: str, p: SetVariableParams) -> None:
    variables[p.name] = p.expression


def _resolve_sel(shape, selector, kind: str):
    from apolo.kernel.selectors import SelectorError, resolve_edges, resolve_faces

    try:
        if kind == "edge":
            return resolve_edges(shape, selector.model_dump(exclude_none=True))
        return resolve_faces(shape, selector.model_dump(exclude_none=True))
    except SelectorError as exc:
        raise CommandError(str(exc)) from exc


def _exec_delete_faces(scene: Scene, cmd_id: str, p: DeleteFacesParams) -> None:
    """Modelado directo (V5.3): borra caras y cura el hueco. Muta EN SITIO
    (conserva feature_id — mates/juntas sobreviven)."""
    from apolo.kernel.direct import DirectError, expand_tangent, remove_faces

    feat = _require(scene, p.feature)
    if p.faces.mode == "todas":
        raise CommandError(
            "Borrar TODAS las caras destruiría el sólido: usa delete_feature, o un "
            "selector acotado (cerca/cara/direccion)"
        )
    faces = _resolve_sel(feat.shape, p.faces, "face")
    try:
        if p.tangentes:
            faces = expand_tangent(feat.shape, faces)
        result = remove_faces(feat.shape, faces)
    except DirectError as exc:
        raise CommandError(
            f"No se pudo curar el hueco de {len(faces)} cara(s): {exc}"
        ) from exc
    feat.shape = result
    feat.make_unique()


def _exec_push_face(scene: Scene, cmd_id: str, p: PushFaceParams) -> None:
    """Modelado directo (V5.3): empuja/jala una cara plana. Muta EN SITIO."""
    from apolo.kernel.direct import DirectError, push_pull

    feat = _require(scene, p.feature)
    faces = _resolve_sel(feat.shape, p.face, "face")
    if len(faces) != 1:
        raise CommandError(
            f"push_face necesita EXACTAMENTE una cara y tu selector devolvió "
            f"{len(faces)}: usa cerca con count=1 o cara del bbox"
        )
    try:
        result = push_pull(feat.shape, faces[0], p.distance)
    except DirectError as exc:
        raise CommandError(str(exc)) from exc
    feat.shape = result
    feat.make_unique()


def _shortest_edge_mm(edges) -> float | None:
    """Longitud de la arista más corta de la selección (None si no se puede medir).
    Da el TOPE accionable de un radio/distancia cuando OCCT rechaza la operación."""
    try:
        return min(e.length for e in edges)
    except Exception:
        return None


def _exec_fillet(scene: Scene, cmd_id: str, p: FilletParams) -> None:
    from build123d import fillet

    feat = _require(scene, p.feature)
    edges = _resolve_sel(feat.shape, p.edges, "edge")
    try:
        result = fillet(edges, radius=p.radius)
    except Exception as exc:
        # Fix H (V6.1): mensaje accionable con el tope real en vez del crudo C++
        short = _shortest_edge_mm(edges)
        tope = (f" La arista más corta seleccionada mide {short:.1f} mm; el radio debe ser "
                f"bastante menor que eso.") if short else ""
        raise CommandError(
            f"Redondeo imposible (radio {p.radius:g} mm en {len(edges)} aristas): prueba un radio "
            f"menor o menos aristas.{tope}"
        ) from exc
    feat.shape = result
    feat.make_unique()


def _exec_chamfer(scene: Scene, cmd_id: str, p: ChamferParams) -> None:
    from build123d import chamfer

    feat = _require(scene, p.feature)
    edges = _resolve_sel(feat.shape, p.edges, "edge")
    try:
        result = chamfer(edges, length=p.distance)
    except Exception as exc:
        short = _shortest_edge_mm(edges)
        tope = (f" La arista más corta seleccionada mide {short:.1f} mm; la distancia debe ser "
                f"menor.") if short else ""
        raise CommandError(
            f"Chaflán imposible (distancia {p.distance:g} mm en {len(edges)} aristas): prueba una "
            f"distancia menor.{tope}"
        ) from exc
    feat.shape = result
    feat.make_unique()


def _exec_shell(scene: Scene, cmd_id: str, p: ShellParams) -> None:
    from build123d import offset

    feat = _require(scene, p.feature)
    # Fix H (V6.1): pre-check barato — un espesor que se come más de la mitad de la
    # dimensión MENOR deja la pieza sin cavidad (condición NECESARIA, sin falsos
    # positivos: solo rechaza lo que igual saldría vacío). Mensaje limpio antes de OCCT.
    bb = feat.shape.bounding_box()
    min_dim = min(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
    if 2 * p.thickness >= min_dim:
        raise CommandError(
            f"Vaciado imposible: un espesor de {p.thickness:g} mm no cabe en la pieza "
            f"(su dimensión menor es {min_dim:.1f} mm; el espesor debe ser < {min_dim / 2:.1f} mm)"
        )
    openings = _resolve_sel(feat.shape, p.openings, "face")
    try:
        result = offset(feat.shape, amount=-p.thickness, openings=openings)
    except Exception as exc:
        raise CommandError(
            f"Vaciado imposible con espesor {p.thickness:g} mm: prueba un espesor menor. Detalle: {exc}"
        ) from exc
    if result.volume <= 0:
        raise CommandError("El vaciado produjo un sólido vacío")
    feat.shape = result
    feat.make_unique()


_DRILL_DIRS = {
    "x": (1, 0, 0), "-x": (-1, 0, 0),
    "y": (0, 1, 0), "-y": (0, -1, 0),
    "z": (0, 0, 1), "-z": (0, 0, -1),
}


def _drill_tool(diameter: float, length: float, entry, direction):
    from build123d import Cylinder, Pos, Rotation

    cyl = Cylinder(diameter / 2.0, length)
    if abs(direction[0]):
        cyl = Rotation(0, 90, 0) * cyl
    elif abs(direction[1]):
        cyl = Rotation(90, 0, 0) * cyl
    center = tuple(entry[i] + direction[i] * length / 2.0 for i in range(3))
    return Pos(*center) * cyl


def _exec_drill_hole(scene: Scene, cmd_id: str, p: DrillHoleParams) -> None:
    feat = _require(scene, p.feature)
    direction = _DRILL_DIRS[p.axis]
    bb = feat.shape.bounding_box()
    through = (
        abs(bb.max.X - bb.min.X) + abs(bb.max.Y - bb.min.Y) + abs(bb.max.Z - bb.min.Z) + 10
    )
    entry = p.position.tuple()
    depth = p.depth if p.depth > 0 else through
    if p.thread:  # roscado: el 3D lleva la BROCA de machuelado (diameter se ignora)
        from apolo.library.engineering.threads import thread_spec

        dia = thread_spec(p.thread)["broca_mm"]
    else:
        dia = p.diameter
    tools = [_drill_tool(dia, depth + 0.01, entry, direction)]
    if p.counterbore_d and p.counterbore_depth:
        if p.counterbore_d <= dia:
            raise CommandError("El caladrillo debe ser mayor que el diámetro del taladro")
        tools.append(_drill_tool(p.counterbore_d, p.counterbore_depth, entry, direction))
    result = feat.shape
    for tool in tools:
        result = result - tool
    if result is None or result.volume <= 0:
        raise CommandError("El taladro eliminó todo el material del sólido")
    if abs(result.volume - feat.shape.volume) < 1e-6:
        raise CommandError("El taladro no toca el sólido: revisa el punto de entrada y el eje")
    feat.shape = result
    feat.make_unique()


def _exec_pattern_circular(scene: Scene, cmd_id: str, p: PatternCircularParams) -> None:
    from build123d import Pos, Rotation

    from apolo.kernel.matrix import axis_rotation_about_point, multiply

    feat = _require(scene, p.feature)
    ap = p.axis_point.tuple()
    full = abs(p.total_angle - 360.0) < 1e-9
    steps = p.count if full else p.count - 1
    for i in range(1, p.count):
        angle = p.total_angle * i / max(1, steps)
        rot = {
            "x": Rotation(angle, 0, 0),
            "y": Rotation(0, angle, 0),
            "z": Rotation(0, 0, angle),
        }[p.axis_dir]
        copy = Pos(*ap) * rot * Pos(-ap[0], -ap[1], -ap[2]) * feat.shape
        fid = f"{cmd_id}_{i}"
        matrix = (
            multiply(axis_rotation_about_point(ap, p.axis_dir, angle), feat.matrix)
            if feat.matrix is not None
            else None
        )
        scene[fid] = Feature(
            fid, f"{feat.name} ({i + 1})", copy, cmd_id,
            component=feat.component, cut_length=feat.cut_length,
            mesh_key=feat.mesh_key if matrix is not None else None, matrix=matrix,
        )


_MIRROR_PLANES = {"xy": "XY", "xz": "XZ", "yz": "YZ"}


def _exec_mirror(scene: Scene, cmd_id: str, p: MirrorParams) -> None:
    from build123d import Plane, mirror

    feat = _require(scene, p.feature)
    plane = getattr(Plane, _MIRROR_PLANES[p.plane])
    if p.offset:
        plane = plane.offset(p.offset)
    copy = mirror(feat.shape, about=plane)
    scene[cmd_id] = Feature(
        cmd_id, f"{feat.name} (espejo)", copy, cmd_id,
        component=feat.component, cut_length=feat.cut_length,
    )


def _exec_sketch_sweep(scene: Scene, cmd_id: str, p: SketchSweepParams) -> None:
    from apolo.kernel.sketch_geom import SketchError, sketch_to_face
    from apolo.kernel.sweep import SweepError, helix_path, make_sweep, path_from_points

    try:
        face, _ = sketch_to_face(p.sketch)
        if p.helix is not None:
            path = helix_path(p.helix.radius, p.helix.pitch, p.helix.turns, p.helix.lefthand)
            base = make_sweep(face, path, is_frenet=True)
        else:
            path = path_from_points(p.path, p.smooth, p.closed)
            base = make_sweep(face, path, is_frenet=p.closed)
    except (SketchError, SweepError) as exc:
        raise CommandError(f"Barrido: {exc}") from exc
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_sketch_loft(scene: Scene, cmd_id: str, p: SketchLoftParams) -> None:
    from build123d import Plane

    from apolo.kernel.sketch_geom import SketchError, sketch_to_face
    from apolo.kernel.sweep import SweepError, make_loft

    try:
        faces = []
        for sec in p.sections:
            face, _ = sketch_to_face(sec.sketch)
            faces.append(Plane.XY.offset(sec.z) * face)
        base = make_loft(faces, p.ruled)
    except (SketchError, SweepError) as exc:
        raise CommandError(f"Transición: {exc}") from exc
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_boundary_surface(scene: Scene, cmd_id: str, p: BoundarySurfaceParams) -> None:
    from apolo.kernel.surface import SurfaceError, boundary_surface

    try:
        base = boundary_surface(p.curves, points=p.points, holes=p.holes)
    except SurfaceError as exc:
        raise CommandError(f"Superficie: {exc}") from exc
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_fill_surface(scene: Scene, cmd_id: str, p: FillSurfaceParams) -> None:
    from apolo.kernel.surface import SurfaceError, fill_surface_from_edges

    feat = _require(scene, p.feature)
    edges = _resolve_sel(feat.shape, p.edges, "edge")
    try:
        patch = fill_surface_from_edges(feat.shape, edges, tangent=p.tangent)
    except SurfaceError as exc:
        raise CommandError(f"Parche: {exc}") from exc
    scene[cmd_id] = Feature(cmd_id, p.name, patch, cmd_id)


def _exec_thicken(scene: Scene, cmd_id: str, p: ThickenParams) -> None:
    from apolo.kernel.shapes import is_surface
    from apolo.kernel.surface import SurfaceError, thicken_surface

    feat = _require(scene, p.feature)
    if not is_surface(feat.shape):
        raise CommandError(
            f"Engrosar necesita una SUPERFICIE (de boundary_surface o fill_surface); "
            f"'{feat.name}' no lo es (¿ya es un sólido?)"
        )
    try:
        solid = thicken_surface(feat.shape, p.thickness, both=p.both, flip=p.flip)
    except SurfaceError as exc:
        raise CommandError(f"Engrosar: {exc}") from exc
    feat.shape = solid
    feat.make_unique()


def _exec_create_revolve(scene: Scene, cmd_id: str, p: CreateRevolveParams) -> None:
    from apolo.kernel.shapes import make_revolution

    try:
        base = make_revolution(p.profile, p.angle)
    except Exception as exc:
        raise CommandError(f"Perfil de revolución inválido: {exc}") from exc
    if base.volume <= 0:
        raise CommandError("La revolución produjo un sólido vacío")
    base = _orient_axis(base, p.axis)
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_create_extrude_poly(scene: Scene, cmd_id: str, p: CreateExtrudePolyParams) -> None:
    from build123d import Polygon, Pos, extrude

    try:
        face = Polygon(*[tuple(pt) for pt in p.points], align=None)
        base = Pos(0, 0, -p.height / 2.0) * extrude(face, p.height)
    except Exception as exc:
        raise CommandError(f"Polígono inválido (¿auto-intersecciones?): {exc}") from exc
    if base.volume <= 0:
        raise CommandError("La extrusión produjo un sólido vacío")
    base = _orient_axis(base, p.axis)
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_sketch_extrude(scene: Scene, cmd_id: str, p: SketchExtrudeParams) -> None:
    from build123d import extrude

    from apolo.kernel.sketch_geom import SketchError, place_sketch_on_plane, sketch_to_face

    try:
        face, _ = sketch_to_face(p.sketch)
        placed = place_sketch_on_plane(face, p.plane)
        base = extrude(placed, p.height)
    except SketchError as exc:
        raise CommandError(f"Croquis: {exc}") from exc
    except Exception as exc:
        raise CommandError(f"No se pudo extruir el croquis: {exc}") from exc
    if base.volume <= 0:
        raise CommandError("La extrusión del croquis produjo un sólido vacío")
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_sketch_revolve(scene: Scene, cmd_id: str, p: SketchRevolveParams) -> None:
    from build123d import Axis, revolve

    from apolo.kernel.sketch_geom import SketchError, place_sketch_on_plane, sketch_to_face

    try:
        face, solved = sketch_to_face(p.sketch)
        min_x = min(v[0] for v in solved["points"].values())
        if min_x < -1e-6:
            raise SketchError(f"Para revolucionar, todas las x deben ser ≥ 0 (radio); hay x={min_x:g}")
        placed = place_sketch_on_plane(face, "xz")
        base = revolve(placed, Axis.Z, revolution_arc=p.angle)
    except SketchError as exc:
        raise CommandError(f"Croquis: {exc}") from exc
    except Exception as exc:
        raise CommandError(f"No se pudo revolucionar el croquis: {exc}") from exc
    if base.volume <= 0:
        raise CommandError("La revolución del croquis produjo un sólido vacío")
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_import_step(scene: Scene, cmd_id: str, p: ImportStepParams, attachments: dict) -> None:
    from apolo.sandbox import step_bytes_to_shape

    data = attachments.get(p.attachment)
    if data is None:
        raise CommandError(f"No existe el adjunto '{p.attachment}' en el documento")
    try:
        imported = step_bytes_to_shape(data)
    except Exception as exc:
        raise CommandError(f"STEP inválido: {exc}") from exc

    solids = list(getattr(imported, "solids", lambda: [])()) if p.split else []
    if p.split and len(solids) > 1:
        for i, solid in enumerate(solids, start=1):
            shape = place(solid, p.position.tuple(), p.rotation.tuple())
            fid = f"{cmd_id}_{i}"
            scene[fid] = Feature(fid, f"{p.name} ({i})", shape, cmd_id)
    else:
        shape = place(imported, p.position.tuple(), p.rotation.tuple())
        scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _register_joint(scene: Scene, joints: Joints, cmd_id: str, spec: dict) -> None:
    name = spec["name"]
    if name in joints:
        raise CommandError(f"Ya existe una junta llamada '{name}'")
    _require(scene, spec["parent"])
    _require(scene, spec["child"])
    if spec["parent"] == spec["child"]:
        raise CommandError("Una junta no puede unir un sólido consigo mismo")
    if any(j["child"] == spec["child"] for j in joints.values()):
        raise CommandError(f"El sólido '{spec['child']}' ya es hijo de otra junta (estructura de árbol)")
    if spec["child"] in _ancestors(joints, spec["parent"]) or spec["child"] == spec["parent"]:
        raise CommandError("La junta crearía un ciclo en la cadena cinemática")
    ax = spec["axis"]
    if abs(ax[0]) + abs(ax[1]) + abs(ax[2]) < 1e-9:
        raise CommandError("El eje de la junta no puede ser el vector nulo")
    if spec["lower"] >= spec["upper"] and spec["type"] not in ("fija", "continua"):
        raise CommandError("El límite inferior debe ser menor que el superior")
    joints[name] = {**spec, "command_id": cmd_id}


def _exec_add_joint(scene: Scene, joints: Joints, cmd_id: str, p: AddJointParams) -> None:
    _register_joint(
        scene, joints, cmd_id,
        {
            "name": p.name, "type": p.type, "parent": p.parent, "child": p.child,
            "origin": list(p.origin.tuple()), "axis": list(p.axis.tuple()),
            "lower": p.lower, "upper": p.upper,
        },
    )


def _exec_add_mate(scene: Scene, mates: dict, cmd_id: str, p: AddMateParams) -> None:
    from apolo.assembly.mates import MateError, register_mate

    try:
        register_mate(
            scene, mates, cmd_id,
            {
                "name": p.name, "type": p.type,
                "feature_a": p.feature_a, "feature_b": p.feature_b,
                "ref_a": p.ref_a.model_dump(exclude_none=True),
                "ref_b": p.ref_b.model_dump(exclude_none=True),
                "value": p.value, "flip": p.flip,
            },
        )
    except MateError as exc:
        raise CommandError(str(exc)) from exc


def _exec_add_rail_constraint(
    scene: Scene, constraints: dict, cmd_id: str, p: AddRailConstraintParams
) -> None:
    from apolo.assembly.constraints import ConstraintError, register_constraint

    try:
        register_constraint(
            constraints, cmd_id,
            {
                "name": p.name, "joint": p.joint,
                "anchor": list(p.anchor.tuple()),
                "point": list(p.point.tuple()),
                "axis": list(p.axis.tuple()),
            },
        )
    except ConstraintError as exc:
        raise CommandError(str(exc)) from exc


def _exec_add_constraint(
    scene: Scene, constraints: dict, cmd_id: str, p: AddConstraintParams
) -> None:
    """Restricción cinemática genérica (multi-restricción / N-GDL). Registra la condición;
    el solver global (solve_constraints) resuelve todas las juntas dependientes a la vez."""
    from apolo.assembly.constraints import ConstraintError, register_constraint

    try:
        register_constraint(
            constraints, cmd_id,
            {
                "name": p.name, "tipo": p.tipo, "joint": p.joint,
                "anchor": list(p.anchor.tuple()),
                "point": list(p.point.tuple()),
                "axis": list(p.axis.tuple()),
                "value": float(p.value),
            },
        )
    except ConstraintError as exc:
        raise CommandError(str(exc)) from exc


def _exec_fasten(scene: Scene, fasteners: dict, grounds: dict, cmd_id: str, p: FastenParams) -> None:
    """Declara un fijador rígido A↔B (estructural; no mueve geometría)."""
    from apolo.assembly.connectivity import ConnectivityError, register_fastener

    spec = {"name": p.name, "a": p.a, "b": p.b, "kind": p.kind, "nota": p.nota}
    # dimensionamiento opcional (Frente A): métrica/cantidad del perno, cordón de soldadura
    if p.size:
        spec["size"] = p.size
    if p.qty:
        spec["qty"] = p.qty
    if p.throat_mm:
        spec["throat_mm"] = p.throat_mm
    if p.length_mm:
        spec["length_mm"] = p.length_mm
    try:
        register_fastener(fasteners, cmd_id, spec)
    except ConnectivityError as exc:
        raise CommandError(str(exc)) from exc


def _exec_ground(scene: Scene, fasteners: dict, grounds: dict, cmd_id: str, p: GroundParams) -> None:
    """Ancla una pieza a tierra (origen del camino de sujeción)."""
    from apolo.assembly.connectivity import ConnectivityError, register_ground

    try:
        register_ground(grounds, cmd_id, {"name": p.name, "feature": p.feature, "nota": p.nota})
    except ConnectivityError as exc:
        raise CommandError(str(exc)) from exc


def _exec_create_group(
    scene: Scene, cmd_id: str, p: "CreateGroupParams", *,
    groups: dict, joints: dict, mates: dict, constraints: dict,
) -> None:
    """Declara un GRUPO/sub-ensamblaje por command_ids (V5.2). No muta geometría:
    la membresía se deriva en cada regenerate (feat.group)."""
    from apolo.assembly.groups import GroupError, register_group

    try:
        register_group(groups, cmd_id, {
            "name": p.name, "members": p.members, "parent": p.parent, "role": p.role,
        })
    except GroupError as exc:
        raise CommandError(str(exc)) from exc


def _transform_point(w: list, pt) -> list[float]:
    """Aplica una matriz 4×4 (filas) a un punto [x,y,z]."""
    x, y, z = float(pt[0]), float(pt[1]), float(pt[2])
    return [w[i][0] * x + w[i][1] * y + w[i][2] * z + w[i][3] for i in range(3)]


def _transform_dir(w: list, v) -> list[float]:
    """Aplica SOLO la rotación de una matriz 4×4 a una dirección [x,y,z]."""
    x, y, z = float(v[0]), float(v[1]), float(v[2])
    return [w[i][0] * x + w[i][1] * y + w[i][2] * z for i in range(3)]


def _exec_transform_group(
    scene: Scene, cmd_id: str, p: "TransformGroupParams", *,
    groups: dict, joints: dict, mates: dict, constraints: dict,
) -> None:
    """Mueve un grupo ENTERO como cuerpo rígido (V5.2): todas sus piezas + las
    juntas/restricciones internas. Rechaza uniones que cruzan la frontera."""
    from apolo.assembly.groups import group_command_ids, group_features
    from apolo.kernel.matrix import multiply, rotation_about_center, translation
    from apolo.kernel.shapes import move_rotated_about

    if p.group not in groups:
        raise CommandError(f"No existe el grupo '{p.group}'")
    # todos los members (incl. descendientes) deben tener piezas YA creadas en este
    # punto del replay (la escena en este instante ES el log hasta aquí)
    cmds = group_command_ids(groups, p.group, recursive=True)
    present = {f.command_id for f in scene.values()}
    missing = sorted(c for c in cmds if c not in present)
    if missing:
        raise CommandError(
            f"El grupo '{p.group}' tiene comandos sin piezas en este punto del log "
            f"({', '.join(missing[:4])}{'…' if len(missing) > 4 else ''}): declara el "
            "transform_group DESPUÉS de crear todas sus piezas"
        )
    fids = set(group_features(scene, groups, p.group, recursive=True))
    if not fids:
        raise CommandError(f"El grupo '{p.group}' no tiene piezas que mover")

    # frontera: juntas/mates/restricciones con UN extremo dentro → rechazo claro
    for j in joints.values():
        inside = (j["parent"] in fids) + (j["child"] in fids)
        if inside == 1:
            raise CommandError(
                f"La junta '{j.get('name')}' cruza la frontera del grupo '{p.group}' "
                "(un extremo fuera): incluye ambos cuerpos en el grupo o quita la junta"
            )
    for m in mates.values():
        inside = (m["feature_a"] in fids) + (m["feature_b"] in fids)
        if inside == 1:
            raise CommandError(
                f"El mate '{m.get('name')}' cruza la frontera del grupo '{p.group}': "
                "solve_mates desharía el movimiento en silencio — inclúyelo o quítalo"
            )

    translate = p.translate.tuple()
    rotate = p.rotate.tuple()
    # centro del bbox CONJUNTO (cuerpo rígido: todas giran sobre el mismo punto)
    import math

    mins = [math.inf] * 3
    maxs = [-math.inf] * 3
    for fid in fids:
        bb = scene[fid].shape.bounding_box()
        for k, v in enumerate((bb.min.X, bb.min.Y, bb.min.Z)):
            mins[k] = min(mins[k], v)
        for k, v in enumerate((bb.max.X, bb.max.Y, bb.max.Z)):
            maxs[k] = max(maxs[k], v)
    center = tuple((mins[k] + maxs[k]) / 2.0 for k in range(3))

    w = translation(*translate)
    if any(rotate):
        w = multiply(w, rotation_about_center(center, rotate))

    from apolo.kernel.matrix import transform_anchors

    for fid in fids:
        feat = scene[fid]
        if feat.matrix is not None:
            feat.matrix = multiply(w, feat.matrix)
        feat.shape = move_rotated_about(feat.shape, translate, rotate, center)
        if feat.anchors:  # las anclas viajan con el grupo (REEMPLAZAR, no mutar)
            feat.anchors = transform_anchors(w, feat.anchors)
    # juntas internas: el marco viaja con el grupo (origin punto, axis dirección)
    for j in joints.values():
        if j["parent"] in fids and j["child"] in fids:
            if j.get("origin") is not None:
                o = j["origin"]
                no = _transform_point(w, (o["x"], o["y"], o["z"]) if isinstance(o, dict) else o)
                j["origin"] = {"x": no[0], "y": no[1], "z": no[2]} if isinstance(o, dict) else no
            if any(rotate) and j.get("axis") is not None:
                a = j["axis"]
                na = _transform_dir(w, (a["x"], a["y"], a["z"]) if isinstance(a, dict) else a)
                j["axis"] = {"x": na[0], "y": na[1], "z": na[2]} if isinstance(a, dict) else na
    # restricciones internas (su junta es interna): anchor/point puntos, axis dirección
    internal_joints = {
        name for name, j in joints.items() if j["parent"] in fids and j["child"] in fids
    }
    for con in constraints.values():
        if con.get("joint") in internal_joints:
            for key in ("anchor", "point"):
                if con.get(key) is not None:
                    con[key] = _transform_point(w, con[key])
            if any(rotate) and con.get("axis") is not None:
                con["axis"] = _transform_dir(w, con["axis"])


def _insert_project_precheck(
    cmd_id: str, sub, p: "InsertProjectParams", scene: Scene, groups: dict,
    joints: Joints, constraints: dict, fasteners: dict, grounds: dict,
) -> None:
    """Pre-valida TODOS los nombres/ids prospectivos de la instancia contra el estado
    YA presente, ANTES de emitir la primera pieza (Fix F): un solo CommandError con la
    lista completa de colisiones, en vez de un críptico 'duplicado' a mitad de emisión
    (con el rollback de _mutate como red pero sin depender de él). El cuerpo del executor
    vuelve a validar al registrar cada entidad (defensa en profundidad)."""
    clashes: list[str] = []
    if p.name in groups:
        clashes.append(f"grupo '{p.name}'")
    for fid in sub.scene:
        if f"{cmd_id}_{fid}" in scene:
            clashes.append(f"sólido '{cmd_id}_{fid}'")
    for jname in sub.joints:
        if f"{p.name}/{jname}" in joints:
            clashes.append(f"junta '{p.name}/{jname}'")
    for cname in sub.constraints:
        if f"{p.name}/{cname}" in constraints:
            clashes.append(f"restricción '{p.name}/{cname}'")
    for fname in sub.fasteners:
        if f"{p.name}/{fname}" in fasteners:
            clashes.append(f"fijador '{p.name}/{fname}'")
    if p.keep_grounds:
        for gname in sub.grounds:
            if f"{p.name}/{gname}" in grounds:
                clashes.append(f"anclaje '{p.name}/{gname}'")
    for gname in sub.groups:
        if f"{p.name}/{gname}" in groups:
            clashes.append(f"grupo '{p.name}/{gname}'")
    if clashes:
        raise CommandError(
            f"La instancia '{p.name}' colisiona con entidades ya presentes: "
            + ", ".join(clashes)
            + " — usa un nombre de instancia distinto"
        )


def _exec_insert_project(
    scene: Scene, cmd_id: str, p: "InsertProjectParams", *,
    attachments: dict, groups: dict, joints: Joints, mates: dict,
    constraints: dict, fasteners: dict, grounds: dict,
) -> None:
    """Instancia un PROYECTO completo (V5.2b): reproduce su snapshot en un sandbox
    (doc/subproject.py, con caché por digest+overrides) y vuelca el resultado con
    ids PREFIJADOS. Los mates del origen llegan BAKED (el sandbox ya los resolvió);
    juntas/restricciones/fijadores/anclajes internos se registran prefijados y el
    conjunto queda bajo un grupo raíz `name` + los grupos internos '{name}/{grupo}'."""
    import copy as _copy

    from apolo.assembly.connectivity import (
        ConnectivityError, register_fastener, register_ground,
    )
    from apolo.assembly.constraints import ConstraintError, register_constraint
    from apolo.assembly.groups import GroupError, register_group
    from apolo.doc.subproject import SubprojectError, build_subproject
    from apolo.kernel.matrix import compose_place, multiply

    # guard temprano: el nombre de instancia ES el grupo raíz — chocar aquí da el
    # error intuitivo (y no uno críptico de junta/fijador duplicado a mitad de emisión)
    if p.name in groups:
        raise CommandError(
            f"Ya existe un grupo llamado '{p.name}': el nombre de la instancia debe ser único"
        )
    data = attachments.get(p.attachment) if p.attachment else None
    if data is None:
        raise CommandError(
            "El snapshot del proyecto no está materializado: ejecuta el comando vía "
            "API/MCP con project_id (la capa API embebe el attachment)"
        )
    try:
        sub = build_subproject(data, p.overrides)
    except SubprojectError as exc:
        raise CommandError(str(exc)) from exc
    if not sub.scene:
        raise CommandError("El proyecto instanciado no tiene sólidos")

    # Fix F: pre-validar TODAS las colisiones ANTES de emitir la primera pieza
    _insert_project_precheck(
        cmd_id, sub, p, scene, groups, joints, constraints, fasteners, grounds
    )

    pos, rot = p.position.tuple(), p.rotation.tuple()
    inst = compose_place(pos, rot)

    # piezas: copia prefijada con instancing de mallas SIEMPRE (dos instancias con
    # los mismos overrides comparten el 100 % de las mallas del viewport). El
    # command_id sintético '{cmd_id}_{cmd_origen}' preserva la exclusión
    # intra-comando de check_interference y la membresía de los grupos internos.
    for fid, feat in sub.scene.items():
        nf = _copy.copy(feat)
        nf.id = f"{cmd_id}_{fid}"
        nf.command_id = f"{cmd_id}_{feat.command_id}"
        nf.name = f"{p.name} · {feat.name}"
        nf.shape = place(feat.shape, pos, rot)
        if feat.mesh_key is not None and feat.matrix is not None and feat.mesh_key in DEFINITIONS:
            nf.matrix = multiply(inst, feat.matrix)
        else:
            key = f"subp|{p.attachment[:12]}|{sub.key_hash}|{fid}"
            register_definition(key, feat.shape)
            nf.mesh_key, nf.matrix = key, inst
        nf.group = None  # derivado: se reasigna al final del regenerate
        if feat.anchors:  # anclas del origen → mundo del anfitrión (REEMPLAZAR: nf es shallow copy)
            from apolo.kernel.matrix import transform_anchors
            nf.anchors = transform_anchors(inst, feat.anchors)
        scene[nf.id] = nf

    # juntas internas: prefijadas y transformadas (origin punto, axis dirección)
    for jname, j in sub.joints.items():
        nj = _copy.deepcopy(j)
        nj["name"] = f"{p.name}/{jname}"
        nj["parent"] = f"{cmd_id}_{j['parent']}"
        nj["child"] = f"{cmd_id}_{j['child']}"
        if nj.get("origin") is not None:
            o = nj["origin"]
            no = _transform_point(inst, (o["x"], o["y"], o["z"]) if isinstance(o, dict) else o)
            nj["origin"] = {"x": no[0], "y": no[1], "z": no[2]} if isinstance(o, dict) else no
        if nj.get("axis") is not None:
            a = nj["axis"]
            na = _transform_dir(inst, (a["x"], a["y"], a["z"]) if isinstance(a, dict) else a)
            nj["axis"] = {"x": na[0], "y": na[1], "z": na[2]} if isinstance(a, dict) else na
        _register_joint(scene, joints, cmd_id, nj)

    # restricciones internas (su junta viaja renombrada con la instancia)
    for cname, con in sub.constraints.items():
        nc = _copy.deepcopy(con)
        nc["name"] = f"{p.name}/{cname}"
        nc["joint"] = f"{p.name}/{con['joint']}"
        for key in ("anchor", "point"):
            if nc.get(key) is not None:
                nc[key] = _transform_point(inst, nc[key])
        if nc.get("axis") is not None:
            nc["axis"] = _transform_dir(inst, nc["axis"])
        try:
            register_constraint(constraints, cmd_id, nc)
        except ConstraintError as exc:
            raise CommandError(str(exc)) from exc

    # fijadores internos, con su dimensionamiento (engineering_check los ve)
    for fname, f in sub.fasteners.items():
        try:
            register_fastener(fasteners, cmd_id, {
                **f, "name": f"{p.name}/{fname}",
                "a": f"{cmd_id}_{f['a']}", "b": f"{cmd_id}_{f['b']}",
            })
        except ConnectivityError as exc:
            raise CommandError(str(exc)) from exc

    # anclajes a tierra: una máquina apoyada en piso sigue apoyada en el layout;
    # keep_grounds=False al elevarla (mezzanine) — el anclaje nuevo se declara aquí
    if p.keep_grounds:
        for gname, g in sub.grounds.items():
            try:
                register_ground(grounds, cmd_id, {
                    **g, "name": f"{p.name}/{gname}", "feature": f"{cmd_id}_{g['feature']}",
                })
            except ConnectivityError as exc:
                raise CommandError(str(exc)) from exc

    # grupos: raíz primero (invariante del DAG: padre antes que hijo), luego los
    # internos del origen como grupos REALES anidados '{name}/{grupo}'
    grouped_in_src: set[str] = set()
    for g in sub.groups.values():
        grouped_in_src.update(g["members"])
    seen: set[str] = set()
    root_members: list[str] = []
    for feat in sub.scene.values():
        c = feat.command_id
        if c not in seen:
            seen.add(c)
            if c not in grouped_in_src:
                root_members.append(f"{cmd_id}_{c}")
    def _put_group(spec: dict) -> None:
        # un grupo SIN members directos es legítimo aquí (raíz cuyo contenido vive
        # todo en sub-grupos — p. ej. una instancia que a su vez instancia): bypass
        # documentado del mínimo de register_group (código de confianza)
        if spec["members"]:
            register_group(groups, cmd_id, spec)
        elif spec["name"] in groups:
            raise GroupError(f"Ya existe un grupo llamado '{spec['name']}'")
        else:
            groups[spec["name"]] = {**spec, "command_id": cmd_id}

    try:
        _put_group({"name": p.name, "members": root_members, "parent": None, "role": None})
        for gname, g in sub.groups.items():  # orden de registro del origen: padre antes que hijo
            _put_group({
                "name": f"{p.name}/{gname}",
                "members": [f"{cmd_id}_{m}" for m in g["members"]],
                "parent": f"{p.name}/{g['parent']}" if g.get("parent") else p.name,
                "role": g.get("role"),
            })
    except GroupError as exc:
        raise CommandError(str(exc)) from exc


def _exec_add_joinery(scene: Scene, cmd_id: str, p: AddJoineryParams) -> None:
    from build123d import Box, Cylinder, Pos, Rotation

    if p.feature_a == p.feature_b:
        raise CommandError("Una unión no puede ser de una pieza consigo misma")
    a = _require(scene, p.feature_a)
    b = _require(scene, p.feature_b)
    ax = p.axis.tuple()
    m = max(abs(ax[0]), abs(ax[1]), abs(ax[2]))
    if m < 1e-9:
        raise CommandError("El eje de inserción no puede ser el vector nulo")
    if abs(ax[0]) == m:
        char, au = "x", (1.0 if ax[0] > 0 else -1.0, 0.0, 0.0)
    elif abs(ax[1]) == m:
        char, au = "y", (0.0, 1.0 if ax[1] > 0 else -1.0, 0.0)
    else:
        char, au = "z", (0.0, 0.0, 1.0 if ax[2] > 0 else -1.0)
    pos = p.position.tuple()

    def obox(u, v, d):  # caja: u,v perpendiculares; d a lo largo del eje
        return {"x": lambda: Box(d, u, v), "y": lambda: Box(u, d, v), "z": lambda: Box(u, v, d)}[char]()

    def cyl_axis(r, length, c):  # cilindro a lo largo del eje, centrado en c
        cy = Cylinder(r, length)
        if char == "y":
            cy = Rotation(90, 0, 0) * cy
        elif char == "x":
            cy = Rotation(0, 90, 0) * cy
        return Pos(*c) * cy

    def center(sh):
        bb = sh.bounding_box()
        return ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)

    def toward_b():  # dirección de A hacia B a lo largo del eje
        ca, cb = center(a.shape), center(b.shape)
        d = sum((cb[i] - ca[i]) * au[i] for i in range(3))
        s = 1.0 if d >= 0 else -1.0
        return (au[0] * s, au[1] * s, au[2] * s)

    try:
        if p.type == "espiga_mortaja":
            tw = toward_b()
            tc = tuple(pos[i] + tw[i] * p.depth / 2 for i in range(3))
            tenon = Pos(*tc) * obox(p.width, p.height, p.depth)
            mort = Pos(*tc) * obox(p.width + 2 * p.clearance, p.height + 2 * p.clearance, p.depth + p.clearance)
            a.shape = a.shape + tenon
            b.shape = b.shape - mort
            a.make_unique()
            b.make_unique()
        elif p.type == "dado":
            tw = toward_b()
            gc = tuple(pos[i] + tw[i] * p.depth / 2 for i in range(3))
            groove = Pos(*gc) * obox(p.width, p.height, p.depth)
            b.shape = b.shape - groove
            b.make_unique()
        elif p.type == "dowel":
            perp = (0.0, 0.0, 1.0) if char in ("x", "y") else (1.0, 0.0, 0.0)
            n = max(1, int(p.count))
            for i in range(n):
                off = (i - (n - 1) / 2.0) * p.spacing
                c = tuple(pos[k] + perp[k] * off for k in range(3))
                hole = cyl_axis(p.width / 2.0, p.depth, c)
                a.shape = a.shape - hole
                b.shape = b.shape - hole
                pin = cyl_axis(max(0.5, p.width / 2.0 - p.clearance), p.depth * 0.95, c)
                fid = f"{cmd_id}_pin{i + 1}"
                scene[fid] = Feature(fid, f"{p.name} clavija {i + 1}", pin, cmd_id)
            a.make_unique()
            b.make_unique()
        elif p.type == "rebaje":
            # corte de caja EN SITIO en B (galce de vidrio): X=width, Y=height, Z=depth.
            cut = Pos(*pos) * Box(p.width, p.height, p.depth)
            b.shape = b.shape - cut
            b.make_unique()
    except CommandError:
        raise
    except Exception as exc:
        raise CommandError(f"Unión '{p.type}' imposible: {exc}") from exc
    for feat in (a, b):
        if getattr(feat.shape, "volume", 1.0) <= 0:
            raise CommandError("La unión dejó una pieza vacía: revisa posición/medidas")


def _exec_create_robot_arm(scene: Scene, joints: Joints, cmd_id: str, p: CreateRobotArmParams) -> None:
    from apolo.robotics.arm import robot_arm_parts

    try:
        parts, joint_specs = robot_arm_parts(p.alcance, p.position.tuple(), cmd_id)
    except ValueError as exc:
        raise CommandError(f"Brazo robótico: {exc}") from exc
    for part in parts:
        fid = f"{cmd_id}_{part['suffix']}"
        scene[fid] = Feature(fid, f"{p.name} · {part['name']}", part["shape"], cmd_id)
    for spec in joint_specs:
        _register_joint(scene, joints, cmd_id, spec)


def _exec_run_script(scene: Scene, cmd_id: str, p: RunScriptParams, resolved_vars: dict) -> None:
    from apolo.sandbox import ScriptError, run_script_to_shape

    try:
        base = run_script_to_shape(p.code, resolved_vars)
    except ScriptError as exc:
        raise CommandError(str(exc)) from exc
    if not hasattr(base, "volume") or base.volume <= 0:
        raise CommandError("El script produjo geometría sin volumen")
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_insert_component(scene: Scene, cmd_id: str, p: InsertComponentParams) -> None:
    from apolo.library.catalog import CATALOG, build_component, component_anchors

    comp = CATALOG[p.component]
    try:
        base, cut = build_component(p.component, p.length)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
    key = f"comp|{p.component}|{cut if cut is not None else 'std'}"
    _instanced(
        scene, cmd_id, p.name or comp.name, base, key,
        p.position.tuple(), p.rotation.tuple(), component=p.component, cut_length=cut,
    )
    # anclas de conexión con nombre (V6.3b): frame LOCAL del builder → mundo por la pose
    local = component_anchors(comp)
    feat = scene[cmd_id]
    if local and feat.matrix is not None:
        from apolo.kernel.matrix import transform_anchors
        feat.anchors = transform_anchors(feat.matrix, local)


_ANCHOR_FNS = {
    "centro": lambda bb, c: c,
    "base": lambda bb, c: (c[0], c[1], bb.min.Z),
    "tope": lambda bb, c: (c[0], c[1], bb.max.Z),
    "min_x": lambda bb, c: (bb.min.X, c[1], c[2]),
    "max_x": lambda bb, c: (bb.max.X, c[1], c[2]),
    "min_y": lambda bb, c: (c[0], bb.min.Y, c[2]),
    "max_y": lambda bb, c: (c[0], bb.max.Y, c[2]),
}


def _anchor_point(shape, anchor: str) -> tuple[float, float, float]:
    bb = shape.bounding_box()
    center = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
    return _ANCHOR_FNS[anchor](bb, center)


def _exec_attach(scene: Scene, cmd_id: str, p: AttachParams) -> None:
    feat = _require(scene, p.feature)
    target = _require(scene, p.target)
    if p.feature == p.target:
        raise CommandError("Un sólido no puede ensamblarse consigo mismo")

    # 1 · orientación: girar sobre su centro para alinear ejes
    if p.align_my and p.align_to and p.align_my != p.align_to:
        from apolo.kernel.matrix import euler_between_axes

        _world_move(feat, (0, 0, 0), euler_between_axes(p.align_my, p.align_to))

    # 2 · traslación: ancla a ancla (con el bbox ya reorientado)
    src = _anchor_point(feat.shape, p.anchor)
    dst = _anchor_point(target.shape, p.target_anchor)
    delta = (
        dst[0] - src[0] + p.offset.x,
        dst[1] - src[1] + p.offset.y,
        dst[2] - src[2] + p.offset.z,
    )
    _world_move(feat, delta, (0, 0, 0))


def _publish_axis_anchor(scene: Scene, fid: str, name: str) -> None:
    """Publica un ancla de EJE (V6.3b) en la Feature `fid` — un rodillo/tambor es un cilindro
    con eje Z en su frame propio (canónico); su `matrix` mapea ese frame a mundo. No-op si el
    fid no existe o no es instancia (sin matrix). REEMPLAZA el dict de anclas (checkpoint-safe)."""
    feat = scene.get(fid)
    if feat is None or feat.matrix is None:
        return
    from apolo.kernel.matrix import transform_anchors

    world = transform_anchors(feat.matrix, {name: {"origin": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, 1.0]}})
    feat.anchors = {**(feat.anchors or {}), **world}


def _exec_create_conveyor(scene: Scene, cmd_id: str, p: CreateConveyorParams) -> None:
    from apolo.kernel.matrix import compose_place, multiply
    from apolo.library.conveyor import conveyor_parts

    try:
        parts = conveyor_parts(
            p.largo, p.ancho, p.altura, p.paso, p.rodillo,
            None if p.motor == "ninguno" else p.motor,
        )
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Transportador: {exc}") from exc
    cmd_matrix = compose_place(p.position.tuple(), p.rotation.tuple())
    roller_idx: list[int] = []
    for part in parts:
        shape = place(part.shape, p.position.tuple(), p.rotation.tuple())
        fid = f"{cmd_id}_{part.suffix}"
        matrix = None
        if part.base_key and part.base_shape is not None:
            register_definition(part.base_key, part.base_shape)
            matrix = multiply(cmd_matrix, compose_place(part.position, part.rotation))
        scene[fid] = Feature(
            fid, f"{p.name} · {part.name}", shape, cmd_id,
            component=part.component, cut_length=part.cut_length,
            mesh_key=part.base_key if matrix is not None else None, matrix=matrix,
        )
        if part.suffix.startswith("rod") and part.suffix[3:].isdigit():
            roller_idx.append(int(part.suffix[3:]))
    # eje de cola (rodillo de entrada, -X) y motriz (rodillo de descarga, +X)
    if roller_idx:
        _publish_axis_anchor(scene, f"{cmd_id}_rod{min(roller_idx)}", "eje_cola")
        _publish_axis_anchor(scene, f"{cmd_id}_rod{max(roller_idx)}", "eje_motriz")


def _exec_create_belt_conveyor(scene: Scene, cmd_id: str, p: CreateBeltConveyorParams) -> None:
    from apolo.library.belt_conveyor import belt_conveyor_parts

    try:
        parts = belt_conveyor_parts(
            p.largo, p.ancho_banda, p.altura, p.tambor_motriz, p.tambor_cola, p.tubo,
            None if p.tensor == "ninguno" else p.tensor,
            None if p.motor == "ninguno" else p.motor,
            p.espesor_banda, p.guardas,
        )
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Faja de banda: {exc}") from exc
    _emit_weldment_parts(scene, cmd_id, p.name, parts, p.position.tuple(), p.rotation.tuple())
    _publish_axis_anchor(scene, f"{cmd_id}_tambor_motriz", "eje_motriz")
    _publish_axis_anchor(scene, f"{cmd_id}_tambor_cola", "eje_cola")


def _exec_create_take_up(scene: Scene, cmd_id: str, p: CreateTakeUpParams) -> None:
    from apolo.library.take_up import take_up_parts

    try:
        parts = take_up_parts(
            p.diam_rodillo, p.ancho_banda, p.rodamiento, p.perno, p.espesor_soporte,
            p.voladizo, p.engomado, p.dir_tensor,
        )
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Tensor de cola: {exc}") from exc
    _emit_weldment_parts(scene, cmd_id, p.name, parts, p.position.tuple(), p.rotation.tuple())


def _exec_create_drive_roller(scene: Scene, cmd_id: str, p: CreateDriveRollerParams) -> None:
    from apolo.library.take_up import drive_roller_parts

    try:
        parts = drive_roller_parts(
            p.diam_rodillo, p.ancho_banda, p.rodamiento, p.perno, p.espesor_soporte,
            p.voladizo, p.largo_eje_motor, p.engomado, p.dir_tensor,
        )
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Rodillo motriz: {exc}") from exc
    _emit_weldment_parts(scene, cmd_id, p.name, parts, p.position.tuple(), p.rotation.tuple())


def _emit_weldment_parts(scene: Scene, cmd_id: str, name: str, parts, position, rotation) -> None:
    """Vuelca las piezas de un super-comando tipo bastidor (weldment/esqueleto) en la
    escena, aplicando la transformación del comando y reusando instancias compartidas."""
    from apolo.kernel.matrix import compose_place, multiply

    cmd_matrix = compose_place(position, rotation)
    for part in parts:
        shape = place(part.shape, position, rotation)
        fid = f"{cmd_id}_{part.suffix}"
        matrix = None
        if part.base_key and part.base_shape is not None:
            register_definition(part.base_key, part.base_shape)
            matrix = multiply(cmd_matrix, compose_place(part.position, part.rotation))
        scene[fid] = Feature(
            fid, f"{name} · {part.name}", shape, cmd_id,
            component=part.component, cut_length=part.cut_length,
            miter=getattr(part, "miter", None),
            mesh_key=part.base_key if matrix is not None else None, matrix=matrix,
        )


def _exec_create_weldment(scene: Scene, cmd_id: str, p: CreateWeldmentParams) -> None:
    from apolo.library.weldment import weldment_parts

    try:
        parts = weldment_parts(
            p.ancho, p.fondo, p.alto, p.perfil, p.anillos_intermedios, p.cordones,
            p.esquinas,
        )
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Bastidor: {exc}") from exc
    _emit_weldment_parts(scene, cmd_id, p.name, parts, p.position.tuple(), p.rotation.tuple())


def _exec_create_frame(scene: Scene, cmd_id: str, p: CreateFrameParams) -> None:
    from apolo.library.frame import frame_from_edges

    try:
        parts = frame_from_edges(p.nodes, p.edges, p.perfil, p.cordones, p.esquinas)
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Esqueleto: {exc}") from exc
    _emit_weldment_parts(scene, cmd_id, p.name, parts, p.position.tuple(), p.rotation.tuple())


def _exec_create_sheet_metal(scene: Scene, cmd_id: str, p: SheetMetalParams) -> None:
    from apolo.library.sheetmetal import flaps_from_specs, sheet_metal_solid

    try:
        base = sheet_metal_solid(
            p.ancho, p.fondo, p.espesor, p.lados, p.altura_pestana, p.angulo, p.radio,
            holes=[(h.x, h.y, h.d) for h in p.holes],
            flaps=flaps_from_specs(p.flaps),
        )
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Chapa: {exc}") from exc
    if not hasattr(base, "volume") or base.volume <= 0:
        raise CommandError("La chapa produjo un sólido vacío")
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


@dataclass
class CommandSpec:
    type: str
    title: str
    category: str
    model: type[BaseModel]
    executor: Callable[..., None]
    kind: str = "scene"  # "scene" muta la escena; "vars" muta las variables
    wants_variables: bool = False  # el ejecutor recibe además las variables resueltas
    wants_joints: bool = False  # el ejecutor recibe además el registro de juntas
    wants_mates: bool = False  # el ejecutor recibe además el registro de mates
    wants_constraints: bool = False  # el ejecutor recibe además el registro de restricciones
    wants_attachments: bool = False  # el ejecutor recibe además los adjuntos del documento
    wants_connectivity: bool = False  # el ejecutor recibe además los fijadores + anclajes a tierra
    wants_groups: bool = False  # firma kwargs: (scene, cmd_id, model, *, groups, joints, mates, constraints)
    wants_all: bool = False  # firma kwargs TOTAL: (scene, cmd_id, model, *, attachments, groups, joints, mates, constraints, fasteners, grounds)


REGISTRY: dict[str, CommandSpec] = {
    spec.type: spec
    for spec in [
        CommandSpec("create_box", "Caja", "crear", CreateBoxParams, _exec_create_box),
        CommandSpec("create_cylinder", "Cilindro", "crear", CreateCylinderParams, _exec_create_cylinder),
        CommandSpec(
            "create_structural_profile",
            "Perfil estructural",
            "crear",
            CreateStructuralProfileParams,
            _exec_create_profile,
        ),
        CommandSpec("sketch_extrude", "Croquis extruido", "croquis", SketchExtrudeParams, _exec_sketch_extrude),
        CommandSpec("sketch_revolve", "Croquis revolucionado", "croquis", SketchRevolveParams, _exec_sketch_revolve),
        CommandSpec("sketch_sweep", "Barrido", "croquis", SketchSweepParams, _exec_sketch_sweep),
        CommandSpec("sketch_loft", "Transición", "croquis", SketchLoftParams, _exec_sketch_loft),
        CommandSpec("boundary_surface", "Superficie de contorno", "superficies", BoundarySurfaceParams, _exec_boundary_surface),
        CommandSpec("fill_surface", "Parche de superficie", "superficies", FillSurfaceParams, _exec_fill_surface),
        CommandSpec("thicken", "Engrosar superficie", "superficies", ThickenParams, _exec_thicken),
        CommandSpec("create_revolve", "Revolución", "crear", CreateRevolveParams, _exec_create_revolve),
        CommandSpec(
            "create_extrude_poly", "Polígono extruido", "crear", CreateExtrudePolyParams, _exec_create_extrude_poly
        ),
        CommandSpec(
            "import_step", "Importar STEP", "crear", ImportStepParams, _exec_import_step,
            wants_attachments=True,
        ),
        CommandSpec(
            "insert_component", "Componente", "biblioteca", InsertComponentParams, _exec_insert_component
        ),
        CommandSpec(
            "insert_project", "Insertar proyecto", "biblioteca", InsertProjectParams,
            _exec_insert_project, wants_all=True,
        ),
        CommandSpec(
            "create_conveyor", "Transportador", "biblioteca", CreateConveyorParams, _exec_create_conveyor
        ),
        CommandSpec(
            "create_belt_conveyor", "Faja de banda", "biblioteca", CreateBeltConveyorParams,
            _exec_create_belt_conveyor,
        ),
        CommandSpec(
            "create_take_up", "Tensor de cola (trotadora)", "biblioteca", CreateTakeUpParams,
            _exec_create_take_up,
        ),
        CommandSpec(
            "create_drive_roller", "Rodillo motriz (trotadora)", "biblioteca", CreateDriveRollerParams,
            _exec_create_drive_roller,
        ),
        CommandSpec(
            "create_weldment", "Bastidor", "biblioteca", CreateWeldmentParams, _exec_create_weldment
        ),
        CommandSpec(
            "create_frame", "Esqueleto", "biblioteca", CreateFrameParams, _exec_create_frame
        ),
        CommandSpec(
            "create_sheet_metal", "Chapa metálica", "biblioteca", SheetMetalParams,
            _exec_create_sheet_metal,
        ),
        CommandSpec(
            "run_script", "Script IA", "crear", RunScriptParams, _exec_run_script, wants_variables=True
        ),
        CommandSpec(
            "create_robot_arm", "Brazo robótico", "robotica", CreateRobotArmParams,
            _exec_create_robot_arm, wants_joints=True,
        ),
        CommandSpec(
            "add_joint", "Junta", "robotica", AddJointParams, _exec_add_joint, wants_joints=True
        ),
        CommandSpec(
            "add_mate", "Mate", "ensamblaje", AddMateParams, _exec_add_mate, wants_mates=True
        ),
        CommandSpec(
            "add_rail_constraint", "Restricción de riel", "ensamblaje", AddRailConstraintParams,
            _exec_add_rail_constraint, wants_constraints=True,
        ),
        CommandSpec(
            "add_constraint", "Restricción", "ensamblaje", AddConstraintParams,
            _exec_add_constraint, wants_constraints=True,
        ),
        CommandSpec(
            "fasten", "Fijador", "ensamblaje", FastenParams, _exec_fasten, wants_connectivity=True
        ),
        CommandSpec(
            "ground", "Anclaje a tierra", "ensamblaje", GroundParams, _exec_ground, wants_connectivity=True
        ),
        CommandSpec(
            "create_group", "Grupo / sub-ensamblaje", "ensamblaje", CreateGroupParams,
            _exec_create_group, wants_groups=True,
        ),
        CommandSpec(
            "transform_group", "Mover grupo", "ensamblaje", TransformGroupParams,
            _exec_transform_group, wants_groups=True,
        ),
        CommandSpec("boolean_op", "Booleana", "modificar", BooleanOpParams, _exec_boolean),
        CommandSpec("fillet", "Redondeo", "modificar", FilletParams, _exec_fillet),
        CommandSpec("chamfer", "Chaflán", "modificar", ChamferParams, _exec_chamfer),
        CommandSpec("shell", "Vaciado", "modificar", ShellParams, _exec_shell),
        CommandSpec("drill_hole", "Taladro", "modificar", DrillHoleParams, _exec_drill_hole),
        CommandSpec("delete_faces", "Borrar caras", "modificar", DeleteFacesParams, _exec_delete_faces),
        CommandSpec("push_face", "Empujar/Jalar cara", "modificar", PushFaceParams, _exec_push_face),
        CommandSpec("add_joinery", "Unión de ebanistería", "modificar", AddJoineryParams, _exec_add_joinery),
        CommandSpec("transform", "Mover / Rotar", "modificar", TransformParams, _exec_transform),
        CommandSpec("center_in", "Centrar en", "modificar", CenterInParams, _exec_center_in),
        CommandSpec("distribute", "Repartir", "modificar", DistributeParams, _exec_distribute),
        CommandSpec("attach", "Ensamblar", "modificar", AttachParams, _exec_attach),
        CommandSpec("pattern_linear", "Patrón lineal", "modificar", PatternLinearParams, _exec_pattern),
        CommandSpec(
            "pattern_circular", "Patrón circular", "modificar", PatternCircularParams, _exec_pattern_circular
        ),
        CommandSpec(
            "pattern_group", "Patrón de grupo", "modificar", PatternGroupParams,
            _exec_pattern_group, wants_joints=True, wants_mates=True,
        ),
        CommandSpec("mirror_feature", "Espejo", "modificar", MirrorParams, _exec_mirror),
        CommandSpec("duplicate_feature", "Duplicar", "modificar", DuplicateParams, _exec_duplicate),
        CommandSpec("delete_feature", "Eliminar", "modificar", DeleteParams, _exec_delete),
        CommandSpec(
            "set_variable", "Variable", "variables", SetVariableParams, _exec_set_variable, kind="vars"
        ),
    ]
}


def _validate_model(cmd_type: str, params: dict) -> BaseModel:
    try:
        return REGISTRY[cmd_type].model.model_validate(params or {})
    except ValidationError as exc:
        issues = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise CommandError(f"Parámetros inválidos para {cmd_type}: {issues}") from exc


def validate_params(cmd_type: str, params: dict, variables: dict | None = None) -> BaseModel:
    """Valida parámetros resolviendo expresiones '=expr' contra las variables.

    Para set_variable comprueba además que la expresión evalúa sin ciclos
    con el resto de variables del proyecto.
    """
    if cmd_type not in REGISTRY:
        raise CommandError(f"Comando desconocido: {cmd_type}")
    variables = variables or {}
    spec = REGISTRY[cmd_type]

    if spec.kind == "vars":
        model = _validate_model(cmd_type, params)
        merged = dict(variables)
        merged[model.name] = model.expression
        try:
            resolve_all(merged)
        except ExpressionError as exc:
            raise CommandError(str(exc)) from exc
        return model

    try:
        resolved = resolve_params(params or {}, resolve_all(variables))
    except ExpressionError as exc:
        raise CommandError(str(exc)) from exc
    return _validate_model(cmd_type, resolved)


def execute_command(
    scene: Scene,
    cmd_id: str,
    cmd_type: str,
    params: dict,
    variables: dict | None = None,
    joints: Joints | None = None,
    attachments: dict | None = None,
    mates: dict | None = None,
    constraints: dict | None = None,
    fasteners: dict | None = None,
    grounds: dict | None = None,
    groups: dict | None = None,
) -> None:
    variables = variables if variables is not None else {}
    joints = joints if joints is not None else {}
    attachments = attachments if attachments is not None else {}
    mates = mates if mates is not None else {}
    constraints = constraints if constraints is not None else {}
    fasteners = fasteners if fasteners is not None else {}
    grounds = grounds if grounds is not None else {}
    groups = groups if groups is not None else {}
    model = validate_params(cmd_type, params, variables)
    spec = REGISTRY[cmd_type]
    if spec.kind == "vars":
        spec.executor(variables, cmd_id, model)
    elif spec.wants_all:
        # firma keyword-only TOTAL (insert_project y futuros super-comandos que
        # necesiten todo el contexto del documento)
        spec.executor(
            scene, cmd_id, model,
            attachments=attachments, groups=groups, joints=joints, mates=mates,
            constraints=constraints, fasteners=fasteners, grounds=grounds,
        )
    elif spec.wants_groups:
        # firma keyword-only uniforme para los comandos de grupo (evita la explosión
        # combinatoria de ramas por flags): reciben todo lo que pueden necesitar
        spec.executor(
            scene, cmd_id, model,
            groups=groups, joints=joints, mates=mates, constraints=constraints,
        )
    elif spec.wants_joints and spec.wants_mates:
        spec.executor(scene, joints, mates, cmd_id, model)
    elif spec.wants_joints:
        spec.executor(scene, joints, cmd_id, model)
    elif spec.wants_mates:
        spec.executor(scene, mates, cmd_id, model)
    elif spec.wants_constraints:
        spec.executor(scene, constraints, cmd_id, model)
    elif spec.wants_connectivity:
        spec.executor(scene, fasteners, grounds, cmd_id, model)
    elif spec.wants_attachments:
        spec.executor(scene, cmd_id, model, attachments)
    elif spec.wants_variables:
        spec.executor(scene, cmd_id, model, resolve_all(variables))
    else:
        spec.executor(scene, cmd_id, model)


def _schema_entry(spec) -> dict:
    return {
        "type": spec.type,
        "title": spec.title,
        "category": spec.category,
        "kind": spec.kind,
        "description": (spec.model.__doc__ or "").strip(),
        "schema": spec.model.model_json_schema(),
    }


def command_schemas(command_type: str | None = None) -> list[dict]:
    """JSON Schema de los comandos. Sin argumento devuelve los 35; con `command_type`
    devuelve una lista con solo ese (vacía si no existe)."""
    if command_type is not None:
        if command_type not in REGISTRY:
            return []
        return [_schema_entry(REGISTRY[command_type])]
    return [_schema_entry(spec) for spec in REGISTRY.values()]
