"""API de Genix Apolo CAD.

La UI y el agente IA son dos clientes de esta misma API: toda operación de
modelado entra por /api/commands (o /api/commands/batch para los lotes que
propone el agente).
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
import traceback
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apolo.agent import chat_stream
from apolo.commands import CommandError, command_schemas
from apolo.doc import Document, DocumentError
from apolo.kernel import bbox_payload, export_step_file, mesh_payload
from apolo.library import (
    bom_from_scene,
    bom_to_csv,
    catalog_payload,
    conveyor_engineering_check,
    interference_report,
)
from apolo.state import STATE_LOCK

from .errorlog import log_error, session_marker

app = FastAPI(title="Genix Apolo CAD", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DOC = Document()
PALETTE = ["#5b8def", "#46b58a", "#c77d4f", "#8e6fd8", "#d8a03a", "#5fa8c9", "#c75f7c"]

# multiproyecto: el almacén se inicializa en startup (los tests no ejecutan
# lifespan, así que no tocan la base de datos). Sin almacén no hay autosave.
STORE = None
PROJECT_ID: int | None = None

# Salud de operación (V6.1): último fallo de autosave (Fix D) y fallo de arranque con
# el proyecto reciente corrupto (Fix E). GET /api/health los expone; None = sano.
AUTOSAVE_ERROR: str | None = None
STARTUP_ERROR: str | None = None


# backoff del autosave: reintentos con espera TOTAL ≤0.6 s (bajo STATE_LOCK, pero solo
# se paga en el caso EXCEPCIONAL de fallo — el camino feliz guarda al primer intento).
_AUTOSAVE_RETRIES = (0.0, 0.1, 0.5)


def _autosave() -> None:
    """Autoguarda con reintentos. Éxito → limpia el flag AUTOSAVE_ERROR. Agotados los
    reintentos → deja el flag (el payload y un WS lo exponen: el cliente SE ENTERA de que
    el doc en memoria diverge de la BD) sin romper la operación en curso (Fix D)."""
    global AUTOSAVE_ERROR
    if STORE is None or PROJECT_ID is None:
        return
    last: Exception | None = None
    for delay in _AUTOSAVE_RETRIES:
        if delay:
            time.sleep(delay)
        try:
            STORE.save(PROJECT_ID, DOC)
            AUTOSAVE_ERROR = None
            return
        except Exception as exc:  # el autosave nunca debe romper la operación
            last = exc
    AUTOSAVE_ERROR = repr(last)
    log_error("backend.autosave", repr(last))
    WS.notify_changed({"type": "autosave_failed", "error": AUTOSAVE_ERROR})


# ------------------------------------------------------------------ websocket
class WsManager:
    def __init__(self) -> None:
        self.clients: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.clients:
            self.clients.remove(ws)

    async def _safe_send(self, ws: WebSocket, payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except Exception:
            self.disconnect(ws)  # cliente muerto: se desecha, no se reintenta

    def notify_changed(self, msg: dict | None = None) -> None:
        if not self.loop:
            return
        payload = msg or {"type": "document_changed"}
        for ws in list(self.clients):
            try:
                asyncio.run_coroutine_threadsafe(self._safe_send(ws, payload), self.loop)
            except Exception:
                self.disconnect(ws)  # ni siquiera se pudo programar el envío


WS = WsManager()


def initialize_store(db_path: str) -> None:
    """Inicializa el almacén y abre el proyecto reciente. Extraído del lifespan para
    testearlo SIN FastAPI (los tests no ejecutan el startup). Robustez (Fix E): el
    reciente se abre TOLERANTE (suprime comandos rotos en vez de negar la apertura); si
    ni así abre (ZIP roto), se deja STARTUP_ERROR + un doc VACÍO en memoria con
    PROJECT_ID=None (el autosave no-opea con None) y NO se crea un 'Sin título' que PISE
    al reciente como más nuevo. STORE.create solo cuando la BD está de verdad VACÍA."""
    global DOC, STORE, PROJECT_ID, STARTUP_ERROR

    from apolo.projects import ProjectStore

    STORE = ProjectStore(db_path)
    STARTUP_ERROR = None
    with STATE_LOCK:
        recent = STORE.most_recent_id()
        if recent is None:
            DOC = Document()
            PROJECT_ID = STORE.create(DOC)
            return
        try:
            DOC = STORE.load(recent, tolerant=True)
            PROJECT_ID = recent
        except Exception as exc:
            STARTUP_ERROR = f"No se pudo abrir el proyecto reciente {recent}: {exc!r}"
            log_error("backend.startup", STARTUP_ERROR)
            DOC = Document()
            PROJECT_ID = None  # el autosave no-opea → NO se sobrescribe el reciente corrupto


@app.on_event("startup")
async def _capture_loop() -> None:
    import os

    WS.loop = asyncio.get_running_loop()
    session_marker("Inicio de sesión del servidor")
    db_path = os.environ.get(
        "APOLO_DB", str(Path(__file__).resolve().parents[3] / "data" / "apolo.db")
    )
    initialize_store(db_path)


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


# ------------------------------------------------------------------- payloads
def variables_payload() -> list[dict]:
    defining: dict[str, str] = {}
    expressions: dict[str, str] = {}
    for cmd in DOC.commands:
        if cmd["type"] == "set_variable":
            defining[cmd["params"]["name"]] = cmd["id"]
            expressions[cmd["params"]["name"]] = cmd["params"]["expression"]
    return [
        {
            "name": name,
            "expression": expressions.get(name, ""),
            "value": DOC.variables_resolved.get(name),
            "command_id": cmd_id,
        }
        for name, cmd_id in defining.items()
    ]


def groups_payload() -> list[dict]:
    """Grupos/sub-ensamblajes con sus members faltantes (integridad tolerante)."""
    from apolo.assembly.groups import missing_members

    gone = missing_members(DOC.scene, DOC.groups)
    return [
        {**g, "missing_members": gone.get(g["name"], [])}
        for g in DOC.groups.values()
    ]


def document_payload() -> dict:
    return {
        "name": DOC.name,
        "commands": DOC.commands,
        "can_undo": DOC.can_undo,
        "can_redo": DOC.can_redo,
        "variables": variables_payload(),
        "configurations": sorted(DOC.configurations.keys()),
        "groups": groups_payload(),
        "project_id": PROJECT_ID,
        # robustez (V6.1): comandos suprimidos por una carga tolerante + estado del
        # autosave (None = sano). La UI pinta un chip cuando el disco no responde.
        "suppressed_commands": DOC.regen_suppressed,
        "autosave_failed": AUTOSAVE_ERROR,
    }


def _expand_ids(value) -> list[str] | None:
    """Normaliza un CSV/lista de ids expandiendo cualquier token que sea el NOMBRE de
    un GRUPO a sus feature_ids (recursivo con sub-grupos). Así isolate/highlight/fit
    aceptan sub-ensamblajes por nombre sin cambiar firmas."""
    from apolo.assembly.groups import group_features

    if value is None:
        return None
    tokens = ([s.strip() for s in value.split(",")] if isinstance(value, str) else
              [str(s).strip() for s in value])
    tokens = [t for t in tokens if t]
    if not tokens:
        return None
    out: list[str] = []
    with STATE_LOCK:
        for tok in tokens:
            if tok in DOC.groups:
                out.extend(group_features(DOC.scene, DOC.groups, tok, recursive=True))
            else:
                out.append(tok)
    # dedup conservando orden
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


_DEF_MESH_CACHE: dict[str, dict] = {}


def _definition_mesh(key: str) -> dict | None:
    from apolo.commands.registry import DEFINITIONS, touch_definition

    if key not in DEFINITIONS:
        return None
    touch_definition(key)  # LRU: renderizar una definición la protege de la evicción (Fix A)
    if key not in _DEF_MESH_CACHE:
        if len(_DEF_MESH_CACHE) > 128:
            _DEF_MESH_CACHE.clear()
        _DEF_MESH_CACHE[key] = mesh_payload(DEFINITIONS[key])
    return _DEF_MESH_CACHE[key]


# Caché de datos de render por IDENTIDAD del shape OCCT (mesh/volumen/bbox). El
# regenerate incremental conserva la MISMA referencia de shape para las features que
# no cambiaron, así que solo se re-tesela/recalcula lo que cambió. La referencia fuerte
# al shape evita reutilización de id mientras está en caché.
_SHAPE_CACHE: dict[int, tuple] = {}
_SHAPE_CACHE_CAP = 2048


def _cached_render(shape, want_mesh: bool) -> dict:
    key = id(shape)
    hit = _SHAPE_CACHE.get(key)
    if hit is None or hit[0] is not shape:
        if len(_SHAPE_CACHE) > _SHAPE_CACHE_CAP:
            _SHAPE_CACHE.clear()
        hit = (shape, {"volume": round(shape.volume, 1), "bbox": bbox_payload(shape)})
        _SHAPE_CACHE[key] = hit
    data = hit[1]
    if want_mesh and "mesh" not in data:
        data["mesh"] = mesh_payload(shape)
    return data


def scene_payload() -> dict:
    from apolo.kernel.matrix import to_column_major16

    features = []
    definitions: dict[str, dict] = {}
    cmd_types = {c["id"]: c["type"] for c in DOC.commands}
    for i, feat in enumerate(DOC.scene.values()):
        def_mesh = _definition_mesh(feat.mesh_key) if feat.mesh_key and feat.matrix else None
        rd = _cached_render(feat.shape, want_mesh=def_mesh is None)  # mesh solo si no es instancia
        entry = {
            "id": feat.id,
            "name": feat.name,
            "visible": feat.visible,
            "color": DOC.colors.get(feat.id) or PALETTE[i % len(PALETTE)],
            "volume_mm3": rd["volume"],
            "bbox": rd["bbox"],
            "mesh": None,
            "mesh_key": None,
            "matrix": None,
            "command_id": feat.command_id,
            "command_type": cmd_types.get(feat.command_id),
            "component": feat.component,
            "cut_length": feat.cut_length,
            "group": feat.group,
        }
        if def_mesh is not None:
            definitions[feat.mesh_key] = def_mesh
            entry["mesh_key"] = feat.mesh_key
            entry["matrix"] = to_column_major16(feat.matrix)
        else:
            entry["mesh"] = rd["mesh"]
        features.append(entry)
    return {
        "features": features,
        "definitions": definitions,
        "document": document_payload(),
        "total_features": len(features),
    }


def _normalize_affected(v) -> list[str]:
    """Normaliza el retorno de una mutación a una lista de command_ids afectados.
    execute→str, execute_many/edit→list|str, lambdas sin retorno→[]."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, (list, tuple)):
        return [str(x) for x in v if x is not None]
    return []


def _state_or_error(fn):
    with STATE_LOCK:
        try:
            affected = fn()
        except (CommandError, DocumentError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _autosave()
        payload = scene_payload()
    payload["affected_command_ids"] = _normalize_affected(affected)
    # avisar DESPUÉS de construir el payload: el refresh de los clientes no
    # compite con esta petición por las formas OCCT
    WS.notify_changed()
    return payload


# ------------------------------------------------------------------ endpoints
@app.get("/api/schemas")
def get_schemas() -> list[dict]:
    return command_schemas()


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
        raw = DOC.check_integrity()
        issues = [i for i in raw if not i.startswith("degradado")]
        degraded = [i for i in raw if i.startswith("degradado")]
        return {
            "ok": not issues and not STARTUP_ERROR,
            "issues": issues,
            "degraded": degraded,
            "suppressed_commands": getattr(DOC, "regen_suppressed", []),
            "autosave_failed": AUTOSAVE_ERROR,
            "startup_error": STARTUP_ERROR,
            "project_id": PROJECT_ID,
            "features": len(DOC.scene),
            "commands": len(DOC.commands),
        }


@app.get("/api/scene")
def get_scene() -> dict:
    with STATE_LOCK:
        return scene_payload()


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
        return {"notes": list(DOC.agent_notes)}


@app.post("/api/agent/notes")
def add_agent_note(body: AgentNoteIn) -> dict:
    with STATE_LOCK:
        DOC.agent_notes.append(body.text)
        del DOC.agent_notes[:-30]  # tope 30 (memoria acotada del agente)
        _autosave()
        return {"notes": list(DOC.agent_notes)}


class CommandIn(BaseModel):
    type: str
    params: dict = {}


def _materialize_insert_project(cmd_type: str, params: dict) -> dict:
    """V5.2b: convierte project_id → attachment embebido (snapshot .apolo) para
    insert_project. Solo la capa API conoce el ProjectStore (el executor es puro y
    el .apolo del layout queda autocontenido). Content-addressed: re-materializar
    sin cambios en el origen reusa el mismo hash (regenerate no-op). Llamar SIEMPRE
    bajo STATE_LOCK (muta DOC.attachments)."""
    if cmd_type != "insert_project" or not isinstance(params, dict) or params.get("attachment"):
        return params
    pid = params.get("project_id")
    if pid is None:
        return params  # el validador pydantic del comando dará el error claro
    if STORE is None:
        raise HTTPException(
            status_code=400,
            detail="No hay almacén de proyectos: insert_project necesita la API con startup",
        )
    if PROJECT_ID is not None and int(pid) == PROJECT_ID:
        raise HTTPException(
            status_code=400, detail="Un proyecto no puede instanciarse dentro de sí mismo"
        )
    try:
        data = STORE.load_bytes(int(pid))
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**params, "attachment": DOC.add_attachment(data)}


def _materialize_edit(command_id: str, params: dict, merge: bool) -> dict:
    """Pre-materializa un edit sobre un insert_project (refresh: {'attachment': ''}).
    Devuelve los params COMPLETOS ya fusionados y materializados; re-fusionarlos
    después (merge) es idempotente."""
    cmd = next((c for c in DOC.commands if c["id"] == command_id), None)
    if cmd is None or cmd["type"] != "insert_project":
        return params
    full = {**cmd["params"], **params} if merge else params
    return _materialize_insert_project("insert_project", full)


@app.post("/api/commands")
def post_command(cmd: CommandIn) -> dict:
    return _state_or_error(
        lambda: DOC.execute(cmd.type, _materialize_insert_project(cmd.type, cmd.params))
    )


class BatchIn(BaseModel):
    actions: list[CommandIn]


@app.post("/api/commands/batch")
def post_batch(batch: BatchIn) -> dict:
    from apolo.batch import execute_batch

    return _state_or_error(
        lambda: execute_batch(
            DOC,
            [
                {"type": a.type, "params": _materialize_insert_project(a.type, a.params)}
                for a in batch.actions
            ],
        )
    )


class EditOne(BaseModel):
    command_id: str
    params: dict = {}


class EditBatchIn(BaseModel):
    edits: list[EditOne]


@app.patch("/api/commands/batch")
def patch_batch(batch: EditBatchIn, merge: bool = False) -> dict:
    return _state_or_error(
        lambda: DOC.edit_many(
            [
                {
                    "command_id": e.command_id,
                    "params": _materialize_edit(e.command_id, e.params, merge),
                }
                for e in batch.edits
            ],
            merge=merge,
        )
    )


class PreviewIn(BaseModel):
    actions: list[CommandIn] = []
    view: str = "iso"
    labels: bool = False
    section: str | None = None


@app.post("/api/commands/preview")
def preview_commands(body: PreviewIn) -> Response:
    """Ghost render: aplica `actions` (formato batch) sobre una COPIA del documento y
    devuelve el PNG resultante SIN tocar el documento real (los sólidos nuevos van
    resaltados). Para que el agente VEA una propuesta antes de ejecutarla con run_batch."""
    from apolo.commands.registry import CommandError
    from apolo.kernel.render import render_scene_png

    with STATE_LOCK:
        try:
            scene, new_ids = DOC.preview(
                [
                    {"type": a.type, "params": _materialize_insert_project(a.type, a.params)}
                    for a in body.actions
                ]
            )
        except (CommandError, DocumentError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        new = set(new_ids)
        hl = [fid for fid, f in scene.items() if f.command_id in new] or None
        try:
            png = render_scene_png(
                scene, body.view, highlight_ids=hl, labels=body.labels, section=body.section
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(content=png, media_type="image/png")


class ParamsIn(BaseModel):
    params: dict


@app.put("/api/commands/{command_id}")
def edit_command(command_id: str, body: ParamsIn, transient: bool = False, merge: bool = False) -> dict:
    return _state_or_error(
        lambda: DOC.edit(
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
    return _state_or_error(lambda: DOC.remove_commands(body.ids))


# ------------------------------------------------------------------ variables
class VariableIn(BaseModel):
    name: str
    expression: str


@app.post("/api/variables")
def set_variable(body: VariableIn) -> dict:
    existing = next(
        (
            c["id"]
            for c in DOC.commands
            if c["type"] == "set_variable" and c["params"].get("name") == body.name
        ),
        None,
    )

    def run():
        params = {"name": body.name, "expression": body.expression}
        return DOC.edit(existing, params) if existing else DOC.execute("set_variable", params)

    return _state_or_error(run)


@app.delete("/api/variables/{name}")
def delete_variable(name: str) -> dict:
    ids = [
        c["id"]
        for c in DOC.commands
        if c["type"] == "set_variable" and c["params"].get("name") == name
    ]
    if not ids:
        raise HTTPException(status_code=404, detail=f"No existe la variable '{name}'")
    return _state_or_error(lambda: DOC.remove_commands(ids))


@app.post("/api/undo")
def undo() -> dict:
    return _state_or_error(DOC.undo)


@app.post("/api/redo")
def redo() -> dict:
    return _state_or_error(DOC.redo)


class VisibilityIn(BaseModel):
    visible: bool


@app.post("/api/features/{feature_id}/visibility")
def set_visibility(feature_id: str, body: VisibilityIn) -> dict:
    # devuelve el command_id afectado → el cliente MCP recorta el retorno a la pieza
    def run():
        DOC.set_visibility(feature_id, body.visible)
        return DOC.scene[feature_id].command_id
    return _state_or_error(run)


class BulkVisibilityIn(BaseModel):
    ids: list[str]
    visible: bool


@app.post("/api/features/visibility")
def set_visibility_bulk(body: BulkVisibilityIn) -> dict:
    """Visibilidad en lote (aislar / mostrar todo) en una sola llamada."""
    def run():
        for fid in body.ids:
            DOC.set_visibility(fid, body.visible)
        return sorted({DOC.scene[fid].command_id for fid in body.ids if fid in DOC.scene})
    return _state_or_error(run)


@app.get("/api/features/{feature_id}/topology")
def get_feature_topology(feature_id: str) -> dict:
    """Caras y aristas de un sólido con su geometría (tipo, centro, normal/eje,
    longitud, radio) para elegir el SELECTOR declarativo. Read-only."""
    from apolo.kernel.topology import feature_topology

    with STATE_LOCK:
        feat = DOC.scene.get(feature_id)
        if feat is None:
            raise HTTPException(status_code=404, detail=f"No existe el sólido '{feature_id}'")
        topo = feature_topology(feat.shape)
    return {"feature_id": feature_id, "name": feat.name, **topo}


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
            return scene_mass_properties(DOC.scene, ids=wanted)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc


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
        fa = DOC.scene.get(body.a)
        fb = DOC.scene.get(body.b)
        if fa is None or fb is None:
            missing = body.a if fa is None else body.b
            raise HTTPException(status_code=404, detail=f"No existe el sólido '{missing}'")
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
def near_endpoint(point: str, radius: float = 50.0) -> dict:
    """Features cuya caja envolvente queda a ≤ radius mm de `point` (JSON [x,y,z]),
    ordenadas por cercanía. Read-only."""
    from apolo.kernel.measure import features_near

    try:
        pt = json.loads(point)
        assert isinstance(pt, (list, tuple)) and len(pt) == 3
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"point debe ser JSON [x,y,z]: {exc}") from exc
    with STATE_LOCK:
        cercanas = features_near(DOC.scene, pt, radius)
    return {"point": pt, "radius": radius, "cercanas": cercanas}


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
                DOC.scene, view, u, v, fit_ids=fit_ids, zoom=zoom,
                azimuth=azimuth, elevation=elevation, isolate=isolate_ids, section=section,
                roll=roll, pan=pan_xy,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


# ------------------------------------------------------------------ proyectos
def _store_required():
    if STORE is None:
        raise HTTPException(status_code=503, detail="Almacén de proyectos no inicializado")
    return STORE


@app.get("/api/projects")
def list_projects() -> list[dict]:
    return _store_required().list_projects()


class ProjectIn(BaseModel):
    name: str = "Sin título"
    template: str | None = None  # "transportador" | "brazo" | None


@app.post("/api/projects")
def create_project(body: ProjectIn) -> dict:
    global DOC, PROJECT_ID
    store = _store_required()
    with STATE_LOCK:
        DOC = Document(body.name)
        if body.template == "transportador":
            DOC.execute("set_variable", {"name": "L", "expression": "2000"})
            DOC.execute("create_conveyor", {"largo": "=L", "ancho": 600, "altura": 750, "paso": 100})
        elif body.template == "brazo":
            DOC.execute("create_robot_arm", {"name": "Robot", "alcance": 700})
        PROJECT_ID = store.create(DOC)
        payload = scene_payload()
    WS.notify_changed()
    return payload


@app.post("/api/projects/{project_id}/open")
def open_project_by_id(project_id: int) -> dict:
    global DOC, PROJECT_ID
    store = _store_required()
    with STATE_LOCK:
        try:
            DOC = store.load(project_id, tolerant=True)  # suprime comandos rotos (schema drift)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DocumentError as exc:  # ZIP roto / no regenera: 400 claro (antes: 500 opaco)
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        PROJECT_ID = project_id
        payload = scene_payload()
    WS.notify_changed()
    return payload


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int) -> dict:
    store = _store_required()
    if project_id == PROJECT_ID:
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
        DOC.name = body.name.strip() or "Sin título"

    return _state_or_error(run)


class RevisionIn(BaseModel):
    note: str = ""


@app.post("/api/revisions")
def save_revision(body: RevisionIn) -> dict:
    store = _store_required()
    if PROJECT_ID is None:
        raise HTTPException(status_code=400, detail="No hay proyecto abierto")
    with STATE_LOCK:
        rev_id = store.save_revision(PROJECT_ID, DOC, body.note)
    return {"id": rev_id}


@app.get("/api/revisions")
def list_revisions() -> list[dict]:
    store = _store_required()
    if PROJECT_ID is None:
        return []
    return store.list_revisions(PROJECT_ID)


@app.post("/api/revisions/{revision_id}/restore")
def restore_revision(revision_id: int) -> dict:
    global DOC, PROJECT_ID
    store = _store_required()
    with STATE_LOCK:
        try:
            project_id, doc = store.load_revision(revision_id, tolerant=True)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        DOC = doc
        PROJECT_ID = project_id
        _autosave()
        payload = scene_payload()
    WS.notify_changed()
    return payload


# ------------------------------------------------------------ configuraciones
class ConfigIn(BaseModel):
    name: str


@app.post("/api/configurations")
def save_configuration(body: ConfigIn) -> dict:
    return _state_or_error(lambda: DOC.save_configuration(body.name.strip()))


@app.post("/api/configurations/{name}/apply")
def apply_configuration(name: str) -> dict:
    return _state_or_error(lambda: DOC.apply_configuration(name))


@app.delete("/api/configurations/{name}")
def delete_configuration(name: str) -> dict:
    return _state_or_error(lambda: DOC.delete_configuration(name))


class ColorIn(BaseModel):
    color: str | None = None  # null = volver al color automático


@app.post("/api/features/{feature_id}/color")
def set_feature_color(feature_id: str, body: ColorIn) -> dict:
    return _state_or_error(lambda: DOC.set_color(feature_id, body.color))


class MaterialIn(BaseModel):
    material: str | None = None  # null = volver al material automático (heurística)


@app.post("/api/features/{feature_id}/material")
def set_feature_material(feature_id: str, body: MaterialIn) -> dict:
    def run():
        DOC.set_material(feature_id, body.material)
        return DOC.scene[feature_id].command_id
    return _state_or_error(run)


class VerticalIn(BaseModel):
    vertical: str  # 'metalmecanica' | 'carpinteria'


@app.post("/api/vertical")
def set_project_vertical(body: VerticalIn) -> dict:
    return _state_or_error(lambda: DOC.set_vertical(body.vertical))


# --------------------------------------------------------- biblioteca y BOM
@app.get("/api/catalog")
def get_catalog(category: str | None = None, names_only: bool = False) -> list[dict]:
    return catalog_payload(category, names_only)


@app.get("/api/bom")
def get_bom(by_group: bool = False) -> list[dict]:
    """Con `by_group=true` cada fila lleva su `grupo` (sub-ensamblaje) y las piezas
    iguales de grupos distintos salen separadas — subtotales por grupo/instancia."""
    with STATE_LOCK:
        return bom_from_scene(DOC.scene, DOC.default_material(), by_group=by_group)


@app.get("/api/costing.json")
def get_costing() -> dict:
    """BOM COSTEADO (misma agrupación del BOM + costo_ud/costo_total USD por fila con su
    fuente: catálogo referencial / estimación hardware / fabricación) + totales por
    categoría, catálogo vs fabricación e ítem más costoso. Read-only."""
    from apolo.library.costing import scene_costing

    with STATE_LOCK:
        return scene_costing(DOC.scene, DOC.default_material())


@app.get("/api/bom.csv")
def get_bom_csv() -> Response:
    with STATE_LOCK:
        csv_text = bom_to_csv(bom_from_scene(DOC.scene, DOC.default_material()))
    return Response(
        content=csv_text.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{DOC.name or "proyecto"}-bom.csv"'},
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


@app.post("/api/checks")
def run_checks(body: ChecksIn) -> dict:
    from apolo.agent.agent import _conveyor_params_from_doc

    with STATE_LOCK:
        from apolo.library.checks import (
            hardware_ids, interpenetration_report, joint_pairs, same_command_pairs,
        )

        jpairs = joint_pairs(DOC)
        shapes_override = None
        pose_warnings: list[str] = []
        if any(v != 0 for v in body.joint_values.values()):
            from apolo.robotics.pose import posed_shapes

            shapes_override, pose_warnings = posed_shapes(DOC, body.joint_values)
        interferencias = interference_report(
            DOC.scene, shapes_override=shapes_override,
            exclude_pairs=jpairs | same_command_pairs(DOC),
            exclude_ids=hardware_ids(DOC),
        )
        if shapes_override is not None:  # interpenetración de cuerpos con junta compartida
            interferencias["interferencias"] += interpenetration_report(
                DOC.scene, shapes_override, jpairs
            )
            interferencias["interferencias"].sort(key=lambda c: -c["volumen_mm3"])
        interferencias["avisos_pose"] = pose_warnings
        ingenieria = None
        conveyor = None
        # los REQUISITOS guardados (bases de diseño) rellenan lo que la llamada no
        # trae — los parámetros explícitos siempre GANAN
        req = DOC.requirements or {}
        carga = body.carga_kg if body.carga_kg is not None else req.get("carga_kg")
        largo_paq = (body.largo_paquete_mm if body.largo_paquete_mm is not None
                     else req.get("largo_paquete_mm"))
        ancho_paq = (body.ancho_paquete_mm if body.ancho_paquete_mm is not None
                     else req.get("ancho_paquete_mm"))
        velocidad = body.velocidad_m_s or float(req.get("velocidad_m_s") or 0)
        if carga and largo_paq:
            from apolo.library.rules import detect_conveyor, infer_from_solids

            conveyor = (
                body.conveyor
                or _conveyor_params_from_doc(DOC)
                or (infer_from_solids(DOC.scene, body.conveyor_solid_ids)
                    if body.conveyor_solid_ids else None)
                or detect_conveyor(DOC.scene, DOC.variables_resolved)
            )
            if conveyor and req.get("inclinacion_deg") and not conveyor.get("inclinacion_deg"):
                conveyor["inclinacion_deg"] = req["inclinacion_deg"]
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
        # chequeo estructural UNIVERSAL (pernos/soldaduras/L10/pandeo/vuelco):
        # aplica a cualquier ensamblaje, no exige carga ni faja detectada
        from apolo.library.engineering.report import structure_engineering_check

        estructura = structure_engineering_check(
            DOC.scene, DOC.fasteners, DOC.grounds, DOC.joints, DOC.mates,
            carga_kg=carga or 0.0,
            rpm=(conveyor or {}).get("rpm_motor"),
        )
        estructura += _fea_rules()  # resultados FEA guardados (con chequeo de vigencia)
    return {"interferencias": interferencias, "ingenieria": ingenieria, "estructura": estructura}


# -------------------------------------------------------------------- robótica
@app.get("/api/kinematics")
def get_kinematics() -> dict:
    from apolo.robotics import joints_payload

    with STATE_LOCK:
        return joints_payload(DOC)


@app.delete("/api/joints/{name}")
def delete_joint(name: str) -> dict:
    with STATE_LOCK:
        joint = DOC.joints.get(name)
    if joint is None:
        raise HTTPException(status_code=404, detail=f"No existe la junta '{name}'")
    cmd = next((c for c in DOC.commands if c["id"] == joint["command_id"]), None)
    if cmd is None or cmd["type"] != "add_joint":
        raise HTTPException(
            status_code=400,
            detail="Esta junta pertenece a una plantilla (p. ej. un brazo): edita o elimina su comando",
        )
    return _state_or_error(lambda: DOC.remove_commands([joint["command_id"]]))


# ------------------------------------------------------------------ ensamblaje
@app.get("/api/mates")
def get_mates() -> list[dict]:
    with STATE_LOCK:
        return [
            {k: v for k, v in m.items() if k not in ("ref_a", "ref_b")}
            for m in DOC.mates.values()
        ]


@app.delete("/api/mates/{name}")
def delete_mate(name: str) -> dict:
    with STATE_LOCK:
        mate = DOC.mates.get(name)
    if mate is None:
        raise HTTPException(status_code=404, detail=f"No existe el mate '{name}'")
    cmd = next((c for c in DOC.commands if c["id"] == mate["command_id"]), None)
    if cmd is None or cmd["type"] != "add_mate":
        raise HTTPException(status_code=400, detail="Este mate pertenece a una plantilla")
    return _state_or_error(lambda: DOC.remove_commands([mate["command_id"]]))


# ------------------------------------------------- restricciones de riel (lazo cerrado)
class SolveIn(BaseModel):
    values: dict[str, float] = {}


@app.get("/api/constraints")
def get_constraints() -> list[dict]:
    with STATE_LOCK:
        return list(DOC.constraints.values())


@app.post("/api/constraints/solve")
def solve_constraints_endpoint(body: SolveIn) -> dict:
    """Dado un conjunto de valores de junta (driver + libres), devuelve los
    valores con las juntas DEPENDIENTES resueltas para cumplir las restricciones
    de riel. Read-only: no muta el documento. Lo usa la UI para arrastre en vivo."""
    from apolo.assembly.constraints import solve_constraints

    with STATE_LOCK:
        return {"values": solve_constraints(DOC.joints, DOC.constraints, body.values)}


@app.delete("/api/constraints/{name}")
def delete_constraint(name: str) -> dict:
    with STATE_LOCK:
        con = DOC.constraints.get(name)
    if con is None:
        raise HTTPException(status_code=404, detail=f"No existe la restricción '{name}'")
    return _state_or_error(lambda: DOC.remove_commands([con["command_id"]]))


# ----------------------------------------- conectividad / validación de ensamblaje
class SoundnessIn(BaseModel):
    with_autodetect: bool = False  # superpone uniones detectadas por geometría (efímeras)


@app.get("/api/connectivity")
def get_connectivity() -> dict:
    """Uniones declaradas del documento: fijadores (A↔B) y anclajes a tierra."""
    with STATE_LOCK:
        return {
            "fasteners": list(DOC.fasteners.values()),
            "grounds": list(DOC.grounds.values()),
        }


@app.post("/api/assembly/autodetect")
def assembly_autodetect() -> dict:
    """Propone uniones desde la geometría (apoyos en el piso + pares en contacto).
    Read-only: no muta el documento. El usuario/agente confirma con ground/fasten."""
    from apolo.assembly.autodetect import detect_connections

    with STATE_LOCK:
        return detect_connections(DOC.scene)


@app.delete("/api/fasteners/{name}")
def delete_fastener(name: str) -> dict:
    with STATE_LOCK:
        f = DOC.fasteners.get(name)
    if f is None:
        raise HTTPException(status_code=404, detail=f"No existe el fijador '{name}'")
    return _state_or_error(lambda: DOC.remove_commands([f["command_id"]]))


@app.delete("/api/grounds/{name}")
def delete_ground(name: str) -> dict:
    with STATE_LOCK:
        g = DOC.grounds.get(name)
    if g is None:
        raise HTTPException(status_code=404, detail=f"No existe el anclaje '{name}'")
    return _state_or_error(lambda: DOC.remove_commands([g["command_id"]]))


@app.post("/api/assembly/declare")
def assembly_declare() -> dict:
    """Auto-declara la ESTRUCTURA real (anclajes al piso + uniones de soporte) como comandos
    PERSISTIDOS. Inteligente (grafo de soporte dirigido): no fija las piezas colgantes (p. ej.
    rodillos de retorno) → la prueba de gravedad EXACTA las tira. Idempotente: no recrea uniones
    ya declaradas. Tras esto, `stability` con `with_autodetect=false` valida solo lo declarado."""
    from apolo.assembly.autodetect import detect_structure
    from apolo.batch import execute_batch

    with STATE_LOCK:
        det = detect_structure(DOC.scene)
        existing_names = set(DOC.fasteners) | set(DOC.grounds)
        ground_feats = {g["feature"] for g in DOC.grounds.values()}
        pairs = {frozenset((f["a"], f["b"])) for f in DOC.fasteners.values()}

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
        return _state_or_error(lambda: execute_batch(DOC, actions))


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
        proposal = propose_groups(DOC.scene, DOC.commands, CATALOG, DOC.groups)
        if body.dry_run or not proposal:
            return {"dry_run": body.dry_run, "proposal": proposal, "created": 0}
        actions = [{"type": "create_group", "params": g} for g in proposal]
        payload = _state_or_error(lambda: execute_batch(DOC, actions))
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
            detected = detect_connections(DOC.scene)
            extra_edges = [(c["a"], c["b"], "contacto", "") for c in detected["fasteners"]]
            extra_grounds = {g["feature"] for g in detected["grounds"]}
        graph = build_graph(
            DOC.scene, DOC.joints, DOC.mates, DOC.fasteners, DOC.grounds,
            extra_edges=extra_edges, extra_grounds=extra_grounds,
        )
        report = soundness_report(graph)
        report["floating_detail"] = [
            {"id": fid, "nombre": getattr(DOC.scene[fid], "name", fid)}
            for fid in report["floating"]
        ]
        if detected is not None:
            report["autodetect"] = {
                "floor_z": detected["floor_z"],
                "n_grounds": len(detected["grounds"]),
                "n_contactos": len(detected["fasteners"]),
            }
        return report


class StabilityIn(BaseModel):
    seconds: float = 2.0
    gravity: float = 9.81
    fps: int = 12
    with_autodetect: bool = False
    exclude: list[str] = []  # piezas a tratar como NO sujetas ("¿y si le falta el tornillo?")
    include_frames: bool = False  # incluir las poses por fotograma (para animar en el viewport)


def _stability(body: StabilityIn) -> dict:
    from apolo.physics import PhysicsError
    from apolo.physics.stability import stability_test

    try:
        return stability_test(
            DOC.scene, DOC.joints, DOC.mates, DOC.fasteners, DOC.grounds,
            seconds=body.seconds, gravity=body.gravity, fps=body.fps,
            with_autodetect=body.with_autodetect, exclude=body.exclude,
        )
    except PhysicsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/assembly/stability")
def assembly_stability(body: StabilityIn) -> dict:
    """Simula la gravedad sobre TODA la máquina (cuerpos rígidos + casco convexo):
    las piezas sujetas a tierra son estáticas, el resto cae. Devuelve qué piezas se
    CAYERON (desplazamiento del centro de masa) y cuáles aguantaron. Read-only.
    `frames` se omite por defecto (es grande); pide `include_frames` para animar la
    caída en el viewport, o usa el endpoint .gif."""
    with STATE_LOCK:
        res = _stability(body)
    if body.include_frames:
        return res
    return {k: v for k, v in res.items() if k != "frames"}


@app.post("/api/assembly/stability.gif")
def assembly_stability_gif(body: StabilityIn) -> Response:
    """GIF animado de la caída: la estructura sujeta de fondo + las piezas que caen."""
    from apolo.physics.anim import render_drop_gif

    with STATE_LOCK:
        res = _stability(body)
        if not res["products"]:
            raise HTTPException(status_code=400, detail=res.get("mensaje", "nada que simular"))
        dynamic_ids = {p["id"] for p in res["products"]}
        static_scene = {fid: f for fid, f in DOC.scene.items() if fid not in dynamic_ids}
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
        for n, kfs in sorted(DOC.motion.items())
    ]


@app.get("/api/motion")
def get_motion() -> dict:
    with STATE_LOCK:
        return {"studies": _motion_studies()}


@app.put("/api/motion")
def put_motion(body: MotionIn) -> dict:
    with STATE_LOCK:
        try:
            DOC.set_motion(body.name, body.keyframes)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _autosave()
        return {"ok": True, "studies": _motion_studies()}


@app.delete("/api/motion")
def delete_motion(body: MotionDeleteIn) -> dict:
    with STATE_LOCK:
        DOC.delete_motion(body.name)
        _autosave()
        return {"ok": True, "studies": _motion_studies()}


# ---------------------------------------------------- requisitos de proyecto
class RequirementsIn(BaseModel):
    fields: dict = {}


@app.get("/api/requirements")
def get_requirements() -> dict:
    with STATE_LOCK:
        return {"requirements": DOC.requirements}


@app.put("/api/requirements")
def put_requirements(body: RequirementsIn) -> dict:
    with STATE_LOCK:
        try:
            DOC.set_requirements(body.fields)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _autosave()
        return {"ok": True, "requirements": DOC.requirements}


@app.post("/api/motion/scan")
def scan_motion(body: ScanIn) -> dict:
    from apolo.robotics.motion import scan_collisions

    with STATE_LOCK:
        return {"colisiones": scan_collisions(DOC, DOC.motion.get(body.name, []), body.steps)}


def _robot_export(builder) -> bytes:
    with STATE_LOCK:
        try:
            return builder(DOC)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/export/urdf")
def export_urdf() -> Response:
    from apolo.robotics import export_urdf_zip

    data = _robot_export(export_urdf_zip)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{DOC.name or "robot"}-urdf.zip"'},
    )


@app.get("/api/export/sdf")
def export_sdf() -> Response:
    from apolo.robotics import export_sdf_zip

    data = _robot_export(export_sdf_zip)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{DOC.name or "robot"}-sdf.zip"'},
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


class ScriptTestIn(BaseModel):
    code: str


@app.post("/api/script/test")
def test_script_endpoint(body: ScriptTestIn) -> dict:
    """Dry-run de un script build123d: lo ejecuta en el sandbox y devuelve volumen/bbox
    SIN tocar el documento. Para que el agente itere sin crear/deshacer features."""
    from apolo.kernel import bbox_payload
    from apolo.sandbox import ScriptError, run_script_to_shape

    with STATE_LOCK:
        variables = dict(DOC.variables_resolved)
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
        scene = DOC.scene
        if isolate_ids:
            scene = {fid: DOC.scene[fid] for fid in isolate_ids if fid in DOC.scene}
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

            vals = solve_constraints(DOC.joints, DOC.constraints, vals)
            override, _ = posed_shapes(DOC, vals)
        # COTA: distancia mínima entre dos piezas → la dibuja la vía VTK encima de la geometría.
        # Usa las shapes RENDERIZADAS (override si hay pose) para que coincida con lo que se ve.
        dimension = None
        if measure:
            from apolo.kernel.measure import measure_distance

            parts = [s.strip() for s in measure.split(",") if s.strip()]
            if len(parts) != 2:
                raise HTTPException(status_code=400, detail="measure: pasa exactamente dos ids 'a,b'")
            a_id, b_id = parts
            fa, fb = DOC.scene.get(a_id), DOC.scene.get(b_id)
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
        # render sombreado de UNA vista → VTK (normales suaves, como el viewport web; incluye
        # labels/rótulos billboard). SOLO la MULTIVISTA (views) o un fallo de VTK (sin OpenGL) →
        # matplotlib. vtk_only=true (lo usa el tool MCP render_view): EXIGE VTK y NO cae a
        # matplotlib (si no hay OpenGL → 503 claro, no una imagen con cuadrícula).
        png = None
        if (vtk_only or shade) and not view_list:
            try:
                from apolo.kernel.render_vtk import render_scene_vtk

                png = render_scene_vtk(
                    scene, view,
                    highlight_ids=highlight_ids, shapes_override=override,
                    fit_ids=fit_ids, zoom=zoom, section=section,
                    show_axes=show_axes, show_bbox=show_bbox, colors=_feature_colors(),
                    ignore_visibility=bool(isolate_ids),
                    azimuth=azimuth, elevation=elevation, dimension=dimension, edges=edges,
                    xray=xray, labels=labels, roll=roll, pan=pan_xy,
                )
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
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
        if png is None:
            try:
                png = render_scene_png(
                    scene, view,
                    highlight_ids=highlight_ids, show_axes=show_axes, show_bbox=show_bbox,
                    shapes_override=override, fit_ids=fit_ids, zoom=zoom, proportional=proportional,
                    views=view_list, labels=labels, section=section,
                    colors=_feature_colors() if shade else None,
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
        variables = dict(DOC.variables_resolved)
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
        project_vars = sorted(DOC.variables_resolved)
    return {
        "functions": sorted(ALLOWED_FUNCS),
        "constants": sorted(ALLOWED_CONSTANTS),
        "operators": ["+", "-", "*", "/", "//", "%", "**"],
        "unary": ["+", "-"],
        "variables": project_vars,
        "note": "Ángulos en grados (sin/cos/tan). Prefijo '=' en campos numéricos.",
        "example": "=largo/2 + sqrt(ancho)",
    }


@app.get("/api/design-guidelines")
def design_guidelines_endpoint() -> dict:
    """Criterio de ingeniería que el agente debe aplicar POR DEFECTO al diseñar (sirve para
    máquinas, muebles, estructuras, cualquier objeto): decálogo con detalle, cómo verificar
    cada regla en Apolo, cuándo preguntar vs. asumir, y ejemplos. No depende del documento."""
    from apolo.design import design_guidelines

    return design_guidelines()


# ------------------------------------------------------------------ física (drop-test)
class Product(BaseModel):
    w: float
    d: float
    h: float
    mass: float | None = None
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


class DropIn(BaseModel):
    products: list[Product]
    seconds: float = 2.0
    gravity: float = 9.81
    fps: int = 20


def _drop(body: DropIn) -> dict:
    """Corre el drop-test sobre la escena actual (read-only). 400 si falta el motor."""
    from apolo.physics import PhysicsError, drop_test

    products = [p.model_dump() for p in body.products]
    with STATE_LOCK:
        try:
            return drop_test(DOC.scene, products, body.seconds, body.gravity, body.fps)
        except PhysicsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/physics/drop")
def physics_drop(body: DropIn) -> dict:
    return _drop(body)


@app.post("/api/physics/drop.gif")
def physics_drop_gif(body: DropIn) -> Response:
    from apolo.physics.anim import render_drop_gif

    res = _drop(body)
    with STATE_LOCK:
        gif = render_drop_gif(DOC.scene, res["products"], res["frames"], fps=body.fps)
    return Response(content=gif, media_type="image/gif")


# ---------------------------------------------------------------- FEA (V5.6)
class FeaLoadIn(BaseModel):
    selector: dict                        # selector declarativo de caras cargadas
    force_n: list[float] | None = None    # fuerza TOTAL [Fx,Fy,Fz] N (repartida F/área)
    pressure_mpa: float | None = None     # presión normal ENTRANTE a la cara


class FeaStaticIn(BaseModel):
    feature_id: str
    fixed: dict                           # selector declarativo de caras EMPOTRADAS
    loads: list[FeaLoadIn] = []
    material: str | None = None           # gana sobre resolve_material
    yield_mpa: float | None = None        # obligatorio si el material no tiene σy tabulado
    self_weight: bool = False
    mesh_size_mm: float | None = None
    fs_min: float = 2.0
    save: bool = True                     # persistir el resumen en DOC.fea (memoria)


_LAST_FEA_FIELD: dict = {}  # feature_id → FeaField del último solve (fringe, no persiste)


def _fea_static_run(body: FeaStaticIn):
    """Patrón dos-locks: (a) STATE_LOCK resuelve material/selectores y exporta el
    STEP; (b) SIN lock (solo FEA_LOCK interno) malla y resuelve; (c) STATE_LOCK
    persiste el resumen. El solve nunca serializa al resto del server."""
    import shutil
    import tempfile

    from apolo.fea import FeaError
    from apolo.fea.mesher import FaceDesc
    from apolo.kernel.selectors import SelectorError, resolve_faces
    from apolo.library.catalog import CATALOG
    from apolo.library.materials import (
        density, has_yield, resolve_material, yield_strength, young_modulus,
    )

    from apolo.kernel.shapes import is_surface

    with STATE_LOCK:
        feat = DOC.scene.get(body.feature_id)
        if feat is None:
            raise HTTPException(status_code=404, detail=f"No existe la pieza '{body.feature_id}'")
        if is_surface(feat.shape):
            raise HTTPException(
                status_code=400,
                detail=f"'{feat.name}' es una superficie (volumen 0); el FEA necesita un "
                       f"sólido. Dale espesor con thicken antes de analizarla.",
            )
        material = body.material or resolve_material(feat, CATALOG, DOC.default_material())
        if body.yield_mpa is not None:
            sy = float(body.yield_mpa)
        elif has_yield(material):
            sy = yield_strength(material)
        else:
            raise HTTPException(
                status_code=400,
                detail=f"El material '{material}' no tiene límite elástico tabulado: "
                       f"pasa yield_mpa explícito (el FS saldría de un default y mentiría)",
            )
        e_mpa, rho = young_modulus(material), density(material)
        try:
            fixed = [FaceDesc.from_face(f) for f in resolve_faces(feat.shape, body.fixed)]
            loads = []
            for ld in body.loads:
                descs = [FaceDesc.from_face(f) for f in resolve_faces(feat.shape, ld.selector)]
                loads.append({"descs": descs, "force_n": ld.force_n,
                              "pressure_mpa": ld.pressure_mpa})
        except SelectorError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        tmp_dir = tempfile.mkdtemp(prefix="apolo_fea_step_")
        step = str(Path(tmp_dir) / "pieza.step")
        export_step_file([feat.shape], step)
        pieza, vol = feat.name, float(feat.shape.volume)

    try:
        from apolo.fea.static import run_static_analysis

        resumen, field = run_static_analysis(
            step, pieza=pieza, fixed=fixed, loads=loads, e_mpa=e_mpa,
            yield_mpa=sy, density_kg_mm3=rho, material=material,
            self_weight=body.self_weight, mesh_size_mm=body.mesh_size_mm,
            fs_min=body.fs_min,
        )
    except FeaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    resumen["feature_id"] = body.feature_id
    resumen["volumen_mm3"] = round(vol, 1)
    if body.save:
        with STATE_LOCK:
            DOC.set_fea_result(body.feature_id, resumen)
            _autosave()
    _LAST_FEA_FIELD.clear()
    _LAST_FEA_FIELD[body.feature_id] = field
    return resumen, field


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


@app.get("/api/fea/{feature_id}")
def get_fea(feature_id: str) -> dict:
    with STATE_LOCK:
        res = DOC.fea.get(feature_id)
        if res is None:
            raise HTTPException(status_code=404, detail="La pieza no tiene FEA guardado")
        return res


@app.get("/api/fea/{feature_id}/fringe.png")
def get_fea_fringe(feature_id: str) -> Response:
    """Fringe del ÚLTIMO análisis de la pieza SIN re-resolver (campo en memoria del
    proceso; si el server se reinició, re-ejecuta POST /api/fea/static)."""
    from apolo.fea.fringe import fringe_png

    field = _LAST_FEA_FIELD.get(feature_id)
    if field is None:
        raise HTTPException(status_code=404,
                            detail="No hay campo FEA en memoria para esa pieza: "
                                   "corre POST /api/fea/static primero")
    with STATE_LOCK:
        res = DOC.fea.get(feature_id) or {}
    title = f"von Mises [MPa] · {res.get('pieza', feature_id)} · FS={res.get('fs')}"
    return Response(content=fringe_png(field, title=title), media_type="image/png")


def _fea_rules() -> list[dict]:
    """Convierte los resultados FEA guardados (DOC.fea) en reglas para checks y
    memoria, con chequeo de VIGENCIA: si la pieza ya no existe o su volumen cambió
    >0.1 % desde el análisis, la regla degrada a aviso (re-ejecutar). Llamar bajo
    STATE_LOCK."""
    rules: list[dict] = []
    for fid, res in DOC.fea.items():
        regla = f"FEA · {res.get('pieza', fid)}"
        feat = DOC.scene.get(fid)
        if feat is None:
            rules.append({"regla": regla, "estado": "aviso",
                          "detalle": "La pieza del análisis FEA ya no existe en la escena.",
                          "recomendacion": "Borra el resultado o re-ejecuta fea_static."})
            continue
        vol_ref = float(res.get("volumen_mm3") or 0)
        vol_now = float(getattr(feat.shape, "volume", 0) or 0)
        if vol_ref and abs(vol_now - vol_ref) > 1e-3 * vol_ref:
            rules.append({"regla": regla, "estado": "aviso",
                          "detalle": f"La geometría cambió desde el análisis "
                                     f"({vol_ref:.0f} → {vol_now:.0f} mm³): resultado obsoleto.",
                          "recomendacion": "Re-ejecuta fea_static para refrescar el FS."})
            continue
        rule = {"regla": regla, "estado": res.get("estado", "aviso"),
                "detalle": res.get("detalle", ""), "calc": res.get("calc")}
        if res.get("estado") == "error":
            rule["recomendacion"] = "Refuerza la pieza o reduce la carga (FS < 1.2)."
        rules.append(rule)
    return rules


# --------------------------------------------------------------------- planos
def _feature_colors() -> dict:
    """Color por pieza IDÉNTICO al viewport web (DOC.colors asignados, o paleta por índice de
    escena) para que el sombreado del plano coincida con lo que el usuario ve en 3D."""
    return {feat.id: DOC.colors.get(feat.id) or PALETTE[i % len(PALETTE)]
            for i, feat in enumerate(DOC.scene.values())}


def _drawing_meta() -> dict:
    """Cajetín: nº de plano (id de proyecto) + revisiones del proyecto (SQLite)."""
    meta: dict = {"drawing_no": str(PROJECT_ID) if PROJECT_ID is not None else "—"}
    store = STORE
    if store is not None and PROJECT_ID is not None:
        try:
            revs = store.list_revisions(PROJECT_ID)
            meta["revisions"] = [
                {"rev": i + 1, "date": r.get("created_at", r.get("date", "")), "note": r.get("note", "")}
                for i, r in enumerate(revs)
            ]
        except Exception:
            pass
    return meta


def _sheet_model(sheet: str, hidden: bool, dims: str = "", section: bool = False, bom: bool = False):
    from apolo.drawing import compose_sheet

    dims_features = [s for s in dims.split(",") if s] or None
    with STATE_LOCK:
        try:
            return compose_sheet(
                DOC.scene, sheet=sheet, include_hidden=hidden, project_name=DOC.name,
                dims_features=dims_features, section=section, bom=bom, meta=_drawing_meta(),
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
        headers={"Content-Disposition": f'attachment; filename="{DOC.name or "plano"}.dxf"'},
    )


def _sheetmetal_flat(feature_id: str):
    """Localiza el comando create_sheet_metal que generó la feature y devuelve su
    SheetModel desplegado (resolviendo expresiones del proyecto)."""
    from apolo.commands import resolve_params
    from apolo.commands.models import SheetMetalParams
    from apolo.library.sheetmetal import flat_pattern

    with STATE_LOCK:
        feat = DOC.scene.get(feature_id)
        if feat is None:
            raise HTTPException(status_code=404, detail=f"No existe el sólido '{feature_id}'")
        cmd = next((c for c in DOC.commands if c["id"] == feat.command_id), None)
        if cmd is None or cmd["type"] != "create_sheet_metal":
            raise HTTPException(status_code=400, detail=f"'{feature_id}' no es una chapa metálica")
        try:
            from apolo.library.catalog import CATALOG
            from apolo.library.materials import resolve_material
            from apolo.library.sheetmetal import flaps_from_specs, k_for_material

            p = SheetMetalParams.model_validate(resolve_params(cmd["params"], DOC.variables_resolved))
            # K-factor: explícito gana; si no, por MATERIAL de la pieza (V5.5)
            k = p.k_factor if p.k_factor is not None else k_for_material(
                resolve_material(feat, CATALOG, DOC.default_material())
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
        headers={"Content-Disposition": f'attachment; filename="{DOC.name or "plano"}.pdf"'},
    )


# --------------------------------------------- despiece de fabricación (Fase D)
@app.get("/api/cutlist.json")
def cutlist_json() -> dict:
    """Lista de corte (a-medida + catálogo cortable, agrupada por material/dimensiones) +
    totales por material + cédula de herraje. Read-only."""
    from apolo.library.cutlist import cut_list, cut_list_totals, hardware_schedule

    with STATE_LOCK:
        rows = cut_list(DOC.scene)
        return {
            "lista_de_corte": rows,
            "totales": cut_list_totals(rows),
            "herraje": hardware_schedule(DOC.scene),
        }


@app.get("/api/cutlist.csv")
def cutlist_csv_endpoint() -> Response:
    from apolo.library.cutlist import cut_list, cut_list_csv, cut_list_totals

    with STATE_LOCK:
        rows = cut_list(DOC.scene)
        text = cut_list_csv(rows, cut_list_totals(rows))
    return Response(
        content=text, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lista-de-corte.csv"},
    )


def _nesting_model(mode: str, stock_w: float, stock_h: float, material: str | None, kerf: float):
    from apolo.library.cutlist import cut_list
    from apolo.library.nesting import nest_1d, nest_2d, nesting_sheet_1d, nesting_sheet_2d

    with STATE_LOCK:
        rows = [r for r in cut_list(DOC.scene) if not material or r["material"] == material]
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
        rows = [r for r in cut_list(DOC.scene) if not material or r["material"] == material]
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
            pages = sheet_set(DOC.scene, project_name=DOC.name, template=template,
                              meta=_drawing_meta(), sheet=sheet, shaded=shaded,
                              colors=_feature_colors(), hole_fits=_hole_fit_map(DOC) or None,
                              hole_threads=_hole_thread_map(DOC) or None,
                              thread_rows=_thread_schedule(DOC) or None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=sheets_to_pdf(pages), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{DOC.name or "juego"}-planos.pdf"'},
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
            pages = sheet_set(DOC.scene, project_name=DOC.name, template=template,
                              meta=_drawing_meta(), sheet=sheet,
                              colors=_feature_colors(), hole_fits=_hole_fit_map(DOC) or None,
                              hole_threads=_hole_thread_map(DOC) or None,
                              thread_rows=_thread_schedule(DOC) or None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        base = (DOC.name or "juego").replace("/", "-")
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
    from apolo.library.engineering.report import structure_engineering_check
    from apolo.library.rules import conveyor_engineering_check as conv_check
    from apolo.library.rules import detect_conveyor
    from apolo.agent.agent import _conveyor_params_from_doc

    with STATE_LOCK:
        req = DOC.requirements or {}
        carga = carga_kg if carga_kg is not None else req.get("carga_kg")
        largo_paq = (largo_paquete_mm if largo_paquete_mm is not None
                     else req.get("largo_paquete_mm"))
        ancho_paq = (ancho_paquete_mm if ancho_paquete_mm is not None
                     else req.get("ancho_paquete_mm"))
        velocidad = velocidad_m_s if velocidad_m_s is not None else float(req.get("velocidad_m_s") or 0)
        if not carga or not largo_paq:
            raise HTTPException(
                status_code=400,
                detail="Faltan la carga y/o el largo de paquete: declara los requisitos con "
                       "set_requirements (carga_kg, largo_paquete_mm, …) o pasa los parámetros.",
            )
        rules: list[dict] = []
        conveyor = _conveyor_params_from_doc(DOC) or detect_conveyor(DOC.scene, DOC.variables_resolved)
        if conveyor:
            if req.get("inclinacion_deg") and not conveyor.get("inclinacion_deg"):
                conveyor["inclinacion_deg"] = req["inclinacion_deg"]
            rules += conv_check(conveyor, carga_kg=carga, largo_paquete_mm=largo_paq,
                                velocidad_m_s=velocidad, ancho_paquete_mm=ancho_paq)
        rules += structure_engineering_check(
            DOC.scene, DOC.fasteners, DOC.grounds, DOC.joints, DOC.mates,
            carga_kg=carga, rpm=(conveyor or {}).get("rpm_motor"),
        )
        rules += _fea_rules()  # página FEA en la memoria (con chequeo de vigencia)
        png = None
        try:
            vis = {fid: f for fid, f in DOC.scene.items() if getattr(f, "visible", True)}
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
        req_efectivos = {**req, "carga_kg": carga, "largo_paquete_mm": largo_paq}
        if ancho_paq:
            req_efectivos["ancho_paquete_mm"] = ancho_paq
        if velocidad:
            req_efectivos["velocidad_m_s"] = velocidad
        pages = calc_report(DOC.scene, rules=rules, requirements=req_efectivos,
                            project_name=DOC.name or "Sin título", png=png, meta=meta,
                            sheet=sheet)
    return Response(
        content=sheets_to_pdf(pages), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{DOC.name or "proyecto"}-memoria-calculo.pdf"'},
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
        req = DOC.requirements or {}
        cur = currency or str(req.get("moneda") or "USD")
        fx_eff = fx if fx is not None else float(req.get("tipo_cambio") or 1.0)
        pages = quotation_pages(
            DOC.scene, project_name=DOC.name or "Sin título",
            requirements=DOC.requirements, margin_pct=margin_pct, tax_pct=tax_pct,
            currency=cur, fx=fx_eff, meta=_drawing_meta(),
        )
    return Response(
        content=sheets_to_pdf(pages), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{DOC.name or "proyecto"}-cotizacion.pdf"'},
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
        scene = DOC.scene
        if isolate:
            ids = _expand_ids(isolate) or []  # acepta NOMBRES de grupo (V5.2)
            scene = {fid: DOC.scene[fid] for fid in ids if fid in DOC.scene}
            if not scene:
                raise HTTPException(status_code=400, detail="isolate: ningún id existe en la escena")
        try:
            pages = assembly_manual(scene, commands=DOC.commands, project_name=title or DOC.name,
                                    sheet=sheet, meta=_drawing_meta(), colors=_feature_colors(),
                                    size_px=size_px)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    fname = (title or DOC.name or "manual").encode("ascii", "ignore").decode() or "manual"
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


_SHAFT_FIT_RE = None  # compilado perezoso en _hole_fit_map


def _hole_fit_map(doc) -> dict[float, str]:
    """Mapa AUTOMÁTICO Ø_nominal → clase ISO 286 para los callouts del plano (V5.4):
    (1) comandos drill_hole con `fit`; (2) NOMBRES de features «… Ø35 h7» (ejes —
    convención bendecida, como el grado de material). Colisión en el mismo Ø: gana
    el drill_hole (los círculos HLR no distinguen origen; documentado)."""
    import re

    global _SHAFT_FIT_RE
    if _SHAFT_FIT_RE is None:
        _SHAFT_FIT_RE = re.compile(
            r"Ø\s*(\d+(?:\.\d+)?)\s+((?:js|[gfhkmnp]))(\d{1,2})\b"
        )
    out: dict[float, str] = {}
    for feat in doc.scene.values():
        m = _SHAFT_FIT_RE.search(getattr(feat, "name", "") or "")
        if m:
            out[float(m.group(1))] = f"{m.group(2)}{m.group(3)}"
    for cmd in doc.commands:
        if cmd.get("type") == "drill_hole" and cmd.get("params", {}).get("fit"):
            try:
                dia = float(cmd["params"].get("diameter", 0))
            except (TypeError, ValueError):
                continue  # diámetro por "=expresión": se omite del mapa automático
            if dia > 0:
                out[dia] = cmd["params"]["fit"]
    return out


def _hole_thread_map(doc) -> dict[float, str]:
    """Mapa AUTOMÁTICO Ø_broca → designación de rosca (V5.7) desde los comandos
    drill_hole con `thread`. El círculo HLR que sale al plano es el de la BROCA
    (M8 → Ø6.8) — si una broca coincide con el Ø de un agujero liso mapeado, gana
    la rosca (los círculos HLR no distinguen origen; mismo caveat que los fits)."""
    from apolo.library.engineering.threads import thread_designation, thread_spec

    out: dict[float, str] = {}
    for cmd in doc.commands:
        thr = cmd.get("params", {}).get("thread") if cmd.get("type") == "drill_hole" else None
        if thr:
            try:
                des = thread_designation(thr)
                out[thread_spec(des)["broca_mm"]] = des
            except KeyError:
                continue  # rosca inválida en un log viejo: no rompe el plano
    return out


def _thread_schedule(doc) -> list[dict]:
    """Roscas agrupadas por designación para la CÉDULA del juego de planos (V5.7):
    [{designacion, etiqueta, cantidad, broca_mm, piezas, norma}]."""
    from apolo.library.engineering.threads import (
        format_thread_label, thread_designation, thread_spec,
    )

    groups: dict[str, dict] = {}
    for cmd in doc.commands:
        if cmd.get("type") != "drill_hole":
            continue
        thr = cmd.get("params", {}).get("thread")
        if not thr:
            continue
        try:
            des = thread_designation(thr)
            spec = thread_spec(des)
        except KeyError:
            continue
        g = groups.setdefault(des, {
            "designacion": des, "etiqueta": format_thread_label(des),
            "cantidad": 0, "broca_mm": spec["broca_mm"], "piezas": [], "norma": spec["norma"],
        })
        g["cantidad"] += 1
        feat = doc.scene.get(cmd.get("params", {}).get("feature"))
        name = getattr(feat, "name", None)
        if name and name not in g["piezas"]:
            g["piezas"].append(name)
    return sorted(groups.values(), key=lambda g: g["designacion"])


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
        scene = DOC.scene
        if spec.isolate:
            iso = _expand_ids(spec.isolate) or []  # acepta NOMBRES de grupo (V5.2)
            scene = {fid: scene[fid] for fid in iso if fid in scene}
            if not scene:
                raise HTTPException(status_code=400, detail="isolate: ningún id existe en la escena")
        fits_map = _hole_fit_map(DOC)
        for k, v in (spec.hole_fits or {}).items():  # override del agente encima del auto
            try:
                fits_map[float(k)] = v
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"hole_fits: clave '{k}' no es un Ø numérico")
        threads_map = _hole_thread_map(DOC)
        for k, v in (spec.hole_threads or {}).items():  # override espejo (V5.7)
            try:
                threads_map[float(k)] = v
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"hole_threads: clave '{k}' no es un Ø numérico")
        try:
            model = compose_sheet(
                scene, sheet=spec.sheet, include_hidden=spec.include_hidden, project_name=DOC.name,
                dims_features=spec.dims or None, section=spec.section or False, bom=spec.bom,
                detail=spec.detail, datum_dims=spec.datum_dims or None,
                cutlist=spec.cutlist, member_detail=spec.member_detail,
                auto_dims=spec.auto_dims, interface_dims=spec.interface_dims,
                hardware=spec.hardware, explode=spec.explode,
                notes=spec.notes or None, assembly_notes=spec.assembly_notes,
                shaded=spec.shaded, colors=_feature_colors(),
                hole_fits=fits_map or None, hole_threads=threads_map or None,
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
                    headers={"Content-Disposition": f'attachment; filename="{DOC.name or "plano"}.pdf"'})


# ----------------------------------------------------------------- export / io
@app.post("/api/import")
async def import_step_file(file: UploadFile, split: bool = False) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Archivo vacío")
    name = (file.filename or "Importado").rsplit(".", 1)[0][:40]

    def run():
        digest = DOC.add_attachment(data)
        try:
            DOC.execute("import_step", {"attachment": digest, "name": name, "split": split})
        except Exception:
            DOC.attachments.pop(digest, None)
            raise

    return _state_or_error(run)


@app.get("/api/export/step")
def export_step() -> FileResponse:
    with STATE_LOCK:
        shapes = [f.shape for f in DOC.scene.values() if f.visible]
        if not shapes:
            raise HTTPException(status_code=400, detail="No hay sólidos visibles que exportar")
        tmp = Path(tempfile.mkstemp(suffix=".step")[1])
        export_step_file(shapes, str(tmp))
    return FileResponse(tmp, filename=f"{DOC.name or 'modelo'}.step", media_type="model/step")


@app.get("/api/export/stl")
def export_stl_endpoint(tolerance: float = 0.5) -> FileResponse:
    """Exporta los sólidos VISIBLES como UN STL binario (malla; para impresión 3D /
    visores externos). `tolerance` = desviación máxima de teselado en mm. Read-only."""
    from build123d import Compound, export_stl

    with STATE_LOCK:
        shapes = [f.shape for f in DOC.scene.values() if f.visible]
        if not shapes:
            raise HTTPException(status_code=400, detail="No hay sólidos visibles que exportar")
        tmp = Path(tempfile.mkstemp(suffix=".stl")[1])
        export_stl(Compound(children=shapes), str(tmp), tolerance=tolerance)
    return FileResponse(tmp, filename=f"{DOC.name or 'modelo'}.stl", media_type="model/stl")


@app.get("/api/project/file")
def download_project() -> Response:
    with STATE_LOCK:
        content = DOC.to_apolo_bytes()
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{DOC.name or "proyecto"}.apolo"'},
    )


@app.post("/api/project/open")
async def open_project(file: UploadFile) -> dict:
    global DOC, PROJECT_ID
    data = await file.read()
    with STATE_LOCK:
        try:
            DOC = Document.from_apolo_bytes(data, tolerant=True)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # E2: un proyecto NUEVO en la BD — el siguiente autosave NO debe pisar el que
        # estaba abierto antes (sin esto, PROJECT_ID seguía apuntando al anterior)
        PROJECT_ID = STORE.create(DOC) if STORE is not None else None
        payload = scene_payload()
    WS.notify_changed()
    return payload


class NewProjectIn(BaseModel):
    name: str = "Sin título"


@app.post("/api/project/new")
def new_project(body: NewProjectIn) -> dict:
    global DOC, PROJECT_ID
    with STATE_LOCK:
        DOC = Document(body.name)
        PROJECT_ID = STORE.create(DOC) if STORE is not None else None  # E2: id propio
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
    return StreamingResponse(
        chat_stream(DOC, messages, auto=body.auto),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------- UI build
_ui_dist = Path(__file__).resolve().parents[3] / "ui" / "dist"
if _ui_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_ui_dist), html=True), name="ui")
