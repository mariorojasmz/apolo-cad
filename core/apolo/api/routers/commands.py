"""Rutas que mutan el log de comandos: comando, lote (con contrato), edición, borrado, búsqueda.

Router de la API (F6c del plan `docs/plans/partir-api-main.md`): movidas tal cual desde
`main.py`. Toda mutación pasa por `_state_or_error`; los lotes pueden encolarse como job
(`?async=true`, `_sync_or_job`) y aceptan contrato (`expect`). También las variables, el
undo/redo, las variantes (tablas de diseño), los jobs y el preview fantasma. El ORDEN importa:
`batch` y `preview` van antes que `PUT /api/commands/{command_id}` y éste antes que `remove`
(Starlette sirve la primera ruta que casa; también decide el `Allow` de un 405).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from apolo.doc import DocumentError
from apolo.kernel import bbox_payload
from apolo.library import interference_report
from apolo.services.assertions import contract_verify
from apolo.state import STATE_LOCK

from ..common import (
    JOB_UNKNOWN,
    JOBS,
    _expand_ids,
    _materialize_edit,
    _materialize_insert_project,
    _not_found,
    _state_or_error,
    _sync_or_job,
)
from ..session import S

router = APIRouter()


class CommandIn(BaseModel):
    type: str
    params: dict = {}


@router.post("/api/commands")
def post_command(cmd: CommandIn) -> dict:
    return _state_or_error(
        lambda: S.doc.execute(cmd.type, _materialize_insert_project(cmd.type, cmd.params))
    )


class BatchIn(BaseModel):
    actions: list[CommandIn]
    # CONTRATO opcional (V6.5b, frente A): aserciones estilo `verify` que deben cumplirse
    # tras el lote; si alguna falla, el lote se revierte por completo (doc intacto).
    expect: list[dict] = []


@router.post("/api/commands/batch")
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


@router.patch("/api/commands/batch")
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


@router.get("/api/jobs")
def list_jobs() -> dict:
    """Los últimos jobs retenidos, sin `resultado` (payload grande). Telemetría."""
    return {"jobs": JOBS.briefs()}


@router.get("/api/jobs/{job_id}")
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


@router.post("/api/commands/preview")
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


@router.put("/api/commands/{command_id}")
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


@router.post("/api/commands/remove")
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


@router.get("/api/commands")
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


class VariableIn(BaseModel):
    name: str
    expression: str


@router.post("/api/variables")
def set_variable(body: VariableIn) -> dict:
    def run():  # buscar DENTRO del lock: fuera, otra petición podía cambiar el log antes de mutar
        params = {"name": body.name, "expression": body.expression}
        existing = next((c["id"] for c in S.doc.commands if c["type"] == "set_variable"
                         and c["params"].get("name") == body.name), None)
        return S.doc.edit(existing, params) if existing else S.doc.execute("set_variable", params)

    return _state_or_error(run)


@router.delete("/api/variables/{name}")
def delete_variable(name: str) -> dict:
    def run():  # búsqueda y borrado en UNA adquisición de STATE_LOCK (sin TOCTOU)
        ids = [c["id"] for c in S.doc.commands
               if c["type"] == "set_variable" and c["params"].get("name") == name]
        if not ids:
            raise HTTPException(status_code=404, detail=f"No existe la variable '{name}'")
        return S.doc.remove_commands(ids)

    return _state_or_error(run)


# `S.doc` se lee DENTRO del lock (lambda): el método ligado afuera apuntaría al documento de
# antes de un cambio de proyecto, no al que la guardia del documento verificó.
@router.post("/api/undo")
def undo() -> dict:
    return _state_or_error(lambda: S.doc.undo())


@router.post("/api/redo")
def redo() -> dict:
    return _state_or_error(lambda: S.doc.redo())


class ConfigIn(BaseModel):
    name: str
    # columnas NUEVAS de la tabla de diseño; la primera variante las necesita (sin columnas → 400)
    variables: list[str] | None = None


@router.post("/api/configurations")
def save_configuration(body: ConfigIn) -> dict:
    """Variante con el valor ACTUAL de las columnas de la tabla ∪ `variables`, SIN aplicarla."""
    return _state_or_error(lambda: S.doc.save_configuration(body.name.strip(), body.variables))


class ConfigValuesIn(BaseModel):
    values: dict[str, str]  # {variable: expresión} — V6.4c edición explícita de una variante


@router.put("/api/configurations/{name}")
def set_configuration(name: str, body: ConfigValuesIn) -> dict:
    """Crea o edita una variante con {variable: expresión} SIN aplicarla; una clave que no era
    columna entra en TODAS las variantes con su expresión actual (tabla rectangular)."""
    return _state_or_error(lambda: S.doc.set_configuration(name, body.values))


@router.post("/api/configurations/{name}/apply")
def apply_configuration(name: str) -> dict:
    """Aplica una variante; el payload suma `cambios` [{variable, antes, despues}] y, si hay,
    `aviso`. Se miden DENTRO del lock, antes de mutar."""
    hecho: dict = {}
    payload = _state_or_error(lambda: hecho.update(S.doc.apply_configuration(name)))
    payload["cambios"] = hecho["cambios"]
    if hecho.get("aviso"):
        payload["aviso"] = hecho["aviso"]
    return payload


@router.delete("/api/configurations/{name}")
def delete_configuration(name: str) -> dict:
    return _state_or_error(lambda: S.doc.delete_configuration(name))


@router.delete("/api/configuration-columns/{variable}")
def delete_configuration_column(variable: str) -> dict:
    """Quita una variable de la tabla de variantes (de TODAS); sigue siendo variable del
    proyecto. Prefijo propio para no solaparse con `/api/configurations/{name}/…`."""
    return _state_or_error(lambda: S.doc.delete_configuration_column(variable))
