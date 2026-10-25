"""Gate permanente: las rutas viejas del núcleo siguen sirviendo, por IDENTIDAD, para siempre.

Plan [partir-nucleo-congelado](../docs/plans/partir-nucleo-congelado.md), D2 y D11: al partir
un archivo congelado, su ruta vieja queda como fachada (shim) que re-exporta cada nombre de
nivel superior que definía. Las listas son CERRADAS: un nombre que falta o que deja de ser el
MISMO objeto que en su casa nueva pone el gate rojo (un re-export por valor o una copia harían
que parchear una ruta no alcance a la otra). Cada fase del plan suma su sección.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

# ── models (F2) ───────────────────────────────────────────────────────────────

#: Casa nueva de cada nombre que `apolo.commands.models` definía en `1f01d0a`/`553b208`
#: (69 definiciones de nivel superior), en el orden del archivo original por familia.
MODELS: dict[str, tuple[str, ...]] = {
    "apolo.commands.models_base": (
        "_floor_to_int", "Vec3", "Rot3", "_roller_refs", "_profile_refs", "_motor_refs",
    ),
    "apolo.commands.models_basicos": (
        "CreateBoxParams", "CreateCylinderParams", "CreateStructuralProfileParams",
        "BooleanOpParams", "TransformParams", "PatternLinearParams", "PatternGroupParams",
        "DeleteParams", "DuplicateParams", "CenterInParams", "DistributeParams", "ANCHOR_NAMES",
        "AttachParams", "SnapToParams", "SetVariableParams",
    ),
    "apolo.commands.models_maquinas": (
        "CreateConveyorParams", "CreateWeldmentParams", "CreateFrameParams", "RunScriptParams",
        "CreateRobotArmParams",
    ),
    "apolo.commands.models_chapa": (
        "SheetSide", "Hole", "FlapHole", "FlapCutout", "ChildFlap", "FlapSpec",
        "SheetMetalParams",
    ),
    "apolo.commands.models_modificar": (
        "FilletParams", "DeleteFacesParams", "PushFaceParams", "ChamferParams", "ShellParams",
        "DRILL_AXES", "DrillHoleParams", "PatternCircularParams", "MirrorParams",
        "JOINERY_TYPES", "AddJoineryParams",
    ),
    "apolo.commands.models_croquis": (
        "CreateRevolveParams", "CreateExtrudePolyParams", "ImportStepParams", "SKETCH_DOC",
        "SketchExtrudeParams", "SketchRevolveParams", "HelixSpec", "SketchSweepParams",
        "LoftSection", "SketchLoftParams", "CurveSpec", "BoundarySurfaceParams",
        "FillSurfaceParams", "ThickenParams",
    ),
    "apolo.commands.models_ensamblaje": (
        "JOINT_TYPES", "AddJointParams", "MATE_TYPES", "AddMateParams",
        "AddRailConstraintParams", "CONSTRAINT_TYPES", "AddConstraintParams",
        "CreateGroupParams", "TransformGroupParams", "InsertProjectParams", "GroundParams",
    ),
    # re-exports que `models` ya tenía antes de partirse (dos directos, dos perezosos)
    "apolo.commands.models_selectores": ("EdgeSelector", "SlideUV"),
    "apolo.commands.models_union": ("JoinBoltedParams",),
    "apolo.commands.models_componente": ("InsertComponentParams", "OrientacionPerfil"),
}

#: Las definiciones propias de `models` antes de partirse (sin los re-exports viejos).
DEFINICIONES_MODELS = 69


def faltantes(ruta_vieja: str, casas: dict[str, tuple[str, ...]]) -> list[str]:
    """Nombres que `ruta_vieja` ya no sirve o que no son el MISMO objeto que en su casa."""
    vieja = importlib.import_module(ruta_vieja)
    malos: list[str] = []
    for casa, nombres in casas.items():
        nueva = importlib.import_module(casa)
        for nombre in nombres:
            if not hasattr(vieja, nombre):
                malos.append(f"{ruta_vieja}.{nombre}: ya no existe")
            elif getattr(vieja, nombre) is not getattr(nueva, nombre):
                malos.append(f"{ruta_vieja}.{nombre}: no es el objeto de {casa}")
    return malos


def test_models_sirve_cada_nombre_viejo_por_identidad():
    assert faltantes("apolo.commands.models", MODELS) == []


#: Casas de los re-exports que `models` ya tenía (no son definiciones suyas).
_REEXPORTS_VIEJOS = {
    "apolo.commands.models_selectores",
    "apolo.commands.models_union",
    "apolo.commands.models_componente",
}


def test_models_lista_cerrada():
    propios = [n for casa, ns in MODELS.items() if casa not in _REEXPORTS_VIEJOS for n in ns]
    assert len(propios) == len(set(propios)) == DEFINICIONES_MODELS


@pytest.mark.parametrize("casa", sorted(MODELS))
def test_cada_casa_nueva_define_lo_que_se_le_atribuye(casa):
    """La casa declarada es la de verdad (una clase o función nace en su módulo)."""
    mod = importlib.import_module(casa)
    for nombre in MODELS[casa]:
        obj = getattr(mod, nombre)
        if isinstance(obj, type) or inspect.isfunction(obj):
            assert obj.__module__ == casa, f"{nombre} nace en {obj.__module__}, no en {casa}"


def test_el_gate_caza_un_nombre_que_falta(monkeypatch):
    import apolo.commands.models as models

    monkeypatch.delattr(models, "Vec3")
    assert faltantes("apolo.commands.models", MODELS) == [
        "apolo.commands.models.Vec3: ya no existe"
    ]


def test_el_gate_caza_una_copia_en_vez_del_mismo_objeto(monkeypatch):
    import apolo.commands.models as models

    class CreateBoxParams:  # mismo nombre, otro objeto
        pass

    monkeypatch.setattr(models, "CreateBoxParams", CreateBoxParams)
    assert faltantes("apolo.commands.models", MODELS) == [
        "apolo.commands.models.CreateBoxParams: no es el objeto de apolo.commands.models_basicos"
    ]


# ── mcp_server (F1) ───────────────────────────────────────────────────────────

#: Casa de cada tool que `apolo.mcp_server` definía en línea en `1f13862` (76), en el orden de
#: `list_tools()`. Las de `tools/` nacen DENTRO de `registrar` (no son atributos de su módulo):
#: su casa se prueba por `__module__` y su identidad contra la tool registrada en `mcp`.
MCP: dict[str, tuple[str, ...]] = {
    "apolo.tools.consulta": (
        "get_scene", "get_command_schemas", "get_catalog", "get_bom", "get_costing",
        "set_material", "set_color", "set_vertical", "get_kinematics", "get_design_guidelines",
    ),
    "apolo.mcp_server": (
        "run_command", "run_batch", "edit_command", "edit_batch", "get_job", "undo",
        "set_variable",
    ),
    "apolo.tools.validacion": ("check_interference", "engineering_check", "render_view", "preview"),
    "apolo.tools.proyectos": (
        "list_projects", "open_project", "create_project", "save_revision", "save_configuration",
        "apply_configuration", "export_step", "export_stl", "export_flat_pattern", "drop_test",
    ),
    "apolo.tools.introspeccion": (
        "get_command", "find_commands", "test_sketch", "test_script", "redo", "get_mates",
        "get_dof", "check_assembly", "autodetect_connections", "get_connections",
        "delete_connection", "delivery_check", "gravity_test", "get_motion", "set_motion",
        "scan_motion", "motion_gif", "get_stackup", "set_stackup", "list_revisions",
        "restore_revision",
    ),
    "apolo.tools.topologia": (
        "get_topology", "get_requirements", "set_requirements", "auto_group", "get_groups",
        "get_mass_properties", "measure", "near", "verify", "pick_point",
    ),
    "apolo.tools.fabricacion": (
        "cut_list", "nesting", "drawing_set", "calc_report", "quotation", "assembly_manual",
        "drawing",
    ),
    "apolo.tools.visibilidad": ("set_visibility", "set_visibility_bulk"),
    "apolo.tools.calculo": (
        "resolve_expression", "get_expression_grammar", "get_fit", "fea_static", "fea_assembly",
    ),
}

#: Lo que `mcp_server` conserva además de las tools (D2): los tests lo parchean o lo importan.
MCP_INFRA = ("_api", "_reject", "_submit_and_wait", "_mutacion", "_paso", "APOLO_URL",
             "APOLO_MCP_WAIT_S", "_scene_brief", "_one_or_many", "_job_receipt", "_job_result")

TOOLS_EN_LINEA_MCP = 76


def faltantes_mcp() -> list[str]:
    """Tools que `apolo.mcp_server` ya no sirve como atributo invocable, que no son la función
    registrada en su `mcp` o que no nacieron en su casa; y la infraestructura que falta."""
    pytest.importorskip("mcp")
    srv = importlib.import_module("apolo.mcp_server")
    malos: list[str] = []
    for casa, nombres in MCP.items():
        for nombre in nombres:
            fn = getattr(srv, nombre, None)
            if not callable(fn):
                malos.append(f"apolo.mcp_server.{nombre}: ya no existe")
                continue
            tool = srv.mcp._tool_manager.get_tool(nombre)
            if tool is None or tool.fn is not fn:
                malos.append(f"apolo.mcp_server.{nombre}: no es la tool registrada en mcp")
            elif fn.__module__ != casa:
                malos.append(f"apolo.mcp_server.{nombre}: nace en {fn.__module__}, no en {casa}")
    return malos + [f"apolo.mcp_server.{n}: ya no existe" for n in MCP_INFRA
                    if not hasattr(srv, n)]


def test_mcp_server_sirve_cada_tool_por_identidad():
    assert faltantes_mcp() == []


def test_mcp_lista_cerrada():
    nombres = [n for ns in MCP.values() for n in ns]
    assert len(nombres) == len(set(nombres)) == TOOLS_EN_LINEA_MCP


def test_el_gate_mcp_caza_una_tool_que_falta(monkeypatch):
    pytest.importorskip("mcp")
    import apolo.mcp_server as srv

    monkeypatch.delattr(srv, "get_scene")
    assert faltantes_mcp() == ["apolo.mcp_server.get_scene: ya no existe"]


def test_el_gate_mcp_caza_una_copia(monkeypatch):
    pytest.importorskip("mcp")
    import apolo.mcp_server as srv

    def verify(checks):  # mismo nombre, otra función
        return ""

    monkeypatch.setattr(srv, "verify", verify)
    assert faltantes_mcp() == ["apolo.mcp_server.verify: no es la tool registrada en mcp"]


def test_las_tools_movidas_ven_el_api_parcheado(monkeypatch):
    """Las tools de `tools/` reciben `_api` como lambda tardía: parchear `mcp_server._api` llega."""
    pytest.importorskip("mcp")
    import apolo.mcp_server as srv

    class _Resp:
        def json(self):
            return {"ok": "parcheado"}

    monkeypatch.setattr(srv, "_api", lambda *a, **k: _Resp())
    assert srv.get_kinematics() == '{"ok": "parcheado"}'
    assert srv.resolve_expression("=1") == '{"ok": "parcheado"}'


# ── registry (F3) ─────────────────────────────────────────────────────────────

#: Casa nueva de cada nombre que `apolo.commands.registry` definía en `c11bca8` y salió en la F3
#: (51), en el orden del archivo original por módulo. Los que salieron en la F4, en `REGISTRY_F4`.
REGISTRY_F3: dict[str, tuple[str, ...]] = {
    "apolo.commands.escena": (
        "Feature", "DEFINITIONS", "_DEFINITIONS_CAP", "register_definition", "touch_definition",
        "Scene", "Joints", "_ancestors", "_require", "_instanced", "_orient_axis", "_resolve_sel",
    ),
    "apolo.commands.exec_basicos": (
        "_exec_create_box", "_exec_create_cylinder", "_exec_create_profile", "_exec_boolean",
        "_exec_pattern", "_PATTERN_GROUP_MAX", "_exec_pattern_group", "_exec_delete",
        "_exec_duplicate", "_exec_set_variable", "_exec_pattern_circular", "_MIRROR_PLANES",
        "_exec_mirror",
    ),
    "apolo.commands.exec_colocacion": (
        "_world_move", "_world_place", "_exec_transform", "_bbox_center", "_exec_center_in",
        "_exec_distribute", "_v_sub", "_v_dot", "_v_cross", "_v_unit", "_planar_face_frame",
        "_ANCHOR_FNS", "_anchor_point", "_exec_attach", "_exec_snap_face", "_exec_snap_to",
    ),
    "apolo.commands.exec_modificar": (
        "_exec_delete_faces", "_exec_push_face", "_shortest_edge_mm", "_exec_fillet",
        "_exec_chamfer", "_exec_shell", "_DRILL_DIRS", "_drill_tool", "_exec_drill_hole",
        "_exec_add_joinery",
    ),
}

MOVIDOS_REGISTRY_F3 = 51


def test_registry_sirve_cada_nombre_movido_por_identidad():
    assert faltantes("apolo.commands.registry", REGISTRY_F3) == []


def test_registry_lista_cerrada():
    nombres = [n for ns in REGISTRY_F3.values() for n in ns]
    assert len(nombres) == len(set(nombres)) == MOVIDOS_REGISTRY_F3


@pytest.mark.parametrize("casa", sorted(REGISTRY_F3))
def test_cada_casa_nueva_de_registry_define_lo_suyo(casa):
    mod = importlib.import_module(casa)
    for nombre in REGISTRY_F3[casa]:
        obj = getattr(mod, nombre)
        if isinstance(obj, type) or inspect.isfunction(obj):
            assert obj.__module__ == casa, f"{nombre} nace en {obj.__module__}, no en {casa}"


def test_los_executors_movidos_del_registro_son_los_de_su_casa():
    """El `REGISTRY` despacha el MISMO objeto que vive en la casa nueva (sin copias)."""
    from apolo.commands.registry import REGISTRY

    casas = {n: casa for casa, ns in REGISTRY_F3.items() for n in ns}
    movidos = [s for s in REGISTRY.values() if s.executor.__name__ in casas]
    assert len(movidos) == 23
    for spec in movidos:
        casa = importlib.import_module(casas[spec.executor.__name__])
        assert spec.executor is getattr(casa, spec.executor.__name__), spec.type


def test_un_blob_viejo_con_la_ruta_de_registry_carga():
    """La caché de geometría picklea `Feature`: los blobs escritos antes de la F3 nombran
    `apolo.commands.registry.Feature` y siguen cargando por el re-export (D3)."""
    import pickle

    from apolo.commands.escena import Feature

    nuevo = pickle.dumps(Feature("c1", "Caja", None, "c1", mesh_key="box|1|1|1"), protocol=0)
    assert b"apolo.commands.escena" in nuevo
    viejo = nuevo.replace(b"apolo.commands.escena", b"apolo.commands.registry")
    feat = pickle.loads(viejo)
    assert type(feat) is Feature
    assert (feat.id, feat.name, feat.mesh_key) == ("c1", "Caja", "box|1|1|1")


def test_el_gate_registry_caza_un_nombre_que_falta(monkeypatch):
    import apolo.commands.registry as registry

    monkeypatch.delattr(registry, "_drill_tool")
    assert faltantes("apolo.commands.registry", REGISTRY_F3) == [
        "apolo.commands.registry._drill_tool: ya no existe"
    ]


def test_el_gate_registry_caza_una_copia(monkeypatch):
    import apolo.commands.registry as registry

    def _require(scene, feature_id):  # mismo nombre, otra función
        return scene[feature_id]

    monkeypatch.setattr(registry, "_require", _require)
    assert faltantes("apolo.commands.registry", REGISTRY_F3) == [
        "apolo.commands.registry._require: no es el objeto de apolo.commands.escena"
    ]


# ── registry (F4) ─────────────────────────────────────────────────────────────

#: Casa nueva de cada nombre que `apolo.commands.registry` definía en `ad26ad5` y salió en la F4
#: (31), en el orden del archivo original por módulo.
REGISTRY_F4: dict[str, tuple[str, ...]] = {
    "apolo.commands.exec_croquis": (
        "_exec_sketch_sweep", "_exec_sketch_loft", "_exec_boundary_surface",
        "_exec_fill_surface", "_exec_thicken", "_exec_create_revolve",
        "_exec_create_extrude_poly", "_exec_sketch_extrude", "_exec_sketch_revolve",
        "_exec_import_step",
    ),
    "apolo.commands.exec_ensamblaje": (
        "_register_joint", "_joint_drag", "_exec_add_joint", "_exec_add_mate",
        "_exec_add_rail_constraint", "_exec_add_constraint", "_exec_ground",
        "_exec_create_group", "_transform_point", "_transform_dir", "_exec_transform_group",
    ),
    "apolo.commands.exec_insertar": ("_insert_project_precheck", "_exec_insert_project"),
    "apolo.commands.exec_biblioteca": (
        "_exec_create_robot_arm", "_exec_run_script", "_publish_axis_anchor",
        "_exec_create_conveyor", "_emit_weldment_parts", "_exec_create_weldment",
        "_exec_create_frame", "_exec_create_sheet_metal",
    ),
}

MOVIDOS_REGISTRY_F4 = 31

#: Lo único que `registry` DEFINE tras la F4 (D7): el registro, el despacho y los schemas. Un
#: executor nuevo va a su `exec_*.py`; aquí sólo se re-exporta.
PROPIOS_REGISTRY = ("REGISTRY", "_validate_model", "validate_params", "execute_command",
                    "_schema_entry", "command_schemas")


def test_registry_sirve_cada_nombre_movido_en_la_f4_por_identidad():
    assert faltantes("apolo.commands.registry", REGISTRY_F4) == []


def test_registry_f4_lista_cerrada():
    nombres = [n for ns in REGISTRY_F4.values() for n in ns]
    assert len(nombres) == len(set(nombres)) == MOVIDOS_REGISTRY_F4
    assert not set(nombres) & {n for ns in REGISTRY_F3.values() for n in ns}


@pytest.mark.parametrize("casa", sorted(REGISTRY_F4))
def test_cada_casa_nueva_de_registry_f4_define_lo_suyo(casa):
    mod = importlib.import_module(casa)
    for nombre in REGISTRY_F4[casa]:
        obj = getattr(mod, nombre)
        if isinstance(obj, type) or inspect.isfunction(obj):
            assert obj.__module__ == casa, f"{nombre} nace en {obj.__module__}, no en {casa}"


def test_los_executors_movidos_en_la_f4_son_los_de_su_casa():
    """El `REGISTRY` despacha el MISMO objeto que vive en la casa nueva (sin copias)."""
    from apolo.commands.registry import REGISTRY

    casas = {n: casa for casa, ns in REGISTRY_F4.items() for n in ns}
    movidos = [s for s in REGISTRY.values() if s.executor.__name__ in casas]
    assert len(movidos) == 24
    for spec in movidos:
        casa = importlib.import_module(casas[spec.executor.__name__])
        assert spec.executor is getattr(casa, spec.executor.__name__), spec.type


def test_registry_solo_define_registro_despacho_y_schemas():
    """Toda función o clase que `registry` expone nace fuera, salvo las de `PROPIOS_REGISTRY`."""
    import apolo.commands.registry as registry

    propias = sorted(
        n for n, obj in vars(registry).items()
        if (inspect.isfunction(obj) or isinstance(obj, type))
        and obj.__module__ == registry.__name__
    )
    assert propias == sorted(n for n in PROPIOS_REGISTRY if n != "REGISTRY")
    assert isinstance(registry.REGISTRY, dict)


def test_el_gate_registry_f4_caza_un_nombre_que_falta(monkeypatch):
    import apolo.commands.registry as registry

    monkeypatch.delattr(registry, "_emit_weldment_parts")
    assert faltantes("apolo.commands.registry", REGISTRY_F4) == [
        "apolo.commands.registry._emit_weldment_parts: ya no existe"
    ]


def test_el_gate_registry_f4_caza_una_copia(monkeypatch):
    import apolo.commands.registry as registry

    def _register_joint(scene, joints, cmd_id, spec):  # mismo nombre, otra función
        return None

    monkeypatch.setattr(registry, "_register_joint", _register_joint)
    assert faltantes("apolo.commands.registry", REGISTRY_F4) == [
        "apolo.commands.registry._register_joint: no es el objeto de apolo.commands.exec_ensamblaje"
    ]
