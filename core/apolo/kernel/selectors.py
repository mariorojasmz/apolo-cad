"""Selectores declarativos de aristas y caras.

El problema del *topological naming* se evita no usando nunca índices de
arista/cara: las referencias son declarativas (dirección, cara del bbox,
longitud, cercanía a un punto) y se re-resuelven en cada regeneración.
Las produce tanto el agente IA (semántica) como el clic del usuario en el
viewport (modo "cerca").

`cerca` mide por defecto al CENTRO de cada cara o arista (`obj.center()`: en una cara curva,
el punto en la mitad de su dominio uv, el mismo que publica `get_topology`). Con
`medir="superficie"` mide a la cara o arista MISMA (OCCT) y desempata por ese centro: un punto
SOBRE una cara grande la elige aunque el centro de un taladro vecino quede más cerca. El
default no cambia: un log viejo no trae `medir` y resuelve igual (plan
`docs/plans/fea-chapa-empernada.md`, D5).
"""

from __future__ import annotations

import math

from build123d import Axis

AXES = {"x": Axis.X, "y": Axis.Y, "z": Axis.Z}
FACE_AXES = {
    "tope": ("z", -1),
    "base": ("z", 0),
    "min_x": ("x", 0),
    "max_x": ("x", -1),
    "min_y": ("y", 0),
    "max_y": ("y", -1),
}


class SelectorError(Exception):
    pass


def _center(obj) -> tuple[float, float, float]:
    c = obj.center()
    return (float(c.X), float(c.Y), float(c.Z))


def _dist2(a, b) -> float:
    return (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2


def _bbox_face(shape, face_key: str):
    axis_name, index = FACE_AXES[face_key]
    faces = shape.faces().sort_by(AXES[axis_name])
    if not faces:
        raise SelectorError("El sólido no tiene caras")
    return faces[index]


#: Cómo mide `cerca`; sin la clave (o None) = "centro", el de siempre.
MEDIR = ("centro", "superficie")

#: Decimales (mm) bajo los que dos distancias a la superficie empatan: un punto sobre una
#: arista está a 0 de sus dos caras (con ruido de OCCT ~1e-12) y decide el centro.
_EMPATE_DECIMALES = 6


def _medir(selector: dict) -> str:
    medir = selector.get("medir")
    if medir is None:
        return "centro"
    if medir not in MEDIR:
        raise SelectorError(
            f"medir='{medir}' no existe: usa 'centro' (default: distancia al centro de cada "
            "cara o arista) o 'superficie' (distancia a la cara o arista misma)"
        )
    return medir


def _dist_superficie(obj, vertex) -> float:
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    calc = BRepExtrema_DistShapeShape(obj.wrapped, vertex)
    return calc.Value() if calc.IsDone() else math.inf


def _cerca(objs: list, selector: dict) -> list:
    """Los `count` objetos más próximos a `point`: al centro (default) o a la superficie."""
    point = selector.get("point")
    if not point or len(point) != 3:
        raise SelectorError("El modo 'cerca' necesita point=[x,y,z]")
    count = max(1, int(selector.get("count", 1)))
    if _medir(selector) == "centro":
        return sorted(objs, key=lambda o: _dist2(_center(o), point))[:count]
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    from OCP.gp import gp_Pnt

    vertex = BRepBuilderAPI_MakeVertex(gp_Pnt(*(float(c) for c in point))).Vertex()

    def clave(o):
        d = round(_dist_superficie(o, vertex), _EMPATE_DECIMALES)
        return (d, _dist2(_center(o), point))

    return sorted(objs, key=clave)[:count]


def resolve_edges(shape, selector: dict) -> list:
    mode = selector.get("mode", "todas")
    _medir(selector)  # un valor inválido falla en todo modo, como en el schema
    edges = list(shape.edges())
    if not edges:
        raise SelectorError("El sólido no tiene aristas")

    if mode == "todas":
        result = edges
    elif mode == "direccion":
        direction = selector.get("direction", "z")
        if direction not in AXES:
            raise SelectorError(f"Dirección desconocida '{direction}' (x, y o z)")
        result = list(shape.edges().filter_by(AXES[direction]))
    elif mode == "cara":
        face_key = selector.get("face", "tope")
        if face_key not in FACE_AXES:
            raise SelectorError(f"Cara desconocida '{face_key}' ({', '.join(FACE_AXES)})")
        result = list(_bbox_face(shape, face_key).edges())
    elif mode == "longitud":
        lo = selector.get("min")
        hi = selector.get("max")
        result = [
            e for e in edges
            if (lo is None or e.length >= lo) and (hi is None or e.length <= hi)
        ]
    elif mode == "cerca":
        result = _cerca(edges, selector)
    else:
        raise SelectorError(f"Modo de selector desconocido '{mode}'")

    if not result:
        raise SelectorError(f"El selector {selector} no encontró ninguna arista")
    return result


def resolve_faces(shape, selector: dict) -> list:
    mode = selector.get("mode", "todas")
    _medir(selector)
    faces = list(shape.faces())
    if not faces:
        raise SelectorError("El sólido no tiene caras")

    if mode == "todas":
        result = faces
    elif mode == "direccion":
        direction = selector.get("direction", "z")
        if direction not in AXES:
            raise SelectorError(f"Dirección desconocida '{direction}' (x, y o z)")
        result = list(shape.faces().filter_by(AXES[direction]))
    elif mode == "cara":
        face_key = selector.get("face", "tope")
        if face_key not in FACE_AXES:
            raise SelectorError(f"Cara desconocida '{face_key}' ({', '.join(FACE_AXES)})")
        result = [_bbox_face(shape, face_key)]
    elif mode == "longitud":
        raise SelectorError("El modo 'longitud' solo aplica a aristas")
    elif mode == "cerca":
        result = _cerca(faces, selector)
    else:
        raise SelectorError(f"Modo de selector desconocido '{mode}'")

    if not result:
        raise SelectorError(f"El selector {selector} no encontró ninguna cara")
    return result
