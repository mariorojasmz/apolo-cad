"""Rutas de proyectos: listar, crear, abrir, borrar, revisiones, importar y exportar.

Router de la API (F6b del plan `docs/plans/partir-api-main.md`): movidas tal cual desde
`main.py`. Todo cambio de documento activo pasa por `_project_switch()` (flush del actual +
swap ATÓMICO bajo `_flush_lock → STATE_LOCK`) y swapea `S.doc`/`S.project_id`, nunca un
global. Un proyecto abierto por upload o nuevo recibe id PROPIO. Abrir, crear o restaurar
toma el candado del proyecto y suelta el del que se deja (D4 de
`docs/plans/varias-maquinas-a-la-vez.md`): uno abierto en otro proceso vivo da 409.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from apolo.doc import Document, DocumentError
from apolo.doc.solo_lectura import aviso, detectar
from apolo.kernel import export_step_file
from apolo.state import STATE_LOCK

from ..common import (
    WS,
    candado,
    _flush_autosave,
    _project_switch,
    _state_or_error,
    _store_required,
)
from ..scene import _open_briefing, scene_payload
from ..session import S

router = APIRouter()


@router.get("/api/projects")
def list_projects() -> list[dict]:
    return _store_required().list_projects()


class ProjectIn(BaseModel):
    name: str = "Sin título"
    template: str | None = None  # "transportador" | "brazo" | None


@router.post("/api/projects")
def create_project(body: ProjectIn) -> dict:
    store = _store_required()
    with _project_switch():  # V6.2e: flush del doc actual + swap ATÓMICO (sin corrupción cruzada)
        S.doc = Document(body.name)
        if body.template == "transportador":
            S.doc.execute("set_variable", {"name": "L", "expression": "2000"})
            S.doc.execute("create_conveyor", {"largo": "=L", "ancho": 600, "altura": 750, "paso": 100})
        elif body.template == "brazo":
            S.doc.execute("create_robot_arm", {"name": "Robot", "alcance": 700})
        actual, S.project_id = S.project_id, store.create(S.doc)
        candado.tras_crear(store, S.project_id, actual)
        payload = scene_payload()
    WS.notify_changed()
    return payload


@router.post("/api/projects/{project_id}/open")
def open_project_by_id(project_id: int) -> dict:
    store = _store_required()
    with _project_switch():  # V6.2e: flush del doc actual + swap ATÓMICO (sin corrupción cruzada)
        with candado.cambio_a(store, project_id, S.project_id):  # D4: 409 si es de otro vivo
            try:
                S.doc = store.load(project_id, tolerant=True)  # suprime comandos rotos (drift)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except DocumentError as exc:  # ZIP roto / no regenera: 400 claro (antes: 500 opaco)
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            S.project_id = project_id
        payload = scene_payload()
        payload["briefing"] = _open_briefing()  # V6.5b: arranque de sesión en 1 llamada
    WS.notify_changed()
    return payload


@router.delete("/api/projects/{project_id}")
def delete_project(project_id: int) -> dict:
    store = _store_required()
    with STATE_LOCK:  # check + borrado atómicos: un open concurrente no lo activa entre medio
        if project_id == S.project_id:
            raise HTTPException(status_code=400, detail="No puedes borrar el proyecto abierto")
        otro = candado.ajeno_vivo(store, project_id)  # D4: abierto en otro proceso → 409
        if otro is not None:
            raise HTTPException(status_code=409, detail=candado.mensaje_ocupado(project_id, otro))
        store.delete(project_id)
    return {"ok": True}


@router.post("/api/projects/{project_id}/duplicate")
def duplicate_project(project_id: int) -> dict:
    """Copia el log TAL CUAL. Uno que usa una extensión ausente se copia igual (la carga lo
    marca y abre tolerante, D4 de nucleo-abierto F1b) y la copia también abre en sólo lectura."""
    try:
        new_id = _store_required().duplicate(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DocumentError as exc:  # ZIP roto / no regenera: 400 claro (antes: 500 opaco)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"id": new_id}


class RenameIn(BaseModel):
    name: str


@router.patch("/api/projects/current")
def rename_project(body: RenameIn) -> dict:
    def run():
        S.doc.name = body.name.strip() or "Sin título"

    return _state_or_error(run)


class RevisionIn(BaseModel):
    note: str = ""


@router.post("/api/revisions")
def save_revision(body: RevisionIn) -> dict:
    store = _store_required()
    if S.project_id is None:
        raise HTTPException(status_code=400, detail="No hay proyecto abierto")
    _flush_autosave()  # V6.2d: el proyecto en disco al día antes de fijar la revisión
    with STATE_LOCK:
        rev_id = store.save_revision(S.project_id, S.doc, body.note)
    return {"id": rev_id}


@router.get("/api/revisions")
def list_revisions() -> list[dict]:
    store = _store_required()
    if S.project_id is None:
        return []
    return store.list_revisions(S.project_id)


def _sin_extension_ausente(store, project_id: int, revision) -> None:
    """D4 (nucleo-abierto F1b): restaurar REEMPLAZA el log guardado del proyecto. 409 si ese log
    usa una extensión ausente (se perderían sus comandos) o si la revisión la usa (restaurada,
    quedaría en sólo lectura y el autosave no la guardaría: el disco no la reflejaría)."""
    try:
        actual = Document.from_apolo_bytes(store.load_bytes(project_id), regenerate=False)
    except (KeyError, DocumentError):
        actual = None  # sin log legible que proteger
    marca = actual is not None and detectar(actual.commands, actual.attachments)
    if marca:
        raise HTTPException(status_code=409, detail=aviso(
            marca["extensiones"], "Este proyecto", "puedes verlo, no restaurar una revisión sobre él"))
    if revision.solo_lectura:
        raise HTTPException(status_code=409, detail=aviso(
            revision.solo_lectura["extensiones"], "Esta revisión", "no se puede restaurar aquí"))


@router.post("/api/revisions/{revision_id}/restore")
def restore_revision(revision_id: int) -> dict:
    store = _store_required()
    with _project_switch():  # V6.2e: flush del doc actual + swap ATÓMICO
        try:
            project_id, doc = store.load_revision(revision_id, tolerant=True)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _sin_extension_ausente(store, project_id, doc)
        with candado.cambio_a(store, project_id, S.project_id):  # D4: 409 si es de otro vivo
            S.doc = doc
            S.project_id = project_id
        payload = scene_payload()
    _flush_autosave(force=True)  # persiste YA el doc restaurado (no esperar la ventana)
    WS.notify_changed()
    return payload


@router.post("/api/import")
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


@router.get("/api/export/step")
def export_step() -> FileResponse:
    with STATE_LOCK:
        shapes = [f.shape for f in S.doc.scene.values() if f.visible]
        if not shapes:
            raise HTTPException(status_code=400, detail="No hay sólidos visibles que exportar")
        tmp = Path(tempfile.mkstemp(suffix=".step")[1])
        export_step_file(shapes, str(tmp))
    return FileResponse(tmp, filename=f"{S.doc.name or 'modelo'}.step", media_type="model/step")


@router.get("/api/export/stl")
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


@router.get("/api/project/file")
def download_project() -> Response:
    with STATE_LOCK:
        content = S.doc.to_apolo_bytes()
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "proyecto"}.apolo"'},
    )


@router.post("/api/project/open")
async def open_project(file: UploadFile) -> dict:
    data = await file.read()
    with _project_switch():  # V6.2e: flush del doc actual + swap ATÓMICO
        try:
            S.doc = Document.from_apolo_bytes(data, tolerant=True)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        # E2: un proyecto NUEVO en la BD — el siguiente autosave NO debe pisar el que
        # estaba abierto antes (sin esto, PROJECT_ID seguía apuntando al anterior)
        actual = S.project_id
        S.project_id = S.store.create(S.doc) if S.store is not None else None
        candado.tras_crear(S.store, S.project_id, actual)
        payload = scene_payload()
    WS.notify_changed()
    return payload


class NewProjectIn(BaseModel):
    name: str = "Sin título"


@router.post("/api/project/new")
def new_project(body: NewProjectIn) -> dict:
    with _project_switch():  # V6.2e: flush del doc actual + swap ATÓMICO
        S.doc = Document(body.name)
        actual = S.project_id
        S.project_id = S.store.create(S.doc) if S.store is not None else None  # E2: id propio
        candado.tras_crear(S.store, S.project_id, actual)
        payload = scene_payload()
    WS.notify_changed()
    return payload
