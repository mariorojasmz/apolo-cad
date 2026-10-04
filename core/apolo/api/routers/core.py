"""Rutas de lectura del documento y herramientas sin estado: escena, documento, salud.

Router de la API (F6b del plan `docs/plans/partir-api-main.md`): las rutas se movieron tal cual
desde `main.py` —mismo método, path, nombre de función (= operationId), modelo, textos y
códigos—. Aquí viven la escena (completa, filtrada, resumen y delta), el documento, la salud,
los schemas, las notas y el chat del agente, el WebSocket, el croquis, el script de prueba y
las expresiones. Lo de transporte sale de `common`/`scene`/`session`; el dominio, de
`apolo.services`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from apolo.agent import AgentHooks, chat_stream
from apolo.commands import command_schemas, command_schemas_persona
from apolo.state import STATE_LOCK

from ..common import WS, _autosave, _autosave_sched, _expand_ids
from ..scene import (
    SCENE_EPOCH,
    _feature_brief,
    document_payload,
    scene_payload,
    scene_summary_dict,
)
from ..session import S

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await WS.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        WS.disconnect(ws)


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


@router.get("/api/schemas")
def get_schemas(vista: str = Query("agente", pattern="^(agente|persona)$")) -> list[dict]:
    return command_schemas() if vista == "agente" else command_schemas_persona()


@router.get("/api/schemas/{command_type}")
def get_schema(command_type: str) -> dict:
    """JSON Schema de UN comando por type (evita volcar todos)."""
    res = command_schemas(command_type)
    if not res:
        raise HTTPException(status_code=404, detail=f"No existe el comando '{command_type}'")
    return res[0]


@router.get("/api/health")
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


@router.get("/api/scene")
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


@router.get("/api/scene/summary")
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


@router.post("/api/scene/delta")
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


@router.get("/api/document")
def get_document() -> dict:
    with STATE_LOCK:
        return document_payload()


# memoria de sesión del agente IA (Document.agent_notes, persistida en el .apolo)
class AgentNoteIn(BaseModel):
    text: str


@router.get("/api/agent/notes")
def get_agent_notes() -> dict:
    with STATE_LOCK:
        return {"notes": list(S.doc.agent_notes)}


@router.post("/api/agent/notes")
def add_agent_note(body: AgentNoteIn) -> dict:
    with STATE_LOCK:
        S.doc.agent_notes.append(body.text)
        del S.doc.agent_notes[:-30]  # tope 30 (memoria acotada del agente)
        _autosave()
        return {"notes": list(S.doc.agent_notes)}


class SketchIn(BaseModel):
    sketch: dict


@router.post("/api/sketch/solve")
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


@router.post("/api/sketch/drag")
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


@router.post("/api/script/test")
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


@router.get("/api/resolve-expression")
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


@router.get("/api/expression-grammar")
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


@router.get("/api/design-guidelines")
def design_guidelines_endpoint() -> dict:
    """Criterio de ingeniería que el agente debe aplicar POR DEFECTO al diseñar (sirve para
    máquinas, muebles, estructuras, cualquier objeto): decálogo con detalle, cómo verificar
    cada regla en Apolo, cuándo preguntar vs. asumir, y ejemplos. No depende del documento."""
    from apolo.design import design_guidelines

    return design_guidelines()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatIn(BaseModel):
    messages: list[ChatMessage]
    auto: bool = False


@router.post("/api/agent/chat")
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
