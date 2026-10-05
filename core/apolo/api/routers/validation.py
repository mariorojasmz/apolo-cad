"""Rutas de validación: chequeos, aserciones `verify`, puerta de entrega, requisitos y stack-up.

Router de la API (F6c del plan `docs/plans/partir-api-main.md`): movidas tal cual desde
`main.py`. El dominio (aserciones, insumos de la puerta, reglas de ingeniería, evaluación de
cadenas) es de `apolo.services`; aquí queda el transporte y las diferencias DELIBERADAS de
`/api/checks` frente a la memoria (D7). El `PUT /api/stackup` hace ROLLBACK si la cadena no
evalúa.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from apolo.doc import DocumentError
from apolo.library import conveyor_engineering_check, interference_report
from apolo.services.assertions import verify_checks
from apolo.services.delivery_inputs import delivery_inputs
from apolo.services.engineering_rules import (
    conveyor_params_from_doc,
    inherit_inclination,
    requirement_inputs,
    structure_rules,
)
from apolo.services.stackup_eval import evaluate_stackups
from apolo.state import STATE_LOCK

from ..common import _autosave, _expand_ids, _verificar_documento
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
    `con_gravedad` añade la simulación MuJoCo (cara; opt-in). Read-only."""
    from apolo.library.delivery import delivery_report

    gravedad = None
    if body.con_gravedad:
        # dos-locks propio (_stability); with_autodetect=False: la puerta es DECLARADA
        res = _stability(StabilityIn(with_autodetect=False))
        gravedad = {k: res.get(k) for k in ("fell", "estables", "settled", "n_grounded")}

    with STATE_LOCK:  # la puerta valida lo DECLARADO: services/delivery_inputs.py
        return delivery_report(**delivery_inputs(S.doc, expand=_expand_ids), gravedad=gravedad)


class RequirementsIn(BaseModel):
    fields: dict = {}


@router.get("/api/requirements")
def get_requirements() -> dict:
    with STATE_LOCK:
        return {"requirements": S.doc.requirements}


@router.put("/api/requirements")
def put_requirements(body: RequirementsIn) -> dict:
    with STATE_LOCK:
        _verificar_documento()  # mutación fuera de _state_or_error: guardia a mano
        try:
            S.doc.set_requirements(body.fields)
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _autosave()
        return {"ok": True, "requirements": S.doc.requirements}


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
