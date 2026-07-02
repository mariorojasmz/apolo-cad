"""Motor scipy del solver de croquis (mínimos cuadrados, el motor original de F11).

FALLBACK VIVO de PlaneGCS (V5.1): se usa cuando `planegcs` no está instalado o con
`APOLO_SKETCH_SOLVER=scipy`. Soporta los 13 tipos clásicos de restricción; los tipos
nuevos (tangent, symmetric, equal_radius, concentric, midpoint, distance_point_line)
requieren PlaneGCS y aquí fallan con un error claro. Los tests parametrizan ambos
motores, así que este código se ejercita en cada CI — no es código muerto.

Algoritmo: least_squares en doble pasada con una regularización suave hacia el
boceto (lo subrestringido se queda cerca de la posición dada). Sin diagnóstico de
DOF ni redundantes (eso lo da PlaneGCS): devuelve dof=None, redundantes/conflictivas
vacías.
"""

from __future__ import annotations

import math

from .sketch_solver import (
    GCS_ONLY_TYPES,
    REGULARIZATION,
    TOLERANCE,
    SketchError,
    _index_sketch,
    describe_constraint,
)


def solve(sketch: dict) -> dict:
    """Resuelve el croquis con scipy. Contrato de solve_sketch (dof=None)."""
    import numpy as np
    from scipy.optimize import least_squares

    points, entities = _index_sketch(sketch)
    constraints = list(sketch.get("constraints") or [])
    for c in constraints:
        if c.get("type") in GCS_ONLY_TYPES:
            raise SketchError(
                f"La restricción '{c['type']}' requiere el motor PlaneGCS "
                "(pip install planegcs); el motor scipy solo cubre los tipos clásicos"
            )

    # los arcos imponen |c-from| == |c-to| implícitamente
    for e in entities.values():
        if e["type"] == "arc":
            constraints.append({"type": "_arc_equal", "entity": e["id"]})

    point_ids = sorted(points.keys())
    circle_ids = sorted(e["id"] for e in entities.values() if e["type"] == "circle")
    p_index = {pid: i * 2 for i, pid in enumerate(point_ids)}
    r_index = {cid: len(point_ids) * 2 + i for i, cid in enumerate(circle_ids)}
    n_unknowns = len(point_ids) * 2 + len(circle_ids)

    x0 = np.zeros(n_unknowns)
    for pid in point_ids:
        x0[p_index[pid]: p_index[pid] + 2] = points[pid][:2]
    for cid in circle_ids:
        x0[r_index[cid]] = max(0.1, float(entities[cid].get("radius", 10)))

    def pt(x, pid):
        i = p_index[pid]
        return x[i], x[i + 1]

    def line_dir(x, lid):
        ent = entities.get(lid)
        if ent is None or ent["type"] not in ("line",):
            raise SketchError(f"La restricción necesita una línea; '{lid}' no lo es")
        x1, y1 = pt(x, ent["from"])
        x2, y2 = pt(x, ent["to"])
        return x2 - x1, y2 - y1

    def need(c, *keys):
        for k in keys:
            if k not in c:
                raise SketchError(f"La restricción {c.get('type')} necesita el campo '{k}'")

    def residuals_for(c, x) -> list[float]:
        t = c["type"]
        if t == "horizontal":
            need(c, "entity")
            _, dy = line_dir(x, c["entity"])
            return [dy]
        if t == "vertical":
            need(c, "entity")
            dx, _ = line_dir(x, c["entity"])
            return [dx]
        if t == "length":
            need(c, "entity", "value")
            dx, dy = line_dir(x, c["entity"])
            return [math.hypot(dx, dy) - float(c["value"])]
        if t == "distance":
            need(c, "a", "b", "value")
            ax, ay = pt(x, c["a"])
            bx, by = pt(x, c["b"])
            return [math.hypot(bx - ax, by - ay) - float(c["value"])]
        if t == "coincident":
            need(c, "a", "b")
            ax, ay = pt(x, c["a"])
            bx, by = pt(x, c["b"])
            return [bx - ax, by - ay]
        if t == "parallel":
            need(c, "a", "b")
            d1, d2 = line_dir(x, c["a"]), line_dir(x, c["b"])
            return [d1[0] * d2[1] - d1[1] * d2[0]]
        if t == "perpendicular":
            need(c, "a", "b")
            d1, d2 = line_dir(x, c["a"]), line_dir(x, c["b"])
            return [d1[0] * d2[0] + d1[1] * d2[1]]
        if t == "angle":
            need(c, "a", "b", "value")
            d1, d2 = line_dir(x, c["a"]), line_dir(x, c["b"])
            diff = math.atan2(d2[1], d2[0]) - math.atan2(d1[1], d1[0]) - math.radians(float(c["value"]))
            while diff > math.pi:
                diff -= 2 * math.pi
            while diff < -math.pi:
                diff += 2 * math.pi
            return [diff * 50.0]  # escala angular ≈ mm
        if t == "radius":
            need(c, "entity", "value")
            if c["entity"] not in r_index:
                raise SketchError(f"'{c['entity']}' no es un círculo")
            return [x[r_index[c["entity"]]] - float(c["value"])]
        if t == "point_on_line":
            need(c, "point", "entity")
            ent = entities.get(c["entity"])
            if ent is None or ent["type"] != "line":
                raise SketchError(f"point_on_line necesita una línea; '{c.get('entity')}' no lo es")
            px, py = pt(x, c["point"])
            ax, ay = pt(x, ent["from"])
            dx, dy = line_dir(x, c["entity"])
            norm = math.hypot(dx, dy) or 1.0
            return [((px - ax) * dy - (py - ay) * dx) / norm]
        if t == "equal_length":
            need(c, "a", "b")
            d1, d2 = line_dir(x, c["a"]), line_dir(x, c["b"])
            return [math.hypot(*d1) - math.hypot(*d2)]
        if t == "fix":
            need(c, "point")
            px, py = pt(x, c["point"])
            ox, oy = points[c["point"]][:2]
            return [(px - ox) * 10.0, (py - oy) * 10.0]
        if t == "_arc_equal":
            ent = entities[c["entity"]]
            cx, cy = pt(x, ent["center"])
            fx, fy = pt(x, ent["from"])
            tx, ty = pt(x, ent["to"])
            return [math.hypot(fx - cx, fy - cy) - math.hypot(tx - cx, ty - cy)]
        raise SketchError(f"Tipo de restricción desconocido: '{t}'")

    def fun(x):
        res = []
        for c in constraints:
            res.extend(residuals_for(c, x))
        res.extend(REGULARIZATION * (x - x0))  # mantiene lo subrestringido cerca del boceto
        return np.array(res)

    n_hard = sum(len(residuals_for(c, x0)) for c in constraints)
    result = least_squares(fun, x0, xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=2000)

    # segunda pasada recentrando la regularización en la solución: en cambios
    # grandes (cotas que estiran mucho el boceto) aprieta el residual final
    x0 = result.x.copy()
    result = least_squares(fun, x0, xtol=1e-12, ftol=1e-12, gtol=1e-12, max_nfev=2000)

    hard = result.fun[:n_hard] if n_hard else np.array([])
    max_residual = float(np.max(np.abs(hard))) if n_hard else 0.0

    diagnostico = []
    if n_hard and max_residual > TOLERANCE:
        offset = 0
        for c in constraints:
            dims = len(residuals_for(c, result.x))
            worst = float(np.max(np.abs(result.fun[offset: offset + dims])))
            if worst > TOLERANCE and c["type"] != "_arc_equal":
                diagnostico.append(f"{describe_constraint(c)}: desvío {worst:.3g}")
            offset += dims
        diagnostico = diagnostico[:6]

    solved_points = {pid: [round(float(result.x[p_index[pid]]), 6), round(float(result.x[p_index[pid] + 1]), 6)] for pid in point_ids}
    solved_radii = {cid: round(float(abs(result.x[r_index[cid]])), 6) for cid in circle_ids}

    return {
        "ok": max_residual <= TOLERANCE,
        "residual": max_residual,
        "points": solved_points,
        "radii": solved_radii,
        "restricciones": n_hard,
        "incognitas": n_unknowns,
        "diagnostico": diagnostico,
        "dof": None,  # el motor scipy no calcula grados de libertad
        "redundantes": [],
        "conflictivas": [],
    }
