"""Solver de restricciones 2D para croquis — FACHADA de dos motores (V5.1).

Filosofía IA-first: el autor (humano o agente) da posiciones APROXIMADAS y
restricciones; el solver las hace exactas. Los croquis subrestringidos son
válidos (la solución se queda cerca del boceto); los imposibles fallan con un
diagnóstico que señala las restricciones culpables para que el agente corrija.

Motores:
  - **planegcs** (default si está instalado): el solver del Sketcher de FreeCAD
    (DogLeg/LM/BFGS). Aporta `dof` (grados de libertad residuales), detección de
    restricciones `redundantes` y `conflictivas` con nombre, y los tipos nuevos
    (tangent, symmetric, equal_radius, concentric, midpoint, distance_point_line).
  - **scipy** (fallback vivo): mínimos cuadrados, los 13 tipos clásicos.
  Override para depurar/tests: env ``APOLO_SKETCH_SOLVER=scipy|planegcs``.

Formato del croquis:
  points: {"p1": [x, y], ...}
  entities: [{"type": "line", "id": "l1", "from": "p1", "to": "p2"},
             {"type": "circle", "id": "c1", "center": "p3", "radius": 20},
             {"type": "arc", "id": "a1", "center": "p4", "from": "p1", "to": "p2", "ccw": true}]
  constraints: [{"type": "horizontal"|"vertical", "entity": "l1"},
                {"type": "length", "entity": "l1", "value": 100},
                {"type": "distance", "a": "p1", "b": "p2", "value": 50},
                {"type": "coincident", "a": "p1", "b": "p2"},
                {"type": "parallel"|"perpendicular", "a": "l1", "b": "l2"},
                {"type": "angle", "a": "l1", "b": "l2", "value": 45},
                {"type": "radius", "entity": "c1", "value": 10},
                {"type": "point_on_line", "point": "p3", "entity": "l1"},
                {"type": "equal_length", "a": "l1", "b": "l2"},
                {"type": "fix", "point": "p1"},
                # solo con el motor planegcs:
                {"type": "tangent", "a": "l1", "b": "a1"},
                {"type": "symmetric", "a": "p1", "b": "p2", "line": "l3"},
                {"type": "equal_radius", "a": "c1", "b": "a1"},
                {"type": "concentric", "a": "c1", "b": "c2"},
                {"type": "midpoint", "point": "p3", "entity": "l1"},
                {"type": "distance_point_line", "point": "p3", "entity": "l1", "value": 25}]
"""

from __future__ import annotations

import os

TOLERANCE = 1e-3  # 1 µm: de sobra para CAD mecánico
REGULARIZATION = 1e-3  # (motor scipy) mantiene lo subrestringido cerca del boceto

# tipos que SOLO resuelve el motor planegcs (el fallback scipy los rechaza claro)
GCS_ONLY_TYPES = frozenset(
    {"tangent", "symmetric", "equal_radius", "concentric", "midpoint", "distance_point_line"}
)


class SketchError(Exception):
    pass


def _index_sketch(sketch: dict):
    points = sketch.get("points") or {}
    entities = {e["id"]: e for e in sketch.get("entities") or []}
    if not points:
        raise SketchError("El croquis no tiene puntos")
    for e in entities.values():
        refs = [e.get("from"), e.get("to"), e.get("center")]
        for ref in refs:
            if ref is not None and ref not in points:
                raise SketchError(f"La entidad '{e['id']}' referencia el punto inexistente '{ref}'")
    return points, entities


def describe_constraint(c: dict) -> str:
    """Descripción legible de una restricción — fuente única del texto que ven
    diagnostico/redundantes/conflictivas (p. ej. "length(l1, 100)")."""
    return f"{c['type']}({', '.join(str(v) for k, v in c.items() if k != 'type')})"


def _pick_engine() -> str:
    forced = (os.environ.get("APOLO_SKETCH_SOLVER") or "").strip().lower()
    if forced in ("scipy", "planegcs"):
        return forced
    from . import sketch_gcs

    return "planegcs" if sketch_gcs.is_available() else "scipy"


def solve_sketch(sketch: dict) -> dict:
    """Resuelve el croquis. Devuelve {ok, residual, points, radii, restricciones,
    incognitas, diagnostico, dof, redundantes, conflictivas}."""
    if _pick_engine() == "planegcs":
        from . import sketch_gcs

        return sketch_gcs.solve(sketch)
    from . import sketch_scipy

    return sketch_scipy.solve(sketch)
