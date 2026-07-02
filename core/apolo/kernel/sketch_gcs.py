"""Motor PlaneGCS del solver de croquis (V5.1) — el solver del Sketcher de FreeCAD.

Adaptador croquis-JSON → `planegcs.Sketch` (bindings LGPL con wheel cp313). Aporta lo
que el motor scipy no puede: `dof` (grados de libertad residuales), detección de
restricciones REDUNDANTES y CONFLICTIVAS con nombre legible, tangencias/simetrías/
concentricidad, y convergencia robusta en croquis grandes (DogLeg).

Diseño:
- Los puntos/círculos del croquis mapean 1:1 a entidades GCS; los ARCOS usan
  `add_arc_cse` (radio/ángulos internos + arc-rules automáticas que sustituyen a la
  `_arc_equal` implícita del motor scipy). Un arco `ccw:false` se construye canónico
  ccw intercambiando start/end — los extremos son los MISMOS puntos, la salida no
  cambia.
- `coincident` NO fusiona puntos (la salida necesita ambos ids; sketch_geom ya
  hace union-find aguas abajo).
- Cada restricción registra su tag → `describe_constraint` para reportar
  redundantes/conflictivas con el mismo texto del diagnóstico clásico.
- El veredicto `ok` NO es el status del solver: se VERIFICA la solución evaluando
  los residuos geométricos (mismas fórmulas/escalas del motor scipy) — así `ok`
  significa lo mismo en ambos motores.
"""

from __future__ import annotations

import math

from .sketch_solver import TOLERANCE, SketchError, _index_sketch, describe_constraint

try:
    from planegcs import Sketch as _GcsSketch
    from planegcs import SolveStatus as _SolveStatus

    _AVAILABLE = True
except ImportError:  # plataforma sin wheel: la fachada cae al motor scipy
    _AVAILABLE = False


def is_available() -> bool:
    return _AVAILABLE


def _need(c: dict, *keys: str) -> None:
    for k in keys:
        if k not in c:
            raise SketchError(f"La restricción {c.get('type')} necesita el campo '{k}'")


# ------------------------------------------------------------------ verificador
def _verify(constraints: list[dict], points: dict, entities: dict, radii: dict):
    """Evalúa los residuos geométricos de CADA restricción sobre la solución.

    Mismas fórmulas y escalas que el motor scipy (ángulo ×50, fix ×2 dims) para que
    el umbral TOLERANCE signifique lo mismo. Devuelve (n_dims, peor_residuo,
    [(restricción, peor_local), ...])."""

    def pt(pid):
        p = points[pid]
        return float(p[0]), float(p[1])

    def line(lid):
        ent = entities.get(lid)
        if ent is None or ent["type"] != "line":
            raise SketchError(f"La restricción necesita una línea; '{lid}' no lo es")
        return pt(ent["from"]), pt(ent["to"])

    def rad(eid):
        ent = entities.get(eid)
        if ent is None:
            raise SketchError(f"No existe la entidad '{eid}'")
        if ent["type"] == "circle":
            return float(radii[eid])
        if ent["type"] == "arc":
            (cx, cy), (fx, fy) = pt(ent["center"]), pt(ent["from"])
            return math.hypot(fx - cx, fy - cy)
        raise SketchError(f"'{eid}' no es un círculo ni un arco")

    def center(eid):
        ent = entities.get(eid)
        if ent is None or ent["type"] not in ("circle", "arc"):
            raise SketchError(f"'{eid}' no es un círculo ni un arco")
        return pt(ent["center"])

    def perp_dist(p, a, b):
        (px, py), (ax, ay), (bx, by) = p, a, b
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1.0
        return ((px - ax) * dy - (py - ay) * dx) / norm

    def residuals(c) -> list[float]:
        t = c["type"]
        if t == "horizontal":
            _need(c, "entity")
            (_, y1), (_, y2) = line(c["entity"])
            return [y2 - y1]
        if t == "vertical":
            _need(c, "entity")
            (x1, _), (x2, _) = line(c["entity"])
            return [x2 - x1]
        if t == "length":
            _need(c, "entity", "value")
            (x1, y1), (x2, y2) = line(c["entity"])
            return [math.hypot(x2 - x1, y2 - y1) - float(c["value"])]
        if t == "distance":
            _need(c, "a", "b", "value")
            (ax, ay), (bx, by) = pt(c["a"]), pt(c["b"])
            return [math.hypot(bx - ax, by - ay) - float(c["value"])]
        if t == "coincident":
            _need(c, "a", "b")
            (ax, ay), (bx, by) = pt(c["a"]), pt(c["b"])
            return [bx - ax, by - ay]
        if t == "parallel":
            _need(c, "a", "b")
            (a1, a2), (b1, b2) = line(c["a"]), line(c["b"])
            d1 = (a2[0] - a1[0], a2[1] - a1[1])
            d2 = (b2[0] - b1[0], b2[1] - b1[1])
            return [d1[0] * d2[1] - d1[1] * d2[0]]
        if t == "perpendicular":
            _need(c, "a", "b")
            (a1, a2), (b1, b2) = line(c["a"]), line(c["b"])
            d1 = (a2[0] - a1[0], a2[1] - a1[1])
            d2 = (b2[0] - b1[0], b2[1] - b1[1])
            return [d1[0] * d2[0] + d1[1] * d2[1]]
        if t == "angle":
            _need(c, "a", "b", "value")
            (a1, a2), (b1, b2) = line(c["a"]), line(c["b"])
            diff = (
                math.atan2(b2[1] - b1[1], b2[0] - b1[0])
                - math.atan2(a2[1] - a1[1], a2[0] - a1[0])
                - math.radians(float(c["value"]))
            )
            while diff > math.pi:
                diff -= 2 * math.pi
            while diff < -math.pi:
                diff += 2 * math.pi
            return [diff * 50.0]
        if t == "radius":
            _need(c, "entity", "value")
            return [rad(c["entity"]) - float(c["value"])]
        if t == "point_on_line":
            _need(c, "point", "entity")
            a, b = line(c["entity"])
            return [perp_dist(pt(c["point"]), a, b)]
        if t == "equal_length":
            _need(c, "a", "b")
            (a1, a2), (b1, b2) = line(c["a"]), line(c["b"])
            return [
                math.hypot(a2[0] - a1[0], a2[1] - a1[1])
                - math.hypot(b2[0] - b1[0], b2[1] - b1[1])
            ]
        if t == "fix":
            # el motor GCS fija los params en exacto: residuo 0 por construcción
            _need(c, "point")
            return [0.0, 0.0]
        if t == "tangent":
            _need(c, "a", "b")
            ka = entities.get(c["a"], {}).get("type")
            kb = entities.get(c["b"], {}).get("type")
            if ka == "line" and kb in ("circle", "arc"):
                a, b = line(c["a"])
                return [abs(perp_dist(center(c["b"]), a, b)) - rad(c["b"])]
            if kb == "line" and ka in ("circle", "arc"):
                a, b = line(c["b"])
                return [abs(perp_dist(center(c["a"]), a, b)) - rad(c["a"])]
            # curva-curva: tangencia externa o interna, la que esté más cerca
            (x1, y1), (x2, y2) = center(c["a"]), center(c["b"])
            d = math.hypot(x2 - x1, y2 - y1)
            r1, r2 = rad(c["a"]), rad(c["b"])
            return [min(abs(d - (r1 + r2)), abs(d - abs(r1 - r2)))]
        if t == "symmetric":
            _need(c, "a", "b", "line")
            a, b = pt(c["a"]), pt(c["b"])
            l1, l2 = line(c["line"])
            # reflejo de a sobre la recta == b
            dx, dy = l2[0] - l1[0], l2[1] - l1[1]
            nn = dx * dx + dy * dy or 1.0
            t_ = ((a[0] - l1[0]) * dx + (a[1] - l1[1]) * dy) / nn
            foot = (l1[0] + t_ * dx, l1[1] + t_ * dy)
            mirror = (2 * foot[0] - a[0], 2 * foot[1] - a[1])
            return [b[0] - mirror[0], b[1] - mirror[1]]
        if t == "equal_radius":
            _need(c, "a", "b")
            return [rad(c["a"]) - rad(c["b"])]
        if t == "concentric":
            _need(c, "a", "b")
            (x1, y1), (x2, y2) = center(c["a"]), center(c["b"])
            return [x2 - x1, y2 - y1]
        if t == "midpoint":
            _need(c, "point", "entity")
            a, b = line(c["entity"])
            px, py = pt(c["point"])
            return [px - (a[0] + b[0]) / 2, py - (a[1] + b[1]) / 2]
        if t == "distance_point_line":
            _need(c, "point", "entity", "value")
            a, b = line(c["entity"])
            return [abs(perp_dist(pt(c["point"]), a, b)) - float(c["value"])]
        raise SketchError(f"Tipo de restricción desconocido: '{t}'")

    n_dims = 0
    worst_global = 0.0
    per_constraint: list[tuple[dict, float]] = []
    for c in constraints:
        res = residuals(c)
        n_dims += len(res)
        worst = max(abs(v) for v in res) if res else 0.0
        per_constraint.append((c, worst))
        worst_global = max(worst_global, worst)
    return n_dims, worst_global, per_constraint


# --------------------------------------------------------------------- adaptador
def solve(sketch: dict) -> dict:
    """Resuelve el croquis con PlaneGCS. Contrato de solve_sketch (con dof)."""
    if not _AVAILABLE:  # defensa: la fachada no debería llamarnos sin el paquete
        raise SketchError("planegcs no está instalado (pip install planegcs)")

    points, entities = _index_sketch(sketch)
    constraints = list(sketch.get("constraints") or [])

    s = _GcsSketch()
    gcs_pt = {pid: s.add_point(float(p[0]), float(p[1])) for pid, p in points.items()}
    gcs_line: dict[str, object] = {}
    gcs_circle: dict[str, object] = {}
    gcs_arc: dict[str, object] = {}

    for e in entities.values():
        if e["type"] == "line":
            gcs_line[e["id"]] = s.add_line(gcs_pt[e["from"]], gcs_pt[e["to"]])
        elif e["type"] == "circle":
            r0 = max(0.1, float(e.get("radius", 10)))
            gcs_circle[e["id"]] = s.add_circle(gcs_pt[e["center"]], s.add_param(r0))
        elif e["type"] == "arc":
            cx, cy = points[e["center"]][:2]
            fx, fy = points[e["from"]][:2]
            tx, ty = points[e["to"]][:2]
            r0 = max(0.1, (math.hypot(fx - cx, fy - cy) + math.hypot(tx - cx, ty - cy)) / 2)
            af = math.atan2(fy - cy, fx - cx)
            at = math.atan2(ty - cy, tx - cx)
            if e.get("ccw", True):
                start, end, sa, ea = e["from"], e["to"], af, at
            else:  # cw de from→to == ccw de to→from (mismos puntos: la salida no cambia)
                start, end, sa, ea = e["to"], e["from"], at, af
            while ea <= sa:
                ea += 2 * math.pi
            gcs_arc[e["id"]] = s.add_arc_cse(
                gcs_pt[e["center"]], gcs_pt[start], gcs_pt[end], r0, sa, ea
            )
        else:
            raise SketchError(f"Tipo de entidad desconocido: '{e['type']}'")

    def kind(eid: str) -> str:
        ent = entities.get(eid)
        if ent is None:
            raise SketchError(f"No existe la entidad '{eid}'")
        return ent["type"]

    def as_line(eid):
        if eid not in gcs_line:
            raise SketchError(f"La restricción necesita una línea; '{eid}' no lo es")
        return gcs_line[eid]

    def as_point(pid):
        if pid not in gcs_pt:
            raise SketchError(f"No existe el punto '{pid}'")
        return gcs_pt[pid]

    tag_desc: dict[int, str] = {}

    def add(c: dict) -> None:
        t = c["type"]
        desc = describe_constraint(c)
        tags: list = []
        if t == "horizontal":
            _need(c, "entity")
            tags = [s.horizontal(as_line(c["entity"]))]
        elif t == "vertical":
            _need(c, "entity")
            tags = [s.vertical(as_line(c["entity"]))]
        elif t == "length":
            _need(c, "entity", "value")
            ent = entities.get(c["entity"])
            if ent is None or ent["type"] != "line":
                raise SketchError(f"La restricción necesita una línea; '{c['entity']}' no lo es")
            tags = [s.set_p2p_distance(as_point(ent["from"]), as_point(ent["to"]), float(c["value"]))]
        elif t == "distance":
            _need(c, "a", "b", "value")
            tags = [s.set_p2p_distance(as_point(c["a"]), as_point(c["b"]), float(c["value"]))]
        elif t == "coincident":
            _need(c, "a", "b")
            tags = [s.coincident(as_point(c["a"]), as_point(c["b"]))]
        elif t == "parallel":
            _need(c, "a", "b")
            tags = [s.parallel(as_line(c["a"]), as_line(c["b"]))]
        elif t == "perpendicular":
            _need(c, "a", "b")
            tags = [s.perpendicular(as_line(c["a"]), as_line(c["b"]))]
        elif t == "angle":
            _need(c, "a", "b", "value")
            tags = [s.set_l2l_angle(as_line(c["a"]), as_line(c["b"]), math.radians(float(c["value"])))]
        elif t == "radius":
            _need(c, "entity", "value")
            k = kind(c["entity"])
            if k == "circle":
                tags = [s.set_circle_radius(gcs_circle[c["entity"]], float(c["value"]))]
            elif k == "arc":
                tags = [s.set_arc_radius(gcs_arc[c["entity"]], float(c["value"]))]
            else:
                raise SketchError(f"'{c['entity']}' no es un círculo")
        elif t == "point_on_line":
            _need(c, "point", "entity")
            ent = entities.get(c["entity"])
            if ent is None or ent["type"] != "line":
                raise SketchError(f"point_on_line necesita una línea; '{c.get('entity')}' no lo es")
            tags = [s.point_on_line(as_point(c["point"]), as_line(c["entity"]))]
        elif t == "equal_length":
            _need(c, "a", "b")
            tags = [s.equal_length(as_line(c["a"]), as_line(c["b"]))]
        elif t == "fix":
            _need(c, "point")
            ox, oy = points[c["point"]][:2]
            tags = list(s.fix_point(as_point(c["point"]), float(ox), float(oy)))
        elif t == "tangent":
            _need(c, "a", "b")
            ka, kb = kind(c["a"]), kind(c["b"])
            pair = {ka, kb}
            # normalizar: línea primero, círculo antes que arco
            a, b = c["a"], c["b"]
            if (ka, kb) in (("circle", "line"), ("arc", "line"), ("arc", "circle")):
                a, b, ka, kb = b, a, kb, ka
            if ka == "line" and kb == "circle":
                tags = [s.tangent_line_circle(gcs_line[a], gcs_circle[b])]
            elif ka == "line" and kb == "arc":
                tags = [s.tangent_line_arc(gcs_line[a], gcs_arc[b])]
            elif ka == "circle" and kb == "circle":
                tags = [s.tangent_circle_circle(gcs_circle[a], gcs_circle[b])]
            elif ka == "circle" and kb == "arc":
                tags = [s.tangent_circle_arc(gcs_circle[a], gcs_arc[b])]
            elif ka == "arc" and kb == "arc":
                tags = [s.tangent_arc_arc(gcs_arc[a], gcs_arc[b])]
            else:
                raise SketchError(
                    f"tangent necesita una curva (círculo/arco); '{a}' y '{b}' son {sorted(pair)}"
                )
        elif t == "symmetric":
            _need(c, "a", "b", "line")
            tags = [s.symmetric_line(as_point(c["a"]), as_point(c["b"]), as_line(c["line"]))]
        elif t == "equal_radius":
            _need(c, "a", "b")
            ka, kb = kind(c["a"]), kind(c["b"])
            a, b = c["a"], c["b"]
            if (ka, kb) == ("arc", "circle"):
                a, b, ka, kb = b, a, kb, ka
            if (ka, kb) == ("circle", "circle"):
                tags = [s.equal_radius_cc(gcs_circle[a], gcs_circle[b])]
            elif (ka, kb) == ("circle", "arc"):
                tags = [s.equal_radius_ca(gcs_circle[a], gcs_arc[b])]
            elif (ka, kb) == ("arc", "arc"):
                tags = [s.equal_radius_aa(gcs_arc[a], gcs_arc[b])]
            else:
                raise SketchError(f"equal_radius necesita círculos/arcos; '{a}' o '{b}' no lo son")
        elif t == "concentric":
            _need(c, "a", "b")
            ca = entities.get(c["a"], {}).get("center")
            cb = entities.get(c["b"], {}).get("center")
            if ca is None or cb is None:
                raise SketchError(f"concentric necesita círculos/arcos; '{c['a']}' o '{c['b']}' no lo son")
            if ca != cb:  # mismo punto de centro = concéntrico por construcción
                tags = [s.coincident(as_point(ca), as_point(cb))]
        elif t == "midpoint":
            _need(c, "point", "entity")
            ent = entities.get(c["entity"])
            if ent is None or ent["type"] != "line":
                raise SketchError(f"midpoint necesita una línea; '{c.get('entity')}' no lo es")
            tags = [s.symmetric_point(as_point(ent["from"]), as_point(ent["to"]), as_point(c["point"]))]
        elif t == "distance_point_line":
            _need(c, "point", "entity", "value")
            tags = [s.set_p2l_distance(as_point(c["point"]), as_line(c["entity"]), float(c["value"]))]
        else:
            raise SketchError(f"Tipo de restricción desconocido: '{t}'")
        for tag in tags:
            tag_desc[int(tag)] = desc

    for c in constraints:
        add(c)

    status = s.solve()
    solved = status in (_SolveStatus.Success, _SolveStatus.Converged)
    diag = s.diagnose()

    solved_points = {
        pid: [round(x, 6), round(y, 6)]
        for pid, (x, y) in ((pid, s.get_point(g)) for pid, g in gcs_pt.items())
    }
    solved_radii = {
        cid: round(abs(s.get_circle(g).radius), 6) for cid, g in gcs_circle.items()
    }

    # veredicto por VERIFICACIÓN geométrica (independiente del status del solver)
    n_dims, worst, per_constraint = _verify(constraints, solved_points, entities, solved_radii)
    ok = solved and worst <= TOLERANCE

    def describe_tags(tags) -> list[str]:
        out = []
        for tag in tags:
            d = tag_desc.get(int(tag))
            if d and d not in out:
                out.append(d)
        return out

    conflictivas = describe_tags(diag.conflicting)
    redundantes = describe_tags(list(diag.redundant) + list(diag.partially_redundant))

    diagnostico: list[str] = []
    if not ok:
        diagnostico = [
            f"{describe_constraint(c)}: desvío {w:.3g}" for c, w in per_constraint if w > TOLERANCE
        ][:6]
        if not diagnostico:
            diagnostico = conflictivas[:6] or ["el solver no convergió"]

    return {
        "ok": ok,
        "residual": worst,
        "points": solved_points,
        "radii": solved_radii,
        "restricciones": n_dims,
        "incognitas": len(points) * 2 + len(gcs_circle),
        "diagnostico": diagnostico,
        "dof": int(diag.dof),
        "redundantes": redundantes,
        "conflictivas": conflictivas,
    }
