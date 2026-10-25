"""Registro de comandos: validación, ejecución y schemas.

Cada comando declara su modelo de parámetros (pydantic) y un ejecutor que
muta la escena. El documento reproduce el log de comandos en orden para
regenerar la escena completa.

La base de la escena (`Feature`, definiciones) está en `escena.py` y los executors, por
familia, en `exec_*.py`; aquí quedan los que aún no se mudaron, el `REGISTRY`, el despacho
y los schemas.
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

from apolo.kernel import place

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
    CreateBoxParams,
    CreateConveyorParams,
    CreateCylinderParams,
    CreateExtrudePolyParams,
    CreateFrameParams,
    CreateRevolveParams,
    CreateRobotArmParams,
    CreateWeldmentParams,
    CreateStructuralProfileParams,
    CreateGroupParams,
    DeleteFacesParams,
    DeleteParams,
    DistributeParams,
    DuplicateParams,
    DrillHoleParams,
    FillSurfaceParams,
    FilletParams,
    GroundParams,
    ImportStepParams,
    InsertProjectParams,
    JoinBoltedParams,
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
    SnapToParams,
    ThickenParams,
    TransformGroupParams,
    TransformParams,
)
from .models_rodillos import CreateDriveRollerParams, CreateTakeUpParams
from .models_transmision import CreateChainParams
from .models_uniones import FastenParams
from .exec_componente import SELLOS as SELLOS_COMPONENTE, _exec_insert_component
from .exec_rodillos import _exec_create_drive_roller, _exec_create_take_up
from .models_componente import InsertComponentParams
from .exec_transmision import _exec_create_chain
from .exec_uniones import _exec_fasten
from .exec_union import _exec_join_bolted, sellar as _sellar_join_bolted
from .electrico import SPECS_ELECTRICO  # el carril eléctrico (V8.1 D2): fuera del bucle
from .cilindro import SPECS_CILINDRO  # super-comando compuesto (V8.9 D5)
from .exec_rodillos_cadena import SPECS_RODILLOS_CADENA  # super-comando compuesto
from .exec_faja import CreateBeltConveyorParams, _exec_create_belt_conveyor, sellar as _sellar_faja
from .errors import CommandError
from .spec import CommandSpec, run_executor
from .state import ExecContext, RegenState
from .strict import reject_unknown

# La base de la escena y los executors de modelado viven en `escena` y `exec_*` (plan
# partir-nucleo-congelado, F3); aquí se re-exportan por IDENTIDAD, para siempre
# (`tests/test_rutas_viejas.py`): los imports perezosos de executors ajenos y los blobs de la
# caché de geometría (`apolo.commands.registry.Feature`) los buscan en esta ruta.
from .escena import (  # noqa: F401
    Feature,
    DEFINITIONS,
    _DEFINITIONS_CAP,
    register_definition,
    touch_definition,
    Scene,
    Joints,
    _ancestors,
    _require,
    _instanced,
    _orient_axis,
    _resolve_sel,
)
from .exec_basicos import (  # noqa: F401
    _exec_create_box,
    _exec_create_cylinder,
    _exec_create_profile,
    _exec_boolean,
    _exec_pattern,
    _PATTERN_GROUP_MAX,
    _exec_pattern_group,
    _exec_delete,
    _exec_duplicate,
    _exec_set_variable,
    _exec_pattern_circular,
    _MIRROR_PLANES,
    _exec_mirror,
)
from .exec_colocacion import (  # noqa: F401
    _world_move,
    _world_place,
    _exec_transform,
    _bbox_center,
    _exec_center_in,
    _exec_distribute,
    _v_sub,
    _v_dot,
    _v_cross,
    _v_unit,
    _planar_face_frame,
    _ANCHOR_FNS,
    _anchor_point,
    _exec_attach,
    _exec_snap_face,
    _exec_snap_to,
)
from .exec_modificar import (  # noqa: F401
    _exec_delete_faces,
    _exec_push_face,
    _shortest_edge_mm,
    _exec_fillet,
    _exec_chamfer,
    _exec_shell,
    _DRILL_DIRS,
    _drill_tool,
    _exec_drill_hole,
    _exec_add_joinery,
)


def _exec_sketch_sweep(ctx: ExecContext, cmd_id: str, p: SketchSweepParams) -> None:
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
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_sketch_loft(ctx: ExecContext, cmd_id: str, p: SketchLoftParams) -> None:
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
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_boundary_surface(ctx: ExecContext, cmd_id: str, p: BoundarySurfaceParams) -> None:
    from apolo.kernel.surface import SurfaceError, boundary_surface

    try:
        base = boundary_surface(p.curves, points=p.points, holes=p.holes)
    except SurfaceError as exc:
        raise CommandError(f"Superficie: {exc}") from exc
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_fill_surface(ctx: ExecContext, cmd_id: str, p: FillSurfaceParams) -> None:
    from apolo.kernel.surface import SurfaceError, fill_surface_from_edges

    feat = _require(ctx.scene, p.feature)
    edges = _resolve_sel(feat.shape, p.edges, "edge")
    try:
        patch = fill_surface_from_edges(feat.shape, edges, tangent=p.tangent)
    except SurfaceError as exc:
        raise CommandError(f"Parche: {exc}") from exc
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, patch, cmd_id)


def _exec_thicken(ctx: ExecContext, cmd_id: str, p: ThickenParams) -> None:
    from apolo.kernel.shapes import is_surface
    from apolo.kernel.surface import SurfaceError, thicken_surface

    feat = _require(ctx.scene, p.feature)
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


def _exec_create_revolve(ctx: ExecContext, cmd_id: str, p: CreateRevolveParams) -> None:
    from apolo.kernel.shapes import make_revolution

    try:
        base = make_revolution(p.profile, p.angle)
    except Exception as exc:
        raise CommandError(f"Perfil de revolución inválido: {exc}") from exc
    if base.volume <= 0:
        raise CommandError("La revolución produjo un sólido vacío")
    base = _orient_axis(base, p.axis)
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_create_extrude_poly(ctx: ExecContext, cmd_id: str, p: CreateExtrudePolyParams) -> None:
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
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_sketch_extrude(ctx: ExecContext, cmd_id: str, p: SketchExtrudeParams) -> None:
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
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_sketch_revolve(ctx: ExecContext, cmd_id: str, p: SketchRevolveParams) -> None:
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
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_import_step(ctx: ExecContext, cmd_id: str, p: ImportStepParams) -> None:
    from apolo.sandbox import step_bytes_to_shape

    scene = ctx.scene
    data = ctx.attachments.get(p.attachment)
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


def _joint_drag(scene: Scene, joints: Joints, fasteners: dict, grounds: dict,
                cmd_id: str, p: AddJointParams) -> dict:
    """Flood de ARRASTRE (V6.8-D): materializa como juntas `fija` el cuerpo rígido
    colgado del hijo. Grafo = FIJADORES declarados hasta este punto del log (los
    declarados después no existen aún → declarar uniones antes que juntas). Cada
    flood EXCLUYE el nodo del lado contrario («sin cruzar esta junta»): así el
    fijador del pivote no fuga un lado hacia el otro. Una pieza alcanzable por
    AMBOS lados = disputa → `frontera`, no se arrastra (el agente decide);
    ya-hija-de-otra-junta o anclada a tierra → se omite con aviso."""
    ids = set(scene.keys())
    adj: dict[str, set[str]] = {}
    for f in fasteners.values():
        a, b = f.get("a"), f.get("b")
        if a in ids and b in ids and a != b:
            adj.setdefault(a, set()).add(b)
            adj.setdefault(b, set()).add(a)

    def reach(seed: str, sin: str) -> set[str]:
        seen, stack = {sin}, [seed]  # `sin` marcado visto = el flood no lo cruza
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(adj.get(n, ()))
        return seen - {sin}

    lado_hijo = reach(p.child, sin=p.parent)
    lado_padre = reach(p.parent, sin=p.child)
    frontera = sorted((lado_hijo & lado_padre) - {p.child, p.parent})
    grounded = {g.get("feature") for g in grounds.values()}
    con_junta = {j["child"] for j in joints.values()}
    arrastrados: list[str] = []
    avisos: list[str] = []
    for fid in sorted(lado_hijo - lado_padre - {p.child}):
        if fid in con_junta:
            avisos.append(f"'{fid}' ya es hijo de otra junta — no se arrastra")
            continue
        if fid in grounded:
            avisos.append(f"'{fid}' está anclado a tierra — no se arrastra")
            continue
        _register_joint(
            scene, joints, cmd_id,
            {
                "name": f"jf_{p.name}_{fid}", "type": "fija", "parent": p.child,
                "child": fid, "origin": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, 1.0],
                "lower": 0.0, "upper": 0.0,
            },
        )
        arrastrados.append(fid)
    if frontera:
        # la disputa es VIRAL: una pieza unida a ambos lados hace ambiguo todo lo
        # conectado a través de ella — se declara, no se adivina
        avisos.append(
            "piezas alcanzables desde AMBOS lados de la articulación (disputa): "
            "revisa esos fijadores (¿cruzan la junta?) o declara la junta ANTES "
            "de declararlos; nada disputado se arrastra"
        )
    if not arrastrados and not frontera and not adj.get(p.child):
        avisos.append(
            f"'{p.child}' no tiene fijadores declarados — nada que arrastrar "
            "(declara las uniones con fasten ANTES de la junta)"
        )
    out: dict = {"arrastrados": arrastrados, "frontera": frontera[:20]}
    if len(frontera) > 20:
        out["frontera_total"] = len(frontera)
    if avisos:
        out["avisos"] = avisos[:20]
    return out


def _exec_add_joint(ctx: ExecContext, cmd_id: str, p: AddJointParams) -> None:
    scene, joints = ctx.scene, ctx.joints
    _register_joint(
        scene, joints, cmd_id,
        {
            "name": p.name, "type": p.type, "parent": p.parent, "child": p.child,
            "origin": list(p.origin.tuple()), "axis": list(p.axis.tuple()),
            "lower": p.lower, "upper": p.upper,
        },
    )
    if p.arrastrar:
        # metadato en la PROPIA junta (viaja en get_kinematics; se recalcula en
        # cada regenerate con el estado del log en este punto)
        joints[p.name]["arrastre"] = _joint_drag(
            scene, joints, ctx.fasteners, ctx.grounds, cmd_id, p
        )


def _exec_add_mate(ctx: ExecContext, cmd_id: str, p: AddMateParams) -> None:
    from apolo.assembly.mates import MateError, register_mate

    try:
        register_mate(
            ctx.scene, ctx.mates, cmd_id,
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


def _exec_add_rail_constraint(ctx: ExecContext, cmd_id: str, p: AddRailConstraintParams) -> None:
    from apolo.assembly.constraints import ConstraintError, register_constraint

    try:
        register_constraint(
            ctx.constraints, cmd_id,
            {
                "name": p.name, "joint": p.joint,
                "anchor": list(p.anchor.tuple()),
                "point": list(p.point.tuple()),
                "axis": list(p.axis.tuple()),
            },
        )
    except ConstraintError as exc:
        raise CommandError(str(exc)) from exc


def _exec_add_constraint(ctx: ExecContext, cmd_id: str, p: AddConstraintParams) -> None:
    """Restricción cinemática genérica (multi-restricción / N-GDL). Registra la condición;
    el solver global (solve_constraints) resuelve todas las juntas dependientes a la vez."""
    from apolo.assembly.constraints import ConstraintError, register_constraint

    try:
        register_constraint(
            ctx.constraints, cmd_id,
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


def _exec_ground(ctx: ExecContext, cmd_id: str, p: GroundParams) -> None:
    """Ancla una pieza a tierra (origen del camino de sujeción)."""
    from apolo.assembly.connectivity import ConnectivityError, register_ground

    try:
        register_ground(ctx.grounds, cmd_id, {"name": p.name, "feature": p.feature, "nota": p.nota})
    except ConnectivityError as exc:
        raise CommandError(str(exc)) from exc


def _exec_create_group(ctx: ExecContext, cmd_id: str, p: CreateGroupParams) -> None:
    """Declara un GRUPO/sub-ensamblaje por command_ids (V5.2). No muta geometría:
    la membresía se deriva en cada regenerate (feat.group)."""
    from apolo.assembly.groups import GroupError, register_group

    try:
        register_group(ctx.groups, cmd_id, {
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


def _exec_transform_group(ctx: ExecContext, cmd_id: str, p: TransformGroupParams) -> None:
    """Mueve un grupo ENTERO como cuerpo rígido (V5.2): todas sus piezas + las
    juntas/restricciones internas. Rechaza uniones que cruzan la frontera."""
    from apolo.assembly.groups import group_command_ids, group_features
    from apolo.kernel.matrix import multiply, rotation_about_center, translation
    from apolo.kernel.shapes import move_rotated_about

    scene, groups, joints, mates = ctx.scene, ctx.groups, ctx.joints, ctx.mates
    constraints = ctx.constraints
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


def _exec_insert_project(ctx: ExecContext, cmd_id: str, p: InsertProjectParams) -> None:
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

    scene, groups, joints, constraints = ctx.scene, ctx.groups, ctx.joints, ctx.constraints
    fasteners, grounds = ctx.fasteners, ctx.grounds
    # guard temprano: el nombre de instancia ES el grupo raíz — chocar aquí da el
    # error intuitivo (y no uno críptico de junta/fijador duplicado a mitad de emisión)
    if p.name in groups:
        raise CommandError(
            f"Ya existe un grupo llamado '{p.name}': el nombre de la instancia debe ser único"
        )
    data = ctx.attachments.get(p.attachment) if p.attachment else None
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


def _exec_create_robot_arm(ctx: ExecContext, cmd_id: str, p: CreateRobotArmParams) -> None:
    from apolo.robotics.arm import robot_arm_parts

    scene = ctx.scene
    try:
        parts, joint_specs = robot_arm_parts(p.alcance, p.position.tuple(), cmd_id)
    except ValueError as exc:
        raise CommandError(f"Brazo robótico: {exc}") from exc
    for part in parts:
        fid = f"{cmd_id}_{part['suffix']}"
        scene[fid] = Feature(fid, f"{p.name} · {part['name']}", part["shape"], cmd_id)
    for spec in joint_specs:
        _register_joint(scene, ctx.joints, cmd_id, spec)


def _exec_run_script(ctx: ExecContext, cmd_id: str, p: RunScriptParams) -> None:
    from apolo.sandbox import ScriptError, run_script_to_shape

    try:
        base = run_script_to_shape(p.code, ctx.resolved_variables())
    except ScriptError as exc:
        raise CommandError(str(exc)) from exc
    if not hasattr(base, "volume") or base.volume <= 0:
        raise CommandError("El script produjo geometría sin volumen")
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


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


def _exec_create_conveyor(ctx: ExecContext, cmd_id: str, p: CreateConveyorParams) -> None:
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
        ctx.scene[fid] = Feature(
            fid, f"{p.name} · {part.name}", shape, cmd_id,
            component=part.component, cut_length=part.cut_length,
            mesh_key=part.base_key if matrix is not None else None, matrix=matrix,
        )
        if part.suffix.startswith("rod") and part.suffix[3:].isdigit():
            roller_idx.append(int(part.suffix[3:]))
    # eje de cola (rodillo de entrada, -X) y motriz (rodillo de descarga, +X)
    if roller_idx:
        _publish_axis_anchor(ctx.scene, f"{cmd_id}_rod{min(roller_idx)}", "eje_cola")
        _publish_axis_anchor(ctx.scene, f"{cmd_id}_rod{max(roller_idx)}", "eje_motriz")


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


def _exec_create_weldment(ctx: ExecContext, cmd_id: str, p: CreateWeldmentParams) -> None:
    from apolo.library.weldment import weldment_parts

    try:
        parts = weldment_parts(
            p.ancho, p.fondo, p.alto, p.perfil, p.anillos_intermedios, p.cordones,
            p.esquinas,
        )
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Bastidor: {exc}") from exc
    _emit_weldment_parts(ctx.scene, cmd_id, p.name, parts, p.position.tuple(), p.rotation.tuple())


def _exec_create_frame(ctx: ExecContext, cmd_id: str, p: CreateFrameParams) -> None:
    from apolo.library.frame import frame_from_edges

    try:
        parts = frame_from_edges(p.nodes, p.edges, p.perfil, p.cordones, p.esquinas)
    except (ValueError, KeyError) as exc:
        raise CommandError(f"Esqueleto: {exc}") from exc
    _emit_weldment_parts(ctx.scene, cmd_id, p.name, parts, p.position.tuple(), p.rotation.tuple())


def _exec_create_sheet_metal(ctx: ExecContext, cmd_id: str, p: SheetMetalParams) -> None:
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
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


# Todo executor es `(ctx: ExecContext, cmd_id, p)`: ver `spec.py` y tests/test_despacho_unico.py.
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
        CommandSpec("import_step", "Importar STEP", "crear", ImportStepParams, _exec_import_step),
        CommandSpec(
            "insert_component", "Componente", "biblioteca", InsertComponentParams,
            _exec_insert_component, version=2, **SELLOS_COMPONENTE,  # v2: anclas; F6: criterio 2
        ),
        CommandSpec(
            "insert_project", "Insertar proyecto", "biblioteca", InsertProjectParams,
            _exec_insert_project, composite=True,  # su replay corre executors ajenos (D9)
        ),
        CommandSpec("create_conveyor", "Transportador", "biblioteca", CreateConveyorParams, _exec_create_conveyor),
        CommandSpec(
            "create_belt_conveyor", "Faja de banda", "biblioteca", CreateBeltConveyorParams,
            _exec_create_belt_conveyor, composite=True,  # corre fasten/ground (exec_faja)
            version=5, al_crear=_sellar_faja,  # v2 engomado; v3 tramos; v4 uniones; v5 cierres
        ),
        CommandSpec(
            "create_take_up", "Tensor de cola (trotadora)", "biblioteca", CreateTakeUpParams,
            _exec_create_take_up, version=2,  # v2: «Anillo Seeger DIN 472-Ø» (nombre comercial, F6)
        ),
        CommandSpec(
            "create_drive_roller", "Rodillo motriz (trotadora)", "biblioteca", CreateDriveRollerParams,
            _exec_create_drive_roller, version=2,  # v2: «Anillo Seeger DIN 472-Ø» (F6)
        ),
        CommandSpec("create_chain", "Cadena", "biblioteca", CreateChainParams, _exec_create_chain, version=2),
        CommandSpec("create_weldment", "Bastidor", "biblioteca", CreateWeldmentParams, _exec_create_weldment),
        CommandSpec("create_frame", "Esqueleto", "biblioteca", CreateFrameParams, _exec_create_frame),
        CommandSpec(
            "create_sheet_metal", "Chapa metálica", "biblioteca", SheetMetalParams,
            _exec_create_sheet_metal,
        ),
        CommandSpec("run_script", "Script IA", "crear", RunScriptParams, _exec_run_script, version=2),
        CommandSpec(
            "create_robot_arm", "Brazo robótico", "robotica", CreateRobotArmParams,
            _exec_create_robot_arm,
        ),
        CommandSpec("add_joint", "Junta", "robotica", AddJointParams, _exec_add_joint),
        CommandSpec("add_mate", "Mate", "ensamblaje", AddMateParams, _exec_add_mate),
        CommandSpec(
            "add_rail_constraint", "Restricción de riel", "ensamblaje", AddRailConstraintParams,
            _exec_add_rail_constraint,
        ),
        CommandSpec(
            "add_constraint", "Restricción", "ensamblaje", AddConstraintParams, _exec_add_constraint
        ),
        CommandSpec("fasten", "Fijador", "ensamblaje", FastenParams, _exec_fasten),
        CommandSpec("ground", "Anclaje a tierra", "ensamblaje", GroundParams, _exec_ground),
        CommandSpec(
            "join_bolted", "Unión atornillada", "ensamblaje", JoinBoltedParams, _exec_join_bolted,
            al_crear=_sellar_join_bolted,
        ),
        CommandSpec(
            "create_group", "Grupo / sub-ensamblaje", "ensamblaje", CreateGroupParams,
            _exec_create_group,
        ),
        CommandSpec(
            "transform_group", "Mover grupo", "ensamblaje", TransformGroupParams,
            _exec_transform_group,
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
        CommandSpec("snap_to", "Colocar junto a", "modificar", SnapToParams, _exec_snap_to),
        CommandSpec("pattern_linear", "Patrón lineal", "modificar", PatternLinearParams, _exec_pattern),
        CommandSpec(
            "pattern_circular", "Patrón circular", "modificar", PatternCircularParams, _exec_pattern_circular
        ),
        CommandSpec(
            "pattern_group", "Patrón de grupo", "modificar", PatternGroupParams, _exec_pattern_group
        ),
        CommandSpec("mirror_feature", "Espejo", "modificar", MirrorParams, _exec_mirror),
        CommandSpec("duplicate_feature", "Duplicar", "modificar", DuplicateParams, _exec_duplicate),
        CommandSpec("delete_feature", "Eliminar", "modificar", DeleteParams, _exec_delete),
        CommandSpec(
            "set_variable", "Variable", "variables", SetVariableParams, _exec_set_variable, kind="vars"
        ),
        *SPECS_RODILLOS_CADENA, *SPECS_CILINDRO,  # V8.9 D5: el cilindro neumático en 3D
        *SPECS_ELECTRICO,
    ]
}


def _validate_model(cmd_type: str, params: dict) -> BaseModel:
    try:  # `ignore` EXPLÍCITO: el replay tolera claves viejas; la entrada estricta va aparte (D6)
        return REGISTRY[cmd_type].model.model_validate(params or {}, extra="ignore")
    except ValidationError as exc:
        issues = "; ".join(
            f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise CommandError(f"Parámetros inválidos para {cmd_type}: {issues}") from exc


def validate_params(cmd_type: str, params: dict, variables: dict | None = None,
                    strict: bool = False, previous: dict | None = None) -> BaseModel:
    """Valida parámetros resolviendo '=expr' contra las variables (set_variable: además, que
    evalúe sin ciclos). `strict` = entrada de un cliente: rechaza las claves que el comando no
    declara; con `previous` (los params guardados de un edit) sólo las NUEVAS (`strict.py`)."""
    if cmd_type not in REGISTRY:
        raise CommandError(f"Comando desconocido: {cmd_type}")
    variables = variables or {}
    spec = REGISTRY[cmd_type]
    if strict:
        reject_unknown(spec, params, previous)

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
        resolved = resolve_params(params or {}, resolve_all(variables), spec.literales)
    except ExpressionError as exc:
        raise CommandError(str(exc)) from exc
    return _validate_model(cmd_type, resolved)


def execute_command(
    state: RegenState, cmd_id: str, cmd_type: str, params: dict, attachments: dict | None = None,
    carril: tuple = ()) -> None:
    """Ejecuta UN comando del log sobre `state` (dicts en sitio); `carril`: doc/carril.lectura."""
    model = validate_params(cmd_type, params, state.variables)
    ctx = ExecContext(state, attachments if attachments is not None else {}, carril)
    run_executor(REGISTRY[cmd_type], ctx, cmd_id, model)


def _schema_entry(spec) -> dict:
    # la description es la del schema (pydantic limpia el docstring con cleandoc): el `__doc__`
    # crudo lleva la sangría en Python 3.11/3.12, que no la quitan al compilar como 3.13
    schema = spec.model.model_json_schema()
    return {"type": spec.type, "title": spec.title, "category": spec.category, "kind": spec.kind,
            "description": schema.get("description", ""), "schema": schema}


def command_schemas(command_type: str | None = None) -> list[dict]:
    """JSON Schema de los comandos. Sin argumento devuelve TODOS; con `command_type`
    devuelve una lista con solo ese (vacía si no existe)."""
    if command_type is not None:
        if command_type not in REGISTRY:
            return []
        return [_schema_entry(REGISTRY[command_type])]
    return [_schema_entry(spec) for spec in REGISTRY.values()]
