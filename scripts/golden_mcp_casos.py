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


def escena(afectados=(), deshechos=(), **extra) -> dict:
    """Payload de escena (lo que devuelven las mutaciones vía `_state_or_error`). `deshechos` =
    la pila de rehacer, la etiqueta más próxima primero (tras un deshacer no está vacía)."""
    return {
        "document": {
            "name": "golden", "configurations": ["4m", "3.2m"], "can_undo": True,
            "can_redo": bool(deshechos),
            "undo_labels": ["Mover «Guarda tambor motriz»", "Caja «Soporte motor»"],
            "redo_labels": list(deshechos),
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
# run_command, edit_command y set_variable también encolan (sandbox-caliente D8): su job
# devuelve la respuesta síncrona de siempre, así que la salida de la tool no cambia.
#: `remove?detail=diff` (cirugia-liviana D1/D2): sin escena; el cliente lo pasa tal cual.
BORRADO = {
    "comandos_borrados": ["c1", "c7"],
    "piezas_borradas": [{"id": "c1", "nombre": "Base"}],
    "uniones_borradas": [{"nombre": "f1", "tipo": "fijador"}],
    "total_solidos": 2,
    "affected_command_ids": ["c9"],
    "dependientes": [{"id": "c7", "tipo": "fasten", "nombre": "f1"}],
    "grupos_editados": [{"grupo": "Estructura", "quitados": ["c1"]}],
}
#: La co-simulación (V8.3 D13): el compacto de `POST /api/cosim/run` (sin trazas: van aparte).
COSIM = {
    "simulacion": "s1a2b3c4", "escenario": "seta", "veredicto": "falla", "n_fallidas": 1,
    "aserciones": [
        {"asercion": "-M1.rpm >= 1700 dentro_de 2 s desde pulsar -S1", "pasa": True,
         "senal": "-M1.rpm", "t": 1.24, "detalle": "se cumple a los 0.94 s (t = 1.24 s)"},
        {"asercion": "-K1.%QX0.0 == false dentro_de 0.1 s desde presionar -S0", "pasa": False,
         "senal": "-K1.%QX0.0", "detalle": "no se cumple en [2.2, 2.3] s: termina en true"}],
    "resumen": {"duracion_s": 3.0, "intercambios": 1500, "factor_tiempo_real": 1.4,
                "huella": "9f2c", "senales": {"discretas": 60, "analogicas": 29}},
    "eventos": [{"t": 0.3, "programado_s": 0.3, "accion": "pulsar", "dispositivo": "-S1"}],
    "n_eventos": 1, "plc": {"-K1": {"estado": "RUN", "fallas": [], "scans": 300}},
    "avisos": [], "hipotesis": ["la entrada del variador a fp 1"],
    "aviso": "simulación a nivel sistema; no reemplaza la puesta en marcha real", "guardado": True,
    "estado": "falla",
}
PLC_OK = {"compila": True, "programas": ["Main"], "tags": [
    {"variable": "marcha", "direccion": "%IX0.2", "borne": "I0.2", "tipo": "BOOL",
     "sentido": "entrada"}]}
#: Un entregable por job (manual-rapido F2): el PDF se baja de `archivo`.
def _archivo(clave: str, nombre: str) -> dict:
    return {"archivo": f"/api/archivos/{clave}", "bytes": len(PDF), "tipo": "application/pdf",
            "nombre": nombre}


SVG = b"<svg>golden</svg>"
JOBS_SUELTOS = {"jmc": _archivo("k1", "golden-memoria-calculo.pdf"),
                "jma": _archivo("k2", "golden-ensamblaje.pdf"),
                "jjp": _archivo("k3", "golden-planos.pdf"),
                "jpp": _archivo("k4", "golden.pdf"),
                "jps": {"archivo": "/api/archivos/k5", "bytes": len(SVG),
                        "tipo": "image/svg+xml", "nombre": "drawing"},
                "jc": MUTA["json"], "jv": escena(["v1"]), "jr": BORRADO, "jrf": escena(),
                "jcs": COSIM, "jpl": {**COSIM, **PLC_OK, "escenario": None, "guardado": None,
                                      "trazas": {"discretas": {"-K1.%QX0.0": {
                                          "cambios": [[0.0, False], [0.31, True]], "total": 2,
                                          "offset": 0, "truncado": False}}}}}


def _plc_test(req):
    return _encolado("jpl") if json.loads(req.content).get("escenario") else J(PLC_OK)


ESCENARIOS = {"escenarios": [
    {"nombre": "marcha", "estado": "pasa", "duracion_s": 3.0, "n_aserciones": 2,
     "corrido": "2026-10-20T10:00:00"},
    {"nombre": "seta", "estado": "vencido", "motivo": "la máquina cambió desde que se corrió",
     "ultimo": "pasa", "duracion_s": 3.0, "n_aserciones": 3}], "firma_documento": "abc123"}


def _encolado(job_id: str) -> dict:
    return J({"job_id": job_id, "estado": "encolado"}, 202)


def _remove(req):
    return _encolado("jr" if req.url.params.get("detail") == "diff" else "jrf")


#: `undo|redo?detail=diff` (mcp-sin-friccion D1): el diff del paso, sin escena; pasa tal cual.
PASO = {"deshecho": "Variable «L»: 2000 → 3200", "comandos_editados": ["v1"],
        "variables": [{"name": "L", "expression": "2000", "value": 2000.0}],
        "piezas_borradas": [{"id": "c9", "nombre": "Tapa"}], "piezas_borradas_omitidas": 3,
        "total_solidos": 3, "puede_deshacer": True, "puede_rehacer": True,
        "affected_command_ids": []}


def _paso(req):
    if req.url.params.get("detail") == "diff":
        return J(PASO)
    return J(escena(deshechos=["Variable «L»: 2000 → 3200"]))


#: `connectivity` (D1/D2): la lista, o el resumen por patrón si lo pide (`resumen=si`/`auto`).
RESUMEN_UNIONES = {"n_fijadores": 57, "n_anclajes": 1, "por_tipo": {"perno": 38, "contacto": 19},
                   "resumen": [{"kind": "perno", "patron": "r*_eje_larguero_my", "n": 19,
                                "ejemplo": {"nombre": "r1_eje_larguero_my", "a": "c57_1",
                                            "b": "c9", "piezas": ["Eje", "Larguero (-Y)"]}}],
                   "anclajes": [{"nombre": "g1", "pieza": "c1"}],
                   "seguir": "la lista con nombres: get_connections(…, resumen=false)"}


def _conexiones(req):
    if req.url.params.get("resumen") in ("si", "auto") and not req.url.params.get("ids"):
        return J(RESUMEN_UNIONES)
    return J({"grounds": [{"name": "g1"}], "fasteners": []})


def _checks(req):
    out = {"interferencias": {"pares": []}, "ingenieria": [{"ok": True}],
           "estructura": {"reglas": []}, "otro": "no se muestra"}
    if json.loads(req.content).get("resumen"):  # el modo corto suma el conteo por estado
        out["conteo"] = {"ingenieria": {"ok": 1}, "estructura": {}}
    return J(out)


def _escena_grande(n: int = 41) -> dict:
    """Un lote que creó más de 40 sólidos (una plantilla): el brief resume `por_comando`."""
    out = escena(["c7"])
    out["features"] = out["features"] + [
        _feat(f"c7_r{k}", f"Rodillo {k}", f"c7_r{k}", group="Rodillos") for k in range(n)]
    out["total_features"] = len(out["features"])
    return out


def _job(req):
    jid = req.url.path.rsplit("/", 1)[-1]
    if jid in JOBS_SUELTOS:
        return J({"id": jid, "estado": "ok", "resultado": JOBS_SUELTOS[jid]})
    return JOB_OK


def _job_error(error: str) -> dict:
    return {("GET", r"/api/jobs/[^/]+"): J({"estado": "error", "http_status": 400, "error": error})}


def _preview(req):
    return J({"fantasmas": [{"name": "Nueva", "bbox": [0, 1]}], "colisiones_nuevas": []}) \
        if json.loads(req.content).get("data") else B(PNG, "image/png")


def _drawing(req):  # el plano por intención también va por job (manual-rapido F2b)
    return _encolado("jps" if json.loads(req.content).get("format") == "svg" else "jpp")


def _archivo_bajado(req):
    if req.url.path.endswith("/k5"):
        return B(SVG, "image/svg+xml")
    return B(PDF, "application/pdf")


def _auto_group(req):
    if json.loads(req.content).get("dry_run"):
        return J({"proposal": [{"name": "Estructura", "members": ["c1"]}]})
    return J({**escena(["c1"]), "proposal": [{"name": "Estructura"}], "created": ["g1"]})


#: `declare` en modo propuesta (uniones-en-lote D3): acciones con `a_revisar` y resumen por raíz.
PROPUESTA = {
    "aplicar": False, "n_grounds": 1, "n_fasteners": 2, "n_a_revisar": 1,
    "acciones": [
        {"type": "ground", "params": {"name": "auto_g_1", "feature": "c1", "nota": "base"}},
        {"type": "fasten", "params": {"name": "auto_f_1", "a": "c1", "b": "c57_1",
                                      "kind": "soldadura", "nota": "'Base' ↔ 'Eje'"}},
        {"type": "fasten", "params": {"name": "auto_f_2", "a": "c57_1", "b": "c9",
                                      "kind": "contacto", "nota": "a revisar: …"},
         "a_revisar": True, "motivo": "'Eje' ↔ 'Piñón'; no se suelda: 'Piñón' es transmision"},
    ],
    "resumen": [{"kind": "soldadura", "a": "c1", "b": "c57", "n": 1,
                 "ejemplo": {"a": "c1", "b": "c57_1", "nombres": ["Base", "Eje"]}}],
}


def _declare(req):
    if req.content and json.loads(req.content).get("aplicar") is False:
        return J(PROPUESTA)
    return J({**escena(["c1"]), "a_revisar": ["auto_f_2"]})


def _scene(req):
    if req.url.query:  # brief filtrado/paginado del servidor
        return J({"total_solidos": 3, "total_filtrado": 1, "truncado": False,
                  "solidos": [{"id": "c1", "nombre": "Base"}]})
    return J(escena())


#: Forma de `POST /api/physics/dynamics` (V8.2 D9): lo que el agente lee y lo que es para animar
#: (`piezas`, `productos`, trazas de `juntas`, `muestras` del sensor), que el cliente recorta.
DINAMICA = {
    "piezas": [{"name": "b_c1_eje_motriz", "id": "c1_tambor_motriz"}],
    "cuerpos": [{"name": "b_c1_eje_motriz", "junta": "c1_eje_motriz", "tipo": "continua",
                 "piezas": ["c1_tambor_motriz"], "masa_kg": 8.0}],
    "productos": [{"name": "p_caja", "w": 150, "d": 120, "h": 100}],
    "juntas": {"c1_eje_motriz": {"t": [0, 1], "q": [0, 90], "qd": [0, 47.7], "par": [0, 1.2]}},
    "sensores": {"foto": {"tipo": "rayo", "flancos": [{"t": 0.5, "tipo": "sube",
                                                         "objeto": "p_caja"}],
                          "cuentas": 1, "muestras": [[0, 0], [1, 1]]}},
    "motores": [{"junta": "c1_eje_motriz", "modo": "velocidad", "consigna": -4.99}],
    "resumen": {"duracion_s": 1.0, "factor_tiempo_real": 6.2,
                "bandas": [{"pieza": "c1_banda", "avanza_hacia": "+X", "v_final_m_s": 0.25}],
                "productos": {"p_caja": {"velocidad_final_mm_s": [250.0, 0.0, 0.0],
                                         "cayo": False}},
                "productos_caidos": [], "juntas_en_limite": []},
    "avisos": ["La banda 'c1_banda' avanza hacia −X con giro positivo de 'c1_eje_motriz'"],
}

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
    ("POST", r"/api/commands", _encolado("jc")),
    ("POST|PATCH", r"/api/commands/batch", ENCOLADO),
    ("GET", r"/api/jobs/[^/]+", _job),
    ("PUT", r"/api/commands/[^/]+", _encolado("jc")),
    ("POST", r"/api/commands/remove", _remove),
    ("POST", r"/api/(undo|redo)", _paso),
    ("POST", r"/api/variables", _encolado("jv")),
    ("POST", r"/api/checks", J({"interferencias": {"pares": []}, "ingenieria": [{"ok": True}],
                                "estructura": {"reglas": []}, "otro": "no se muestra"})),
    ("GET", r"/api/render\.png", B(PNG, "image/png")),
    ("POST", r"/api/commands/preview", _preview),
    ("GET", r"/api/projects", J([{"id": 38, "name": "faja"}])),
    ("POST", r"/api/projects/\d+/open", J({**escena(), "briefing": {"grupos": 6}})),
    ("POST", r"/api/projects", J(escena())),
    ("POST", r"/api/revisions", J({"id": 7, "note": "golden"})),
    ("POST", r"/api/configurations", J(escena())),
    ("PUT", r"/api/configurations/[^/]+", J(escena())),
    ("POST", r"/api/configurations/[^/]+/apply", J(escena(["v1"], cambios=[
        {"variable": "L", "antes": "2000", "despues": "3200"}]))),
    ("GET", r"/api/export/(step|stl)", B(b"ISO-10303-21; golden")),
    ("GET", r"/api/sheetmetal/[^/]+/flat\.dxf", B(b"0\nSECTION golden")),
    ("POST", r"/api/physics/drop", J({"resting": [[0, 0, 10]], "settled": True,
                                      "frames": [1, 2, 3]})),
    ("POST", r"/api/physics/drop\.gif", B(GIF, "image/gif")),
    ("POST", r"/api/physics/dynamics", J(DINAMICA)),
    ("POST", r"/api/physics/dynamics\.gif", B(GIF, "image/gif")),
    ("GET", r"/api/document", J(escena()["document"])),
    ("GET", r"/api/commands", J([{"id": "c1", "type": "create_box", "resumen": "Base"}])),
    ("POST", r"/api/sketch/solve", J({"ok": True, "dof": 0})),
    ("POST", r"/api/script/test", J({"ok": True, "volumen_mm3": 1.0})),
    ("GET", r"/api/mates", J([{"name": "m1"}])),
    ("GET", r"/api/assembly/dof", J({"solidos": []})),
    ("POST", r"/api/assembly/(soundness|autodetect)", J({"flotantes": [], "aisladas": []})),
    ("POST", r"/api/assembly/declare", _declare),
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
    ("GET", r"/api/quote\.pdf", B(PDF, "application/pdf")),
    ("GET", r"/api/drawingset\.pdf", _encolado("jjp")),
    ("GET", r"/api/calc-report\.pdf", _encolado("jmc")),
    ("GET", r"/api/assembly-manual\.pdf", _encolado("jma")),
    ("GET", r"/api/archivos/[^/]+", _archivo_bajado),
    ("POST", r"/api/drawing/spec", _drawing),
    ("GET", r"/api/resolve-expression", J({"ok": True, "value": 2000.0})),
    ("GET", r"/api/expression-grammar", J({"funciones": ["sqrt"]})),
    ("GET", r"/api/fits", J({"juego_min_um": 0})),
    ("POST", r"/api/fea/static", J({"fs": 3.2, "sigma_vm_max_mpa": 75.0})),
    ("GET", r"/api/fea/[^/]+/fringe\.png", B(PNG, "image/png")),
    ("POST", r"/api/fea/assembly", J({"grupo": "Bastidor", "fs_gobernante": 93.5})),
    ("GET", r"/api/fea/group/[^/]+/fringe\.png", B(PNG, "image/png")),
    ("GET", r"/api/electrico/circuito", J({
        "dispositivos": [{"designacion": "-Q1", "ref": "GM-2.5-4A", "funcion": "Q",
                          "bornes": [{"id": "1", "rol": "potencia", "red": "N1"}]}],
        "redes": [{"id": "N1", "puntos": ["-G1:L1", "-Q1:1"], "tension": "-G1:L1 · 220 VAC"}],
        "conductores": [{"comando": "c5", "puntos": ["-G1:L1", "-Q1:1"], "color": "BK"}],
        "cables": [], "resumen": {"n_dispositivos": 2, "n_conductores": 1}})),
    ("GET", r"/api/electrico/check", J({"estado": "error", "errores": 1, "avisos": 0, "reglas": [
        {"regla": "protección del motor", "estado": "error", "detalle": "-M1 sin guardamotor"}]})),
    ("POST", r"/api/cosim/run", _encolado("jcs")),
    ("POST", r"/api/cosim/plc/test", _plc_test),
    ("GET", r"/api/cosim/simulaciones", J({"simulaciones": [
        {"id": "s1a2b3c4", "proyecto": 38, "escenario": "seta", "veredicto": "falla",
         "creado": "10:00:00", "prueba_plc": False}]})),
    ("GET", r"/api/cosim/simulaciones/[^/]+", J({
        "simulacion": "s1a2b3c4", "ventana_s": [1.0, 2.0],
        "discretas": {}, "analogicas": {"t": [1.0, 1.02], "senales": {"-M1.rpm": [1700.1, 1712.4]},
                                        "total": 51, "offset": 10, "truncado": False}})),
    ("GET", r"/api/escenarios", J(ESCENARIOS)),
    ("PUT", r"/api/escenarios/[^/]+", J({"nombre": "seta", "estado": "vencido", "n_aserciones": 1,
                                         "aserciones": ["-M1.par_Nm == 0 dentro_de 0.5 s desde "
                                                        "presionar -S0"], "avisos": []})),
    ("DELETE", r"/api/escenarios/[^/]+", J({"borrado": "viejo", **ESCENARIOS})),
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
    caso("comando → recibo", "run_command", {"type": "create_box", "params": {}}, espera=0.0),
    caso("comando → job en error", "run_command",
         {"type": "fillet", "params": {"feature": "c9", "radius": 2}},
         rutas=_job_error("Error al regenerar c4 (fillet): No existe el sólido 'c9' en la escena")),
    caso("lote con contrato", "run_batch", {"actions": [_ESC, _ESC], "detail": "summary",
                                           "expect": [{"tipo": "existe", "id": "$1"}]}),
    caso("lote → recibo", "run_batch", {"actions": [_ESC]}, espera=0.0),
    caso("lote de una plantilla → por comando", "run_batch", {"actions": [_ESC], "detail": "summary"},
         rutas={("GET", r"/api/jobs/[^/]+"): J({"estado": "ok", "resultado": _escena_grande()})}),
    caso("lote → job en error", "run_batch", {"actions": [_ESC]}, rutas={
        ("GET", r"/api/jobs/[^/]+"): J({"estado": "error", "http_status": 400,
                                        "error": "Contrato incumplido: medido 150 > 10"})}),
    caso("lote → job corriendo y luego ok", "run_batch", {"actions": [_ESC]}, rutas={
        ("GET", r"/api/jobs/[^/]+"): [J({"estado": "corriendo"}), JOB_OK]}),
    caso("editar", "edit_command", {"command_id": "c1", "params": {"width": 80}}),
    caso("editar replace", "edit_command", {"command_id": "c1", "params": {}, "merge": False,
                                            "detail": "summary"}),
    caso("editar → recibo", "edit_command", {"command_id": "c1", "params": {"width": 80}},
         espera=0.0),
    caso("editar → job en error", "edit_command", {"command_id": "c1", "params": {"anchura": 3}},
         rutas=_job_error("Parámetro desconocido en create_box (no se aplicó nada):\n- «anchura» "
                          "no existe. Válidos en ese nivel: name, width, depth, height, position, "
                          "rotation.")),
    caso("editar lote", "edit_batch", {"edits": [{"command_id": "c1", "params": {"width": 1}}],
                                       "expect": [{"tipo": "existe", "id": "c1"}]}),
    caso("editar lote replace → recibo", "edit_batch", {"edits": [], "merge": False}, espera=0.0),
    caso("borrar comandos", "remove_commands", {"ids": ["c1"], "con_dependientes": True}),
    caso("borrar comandos full", "remove_commands", {"ids": ["c1"], "detail": "full"}),
    caso("borrar → recibo", "remove_commands", {"ids": ["c1"]}, espera=0.0),
    caso("borrar → job en error", "remove_commands", {"ids": ["c1"]}, rutas=_job_error(
        "El fijador 'f1' referencia el sólido 'c1', que ya no existe: elimina primero el fijador")),
    caso("job ok", "get_job", {"job_id": "j1", "detail": "full", "wait_s": 5}),
    caso("job de un borrado", "get_job", {"job_id": "jr"}),
    caso("job corriendo", "get_job", {"job_id": "j1"},
         rutas={("GET", r"/api/jobs/[^/]+"): J({"estado": "encolado"})}),
    caso("job en error", "get_job", {"job_id": "j1"},
         rutas={("GET", r"/api/jobs/[^/]+"): J({"estado": "error", "error": "boom"})}),
    caso("job 404", "get_job", {"job_id": "zz"}, rutas={("GET", r"/api/jobs/[^/]+"): JOB_404}),
    caso("deshacer", "undo"),
    caso("deshacer con la escena", "undo", {"detail": "full"}),
    caso("variable", "set_variable", {"name": "L", "expression": "2500"}),
    caso("variable → recibo", "set_variable", {"name": "L", "expression": "2500"}, espera=0.0),
    caso("variable → job en error", "set_variable", {"name": "L", "expression": "=L*"},
         rutas=_job_error("Variable 'L': Expresión inválida 'L*': invalid syntax")),
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
    caso("guardar configuración con valores", "save_configuration",
         {"name": "3.2m", "values": {"L": "3200"}}),
    caso("aplicar configuración", "apply_configuration", {"name": "3.2m"}),
    caso("aplicar configuración con aviso", "apply_configuration", {"name": "vieja"}, rutas={
        ("POST", r"/api/configurations/[^/]+/apply"): J(escena(["v1"], cambios=[],
            aviso="Se ignoraron n: ya no son variables del proyecto (golden)"))}),
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
    caso("rehacer con la escena", "redo", {"detail": "full"}),
    caso("mates", "get_mates"),
    caso("dof", "get_dof"),
    caso("sujeción", "check_assembly"),
    caso("sujeción con autodetect", "check_assembly", {"with_autodetect": True}),
    caso("autodetección", "autodetect_connections"),
    caso("proponer estructura", "declare_structure"),
    caso("declarar estructura", "declare_structure", {"aplicar": True}),
    caso("proponer estructura sin la lista", "declare_structure", rutas={
        ("POST", r"/api/assembly/declare"): J({**PROPUESTA, "acciones": [
            PROPUESTA["acciones"][1]] * 61})}),
    caso("conexiones", "get_connections"),
    caso("borrar conexión", "delete_connection", {"name": "f1"}),
    caso("borrar conexiones lote", "delete_connection", {"names": ["f1", "g1"]}),
    caso("borrar conexión sin nombre", "delete_connection"),
    caso("puerta de entrega", "delivery_check", {"con_gravedad": True}),
    caso("gravedad", "gravity_test"),
    caso("gravedad con gif", "gravity_test", {"with_autodetect": True, "exclude": ["c3"],
                                              "seconds": 1.5, "path": "gravedad.gif"}),
    caso("simulación", "simulate", {
        "motores": [{"junta": "c1_eje_motriz", "modo": "velocidad", "v_superficie_m_s": 0.25,
                     "direccion_transporte": [1, 0, 0]}],
        "productos": [{"nombre": "caja", "dims_mm": [150, 120, 100], "posicion_mm": [0, 0, 851]}],
        "sensores": [{"nombre": "foto", "origen": [900, -400, 850], "direccion": [0, 1, 0]}],
        "duracion_s": 1.0}),
    caso("simulación con gif y opciones", "simulate", {
        "motores": [{"junta": "j1", "modo": "par", "valor": 2.0}], "con_autodeteccion": True,
        "juntas": {"j1": {"amortiguamiento": 0.1}}, "opciones": {"fps": 10, "nstep": 1},
        "path": "marcha.gif"}),
    caso("simulación nada que simular", "simulate", {"path": "nada.gif"}, rutas={
        ("POST", r"/api/physics/dynamics"): J({"frames": [], "resumen": {"duracion_s": 0.0},
                                               "avisos": [], "mensaje": "Nada que simular"})}),
    caso("simulación opción repetida → error", "simulate", {"opciones": {"duracion_s": 5}}),
    caso("simulación 400", "simulate", {"motores": [{"junta": "j1", "modo": "giro"}]}, rutas={
        ("POST", r"/api/physics/dynamics"): J({"detail": "motores[0]: 'modo' debe ser "
                                                         "'velocidad' o 'par' (vino 'giro')"}, 400)}),
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
    caso("juego de planos → recibo", "drawing_set", {"path": "juego2.pdf", "shaded": True},
         espera=0.0),
    caso("job del juego: al path del recibo", "get_job", {"job_id": "jjp"}),
    caso("memoria", "calc_report", {"path": "memoria.pdf", "carga_kg": 15,
                                    "largo_paquete_mm": 400}),
    caso("cotización", "quotation", {"path": "cot.pdf", "currency": "PEN", "fx": 3.7}),
    caso("manual", "assembly_manual", {"path": "manual.pdf", "isolate": ["Estructura"],
                                       "title": "Bastidor"}),
    caso("job de un manual sin path", "get_job", {"job_id": "jma"}),
    caso("memoria → recibo", "calc_report", {"path": "memoria2.pdf"}, espera=0.0),
    caso("job de la memoria: al path del recibo", "get_job", {"job_id": "jmc"}),
    caso("job de un manual con path", "get_job", {"job_id": "jma", "path": "manual2.pdf"}),
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
    caso("circuito", "get_circuit"),
    caso("circuito de un dispositivo", "get_circuit", {"designacion": "-Q1"}),
    caso("chequeo eléctrico", "electrical_check"),
    # V8.3 D13: la prueba virtual
    caso("simulación con escenario", "simulate", {"escenario": "seta"}),
    caso("simulación con escenario inline → recibo", "simulate", {"escenario": {
        "duracion_s": 2, "aserciones": ["-M1.rpm > 100 al_final"]}}, espera=0.0),
    caso("simulación con escenario y motores → error", "simulate", {
        "escenario": "seta", "motores": [{"junta": "j1", "modo": "par", "valor": 1}]}),
    caso("simulación con escenario → job en error", "simulate", {"escenario": "seta"},
         rutas=_job_error("el motor -M1 no está acoplado a una junta")),
    caso("probar plc", "test_plc", {"fuente": "PROGRAM Main\nEND_PROGRAM", "plc": "-K1"}),
    caso("probar plc con escenario", "test_plc", {
        "fuente": "PROGRAM Main\nEND_PROGRAM", "plc": "-K1", "escenario": "seta", "ciclo_ms": 5,
        "ciclos": {"Main": 5}, "senales": ["-K1.%QX0.0"]}),
    caso("probar plc que no compila", "test_plc", {"fuente": "PROGRAM Main\nx := ;"}, rutas={
        ("POST", r"/api/cosim/plc/test"): J({"compila": False, "errores": [
            {"linea": 2, "columna": 6, "mensaje": "se esperaba una expresión"}],
            "error": "línea 2, columna 6: se esperaba una expresión"})}),
    caso("simulaciones", "get_simulation"),
    caso("simulación por partes", "get_simulation", {
        "simulacion": "s1a2b3c4", "parte": "trazas", "senales": ["-M1.rpm", "-K1.*"],
        "desde_s": 1.0, "hasta_s": 2.0, "limite": 50, "offset": 10}),
    caso("simulación que no está", "get_simulation", {"simulacion": "s9"}, rutas={
        ("GET", r"/api/cosim/simulaciones/[^/]+"): J({"detail": "No hay simulación «s9» en "
                                                                "memoria"}, 404)}),
    caso("escenarios", "get_scenarios"),
    caso("escenario uno", "get_scenarios", {"nombre": "seta"}),
    caso("declarar escenario", "set_scenario", {"nombre": "seta", "escenario": {
        "duracion_s": 3, "acciones": [{"t": 2.2, "accion": "presionar", "dispositivo": "-S0"}],
        "acoples": {"motores": {"-M1": {"junta": "c1_eje_motriz"}}},
        "aserciones": ["-M1.par_Nm == 0 dentro_de 0,5 s desde presionar -S0"]}}),
    caso("borrar escenario", "set_scenario", {"nombre": "viejo"}),
]
