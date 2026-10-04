"""Datos del golden del MCP (`scripts/golden_mcp.py`): respuestas canónicas por ruta y casos.

Las respuestas imitan la FORMA de la API real (las claves que el cliente fino lee), no sus
valores: el golden mide al cliente, no al servidor. Una tool nueva necesita al menos un caso
aquí (`tests/test_mcp_golden.py` lo exige).
"""

from __future__ import annotations

import json

URL_GOLDEN = "http://127.0.0.1:8000"
PNG = b"\x89PNG\r\n\x1a\n golden-png"
GIF = b"GIF89a golden-gif"
PDF = b"%PDF-1.7 golden-pdf"


def J(obj, status: int = 200) -> dict:
    return {"json": obj, "status": status}


def B(data: bytes, tipo: str = "application/octet-stream") -> dict:
    return {"bytes": data, "tipo": tipo}


def _feat(fid, nombre, cmd, **extra):
    return {"id": fid, "name": nombre, "visible": extra.pop("visible", True),
            "bbox": {"min": [0, 0, 0], "max": [100, 50, 20]}, "volume_mm3": 100000.0,
            "component": extra.pop("component", None), "command_id": cmd, **extra}


def escena(afectados=(), **extra) -> dict:
    """Payload de escena (lo que devuelven las mutaciones vía `_state_or_error`)."""
    return {
        "document": {
            "name": "golden", "configurations": ["4m", "3.2m"], "can_undo": True,
            "can_redo": False,
            "variables": [{"name": "L", "expression": "2000", "value": 2000.0}],
            "commands": [{"id": "c1", "type": "create_box", "params": {"name": "Base"}},
                         {"id": "v1", "type": "set_variable",
                          "params": {"name": "L", "expression": "2000"}},
                         {"id": "c2", "type": "insert_project", "params": {"project_id": 3}}],
        },
        "features": [
            _feat("c1", "Base", "c1", group="Estructura"),
            _feat("c2_c1", "Rodillo", "c2_c1", component="RODILLO-50", visible=False),
            _feat("c3", "Croquis", "c3", is_guide=True),
        ],
        "total_features": 3,
        "affected_command_ids": list(afectados),
        "mesh": "MALLA-NO-VA-AL-AGENTE",
        **extra,
    }


MUTA = J(escena(["c1"], aviso_estructura="0 anclajes declarados (golden)"))
RESULTADO_JOB = {**escena(["c1", "c2"]), "contrato": {"n_aserciones": 1, "ok": True}}
JOB_OK = J({"id": "j1", "estado": "ok", "resultado": RESULTADO_JOB})
ENCOLADO = J({"job_id": "j1", "estado": "encolado"}, 202)
JOB_404 = J({"detail": "Job 'zz' desconocido: el servidor se reinició o se desalojó. "
                       "El lote PUDO haber aplicado; verifícalo con get_scene."}, 404)


def _preview(req):
    return J({"fantasmas": [{"name": "Nueva", "bbox": [0, 1]}], "colisiones_nuevas": []}) \
        if json.loads(req.content).get("data") else B(PNG, "image/png")


def _drawing(req):
    if json.loads(req.content).get("format") == "svg":
        return B(b"<svg>golden</svg>", "image/svg+xml")
    return B(PDF, "application/pdf")


def _auto_group(req):
    if json.loads(req.content).get("dry_run"):
        return J({"proposal": [{"name": "Estructura", "members": ["c1"]}]})
    return J({**escena(["c1"]), "proposal": [{"name": "Estructura"}], "created": ["g1"]})


def _scene(req):
    if req.url.query:  # brief filtrado/paginado del servidor
        return J({"total_solidos": 3, "total_filtrado": 1, "truncado": False,
                  "solidos": [{"id": "c1", "nombre": "Base"}]})
    return J(escena())


RUTAS = [
    ("GET", r"/api/scene/summary", J({"grupos": [{"nombre": "Estructura", "n_piezas": 1}]})),
    ("GET", r"/api/scene", _scene),
    ("GET", r"/api/schemas", J([{"type": "create_box", "schema": {"type": "object"}}])),
    ("GET", r"/api/schemas/[^/]+", J({"type": "create_box", "schema": {"type": "object"}})),
    ("GET", r"/api/catalog", J([{"ref": "RODILLO-50", "name": "Rodillo Ø50"}])),
    ("GET", r"/api/bom", J([{"ref": "RODILLO-50", "qty": 4}])),
    ("GET", r"/api/costing\.json", J({"total_usd": 123.4, "filas": []})),
    ("POST", r"/api/features/(material|color|visibility)", MUTA),
    ("POST", r"/api/features/[^/]+/visibility", MUTA),
    ("POST", r"/api/vertical", MUTA),
    ("GET", r"/api/kinematics", J({"joints": [{"name": "j1", "tipo": "giratoria"}]})),
    ("GET", r"/api/design-guidelines", J({"principio": "golden"})),
    ("POST", r"/api/commands", MUTA),
    ("POST|PATCH", r"/api/commands/batch", ENCOLADO),
    ("GET", r"/api/jobs/[^/]+", JOB_OK),
    ("PUT", r"/api/commands/[^/]+", MUTA),
    ("POST", r"/api/(undo|redo)", J(escena())),
    ("POST", r"/api/variables", J(escena(["v1"]))),
    ("POST", r"/api/checks", J({"interferencias": {"pares": []}, "ingenieria": [{"ok": True}],
                                "estructura": {"reglas": []}, "otro": "no se muestra"})),
    ("GET", r"/api/render\.png", B(PNG, "image/png")),
    ("POST", r"/api/commands/preview", _preview),
    ("GET", r"/api/projects", J([{"id": 38, "name": "faja"}])),
    ("POST", r"/api/projects/\d+/open", J({**escena(), "briefing": {"grupos": 6}})),
    ("POST", r"/api/projects", J(escena())),
    ("POST", r"/api/revisions", J({"id": 7, "note": "golden"})),
    ("POST", r"/api/configurations", J(escena())),
    ("POST", r"/api/configurations/[^/]+/apply", J(escena(["v1"]))),
    ("GET", r"/api/export/(step|stl)", B(b"ISO-10303-21; golden")),
    ("GET", r"/api/sheetmetal/[^/]+/flat\.dxf", B(b"0\nSECTION golden")),
    ("POST", r"/api/physics/drop", J({"resting": [[0, 0, 10]], "settled": True,
                                      "frames": [1, 2, 3]})),
    ("POST", r"/api/physics/drop\.gif", B(GIF, "image/gif")),
    ("GET", r"/api/document", J(escena()["document"])),
    ("GET", r"/api/commands", J([{"id": "c1", "type": "create_box", "resumen": "Base"}])),
    ("POST", r"/api/sketch/solve", J({"ok": True, "dof": 0})),
    ("POST", r"/api/script/test", J({"ok": True, "volumen_mm3": 1.0})),
    ("GET", r"/api/mates", J([{"name": "m1"}])),
    ("GET", r"/api/assembly/dof", J({"solidos": []})),
    ("POST", r"/api/assembly/(soundness|autodetect)", J({"flotantes": [], "aisladas": []})),
    ("POST", r"/api/assembly/declare", J(escena(["c1"]))),
    ("GET", r"/api/connectivity", J({"grounds": [{"name": "g1"}], "fasteners": []})),
    ("POST", r"/api/connections/remove", J({**escena(), "conexiones_borradas": ["f1", "g1"]})),
    ("POST", r"/api/delivery-check", J({"veredicto": "VERDE", "bloqueantes": []})),
    ("POST", r"/api/assembly/stability", J({"n_grounded": 2, "n_dynamic": 1, "fell": [],
                                            "estables": ["c1"], "settled": True,
                                            "mensaje": "ok", "frames": [1, 2]})),
    ("POST", r"/api/assembly/stability\.gif", B(GIF, "image/gif")),
    ("GET", r"/api/motion", J({"studies": [{"name": "abrir"}]})),
    ("PUT", r"/api/motion", J({"ok": True, "studies": [
        {"name": "abrir", "duration": 2.0, "keyframes": [{"t": 0}, {"t": 2}]}]})),
    ("POST", r"/api/motion/scan", J({"colisiones": []})),
    ("POST", r"/api/motion\.gif", B(GIF, "image/gif")),
    ("GET|PUT", r"/api/stackup", J({"ok": True, "cadenas": []})),
    ("GET|POST", r"/api/agent/notes", J({"notes": ["nota golden"]})),
    ("GET", r"/api/revisions", J([{"id": 7}])),
    ("POST", r"/api/revisions/\d+/restore", J(escena())),
    ("GET", r"/api/features/[^/]+/topology", J({"caras": [], "aristas": []})),
    ("GET|PUT", r"/api/requirements", J({"requirements": {"carga_kg": 15}})),
    ("POST", r"/api/assembly/auto-group", _auto_group),
    ("GET", r"/api/groups", J({"groups": [{"name": "Estructura"}]})),
    ("GET", r"/api/mass-properties", J({"conjunto": {"masa_kg": 1.5}})),
    ("POST", r"/api/measure", J({"distancia_mm": 12.5})),
    ("GET", r"/api/near", J({"cercanos": []})),
    ("POST", r"/api/verify", J({"ok": True, "resultados": []})),
    ("GET", r"/api/pick", J({"feature": "c1", "punto": [0, 0, 0]})),
    ("GET", r"/api/cutlist\.json", J({"piezas": []})),
    ("GET", r"/api/nesting\.json", J({"planchas": 1, "desperdicio_pct": 12.0})),
    ("GET", r"/api/(drawingset|calc-report|quote|assembly-manual)\.pdf", B(PDF, "application/pdf")),
    ("POST", r"/api/drawing/spec", _drawing),
    ("GET", r"/api/resolve-expression", J({"ok": True, "value": 2000.0})),
    ("GET", r"/api/expression-grammar", J({"funciones": ["sqrt"]})),
    ("GET", r"/api/fits", J({"juego_min_um": 0})),
    ("POST", r"/api/fea/static", J({"fs": 3.2, "sigma_vm_max_mpa": 75.0})),
    ("GET", r"/api/fea/[^/]+/fringe\.png", B(PNG, "image/png")),
    ("POST", r"/api/fea/assembly", J({"grupo": "Bastidor", "fs_gobernante": 93.5})),
    ("GET", r"/api/fea/group/[^/]+/fringe\.png", B(PNG, "image/png")),
]
# «POST|PATCH» → dos entradas (el motor compara el método exacto)
RUTAS = [(m, rx, spec) for metodos, rx, spec in RUTAS for m in metodos.split("|")]

_ESC = {"type": "create_box", "params": {"name": "A", "width": 50}}


def caso(nombre, tool, args=None, rutas=None, espera=None) -> dict:
    c = {"caso": nombre, "tool": tool, "args": args or {}}
    if rutas:
        c["rutas"] = rutas
    if espera is not None:
        c["espera"] = espera
    return c


CASOS = [
    caso("escena completa", "get_scene"),
    caso("escena summary", "get_scene", {"summary": True}),
    caso("escena filtrada", "get_scene", {"ids": ["c1", "Estructura"], "name": "base",
                                          "limit": 10, "offset": 5}),
    caso("conexión rechazada", "get_scene", rutas={("GET", r"/api/scene"): {"conexion": True}}),
    caso("schemas todos", "get_command_schemas"),
    caso("schema uno", "get_command_schemas", {"command_type": "create_box"}),
    caso("catálogo", "get_catalog", {"category": "rodamientos", "names_only": True}),
    caso("bom", "get_bom"),
    caso("bom por grupo", "get_bom", {"by_group": True}),
    caso("costeo", "get_costing"),
    caso("material uno", "set_material", {"feature": "c1", "material": "acero"}),
    caso("material lote", "set_material", {"features": ["c1", "c3"]}),
    caso("material ambos → error", "set_material", {"feature": "c1", "features": ["c3"]}),
    caso("color", "set_color", {"color": "#ff0000", "features": ["c1"]}),
    caso("vertical", "set_vertical", {"vertical": "carpinteria"}),
    caso("cinemática", "get_kinematics"),
    caso("guía de diseño", "get_design_guidelines"),
    caso("comando", "run_command", {"type": "create_box", "params": {"width": 10}}),
    caso("comando full", "run_command", {"type": "create_box", "params": {}, "detail": "full"}),
    caso("comando 400 con detail", "run_command", {"type": "x", "params": {}},
         rutas={("POST", r"/api/commands"): J({"detail": "No existe el comando 'x'"}, 400)}),
    caso("comando 500 sin json", "run_command", {"type": "x", "params": {}},
         rutas={("POST", r"/api/commands"): B(b"Internal Server Error", "text/plain") | {"status": 500}}),
    caso("lote con contrato", "run_batch", {"actions": [_ESC, _ESC], "detail": "summary",
                                           "expect": [{"tipo": "existe", "id": "$1"}]}),
    caso("lote → recibo", "run_batch", {"actions": [_ESC]}, espera=0.0),
    caso("lote → job en error", "run_batch", {"actions": [_ESC]}, rutas={
        ("GET", r"/api/jobs/[^/]+"): J({"estado": "error", "http_status": 400,
                                        "error": "Contrato incumplido: medido 150 > 10"})}),
    caso("lote → job corriendo y luego ok", "run_batch", {"actions": [_ESC]}, rutas={
        ("GET", r"/api/jobs/[^/]+"): [J({"estado": "corriendo"}), JOB_OK]}),
    caso("editar", "edit_command", {"command_id": "c1", "params": {"width": 80}}),
    caso("editar replace", "edit_command", {"command_id": "c1", "params": {}, "merge": False,
                                            "detail": "summary"}),
    caso("editar lote", "edit_batch", {"edits": [{"command_id": "c1", "params": {"width": 1}}],
                                       "expect": [{"tipo": "existe", "id": "c1"}]}),
    caso("editar lote replace → recibo", "edit_batch", {"edits": [], "merge": False}, espera=0.0),
    caso("job ok", "get_job", {"job_id": "j1", "detail": "full", "wait_s": 5}),
    caso("job corriendo", "get_job", {"job_id": "j1"},
         rutas={("GET", r"/api/jobs/[^/]+"): J({"estado": "encolado"})}),
    caso("job en error", "get_job", {"job_id": "j1"},
         rutas={("GET", r"/api/jobs/[^/]+"): J({"estado": "error", "error": "boom"})}),
    caso("job 404", "get_job", {"job_id": "zz"}, rutas={("GET", r"/api/jobs/[^/]+"): JOB_404}),
    caso("deshacer", "undo"),
    caso("variable", "set_variable", {"name": "L", "expression": "2500"}),
    caso("interferencia global", "check_interference"),
    caso("interferencia acotada en pose", "check_interference",
         {"joint_values": {"j1": 30}, "ids": ["Estructura"]}),
    caso("ingeniería", "engineering_check", {"carga_kg": 15, "velocidad_m_s": 0.5}),
    caso("ingeniería faja", "engineering_check", {"conveyor": {"largo": 4000},
                                                  "conveyor_solid_ids": ["c1"]}),
    caso("render", "render_view"),
    caso("render completo", "render_view", {
        "view": "planta", "highlight_ids": ["c1"], "show_axes": True, "show_bbox": True,
        "joint_values": {"j1": 10.0}, "fit_ids": ["c1"], "zoom": 2.0, "section": "x",
        "isolate": ["Estructura"], "azimuth": 30, "elevation": 20, "measure": ["c1", "c3"],
        "edges": False, "xray": True, "labels": True, "roll": 5, "pan": [0.1, -0.2]}),
    caso("preview imagen", "preview", {"actions": [_ESC], "section": "z", "labels": True}),
    caso("preview datos", "preview", {"actions": [_ESC], "data": True}),
    caso("proyectos", "list_projects"),
    caso("abrir proyecto", "open_project", {"project_id": 38}),
    caso("crear proyecto", "create_project", {"name": "nuevo", "template": "transportador"}),
    caso("revisión", "save_revision", {"note": "antes de editar"}),
    caso("guardar configuración", "save_configuration", {"name": "4m"}),
    caso("aplicar configuración", "apply_configuration", {"name": "3.2m"}),
    caso("exportar step", "export_step", {"path": "modelo.step"}),
    caso("exportar stl", "export_stl", {"path": "modelo.stl", "tolerance": 0.2}),
    caso("desplegado", "export_flat_pattern", {"feature_id": "c1", "path": "flat.dxf"}),
    caso("caída", "drop_test", {"products": [{"w": 100, "d": 100, "h": 50, "x": 0, "y": 0,
                                              "z": 500}], "path": "caida.gif", "seconds": 1.0}),
    caso("comando por id", "get_command", {"command_id": "c1"}),
    caso("comando inexistente", "get_command", {"command_id": "c99"}),
    caso("buscar comandos", "find_commands", {"type": "chamfer", "feature": "c14",
                                              "name": "pata", "limit": 5}),
    caso("croquis", "test_sketch", {"sketch": {"points": [], "constraints": []}}),
    caso("script", "test_script", {"code": "result = Box(1, 1, 1)"}),
    caso("rehacer", "redo"),
    caso("mates", "get_mates"),
    caso("dof", "get_dof"),
    caso("sujeción", "check_assembly"),
    caso("sujeción con autodetect", "check_assembly", {"with_autodetect": True}),
    caso("autodetección", "autodetect_connections"),
    caso("declarar estructura", "declare_structure"),
    caso("conexiones", "get_connections"),
    caso("borrar conexión", "delete_connection", {"name": "f1"}),
    caso("borrar conexiones lote", "delete_connection", {"names": ["f1", "g1"]}),
    caso("borrar conexión sin nombre", "delete_connection"),
    caso("puerta de entrega", "delivery_check", {"con_gravedad": True}),
    caso("gravedad", "gravity_test"),
    caso("gravedad con gif", "gravity_test", {"with_autodetect": True, "exclude": ["c3"],
                                              "seconds": 1.5, "path": "gravedad.gif"}),
    caso("movimiento", "get_motion"),
    caso("definir movimiento", "set_motion", {"name": "abrir", "keyframes": [
        {"t": 0, "values": {"j1": 0}}, {"t": 2, "values": {"j1": 90}}]}),
    caso("escanear movimiento", "scan_motion", {"name": "abrir", "steps": 12}),
    caso("gif de movimiento", "motion_gif", {"name": "abrir", "path": "mov.gif", "pingpong": True,
                                             "azimuth": 45, "elevation": 30, "size_px": 400}),
    caso("stack-up", "get_stackup", {"scope": "declared"}),
    caso("declarar stack-up", "set_stackup", {"name": "asiento", "eslabones": [
        {"nombre": "eje", "nominal_mm": 35, "sentido": 1, "tol": {"fit": "h7"}}],
        "requisito": {"min_mm": 0}}),
    caso("notas", "get_agent_notes"),
    caso("añadir nota", "add_agent_note", {"text": "decisión golden"}),
    caso("revisiones", "list_revisions"),
    caso("restaurar revisión", "restore_revision", {"revision_id": 7}),
    caso("topología", "get_topology", {"feature_id": "c1"}),
    caso("topología filtrada", "get_topology", {"feature_id": "c1", "only": "caras", "min_mm": 2}),
    caso("requisitos", "get_requirements"),
    caso("guardar requisitos", "set_requirements", {"fields": {"carga_kg": 15}}),
    caso("auto-grupo", "auto_group"),
    caso("auto-grupo en seco", "auto_group", {"dry_run": True}),
    caso("grupos", "get_groups"),
    caso("masa", "get_mass_properties"),
    caso("masa de ids", "get_mass_properties", {"ids": ["c1", "c3"]}),
    caso("medir", "measure", {"a": "c1", "b": "c3"}),
    caso("medir caras", "measure", {"a": "c1", "b": "c3", "face_a": {"mode": "cara", "face": "tope"},
                                    "face_b": {"mode": "cara", "face": "base"}}),
    caso("cerca de punto", "near", {"point": [0, 0, 0]}),
    caso("cerca de pieza", "near", {"feature": "c1", "radius": 0, "limit": 3}),
    caso("cerca de caja", "near", {"box": [[0, 0, 0], [10, 10, 10]]}),
    caso("cerca sin nada", "near"),
    caso("verificar", "verify", {"checks": [{"tipo": "existe", "id": "c1"}]}),
    caso("señalar", "pick_point", {"u": 0.5, "v": 0.25}),
    caso("señalar completo", "pick_point", {
        "u": 0.1, "v": 0.9, "view": "frente", "fit_ids": ["c1"], "zoom": 1.5, "azimuth": 10,
        "elevation": 5, "isolate": ["c1"], "section": "y", "roll": 2, "pan": [0.5, 0.5]}),
    caso("lista de corte", "cut_list"),
    caso("nesting", "nesting", {"mode": "1d", "stock_w": 6000, "material": "acero"}),
    caso("juego de planos", "drawing_set", {"path": "juego.pdf", "template": "weldment",
                                            "shaded": True}),
    caso("memoria", "calc_report", {"path": "memoria.pdf", "carga_kg": 15,
                                    "largo_paquete_mm": 400}),
    caso("cotización", "quotation", {"path": "cot.pdf", "currency": "PEN", "fx": 3.7}),
    caso("manual", "assembly_manual", {"path": "manual.pdf", "isolate": ["Estructura"],
                                       "title": "Bastidor"}),
    caso("plano a archivo", "drawing", {"spec": {"sheet": "A3"}, "path": "plano.pdf"}),
    caso("plano svg", "drawing", {"spec": {"format": "svg"}}),
    caso("plano sin path", "drawing", {"spec": {"format": "pdf"}}),
    caso("visibilidad", "set_visibility", {"feature_id": "c1", "visible": False}),
    caso("visibilidad lote", "set_visibility_bulk", {"feature_ids": ["c1", "c3"],
                                                     "visible": True}),
    caso("expresión", "resolve_expression", {"expression": "=L/2"}),
    caso("gramática", "get_expression_grammar"),
    caso("ajuste", "get_fit", {"nominal_mm": 35, "hole": "H7", "shaft": "k6"}),
    caso("ajuste solo eje", "get_fit", {"nominal_mm": 35, "shaft": "h7"}),
    caso("fea pieza", "fea_static", {"feature_id": "c1", "fixed": {"mode": "cara", "face": "base"},
                                     "loads": [{"selector": {"mode": "cara", "face": "tope"},
                                                "force_n": [0, 0, -100]}],
                                     "material": "acero", "mesh_size_mm": 5,
                                     "fringe_path": "fringe.png"}),
    caso("fea ensamblaje", "fea_assembly", {"group": "Bastidor", "carga_kg": 15,
                                            "fringe_path": "fea.png", "nota": "golden"}),
    caso("fea ensamblaje por ids", "fea_assembly", {"ids": ["c1"], "name": "Sub",
                                                    "fixed_pieces": ["c1"], "yield_mpa": 250,
                                                    "mesh_size_mm": 40}),
]
