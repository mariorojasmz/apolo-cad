"""Conectividad de ensamblaje y análisis de "soundness" del montaje.

A diferencia de los mates (que recolocan geometría) y de las restricciones
cinemáticas (lazos), la conectividad es PURAMENTE estructural: un grafo cuyos
nodos son los sólidos y cuyas aristas son las uniones declaradas — juntas
(`add_joint`), mates (`add_mate`) y fijadores (`fasten`: perno/soldadura/
pegado/contacto) — más el conjunto de piezas ancladas al piso (`ground`).

El análisis es determinista y barato (sin geometría): una pieza está "sujeta"
si tiene un camino en el grafo hasta alguna pieza anclada a tierra; si no, está
"flotando" (caería bajo gravedad). Es el cimiento de la validación de ensamblaje:
este chequeo estático responde el 80% ("¿qué se cae?") sin motor de física; la
simulación (physics/stability.py) lo hace visible.

Espejo estructural de ``assembly/constraints.py``: clase de error + ``register_*``
para registrar la relación durante la regeneración del log + funciones puras de
análisis. No muta el documento ni la escena.
"""

from __future__ import annotations

# tipos de fijador: perno/soldadura/pegado son uniones que el usuario declara;
# "contacto" lo emite la auto-detección (apoyo geométrico, más débil).
FASTEN_KINDS = ("perno", "soldadura", "pegado", "contacto")


class ConnectivityError(Exception):
    pass


# --------------------------------------------------------------- registro
def register_fastener(fasteners: dict, cmd_id: str, spec: dict) -> None:
    """Valida y registra un fijador rígido A↔B en el dict del documento. La
    existencia de los sólidos se valida tras regenerar (igual que los mates),
    porque las piezas pueden definirse después en el log."""
    name = spec["name"]
    if name in fasteners:
        raise ConnectivityError(f"Ya existe un fijador llamado '{name}'")
    if spec["a"] == spec["b"]:
        raise ConnectivityError("Un fijador une dos sólidos distintos (a ≠ b)")
    kind = spec.get("kind", "perno")
    if kind not in FASTEN_KINDS:
        raise ConnectivityError(f"Tipo de fijador desconocido: '{kind}'")
    fasteners[name] = {**spec, "command_id": cmd_id}


def register_ground(grounds: dict, cmd_id: str, spec: dict) -> None:
    """Valida y registra un anclaje a tierra (una pieza fijada al piso/cimiento)."""
    name = spec["name"]
    if name in grounds:
        raise ConnectivityError(f"Ya existe un anclaje llamado '{name}'")
    grounds[name] = {**spec, "command_id": cmd_id}


# ----------------------------------------------------------------- grafo
def build_graph(
    scene,
    joints: dict,
    mates: dict,
    fasteners: dict,
    grounds: dict,
    extra_edges: list | None = None,
    extra_grounds: set | None = None,
) -> dict:
    """Construye el grafo de conectividad: adyacencia entre sólidos (juntas +
    mates + fijadores) y el conjunto semilla de sólidos anclados a tierra.

    `extra_edges` (lista de (a, b, via, name)) y `extra_grounds` (set de ids)
    permiten superponer uniones DETECTADAS por geometría sin persistirlas — para
    responder "si fijara todo lo que se toca, ¿qué seguiría flotando?". Solo se
    consideran sólidos presentes en la escena; las referencias colgantes se ignoran.
    """
    ids = set(scene.keys())
    adj: dict[str, set[str]] = {fid: set() for fid in ids}
    edges: list[dict] = []

    def link(a, b, via, name):
        if a in ids and b in ids and a != b:
            adj[a].add(b)
            adj[b].add(a)
            edges.append({"a": a, "b": b, "via": via, "name": name})

    for j in joints.values():
        link(j["parent"], j["child"], "junta", j.get("name", ""))
    for m in mates.values():
        link(m["feature_a"], m["feature_b"], "mate", m.get("name", ""))
    for f in fasteners.values():
        link(f["a"], f["b"], f.get("kind", "perno"), f.get("name", ""))
    for a, b, via, name in extra_edges or []:
        link(a, b, via, name)

    seed = {g["feature"] for g in grounds.values() if g.get("feature") in ids}
    seed |= {fid for fid in (extra_grounds or set()) if fid in ids}
    return {"adj": adj, "edges": edges, "grounded_seed": seed, "ids": ids}


def _reachable(adj: dict, seeds) -> set:
    """Conjunto de nodos alcanzables desde `seeds` (DFS iterativo)."""
    seen: set = set()
    stack = list(seeds)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(adj.get(n, ()))
    return seen


def _components(adj: dict, ids: set) -> list[list[str]]:
    """Componentes conexos del grafo (sub-ensamblajes sueltos)."""
    comps: list[list[str]] = []
    unseen = set(ids)
    while unseen:
        comp = _reachable(adj, {next(iter(unseen))}) & ids
        comps.append(sorted(comp))
        unseen -= comp
    return comps


def soundness_report(graph: dict) -> dict:
    """Analiza el grafo: qué piezas tienen camino de sujeción hasta tierra
    (`grounded`) y cuáles no (`floating` → caerían). Determinista.

    `isolated` = piezas flotantes que además NO tienen NINGUNA unión (sueltas del
    todo, p. ej. un motor solo colocado en el aire), el caso más claro de error.
    """
    adj, ids = graph["adj"], graph["ids"]
    grounded = _reachable(adj, graph["grounded_seed"]) & ids
    floating = sorted(ids - grounded)
    isolated = sorted(fid for fid in floating if not adj.get(fid))
    return {
        "has_ground": bool(graph["grounded_seed"]),
        "n_total": len(ids),
        "n_grounded": len(grounded),
        "n_floating": len(floating),
        "grounded": sorted(grounded),
        "floating": floating,
        "isolated": isolated,
        "components": _components(adj, ids),
    }
