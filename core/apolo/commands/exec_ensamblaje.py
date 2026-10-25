"""Executors de ensamblaje: juntas (`_register_joint`, el arrastre `_joint_drag`), mates,
restricciones, anclaje a tierra, grupos y `transform_group` (con `_transform_point` y
`_transform_dir`, que usa también `insert_project`).

Salieron de `registry.py` (plan partir-nucleo-congelado, F4) SIN cambiar su código: la huella de
`tests/test_contrato_comandos.py` es la misma. `registry` los re-exporta por IDENTIDAD; params
de la fachada `.models`.
"""

from __future__ import annotations

from .errors import CommandError
from .escena import Joints, Scene, _ancestors, _require
from .models import (
    AddConstraintParams,
    AddJointParams,
    AddMateParams,
    AddRailConstraintParams,
    CreateGroupParams,
    GroundParams,
    TransformGroupParams,
)
from .state import ExecContext


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
