"""Solver de restricciones 2D para croquis (mínimos cuadrados, scipy).

Filosofía IA-first: el autor (humano o agente) da posiciones APROXIMADAS y
restricciones; el solver las hace exactas. Los croquis subrestringidos son
válidos (una regularización suave los mantiene cerca de la posición dada);
los imposibles fallan con un diagnóstico que señala las restricciones
culpables para que el agente corrija.

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
                {"type": "fix", "point": "p1"}]
"""

from __future__ import annotations

import math

TOLERANCE = 1e-3  # 1 µm: de sobra para CAD mecánico
REGULARIZATION = 1e-3


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


def solve_sketch(sketch: dict) -> dict:
    """Resuelve el croquis. Devuelve {points, radii, residual, ok, diagnostico}."""
    import numpy as np
    from scipy.optimize import least_squares

    points, entities = _index_sketch(sketch)
    constraints = list(sketch.get("constraints") or [])

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
                diagnostico.append(f"{c['type']}({', '.join(str(v) for k, v in c.items() if k != 'type')}): desvío {worst:.3g}")
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
    }
