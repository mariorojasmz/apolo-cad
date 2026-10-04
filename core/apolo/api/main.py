"""API de Genix Apolo CAD.

La UI y el agente IA son dos clientes de esta misma API: toda operación de
modelado entra por /api/commands (o /api/commands/batch para los lotes que
propone el agente).
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apolo import paths as _paths
from apolo.doc import DocumentError
from apolo.kernel import bbox_payload
from apolo.library import (
    bom_from_scene,
    bom_to_csv,
    catalog_payload,
    conveyor_engineering_check,
    interference_report,
)
from apolo.services.drawing_maps import (  # D4: nombres viejos por IDENTIDAD (tests)
    feature_fit_maps as _feature_fit_maps,  # noqa: F401
    hole_fit_map as _hole_fit_map,  # noqa: F401
    hole_thread_map as _hole_thread_map,  # noqa: F401
    piece_datum_frame as _piece_datum_frame,  # noqa: F401
    piece_datum_sides as _piece_datum_sides,  # noqa: F401
    piece_dim_tols as _piece_dim_tols,  # noqa: F401
    piece_pos_tols as _piece_pos_tols,  # noqa: F401
    scene_fit_map as _scene_fit_map,  # noqa: F401
    thread_schedule as _thread_schedule,  # noqa: F401
)
from apolo.services.assertions import contract_verify, verify_checks
from apolo.services.delivery_inputs import delivery_inputs
from apolo.services.engineering_rules import (
    conveyor_params_from_doc,
    inherit_inclination,
    requirement_inputs,
    structure_rules,
)
from apolo.services.fea_rules import fea_rules
from apolo.services.installation_data import installation_data as _installation_data  # noqa: F401
from apolo.services.lookup import suggest_ids
from apolo.services.stackup_eval import evaluate_stackups, stackup_rules
from apolo.state import STATE_LOCK

from .autosave import (  # D4: por IDENTIDAD (los endpoints y los tests usan los mismos objetos)
    _autosave,
    _autosave_sched,  # noqa: F401
    _flush_autosave,
    _flush_lock,  # noqa: F401 — sólo los tests (orden de locks)
    _project_switch,  # noqa: F401
)
from .common import (
    JOBS,
    _drawing_meta,
    _expand_ids,
    _materialize_edit,
    _materialize_insert_project,
    _not_found,
    _remove_owner_command,
    _state_or_error,
    _sync_or_job,
)
from .errorlog import log_error, session_marker
from .fea_runs import (  # D4: por IDENTIDAD (los tests espían la guardia y el campo en memoria)
    _LAST_FEA_FIELD,  # noqa: F401
    FeaAssemblyIn,
    FeaStaticIn,
    _fea_assembly_run,
    _fea_owner,  # noqa: F401
    _fea_static_run,
    _last_fea_field,
    _persist_fea_if_same_project,  # noqa: F401
)
from .jobs import JOB_UNKNOWN
from .routers import core, drawings, features, motion, projects, render
from .routers.projects import delete_project  # noqa: F401 — D4: un test la llama directo
from .scene import (  # D4: por IDENTIDAD (cachés mutadas en sitio por los tests)
    _DEF_MESH_CACHE,  # noqa: F401
    _GEOM_REVS,  # noqa: F401
    _cached_render,  # noqa: F401
    _definition_mesh,  # noqa: F401
    _feature_colors,
    _open_briefing,  # noqa: F401
    scene_payload,  # noqa: F401
)
from .session import S, _MainModule, initialize_store
from .sims import DropIn, StabilityIn, _drop, _stability
from .ws import WS

app = FastAPI(title="Genix Apolo CAD", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Estado de sesión (D3 del plan partir-api-main): vive en `session.S` y el código lee y swapea
# `S.<campo>`. `api.DOC`/`STORE`/`PROJECT_ID`/`AUTOSAVE_ERROR`/`STARTUP_ERROR` quedan como
# alias de `S` para los tests (leer, asignar, `monkeypatch`): los da la clase del módulo.
sys.modules[__name__].__class__ = _MainModule


@app.on_event("startup")
async def _capture_loop() -> None:
    WS.loop = asyncio.get_running_loop()
    session_marker("Inicio de sesión del servidor")
    initialize_store(_paths.db_path())


@app.on_event("shutdown")
async def _flush_on_shutdown() -> None:
    """Al apagar, vuelca cualquier autosave pendiente (V6.2d): la ventana de debounce no
    puede tragarse un cambio si el server se cierra dentro de ella."""
    _flush_autosave()


# -------------------------------------------------------- registro de errores
@app.middleware("http")
async def _catch_unhandled(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:  # error no controlado → 500 + log con traceback
        log_error(
            "backend.unhandled",
            repr(exc),
            path=request.url.path,
            method=request.method,
            traceback=traceback.format_exc(),
        )
        return JSONResponse(status_code=500, content={"detail": f"Error interno: {exc}"})


@app.exception_handler(HTTPException)
async def _log_http_errors(request: Request, exc: HTTPException):
    if exc.status_code >= 400:
        log_error(
            "backend.http",
            str(exc.detail),
            path=request.url.path,
            method=request.method,
            status=exc.status_code,
        )
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


class ClientErrorIn(BaseModel):
    source: str = "frontend"
    message: str
    stack: str | None = None
    context: dict = {}


@app.post("/api/client-errors")
def report_client_error(body: ClientErrorIn) -> dict:
    context = dict(body.context)
    if body.stack:
        context.setdefault("stack", body.stack)
    log_error(f"frontend.{body.source}", body.message, **context)
    return {"ok": True}


def _suggest_ids(missing, limit: int = 3) -> list[str]:
    """Envoltorio de compatibilidad (D4 del plan partir-api-main): «¿quisiste decir…?» sobre
    el documento ACTIVO (`services.lookup.suggest_ids`). Llamar bajo STATE_LOCK."""
    return suggest_ids(S.doc, missing, limit)


# ------------------------------------------------------------------ endpoints
class CommandIn(BaseModel):
    type: str
    params: dict = {}


@app.post("/api/commands")
def post_command(cmd: CommandIn) -> dict:
    return _state_or_error(
        lambda: S.doc.execute(cmd.type, _materialize_insert_project(cmd.type, cmd.params))
    )


class BatchIn(BaseModel):
    actions: list[CommandIn]
    # CONTRATO opcional (V6.5b, frente A): aserciones estilo `verify` que deben cumplirse
    # tras el lote; si alguna falla, el lote se revierte por completo (doc intacto).
    expect: list[dict] = []


@app.post("/api/commands/batch")
def post_batch(batch: BatchIn, async_: bool = Query(False, alias="async")):
    from apolo.batch import execute_batch

    # OJO: _materialize_insert_project muta DOC.attachments → DEBE correr bajo
    # STATE_LOCK (dentro del lambda de _state_or_error), no antes.
    def _run():
        actions = [
            {"type": a.type, "params": _materialize_insert_project(a.type, a.params)}
            for a in batch.actions
        ]
        return execute_batch(S.doc, actions,
                             verify=contract_verify(S.doc, batch.expect, expand=_expand_ids))

    def _work() -> dict:
        payload = _state_or_error(_run)
        if batch.expect:  # el lote sobrevivió al contrato (si no, ContractError → 400)
            payload["contrato"] = {"n_aserciones": len(batch.expect), "ok": True}
        return payload

    return _sync_or_job("run_batch", _work, async_)


class EditOne(BaseModel):
    command_id: str
    params: dict = {}


class EditBatchIn(BaseModel):
    edits: list[EditOne]
    expect: list[dict] = []  # CONTRATO opcional (V6.5b): igual que en /api/commands/batch


@app.patch("/api/commands/batch")
def patch_batch(
    batch: EditBatchIn, merge: bool = False, async_: bool = Query(False, alias="async")
):
    # OJO: _materialize_edit lee DOC.commands → bajo STATE_LOCK (dentro del lambda).
    def _run():
        edits = [
            {
                "command_id": e.command_id,
                "params": _materialize_edit(e.command_id, e.params, merge),
            }
            for e in batch.edits
        ]
        return S.doc.edit_many(edits, merge=merge,
                               verify=contract_verify(S.doc, batch.expect, expand=_expand_ids))

    def _work() -> dict:
        payload = _state_or_error(_run)
        if batch.expect:
            payload["contrato"] = {"n_aserciones": len(batch.expect), "ok": True}
        return payload

    return _sync_or_job("edit_batch", _work, async_)


@app.get("/api/jobs")
def list_jobs() -> dict:
    """Los últimos jobs retenidos, sin `resultado` (payload grande). Telemetría."""
    return {"jobs": JOBS.briefs()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, wait_s: float = 0.0) -> dict:
    """Estado/resultado de un job (V6.5e). ``wait_s`` (0..30) = long-poll: responde en
    cuanto termina. El resultado queda CACHEADO → re-preguntar es siempre seguro."""
    job = JOBS.get(job_id, wait_s=wait_s)
    if job is None:
        raise HTTPException(
            status_code=404, detail=JOB_UNKNOWN.format(job_id=job_id, retention=JOBS.retention)
        )
    return job


class PreviewIn(BaseModel):
    actions: list[CommandIn] = []
    view: str = "iso"
    labels: bool = False
    section: str | None = None
    data: bool = False  # V6.5d: en vez del PNG, devuelve datos del fantasma (bbox/volumen + colisiones nuevas)


def _preview_new_feats(scene: dict, new_ids) -> list[str]:
    """Feature_ids de los sólidos NUEVOS del preview (incluye el prefijo sintético de
    insert_project: '{cmd}_{orig}')."""
    new = set(new_ids)
    return [
        fid for fid, f in scene.items()
        if f.command_id in new or any(f.command_id.startswith(a + "_") for a in new)
    ]


@app.post("/api/commands/preview")
def preview_commands(body: PreviewIn):
    """Ghost: aplica `actions` (formato batch) sobre una COPIA del documento SIN tocar el
    modelo real. `data=false` (default, compat) → PNG con los sólidos nuevos resaltados.
    `data=true` (V6.5d) → JSON `{fantasmas:[{name,bbox,volumen_mm3}], colisiones_nuevas:[...]}`:
    las colisiones SOLO de los fantasmas (contra la escena y entre sí, excluyendo hardware y
    parejas por diseño) → el agente prueba N colocaciones y compromete 1 sin generar escombro."""
    from types import SimpleNamespace

    from apolo.commands.registry import CommandError
    from apolo.kernel.render import render_scene_png
    from apolo.library.checks import hardware_ids, joint_pairs, same_command_pairs

    with STATE_LOCK:
        try:
            scene, new_ids = S.doc.preview(
                [
                    {"type": a.type, "params": _materialize_insert_project(a.type, a.params)}
                    for a in body.actions
                ]
            )
        except (CommandError, DocumentError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        new_feats = _preview_new_feats(scene, new_ids)
        if body.data:
            shim = SimpleNamespace(scene=scene)
            rep = interference_report(
                scene, focus=set(new_feats),
                exclude_pairs=joint_pairs(S.doc) | same_command_pairs(shim),
                exclude_ids=hardware_ids(shim),
            )
            fantasmas = [
                {"id": fid, "name": scene[fid].name,
                 "bbox": bbox_payload(scene[fid].shape),
                 "volumen_mm3": round(float(scene[fid].shape.volume), 1)}
                for fid in new_feats
            ]
            colisiones = [
                {"a": c["a"], "nombre_a": c["nombre_a"], "b": c["b"],
                 "nombre_b": c["nombre_b"], "tipo": "solape", "volumen_mm3": c["volumen_mm3"]}
                for c in rep["interferencias"]
            ]
            # NO caps silenciosos: si la interferencia acotada recortó a MAX_PAIRS, se declara
            return {"fantasmas": fantasmas, "colisiones_nuevas": colisiones,
                    "truncado": rep["truncado"]}
        try:
            png = render_scene_png(
                scene, body.view, highlight_ids=new_feats or None,
                labels=body.labels, section=body.section,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=png, media_type="image/png")


class ParamsIn(BaseModel):
    params: dict


@app.put("/api/commands/{command_id}")
def edit_command(command_id: str, body: ParamsIn, transient: bool = False, merge: bool = False) -> dict:
    with STATE_LOCK:  # 404 con «¿quisiste decir…?» antes de mutar (V6.5b, frente C)
        if not any(c["id"] == command_id for c in S.doc.commands):
            raise _not_found(command_id, kind="comando")
    return _state_or_error(
        lambda: S.doc.edit(
            command_id,
            _materialize_edit(command_id, body.params, merge),
            coalesce=transient,
            merge=merge,
        )
    )


class RemoveIn(BaseModel):
    ids: list[str]


@app.post("/api/commands/remove")
def remove_commands_endpoint(body: RemoveIn) -> dict:
    """Elimina comandos del log por id (atómico, con rollback si algo queda roto).
    Útil para cirugía de modelo: quitar features + sus juntas en un solo paso."""
    return _state_or_error(lambda: S.doc.remove_commands(body.ids))


def _params_reference(params: dict, fid: str) -> str | None:
    """Primera clave de params cuyo valor referencia el feature id: string igual,
    lista que lo contiene, o un nivel de dict anidado (selectores {'cerca': fid}).
    Búsqueda SUPERFICIAL por valores — no semántica profunda (V6.8-B)."""
    for key, val in params.items():
        if val == fid:
            return key
        if isinstance(val, list) and any(v == fid for v in val):
            return key
        if isinstance(val, dict) and any(v == fid for v in val.values()):
            return key
    return None


def _command_resumen(cmd: dict) -> str:
    """Etiqueta compacta de una fila del log: el `name` si existe, o «tipo sobre X»."""
    p = cmd.get("params", {})
    if p.get("name"):
        return str(p["name"])
    for k in ("feature", "feature_a", "target", "a", "parent", "members"):
        v = p.get(k)
        if v:
            if isinstance(v, list):
                v = ",".join(map(str, v[:3])) + ("…" if len(v) > 3 else "")
            return f"{cmd['type']} sobre {v}"
    return cmd["type"]


@app.get("/api/commands")
def find_commands_endpoint(
    type: str | None = None, feature: str | None = None,
    name: str | None = None, limit: int = 100,
) -> dict:
    """Busca en el LOG de comandos (V6.8-B): el command_id de una operación sin
    deducirlo por aritmética de lotes. Al menos UN filtro es obligatorio (el log
    entero ya lo da GET /api/document). Filas compactas [{id, type, resumen}].
      - type: match exacto del tipo de comando.
      - feature: comandos que CREARON ese feature id o lo REFERENCIAN en params.
      - name: substring case-insensitive del param `name`.
    Read-only. `total` declara el conteo sin recortar; `truncado` si limit lo cortó."""
    if not (type or feature or name):
        raise HTTPException(
            status_code=400,
            detail="Pasa al menos un filtro: type, feature o name "
            "(el log completo está en GET /api/document)",
        )
    limit = max(1, int(limit))
    with STATE_LOCK:
        creator = None
        if feature:
            feat = S.doc.scene.get(feature)
            creator = feat.command_id if feat is not None else None
        rows = []
        for c in S.doc.commands:
            if type and c["type"] != type:
                continue
            params = c.get("params", {})
            if name and name.lower() not in str(params.get("name", "")).lower():
                continue
            if feature:
                es_creador = c["id"] in (feature, creator)
                ref = _params_reference(params, feature)
                if not es_creador and ref is None:
                    continue
            rows.append({"id": c["id"], "type": c["type"], "resumen": _command_resumen(c)})
        if feature and not rows and creator is None:
            # el id no existe ni se referencia → 404 con «¿quisiste decir…?»
            raise _not_found(feature)
    return {"total": len(rows), "truncado": len(rows) > limit, "commands": rows[:limit]}


# ------------------------------------------------------------------ variables
class VariableIn(BaseModel):
    name: str
    expression: str


@app.post("/api/variables")
def set_variable(body: VariableIn) -> dict:
    def run():  # buscar DENTRO del lock: fuera, otra petición podía cambiar el log antes de mutar
        params = {"name": body.name, "expression": body.expression}
        existing = next((c["id"] for c in S.doc.commands if c["type"] == "set_variable"
                         and c["params"].get("name") == body.name), None)
        return S.doc.edit(existing, params) if existing else S.doc.execute("set_variable", params)

    return _state_or_error(run)


@app.delete("/api/variables/{name}")
def delete_variable(name: str) -> dict:
    def run():  # búsqueda y borrado en UNA adquisición de STATE_LOCK (sin TOCTOU)
        ids = [c["id"] for c in S.doc.commands
               if c["type"] == "set_variable" and c["params"].get("name") == name]
        if not ids:
            raise HTTPException(status_code=404, detail=f"No existe la variable '{name}'")
        return S.doc.remove_commands(ids)

    return _state_or_error(run)


@app.post("/api/undo")
def undo() -> dict:
    return _state_or_error(S.doc.undo)


@app.post("/api/redo")
def redo() -> dict:
    return _state_or_error(S.doc.redo)


# ------------------------------------------------------------ configuraciones
class ConfigIn(BaseModel):
    name: str


@app.post("/api/configurations")
def save_configuration(body: ConfigIn) -> dict:
    return _state_or_error(lambda: S.doc.save_configuration(body.name.strip()))


class ConfigValuesIn(BaseModel):
    values: dict[str, str]  # {variable: expresión} — V6.4c edición explícita de una variante


@app.put("/api/configurations/{name}")
def set_configuration(name: str, body: ConfigValuesIn) -> dict:
    """Edita una variante con {variable: expresión} explícito (tabla de diseño) SIN aplicarla."""
    return _state_or_error(lambda: S.doc.set_configuration(name, body.values))


@app.post("/api/configurations/{name}/apply")
def apply_configuration(name: str) -> dict:
    return _state_or_error(lambda: S.doc.apply_configuration(name))


@app.delete("/api/configurations/{name}")
def delete_configuration(name: str) -> dict:
    return _state_or_error(lambda: S.doc.delete_configuration(name))


# --------------------------------------------------------- biblioteca y BOM
@app.get("/api/catalog")
def get_catalog(category: str | None = None, names_only: bool = False) -> list[dict]:
    return catalog_payload(category, names_only)


@app.get("/api/bom")
def get_bom(by_group: bool = False) -> list[dict]:
    """Con `by_group=true` cada fila lleva su `grupo` (sub-ensamblaje) y las piezas
    iguales de grupos distintos salen separadas — subtotales por grupo/instancia."""
    with STATE_LOCK:
        return bom_from_scene(S.doc.scene, S.doc.default_material(), by_group=by_group)


@app.get("/api/costing.json")
def get_costing() -> dict:
    """BOM COSTEADO (misma agrupación del BOM + costo_ud/costo_total USD por fila con su
    fuente: catálogo referencial / estimación hardware / fabricación) + totales por
    categoría, catálogo vs fabricación e ítem más costoso. Read-only."""
    from apolo.library.costing import scene_costing

    with STATE_LOCK:
        return scene_costing(S.doc.scene, S.doc.default_material())


@app.get("/api/bom.csv")
def get_bom_csv() -> Response:
    with STATE_LOCK:
        csv_text = bom_to_csv(bom_from_scene(S.doc.scene, S.doc.default_material()))
    return Response(
        content=csv_text.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "proyecto"}-bom.csv"'},
    )


# --------------------------------------------------------------- validaciones
class ChecksIn(BaseModel):
    carga_kg: float | None = None
    largo_paquete_mm: float | None = None
    ancho_paquete_mm: float | None = None
    velocidad_m_s: float = 0
    joint_values: dict[str, float] = {}
    conveyor: dict | None = None  # validación predictiva: params de faja a evaluar sin construirla
    conveyor_solid_ids: list[str] | None = None  # marca explícita de los sólidos que forman la faja
    interference_ids: list[str] | None = None  # V6.5b: acota la interferencia a pares que tocan estos ids/grupos


@app.post("/api/checks")
def run_checks(body: ChecksIn) -> dict:
    with STATE_LOCK:
        from apolo.library.checks import (
            hardware_ids, interpenetration_report, joint_pairs, same_command_pairs,
        )

        jpairs = joint_pairs(S.doc)
        shapes_override = None
        pose_warnings: list[str] = []
        if any(v != 0 for v in body.joint_values.values()):
            from apolo.robotics.pose import posed_shapes

            shapes_override, pose_warnings = posed_shapes(S.doc, body.joint_values)
        # V6.5b: `interference_ids` acota a las parejas donde participa un id/grupo dado
        # (O(k·n)) — el agente valida SU zona de trabajo, no la máquina entera.
        focus = _expand_ids(body.interference_ids) if body.interference_ids else None
        interferencias = interference_report(
            S.doc.scene, shapes_override=shapes_override,
            exclude_pairs=jpairs | same_command_pairs(S.doc),
            exclude_ids=hardware_ids(S.doc),
            focus=focus,
        )
        if shapes_override is not None:  # interpenetración de cuerpos con junta compartida
            interferencias["interferencias"] += interpenetration_report(
                S.doc.scene, shapes_override, jpairs
            )
            interferencias["interferencias"].sort(key=lambda c: -c["volumen_mm3"])
        interferencias["avisos_pose"] = pose_warnings
        ingenieria = None
        conveyor = None
        req, carga, largo_paq, ancho_paq = requirement_inputs(
            S.doc, body.carga_kg, body.largo_paquete_mm, body.ancho_paquete_mm)
        velocidad = body.velocidad_m_s or float(req.get("velocidad_m_s") or 0)
        if carga and largo_paq:
            from apolo.library.rules import detect_conveyor, infer_from_solids

            conveyor = (
                body.conveyor
                or conveyor_params_from_doc(S.doc)
                or (infer_from_solids(S.doc.scene, body.conveyor_solid_ids)
                    if body.conveyor_solid_ids else None)
                or detect_conveyor(S.doc.scene, S.doc.variables_resolved)
            )
            inherit_inclination(conveyor, req)
            if conveyor:
                ingenieria = conveyor_engineering_check(
                    conveyor,
                    carga_kg=carga,
                    largo_paquete_mm=largo_paq,
                    velocidad_m_s=velocidad,
                    ancho_paquete_mm=ancho_paq,
                )
            else:
                ingenieria = [
                    {
                        "regla": "transportador",
                        "estado": "aviso",
                        "detalle": "No hay ningún transportador en el documento que validar.",
                    }
                ]
        # chequeo estructural UNIVERSAL + resultados FEA guardados (con vigencia)
        estructura = structure_rules(S.doc, carga, conveyor)
        # V7.2b: lints pre-entrega (barreno sin perno · pieza sin grupo ni unión) —
        # olvidos de MODELADO que el chequeo estructural no ve; vacíos si el modelo está sano
        from apolo.commands.expressions import resolve_params
        from apolo.library.lints import predelivery_lints

        estructura += predelivery_lints(
            S.doc.scene, S.doc.commands, S.doc.fasteners, S.doc.grounds, S.doc.joints, S.doc.mates,
            resolve=lambda p: resolve_params(p, S.doc.variables_resolved),
        )
    return {"interferencias": interferencias, "ingenieria": ingenieria, "estructura": estructura}


class VerifyIn(BaseModel):
    checks: list[dict] = []


@app.post("/api/verify")
def verify_endpoint(body: VerifyIn) -> dict:
    """Lote de ASERCIONES numéricas (V6.5c), READ-ONLY: el agente declara sus invariantes
    (distancia/volumen/bbox/sin_interferencia/existe) y las verifica en UNA llamada en vez de
    encadenar N `measure` + aritmética mental. Devuelve `{ok, resultados:[{check,ok,actual,
    esperado}]}`. La interferencia se reusa acotada (V6.5b) con las exclusiones normales."""
    with STATE_LOCK:
        resultados = verify_checks(S.doc, S.doc.scene, body.checks, expand=_expand_ids)
    return {"ok": all(r["ok"] for r in resultados), "resultados": resultados}


class DeliveryIn(BaseModel):
    con_gravedad: bool = False


@app.post("/api/delivery-check")
def delivery_check_endpoint(body: DeliveryIn) -> dict:
    """PUERTA DE ENTREGA (V6.9): corre la batería de cierre y devuelve el SEMÁFORO
    {veredicto VERDE|AMARILLO|ROJO, bloqueantes, avisos, no_aplica, resumen}. Agregación
    PURA de chequeos existentes (library/delivery.py): interferencias en DISEÑO
    (exclusiones normales) + sujeción DECLARADA (soundness SIN autodetect — la puerta
    valida lo que el modelo declara, no lo que un detector adivina) + lints pre-entrega
    + integridad/suprimidos + colisión EN POSE en los fotogramas de REPOSO de los
    estudios declarados (extremos + dwells; asiento ≤ tolerancia declarado, no bloquea).
    `con_gravedad` añade la simulación MuJoCo (cara; opt-in). Read-only."""
    from apolo.library.delivery import delivery_report

    gravedad = None
    if body.con_gravedad:
        # dos-locks propio (_stability); with_autodetect=False: la puerta es DECLARADA
        res = _stability(StabilityIn(with_autodetect=False))
        gravedad = {k: res.get(k) for k in ("fell", "estables", "settled", "n_grounded")}

    with STATE_LOCK:  # la puerta valida lo DECLARADO: services/delivery_inputs.py
        return delivery_report(**delivery_inputs(S.doc, expand=_expand_ids), gravedad=gravedad)


# ------------------------------------------------------------------ ensamblaje
@app.get("/api/mates")
def get_mates() -> list[dict]:
    with STATE_LOCK:
        return [
            {k: v for k, v in m.items() if k not in ("ref_a", "ref_b")}
            for m in S.doc.mates.values()
        ]


@app.delete("/api/mates/{name}")
def delete_mate(name: str) -> dict:
    return _state_or_error(lambda: _remove_owner_command(
        S.doc.mates, name, "add_mate", f"No existe el mate '{name}'", "Este mate pertenece a una plantilla"))


# ------------------------------------------------- restricciones de riel (lazo cerrado)
class SolveIn(BaseModel):
    values: dict[str, float] = {}


@app.get("/api/constraints")
def get_constraints() -> list[dict]:
    with STATE_LOCK:
        return list(S.doc.constraints.values())


@app.post("/api/constraints/solve")
def solve_constraints_endpoint(body: SolveIn) -> dict:
    """Dado un conjunto de valores de junta (driver + libres), devuelve los
    valores con las juntas DEPENDIENTES resueltas para cumplir las restricciones
    de riel. Read-only: no muta el documento. Lo usa la UI para arrastre en vivo."""
    from apolo.assembly.constraints import solve_constraints

    with STATE_LOCK:
        return {"values": solve_constraints(S.doc.joints, S.doc.constraints, body.values)}


@app.delete("/api/constraints/{name}")
def delete_constraint(name: str) -> dict:
    with STATE_LOCK:
        con = S.doc.constraints.get(name)
    if con is None:
        raise HTTPException(status_code=404, detail=f"No existe la restricción '{name}'")
    return _state_or_error(lambda: S.doc.remove_commands([con["command_id"]]))


# ----------------------------------------- conectividad / validación de ensamblaje
class SoundnessIn(BaseModel):
    with_autodetect: bool = False  # superpone uniones detectadas por geometría (efímeras)


@app.get("/api/connectivity")
def get_connectivity() -> dict:
    """Uniones declaradas del documento: fijadores (A↔B) y anclajes a tierra."""
    with STATE_LOCK:
        return {
            "fasteners": list(S.doc.fasteners.values()),
            "grounds": list(S.doc.grounds.values()),
        }


@app.post("/api/assembly/autodetect")
def assembly_autodetect() -> dict:
    """Propone uniones desde la geometría (apoyos en el piso + pares en contacto).
    Read-only: no muta el documento. El usuario/agente confirma con ground/fasten."""
    from apolo.assembly.autodetect import detect_connections

    with STATE_LOCK:
        return detect_connections(S.doc.scene)


@app.delete("/api/fasteners/{name}")
def delete_fastener(name: str) -> dict:
    with STATE_LOCK:
        f = S.doc.fasteners.get(name)
    if f is None:
        raise HTTPException(status_code=404, detail=f"No existe el fijador '{name}'")
    return _state_or_error(lambda: S.doc.remove_commands([f["command_id"]]))


@app.delete("/api/grounds/{name}")
def delete_ground(name: str) -> dict:
    with STATE_LOCK:
        g = S.doc.grounds.get(name)
    if g is None:
        raise HTTPException(status_code=404, detail=f"No existe el anclaje '{name}'")
    return _state_or_error(lambda: S.doc.remove_commands([g["command_id"]]))


class ConnectionsRemoveIn(BaseModel):
    names: list[str]


@app.post("/api/connections/remove")
def remove_connections(body: ConnectionsRemoveIn) -> dict:
    """Borra VARIAS uniones declaradas por nombre (fijadores y/o anclajes, V6.8-A)
    en UN remove_commands atómico (1 undo). Un nombre inexistente → 404 nombrándolo
    y NO se borra ninguna — sin estados a medias en cirugías. El payload lleva
    `conexiones_borradas` [{name, tipo}]."""
    names = list(dict.fromkeys(body.names))
    if not names:
        raise HTTPException(status_code=400, detail="La lista 'names' no puede estar vacía")
    borradas: list[dict] = []

    def run():
        ids: list[str] = []
        for name in names:
            if name in S.doc.fasteners:
                conn, tipo = S.doc.fasteners[name], "fijador"
            elif name in S.doc.grounds:
                conn, tipo = S.doc.grounds[name], "anclaje"
            else:
                validas = sorted(set(S.doc.fasteners) | set(S.doc.grounds))
                raise HTTPException(
                    status_code=404,
                    detail=f"No existe la unión '{name}' — no se borró ninguna. "
                    f"Declaradas: {', '.join(validas) or 'ninguna'}",
                )
            borradas.append({"name": name, "tipo": tipo})
            ids.append(conn["command_id"])
        return S.doc.remove_commands(list(dict.fromkeys(ids)))

    payload = _state_or_error(run)
    payload["conexiones_borradas"] = borradas
    return payload


@app.post("/api/assembly/declare")
def assembly_declare() -> dict:
    """Auto-declara la ESTRUCTURA real (anclajes al piso + uniones de soporte) como comandos
    PERSISTIDOS. Inteligente (grafo de soporte dirigido): no fija las piezas colgantes (p. ej.
    rodillos de retorno) → la prueba de gravedad EXACTA las tira. Idempotente: no recrea uniones
    ya declaradas. Tras esto, `stability` con `with_autodetect=false` valida solo lo declarado."""
    from apolo.assembly.autodetect import detect_structure
    from apolo.batch import execute_batch

    with STATE_LOCK:
        det = detect_structure(S.doc.scene)
        existing_names = set(S.doc.fasteners) | set(S.doc.grounds)
        ground_feats = {g["feature"] for g in S.doc.grounds.values()}
        pairs = {frozenset((f["a"], f["b"])) for f in S.doc.fasteners.values()}

        def uniq(prefix: str) -> str:
            i = 1
            while f"{prefix}{i}" in existing_names:
                i += 1
            name = f"{prefix}{i}"
            existing_names.add(name)
            return name

        actions: list[dict] = []
        for g in det["grounds"]:
            if g["feature"] in ground_feats:
                continue
            ground_feats.add(g["feature"])
            actions.append({"type": "ground", "params": {
                "name": uniq("auto_g_"), "feature": g["feature"], "nota": (g.get("reason") or "")[:120]}})
        for f in det["fasteners"]:
            pair = frozenset((f["a"], f["b"]))
            if pair in pairs:
                continue
            pairs.add(pair)
            actions.append({"type": "fasten", "params": {
                "name": uniq("auto_f_"), "a": f["a"], "b": f["b"], "kind": f["kind"],
                "nota": (f.get("reason") or "")[:120]}})
        if not actions:
            return _state_or_error(lambda: None)
        return _state_or_error(lambda: execute_batch(S.doc, actions))


class AutoGroupIn(BaseModel):
    dry_run: bool = False


@app.post("/api/assembly/auto-group")
def assembly_auto_group(body: AutoGroupIn) -> dict:
    """Auto-agrupa el modelo en SUB-ENSAMBLAJES por subsistema (misma heurística del
    árbol: super-comando → catálogo → palabra clave del nombre). Idempotente (omite
    grupos ya existentes y comandos ya agrupados); con `dry_run` solo PROPONE sin
    mutar. Los grupos quedan como comandos `create_group` del log (undo/persistencia)."""
    from apolo.assembly.grouping import propose_groups
    from apolo.batch import execute_batch
    from apolo.library.catalog import CATALOG

    with STATE_LOCK:
        proposal = propose_groups(S.doc.scene, S.doc.commands, CATALOG, S.doc.groups)
        if body.dry_run or not proposal:
            return {"dry_run": body.dry_run, "proposal": proposal, "created": 0}
        actions = [{"type": "create_group", "params": g} for g in proposal]
        payload = _state_or_error(lambda: execute_batch(S.doc, actions))
    payload["proposal"] = proposal
    payload["created"] = len(proposal)
    return payload


@app.post("/api/assembly/soundness")
def assembly_soundness(body: SoundnessIn) -> dict:
    """Validación de ensamblaje: ¿cada pieza tiene un camino de sujeción hasta el
    piso? Determinista, sin física. Con `with_autodetect` superpone (sin persistir)
    las uniones detectadas por geometría para responder 'si fijara todo lo que se
    toca, ¿qué seguiría flotando?'. Read-only."""
    from apolo.assembly.autodetect import detect_connections
    from apolo.assembly.connectivity import build_graph, soundness_report

    with STATE_LOCK:
        extra_edges: list = []
        extra_grounds: set = set()
        detected = None
        if body.with_autodetect:
            detected = detect_connections(S.doc.scene)
            extra_edges = [(c["a"], c["b"], "contacto", "") for c in detected["fasteners"]]
            extra_grounds = {g["feature"] for g in detected["grounds"]}
        graph = build_graph(
            S.doc.scene, S.doc.joints, S.doc.mates, S.doc.fasteners, S.doc.grounds,
            extra_edges=extra_edges, extra_grounds=extra_grounds,
        )
        report = soundness_report(graph)
        report["floating_detail"] = [
            {"id": fid, "nombre": getattr(S.doc.scene[fid], "name", fid)}
            for fid in report["floating"]
        ]
        if detected is not None:
            report["autodetect"] = {
                "floor_z": detected["floor_z"],
                "n_grounds": len(detected["grounds"]),
                "n_contactos": len(detected["fasteners"]),
            }
        return report


@app.get("/api/assembly/dof")
def assembly_dof() -> dict:
    """Reporte de GRADOS DE LIBERTAD (V6.3c): por sólido, ¿cuántos GDL le quedan tras
    ground/juntas/mates? Conteo Grübler determinista, sin OCCT. Read-only."""
    from apolo.assembly.dof import dof_report

    with STATE_LOCK:
        return dof_report(S.doc.scene, S.doc.joints, S.doc.mates, S.doc.grounds)


@app.post("/api/assembly/stability")
def assembly_stability(body: StabilityIn) -> dict:
    """Simula la gravedad sobre TODA la máquina (cuerpos rígidos + casco convexo):
    las piezas sujetas a tierra son estáticas, el resto cae. Devuelve qué piezas se
    CAYERON (desplazamiento del centro de masa) y cuáles aguantaron. Read-only.
    `frames` se omite por defecto (es grande); pide `include_frames` para animar la
    caída en el viewport, o usa el endpoint .gif."""
    res = _stability(body)
    if body.include_frames:
        return res
    return {k: v for k, v in res.items() if k != "frames"}


@app.post("/api/assembly/stability.gif")
def assembly_stability_gif(body: StabilityIn) -> Response:
    """GIF animado de la caída: la estructura sujeta de fondo + las piezas que caen."""
    from apolo.physics.anim import render_drop_gif

    res = _stability(body)  # simulación bajo dos-locks (no bajo STATE_LOCK)
    if not res["products"]:
        raise HTTPException(status_code=400, detail=res.get("mensaje", "nada que simular"))
    dynamic_ids = {p["id"] for p in res["products"]}
    with STATE_LOCK:  # el GIF tesela la escena estática de fondo (OCCT) → bajo el lock
        static_scene = {fid: f for fid, f in S.doc.scene.items() if fid not in dynamic_ids}
        gif = render_drop_gif(static_scene, res["products"], res["frames"], fps=body.fps)
    return Response(content=gif, media_type="image/gif")


# ---------------------------------------------------- requisitos de proyecto
class RequirementsIn(BaseModel):
    fields: dict = {}


@app.get("/api/requirements")
def get_requirements() -> dict:
    with STATE_LOCK:
        return {"requirements": S.doc.requirements}


@app.put("/api/requirements")
def put_requirements(body: RequirementsIn) -> dict:
    with STATE_LOCK:
        try:
            S.doc.set_requirements(body.fields)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _autosave()
        return {"ok": True, "requirements": S.doc.requirements}


# ------------------------------------------------ cadenas de cotas / stack-up (V7.3)
class StackupIn(BaseModel):
    name: str
    eslabones: list[dict] = []
    requisito: dict = {}


class StackupDeleteIn(BaseModel):
    name: str


def _stackup_rules() -> list[dict]:
    """Envoltorio de compatibilidad (D4 del plan partir-api-main): las reglas de stack-up
    del documento ACTIVO (`services.stackup_eval.stackup_rules`). Bajo STATE_LOCK."""
    return stackup_rules(S.doc)


@app.get("/api/stackup")
def get_stackup(scope: str = "all") -> dict:
    """Evalúa las cadenas de cotas (declaradas + auto de pernos): peor caso, RSS y
    veredicto por cadena. scope = all | declared | auto. Read-only."""
    if scope not in ("all", "declared", "auto"):  # V7.3 auditoría: typo ≠ lista vacía silenciosa
        raise HTTPException(status_code=400,
                            detail=f"scope '{scope}' inválido (usa all | declared | auto)")
    with STATE_LOCK:
        chains = evaluate_stackups(S.doc, scope)  # aislada por cadena: nunca lanza por una mala
    # el `ok` global pesa las cadenas CON veredicto (declaradas + join_bolted) — y una
    # cadena DECLARADA en error también lo baja (declaraste algo que no se puede verificar);
    # las informativas (pernos manuales sin tolerancia de posición) no cuentan.
    ok = True
    for c in chains:
        if c.get("informativo"):
            continue
        if c.get("error") or not c.get("ok_peor_caso", True):
            ok = False
    return {"ok": ok, "cadenas": chains}


@app.put("/api/stackup")
def put_stackup(body: StackupIn) -> dict:
    with STATE_LOCK:
        prev = S.doc.stackups.get(body.name)  # para rollback si la cadena no evalúa
        try:
            S.doc.set_stackup(body.name, body.eslabones, body.requisito)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        chains = evaluate_stackups(S.doc, "declared")
        mine = next((c for c in chains if c.get("name") == body.name.strip()), None)
        if mine is not None and mine.get("error"):
            # V7.3 auditoría: una cadena que NO evalúa no se persiste (antes quedaba
            # guardada y envenenaba GET/memoria para siempre) — rollback + 400.
            if prev is None:
                S.doc.stackups.pop(body.name.strip(), None)
            else:
                S.doc.stackups[body.name.strip()] = prev
            raise HTTPException(status_code=400,
                                detail=f"La cadena no evalúa (no se guardó): {mine['error']}")
        _autosave()
        return {"ok": True, "cadenas": chains}


@app.delete("/api/stackup")
def delete_stackup(body: StackupDeleteIn) -> dict:
    with STATE_LOCK:
        S.doc.delete_stackup(body.name)
        _autosave()
        return {"ok": True}


# ------------------------------------------------------------------ física (drop-test)
@app.post("/api/physics/drop")
def physics_drop(body: DropIn) -> dict:
    return _drop(body)


@app.post("/api/physics/drop.gif")
def physics_drop_gif(body: DropIn) -> Response:
    from apolo.physics.anim import render_drop_gif

    res = _drop(body)
    with STATE_LOCK:
        gif = render_drop_gif(S.doc.scene, res["products"], res["frames"], fps=body.fps)
    return Response(content=gif, media_type="image/gif")


# ---------------------------------------------------------------- FEA (V5.6)
@app.post("/api/fea/static")
def fea_static(body: FeaStaticIn) -> dict:
    """FEA estático lineal de UNA pieza (malla tet P2 + elasticidad lineal).
    Read-only sobre la geometría; el resumen se guarda como metadato para la
    memoria de cálculo (save=false para no persistir)."""
    resumen, _ = _fea_static_run(body)
    return resumen


@app.post("/api/fea/static.png")
def fea_static_png(body: FeaStaticIn) -> Response:
    """Igual que /api/fea/static pero devuelve el FRINGE von Mises (PNG, mapa de
    colores + barra de escala) del campo resuelto."""
    from apolo.fea.fringe import fringe_png

    resumen, field = _fea_static_run(body)
    png = fringe_png(field, title=f"von Mises [MPa] · {resumen['pieza']} · FS={resumen['fs']}")
    return Response(content=png, media_type="image/png")


@app.post("/api/fea/assembly")
def fea_assembly(body: FeaAssemblyIn) -> dict:
    """FEA estático lineal BONDED de un SUB-ENSAMBLAJE (V7.4): el bastidor pegado bajo
    la carga de diseño, multi-material, con FS POR PIEZA. Deriva el empotramiento de
    los grounds y la carga de los requisitos (sobre la cama) salvo override explícito.
    El solve puede tardar MINUTOS: invoca con mesh_size_mm generoso primero."""
    resumen, _ = _fea_assembly_run(body)
    return resumen


@app.post("/api/fea/assembly.png")
def fea_assembly_png(body: FeaAssemblyIn) -> Response:
    """Igual que /api/fea/assembly pero devuelve el FRINGE von Mises del ensamblaje."""
    from apolo.fea.fringe import fringe_png

    resumen, field = _fea_assembly_run(body)
    png = fringe_png(field, title=f"von Mises [MPa] · {resumen['grupo']} · FS={resumen['fs']}")
    return Response(content=png, media_type="image/png")


@app.get("/api/fea/group/{name}")
def get_fea_group(name: str) -> dict:
    with STATE_LOCK:
        res = S.doc.fea.get(f"group:{name}")
        if res is None:
            raise HTTPException(status_code=404, detail="El grupo no tiene FEA guardado")
        return res


@app.get("/api/fea/{feature_id}")
def get_fea(feature_id: str) -> dict:
    with STATE_LOCK:
        res = S.doc.fea.get(feature_id)
        if res is None:
            raise HTTPException(status_code=404, detail="La pieza no tiene FEA guardado")
        return res


@app.get("/api/fea/group/{name}/fringe.png")
def get_fea_group_fringe(name: str) -> Response:
    """Fringe del ÚLTIMO análisis del ensamblaje SIN re-resolver (campo en memoria del
    proceso; si el server se reinició, re-ejecuta POST /api/fea/assembly)."""
    from apolo.fea.fringe import fringe_png

    key = f"group:{name}"
    field = _last_fea_field(key)
    if field is None:
        raise HTTPException(status_code=404,
                            detail="No hay campo FEA en memoria para ese grupo: "
                                   "corre POST /api/fea/assembly primero")
    with STATE_LOCK:
        res = S.doc.fea.get(key) or {}
    title = f"von Mises [MPa] · {res.get('grupo', name)} · FS={res.get('fs')}"
    return Response(content=fringe_png(field, title=title), media_type="image/png")


@app.get("/api/fea/{feature_id}/fringe.png")
def get_fea_fringe(feature_id: str) -> Response:
    """Fringe del ÚLTIMO análisis de la pieza SIN re-resolver (campo en memoria del
    proceso; si el server se reinició, re-ejecuta POST /api/fea/static)."""
    from apolo.fea.fringe import fringe_png

    field = _last_fea_field(feature_id)
    if field is None:
        raise HTTPException(status_code=404,
                            detail="No hay campo FEA en memoria para esa pieza: "
                                   "corre POST /api/fea/static primero")
    with STATE_LOCK:
        res = S.doc.fea.get(feature_id) or {}
    title = f"von Mises [MPa] · {res.get('pieza', feature_id)} · FS={res.get('fs')}"
    return Response(content=fringe_png(field, title=title), media_type="image/png")


def _fea_rules() -> list[dict]:
    """Envoltorio de compatibilidad (D4 del plan partir-api-main): las reglas FEA con
    vigencia del documento ACTIVO (`services.fea_rules.fea_rules`). Bajo STATE_LOCK."""
    return fea_rules(S.doc)


# --------------------------------------------- despiece de fabricación (Fase D)
@app.get("/api/cutlist.json")
def cutlist_json() -> dict:
    """Lista de corte (a-medida + catálogo cortable, agrupada por material/dimensiones) +
    totales por material + cédula de herraje. Read-only."""
    from apolo.library.cutlist import cut_list, cut_list_totals, hardware_schedule

    with STATE_LOCK:
        rows = cut_list(S.doc.scene)
        return {
            "lista_de_corte": rows,
            "totales": cut_list_totals(rows),
            "herraje": hardware_schedule(S.doc.scene),
        }


@app.get("/api/cutlist.csv")
def cutlist_csv_endpoint() -> Response:
    from apolo.library.cutlist import cut_list, cut_list_csv, cut_list_totals

    with STATE_LOCK:
        rows = cut_list(S.doc.scene)
        text = cut_list_csv(rows, cut_list_totals(rows))
    return Response(
        content=text, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lista-de-corte.csv"},
    )


def _nesting_model(mode: str, stock_w: float, stock_h: float, material: str | None, kerf: float):
    from apolo.library.cutlist import cut_list
    from apolo.library.nesting import nest_1d, nest_2d, nesting_sheet_1d, nesting_sheet_2d

    with STATE_LOCK:
        rows = [r for r in cut_list(S.doc.scene) if not material or r["material"] == material]
    if mode == "1d":
        lengths = [r["largo_mm"] for r in rows for _ in range(r["cantidad"])]
        bars = nest_1d(lengths, stock_w, kerf)
        return nesting_sheet_1d(bars, stock_w, title=f"NESTING 1D · {material or 'todos'}")
    rects = [(r["ancho_mm"], r["largo_mm"]) for r in rows for _ in range(r["cantidad"])]
    sheets = nest_2d(rects, stock_w, stock_h, kerf)
    return nesting_sheet_2d(sheets, stock_w, stock_h, title=f"NESTING 2D · {material or 'todos'}")


@app.get("/api/nesting.svg")
def nesting_svg(
    mode: str = "2d", stock_w: float = 2440.0, stock_h: float = 1220.0,
    material: str | None = None, kerf: float = 3.0,
) -> Response:
    """Plano de nesting (acomodo de corte). mode=2d (tableros/vidrio, stock_w×stock_h) o
    1d (barras de largo stock_w). `material` filtra (madera/vidrio/acero...). Read-only."""
    from apolo.drawing import sheet_to_svg

    model = _nesting_model(mode, stock_w, stock_h, material, kerf)
    return Response(content=sheet_to_svg(model), media_type="image/svg+xml")


@app.get("/api/nesting.dxf")
def nesting_dxf(
    mode: str = "2d", stock_w: float = 2440.0, stock_h: float = 1220.0,
    material: str | None = None, kerf: float = 3.0,
) -> Response:
    from apolo.drawing import sheet_to_dxf

    model = _nesting_model(mode, stock_w, stock_h, material, kerf)
    return Response(
        content=sheet_to_dxf(model), media_type="application/dxf",
        headers={"Content-Disposition": "attachment; filename=nesting.dxf"},
    )


@app.get("/api/nesting.json")
def nesting_json(
    mode: str = "2d", stock_w: float = 2440.0, stock_h: float = 1220.0,
    material: str | None = None, kerf: float = 3.0,
) -> dict:
    """Resumen del nesting: nº de planchas/barras, desperdicio % y nº de piezas. Read-only."""
    from apolo.library.cutlist import cut_list
    from apolo.library.nesting import nest_1d, nest_2d, waste_1d, waste_2d

    with STATE_LOCK:
        rows = [r for r in cut_list(S.doc.scene) if not material or r["material"] == material]
    if mode == "1d":
        lengths = [r["largo_mm"] for r in rows for _ in range(r["cantidad"])]
        bars = nest_1d(lengths, stock_w, kerf)
        return {"mode": "1d", "stock_len_mm": stock_w, "n_barras": len(bars),
                "desperdicio_pct": waste_1d(bars, stock_w), "n_piezas": len(lengths)}
    rects = [(r["ancho_mm"], r["largo_mm"]) for r in rows for _ in range(r["cantidad"])]
    sheets = nest_2d(rects, stock_w, stock_h, kerf)
    return {"mode": "2d", "stock_mm": [stock_w, stock_h], "n_planchas": len(sheets),
            "desperdicio_pct": waste_2d(sheets, stock_w, stock_h), "n_piezas": len(rects)}


@app.get("/api/calc-report.pdf")
def calc_report_pdf(
    carga_kg: float | None = None,
    largo_paquete_mm: float | None = None,
    ancho_paquete_mm: float | None = None,
    velocidad_m_s: float | None = None,
    rev: str = "A",
    sheet: str = "A4",
) -> Response:
    """MEMORIA DE CÁLCULO en PDF multipágina: portada (bases de diseño + índice +
    veredicto) + una página por verificación con su fórmula, sustitución, criterio y
    factor de seguridad. Sin parámetros usa los REQUISITOS guardados del proyecto;
    los explícitos ganan. Read-only."""
    from datetime import date

    from apolo.drawing import sheets_to_pdf
    from apolo.drawing.calc_report import calc_report
    from apolo.kernel.render import render_scene_png
    from apolo.library.rules import conveyor_engineering_check as conv_check
    from apolo.library.rules import detect_conveyor

    with STATE_LOCK:
        req, carga, largo_paq, ancho_paq = requirement_inputs(
            S.doc, carga_kg, largo_paquete_mm, ancho_paquete_mm)
        velocidad = velocidad_m_s if velocidad_m_s is not None else float(req.get("velocidad_m_s") or 0)
        # carga/largo de paquete son requisitos del VERTICAL transportadores: sin ellos se
        # omiten las reglas de conveyor y la memoria se emite igual con las verificaciones
        # UNIVERSALES (estructura/uniones/vuelco + FEA + cadenas de cotas). Exigirlos para
        # todo bloqueaba la memoria de cualquier proyecto que no fuera una faja — hallazgo
        # del SEGUNDO testigo (puerta de carpintería, 2026-07-24).
        sin_req_conveyor = not carga or not largo_paq
        rules: list[dict] = []
        conveyor = None if sin_req_conveyor else (
            conveyor_params_from_doc(S.doc) or detect_conveyor(S.doc.scene, S.doc.variables_resolved))
        if conveyor:
            inherit_inclination(conveyor, req)
            rules += conv_check(conveyor, carga_kg=carga, largo_paquete_mm=largo_paq,
                                velocidad_m_s=velocidad, ancho_paquete_mm=ancho_paq)
        # estructura/uniones/vuelco + página FEA en la memoria (con chequeo de vigencia)
        rules += structure_rules(S.doc, carga, conveyor)
        rules += _stackup_rules()  # V7.3: cadenas de cotas (stack-up) declaradas/auto
        if sin_req_conveyor:
            # DECLARAR lo omitido: una memoria que calla lo que no verificó miente por
            # ausencia. Va como regla-aviso, así viaja a la misma página que el resto.
            rules.append({
                "regla": "alcance de la memoria",
                "estado": "aviso",
                "detalle": "Sin `carga_kg` / `largo_paquete_mm` declarados: se OMITEN las "
                           "verificaciones de transportador (arrastre, adherencia del tambor, "
                           "capacidad, velocidad). Lo verificado aquí es estructural y de "
                           "uniones.",
                "recomendacion": "Declara los requisitos con set_requirements si el equipo "
                                 "transporta producto.",
            })
        hay_piezas = any(getattr(f, "visible", True) for f in S.doc.scene.values())
        if not rules or not hay_piezas:
            raise HTTPException(
                status_code=400,
                detail="No hay nada que documentar: el modelo está vacío o no declara "
                       "uniones, apoyos ni requisitos. Modela/declara y reintenta.",
            )
        png = None
        try:
            vis = {fid: f for fid, f in S.doc.scene.items() if getattr(f, "visible", True)}
            if vis:
                png = render_scene_png(vis, view="iso", size_px=620, clean=True,
                                       colors=_feature_colors())
        except Exception:
            png = None  # sin render la memoria sigue valiendo
        meta = _drawing_meta()
        meta["revisions"] = (meta.get("revisions") or []) + [
            {"rev": rev, "date": date.today().isoformat(), "note": "Memoria de cálculo"}
        ]
        # los requisitos completos van a la portada; los efectivos ganan
        # sin requisitos de transportador NO se inyectan claves vacías a la portada (un
        # «carga_kg: None» impreso es peor que la ausencia del renglón)
        req_efectivos = dict(req)
        if carga:
            req_efectivos["carga_kg"] = carga
        if largo_paq:
            req_efectivos["largo_paquete_mm"] = largo_paq
        if ancho_paq:
            req_efectivos["ancho_paquete_mm"] = ancho_paq
        if velocidad:
            req_efectivos["velocidad_m_s"] = velocidad
        pages = calc_report(S.doc.scene, rules=rules, requirements=req_efectivos,
                            project_name=S.doc.name or "Sin título", png=png, meta=meta,
                            sheet=sheet)
    return Response(
        content=sheets_to_pdf(pages), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "proyecto"}-memoria-calculo.pdf"'},
    )


@app.get("/api/quote.pdf")
def quote_pdf(margin_pct: float = 25.0, tax_pct: float = 0.0,
              currency: str | None = None, fx: float | None = None,
              sheet: str = "A4") -> Response:
    """COTIZACIÓN en PDF multipágina: resumen económico (desglose por categoría, margen,
    impuesto opcional, PRECIO DE VENTA, ítem más costoso, notas comerciales) + detalle
    de partidas (BOM costeado completo con la fuente de cada precio). `currency`/`fx`
    (tipo de cambio sobre USD, solo presentación) caen a los requisitos del proyecto
    (claves `moneda`/`tipo_cambio`); los params explícitos ganan. Read-only."""
    from apolo.drawing import sheets_to_pdf
    from apolo.drawing.quote import quotation_pages

    with STATE_LOCK:
        req = S.doc.requirements or {}
        cur = currency or str(req.get("moneda") or "USD")
        fx_eff = fx if fx is not None else float(req.get("tipo_cambio") or 1.0)
        pages = quotation_pages(
            S.doc.scene, project_name=S.doc.name or "Sin título",
            requirements=S.doc.requirements, margin_pct=margin_pct, tax_pct=tax_pct,
            currency=cur, fx=fx_eff, meta=_drawing_meta(),
        )
    return Response(
        content=sheets_to_pdf(pages), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "proyecto"}-cotizacion.pdf"'},
    )


@app.get("/api/assembly-manual.pdf")
def assembly_manual_pdf(sheet: str = "A3", size_px: int = 700, isolate: str = "",
                        title: str = "") -> Response:
    """MANUAL DE ENSAMBLAJE paso a paso (PDF multipágina): portada con la secuencia + 1 lámina por
    PASO (render 3D acumulado con las piezas nuevas resaltadas y lo previo en gris, cámara estable,
    lista de piezas/herraje + instrucción). La secuencia se deriva del log de comandos (orden de
    armado real) + familias de catálogo. `isolate` (CSV de ids) acota el manual a un SUB-ENSAMBLAJE
    (p. ej. una hoja) sin tocar el documento. Read-only."""
    from apolo.drawing import assembly_manual, sheets_to_pdf

    with STATE_LOCK:
        scene = S.doc.scene
        if isolate:
            ids = _expand_ids(isolate) or []  # acepta NOMBRES de grupo (V5.2)
            scene = {fid: S.doc.scene[fid] for fid in ids if fid in S.doc.scene}
            if not scene:
                raise HTTPException(status_code=400, detail="isolate: ningún id existe en la escena")
        try:
            pages = assembly_manual(scene, commands=S.doc.commands, project_name=title or S.doc.name,
                                    sheet=sheet, meta=_drawing_meta(), colors=_feature_colors(),
                                    size_px=size_px)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    fname = (title or S.doc.name or "manual").encode("ascii", "ignore").decode() or "manual"
    return Response(
        content=sheets_to_pdf(pages), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}-ensamblaje.pdf"'},
    )


# -------------------------------------------------------------------- routers
# Cada router agrupa las rutas de un tema; las rutas que pueden casar la MISMA URL viven en
# el mismo router y en su orden de siempre (D5 del plan partir-api-main).
for _router in (core, features, projects, motion, render, drawings):
    app.include_router(_router.router)


# ------------------------------------------------------------------- UI build
# `paths.ui_dist()` resuelve la UI empaquetada (instalación pip) o el build del
# checkout; None = sin bundle → la API sirve solo /api (headless, útil para MCP).
_ui_dist = _paths.ui_dist()
if _ui_dist is not None:
    app.mount("/", StaticFiles(directory=str(_ui_dist), html=True), name="ui")
