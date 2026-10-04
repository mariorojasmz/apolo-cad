"""API de Genix Apolo CAD.

La UI y el agente IA son dos clientes de esta misma API: toda operación de
modelado entra por /api/commands (o /api/commands/batch para los lotes que
propone el agente).
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import traceback
from pathlib import Path

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apolo import paths as _paths
from apolo.agent import AgentHooks, chat_stream
from apolo.commands import command_schemas, command_schemas_persona
from apolo.doc import Document, DocumentError
from apolo.kernel import bbox_payload, export_step_file
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
    hole_thread_map as _hole_thread_map,
    piece_datum_frame as _piece_datum_frame,  # noqa: F401
    piece_datum_sides as _piece_datum_sides,  # noqa: F401
    piece_dim_tols as _piece_dim_tols,  # noqa: F401
    piece_pos_tols as _piece_pos_tols,  # noqa: F401
    scene_fit_map as _scene_fit_map,
    sheet_set_maps,
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
    _autosave_sched,
    _flush_autosave,
    _flush_lock,  # noqa: F401 — sólo los tests (orden de locks)
    _project_switch,
)
from .common import (
    JOBS,
    _drawing_meta,
    _expand_ids,
    _materialize_edit,
    _materialize_insert_project,
    _not_found,
    _state_or_error,
    _store_required,
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
from .scene import (  # D4: por IDENTIDAD (cachés mutadas en sitio por los tests)
    _DEF_MESH_CACHE,  # noqa: F401
    _GEOM_REVS,  # noqa: F401
    SCENE_EPOCH,
    _cached_render,  # noqa: F401
    _definition_mesh,  # noqa: F401
    _feature_brief,
    _feature_colors,
    _open_briefing,
    document_payload,
    groups_payload,
    scene_payload,
    scene_summary_dict,
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


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await WS.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        WS.disconnect(ws)


def _suggest_ids(missing, limit: int = 3) -> list[str]:
    """Envoltorio de compatibilidad (D4 del plan partir-api-main): «¿quisiste decir…?» sobre
    el documento ACTIVO (`services.lookup.suggest_ids`). Llamar bajo STATE_LOCK."""
    return suggest_ids(S.doc, missing, limit)


def _scene_filtered(ids, name, limit, offset) -> dict:
    """Brief LIGERO (sin mallas) filtrado por ids/nombres de grupo (`_expand_ids`) y/o
    substring del nombre, con paginación defensiva. Declara `total_filtrado`/`truncado`
    (sin caps silenciosos). Presupuesto: una lectura de rutina < ~10 KB a 1000 piezas."""
    items = list(S.doc.scene.items())
    if ids is not None:
        wanted = set(_expand_ids(ids) or [])
        items = [(fid, f) for fid, f in items if fid in wanted]
    if name:
        nl = name.lower()
        items = [(fid, f) for fid, f in items if nl in (f.name or "").lower()]
    total_filtrado = len(items)
    off = max(0, int(offset or 0))
    lim = 200 if limit is None else int(limit)
    page = items[off:] if lim < 0 else items[off:off + lim]
    return {
        "proyecto": S.doc.name,
        "configuraciones": sorted(S.doc.configurations.keys()),
        "puede_deshacer": S.doc.can_undo,
        "puede_rehacer": S.doc.can_redo,
        "total_solidos": len(S.doc.scene),
        "total_filtrado": total_filtrado,
        "offset": off,
        "solidos_mostrados": len(page),
        "truncado": off + len(page) < total_filtrado,
        "solidos": [_feature_brief(fid, f) for fid, f in page],
    }


# ------------------------------------------------------------------ endpoints
@app.get("/api/schemas")
def get_schemas(vista: str = Query("agente", pattern="^(agente|persona)$")) -> list[dict]:
    return command_schemas() if vista == "agente" else command_schemas_persona()


@app.get("/api/schemas/{command_type}")
def get_schema(command_type: str) -> dict:
    """JSON Schema de UN comando por type (evita volcar todos)."""
    res = command_schemas(command_type)
    if not res:
        raise HTTPException(status_code=404, detail=f"No existe el comando '{command_type}'")
    return res[0]


@app.get("/api/health")
def health() -> dict:
    """Salud de operación (V6.1): integridad del documento en memoria + estado de la
    capa de persistencia. Lectura pura bajo STATE_LOCK. ``ok`` es verde solo si NO hay
    violaciones de integridad (los 'degradado' no cuentan) NI error de arranque. Sin
    tool MCP: es telemetría de operación (la UI pinta un chip; V6.x si se pide agente)."""
    with STATE_LOCK:
        raw = S.doc.check_integrity()
        issues = [i for i in raw if not i.startswith("degradado")]
        degraded = [i for i in raw if i.startswith("degradado")]
        return {
            "ok": not issues and not S.startup_error,
            "issues": issues,
            "degraded": degraded,
            "suppressed_commands": getattr(S.doc, "regen_suppressed", []),
            "autosave_failed": S.autosave_error,
            "autosave_pending": _autosave_sched.pending(),  # V6.2d: hay un flush en la ventana de debounce
            "startup_error": S.startup_error,
            "project_id": S.project_id,
            "features": len(S.doc.scene),
            "commands": len(S.doc.commands),
        }


@app.get("/api/scene")
def get_scene(
    ids: str | None = None,
    name: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> dict:
    """Sin parámetros: escena COMPLETA con mallas (para el viewport) — compat byte-idéntico.
    Con `ids` (CSV de feature_ids o NOMBRES de grupo, vía `_expand_ids`), `name` (substring del
    nombre, case-insensitive), `limit` (default 200) u `offset`: BRIEF ligero SIN mallas,
    filtrado y paginado, con `total_solidos`/`total_filtrado`/`truncado`. La vía de escala del
    agente (V6.5a): ninguna lectura de rutina debe volcar la escena entera."""
    with STATE_LOCK:
        if ids is None and name is None and limit is None and not offset:
            return scene_payload()
        return _scene_filtered(ids, name, limit, offset)


@app.get("/api/scene/summary")
def get_scene_summary() -> dict:
    """Resumen agregado por GRUPO (V6.5a): n_piezas + masa + bbox conjunto por sub-ensamblaje
    de nivel superior (recursivo) + «(sin grupo)» + totales + variables. Punto de entrada del
    agente a un proyecto grande. Read-only."""
    with STATE_LOCK:
        return scene_summary_dict()


class SceneDeltaIn(BaseModel):
    # geometría que el cliente YA tiene: rev por feature + claves de definición conocidas +
    # el epoch del proceso con el que las obtuvo (V6.2e Fix 2)
    revs: dict[str, int] = {}
    defs: list[str] = []
    epoch: str | None = None


@app.post("/api/scene/delta")
def get_scene_delta(body: SceneDeltaIn) -> dict:
    """Escena en forma DELTA (V6.2b): mismo shape que GET /api/scene, pero las features
    cuya geometría no cambió respecto a lo que declara el cliente van con ``mesh=null`` +
    ``same=true`` y sin re-enviar sus definiciones. Lo usa el refresh por WebSocket (los
    metadatos —color/visibilidad/grupo— siempre llegan). Si el ``epoch`` del cliente no
    coincide con el del PROCESO (restart del API → los revs renacieron), se ignora ``known``
    y se devuelve el payload COMPLETO con el epoch nuevo (V6.2e Fix 2)."""
    with STATE_LOCK:
        known = None if body.epoch != SCENE_EPOCH else {"revs": body.revs, "defs": body.defs}
        return scene_payload(known=known)


@app.get("/api/document")
def get_document() -> dict:
    with STATE_LOCK:
        return document_payload()


# memoria de sesión del agente IA (Document.agent_notes, persistida en el .apolo)
class AgentNoteIn(BaseModel):
    text: str


@app.get("/api/agent/notes")
def get_agent_notes() -> dict:
    with STATE_LOCK:
        return {"notes": list(S.doc.agent_notes)}


@app.post("/api/agent/notes")
def add_agent_note(body: AgentNoteIn) -> dict:
    with STATE_LOCK:
        S.doc.agent_notes.append(body.text)
        del S.doc.agent_notes[:-30]  # tope 30 (memoria acotada del agente)
        _autosave()
        return {"notes": list(S.doc.agent_notes)}


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


class VisibilityIn(BaseModel):
    visible: bool


@app.post("/api/features/{feature_id}/visibility")
def set_visibility(feature_id: str, body: VisibilityIn) -> dict:
    # devuelve el command_id afectado → el cliente MCP recorta el retorno a la pieza
    def run():
        S.doc.set_visibility(feature_id, body.visible)
        return S.doc.scene[feature_id].command_id
    return _state_or_error(run)


class BulkVisibilityIn(BaseModel):
    ids: list[str]
    visible: bool


@app.post("/api/features/visibility")
def set_visibility_bulk(body: BulkVisibilityIn) -> dict:
    """Visibilidad en lote (aislar / mostrar todo) en una sola llamada."""
    def run():
        for fid in body.ids:
            S.doc.set_visibility(fid, body.visible)
        return sorted({S.doc.scene[fid].command_id for fid in body.ids if fid in S.doc.scene})
    return _state_or_error(run)


class SketchGuideIn(BaseModel):
    guide: bool


@app.post("/api/features/{feature_id}/sketch-guide")
def set_sketch_guide(feature_id: str, body: SketchGuideIn) -> dict:
    """Marca/desmarca un sólido (y las piezas de su comando) como boceto-guía (blockout):
    geometría de intención excluida de BOM/masa/interferencia/FEA que el agente consume."""
    def run():
        S.doc.set_sketch_guide(feature_id, body.guide)
        return S.doc.scene[feature_id].command_id
    return _state_or_error(run)


@app.get("/api/features/{feature_id}/topology")
def get_feature_topology(
    feature_id: str, only: str | None = None, min_mm: float = 0.0
) -> dict:
    """Caras y aristas de un sólido con su geometría (tipo, centro, normal/eje,
    longitud, radio) para elegir el SELECTOR declarativo. Incluye las ANCLAS de conexión
    con nombre (V6.3b) para matear por `{"mode":"ancla","name":...}`. `only` acota a
    `caras`|`aristas`|`anclas`; `min_mm` omite aristas/caras menores (micro-fillets, taladros
    diminutos = el grueso del ruido en piezas mecanizadas). Read-only."""
    from apolo.kernel.topology import feature_topology

    with STATE_LOCK:
        feat = S.doc.scene.get(feature_id)
        if feat is None:
            raise _not_found(feature_id)
        topo = feature_topology(feat.shape, only=only, min_mm=min_mm)
        anchors = feat.anchors or {}
    out = {"feature_id": feature_id, "name": feat.name, **topo}
    if only in (None, "", "anclas"):  # anclas solo en la vista completa o si se piden
        out["anchors"] = anchors
    return out


@app.get("/api/groups")
def get_groups_endpoint() -> dict:
    """Grupos/sub-ensamblajes del documento (con members faltantes). Read-only."""
    with STATE_LOCK:
        return {"groups": groups_payload()}


@app.get("/api/mass-properties")
def mass_properties(ids: str | None = None) -> dict:
    """Masa, centro de gravedad y bbox por pieza y del conjunto. Sin `ids`
    (CSV) analiza todas las visibles; con ids las incluye aunque estén ocultas.
    Catálogo pesa por ficha; a-medida por volumen × densidad. Read-only."""
    from apolo.library.engineering.mass import scene_mass_properties

    wanted = [s.strip() for s in ids.split(",") if s.strip()] if ids else None
    with STATE_LOCK:
        try:
            return scene_mass_properties(S.doc.scene, ids=wanted)
        except KeyError as exc:
            raise _not_found(exc.args[0]) from exc


class MeasureIn(BaseModel):
    a: str
    b: str
    face_a: dict | None = None  # selector de cara opcional para medir contra UNA cara de a
    face_b: dict | None = None


@app.post("/api/measure")
def measure_endpoint(body: MeasureIn) -> dict:
    """Distancia mínima (mm) y puntos más cercanos entre los sólidos a y b. Con face_a/face_b
    (selector declarativo) mide contra una cara concreta. Read-only."""
    from apolo.kernel.measure import measure_distance
    from apolo.kernel.selectors import SelectorError, resolve_faces

    with STATE_LOCK:
        fa = S.doc.scene.get(body.a)
        fb = S.doc.scene.get(body.b)
        if fa is None or fb is None:
            raise _not_found(body.a if fa is None else body.b)
        sa, sb = fa.shape, fb.shape
        try:
            if body.face_a:
                sa = resolve_faces(sa, body.face_a)[0]
            if body.face_b:
                sb = resolve_faces(sb, body.face_b)[0]
        except (SelectorError, IndexError) as exc:
            raise HTTPException(status_code=400, detail=f"Selector de cara inválido: {exc}") from exc
        try:
            res = measure_distance(sa, sb)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"a": body.a, "b": body.b, **res}


@app.get("/api/near")
def near_endpoint(
    point: str | None = None,
    feature: str | None = None,
    box: str | None = None,
    radius: float = 50.0,
    limit: int = 20,
) -> dict:
    """Features cercanas por caja envolvente, ordenadas de más cerca a más lejos (V6.5b).
    Exactamente UNO de: `point` (JSON [x,y,z] — «¿qué hay por aquí?»), `feature` (id —
    «¿qué rodea a X?», excluyéndolo) o `box` (JSON [[min],[max]] — «¿qué hay en esta región?»).
    `radius` (mm) + `limit`. Barrido O(n) sobre AABBs. Read-only."""
    from apolo.kernel.measure import features_near, features_near_box, features_near_feature

    dados = [k for k, v in (("point", point), ("feature", feature), ("box", box)) if v is not None]
    if len(dados) != 1:
        raise HTTPException(
            status_code=400, detail="Da EXACTAMENTE uno de: point, feature, box"
        )
    lim = limit if limit and limit > 0 else None
    with STATE_LOCK:
        if feature is not None:
            if feature not in S.doc.scene:
                raise _not_found(feature)
            cercanas = features_near_feature(S.doc.scene, feature, radius, limit=lim)
            modo = {"feature": feature}
        elif box is not None:
            try:
                bx = json.loads(box)
                assert (isinstance(bx, (list, tuple)) and len(bx) == 2
                        and all(len(p) == 3 for p in bx))
            except Exception as exc:
                raise HTTPException(
                    status_code=400, detail=f"box debe ser JSON [[min_x,min_y,min_z],[max...]]: {exc}"
                ) from exc
            cercanas = features_near_box(S.doc.scene, bx, radius, limit=lim)
            modo = {"box": bx}
        else:
            try:
                pt = json.loads(point)
                assert isinstance(pt, (list, tuple)) and len(pt) == 3
            except Exception as exc:
                raise HTTPException(
                    status_code=400, detail=f"point debe ser JSON [x,y,z]: {exc}"
                ) from exc
            cercanas = features_near(S.doc.scene, pt, radius, limit=lim)
            modo = {"point": pt}
    return {**modo, "radius": radius, "cercanas": cercanas}


@app.get("/api/pick")
def pick_endpoint(
    u: float,
    v: float,
    view: str = "iso",
    fit: str | None = None,
    zoom: float = 1.0,
    azimuth: float | None = None,
    elevation: float | None = None,
    isolate: str | None = None,
    section: str | None = None,
    roll: float = 0.0,
    pan: str | None = None,
) -> dict:
    """Píxel→3D: para el punto (u,v) NORMALIZADO [0,1] de un render (vista `view`, opcionalmente a
    ÁNGULO LIBRE `azimuth`/`elevation`, `roll`, `pan`), devuelve la feature/cara cuyo centro proyectado
    queda más cerca (snap a geometría). Usa la misma cámara que el render VTK (orto, proporciones reales).
    Pasa los MISMOS view/azimuth/elevation/roll/pan/fit/zoom/isolate/section que usaste en el render: con
    `isolate` (CSV de ids) el pick solo considera esas piezas y con `section` ∈ {x,y,z} las recorta
    igual que la foto → coherencia render↔pick. Read-only."""
    from apolo.kernel.pick import pick_point

    fit_ids = _expand_ids(fit)  # acepta NOMBRES de grupo (V5.2)
    isolate_ids = _expand_ids(isolate)
    pan_xy = None
    if pan:
        try:
            pan_xy = [float(s) for s in pan.split(",")]
            assert len(pan_xy) == 2
        except Exception as exc:
            raise HTTPException(status_code=400, detail="pan debe ser 'px,py' (dos números)") from exc
    with STATE_LOCK:
        try:
            return pick_point(
                S.doc.scene, view, u, v, fit_ids=fit_ids, zoom=zoom,
                azimuth=azimuth, elevation=elevation, isolate=isolate_ids, section=section,
                roll=roll, pan=pan_xy,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


# ------------------------------------------------------------------ proyectos
@app.get("/api/projects")
def list_projects() -> list[dict]:
    return _store_required().list_projects()


class ProjectIn(BaseModel):
    name: str = "Sin título"
    template: str | None = None  # "transportador" | "brazo" | None


@app.post("/api/projects")
def create_project(body: ProjectIn) -> dict:
    store = _store_required()
    with _project_switch():  # V6.2e: flush del doc actual + swap ATÓMICO (sin corrupción cruzada)
        S.doc = Document(body.name)
        if body.template == "transportador":
            S.doc.execute("set_variable", {"name": "L", "expression": "2000"})
            S.doc.execute("create_conveyor", {"largo": "=L", "ancho": 600, "altura": 750, "paso": 100})
        elif body.template == "brazo":
            S.doc.execute("create_robot_arm", {"name": "Robot", "alcance": 700})
        S.project_id = store.create(S.doc)
        payload = scene_payload()
    WS.notify_changed()
    return payload


@app.post("/api/projects/{project_id}/open")
def open_project_by_id(project_id: int) -> dict:
    store = _store_required()
    with _project_switch():  # V6.2e: flush del doc actual + swap ATÓMICO (sin corrupción cruzada)
        try:
            S.doc = store.load(project_id, tolerant=True)  # suprime comandos rotos (schema drift)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DocumentError as exc:  # ZIP roto / no regenera: 400 claro (antes: 500 opaco)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        S.project_id = project_id
        payload = scene_payload()
        payload["briefing"] = _open_briefing()  # V6.5b: arranque de sesión en 1 llamada
    WS.notify_changed()
    return payload


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int) -> dict:
    store = _store_required()
    with STATE_LOCK:  # check + borrado atómicos: un open concurrente no lo activa entre medio
        if project_id == S.project_id:
            raise HTTPException(status_code=400, detail="No puedes borrar el proyecto abierto")
        store.delete(project_id)
    return {"ok": True}


@app.post("/api/projects/{project_id}/duplicate")
def duplicate_project(project_id: int) -> dict:
    new_id = _store_required().duplicate(project_id)
    return {"id": new_id}


class RenameIn(BaseModel):
    name: str


@app.patch("/api/projects/current")
def rename_project(body: RenameIn) -> dict:
    def run():
        S.doc.name = body.name.strip() or "Sin título"

    return _state_or_error(run)


class RevisionIn(BaseModel):
    note: str = ""


@app.post("/api/revisions")
def save_revision(body: RevisionIn) -> dict:
    store = _store_required()
    if S.project_id is None:
        raise HTTPException(status_code=400, detail="No hay proyecto abierto")
    _flush_autosave()  # V6.2d: el proyecto en disco al día antes de fijar la revisión
    with STATE_LOCK:
        rev_id = store.save_revision(S.project_id, S.doc, body.note)
    return {"id": rev_id}


@app.get("/api/revisions")
def list_revisions() -> list[dict]:
    store = _store_required()
    if S.project_id is None:
        return []
    return store.list_revisions(S.project_id)


@app.post("/api/revisions/{revision_id}/restore")
def restore_revision(revision_id: int) -> dict:
    store = _store_required()
    with _project_switch():  # V6.2e: flush del doc actual + swap ATÓMICO
        try:
            project_id, doc = store.load_revision(revision_id, tolerant=True)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        S.doc = doc
        S.project_id = project_id
        payload = scene_payload()
    _flush_autosave(force=True)  # persiste YA el doc restaurado (no esperar la ventana)
    WS.notify_changed()
    return payload


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


class ColorIn(BaseModel):
    color: str | None = None  # null = volver al color automático


@app.post("/api/features/{feature_id}/color")
def set_feature_color(feature_id: str, body: ColorIn) -> dict:
    return _state_or_error(lambda: S.doc.set_color(feature_id, body.color))


class BulkColorIn(BaseModel):
    ids: list[str]
    color: str | None = None  # null = volver al color automático


@app.post("/api/features/color")
def set_color_bulk(body: BulkColorIn) -> dict:
    """Color en LOTE (V6.8-A): valida TODOS los ids ANTES de tocar nada (uno
    inexistente → 404 con sugerencia y CERO efectos parciales) y aplica en una
    pasada — un solo autosave/notify en vez de N llamadas."""
    if not body.ids:
        raise HTTPException(status_code=400, detail="La lista 'ids' no puede estar vacía")

    def run():
        for fid in body.ids:
            if fid not in S.doc.scene:
                raise _not_found(fid)
        for fid in body.ids:
            S.doc.set_color(fid, body.color)
        return sorted({S.doc.scene[fid].command_id for fid in body.ids})

    return _state_or_error(run)


class MaterialIn(BaseModel):
    material: str | None = None  # null = volver al material automático (heurística)


@app.post("/api/features/{feature_id}/material")
def set_feature_material(feature_id: str, body: MaterialIn) -> dict:
    def run():
        S.doc.set_material(feature_id, body.material)
        return S.doc.scene[feature_id].command_id
    return _state_or_error(run)


class BulkMaterialIn(BaseModel):
    ids: list[str]
    material: str | None = None  # null = volver al material automático (heurística)


@app.post("/api/features/material")
def set_material_bulk(body: BulkMaterialIn) -> dict:
    """Material en LOTE (V6.8-A) — mismo contrato que el color bulk: validar
    todo, aplicar todo, o 404 sin efectos parciales."""
    if not body.ids:
        raise HTTPException(status_code=400, detail="La lista 'ids' no puede estar vacía")

    def run():
        for fid in body.ids:
            if fid not in S.doc.scene:
                raise _not_found(fid)
        for fid in body.ids:
            S.doc.set_material(fid, body.material)
        return sorted({S.doc.scene[fid].command_id for fid in body.ids})

    return _state_or_error(run)


class VerticalIn(BaseModel):
    vertical: str  # 'metalmecanica' | 'carpinteria'


@app.post("/api/vertical")
def set_project_vertical(body: VerticalIn) -> dict:
    return _state_or_error(lambda: S.doc.set_vertical(body.vertical))


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


# -------------------------------------------------------------------- robótica
@app.get("/api/kinematics")
def get_kinematics() -> dict:
    from apolo.robotics import joints_payload

    with STATE_LOCK:
        return joints_payload(S.doc)


def _remove_owner_command(items: dict, name: str, cmd_type: str, missing: str, foreign: str):
    """Borra el comando `cmd_type` que declaró `items[name]` (junta o mate). Corre DENTRO
    del closure de `_state_or_error`: buscar y borrar en UNA adquisición de STATE_LOCK
    (antes la búsqueda en el log iba fuera → TOCTOU con una mutación concurrente)."""
    item = items.get(name)
    if item is None:
        raise HTTPException(status_code=404, detail=missing)
    cmd = next((c for c in S.doc.commands if c["id"] == item["command_id"]), None)
    if cmd is None or cmd["type"] != cmd_type:
        raise HTTPException(status_code=400, detail=foreign)
    return S.doc.remove_commands([item["command_id"]])


@app.delete("/api/joints/{name}")
def delete_joint(name: str) -> dict:
    return _state_or_error(lambda: _remove_owner_command(
        S.doc.joints, name, "add_joint", f"No existe la junta '{name}'",
        "Esta junta pertenece a una plantilla (p. ej. un brazo): edita o elimina su comando"))


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


# --------------------------------------------------------------- motion study
class MotionIn(BaseModel):
    name: str
    keyframes: list[dict] = []


class MotionDeleteIn(BaseModel):
    name: str


class ScanIn(BaseModel):
    name: str
    steps: int = 24


def _motion_studies() -> list[dict]:
    from apolo.robotics.motion import duration

    return [
        {"name": n, "keyframes": kfs, "duration": duration(kfs)}
        for n, kfs in sorted(S.doc.motion.items())
    ]


@app.get("/api/motion")
def get_motion() -> dict:
    with STATE_LOCK:
        return {"studies": _motion_studies()}


@app.put("/api/motion")
def put_motion(body: MotionIn) -> dict:
    with STATE_LOCK:
        try:
            S.doc.set_motion(body.name, body.keyframes)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _autosave()
        return {"ok": True, "studies": _motion_studies()}


@app.delete("/api/motion")
def delete_motion(body: MotionDeleteIn) -> dict:
    with STATE_LOCK:
        S.doc.delete_motion(body.name)
        _autosave()
        return {"ok": True, "studies": _motion_studies()}


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


def _motion_values_or_400(name: str, kfs: list[dict]) -> None:
    """Estudio persistido sin ningún 'values' (formato viejo/mal formado): mejor un 400
    accionable que 'reproducir' un recorrido que no mueve ninguna junta."""
    if kfs and not any(k.get("values") for k in kfs):
        raise HTTPException(
            status_code=400,
            detail=(
                f"El estudio '{name}' no tiene valores de junta en ningún fotograma — "
                'formato: {"t": segundos, "values": {junta: valor}}. Reescríbelo con '
                "PUT /api/motion."
            ),
        )


@app.post("/api/motion/scan")
def scan_motion(body: ScanIn) -> dict:
    from apolo.robotics.motion import scan_collisions

    with STATE_LOCK:
        kfs = S.doc.motion.get(body.name, [])
        _motion_values_or_400(body.name, kfs)
        return {"colisiones": scan_collisions(S.doc, kfs, body.steps)}


class MotionGifIn(BaseModel):
    name: str
    steps: int = 48          # intervalos del recorrido (steps+1 fotogramas)
    fps: int = 12
    pingpong: bool = False   # añade la vuelta → el bucle no salta al reiniciar
    view: str = "iso"
    azimuth: float | None = None
    elevation: float | None = None
    zoom: float = 1.0
    size_px: int = 720
    edges: bool = True


@app.post("/api/motion.gif")
def motion_gif(body: MotionGifIn) -> Response:
    """GIF animado de un estudio de movimiento CON NOMBRE: interpola las juntas a lo largo
    del recorrido y pinta cada fotograma con el MISMO motor VTK que `render_view`, con la
    cámara FIJA a todo el recorrido (si no, el encuadre 'respira' al moverse el mecanismo).
    Espejo de `/api/physics/drop.gif` pero para cinemática, no para física."""
    from apolo.robotics.anim import extract_motion_frames, render_motion_gif

    with STATE_LOCK:  # FASE OCCT: FK + teselado → snapshots de datos PUROS
        kfs = S.doc.motion.get(body.name)
        if not kfs:
            disponibles = ", ".join(sorted(S.doc.motion)) or "ninguno"
            raise HTTPException(
                status_code=404,
                detail=f"No existe el estudio de movimiento '{body.name}' (hay: {disponibles})",
            )
        _motion_values_or_400(body.name, kfs)
        try:
            snaps = extract_motion_frames(
                S.doc, kfs, steps=body.steps, pingpong=body.pingpong,
                view=body.view, azimuth=body.azimuth, elevation=body.elevation,
                zoom=body.zoom, size_px=body.size_px, colors=_feature_colors(),
                edges=body.edges,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    # FUERA de STATE_LOCK: el bucle VTK (lo lento) corre bajo RENDER_LOCK
    try:
        gif = render_motion_gif(snaps, fps=body.fps)
    except RuntimeError as exc:  # sin Pillow
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL u otro fallo VTK
        raise HTTPException(status_code=503, detail=f"El render VTK falló: {exc}") from exc
    return Response(content=gif, media_type="image/gif")


def _robot_export(builder) -> bytes:
    with STATE_LOCK:
        try:
            return builder(S.doc)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/export/urdf")
def export_urdf() -> Response:
    from apolo.robotics import export_urdf_zip

    data = _robot_export(export_urdf_zip)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "robot"}-urdf.zip"'},
    )


@app.get("/api/export/sdf")
def export_sdf() -> Response:
    from apolo.robotics import export_sdf_zip

    data = _robot_export(export_sdf_zip)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "robot"}-sdf.zip"'},
    )


class SketchIn(BaseModel):
    sketch: dict


@app.post("/api/sketch/solve")
def solve_sketch_endpoint(body: SketchIn) -> dict:
    from apolo.kernel.sketch_solver import SketchError, solve_sketch

    try:
        return solve_sketch(body.sketch)
    except SketchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class SketchDragIn(BaseModel):
    """Arrastre de un punto del croquis (V6.6 A): el punto va al cursor y el croquis se
    re-resuelve cumpliendo sus restricciones DURAS."""
    sketch: dict
    point_id: str
    target_xy: list[float]


@app.post("/api/sketch/drag")
def drag_sketch_endpoint(body: SketchDragIn) -> dict:
    """Re-resuelve el croquis con `point_id` SEMBRADO en `target_xy` — READ-ONLY (no
    persiste: es el preview que la UI pinta durante el arrastre).

    Soft-constraint por SIEMBRA, no por peso: el punto arrastrado entra al solver en la
    posición del cursor y las restricciones DURAS mandan; lo que queda libre se mantiene
    cerca del boceto (la regularización del motor). Funciona igual en los dos motores
    —planegcs y scipy— porque no toca sus internos; a cambio, no es el DragPoint de
    PlaneGCS: con dof=0 el croquis NO se deforma y el punto vuelve a su sitio, que es el
    comportamiento correcto y así se declara en `movido_mm`."""
    from apolo.kernel.sketch_solver import SketchError, solve_sketch

    if body.point_id not in (body.sketch.get("points") or {}):
        raise HTTPException(status_code=404,
                            detail=f"El croquis no tiene el punto '{body.point_id}'")
    if len(body.target_xy) < 2:
        raise HTTPException(status_code=400, detail="target_xy = [x, y]")
    tx, ty = float(body.target_xy[0]), float(body.target_xy[1])
    semilla = {**body.sketch, "points": {**body.sketch["points"], body.point_id: [tx, ty]}}
    try:
        solved = solve_sketch(semilla)
    except SketchError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    px, py = solved["points"][body.point_id][:2]
    solved["movido_mm"] = round(((px - tx) ** 2 + (py - ty) ** 2) ** 0.5, 4)
    solved["sigue_al_cursor"] = solved["movido_mm"] <= 1e-3
    return solved


class ScriptTestIn(BaseModel):
    code: str


@app.post("/api/script/test")
def test_script_endpoint(body: ScriptTestIn) -> dict:
    """Dry-run de un script build123d: lo ejecuta en el sandbox y devuelve volumen/bbox
    SIN tocar el documento. Para que el agente itere sin crear/deshacer features."""
    from apolo.kernel import bbox_payload
    from apolo.sandbox import ScriptError, run_script_to_shape

    with STATE_LOCK:
        variables = dict(S.doc.variables_resolved)
    try:
        shape = run_script_to_shape(body.code, variables)
        return {"ok": True, "volume_mm3": round(float(shape.volume), 1), "bbox": bbox_payload(shape)}
    except ScriptError as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/render.png")
def render_png(
    view: str = "iso",
    highlight: str | None = None,
    show_axes: bool = False,
    show_bbox: bool = False,
    joints: str | None = None,
    fit: str | None = None,
    zoom: float = 1.0,
    proportional: bool = False,
    views: str | None = None,
    labels: bool = False,
    section: str | None = None,
    shade: bool = False,
    isolate: str | None = None,
    azimuth: float | None = None,
    elevation: float | None = None,
    vtk_only: bool = False,
    measure: str | None = None,
    edges: bool = True,
    xray: bool = False,
    roll: float = 0.0,
    pan: str | None = None,
) -> Response:
    """Render de la escena. `highlight` = CSV de ids a resaltar (el resto se atenúa);
    `shade`=true usa el COLOR real por pieza (igual que el viewport web) en vez de la paleta
    por índice → render sombreado a color, más legible para distinguir piezas.
    `isolate` = CSV de ids para renderizar SOLO esas piezas (aislado real sobre una copia de la
    escena; NO toca la visibilidad del documento). Es la forma limpia de fotografiar una pieza:
    sin ocultar/restaurar nada en vivo. Respeta la visibilidad actual (una pieza oculta no aparece).
    `show_axes` dibuja los ejes del origen; `show_bbox` la caja envolvente.
    `joints` = JSON {junta: valor} para renderizar una POSE cinemática (resuelve las
    restricciones de riel y posa el mecanismo; read-only, no muta el documento).
    `fit` = CSV de ids para encuadrar la cámara en esas piezas (primer plano);
    `zoom`>1 acerca; `proportional`=true ciñe los ejes al bbox con proporciones reales
    (recomendado para máquinas largas y bajas). `views` = CSV de vistas (≥2) para componer
    varias en una imagen; `labels`=true rotula ids; `section` ∈ {x,y,z} corta para ver dentro.
    `azimuth`/`elevation` (grados) fijan la cámara a un ÁNGULO LIBRE (anulan el preset `view`;
    override parcial); aplican a vista única (con `views`/multivista se ignoran).
    `vtk_only`=true EXIGE el motor VTK (sombreado suave): ignora multivista/etiquetas y NO cae a
    matplotlib (sin OpenGL → 503 claro). Lo usa el tool MCP `render_view` para garantizar capturas
    limpias VTK; el resto de la API conserva matplotlib (fallback/multivista/labels/plomería).
    `measure`="a,b" (dos ids) dibuja una COTA (línea + "X mm" del gap mínimo OCCT entre las dos
    piezas) ENCIMA del render (solo vía VTK; en multivista/matplotlib se ignora).
    `xray`=true (rayos-X, solo VTK): lo NO resaltado se vuelve translúcido EN SU COLOR (no oculto)
    para ver una pieza interna en su contexto sin cortar; el vidrio siempre sale translúcido.
    `labels`=true rotula el id de cada pieza sobre el render (VTK billboard en vista única; matplotlib
    en multivista). `roll` (grados) gira la cámara sobre su eje de visión; `pan`="px,py" desplaza el
    encuadre en el plano de vista (fracción de la semialtura; +px→derecha, +py→arriba) — ambos solo
    vía VTK (vista única)."""
    from apolo.kernel.render import render_scene_png

    highlight_ids = _expand_ids(highlight)  # acepta NOMBRES de grupo (V5.2)
    fit_ids = _expand_ids(fit)
    isolate_ids = _expand_ids(isolate)
    view_list = [s.strip() for s in views.split(",") if s.strip()] if views else None
    pan_xy = None
    if pan:
        try:
            pan_xy = [float(s) for s in pan.split(",")]
            assert len(pan_xy) == 2
        except Exception as exc:
            raise HTTPException(status_code=400, detail="pan debe ser 'px,py' (dos números)") from exc
    if vtk_only and view_list:
        raise HTTPException(status_code=400, detail="vtk_only no soporta multivista (views); usa matplotlib o llamadas por vista")
    with STATE_LOCK:
        scene = S.doc.scene
        if isolate_ids:
            scene = {fid: S.doc.scene[fid] for fid in isolate_ids if fid in S.doc.scene}
            if not scene:
                raise HTTPException(status_code=400, detail="isolate: ningún id existe en la escena")
        override = None
        if joints:
            try:
                vals = json.loads(joints)
                assert isinstance(vals, dict)
                vals = {k: float(v) for k, v in vals.items()}
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"joints debe ser JSON {{junta: valor}}: {exc}") from exc
            from apolo.assembly.constraints import solve_constraints
            from apolo.robotics.pose import posed_shapes

            vals = solve_constraints(S.doc.joints, S.doc.constraints, vals)
            override, _ = posed_shapes(S.doc, vals)
        # COTA: distancia mínima entre dos piezas → la dibuja la vía VTK encima de la geometría.
        # Usa las shapes RENDERIZADAS (override si hay pose) para que coincida con lo que se ve.
        dimension = None
        if measure:
            from apolo.kernel.measure import measure_distance

            parts = [s.strip() for s in measure.split(",") if s.strip()]
            if len(parts) != 2:
                raise HTTPException(status_code=400, detail="measure: pasa exactamente dos ids 'a,b'")
            a_id, b_id = parts
            fa, fb = S.doc.scene.get(a_id), S.doc.scene.get(b_id)
            if fa is None or fb is None:
                missing = a_id if fa is None else b_id
                raise HTTPException(status_code=404, detail=f"measure: no existe el sólido '{missing}'")
            sa = override.get(a_id, fa.shape) if override else fa.shape
            sb = override.get(b_id, fb.shape) if override else fb.shape
            try:
                m = measure_distance(sa, sb)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            dimension = {"p1": m["punto_a"], "p2": m["punto_b"], "label": f"{m['dist_mm']:g} mm"}
        # Dos-locks del render (V6.2c): bajo STATE_LOCK solo se EXTRAE la geometría (teselado
        # con caché) a un snapshot de datos PUROS; el render VTK (depth-peeling/FXAA, lo lento)
        # corre FUERA del lock → una foto no congela las mutaciones. SOLO la MULTIVISTA (views) o
        # un fallo de VTK (sin OpenGL) → matplotlib. vtk_only=true (tool MCP render_view): EXIGE
        # VTK y NO cae a matplotlib (si no hay OpenGL → 503 claro, no una imagen con cuadrícula).
        feat_colors = _feature_colors()
        snapshot = None
        if (vtk_only or shade) and not view_list:
            try:
                from apolo.kernel.render_vtk import extract_render_scene

                snapshot = extract_render_scene(
                    scene, view,
                    highlight_ids=highlight_ids, shapes_override=override,
                    fit_ids=fit_ids, zoom=zoom, section=section,
                    show_axes=show_axes, show_bbox=show_bbox, colors=feat_colors,
                    ignore_visibility=bool(isolate_ids),
                    azimuth=azimuth, elevation=elevation, dimension=dimension, edges=edges,
                    xray=xray, labels=labels, roll=roll, pan=pan_xy,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
    # FUERA de STATE_LOCK: render VTK (bajo RENDER_LOCK) desde el snapshot de datos puros
    png = None
    if snapshot is not None:
        try:
            from apolo.kernel.render_vtk import RENDER_LOCK, render_snapshot_vtk

            with RENDER_LOCK:
                png = render_snapshot_vtk(snapshot)
        except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL u otro fallo VTK
            if vtk_only:
                raise HTTPException(
                    status_code=503,
                    detail=f"Render VTK no disponible (¿sin contexto OpenGL?): {exc}",
                ) from exc
            import logging

            logging.getLogger("uvicorn.error").warning(
                "VTK render falló; usando matplotlib", exc_info=True
            )
            png = None
    if png is None:  # matplotlib (multivista/fallback): tesela dentro → bajo STATE_LOCK
        with STATE_LOCK:
            try:
                png = render_scene_png(
                    scene, view,
                    highlight_ids=highlight_ids, show_axes=show_axes, show_bbox=show_bbox,
                    shapes_override=override, fit_ids=fit_ids, zoom=zoom, proportional=proportional,
                    views=view_list, labels=labels, section=section,
                    colors=feat_colors if shade else None,
                    ignore_visibility=bool(isolate_ids),
                    azimuth=azimuth, elevation=elevation, roll=roll,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=png, media_type="image/png")


# --------------------------------------------------------- expresiones (read-only)
@app.get("/api/resolve-expression")
def resolve_expression_endpoint(expr: str) -> dict:
    """Evalúa una expresión aritmética contra las variables del proyecto. No muta nada."""
    from apolo.commands.expressions import ExpressionError, eval_expression

    with STATE_LOCK:
        variables = dict(S.doc.variables_resolved)
    try:
        value = eval_expression(expr, variables)
        return {"ok": True, "value": round(float(value), 9), "expression": expr}
    except ExpressionError as exc:
        return {"ok": False, "error": str(exc), "expression": expr}


@app.get("/api/expression-grammar")
def expression_grammar() -> dict:
    """Gramática permitida en campos '=expr': funciones, constantes, operadores y
    las variables del proyecto disponibles."""
    from apolo.commands.expressions import ALLOWED_CONSTANTS, ALLOWED_FUNCS

    with STATE_LOCK:
        project_vars = sorted(S.doc.variables_resolved)
    return {
        "functions": sorted(ALLOWED_FUNCS),
        "constants": sorted(ALLOWED_CONSTANTS),
        "operators": ["+", "-", "*", "/", "//", "%", "**"],
        "unary": ["+", "-"],
        "comparators": ["<", "<=", ">", ">=", "==", "!="],
        "conditionals": ["a if cond else b", "and", "or"],
        "variables": project_vars,
        "note": ("Ángulos en grados (sin/cos/tan). Prefijo '=' en campos numéricos. "
                 "Condicionales para tablas de diseño: '=3 if largo>3500 else 2' (la rama "
                 "no tomada no se evalúa). 'and'/'or' colapsan a 1.0/0.0 (booleanos), NO al "
                 "operando: el idiom 'x or 5' NO devuelve 5. Sin texto, listas ni funciones propias."),
        "example": "=3 if largo_total > 3500 else 2",
    }


@app.get("/api/design-guidelines")
def design_guidelines_endpoint() -> dict:
    """Criterio de ingeniería que el agente debe aplicar POR DEFECTO al diseñar (sirve para
    máquinas, muebles, estructuras, cualquier objeto): decálogo con detalle, cómo verificar
    cada regla en Apolo, cuándo preguntar vs. asumir, y ejemplos. No depende del documento."""
    from apolo.design import design_guidelines

    return design_guidelines()


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


# --------------------------------------------------------------------- planos
def _sheet_model(sheet: str, hidden: bool, dims: str = "", section: bool = False, bom: bool = False):
    from apolo.drawing import compose_sheet

    dims_features = [s for s in dims.split(",") if s] or None
    with STATE_LOCK:
        try:
            return compose_sheet(
                S.doc.scene, sheet=sheet, include_hidden=hidden, project_name=S.doc.name,
                dims_features=dims_features, section=section, bom=bom, meta=_drawing_meta(),
                fasteners=S.doc.fasteners,  # V7.2 A: símbolos de soldadura ISO 2553 (no-op sin cordones)
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/drawing.svg")
def drawing_svg(sheet: str = "A3", hidden: bool = False, dims: str = "", section: bool = False, bom: bool = False) -> Response:
    from apolo.drawing import sheet_to_svg

    return Response(
        content=sheet_to_svg(_sheet_model(sheet, hidden, dims, section, bom)),
        media_type="image/svg+xml",
    )


@app.get("/api/drawing.dxf")
def drawing_dxf(sheet: str = "A3", hidden: bool = False, dims: str = "", section: bool = False, bom: bool = False) -> Response:
    from apolo.drawing import sheet_to_dxf

    return Response(
        content=sheet_to_dxf(_sheet_model(sheet, hidden, dims, section, bom)),
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "plano"}.dxf"'},
    )


def _sheetmetal_flat(feature_id: str):
    """Localiza el comando create_sheet_metal que generó la feature y devuelve su
    SheetModel desplegado (resolviendo expresiones del proyecto)."""
    from apolo.commands import resolve_params
    from apolo.commands.models import SheetMetalParams
    from apolo.library.sheetmetal import flat_pattern

    with STATE_LOCK:
        feat = S.doc.scene.get(feature_id)
        if feat is None:
            raise HTTPException(status_code=404, detail=f"No existe el sólido '{feature_id}'")
        cmd = next((c for c in S.doc.commands if c["id"] == feat.command_id), None)
        if cmd is None or cmd["type"] != "create_sheet_metal":
            raise HTTPException(status_code=400, detail=f"'{feature_id}' no es una chapa metálica")
        try:
            from apolo.library.catalog import CATALOG
            from apolo.library.materials import resolve_material
            from apolo.library.sheetmetal import flaps_from_specs, k_for_material

            p = SheetMetalParams.model_validate(resolve_params(cmd["params"], S.doc.variables_resolved))
            # K-factor: explícito gana; si no, por MATERIAL de la pieza (V5.5)
            k = p.k_factor if p.k_factor is not None else k_for_material(
                resolve_material(feat, CATALOG, S.doc.default_material())
            )
            return p.name, flat_pattern(
                p.name, p.ancho, p.fondo, p.espesor, p.lados,
                p.altura_pestana, p.angulo, p.radio, k,
                holes=[(h.x, h.y, h.d) for h in p.holes],
                flaps=flaps_from_specs(p.flaps),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/sheetmetal/{feature_id}/flat.svg")
def sheetmetal_flat_svg(feature_id: str) -> Response:
    from apolo.drawing import sheet_to_svg

    _, model = _sheetmetal_flat(feature_id)
    return Response(content=sheet_to_svg(model), media_type="image/svg+xml")


@app.get("/api/sheetmetal/{feature_id}/flat.dxf")
def sheetmetal_flat_dxf(feature_id: str) -> Response:
    from apolo.drawing import sheet_to_dxf

    name, model = _sheetmetal_flat(feature_id)
    return Response(
        content=sheet_to_dxf(model),
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{name or "chapa"}-flat.dxf"'},
    )


@app.get("/api/sheetmetal/{feature_id}/flat.dwg")
def sheetmetal_flat_dwg(feature_id: str) -> Response:
    """Desplegado en DWG (V5.9) — requiere ODA File Converter instalado."""
    from apolo.drawing import DwgError, sheet_to_dwg

    name, model = _sheetmetal_flat(feature_id)
    try:
        data = sheet_to_dwg(model)
    except DwgError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type="application/acad",
        headers={"Content-Disposition": f'attachment; filename="{name or "chapa"}-flat.dwg"'},
    )


@app.get("/api/drawing.pdf")
def drawing_pdf(sheet: str = "A3", hidden: bool = False, dims: str = "", section: bool = False, bom: bool = False) -> Response:
    from apolo.drawing import sheet_to_pdf

    return Response(
        content=sheet_to_pdf(_sheet_model(sheet, hidden, dims, section, bom)),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "plano"}.pdf"'},
    )


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


@app.get("/api/drawingset.pdf")
def drawingset_pdf(template: str = "generico", sheet: str = "A3", shaded: bool = False) -> Response:
    """Juego de planos en PDF MULTIPÁGINA: conjunto (con BOM) + 1 lámina por pieza acotada +
    cédula de corte/herraje. `template`: carpinteria/weldment/chapa/generico. `shaded`: el
    conjunto lleva isométrica SOMBREADA a color (estilo Inventor)."""
    from apolo.drawing import sheet_set, sheets_to_pdf

    with STATE_LOCK:
        try:
            pages = sheet_set(S.doc.scene, project_name=S.doc.name, template=template,
                              meta=_drawing_meta(), sheet=sheet, shaded=shaded,
                              colors=_feature_colors(), **sheet_set_maps(S.doc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=sheets_to_pdf(pages), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "juego"}-planos.pdf"'},
    )


@app.get("/api/drawingset.dwg")
def drawingset_dwg(template: str = "generico", sheet: str = "A3") -> Response:
    """Juego de planos en DWG (V5.9): como DWG no es multipágina, devuelve un ZIP con
    un DWG por lámina. Requiere ODA File Converter instalado."""
    import io as _io
    import zipfile

    from apolo.drawing import DwgError, sheet_set, sheet_to_dwg

    with STATE_LOCK:
        try:
            pages = sheet_set(S.doc.scene, project_name=S.doc.name, template=template,
                              meta=_drawing_meta(), sheet=sheet,
                              colors=_feature_colors(), **sheet_set_maps(S.doc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        base = (S.doc.name or "juego").replace("/", "-")
    buf = _io.BytesIO()
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, page in enumerate(pages, start=1):
                zf.writestr(f"{base}-hoja-{i:02d}.dwg", sheet_to_dwg(page))
    except DwgError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{base}-planos-dwg.zip"'},
    )


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


# ---------------------------------------- planos por INTENCIÓN (agente-nativo, Fase G)
class DrawingSpecIn(BaseModel):
    sheet: str = "A3"
    section: str = ""          # "x"/"y"/"z" o "" (sin corte)
    detail: dict | None = None  # {view,u,v,radius,scale}
    dims: list[str] = []        # ids a acotar (tamaño en planta)
    datum_dims: list[str] = []  # ids → cotas de posición desde la base (alzado)
    bom: bool = False
    isolate: list[str] = []     # solo estas piezas (aislado, sin tocar el documento)
    include_hidden: bool = False
    format: str = "pdf"         # pdf | svg | dxf
    meta: dict | None = None
    cutlist: bool = False       # tabla DESPIECE (L×A×E por tabla) en vez del BOM sin dimensiones
    member_detail: dict | None = None  # {member, pick:[t,w,l], locate:[ids], scale, name} → detalle de 1 tabla
    auto_dims: bool = False     # acota SOLO la posición de los agujeros (Fase 2)
    interface_dims: bool = False  # cotas de MONTAJE: pitch centro-a-centro del patrón de agujeros
    hardware: bool = False      # añade tabla CÉDULA DE HERRAJE bajo el DESPIECE (Fase 4)
    explode: dict | None = None  # {axis,factor} → VISTA EXPLOSIONADA (Fase 3)
    notes: list[str] = []        # bloque de NOTAS generales en la lámina (Fase 5)
    assembly_notes: list[str] | None = None  # NOTAS DE MONTAJE: null=off · []=auto del herraje · [..]=explícitas
    shaded: bool = False         # isométrica SOMBREADA a color (estilo Inventor)
    hole_fits: dict[str, str] = {}  # {"20": "H7"} Ø_nominal→clase ISO 286; se mergea SOBRE el mapa automático (V5.4)
    hole_threads: dict[str, str] = {}  # {"6.8": "M8"} Ø_broca→rosca; se mergea SOBRE el mapa automático (V5.7)


@app.get("/api/fits")
def get_fits(nominal: float, hole: str = "", shaft: str = "") -> dict:
    """Límites ISO 286 (V5.4): con `hole` y `shaft` devuelve el análisis del ajuste
    (juego/transición/apriete); con uno solo, sus límites. Read-only."""
    from apolo.library.engineering.fits import fit_check, fit_limits

    try:
        if hole and shaft:
            return fit_check(nominal, hole, shaft)
        if hole or shaft:
            return fit_limits(nominal, hole or shaft)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip("'\"")) from exc
    raise HTTPException(status_code=400, detail="Indica hole (H7) y/o shaft (g6)")


@app.get("/api/threads")
def get_threads(size: str) -> dict:
    """Ficha de una rosca métrica ISO 261/262 (V5.7): paso, broca de machuelado
    publicada, área resistente y norma. Read-only."""
    from apolo.library.engineering.threads import thread_spec

    try:
        return thread_spec(size)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip("'\"")) from exc


@app.post("/api/drawing/spec")
def drawing_spec(spec: DrawingSpecIn) -> Response:
    """Plano profesional por INTENCIÓN: una sola spec declara vistas/corte/detalle/cotas/
    BOM/aislado/cajetín y el motor lo compone. format = pdf|svg|dxf. Read-only (el aislado
    filtra la escena sin tocar la visibilidad del documento)."""
    from apolo.drawing import compose_sheet, sheet_to_dxf, sheet_to_pdf, sheet_to_svg

    with STATE_LOCK:
        scene = S.doc.scene
        if spec.isolate:
            iso = _expand_ids(spec.isolate) or []  # acepta NOMBRES de grupo (V5.2)
            scene = {fid: scene[fid] for fid in iso if fid in scene}
            if not scene:
                raise HTTPException(status_code=400, detail="isolate: ningún id existe en la escena")
        # el mapa de fits se construye desde la escena EFECTIVA (post-isolate): aislar un
        # solo eje muestra SU fit sin conflicto con otro Ø igual del resto (V7.2c)
        fits_map = _scene_fit_map(S.doc, scene)
        for k, v in (spec.hole_fits or {}).items():  # override del agente encima del auto
            try:
                fits_map[float(k)] = v
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"hole_fits: clave '{k}' no es un Ø numérico") from None
        threads_map = _hole_thread_map(S.doc)
        for k, v in (spec.hole_threads or {}).items():  # override espejo (V5.7)
            try:
                threads_map[float(k)] = v
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"hole_threads: clave '{k}' no es un Ø numérico") from None
        try:
            model = compose_sheet(
                scene, sheet=spec.sheet, include_hidden=spec.include_hidden, project_name=S.doc.name,
                dims_features=spec.dims or None, section=spec.section or False, bom=spec.bom,
                detail=spec.detail, datum_dims=spec.datum_dims or None,
                cutlist=spec.cutlist, member_detail=spec.member_detail,
                auto_dims=spec.auto_dims, interface_dims=spec.interface_dims,
                hardware=spec.hardware, explode=spec.explode,
                notes=spec.notes or None, assembly_notes=spec.assembly_notes,
                shaded=spec.shaded, colors=_feature_colors(),
                hole_fits=fits_map or None, hole_threads=threads_map or None,
                fasteners=S.doc.fasteners,  # V7.2 A: símbolos de soldadura ISO 2553 en el conjunto/GA
                meta={**_drawing_meta(), **(spec.meta or {})},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if spec.format == "svg":
        return Response(content=sheet_to_svg(model), media_type="image/svg+xml")
    if spec.format == "dxf":
        return Response(content=sheet_to_dxf(model), media_type="application/dxf",
                        headers={"Content-Disposition": "attachment; filename=plano.dxf"})
    if spec.format == "dwg":  # V5.9: DXF convertido con ODA File Converter
        from apolo.drawing import DwgError, sheet_to_dwg

        try:
            data = sheet_to_dwg(model)
        except DwgError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(content=data, media_type="application/acad",
                        headers={"Content-Disposition": "attachment; filename=plano.dwg"})
    return Response(content=sheet_to_pdf(model), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "plano"}.pdf"'})


# ----------------------------------------------------------------- export / io
@app.post("/api/import")
async def import_step_file(file: UploadFile, split: bool = False) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    name = (file.filename or "Importado").rsplit(".", 1)[0][:40]

    def run():
        digest = S.doc.add_attachment(data)
        try:
            S.doc.execute("import_step", {"attachment": digest, "name": name, "split": split})
        except Exception:
            S.doc.attachments.pop(digest, None)
            raise

    return _state_or_error(run)


@app.get("/api/export/step")
def export_step() -> FileResponse:
    with STATE_LOCK:
        shapes = [f.shape for f in S.doc.scene.values() if f.visible]
        if not shapes:
            raise HTTPException(status_code=400, detail="No hay sólidos visibles que exportar")
        tmp = Path(tempfile.mkstemp(suffix=".step")[1])
        export_step_file(shapes, str(tmp))
    return FileResponse(tmp, filename=f"{S.doc.name or 'modelo'}.step", media_type="model/step")


@app.get("/api/export/stl")
def export_stl_endpoint(tolerance: float = 0.5) -> FileResponse:
    """Exporta los sólidos VISIBLES como UN STL binario (malla; para impresión 3D /
    visores externos). `tolerance` = desviación máxima de teselado en mm. Read-only."""
    from build123d import Compound, export_stl

    with STATE_LOCK:
        shapes = [f.shape for f in S.doc.scene.values() if f.visible]
        if not shapes:
            raise HTTPException(status_code=400, detail="No hay sólidos visibles que exportar")
        tmp = Path(tempfile.mkstemp(suffix=".stl")[1])
        export_stl(Compound(children=shapes), str(tmp), tolerance=tolerance)
    return FileResponse(tmp, filename=f"{S.doc.name or 'modelo'}.stl", media_type="model/stl")


@app.get("/api/project/file")
def download_project() -> Response:
    with STATE_LOCK:
        content = S.doc.to_apolo_bytes()
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "proyecto"}.apolo"'},
    )


@app.post("/api/project/open")
async def open_project(file: UploadFile) -> dict:
    data = await file.read()
    with _project_switch():  # V6.2e: flush del doc actual + swap ATÓMICO
        try:
            S.doc = Document.from_apolo_bytes(data, tolerant=True)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # E2: un proyecto NUEVO en la BD — el siguiente autosave NO debe pisar el que
        # estaba abierto antes (sin esto, PROJECT_ID seguía apuntando al anterior)
        S.project_id = S.store.create(S.doc) if S.store is not None else None
        payload = scene_payload()
    WS.notify_changed()
    return payload


class NewProjectIn(BaseModel):
    name: str = "Sin título"


@app.post("/api/project/new")
def new_project(body: NewProjectIn) -> dict:
    with _project_switch():  # V6.2e: flush del doc actual + swap ATÓMICO
        S.doc = Document(body.name)
        S.project_id = S.store.create(S.doc) if S.store is not None else None  # E2: id propio
        payload = scene_payload()
    WS.notify_changed()
    return payload


# ----------------------------------------------------------------------- agente
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    messages: list[ChatMessage]
    auto: bool = False


@app.post("/api/agent/chat")
def agent_chat(body: ChatIn) -> StreamingResponse:
    messages = [m.model_dump() for m in body.messages]
    with STATE_LOCK:  # el chat queda atado al documento ACTIVO de este instante
        pid, doc = S.project_id, S.doc
    hooks = AgentHooks(alive=lambda: S.project_id == pid and S.doc is doc,  # revalidado bajo el lock
                       after_mutation=lambda: _autosave(), notify=lambda: WS.notify_changed())
    return StreamingResponse(
        chat_stream(doc, messages, auto=body.auto, hooks=hooks),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------- UI build
# `paths.ui_dist()` resuelve la UI empaquetada (instalación pip) o el build del
# checkout; None = sin bundle → la API sirve solo /api (headless, útil para MCP).
_ui_dist = _paths.ui_dist()
if _ui_dist is not None:
    app.mount("/", StaticFiles(directory=str(_ui_dist), html=True), name="ui")
