"""API de Genix Apolo CAD.

La UI y el agente IA son dos clientes de esta misma API: toda operación de
modelado entra por /api/commands (o /api/commands/batch para los lotes que
propone el agente).

Este módulo es la COMPOSICIÓN (D1 del plan `docs/plans/partir-api-main.md`): la app, CORS,
el registro de errores, arranque y apagado, los routers (`api/routers/`) y el montaje de la
UI. Es además la superficie de compatibilidad de los tests: `api.DOC` & co. son alias de
`session.S` (D3) y lo que los tests usan se re-exporta por IDENTIDAD (D4). Sin lógica: una
ruta nueva va al router de su tema; lo que comparten los endpoints, a `common`.
"""

from __future__ import annotations

import asyncio
import sys
import traceback

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from apolo import paths as _paths
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
from apolo.services.fea_rules import fea_rules
from apolo.services.installation_data import installation_data as _installation_data  # noqa: F401
from apolo.services.lookup import suggest_ids
from apolo.state import STATE_LOCK  # noqa: F401 — D4: los tests lo toman de aquí

from .autosave import (  # D4: por IDENTIDAD (los tests usan los mismos objetos)
    _autosave_sched,  # noqa: F401
    _flush_autosave,
    _flush_lock,  # noqa: F401 — sólo los tests (orden de locks)
    _project_switch,  # noqa: F401
)
from .common import JOBS, _stackup_rules  # noqa: F401 — D4
from .errorlog import log_error, session_marker
from .fea_runs import (  # D4: por IDENTIDAD (los tests espían la guardia y el campo en memoria)
    _LAST_FEA_FIELD,  # noqa: F401
    _fea_owner,  # noqa: F401
    _last_fea_field,  # noqa: F401
    _persist_fea_if_same_project,  # noqa: F401
)
from .guardia_documento import CabeceraDocumento
from .routers import (
    assembly,
    commands,
    core,
    deliverables,
    drawings,
    fea,
    features,
    motion,
    projects,
    render,
    validation,
)
from .routers.projects import delete_project  # noqa: F401 — D4: un test la llama directo
from .scene import (  # D4: por IDENTIDAD (cachés mutadas en sitio por los tests)
    _DEF_MESH_CACHE,  # noqa: F401
    _GEOM_REVS,  # noqa: F401
    _cached_render,  # noqa: F401
    _definition_mesh,  # noqa: F401
    _open_briefing,  # noqa: F401
    scene_payload,  # noqa: F401
)
from .session import S, _MainModule, initialize_store, prewarm_sandbox
from .sims import StabilityIn, _stability  # noqa: F401 — D4
from .ws import WS

app = FastAPI(title="Genix Apolo CAD", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(CabeceraDocumento)  # X-Apolo-Documento → la guardia del documento (common)


# Estado de sesión (D3 del plan partir-api-main): vive en `session.S` y el código lee y swapea
# `S.<campo>`. `api.DOC`/`STORE`/`PROJECT_ID`/`AUTOSAVE_ERROR`/`STARTUP_ERROR` quedan como
# alias de `S` para los tests (leer, asignar, `monkeypatch`): los da la clase del módulo.
sys.modules[__name__].__class__ = _MainModule


@app.on_event("startup")
async def _capture_loop() -> None:
    WS.loop = asyncio.get_running_loop()
    session_marker("Inicio de sesión del servidor")
    prewarm_sandbox()  # en un hilo; antes del reciente: su replay usa el worker que ya arranca
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


# ------------------------------------------------- envoltorios de compatibilidad (D4)
def _suggest_ids(missing, limit: int = 3) -> list[str]:
    """Envoltorio de compatibilidad (D4 del plan partir-api-main): «¿quisiste decir…?» sobre
    el documento ACTIVO (`services.lookup.suggest_ids`). Llamar bajo STATE_LOCK."""
    return suggest_ids(S.doc, missing, limit)


def _fea_rules() -> list[dict]:
    """Envoltorio de compatibilidad (D4 del plan partir-api-main): las reglas FEA con
    vigencia del documento ACTIVO (`services.fea_rules.fea_rules`). Bajo STATE_LOCK."""
    return fea_rules(S.doc)


# -------------------------------------------------------------------- routers
# Cada router agrupa las rutas de un tema; las rutas que pueden casar la MISMA URL viven en
# el mismo router y en su orden de siempre (D5 del plan partir-api-main).
for _router in (core, commands, features, render, projects, deliverables, validation, motion,
                assembly, fea, drawings):
    app.include_router(_router.router)


# ------------------------------------------------------------------- UI build
# `paths.ui_dist()` resuelve la UI empaquetada (instalación pip) o el build del
# checkout; None = sin bundle → la API sirve solo /api (headless, útil para MCP).
_ui_dist = _paths.ui_dist()
if _ui_dist is not None:
    app.mount("/", StaticFiles(directory=str(_ui_dist), html=True), name="ui")
