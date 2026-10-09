"""Coreografía del FEA en la API: fases, tmp dir, guardia de proyecto y campo en memoria.

Movido tal cual desde `main.py` (F6a del plan `docs/plans/partir-api-main.md`; D8). Patrón
dos-locks: (a) bajo `STATE_LOCK`, la preparación de `services/fea_setup.py` + el tmp dir + el
STEP; (b) malla y solve FUERA del lock (sólo el `FEA_LOCK` interno del solver); (c) bajo
`STATE_LOCK`, persistir SÓLO si el documento activo sigue siendo el del solve
(`_persist_fea_if_same_project`). El campo del último solve (`_LAST_FEA_FIELD`) vale sólo para su
documento: su dueño es `_LAST_FEA_OWNER`, que vive AQUÍ — un test lo parchea en
`apolo.api.fea_runs`, no en `main` (D4 c). Con `X-Apolo-Documento` (guardia del documento,
plan chat-cliente-igual D3) la fase (a) verifica el token: uno ajeno → 409 antes de preparar
nada; la (c) ya compara la IDENTIDAD del documento, que es lo que el token nombra.
"""

from __future__ import annotations

import weakref
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel

from apolo.kernel import export_step_file
from apolo.services.errors import ServiceError
from apolo.services.fea_setup import (
    merge_convergence,
    prepare_assembly,
    prepare_static,
    resolve_assembly_scope,
)
from apolo.state import STATE_LOCK

from .autosave import _autosave
from .guardia_documento import verificar as _verificar_documento
from .session import S


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


class FeaAsmLoadIn(BaseModel):
    feature_id: str                       # la carga se resuelve contra ESTA pieza
    selector: dict                        # selector declarativo de sus caras
    force_n: list[float] | None = None
    pressure_mpa: float | None = None


class FeaAssemblyIn(BaseModel):
    """FEA BONDED de un sub-ensamblaje (V7.4): un GRUPO o lista de piezas pegadas."""
    group: str | None = None              # nombre de grupo (o usa ids)
    ids: list[str] | None = None          # o piezas explícitas
    name: str | None = None               # etiqueta si se pasan ids sueltos
    carga_kg: float | None = None         # carga de diseño (si None → requirements.carga_kg)
    self_weight: bool = True              # peso propio (por defecto SÍ en un bastidor)
    yield_mpa: float | None = None        # σy de respaldo para piezas sin σy tabulado
    loads: list[FeaAsmLoadIn] = []        # cargas EXPLÍCITAS (si vacío → auto sobre la cama/mesa)
    fixed_pieces: list[str] | None = None  # empotrar la base de estas piezas (si None → grounds ∩ grupo)
    mesh_size_mm: float | None = None
    fs_min: float = 2.0
    save: bool = True
    nota: str | None = None               # nota del ANALISTA (alcance/limitaciones) → hipótesis


_LAST_FEA_FIELD: dict = {}  # feature_id → FeaField del último solve (fringe, no persiste)
# Dueño del campo en memoria: (PROJECT_ID, weakref al DOC del solve). Los feature_ids
# («c12») se repiten entre proyectos → sin dueño, el fringe «sin re-resolver» serviría
# el campo de OTRO proyecto tras abrir uno nuevo.
_LAST_FEA_OWNER: tuple | None = None


def _fea_owner() -> tuple:
    """Identidad del documento activo (PROJECT_ID, DOC) para el patrón dos-locks del
    FEA: se captura en la fase (a), BAJO STATE_LOCK, y se revalida en la (c)."""
    return (S.project_id, S.doc)


def _persist_fea_if_same_project(owner: tuple, key: str, resumen: dict, field,
                                 save: bool, before_save=None) -> dict:
    """Fase (c) del FEA: persiste el resumen y publica el campo SOLO si el documento
    activo sigue siendo el del solve. El solve corre FUERA de STATE_LOCK (minutos): si
    entretanto se abrió/creó otro proyecto o se restauró una revisión (DOC reemplazado),
    guardar escribiría el resultado en el documento EQUIVOCADO → NO se guarda y se
    devuelve el resultado con `aviso`. Mismo patrón que la guardia de jobs
    (`_sync_or_job`): check + escritura atómicos en UNA adquisición del lock, sin TOCTOU.
    `before_save(doc, resumen)` corre bajo el lock justo antes de guardar (historial de
    convergencia del ensamblaje)."""
    global _LAST_FEA_OWNER
    pid, doc = owner
    with STATE_LOCK:
        if S.project_id != pid or S.doc is not doc:
            if save:
                resumen["guardado"] = False
                resumen["aviso"] = (
                    f"El proyecto activo cambió durante el análisis (era {pid}, ahora "
                    f"{S.project_id}): el resultado NO se guardó para no escribirlo en el "
                    f"documento equivocado. Abre el proyecto analizado y re-ejecuta el FEA."
                )
            return resumen  # el campo tampoco se publica: es de otro documento
        if save:
            if before_save is not None:
                before_save(S.doc, resumen)
            S.doc.set_fea_result(key, resumen)
            _autosave()
        _LAST_FEA_FIELD.clear()
        _LAST_FEA_FIELD[key] = field
        _LAST_FEA_OWNER = (pid, weakref.ref(doc))
    return resumen


def _last_fea_field(key: str):
    """Campo FEA en memoria de `key`, SOLO si pertenece al documento activo."""
    with STATE_LOCK:
        field = _LAST_FEA_FIELD.get(key)
        if field is None or _LAST_FEA_OWNER is None:
            return None
        pid, ref = _LAST_FEA_OWNER
        if pid != S.project_id or ref() is not S.doc:
            _LAST_FEA_FIELD.clear()  # de otro proyecto: no retener su malla
            return None
        return field


def _http_error(exc: ServiceError) -> HTTPException:
    """Un error de dominio de `services` (D8) → el 400/404 con su texto EXACTO."""
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _fea_static_run(body: FeaStaticIn):
    """Patrón dos-locks: (a) STATE_LOCK resuelve material/selectores y exporta el
    STEP; (b) SIN lock (solo FEA_LOCK interno) malla y resuelve; (c) STATE_LOCK
    persiste el resumen. El solve nunca serializa al resto del server."""
    import shutil
    import tempfile

    from apolo.fea import FeaError

    with STATE_LOCK:
        _verificar_documento(S.doc)  # guarda en DOC.fea: un token ajeno no llega al solve
        try:  # validación + material + selectores: services/fea_setup.py
            prep = prepare_static(S.doc, body)
        except ServiceError as exc:
            raise _http_error(exc) from exc
        feat = prep["feat"]
        tmp_dir = tempfile.mkdtemp(prefix="apolo_fea_step_")
        step = str(Path(tmp_dir) / "pieza.step")
        export_step_file([feat.shape], step)
        pieza, vol = feat.name, float(feat.shape.volume)
        owner = _fea_owner()

    try:
        from apolo.fea.static import run_static_analysis

        resumen, field = run_static_analysis(
            step, pieza=pieza, fixed=prep["fixed"], loads=prep["loads"], e_mpa=prep["e_mpa"],
            yield_mpa=prep["sy"], density_kg_mm3=prep["rho"], material=prep["material"],
            self_weight=body.self_weight, mesh_size_mm=body.mesh_size_mm,
            fs_min=body.fs_min,
        )
    except FeaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    resumen["feature_id"] = body.feature_id
    resumen["volumen_mm3"] = round(vol, 1)
    _persist_fea_if_same_project(owner, body.feature_id, resumen, field, body.save)
    return resumen, field


def _hipotesis_empernadas(n: int) -> str:
    """El bonded pega las juntas con perno: se DECLARA (D8 de fea-chapa-empernada). El conteo
    es de `services/fea_setup.py::bolted_joints_in_mesh`."""
    if n == 1:
        return ("1 unión empernada modelada PEGADA sobre su superficie de contacto (sin "
                "deslizamiento ni separación: más rígida que la junta real); el perno se "
                "verifica aparte (engineering_check)")
    return (f"{n} uniones empernadas modeladas PEGADAS sobre sus superficies de contacto (sin "
            f"deslizamiento ni separación: más rígidas que las juntas reales); los pernos se "
            f"verifican aparte (engineering_check)")


def _fea_assembly_run(body: FeaAssemblyIn):
    """FEA BONDED de un sub-ensamblaje (V7.4). Patrón dos-locks igual que la pieza:
    (a) STATE_LOCK expande el grupo, resuelve material/selectores, deriva
    empotramiento (grounds) y carga (requisitos sobre la cama), exporta un STEP por
    pieza; (b) SIN lock malla+resuelve (bonded); (c) STATE_LOCK persiste (clave
    `group:<nombre>`, vigencia por volumen conjunto). El herraje de catálogo se EXCLUYE
    de la malla y su peso entra como carga sustituta DECLARADA; las uniones empernadas entre
    piezas malladas, que el bonded pega, también se declaran en la hipótesis."""
    import shutil
    import tempfile

    from apolo.fea import FeaError

    tmp_dir = None
    with STATE_LOCK:  # la preparación es de services/fea_setup.py; el tmp dir, de aquí
        _verificar_documento(S.doc)
        try:
            fids, grupo = resolve_assembly_scope(S.doc, body)
        except ServiceError as exc:
            raise _http_error(exc) from exc
        tmp_dir = tempfile.mkdtemp(prefix="apolo_fea_asm_step_")
        try:
            params = prepare_assembly(S.doc, body, fids, grupo, tmp_dir)
        except ServiceError as exc:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise _http_error(exc) from exc
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            raise
        owner = _fea_owner()

    try:
        from apolo.fea.assembly import run_assembly_analysis

        resumen, field = run_assembly_analysis(
            params["pieces"], grupo=params["grupo"], fixed=params["fixed"],
            loads=params["loads"], self_weight=body.self_weight,
            excluded=params["excluded"], substitute_applied=params["substitute_applied"],
            mesh_size_mm=body.mesh_size_mm, fs_min=body.fs_min,
        )
    except FeaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    key = f"group:{params['grupo']}"
    resumen["fea_key"] = key
    resumen["volumen_mm3"] = round(sum(p["volumen_mm3"] for p in params["pieces"]), 1)
    resumen["piezas_fids"] = params["struct_ids"]
    if params["uniones_empernadas"]:
        resumen["hipotesis"].append(_hipotesis_empernadas(params["uniones_empernadas"]))
    if body.ids:
        # alcance ACOTADO (ids explícitos, no un grupo completo): declararlo — lo no
        # incluido no aporta rigidez y sus pesos deben entrar como loads
        resumen["hipotesis"].append(
            f"alcance: análisis acotado a los {len(params['pieces'])} sólidos declarados "
            f"(«{params['grupo']}») — lo no incluido no aporta rigidez; sus cargas entran "
            f"como fuerzas aplicadas"
        )
    if body.nota:
        resumen["hipotesis"].append(f"nota del analista: {body.nota}")

    _persist_fea_if_same_project(
        owner, key, resumen, field, body.save,
        before_save=lambda doc, res: merge_convergence(doc, key, res))
    return resumen, field
