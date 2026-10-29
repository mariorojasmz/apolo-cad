"""Rutas de ensamblaje: mates, restricciones de riel, uniones, estructura, DOF y física.

Router de la API (F6c del plan `docs/plans/partir-api-main.md`): movidas tal cual desde
`main.py`. La gravedad, el drop-test, la dinámica (V8.2) y la serie de la marcha para el visor
(visor-realista D4) siguen el patrón dos-locks (`sims.py`). El ORDEN importa:
`POST /api/constraints/solve` va antes que `DELETE /api/constraints/{name}`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel

from apolo.services import conexiones
from apolo.services.errors import ServiceError
from apolo.state import STATE_LOCK

from ..common import _expand_ids, _remove_owner_command, _state_or_error
from ..session import S
from ..sims import (
    MARCHAS,
    DropIn,
    DynamicsIn,
    StabilityIn,
    _drop,
    _dynamics,
    _serie_dinamica,
    _stability,
)

router = APIRouter()


@router.get("/api/mates")
def get_mates() -> list[dict]:
    with STATE_LOCK:
        return [
            {k: v for k, v in m.items() if k not in ("ref_a", "ref_b")}
            for m in S.doc.mates.values()
        ]


@router.delete("/api/mates/{name}")
def delete_mate(name: str) -> dict:
    return _state_or_error(lambda: _remove_owner_command(
        S.doc.mates, name, "add_mate", f"No existe el mate '{name}'", "Este mate pertenece a una plantilla"))


class SolveIn(BaseModel):
    values: dict[str, float] = {}


@router.get("/api/constraints")
def get_constraints() -> list[dict]:
    with STATE_LOCK:
        return list(S.doc.constraints.values())


@router.post("/api/constraints/solve")
def solve_constraints_endpoint(body: SolveIn) -> dict:
    """Dado un conjunto de valores de junta (driver + libres), devuelve los
    valores con las juntas DEPENDIENTES resueltas para cumplir las restricciones
    de riel. Read-only: no muta el documento. Lo usa la UI para arrastre en vivo."""
    from apolo.assembly.constraints import solve_constraints

    with STATE_LOCK:
        return {"values": solve_constraints(S.doc.joints, S.doc.constraints, body.values)}


@router.delete("/api/constraints/{name}")
def delete_constraint(name: str) -> dict:
    with STATE_LOCK:
        con = S.doc.constraints.get(name)
    if con is None:
        raise HTTPException(status_code=404, detail=f"No existe la restricción '{name}'")
    return _state_or_error(lambda: S.doc.remove_commands([con["command_id"]]))


class SoundnessIn(BaseModel):
    with_autodetect: bool = False  # superpone uniones detectadas por geometría (efímeras)
    resumen: bool = False  # mcp-sin-friccion D1: conteos + lo que flota (services/conexiones.py)


@router.get("/api/connectivity")
def get_connectivity(
    ids: str | None = None, kind: str | None = None,
    resumen: str = Query("no", pattern="^(no|si|auto)$"),
) -> dict:
    """Uniones declaradas del documento: fijadores (A↔B) y anclajes a tierra. Sin parámetros,
    todas (la UI). `ids` (CSV de piezas, grupos o comandos) y `kind` (perno, soldadura, pegado,
    contacto o anclaje) filtran; `resumen=si` agrupa por raíz de patrón y `auto` lo hace con más
    de `MAX_UNIONES` (mcp-sin-friccion D1/D2, `services/conexiones.py`)."""
    tokens = [t.strip() for t in (ids or "").split(",") if t.strip()]
    with STATE_LOCK:
        try:
            fijadores, anclajes = conexiones.filtrar(S.doc, tokens, kind, expand=_expand_ids)
        except ServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
        if resumen == "si" or (resumen == "auto"
                               and len(fijadores) + len(anclajes) > conexiones.MAX_UNIONES):
            return conexiones.resumen_conexiones(S.doc, fijadores, anclajes)
        return {"fasteners": fijadores, "grounds": anclajes}


@router.post("/api/assembly/autodetect")
def assembly_autodetect() -> dict:
    """Propone uniones desde la geometría (apoyos en el piso + pares en contacto).
    Read-only: no muta el documento. El usuario/agente confirma con ground/fasten."""
    from apolo.assembly.autodetect import detect_connections

    with STATE_LOCK:
        return detect_connections(S.doc.scene)


@router.delete("/api/fasteners/{name}")
def delete_fastener(name: str) -> dict:
    with STATE_LOCK:
        f = S.doc.fasteners.get(name)
    if f is None:
        raise HTTPException(status_code=404, detail=f"No existe el fijador '{name}'")
    return _state_or_error(lambda: S.doc.remove_commands([f["command_id"]]))


@router.delete("/api/grounds/{name}")
def delete_ground(name: str) -> dict:
    with STATE_LOCK:
        g = S.doc.grounds.get(name)
    if g is None:
        raise HTTPException(status_code=404, detail=f"No existe el anclaje '{name}'")
    return _state_or_error(lambda: S.doc.remove_commands([g["command_id"]]))


class ConnectionsRemoveIn(BaseModel):
    names: list[str]


@router.post("/api/connections/remove")
def remove_connections(body: ConnectionsRemoveIn) -> dict:
    """Borra VARIAS uniones declaradas por nombre (fijadores y/o anclajes, V6.8-A)
    en UN remove_commands atómico (1 undo). Un nombre inexistente → 404 nombrándolo
    y NO se borra ninguna — sin estados a medias en cirugías. El payload lleva
    `conexiones_borradas` [{name, tipo}]."""
    names = list(dict.fromkeys(body.names))
    if not names:
        raise HTTPException(status_code=400, detail="La lista 'names' no puede estar vacía")
    borradas: list[dict] = []

    def run():
        ids: list[str] = []
        for name in names:
            if name in S.doc.fasteners:
                conn, tipo = S.doc.fasteners[name], "fijador"
            elif name in S.doc.grounds:
                conn, tipo = S.doc.grounds[name], "anclaje"
            else:
                validas = sorted(set(S.doc.fasteners) | set(S.doc.grounds))
                raise HTTPException(
                    status_code=404,
                    detail=f"No existe la unión '{name}' — no se borró ninguna. "
                    f"Declaradas: {', '.join(validas) or 'ninguna'}",
                )
            borradas.append({"name": name, "tipo": tipo})
            ids.append(conn["command_id"])
        return S.doc.remove_commands(list(dict.fromkeys(ids)))

    payload = _state_or_error(run)
    payload["conexiones_borradas"] = borradas
    return payload


class DeclareIn(BaseModel):
    aplicar: bool = True  # False = sólo PROPONE (D3 de uniones-en-lote); sin cuerpo, aplica
    resumen: bool = False  # True = la respuesta corta del agente (D6 de mcp-sin-friccion)


@router.post("/api/assembly/declare")
def assembly_declare(body: DeclareIn | None = None) -> dict:
    """Auto-declara la ESTRUCTURA real (anclajes al piso + uniones de soporte) como comandos
    PERSISTIDOS. Inteligente (grafo de soporte dirigido): no fija las piezas colgantes (p. ej.
    rodillos de retorno) → la prueba de gravedad EXACTA las tira; el TIPO de cada unión sale del
    criterio de taller (`services/criterio_uniones.py`: lo desmontable va atornillado, lo que
    gira no se suelda). Idempotente: no recrea uniones ya declaradas. Tras esto, `stability`
    con `with_autodetect=false` valida solo lo declarado.

    `aplicar=false` no muta: devuelve `{aplicar, acciones, resumen, omitidas, n_*}` de
    `services/estructura.py` para que el agente la corrija y la aplique en un lote; con
    `resumen=true`, el modo corto de `services/estructura_corta.py`. Aplicada, escribe esas
    mismas uniones, dimensionadas, con un `fasten` por CONJUNTO (`lote_compacto`, D8 de
    mcp-sin-friccion); la escena suma `a_revisar` (nombres) sólo si alguna unión lo está; con
    `resumen=true`, en vez de la escena, los conteos de lo declarado."""
    from apolo.batch import execute_batch
    from apolo.services.estructura import propuesta_estructura
    from apolo.services.estructura_corta import aplicada_corta, lote_compacto, propuesta_corta

    aplicar = body is None or body.aplicar
    corto = body is not None and body.resumen
    with STATE_LOCK:
        prop = propuesta_estructura(S.doc)
        acciones = prop["acciones"]
        if not aplicar:
            if corto:
                return {"aplicar": False, **propuesta_corta(S.doc, prop)}
            fasten = [a for a in acciones if a["type"] == "fasten"]
            return {"aplicar": False, "n_grounds": len(acciones) - len(fasten),
                    "n_fasteners": len(fasten),
                    "n_a_revisar": sum(1 for a in fasten if a.get("a_revisar")), **prop}
        lote = lote_compacto(S.doc, acciones)
        armar = (lambda: aplicada_corta(S.doc, acciones, len(lote))) if corto else None
        if not acciones:
            return _state_or_error(lambda: None, armar=armar)
        payload = _state_or_error(lambda: execute_batch(S.doc, lote), armar=armar)
    revisar = [a["params"]["name"] for a in acciones if a.get("a_revisar")]
    if revisar and not corto:
        payload["a_revisar"] = revisar
    return payload


class AutoGroupIn(BaseModel):
    dry_run: bool = False


@router.post("/api/assembly/auto-group")
def assembly_auto_group(body: AutoGroupIn) -> dict:
    """Auto-agrupa el modelo en SUB-ENSAMBLAJES por subsistema (misma heurística del
    árbol: super-comando → catálogo → palabra clave del nombre). Idempotente (omite
    grupos ya existentes y comandos ya agrupados); con `dry_run` solo PROPONE sin
    mutar. Los grupos quedan como comandos `create_group` del log (undo/persistencia)."""
    from apolo.assembly.grouping import propose_groups
    from apolo.batch import execute_batch
    from apolo.library.catalog import CATALOG

    with STATE_LOCK:
        proposal = propose_groups(S.doc.scene, S.doc.commands, CATALOG, S.doc.groups)
        if body.dry_run or not proposal:
            return {"dry_run": body.dry_run, "proposal": proposal, "created": 0}
        actions = [{"type": "create_group", "params": g} for g in proposal]
        payload = _state_or_error(lambda: execute_batch(S.doc, actions))
    payload["proposal"] = proposal
    payload["created"] = len(proposal)
    return payload


@router.post("/api/assembly/soundness")
def assembly_soundness(body: SoundnessIn) -> dict:
    """Validación de ensamblaje: ¿cada pieza tiene un camino de sujeción hasta el
    piso? Determinista, sin física. Con `with_autodetect` superpone (sin persistir)
    las uniones detectadas por geometría para responder 'si fijara todo lo que se
    toca, ¿qué seguiría flotando?'. Read-only."""
    from apolo.assembly.autodetect import detect_connections
    from apolo.assembly.connectivity import build_graph, soundness_report
    from apolo.services.delivery_inputs import aristas_tornilleria_join_bolted

    with STATE_LOCK:
        # la tornillería de un join_bolted cuelga de las piezas de SU fijador declarado (D6 de
        # bom-de-compra-fiel): no es una pieza «aislada»
        extra_edges: list = aristas_tornilleria_join_bolted(S.doc)
        extra_grounds: set = set()
        detected = None
        if body.with_autodetect:
            detected = detect_connections(S.doc.scene)
            extra_edges += [(c["a"], c["b"], "contacto", "") for c in detected["fasteners"]]
            extra_grounds = {g["feature"] for g in detected["grounds"]}
        graph = build_graph(
            S.doc.scene, S.doc.joints, S.doc.mates, S.doc.fasteners, S.doc.grounds,
            extra_edges=extra_edges, extra_grounds=extra_grounds,
        )
        report = soundness_report(graph)
        report["floating_detail"] = [
            {"id": fid, "nombre": getattr(S.doc.scene[fid], "name", fid)}
            for fid in report["floating"]
        ]
        if detected is not None:
            report["autodetect"] = {
                "floor_z": detected["floor_z"],
                "n_grounds": len(detected["grounds"]),
                "n_contactos": len(detected["fasteners"]),
            }
        return conexiones.sujecion_corta(S.doc, report) if body.resumen else report


@router.get("/api/assembly/dof")
def assembly_dof() -> dict:
    """Reporte de GRADOS DE LIBERTAD (V6.3c): por sólido, ¿cuántos GDL le quedan tras
    ground/juntas/mates? Conteo Grübler determinista, sin OCCT. Read-only."""
    from apolo.assembly.dof import dof_report

    with STATE_LOCK:
        return dof_report(S.doc.scene, S.doc.joints, S.doc.mates, S.doc.grounds)


@router.post("/api/assembly/stability")
def assembly_stability(body: StabilityIn) -> dict:
    """Simula la gravedad sobre TODA la máquina (cuerpos rígidos + casco convexo):
    las piezas sujetas a tierra son estáticas, el resto cae. Devuelve qué piezas se
    CAYERON (desplazamiento del centro de masa) y cuáles aguantaron. Read-only.
    `frames` se omite por defecto (es grande); pide `include_frames` para animar la
    caída en el viewport, o usa el endpoint .gif."""
    res = _stability(body)
    if body.include_frames:
        return res
    return {k: v for k, v in res.items() if k != "frames"}


@router.post("/api/assembly/stability.gif")
def assembly_stability_gif(body: StabilityIn) -> Response:
    """GIF animado de la caída: la estructura sujeta de fondo + las piezas que caen."""
    from apolo.physics.anim import render_drop_gif

    res = _stability(body)  # simulación bajo dos-locks (no bajo STATE_LOCK)
    if not res["products"]:
        raise HTTPException(status_code=400, detail=res.get("mensaje", "nada que simular"))
    dynamic_ids = {p["id"] for p in res["products"]}
    with STATE_LOCK:  # el GIF tesela la escena estática de fondo (OCCT) → bajo el lock
        static_scene = {fid: f for fid, f in S.doc.scene.items() if fid not in dynamic_ids}
        gif = render_drop_gif(static_scene, res["products"], res["frames"], fps=body.fps)
    return Response(content=gif, media_type="image/gif")


@router.post("/api/physics/drop")
def physics_drop(body: DropIn) -> dict:
    return _drop(body)


@router.post("/api/physics/drop.gif")
def physics_drop_gif(body: DropIn) -> Response:
    from apolo.physics.anim import render_drop_gif

    res = _drop(body)
    with STATE_LOCK:
        gif = render_drop_gif(S.doc.scene, res["products"], res["frames"], fps=body.fps)
    return Response(content=gif, media_type="image/gif")


@router.post("/api/physics/dynamics")
def physics_dynamics(body: DynamicsIn) -> dict:
    """La máquina EN MARCHA (V8.2): juntas con motores, productos sobre la banda o los
    rodillos y fotoceldas. Read-only. `frames` (poses por fotograma) se omite por defecto,
    como en la gravedad: pide `include_frames` para animar, o usa el endpoint .gif."""
    res = _dynamics(body)
    if body.include_frames:
        return res
    return {k: v for k, v in res.items() if k != "frames"}


@router.post("/api/physics/dynamics.gif")
def physics_dynamics_gif(body: DynamicsIn) -> Response:
    """GIF de la marcha, a tiempo real, con el render de `render_view`: la escena, los cuerpos
    de junta en su pose y los productos. Se tesela con el MISMO documento que la simulación
    (bajo STATE_LOCK) y se pinta fuera, bajo RENDER_LOCK."""
    from apolo.physics.gif_dinamica import render_dynamics_gif

    res, escena = _dynamics(body, con_escena=True)
    if escena is None or not res["frames"]:
        raise HTTPException(status_code=400, detail=res.get("mensaje", "Nada que simular"))
    try:
        gif = render_dynamics_gif(escena, res["productos"], res["frames"], view=body.view,
                                  size_px=body.size_px, max_fotogramas=body.max_frames,
                                  poses_diseno=res.get("poses_diseno"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:  # sin Pillow
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 — sin contexto OpenGL u otro fallo VTK
        raise HTTPException(status_code=503, detail=f"El render VTK falló: {exc}") from exc
    return Response(content=gif, media_type="image/gif")


_SIN_MARCHA = ("Todavía no hay una simulación de esta máquina en marcha: pídele al agente que la "
               "simule y vuelve a intentarlo.")


@router.get("/api/physics/dynamics/serie")
def physics_dynamics_serie() -> dict:
    """La ÚLTIMA marcha simulada del proyecto activo (la del agente con `simulate` o la de esta
    misma ruta) como serie de tiempo para el reproductor del visor (visor-realista D4): poses
    relativas por cuerpo y absolutas por producto a ~50 Hz, `q` por junta y velocidad de cada
    banda. Si el documento cambió desde entonces, se simula otra vez sobre el actual."""
    with STATE_LOCK:
        proyecto = S.project_id
    peticion = MARCHAS.ultimo_escenario(proyecto)
    if peticion is None:
        raise HTTPException(status_code=404, detail=_SIN_MARCHA)
    return _serie_dinamica(peticion)


@router.post("/api/physics/dynamics/serie")
def physics_dynamics_serie_de(body: DynamicsIn) -> dict:
    """La serie del reproductor para un escenario explícito (la petición de `simulate`); pasa a
    ser la última marcha del proyecto. Las opciones del transporte se ignoran."""
    return _serie_dinamica(dict(body.model_extra or {}))
