"""Croquis resuelto → cara B-rep en un plano de trabajo.

Reglas v1: las líneas/arcos deben encadenar en UN lazo cerrado (los puntos
unidos por restricción coincident se fusionan); los círculos dentro del lazo
son agujeros, y si no hay lazo, el primer círculo es el contorno y el resto
agujeros.
"""

from __future__ import annotations

import math

from .sketch_solver import SketchError, solve_sketch

PLANES = {"xy", "xz", "yz"}


def _merge_groups(sketch: dict) -> dict[str, str]:
    """Union-find de puntos unidos por 'coincident' → representante por punto."""
    parent: dict[str, str] = {p: p for p in (sketch.get("points") or {})}

    def find(a: str) -> str:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for c in sketch.get("constraints") or []:
        if c.get("type") == "coincident" and c.get("a") in parent and c.get("b") in parent:
            parent[find(c["a"])] = find(c["b"])
    return {p: find(p) for p in parent}


def _chain_loop(segments: list[tuple[str, str, dict]]) -> list[dict]:
    """Encadena segmentos (rep_from, rep_to, entidad) en un lazo cerrado."""
    if not segments:
        return []
    remaining = segments[:]
    first = remaining.pop(0)
    ordered = [{"ent": first[2], "start": first[0], "end": first[1]}]
    while remaining:
        tail = ordered[-1]["end"]
        for i, (a, b, ent) in enumerate(remaining):
            if a == tail:
                ordered.append({"ent": ent, "start": a, "end": b})
                remaining.pop(i)
                break
            if b == tail:
                ordered.append({"ent": ent, "start": b, "end": a})
                remaining.pop(i)
                break
        else:
            raise SketchError(
                "Las líneas/arcos no forman un lazo cerrado: hay un hueco después de "
                f"'{ordered[-1]['ent']['id']}' (une los extremos o añade coincident)"
            )
    if ordered[0]["start"] != ordered[-1]["end"]:
        raise SketchError("El lazo no cierra: el último segmento no vuelve al primero")
    return ordered


def _arc_mid(center, start, end, ccw: bool):
    a0 = math.atan2(start[1] - center[1], start[0] - center[0])
    a1 = math.atan2(end[1] - center[1], end[0] - center[0])
    if ccw and a1 <= a0:
        a1 += 2 * math.pi
    if not ccw and a1 >= a0:
        a1 -= 2 * math.pi
    am = (a0 + a1) / 2
    r = math.hypot(start[0] - center[0], start[1] - center[1])
    return (center[0] + r * math.cos(am), center[1] + r * math.sin(am))


def sketch_to_face(sketch: dict):
    """Resuelve el croquis y construye la cara 2D (en coordenadas locales XY).
    Devuelve (face, solved)."""
    from build123d import Circle, Line, Pos, ThreePointArc, make_face

    solved = solve_sketch(sketch)
    if not solved["ok"]:
        raise SketchError(
            "El croquis no satisface sus restricciones (desvío máx. "
            f"{solved['residual']:.3g} mm). Problemas: " + "; ".join(solved["diagnostico"])
        )

    points = solved["points"]
    radii = solved["radii"]
    rep = _merge_groups(sketch)
    coord = lambda pid: tuple(points[pid])

    segments = []
    circles = []
    for ent in sketch.get("entities") or []:
        if ent["type"] == "line":
            a, b = rep[ent["from"]], rep[ent["to"]]
            if a == b:
                raise SketchError(f"La línea '{ent['id']}' tiene longitud cero tras resolver")
            segments.append((a, b, ent))
        elif ent["type"] == "arc":
            segments.append((rep[ent["from"]], rep[ent["to"]], ent))
        elif ent["type"] == "circle":
            circles.append(ent)
        else:
            raise SketchError(f"Entidad desconocida '{ent['type']}'")

    face = None
    if segments:
        loop = _chain_loop(segments)
        edges = []
        for item in loop:
            ent = item["ent"]
            start = coord(item["start"])
            end = coord(item["end"])
            if ent["type"] == "line":
                edges.append(Line(start, end))
            else:
                mid = _arc_mid(coord(rep[ent["center"]]), start, end, bool(ent.get("ccw", True)))
                edges.append(ThreePointArc(start, mid, end))
        face = make_face(edges)
        for circle in circles:  # círculos = agujeros
            cx, cy = coord(rep[circle["center"]])
            face = face - Pos(cx, cy) * Circle(radii[circle["id"]])
    elif circles:
        cx, cy = coord(rep[circles[0]["center"]])
        face = Pos(cx, cy) * Circle(radii[circles[0]["id"]])
        for circle in circles[1:]:
            hx, hy = coord(rep[circle["center"]])
            face = face - Pos(hx, hy) * Circle(radii[circle["id"]])
    else:
        raise SketchError("El croquis no tiene entidades que formen un perfil")

    if face.area <= 0:
        raise SketchError("El perfil del croquis tiene área cero")
    return face, solved


def place_sketch_on_plane(face, plane: str):
    from build123d import Plane

    if plane not in PLANES:
        raise SketchError(f"Plano desconocido '{plane}' (xy, xz o yz)")
    mapping = {"xy": Plane.XY, "xz": Plane.XZ, "yz": Plane.YZ}
    return mapping[plane] * face
