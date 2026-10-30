"""Las lecturas largas de validación: `/api/checks` (interferencias, reglas de ingeniería y de
estructura, lints pre-entrega) y la puerta de entrega (`/api/delivery-check`).

Salieron de `validation.py` (que estaba en el tope de 500 líneas) con la F3 del plan
`docs/plans/maquinas-grandes.md`, sin cambiar lo que responden:
- D4: `/api/checks` acepta `partes` y corre SÓLO lo pedido; sin el campo, todo y byte-idéntico (la
  UI no lo manda).
- D5: las dos aceptan `?async=true` y van como JOB a `COSIM_JOBS` (`_job_lectura`): 202 + recibo,
  y una lectura idéntica en curso devuelve el job que ya corre. Sin `?async`, byte-idénticas.

El dominio (insumos de la puerta, reglas de ingeniería, filtros cortos) es de `apolo.services`;
aquí queda el transporte y las diferencias DELIBERADAS de `/api/checks` frente a la memoria (D7 de
partir-api-main).
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from apolo.library import conveyor_engineering_check, interference_report
from apolo.services import conexiones
from apolo.services import reglas_cortas as rc
from apolo.services.delivery_inputs import delivery_inputs, exclusiones_declaradas
from apolo.services.engineering_rules import (
    conveyor_params_from_doc,
    inherit_inclination,
    inherit_tensor,
    requirement_inputs,
    structure_rules,
)
from apolo.services.interferencias import como_acotar
from apolo.state import STATE_LOCK

from ..common import _expand_ids, _job_lectura, _mismo_proyecto
from ..session import S
from ..sims import StabilityIn, _stability

router = APIRouter()

#: Lo que `/api/checks` sabe correr (D4), en el orden de la respuesta. `lints` sale DENTRO de
#: `estructura`, como siempre (los lints pre-entrega van al final de esa lista).
PARTES = ("interferencias", "ingenieria", "estructura", "lints")


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
    # maquinas-grandes D4: qué correr (subconjunto de PARTES); sin él, todo (byte-idéntico)
    partes: list[str] | None = None


def _partes(pedidas: list[str] | None) -> tuple[str, ...]:
    """Las partes a correr, en el orden de PARTES; 400 si piden una que no existe o ninguna."""
    if pedidas is None:
        return PARTES
    malas = [p for p in pedidas if p not in PARTES]
    if malas or not pedidas:
        raise HTTPException(status_code=400, detail=(
            f"partes inválidas: {malas or '[] (vacía)'}. Válidas: {', '.join(PARTES)} "
            "(o sin `partes`: todas)."))
    return tuple(p for p in PARTES if p in pedidas)


@router.post("/api/checks", response_model=dict)
def run_checks(body: ChecksIn, async_: bool = Query(False, alias="async")):
    """Interferencias + reglas de ingeniería + estructura universal y lints. Con `partes`, sólo lo
    pedido: lo que no se pidió no aparece (no sale con `null`). Con `?async=true`, JOB."""
    partes = _partes(body.partes)
    tipo = "checks" if body.partes is None else "checks:" + ",".join(partes)
    return _job_lectura(tipo, lambda proyecto: _checks(body, partes, proyecto), async_,
                        body.model_dump())


def _interferencias(body: ChecksIn) -> dict:
    """Bajo STATE_LOCK: la interferencia en diseño o en pose, acotada o paginada."""
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
    return interferencias


def _ingenieria(body: ChecksIn) -> tuple[list | None, dict | None, float | None]:
    """Bajo STATE_LOCK: (reglas del transportador o None, la faja evaluada, la carga)."""
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
    return ingenieria, conveyor, carga


def _lints() -> list:
    """Bajo STATE_LOCK. V7.2b: lints pre-entrega (barreno sin perno · pieza sin grupo ni unión)
    — olvidos de MODELADO que el chequeo estructural no ve; vacíos si el modelo está sano."""
    from apolo.commands.expressions import resolve_params
    from apolo.library.lints import predelivery_lints
    from apolo.services.calidad_agujeros import agujeros_atribuidos

    doc = S.doc
    return predelivery_lints(
        doc.scene, doc.commands, doc.fasteners, doc.grounds, doc.joints, doc.mates,
        resolve=lambda p: resolve_params(p, doc.variables_resolved),
        material_vertical=doc.default_material(),
        agujeros_declarados=lambda: agujeros_atribuidos(doc),
    )


def _checks(body: ChecksIn, partes: tuple[str, ...], proyecto) -> dict:
    out: dict = {}
    conveyor = carga = None
    with STATE_LOCK:
        _mismo_proyecto(proyecto)  # en un job: el proyecto que estaba activo al pedirlo
        if "interferencias" in partes:
            out["interferencias"] = _interferencias(body)
        if "ingenieria" in partes or "estructura" in partes:
            ingenieria, conveyor, carga = _ingenieria(body)
            if "ingenieria" in partes:
                out["ingenieria"] = ingenieria
        if "estructura" in partes or "lints" in partes:
            # chequeo estructural UNIVERSAL + resultados FEA guardados (con vigencia)
            estructura = structure_rules(S.doc, carga, conveyor) if "estructura" in partes else []
            if "lints" in partes:
                estructura += _lints()
            out["estructura"] = estructura
    claves = [k for k in ("ingenieria", "estructura") if k in out]
    if body.grupo or body.solo_fallas or body.resumen:
        for k in claves:
            out[k] = rc.filtrar_reglas(out[k], body.grupo, body.solo_fallas)
        if body.resumen:  # D12: las de cada unión, por el par de piezas; lo «ok», sin detalle
            out["conteo"] = {k: rc.conteo(out[k]) for k in claves}
            with STATE_LOCK:  # la clave lee las uniones y los nombres del documento
                _mismo_proyecto(proyecto)
                clave = conexiones.clave_de_reglas(S.doc)
                for k in claves:
                    out[k] = rc.reglas_cortas(out[k], clave, ok_sin_detalle=not body.grupo)
    return out


class DeliveryIn(BaseModel):
    con_gravedad: bool = False


@router.post("/api/delivery-check", response_model=dict)
def delivery_check_endpoint(body: DeliveryIn, async_: bool = Query(False, alias="async")):
    """PUERTA DE ENTREGA (V6.9): corre la batería de cierre y devuelve el SEMÁFORO
    {veredicto VERDE|AMARILLO|ROJO, bloqueantes, avisos, no_aplica, resumen}. Agregación
    PURA de chequeos existentes (library/delivery.py): interferencias en DISEÑO
    (exclusiones normales) + sujeción DECLARADA (soundness SIN autodetect — la puerta
    valida lo que el modelo declara, no lo que un detector adivina) + lints pre-entrega
    + integridad/suprimidos + colisión EN POSE en los fotogramas de REPOSO de los
    estudios declarados (extremos + dwells; asiento ≤ tolerancia declarado, no bloquea).
    `con_gravedad` añade la simulación MuJoCo (cara; opt-in). Read-only. `tiempos_s` dice
    cuánto tardó en total y cada regla (mcp-sin-friccion D4). Con `?async=true`, JOB (D5 de
    maquinas-grandes)."""
    return _job_lectura("delivery_check", lambda proyecto: _delivery(body, proyecto), async_,
                        body.model_dump())


def _delivery(body: DeliveryIn, proyecto) -> dict:
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
        _mismo_proyecto(proyecto)
        out = delivery_report(**delivery_inputs(S.doc, expand=_expand_ids, tiempos=tiempos),
                              gravedad=gravedad)
    out["tiempos_s"] = {"total": round(time.perf_counter() - t0, 2), "por_regla": tiempos}
    return out
