"""Lo que comparten los endpoints de la API: transporte, no dominio.

Movido tal cual desde `main.py` (F6a del plan `docs/plans/partir-api-main.md`): nombres de grupo
→ feature_ids (`_expand_ids`, toma `STATE_LOCK`), el 404 con «¿quisiste decir…?»
(`_not_found`), el retorno de TODA mutación (`_state_or_error`: autosave, payload, alarma
ambiental y aviso por WebSocket), la materialización de `insert_project`, los jobs (`JOBS`,
`_sync_or_job` con su guardia de proyecto), el lock de física (`PHYSICS_LOCK`), el almacén
requerido, el cajetín de los planos (`_drawing_meta`) y, desde F6b/F6c, lo que comparten dos
routers: el borrado del comando dueño de una junta o un mate (`_remove_owner_command`) y las
reglas de stack-up del documento activo (`_stackup_rules`, envoltorio D4 que también usan
los tests por `main`). Aquí sí viven `HTTPException` y
`STATE_LOCK`; la lógica que lee un `Document` es de `apolo.services`. La guardia del documento
(`guardia_documento.py`, D3 del plan `docs/plans/chat-cliente-igual.md`) se verifica en
`_state_or_error`, en el job de `_sync_or_job` y, con `_verificar_documento`, en cada mutación
fuera de ese embudo.

Es también el KIT de los routers (`api/routers/`): lo que un endpoint necesita del autosave, del
WebSocket y de los jobs lo importa de aquí, nunca de `autosave`/`ws`/`jobs` directamente
(gate de capas en `tests/test_api_sesion.py`).
"""

from __future__ import annotations

import threading

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from apolo.commands import CommandError
from apolo.doc import DocumentError
from apolo.services.lookup import suggest_suffix
from apolo.services.stackup_eval import stackup_rules
from apolo.state import STATE_LOCK

from .autosave import (  # el resto, kit de los routers: lo importan de AQUÍ (gate de capas)
    _autosave,
    _autosave_sched,  # noqa: F401
    _flush_autosave,  # noqa: F401
    _project_switch,  # noqa: F401
)
from .guardia_documento import esperado, esperando, token, verificar
from .jobs import JOB_UNKNOWN, JobStore  # noqa: F401 — JOB_UNKNOWN: kit de los routers
from .scene import scene_payload
from .session import S
from .ws import WS


# Dos-locks (V6.2c): las simulaciones físicas (MuJoCo, potencialmente segundos) corren
# BAJO PHYSICS_LOCK y FUERA de STATE_LOCK → no congelan las mutaciones/lecturas del doc.
# Regla de oro: bajo STATE_LOCK se EXTRAE geometría (OCCT, cascos/bbox); el bucle de
# integración corre desde datos PUROS. PHYSICS_LOCK serializa sims entre sí (no contra el
# doc). El render tiene su propio RENDER_LOCK en kernel/render_vtk.py.
PHYSICS_LOCK = threading.Lock()


# Jobs (V6.5e): las mutaciones por lote pueden ENCOLARSE (?async=true) y recogerse por
# recibo → un timeout del cliente ya no deja al agente ciego. El worker corre el MISMO
# closure que el endpoint (misma atomicidad/undo/contratos/autosave), solo que fuera de
# la request. Vive en MEMORIA: un reload los pierde (son recibos, no datos).
JOBS = JobStore()


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
            if tok in S.doc.groups:
                out.extend(group_features(S.doc.scene, S.doc.groups, tok, recursive=True))
            else:
                out.append(tok)
    # dedup conservando orden
    seen: set[str] = set()
    return [x for x in out if not (x in seen or seen.add(x))]


def _not_found(missing, kind: str = "sólido") -> HTTPException:
    """404 con candidatos cercanos («¿quisiste decir…?»). Llamar bajo STATE_LOCK."""
    return HTTPException(status_code=404, detail=f"No existe el {kind} '{missing}'{suggest_suffix(S.doc, missing)}")


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


def _verificar_documento() -> None:
    """Guardia del documento para una mutación FUERA de `_state_or_error`: si la petición trae
    `X-Apolo-Documento` y no es el token del documento activo → 409 sin aplicar nada. Llamar
    BAJO `STATE_LOCK`, en la misma adquisición que la mutación y antes de tocar nada."""
    verificar(S.doc)


def _token_documento() -> str:
    """Token del documento activo (`GET /api/health` → `documento`). Bajo `STATE_LOCK`."""
    return token(S.doc)


def _state_or_error(fn):
    from apolo.library.delivery import AVISO_SIN_ANCLAJES, MIN_SOLIDOS_SUJECION

    with STATE_LOCK:
        _verificar_documento()  # antes de fn(): un 409 no deja comando, autosave ni aviso
        try:
            affected = fn()
        except (CommandError, DocumentError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _autosave()
        payload = scene_payload()
        # Alarma ambiental (V6.9-B): con ≥5 sólidos y CERO anclajes declarados, CADA
        # retorno de mutación lo recuerda — stateless y molesto a propósito (como la
        # alarma del tren de aterrizaje); se apaga al declarar el primer ground.
        # Solo en mutaciones: las lecturas (get_scene etc.) no lo llevan.
        if len(S.doc.scene) >= MIN_SOLIDOS_SUJECION and not S.doc.grounds:
            payload["aviso_estructura"] = AVISO_SIN_ANCLAJES
    payload["affected_command_ids"] = _normalize_affected(affected)
    # avisar DESPUÉS de construir el payload: el refresh de los clientes no
    # compite con esta petición por las formas OCCT
    WS.notify_changed()
    return payload


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
    if S.store is None:
        raise HTTPException(
            status_code=400,
            detail="No hay almacén de proyectos: insert_project necesita la API con startup",
        )
    if S.project_id is not None and int(pid) == S.project_id:
        raise HTTPException(
            status_code=400, detail="Un proyecto no puede instanciarse dentro de sí mismo"
        )
    try:
        data = S.store.load_bytes(int(pid))
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {**params, "attachment": S.doc.add_attachment(data)}


def _materialize_edit(command_id: str, params: dict, merge: bool) -> dict:
    """Pre-materializa un edit sobre un insert_project (refresh: {'attachment': ''}).
    Devuelve los params COMPLETOS ya fusionados y materializados; re-fusionarlos
    después (merge) es idempotente."""
    cmd = next((c for c in S.doc.commands if c["id"] == command_id), None)
    if cmd is None or cmd["type"] != "insert_project":
        return params
    full = {**cmd["params"], **params} if merge else params
    return _materialize_insert_project("insert_project", full)


def _sync_or_job(tipo: str, work, async_: bool):
    """Ejecuta ``work`` (el closure COMPLETO del endpoint) o lo encola como job (V6.5e).

    Sin ``?async``: byte-idéntico a antes de V6.5e (los clientes existentes ni se enteran).
    Con él: 202 + recibo al instante y el MISMO closure corre en el worker → misma
    atomicidad, mismo undo, mismos contratos, mismo autosave, cero código duplicado."""
    if not async_:
        return work()
    # Un job ENCOLADO no puede aplicar al proyecto EQUIVOCADO (auditoría V6.5e): se
    # captura el proyecto destino al encolar (lectura de global sin STATE_LOCK: el 202
    # debe ser instantáneo aunque haya un regenerate en curso) y se revalida DENTRO de
    # la misma adquisición del RLock que ejecuta el lote — check+mutación atómicos, sin
    # TOCTOU. Restaura las semánticas del mundo sync, donde el switch serializaba tras
    # STATE_LOCK. `restore_revision` conserva el PROJECT_ID → el lote aplica sobre la
    # revisión restaurada, igual que aplicaría en sync.
    expected = S.project_id
    # Guardia del documento (chat-cliente-igual D3): el ContextVar de la cabecera no llega al
    # hilo del worker → se captura al encolar y se re-fija allí; con cabecera, un documento
    # distinto (también una revisión restaurada con el mismo id) da 409 sin aplicar nada.
    documento = esperado()

    def guarded():
        with STATE_LOCK, esperando(documento):
            if S.project_id != expected:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"El proyecto activo cambió mientras el lote esperaba en cola "
                        f"(era {expected}, ahora {S.project_id}): el lote NO se aplicó. "
                        f"Abre el proyecto correcto y reenvíalo."
                    ),
                )
            _verificar_documento()
            return work()

    return JSONResponse(
        status_code=202, content={"job_id": JOBS.submit(tipo, guarded), "estado": "encolado"}
    )


def _store_required():
    if S.store is None:
        raise HTTPException(status_code=503, detail="Almacén de proyectos no inicializado")
    return S.store


def _drawing_meta() -> dict:
    """Cajetín: nº de plano (id de proyecto) + revisiones del proyecto (SQLite)."""
    meta: dict = {"drawing_no": str(S.project_id) if S.project_id is not None else "—"}
    store = S.store
    if store is not None and S.project_id is not None:
        try:
            revs = store.list_revisions(S.project_id)
            meta["revisions"] = [
                {"rev": i + 1, "date": r.get("created_at", r.get("date", "")), "note": r.get("note", "")}
                for i, r in enumerate(revs)
            ]
        except Exception:
            pass
    return meta


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


def _stackup_rules() -> list[dict]:
    """Envoltorio de compatibilidad (D4 del plan partir-api-main): las reglas de stack-up
    del documento ACTIVO (`services.stackup_eval.stackup_rules`). Bajo STATE_LOCK."""
    return stackup_rules(S.doc)
