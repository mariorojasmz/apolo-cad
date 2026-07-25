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


def _closed_face(ent: dict, coord, rep: dict, radii: dict):
    """Cara de una entidad CERRADA (V6.6): elipse o spline cerrada. Devuelve la Face en
    coordenadas locales del croquis."""
    from build123d import Ellipse, Plane, Pos, Rot, Spline, make_face

    if ent["type"] == "ellipse":
        cx, cy = coord(rep[ent["center"]])
        rx, ry = float(ent["rx"]), float(ent["ry"])
        if rx <= 0 or ry <= 0:
            raise SketchError(f"La elipse '{ent['id']}' necesita rx y ry > 0")
        face = Ellipse(rx, ry)
        rot = float(ent.get("rotation", 0.0) or 0.0)
        if rot:
            face = Rot(0, 0, rot) * face
        return Pos(cx, cy) * face
    pts = [coord(rep[p]) for p in ent["points"]]
    # spline CERRADA: build123d cierra el lazo repitiendo el primer punto (periódica
    # daría una curva distinta a la que el usuario dibujó punto a punto)
    if pts[0] != pts[-1]:
        pts = pts + [pts[0]]
    return make_face(Plane.XY * Spline(*[(x, y) for x, y in pts]))


def sketch_to_face(sketch: dict):
    """Resuelve el croquis y construye la cara 2D (en coordenadas locales XY).
    Devuelve (face, solved)."""
    from build123d import Circle, Line, Pos, Spline, ThreePointArc, make_face

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
    closed_shapes = []          # V6.6: elipses y splines CERRADAS (perfil o agujero)
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
        elif ent["type"] == "ellipse":
            closed_shapes.append(ent)
        elif ent["type"] == "spline":
            # V6.6: los puntos de control son PUNTOS del croquis → el solver los mueve y
            # se pueden restringir/arrastrar como cualquier otro (nada de coords sueltas)
            ctrl = [rep[p] for p in (ent.get("points") or [])]
            if len(ctrl) < 3:
                raise SketchError(f"La spline '{ent['id']}' necesita al menos 3 puntos de control")
            if ent.get("closed"):
                closed_shapes.append(ent)
            else:
                segments.append((ctrl[0], ctrl[-1], ent))
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
            elif ent["type"] == "spline":      # V6.6: tramo abierto del lazo
                pts = [coord(rep[p]) for p in ent["points"]]
                if item["start"] != rep[ent["points"][0]]:
                    pts.reverse()              # el lazo la recorre en REVERSA
                edges.append(Spline(*[(x, y) for x, y in pts]))
            else:
                # si el lazo recorre el arco EN REVERSA (start/end intercambiados por
                # _chain_loop), el sentido efectivo se invierte — sin esto el punto
                # medio cae del lado equivocado y la tapa se abomba hacia dentro
                ccw = bool(ent.get("ccw", True))
                if item["start"] != rep[ent["from"]]:
                    ccw = not ccw
                mid = _arc_mid(coord(rep[ent["center"]]), start, end, ccw)
                edges.append(ThreePointArc(start, mid, end))
        face = make_face(edges)
        for circle in circles:  # círculos = agujeros
            cx, cy = coord(rep[circle["center"]])
            face = face - Pos(cx, cy) * Circle(radii[circle["id"]])
        for sh in closed_shapes:               # V6.6: elipse/spline cerrada = agujero
            face = face - _closed_face(sh, coord, rep, radii)
    elif circles or closed_shapes:
        # el PRIMER cerrado es el contorno; el resto, agujeros (misma regla que círculos)
        orden = ([("c", c) for c in circles] + [("s", s) for s in closed_shapes])
        kind, first = orden[0]
        if kind == "c":
            cx, cy = coord(rep[first["center"]])
            face = Pos(cx, cy) * Circle(radii[first["id"]])
        else:
            face = _closed_face(first, coord, rep, radii)
        for kind, ent in orden[1:]:
            if kind == "c":
                hx, hy = coord(rep[ent["center"]])
                face = face - Pos(hx, hy) * Circle(radii[ent["id"]])
            else:
                face = face - _closed_face(ent, coord, rep, radii)
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
