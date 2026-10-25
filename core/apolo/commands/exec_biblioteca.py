"""Executors de biblioteca: script IA, brazo robótico, transportador (con `_publish_axis_anchor`),
bastidor y esqueleto (`_emit_weldment_parts`) y chapa metálica.

Salieron de `registry.py` (plan partir-nucleo-congelado, F4) SIN cambiar su código: la huella de
`tests/test_contrato_comandos.py` es la misma. `registry` los re-exporta por IDENTIDAD
(`_publish_axis_anchor` y `_emit_weldment_parts` los usan otros super-comandos); params de la
fachada `.models`.
"""

from __future__ import annotations

from apolo.kernel import place

from .errors import CommandError
from .escena import Feature, Scene, register_definition
from .exec_ensamblaje import _register_joint
from .models import (
    CreateConveyorParams,
    CreateFrameParams,
    CreateRobotArmParams,
    CreateWeldmentParams,
    RunScriptParams,
    SheetMetalParams,
)
from .state import ExecContext


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
