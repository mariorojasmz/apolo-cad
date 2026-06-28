"""Mates persistentes: relaciones de ensamblaje que se re-resuelven en cada
regeneración (a diferencia de `attach`, que es one-shot por anclas de bbox).

Un mate referencia una CARA en cada pieza (plana → normal; cilíndrica → eje) y,
en `solve_mates`, recoloca la pieza B para satisfacer la relación respecto a la
pieza A (que actúa de base). Igual que las juntas: nombrado, con integridad
referencial, estructura de árbol (un mate por hijo, sin ciclos). Pragmático y
coherente con `robotics/pose.py`: trabaja con frames; reporta error claro si no
puede extraer la geometría en vez de colocar mal.
"""

from __future__ import annotations

import math

from apolo.kernel.matrix import (
    euler_from_matrix,
    frame,
    invert_rigid,
    multiply,
    translation_of,
)
from apolo.kernel.selectors import SelectorError, resolve_faces

MATE_TYPES = ("coincidente", "distancia", "concentrico", "paralelo", "angulo")


class MateError(Exception):
    pass


# ----------------------------------------------------------------- vectores
def _normalize(v):
    n = math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
    if n < 1e-9:
        raise MateError("Vector nulo al construir el frame del mate")
    return (v[0] / n, v[1] / n, v[2] / n)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _rotate_about(v, k, deg):
    """Rota el vector `v` un ángulo `deg` alrededor del eje unitario `k` (Rodrigues)."""
    th = math.radians(deg)
    c, s = math.cos(th), math.sin(th)
    kv = _dot(k, v)
    cr = _cross(k, v)
    return (
        v[0] * c + cr[0] * s + k[0] * kv * (1 - c),
        v[1] * c + cr[1] * s + k[1] * kv * (1 - c),
        v[2] * c + cr[2] * s + k[2] * kv * (1 - c),
    )


def _frame_from_axis(origin, axis, flip: bool = False):
    """Frame ortonormal determinista a partir de (origen, eje primario z).
    El secundario se elige contra el eje de mundo menos alineado (Gram-Schmidt)."""
    z = _normalize(axis)
    ref = min(((1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0)), key=lambda w: abs(_dot(w, z)))
    x = _normalize(_cross(ref, z))
    y = _cross(z, x)
    if flip:  # 180° alrededor del eje
        x = (-x[0], -x[1], -x[2])
        y = (-y[0], -y[1], -y[2])
    return frame(origin, x, y, z)


# --------------------------------------------------------------- conectores
def _cylinder_axis(face):
    """(punto del eje, dirección) de una cara cilíndrica (vía OCCT BRepAdaptor)."""
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Surface

        cyl = BRepAdaptor_Surface(face.wrapped).Cylinder()
        ax = cyl.Axis()
        p, d = ax.Location(), ax.Direction()
        return (p.X(), p.Y(), p.Z()), (d.X(), d.Y(), d.Z())
    except Exception as exc:  # noqa: BLE001
        raise MateError("No se pudo extraer el eje de la cara cilíndrica") from exc


def _project_on_axis(point, p0, axis):
    """Proyecta `point` sobre la recta (p0, axis) — punto del eje a esa altura."""
    w = (point[0] - p0[0], point[1] - p0[1], point[2] - p0[2])
    t = _dot(w, axis)
    return (p0[0] + axis[0] * t, p0[1] + axis[1] * t, p0[2] + axis[2] * t)


def connector_of(shape, ref: dict):
    """Devuelve (origen, eje) del conector resuelto sobre `shape`. Cara plana →
    centro + normal; cara cilíndrica → punto SOBRE EL EJE + eje de revolución."""
    try:
        faces = resolve_faces(shape, ref or {"mode": "todas"})
    except SelectorError as exc:
        raise MateError(f"Referencia de mate inválida: {exc}") from exc
    face = faces[0]
    c = face.center()
    center = (float(c.X), float(c.Y), float(c.Z))
    gt = str(getattr(face, "geom_type", "")).upper()
    if "PLANE" in gt:
        n = face.normal_at()
        return center, _normalize((float(n.X), float(n.Y), float(n.Z)))
    if "CYLINDER" in gt:
        p0, axis = _cylinder_axis(face)
        axis = _normalize(axis)
        return _project_on_axis(center, p0, axis), axis  # origen en el eje, a la altura del centro
    raise MateError(f"La cara del mate debe ser plana o cilíndrica (es {gt or 'desconocida'})")


# ----------------------------------------------------------- validación/registro
def _mate_ancestors(mates: dict, feature_id: str) -> set:
    """Ancestros de una pieza por la cadena de mates (feature_b → feature_a)."""
    seen: set = set()
    current = feature_id
    while True:
        mate = next((m for m in mates.values() if m["feature_b"] == current), None)
        if mate is None or mate["feature_a"] in seen:
            return seen
        seen.add(mate["feature_a"])
        current = mate["feature_a"]


def register_mate(scene: dict, mates: dict, cmd_id: str, spec: dict) -> None:
    name = spec["name"]
    if name in mates:
        raise MateError(f"Ya existe un mate llamado '{name}'")
    for ref in (spec["feature_a"], spec["feature_b"]):
        if ref not in scene:
            raise MateError(f"El mate '{name}' referencia el sólido '{ref}', que no existe")
    if spec["feature_a"] == spec["feature_b"]:
        raise MateError("Un mate no puede unir un sólido consigo mismo")
    if spec["type"] not in MATE_TYPES:
        raise MateError(f"Tipo de mate desconocido '{spec['type']}' ({', '.join(MATE_TYPES)})")
    if any(m["feature_b"] == spec["feature_b"] for m in mates.values()):
        raise MateError(
            f"El sólido '{spec['feature_b']}' ya está mateado por otra relación (estructura de árbol)"
        )
    if spec["feature_b"] in _mate_ancestors(mates, spec["feature_a"]):
        raise MateError("El mate crearía un ciclo de ensamblaje")
    mates[name] = {**spec, "command_id": cmd_id}


# -------------------------------------------------------------------- solver
def _desired_current_frames(a_origin, a_axis, b_origin, b_axis, mate_type, value, flip):
    if mate_type in ("coincidente", "distancia"):
        # caras enfrentadas (normales opuestas), separadas `value` a lo largo de n_A
        target_origin = (
            a_origin[0] + a_axis[0] * value,
            a_origin[1] + a_axis[1] * value,
            a_origin[2] + a_axis[2] * value,
        )
        desired = _frame_from_axis(target_origin, (-a_axis[0], -a_axis[1], -a_axis[2]), flip)
    elif mate_type == "concentrico":
        # ejes colineales (mismo sentido); origen de B sobre el eje de A a `value`
        target_origin = (
            a_origin[0] + a_axis[0] * value,
            a_origin[1] + a_axis[1] * value,
            a_origin[2] + a_axis[2] * value,
        )
        desired = _frame_from_axis(target_origin, a_axis, flip)
    elif mate_type == "paralelo":
        # orientación: normal de B paralela a la de A; NO se mueve la posición de B
        desired = _frame_from_axis(b_origin, a_axis, flip)
    elif mate_type == "angulo":
        # normal de B a `value` grados de la de A (gira en el plano de ambas normales)
        rot_axis = _cross(a_axis, b_axis)
        if _dot(rot_axis, rot_axis) < 1e-9:  # ya casi paralelas: eje perpendicular cualquiera
            ref = min(((1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0)), key=lambda w: abs(_dot(w, a_axis)))
            rot_axis = _cross(a_axis, ref)
        rot_axis = _normalize(rot_axis)
        target = _rotate_about(a_axis, rot_axis, value)
        desired = _frame_from_axis(b_origin, target, flip)
    else:
        raise MateError(f"Tipo de mate desconocido '{mate_type}'")
    current = _frame_from_axis(b_origin, b_axis, False)
    return desired, current


def _solve_one(scene: dict, mate: dict) -> None:
    from build123d import Pos, Rotation

    feat_a = scene[mate["feature_a"]]
    feat_b = scene[mate["feature_b"]]
    a_origin, a_axis = connector_of(feat_a.shape, mate.get("ref_a"))
    b_origin, b_axis = connector_of(feat_b.shape, mate.get("ref_b"))

    desired, current = _desired_current_frames(
        a_origin, a_axis, b_origin, b_axis,
        mate["type"], float(mate.get("value", 0.0)), bool(mate.get("flip", False)),
    )
    delta = multiply(desired, invert_rigid(current))
    t = translation_of(delta)
    euler = euler_from_matrix(delta)

    feat_b.shape = Pos(*t) * Rotation(*euler) * feat_b.shape
    if feat_b.matrix is not None:
        feat_b.matrix = multiply(delta, feat_b.matrix)


def solve_mates(scene: dict, mates: dict) -> None:
    """Recoloca las piezas mateadas en orden de dependencia (padres antes que
    hijos). El árbol está garantizado por register_mate (1 mate por hijo, sin ciclos)."""
    if not mates:
        return
    by_child = {m["feature_b"]: m for m in mates.values()}
    pending = set(by_child)
    progress = True
    while pending and progress:
        progress = False
        for child in list(pending):
            parent = by_child[child]["feature_a"]
            if parent in pending:
                continue  # el padre es a su vez hijo de otro mate aún sin resolver
            _solve_one(scene, by_child[child])
            pending.discard(child)
            progress = True
    if pending:
        raise MateError("No se pudieron resolver los mates (ciclo de ensamblaje)")
