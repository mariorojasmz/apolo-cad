"""Reparto de cargas por el grafo de conectividad: ¿cuánto CUELGA de una unión?

La carga que soporta un fijador A↔B se define como la masa que PIERDE el camino
a tierra si se quita esa arista del grafo (`connectivity.build_graph`). Es un
modelo estáticamente honesto: si al quitar la arista ambos lados siguen
aterrizados, la unión es REDUNDANTE (camino de carga múltiple) y el reparto es
estáticamente indeterminado sin FEA → se devuelve None y la regla lo reporta
como no determinable, en vez de inventar un número.
"""

from __future__ import annotations


def _reachable_without(adj: dict, seeds, a: str, b: str) -> set:
    """Nodos alcanzables desde `seeds` ignorando la arista a↔b (DFS)."""
    seen: set = set()
    stack = list(seeds)
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        for m in adj.get(n, ()):
            if (n == a and m == b) or (n == b and m == a):
                continue
            stack.append(m)
    return seen


def alcanzables(graph: dict) -> set:
    """Los nodos que llegan a tierra en `graph` (DFS desde `grounded_seed`): lo que
    `hanging_load_kg` compara contra el grafo sin cada arista."""
    adj = graph["adj"]
    before: set = set()
    stack = list(graph["grounded_seed"])
    while stack:
        n = stack.pop()
        if n in before:
            continue
        before.add(n)
        stack.extend(adj.get(n, ()))
    return before


def hanging_load_kg(graph: dict, masses: dict[str, float], a: str, b: str,
                    before: set | None = None) -> float | None:
    """Masa (kg) que cuelga de la unión a↔b: piezas que estaban aterrizadas y
    dejan de estarlo al quitar la arista. None si la unión es redundante (nada
    pierde tierra → carga compartida no determinable) o si el lado ya flotaba.
    `before` = `alcanzables(graph)` si el llamador recorre muchas uniones del MISMO
    grafo sin cambiarlo (una vez por grafo, no por unión: plan puerta-rapida, D3)."""
    adj, seeds = graph["adj"], graph["grounded_seed"]
    if not seeds:
        return None
    if before is None:
        before = alcanzables(graph)
    after = _reachable_without(adj, seeds, a, b)
    hanging = before - after
    if not hanging:
        return None
    return sum(float(masses.get(fid, 0.0)) for fid in hanging)
