"""Executor de `insert_project`: instancia un proyecto completo con ids prefijados, tras
pre-validar todas sus colisiones (`_insert_project_precheck`).

Salió de `registry.py` (plan partir-nucleo-congelado, F4) SIN cambiar su código: la huella de
`tests/test_contrato_comandos.py` es la misma. `registry` lo re-exporta por IDENTIDAD; params de
la fachada `.models`; juntas y transformaciones de `exec_ensamblaje`.
"""

from __future__ import annotations

from apolo.kernel import place

from .errors import CommandError
from .escena import DEFINITIONS, Joints, Scene, register_definition
from .exec_ensamblaje import _register_joint, _transform_dir, _transform_point
from .models import InsertProjectParams
from .state import ExecContext


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
