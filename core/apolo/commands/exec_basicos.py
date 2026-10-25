"""Executors básicos: primitivas, booleana, patrones (lineal, de grupo, circular), espejo,
borrar, duplicar y `set_variable`.

Salieron de `registry.py` (plan partir-nucleo-congelado, F3) SIN cambiar su código: la huella de
`tests/test_contrato_comandos.py` es la misma. `registry` los re-exporta por IDENTIDAD; params
de la fachada `.models`.
"""

from __future__ import annotations

from apolo.kernel import boolean_op, linear_copy, make_box, make_cylinder, make_structural_profile

from .errors import CommandError
from .escena import Feature, _instanced, _orient_axis, _require
from .models import (
    BooleanOpParams,
    CreateBoxParams,
    CreateCylinderParams,
    CreateStructuralProfileParams,
    DeleteParams,
    DuplicateParams,
    MirrorParams,
    PatternCircularParams,
    PatternGroupParams,
    PatternLinearParams,
    SetVariableParams,
)
from .state import ExecContext


def _exec_create_box(ctx: ExecContext, cmd_id: str, p: CreateBoxParams) -> None:
    key = f"box|{p.width:g}|{p.depth:g}|{p.height:g}"
    _instanced(ctx.scene, cmd_id, p.name, make_box(p.width, p.depth, p.height), key,
               p.position.tuple(), p.rotation.tuple())


def _exec_create_cylinder(ctx: ExecContext, cmd_id: str, p: CreateCylinderParams) -> None:
    key = f"cyl|{p.radius:g}|{p.height:g}|{p.axis}"
    _instanced(ctx.scene, cmd_id, p.name, _orient_axis(make_cylinder(p.radius, p.height), p.axis),
               key, p.position.tuple(), p.rotation.tuple())


def _exec_create_profile(ctx: ExecContext, cmd_id: str, p: CreateStructuralProfileParams) -> None:
    try:
        base = make_structural_profile(p.profile, p.length)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
    key = f"prof|{p.profile}|{p.length:g}"
    _instanced(ctx.scene, cmd_id, p.name, base, key, p.position.tuple(), p.rotation.tuple())


def _exec_boolean(ctx: ExecContext, cmd_id: str, p: BooleanOpParams) -> None:
    target = _require(ctx.scene, p.target)
    tools = [_require(ctx.scene, t) for t in p.tools]
    if p.target in p.tools:
        raise CommandError("El objetivo no puede ser también herramienta")
    result = boolean_op(p.operation, target.shape, [t.shape for t in tools])
    if result is None or (hasattr(result, "volume") and result.volume <= 0):
        raise CommandError("La operación booleana produjo un sólido vacío")
    del ctx.scene[p.target]
    for t in p.tools:
        del ctx.scene[t]
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, result, cmd_id)


def _exec_pattern(ctx: ExecContext, cmd_id: str, p: PatternLinearParams) -> None:
    from apolo.kernel.matrix import multiply, transform_anchors, translation

    feat = _require(ctx.scene, p.feature)
    if p.spacing.tuple() == (0, 0, 0):
        raise CommandError("La separación del patrón no puede ser cero")
    sx, sy, sz = p.spacing.tuple()
    for i in range(1, p.count):
        copy = linear_copy(feat.shape, i, p.spacing.tuple())
        fid = f"{cmd_id}_{i}"
        off = translation(sx * i, sy * i, sz * i)
        matrix = multiply(off, feat.matrix) if feat.matrix is not None else None
        ctx.scene[fid] = Feature(
            fid, f"{feat.name} ({i + 1})", copy, cmd_id,
            component=feat.component, cut_length=feat.cut_length,
            mesh_key=feat.mesh_key if matrix is not None else None, matrix=matrix,
            anchors=transform_anchors(off, feat.anchors),  # V6.3d Fix 2: la copia hereda anclas
        )


_PATTERN_GROUP_MAX = 2000  # tope de sólidos generados por pattern_group (protege OCCT)


def _exec_pattern_group(ctx: ExecContext, cmd_id: str, p: PatternGroupParams) -> None:
    """Arraya todas las features del comando `source` en línea (count/spacing) y opcional
    rejilla (count2/spacing2). Bloquea si la fuente está referenciada por juntas/mates."""
    from apolo.kernel.matrix import multiply, transform_anchors, translation

    scene, joints, mates = ctx.scene, ctx.joints, ctx.mates
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
                off_m = translation(*off)
                matrix = multiply(off_m, feat.matrix) if feat.matrix is not None else None
                scene[fid] = Feature(
                    fid, f"{feat.name} ({i + 1},{k + 1})", copy, cmd_id,
                    component=feat.component, cut_length=feat.cut_length,
                    mesh_key=feat.mesh_key if matrix is not None else None, matrix=matrix,
                    anchors=transform_anchors(off_m, feat.anchors),  # V6.3d Fix 2: copia hereda anclas
                )


def _exec_delete(ctx: ExecContext, cmd_id: str, p: DeleteParams) -> None:
    _require(ctx.scene, p.feature)
    del ctx.scene[p.feature]


def _exec_duplicate(ctx: ExecContext, cmd_id: str, p: DuplicateParams) -> None:
    from apolo.kernel.matrix import multiply, transform_anchors, translation

    feat = _require(ctx.scene, p.feature)
    off = p.offset.tuple()
    copy = linear_copy(feat.shape, 1, off)  # clona y traslada por el desfase
    off_m = translation(*off)
    matrix = multiply(off_m, feat.matrix) if feat.matrix is not None else None
    ctx.scene[cmd_id] = Feature(
        cmd_id, f"{feat.name} (copia)", copy, cmd_id,
        component=feat.component, cut_length=feat.cut_length,
        mesh_key=feat.mesh_key if matrix is not None else None, matrix=matrix,
        anchors=transform_anchors(off_m, feat.anchors),  # V6.3d Fix 2: la copia hereda anclas
    )


def _exec_set_variable(ctx: ExecContext, cmd_id: str, p: SetVariableParams) -> None:
    ctx.variables[p.name] = p.expression


def _exec_pattern_circular(ctx: ExecContext, cmd_id: str, p: PatternCircularParams) -> None:
    from build123d import Pos, Rotation

    from apolo.kernel.matrix import axis_rotation_about_point, multiply, transform_anchors

    feat = _require(ctx.scene, p.feature)
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
        off = axis_rotation_about_point(ap, p.axis_dir, angle)
        matrix = multiply(off, feat.matrix) if feat.matrix is not None else None
        ctx.scene[fid] = Feature(
            fid, f"{feat.name} ({i + 1})", copy, cmd_id,
            component=feat.component, cut_length=feat.cut_length,
            mesh_key=feat.mesh_key if matrix is not None else None, matrix=matrix,
            anchors=transform_anchors(off, feat.anchors),  # V6.3d Fix 2: la copia hereda anclas
        )


_MIRROR_PLANES = {"xy": "XY", "xz": "XZ", "yz": "YZ"}


def _exec_mirror(ctx: ExecContext, cmd_id: str, p: MirrorParams) -> None:
    from build123d import Plane, mirror

    feat = _require(ctx.scene, p.feature)
    plane = getattr(Plane, _MIRROR_PLANES[p.plane])
    if p.offset:
        plane = plane.offset(p.offset)
    copy = mirror(feat.shape, about=plane)
    ctx.scene[cmd_id] = Feature(
        cmd_id, f"{feat.name} (espejo)", copy, cmd_id,
        component=feat.component, cut_length=feat.cut_length,
    )
