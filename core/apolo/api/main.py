"""API de Genix Apolo CAD.

La UI y el agente IA son dos clientes de esta misma API: toda operación de
modelado entra por /api/commands (o /api/commands/batch para los lotes que
propone el agente).
"""

from __future__ import annotations

import asyncio
import json
import tempfile
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


def _autosave() -> None:
    if STORE is not None and PROJECT_ID is not None:
        try:
            STORE.save(PROJECT_ID, DOC)
        except Exception as exc:  # el autosave nunca debe romper la operación
            log_error("backend.autosave", repr(exc))


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

    def notify_changed(self) -> None:
        if not self.loop:
            return
        for ws in list(self.clients):
            asyncio.run_coroutine_threadsafe(
                ws.send_json({"type": "document_changed"}), self.loop
            )


WS = WsManager()


@app.on_event("startup")
async def _capture_loop() -> None:
    global DOC, STORE, PROJECT_ID
    WS.loop = asyncio.get_running_loop()
    session_marker("Inicio de sesión del servidor")

    import os

    from apolo.projects import ProjectStore

    db_path = os.environ.get(
        "APOLO_DB", str(Path(__file__).resolve().parents[3] / "data" / "apolo.db")
    )
    STORE = ProjectStore(db_path)
    with STATE_LOCK:
        recent = STORE.most_recent_id()
        if recent is not None:
            try:
                DOC = STORE.load(recent)
                PROJECT_ID = recent
            except Exception as exc:
                log_error("backend.startup", f"No se pudo cargar el proyecto {recent}: {exc!r}")
                PROJECT_ID = STORE.create(DOC)
        else:
            PROJECT_ID = STORE.create(DOC)


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


def document_payload() -> dict:
    return {
        "name": DOC.name,
        "commands": DOC.commands,
        "can_undo": DOC.can_undo,
        "can_redo": DOC.can_redo,
        "variables": variables_payload(),
        "configurations": sorted(DOC.configurations.keys()),
        "project_id": PROJECT_ID,
    }


_DEF_MESH_CACHE: dict[str, dict] = {}


def _definition_mesh(key: str) -> dict | None:
    from apolo.commands.registry import DEFINITIONS

    if key not in DEFINITIONS:
        return None
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


@app.post("/api/commands")
def post_command(cmd: CommandIn) -> dict:
    return _state_or_error(lambda: DOC.execute(cmd.type, cmd.params))


class BatchIn(BaseModel):
    actions: list[CommandIn]


@app.post("/api/commands/batch")
def post_batch(batch: BatchIn) -> dict:
    from apolo.batch import execute_batch

    return _state_or_error(
        lambda: execute_batch(DOC, [{"type": a.type, "params": a.params} for a in batch.actions])
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
            [{"command_id": e.command_id, "params": e.params} for e in batch.edits],
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
                [{"type": a.type, "params": a.params} for a in body.actions]
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
        lambda: DOC.edit(command_id, body.params, coalesce=transient, merge=merge)
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
    return _state_or_error(lambda: DOC.set_visibility(feature_id, body.visible))


class BulkVisibilityIn(BaseModel):
    ids: list[str]
    visible: bool


@app.post("/api/features/visibility")
def set_visibility_bulk(body: BulkVisibilityIn) -> dict:
    """Visibilidad en lote (aislar / mostrar todo) en una sola llamada."""
    def run():
        for fid in body.ids:
            DOC.set_visibility(fid, body.visible)
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

    fit_ids = [s.strip() for s in fit.split(",") if s.strip()] if fit else None
    isolate_ids = [s.strip() for s in isolate.split(",") if s.strip()] if isolate else None
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
            DOC = store.load(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
            project_id, doc = store.load_revision(revision_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
    return _state_or_error(lambda: DOC.set_material(feature_id, body.material))


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
def get_bom() -> list[dict]:
    with STATE_LOCK:
        return bom_from_scene(DOC.scene, DOC.default_material())


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
        if body.carga_kg and body.largo_paquete_mm:
            from apolo.library.rules import detect_conveyor, infer_from_solids

            conveyor = (
                body.conveyor
                or _conveyor_params_from_doc(DOC)
                or (infer_from_solids(DOC.scene, body.conveyor_solid_ids)
                    if body.conveyor_solid_ids else None)
                or detect_conveyor(DOC.scene, DOC.variables_resolved)
            )
            if conveyor:
                ingenieria = conveyor_engineering_check(
                    conveyor,
                    carga_kg=body.carga_kg,
                    largo_paquete_mm=body.largo_paquete_mm,
                    velocidad_m_s=body.velocidad_m_s,
                    ancho_paquete_mm=body.ancho_paquete_mm,
                )
            else:
                ingenieria = [
                    {
                        "regla": "transportador",
                        "estado": "aviso",
                        "detalle": "No hay ningún transportador en el documento que validar.",
                    }
                ]
    return {"interferencias": interferencias, "ingenieria": ingenieria}


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

    highlight_ids = [s.strip() for s in highlight.split(",") if s.strip()] if highlight else None
    fit_ids = [s.strip() for s in fit.split(",") if s.strip()] if fit else None
    isolate_ids = [s.strip() for s in isolate.split(",") if s.strip()] if isolate else None
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
            p = SheetMetalParams.model_validate(resolve_params(cmd["params"], DOC.variables_resolved))
            return p.name, flat_pattern(
                p.name, p.ancho, p.fondo, p.espesor, p.lados,
                p.altura_pestana, p.angulo, p.radio, p.k_factor,
                holes=[(h.x, h.y, h.d) for h in p.holes],
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
                              colors=_feature_colors())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=sheets_to_pdf(pages), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{DOC.name or "juego"}-planos.pdf"'},
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
            ids = [s.strip() for s in isolate.split(",") if s.strip()]
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


@app.post("/api/drawing/spec")
def drawing_spec(spec: DrawingSpecIn) -> Response:
    """Plano profesional por INTENCIÓN: una sola spec declara vistas/corte/detalle/cotas/
    BOM/aislado/cajetín y el motor lo compone. format = pdf|svg|dxf. Read-only (el aislado
    filtra la escena sin tocar la visibilidad del documento)."""
    from apolo.drawing import compose_sheet, sheet_to_dxf, sheet_to_pdf, sheet_to_svg

    with STATE_LOCK:
        scene = DOC.scene
        if spec.isolate:
            scene = {fid: scene[fid] for fid in spec.isolate if fid in scene}
            if not scene:
                raise HTTPException(status_code=400, detail="isolate: ningún id existe en la escena")
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
                meta={**_drawing_meta(), **(spec.meta or {})},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if spec.format == "svg":
        return Response(content=sheet_to_svg(model), media_type="image/svg+xml")
    if spec.format == "dxf":
        return Response(content=sheet_to_dxf(model), media_type="application/dxf",
                        headers={"Content-Disposition": "attachment; filename=plano.dxf"})
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
    global DOC
    data = await file.read()
    with STATE_LOCK:
        try:
            DOC = Document.from_apolo_bytes(data)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        payload = scene_payload()
    WS.notify_changed()
    return payload


class NewProjectIn(BaseModel):
    name: str = "Sin título"


@app.post("/api/project/new")
def new_project(body: NewProjectIn) -> dict:
    global DOC
    with STATE_LOCK:
        DOC = Document(body.name)
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
