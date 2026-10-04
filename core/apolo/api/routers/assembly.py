"""Rutas de ensamblaje: mates, restricciones de riel, uniones, estructura, DOF y gravedad.

Router de la API (F6c del plan `docs/plans/partir-api-main.md`): movidas tal cual desde
`main.py`. La gravedad y el drop-test siguen el patrón dos-locks (`sims.py`). El ORDEN importa:
`POST /api/constraints/solve` va antes que `DELETE /api/constraints/{name}`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from apolo.state import STATE_LOCK

from ..common import _remove_owner_command, _state_or_error
from ..session import S
from ..sims import DropIn, StabilityIn, _drop, _stability

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


@router.get("/api/connectivity")
def get_connectivity() -> dict:
    """Uniones declaradas del documento: fijadores (A↔B) y anclajes a tierra."""
    with STATE_LOCK:
        return {
            "fasteners": list(S.doc.fasteners.values()),
            "grounds": list(S.doc.grounds.values()),
        }


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


@router.post("/api/assembly/declare")
def assembly_declare() -> dict:
    """Auto-declara la ESTRUCTURA real (anclajes al piso + uniones de soporte) como comandos
    PERSISTIDOS. Inteligente (grafo de soporte dirigido): no fija las piezas colgantes (p. ej.
    rodillos de retorno) → la prueba de gravedad EXACTA las tira. Idempotente: no recrea uniones
    ya declaradas. Tras esto, `stability` con `with_autodetect=false` valida solo lo declarado."""
    from apolo.assembly.autodetect import detect_structure
    from apolo.batch import execute_batch

    with STATE_LOCK:
        det = detect_structure(S.doc.scene)
        existing_names = set(S.doc.fasteners) | set(S.doc.grounds)
        ground_feats = {g["feature"] for g in S.doc.grounds.values()}
        pairs = {frozenset((f["a"], f["b"])) for f in S.doc.fasteners.values()}

        def uniq(prefix: str) -> str:
            i = 1
            while f"{prefix}{i}" in existing_names:
                i += 1
            name = f"{prefix}{i}"
            existing_names.add(name)
            return name

        actions: list[dict] = []
        for g in det["grounds"]:
            if g["feature"] in ground_feats:
                continue
            ground_feats.add(g["feature"])
            actions.append({"type": "ground", "params": {
                "name": uniq("auto_g_"), "feature": g["feature"], "nota": (g.get("reason") or "")[:120]}})
        for f in det["fasteners"]:
            pair = frozenset((f["a"], f["b"]))
            if pair in pairs:
                continue
            pairs.add(pair)
            actions.append({"type": "fasten", "params": {
                "name": uniq("auto_f_"), "a": f["a"], "b": f["b"], "kind": f["kind"],
                "nota": (f.get("reason") or "")[:120]}})
        if not actions:
            return _state_or_error(lambda: None)
        return _state_or_error(lambda: execute_batch(S.doc, actions))


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

    with STATE_LOCK:
        extra_edges: list = []
        extra_grounds: set = set()
        detected = None
        if body.with_autodetect:
            detected = detect_connections(S.doc.scene)
            extra_edges = [(c["a"], c["b"], "contacto", "") for c in detected["fasteners"]]
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
        return report


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
