"""Registro de comandos: validación, ejecución y schemas.

Cada comando declara su modelo de parámetros (pydantic) y un ejecutor que
muta la escena. El documento reproduce el log de comandos en orden para
regenerar la escena completa.

La base de la escena (`Feature`, definiciones) está en `escena.py` y los executors, por
familia, en `exec_*.py`; aquí quedan el shim que los re-exporta, el `REGISTRY`, el despacho
y los schemas.
"""

from __future__ import annotations

from pydantic import BaseModel, ValidationError

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
from .exec_izaje import _exec_create_hoist_chain  # plan cadena-de-izaje
from .models_izaje import CreateHoistChainParams
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

# La base de la escena y los executors viven en `escena` y `exec_*` (plan
# partir-nucleo-congelado, F3 y F4); aquí se re-exportan por IDENTIDAD, para siempre
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
from .exec_croquis import (  # noqa: F401
    _exec_sketch_sweep,
    _exec_sketch_loft,
    _exec_boundary_surface,
    _exec_fill_surface,
    _exec_thicken,
    _exec_create_revolve,
    _exec_create_extrude_poly,
    _exec_sketch_extrude,
    _exec_sketch_revolve,
    _exec_import_step,
)
from .exec_ensamblaje import (  # noqa: F401
    _register_joint,
    _joint_drag,
    _exec_add_joint,
    _exec_add_mate,
    _exec_add_rail_constraint,
    _exec_add_constraint,
    _exec_ground,
    _exec_create_group,
    _transform_point,
    _transform_dir,
    _exec_transform_group,
)
from .exec_insertar import (  # noqa: F401
    _insert_project_precheck,
    _exec_insert_project,
)
from .exec_biblioteca import (  # noqa: F401
    _exec_create_robot_arm,
    _exec_run_script,
    _publish_axis_anchor,
    _exec_create_conveyor,
    _emit_weldment_parts,
    _exec_create_weldment,
    _exec_create_frame,
    _exec_create_sheet_metal,
)


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
            version=6, al_crear=_sellar_faja,  # v4 uniones; v5 cierres; v6 tramos y retorno
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
        CommandSpec("create_hoist_chain", "Cadena de izaje", "biblioteca", CreateHoistChainParams,
                    _exec_create_hoist_chain),
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
            al_crear=_sellar_join_bolted, version=2,  # v2: el remache declara su Ø «Ø4.8» (F3f)
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
        issues = "; ".join(  # un validador de modelo no tiene loc: sólo su mensaje
            (f"{'.'.join(str(loc) for loc in e['loc'])}: " if e["loc"] else "") + e["msg"]
            for e in exc.errors()
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
