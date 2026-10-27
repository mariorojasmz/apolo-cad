"""Rutas de validación: chequeos, aserciones `verify`, puerta de entrega, puerta de publicación,
requisitos (y la identificación comercial del proyecto, que viaja con ellos), stack-up y los
tensores, funciones y justificaciones declarados (metadatos de la puerta de publicación).

Router de la API (F6c del plan `docs/plans/partir-api-main.md`): movidas tal cual desde
`main.py`. El dominio (aserciones, insumos de la puerta, reglas de ingeniería, evaluación de
cadenas) es de `apolo.services`; aquí queda el transporte y las diferencias DELIBERADAS de
`/api/checks` frente a la memoria (D7). El `PUT /api/stackup` hace ROLLBACK si la cadena no
evalúa.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from apolo.doc import DocumentError
from apolo.library import conveyor_engineering_check, interference_report
from apolo.services import conexiones
from apolo.services import reglas_cortas as rc
from apolo.services.assertions import verify_checks
from apolo.services.delivery_inputs import delivery_inputs, exclusiones_declaradas
from apolo.services.engineering_rules import (
    conveyor_params_from_doc,
    inherit_inclination,
    inherit_tensor,
    requirement_inputs,
    structure_rules,
)
from apolo.services.interferencias import como_acotar
from apolo.services.stackup_eval import evaluate_stackups
from apolo.state import STATE_LOCK

from ..common import (
    PHYSICS_LOCK,
    _autosave,
    _expand_ids,
    _job_cosim,
    _mismo_proyecto,
    _verificar_documento,
)
from ..session import S
from ..sims import StabilityIn, _stability

router = APIRouter()


class ChecksIn(BaseModel):
    carga_kg: float | None = None
    largo_paquete_mm: float | None = None
    ancho_paquete_mm: float | None = None
    velocidad_m_s: float = 0
    joint_values: dict[str, float] = {}
    conveyor: dict | None = None  # validación predictiva: params de faja a evaluar sin construirla
    conveyor_solid_ids: list[str] | None = None  # marca explícita de los sólidos que forman la faja
    interference_ids: list[str] | None = None  # V6.5b: acota la interferencia a pares que tocan estos ids/grupos
    # mcp-sin-friccion D10: página de parejas candidatas y el criterio de la puerta (sin lo declarado)
    interference_desde: int = 0
    excluir_declaradas: bool = False
    # mcp-sin-friccion D1/D2 (`services/reglas_cortas.py`): sin ellos, byte-idéntico (la UI)
    grupo: str | None = None  # familia de regla («unión apernada», «flecha de viga»…)
    solo_fallas: bool = False  # sólo lo que no está «ok»
    resumen: bool = False  # patrones repetidos en una línea con su peor caso, sin `calc` salvo error


@router.post("/api/checks")
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
        excl_pares, excl_ids = (exclusiones_declaradas(S.doc) if body.excluir_declaradas
                                else (set(), set()))
        interferencias = interference_report(
            S.doc.scene, shapes_override=shapes_override,
            exclude_pairs=jpairs | same_command_pairs(S.doc) | excl_pares,
            exclude_ids=hardware_ids(S.doc) | excl_ids,
            focus=focus, desde=body.interference_desde,
        )
        if interferencias["truncado"]:  # D4/D10 de mcp-sin-friccion: la página siguiente y zonas
            interferencias["como_acotar"] = como_acotar(
                S.doc, interferencias, body.interference_ids, body.excluir_declaradas)
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
                or detect_conveyor(S.doc.scene, S.doc.variables_resolved, S.doc.fasteners)
            )
            inherit_inclination(conveyor, req)
            inherit_tensor(S.doc, conveyor)
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
            material_vertical=S.doc.default_material(),
        )
    out = {"interferencias": interferencias, "ingenieria": ingenieria, "estructura": estructura}
    if body.grupo or body.solo_fallas or body.resumen:
        for k in ("ingenieria", "estructura"):
            out[k] = rc.filtrar_reglas(out[k], body.grupo, body.solo_fallas)
        if body.resumen:  # D12: las de cada unión, por el par de piezas; lo «ok», sin detalle
            out["conteo"] = {k: rc.conteo(out[k]) for k in ("ingenieria", "estructura")}
            with STATE_LOCK:  # la clave lee las uniones y los nombres del documento
                clave = conexiones.clave_de_reglas(S.doc)
                for k in ("ingenieria", "estructura"):
                    out[k] = rc.reglas_cortas(out[k], clave, ok_sin_detalle=not body.grupo)
    return out


class VerifyIn(BaseModel):
    checks: list[dict] = []


@router.post("/api/verify")
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


@router.post("/api/delivery-check")
def delivery_check_endpoint(body: DeliveryIn) -> dict:
    """PUERTA DE ENTREGA (V6.9): corre la batería de cierre y devuelve el SEMÁFORO
    {veredicto VERDE|AMARILLO|ROJO, bloqueantes, avisos, no_aplica, resumen}. Agregación
    PURA de chequeos existentes (library/delivery.py): interferencias en DISEÑO
    (exclusiones normales) + sujeción DECLARADA (soundness SIN autodetect — la puerta
    valida lo que el modelo declara, no lo que un detector adivina) + lints pre-entrega
    + integridad/suprimidos + colisión EN POSE en los fotogramas de REPOSO de los
    estudios declarados (extremos + dwells; asiento ≤ tolerancia declarado, no bloquea).
    `con_gravedad` añade la simulación MuJoCo (cara; opt-in). Read-only. `tiempos_s` dice
    cuánto tardó en total y cada regla (mcp-sin-friccion D4)."""
    from apolo.library.delivery import delivery_report

    t0 = time.perf_counter()
    tiempos: dict = {}
    gravedad = None
    if body.con_gravedad:
        # dos-locks propio (_stability); with_autodetect=False: la puerta es DECLARADA, y su
        # tornillería, asentada (como en su sujeción)
        res = _stability(StabilityIn(with_autodetect=False), tornilleria_asentada=True)
        gravedad = {k: res.get(k) for k in ("fell", "estables", "settled", "n_grounded")}
        tiempos["gravedad"] = round(time.perf_counter() - t0, 2)

    with STATE_LOCK:  # la puerta valida lo DECLARADO: services/delivery_inputs.py
        out = delivery_report(**delivery_inputs(S.doc, expand=_expand_ids, tiempos=tiempos),
                              gravedad=gravedad)
    out["tiempos_s"] = {"total": round(time.perf_counter() - t0, 2), "por_regla": tiempos}
    return out


@router.post("/api/puerta-publicacion", response_model=dict)
def puerta_publicacion(async_: bool = Query(False, alias="async")):
    """PUERTA DE PUBLICACIÓN (plan puerta-de-publicacion, F1): el registro de ítems de calidad
    (`library/calidad/registro.py`) sobre el documento activo → {aprobado, items, por_familia,
    conteos, mantenimiento, firma, version_registro, tiempos_s}. Read-only. Corre la gravedad (sin
    MuJoCo o si falla: SIN_EVALUAR, nunca la caída silenciosa) y simula la marcha del video; las
    dos FUERA de `STATE_LOCK` con `PHYSICS_LOCK` (dos locks). Tarda: con `?async=true` va como JOB
    a `COSIM_JOBS` (la cola de las simulaciones largas) y vuelve el recibo."""
    return _job_cosim("puerta_publicacion", _puerta_publicacion, async_)


def _gravedad_obligatoria() -> dict:
    """La gravedad de la puerta (dos locks propios, `_stability`, sujeción DECLARADA y la
    tornillería asentada: su casco convexo no cabe en el barreno). Si no corre, `resultado` None
    y el porqué: el ítem sale SIN_EVALUAR."""
    try:
        res = _stability(StabilityIn(with_autodetect=False), tornilleria_asentada=True)
    except HTTPException as exc:
        return {"resultado": None, "motivo": str(exc.detail)}
    except Exception as exc:  # noqa: BLE001 — sin MuJoCo (ImportError) u otro fallo del motor
        return {"resultado": None, "motivo": f"{type(exc).__name__}: {exc}"}
    return {"resultado": {k: res.get(k) for k in ("fell", "estables", "settled", "n_grounded")},
            "motivo": ""}


def _misma_firma(firma: str) -> None:
    """Bajo STATE_LOCK: la puerta evalúa UN modelo; si cambió mientras corría la gravedad o la
    marcha, 409 (el veredicto mezclaría dos modelos)."""
    from apolo.services.puerta_publicacion import firma as firma_de

    if firma_de(S.doc) != firma:
        raise HTTPException(status_code=409, detail=(
            "El modelo cambió mientras corría la puerta de publicación: no doy un veredicto que "
            "mezcle dos modelos. Vuelve a correrla cuando termines de editar."))


def _puerta_publicacion(proyecto) -> dict:
    from apolo.library.calidad.registro import evaluar, vigente
    from apolo.services import marcha_ejemplo as me
    from apolo.services import puerta_publicacion as pp
    from apolo.services.calidad_sobrantes import marcar_primera_corrida

    registro = vigente()  # el del núcleo más los ítems de las extensiones cargadas (F1d)
    t0 = time.perf_counter()
    tiempos: dict = {}
    with STATE_LOCK:
        _mismo_proyecto(proyecto)
        firma = pp.firma(S.doc)
        if marcar_primera_corrida(S.doc):  # D9 de puerta-sin-sobrediseno: lo de después, «agregado»
            _autosave()
    gravedad = _gravedad_obligatoria()  # (a) STATE_LOCK extrae, (b) PHYSICS_LOCK simula
    tiempos["gravedad"] = round(time.perf_counter() - t0, 2)
    with STATE_LOCK:
        _mismo_proyecto(proyecto)
        _misma_firma(firma)
        insumos = pp.reunir(S.doc, expand=_expand_ids, gravedad=gravedad, registro=registro,
                            tiempos=tiempos)
        t = time.perf_counter()
        animadas = insumos["hechos"]["elementos"].get("sustitutos_animados")
        prep = (pp.preparar_marcha(S.doc) if animadas else
                {"resultado": "sin_marcha", "detalle": "nada se dibuja en lugar de su sólido"})
    res = error = None
    if "snap" in prep:
        try:
            with PHYSICS_LOCK:
                res = me.simular_prueba(prep["snap"])
        except me.SinMarcha as exc:
            error = str(exc)
    insumos["marcha"] = pp.concluir_marcha(prep, res, error, desde=t)
    tiempos["marcha"] = round(time.perf_counter() - t, 2)
    with STATE_LOCK:
        _mismo_proyecto(proyecto)
        _misma_firma(firma)
    tiempos["total"] = round(time.perf_counter() - t0, 2)
    return evaluar(insumos, registro)


class RequirementsIn(BaseModel):
    fields: dict = {}
    # la identificación comercial (cotizacion-identificada D1); sin ella no se toca, y con ella
    # sola (sin `fields`) los requisitos tampoco
    comercial: dict | None = None


@router.get("/api/requirements")
def get_requirements() -> dict:
    with STATE_LOCK:
        out = {"requirements": S.doc.requirements}
        if S.doc.comercial:  # sólo si hay: sin ella, la respuesta de siempre
            out["comercial"] = S.doc.comercial
        return out


@router.put("/api/requirements")
def put_requirements(body: RequirementsIn) -> dict:
    from apolo.library.comercial import normalizar
    from apolo.services.identificacion import poner_comercial

    with STATE_LOCK:
        _verificar_documento()  # mutación fuera de _state_or_error: guardia a mano
        try:
            comercial = None if body.comercial is None else normalizar(body.comercial)
            if body.comercial is None or "fields" in body.model_fields_set:
                S.doc.set_requirements(body.fields)
            if comercial is not None:  # validada antes de tocar nada
                poner_comercial(S.doc, comercial)
        except (DocumentError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _autosave()
        out = {"ok": True, "requirements": S.doc.requirements}
        if comercial is not None:
            out["comercial"] = S.doc.comercial
        return out


@router.get("/api/project/comercial")
def get_comercial() -> dict:
    """La identificación comercial del proyecto (D1: titulo, cliente, numero, revision) y la que
    usará la cotización (`efectiva`, con su `fuente`: proyecto, una extensión o el nombre)."""
    from apolo.services.identificacion import identificacion

    with STATE_LOCK:
        return {"comercial": S.doc.comercial, "efectiva": identificacion(S.doc)}


@router.put("/api/project/comercial")
def put_comercial(body: dict) -> dict:
    """Reemplaza la identificación comercial (`{}` la borra); un campo desconocido → 400."""
    from apolo.services.identificacion import poner_comercial

    with STATE_LOCK:
        _verificar_documento()  # mutación fuera de _state_or_error: guardia a mano
        try:
            poner_comercial(S.doc, body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _autosave()
        return {"ok": True, "comercial": S.doc.comercial}


class TensoresIn(BaseModel):
    tensores: list = []


@router.get("/api/tensores")
def get_tensores() -> dict:
    """Los tensores DECLARADOS (metadato de la puerta de publicación, plan
    puerta-de-publicacion D3): [{piezas, carrera_mm, eje, nota?}]."""
    with STATE_LOCK:
        return {"tensores": S.doc.tensores}


@router.put("/api/tensores")
def put_tensores(body: TensoresIn) -> dict:
    """Reemplaza los tensores declarados (metadato: no entra al log ni al undo)."""
    from apolo.services.calidad_tensores import poner_tensores
    from apolo.services.errors import ServiceError

    with STATE_LOCK:
        _verificar_documento()  # mutación fuera de _state_or_error: guardia a mano
        try:
            tensores = poner_tensores(S.doc, body.tensores)
        except ServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        _autosave()
        return {"ok": True, "tensores": tensores}


class FuncionesIn(BaseModel):
    funciones: list | dict = []  # también {funcion: {...}} (`calidad/funciones._normalizar`)


@router.get("/api/funciones")
def get_funciones() -> dict:
    """La solución DECLARADA por función (plan puerta-de-publicacion D15): [{funcion, solucion,
    descartadas: [{solucion, motivo}], piezas}]. La puerta de publicación exige una por cada
    familia de función que la máquina tiene."""
    from apolo.library.calidad.funciones import FAMILIAS_FUNCION

    with STATE_LOCK:
        return {"funciones": S.doc.funciones, "familias": FAMILIAS_FUNCION}


@router.put("/api/funciones")
def put_funciones(body: FuncionesIn) -> dict:
    """Reemplaza las funciones declaradas (metadato: no entra al log ni al undo)."""
    from apolo.services.errors import ServiceError
    from apolo.services.puerta_publicacion import poner_funciones

    with STATE_LOCK:
        _verificar_documento()  # mutación fuera de _state_or_error: guardia a mano
        try:
            funciones = poner_funciones(S.doc, body.funciones)
        except ServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        _autosave()
        return {"ok": True, "funciones": funciones}


class JustificadasIn(BaseModel):
    justificadas: list = []


@router.get("/api/justificadas")
def get_justificadas() -> dict:
    """Los avisos y las piezas aceptados POR ESCRITO (plan puerta-sin-sobrediseno D6/D11):
    [{regla?, pieza?, porque}]. Un aviso justificado deja de bloquear la puerta; un error, nunca."""
    with STATE_LOCK:
        return {"justificadas": S.doc.justificadas}


@router.put("/api/justificadas")
def put_justificadas(body: JustificadasIn) -> dict:
    """Reemplaza las justificaciones (metadato: no entra al log ni al undo)."""
    from apolo.services.errors import ServiceError
    from apolo.services.puerta_publicacion import poner_justificadas

    with STATE_LOCK:
        _verificar_documento()  # mutación fuera de _state_or_error: guardia a mano
        try:
            justificadas = poner_justificadas(S.doc, body.justificadas)
        except ServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        _autosave()
        return {"ok": True, "justificadas": justificadas}


class StackupIn(BaseModel):
    name: str
    eslabones: list[dict] = []
    requisito: dict = {}


class StackupDeleteIn(BaseModel):
    name: str


@router.get("/api/stackup")
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


@router.put("/api/stackup")
def put_stackup(body: StackupIn) -> dict:
    with STATE_LOCK:
        _verificar_documento()  # mutación fuera de _state_or_error: guardia a mano
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


@router.delete("/api/stackup")
def delete_stackup(body: StackupDeleteIn) -> dict:
    with STATE_LOCK:
        _verificar_documento()
        S.doc.delete_stackup(body.name)
        _autosave()
        return {"ok": True}
