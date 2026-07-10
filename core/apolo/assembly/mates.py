"""Mates persistentes: relaciones de ensamblaje que se re-resuelven en cada
regeneración (a diferencia de `attach`, que es one-shot por anclas de bbox).

Un mate referencia una CARA en cada pieza (plana → normal; cilíndrica → eje) y,
en `solve_mates`, recoloca la pieza B para satisfacer la relación respecto a la
pieza A (que actúa de base). Igual que las juntas: nombrado, con integridad
referencial, sin ciclos. Pragmático y coherente con `robotics/pose.py`: trabaja
con frames; reporta error claro si no puede extraer la geometría en vez de colocar
mal.

MULTI-MATE (V6.3a): un sólido puede ser B (hijo) de VARIOS mates a la vez (placa
coincidente sobre dos rieles; ménsula coincidente a una cara + concéntrica a un
eje). El grafo hijo→padres es un DAG multi-padre (los lazos cerrados A↔B siguen
FUERA de alcance: `register_mate` los rechaza como ciclo). El solver tiene DOS
caminos: un hijo con UN mate usa el camino cerrado exacto (`_solve_one`, INTACTO —
pose determinista bit-a-bit como siempre); un hijo con ≥2 mates resuelve su pose
6-DOF por `least_squares` con residuos por tipo (`_mate_residuals`) CONSISTENTES
con la semántica del camino cerrado (a residuo 0 coinciden con `_desired_current_
frames`), pero cada mate solo restringe SUS grados de libertad naturales (un
coincidente no fija el deslizamiento en el plano ni el giro sobre la normal; un
concéntrico deja deslizar y girar sobre el eje).
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
    """Ancestros de una pieza en el DAG de mates (feature_b → feature_a), MULTI-PADRE:
    un hijo puede tener varios padres (varios mates), así que se recorre el grafo entero
    (no una cadena única). Cierra ante ciclos vía el conjunto `seen`."""
    parents_of: dict[str, list[str]] = {}
    for m in mates.values():
        parents_of.setdefault(m["feature_b"], []).append(m["feature_a"])
    seen: set = set()
    stack = list(parents_of.get(feature_id, ()))
    while stack:
        p = stack.pop()
        if p in seen:
            continue
        seen.add(p)
        stack.extend(parents_of.get(p, ()))
    return seen


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
    # V6.3a: se PERMITE ≥2 mates al mismo hijo (multi-mate). El único límite es el ciclo:
    # si B ya es ancestro de A en el DAG, añadir A→B cerraría un lazo (A↔B fuera de alcance).
    if spec["feature_b"] in _mate_ancestors(mates, spec["feature_a"]) \
            or spec["feature_b"] == spec["feature_a"]:
        raise MateError(
            "El mate crearía un ciclo de ensamblaje (lazo cerrado A↔B fuera de alcance)"
        )
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


# --------------------------------------------------------------- multi-mate (V6.3a)
_MATE_TOL = 1e-3  # residuo (mm-equiv) por mate por encima del cual se declara conflicto
# perturbación FIJA (determinista — nada de random/tiempo, rompería la reproducibilidad de
# los tests) del guess si el least_squares no converge desde la identidad (guess degenerado,
# p. ej. una rotación de 180° que atasca el gradiente): un segundo intento con un pequeño
# giro sesga la búsqueda fuera del mínimo local.
_MATE_RETRY_PERTURB = (0.0, 0.0, 0.0, 0.37, 0.29, 0.19)


def _char_length(shape) -> float:
    """Longitud característica del sólido (mayor extensión del bbox) para escalar los
    residuos angulares a mm y que el costo mezcle unidades comparables. Fallback 1.0."""
    try:
        bb = shape.bounding_box()
        ext = max(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
        return float(ext) if ext > 1e-6 else 1.0
    except Exception:  # noqa: BLE001
        return 1.0


def _mate_residuals(a_origin, a_axis, b_origin, b_axis, mate_type, value, flip, L):
    """Residuos (mm-equivalentes) de UN mate dada la pose actual del conector de B
    (`b_origin`, `b_axis`) frente al conector del padre A. 0 = satisfecho. CONSISTENTE con
    `_desired_current_frames`: al evaluar la pose que produce el camino cerrado, todos los
    residuos son 0 (probado). Cada mate restringe SOLO sus GDL naturales.

    Longitud del bloque por tipo (fija, para least_squares): coincidente/distancia=4,
    concentrico=6, paralelo=3, angulo=1. Los términos angulares se escalan ×L."""
    n_a = _normalize(a_axis)
    n_b = _normalize(b_axis)
    d = (b_origin[0] - a_origin[0], b_origin[1] - a_origin[1], b_origin[2] - a_origin[2])
    if mate_type in ("coincidente", "distancia"):
        # posición: proyección de (o_b−o_a) sobre n_a = value (0 para coincidente)
        along = _dot(n_a, d) - value
        # orientación: normal de B ANTI-paralela a n_a (caras enfrentadas) — dirección
        # DEFINIDA (n_b→−n_a), no un cross ambiguo que aceptaría también n_b=+n_a
        align = [(n_b[i] + n_a[i]) * L for i in range(3)]
        return [along, *align]
    if mate_type == "concentrico":
        # ejes colineales: dos puntos del eje de B a distancia perpendicular 0 de la recta
        # (a_origin, n_a). NO fija ni el deslizamiento a lo largo ni el giro axial.
        out: list[float] = []
        for s in (0.0, L):
            p = (b_origin[0] + n_b[0] * s, b_origin[1] + n_b[1] * s, b_origin[2] + n_b[2] * s)
            w = (p[0] - a_origin[0], p[1] - a_origin[1], p[2] - a_origin[2])
            proj = _dot(w, n_a)
            out.extend((w[0] - n_a[0] * proj, w[1] - n_a[1] * proj, w[2] - n_a[2] * proj))
        return out
    if mate_type == "paralelo":
        # ejes paralelos (cualquiera de los dos sentidos): cross = 0. No mueve posición.
        c = _cross(n_b, n_a)
        return [c[0] * L, c[1] * L, c[2] * L]
    if mate_type == "angulo":
        ang = math.degrees(math.acos(max(-1.0, min(1.0, _dot(n_a, n_b)))))
        return [math.radians(ang - value) * L]
    raise MateError(f"Tipo de mate desconocido '{mate_type}'")


def _solve_multi(scene: dict, child_fid: str, child_mates: list) -> None:
    """Resuelve la pose 6-DOF del hijo `child_fid` para satisfacer SIMULTÁNEAMENTE ≥2 mates
    (least_squares sobre [tx,ty,tz, rvx,rvy,rvz], vector de rotación de scipy). La ROTACIÓN se
    parametriza SOBRE EL CENTRO de B (no el origen del mundo): si B está lejos del origen,
    rotar sobre el origen lo desplaza enormemente y acopla mal traslación↔rotación (el solver
    cambia posición por giro y no converge). Guess inicial = identidad (deja B donde el executor
    lo puso). Si no converge, reintenta UNA vez con una perturbación fija. Costo final >
    tolerancia → MateError nombrando los mates y su residuo. Aplica la pose por el MISMO camino
    que `_solve_one` (transform del shape + matrix si es instancia)."""
    import numpy as np
    from build123d import Pos, Rotation
    from scipy.optimize import least_squares
    from scipy.spatial.transform import Rotation as SciRot

    feat_b = scene[child_fid]
    L = _char_length(feat_b.shape)
    bb = feat_b.shape.bounding_box()
    c = np.array([(bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2])
    # conectores base (una sola extracción OCCT cada uno): el del padre (ya resuelto) y el de
    # B en su pose actual — rígidamente unidos, se transforman analíticamente en el bucle.
    a_conns = [connector_of(scene[m["feature_a"]].shape, m.get("ref_a")) for m in child_mates]
    b_conns = [connector_of(feat_b.shape, m.get("ref_b")) for m in child_mates]

    def _rt(x):
        """(t, R) del vector 6-DOF. La pose de un punto p: R·(p−c)+c+t; de una dir: R·d."""
        t = np.asarray(x[:3], dtype=float)
        Rm = SciRot.from_rotvec(np.asarray(x[3:], dtype=float)).as_matrix()
        return t, Rm

    def _conns(x):
        t, Rm = _rt(x)
        out = []
        for (b_o, b_a) in b_conns:
            o = Rm @ (np.asarray(b_o) - c) + c + t
            a = Rm @ np.asarray(b_a)
            out.append((tuple(o), tuple(a)))
        return out

    def resid(x):
        out: list[float] = []
        for (a_o, a_a), (b_o, b_a), m in zip(a_conns, _conns(x), child_mates):
            out.extend(_mate_residuals(
                a_o, a_a, b_o, b_a, m["type"], float(m.get("value", 0.0)),
                bool(m.get("flip", False)), L,
            ))
        return out

    def per_mate_error(x) -> list[float]:
        errs = []
        for (a_o, a_a), (b_o, b_a), m in zip(a_conns, _conns(x), child_mates):
            r = _mate_residuals(a_o, a_a, b_o, b_a, m["type"], float(m.get("value", 0.0)),
                                bool(m.get("flip", False)), L)
            errs.append(math.sqrt(sum(v * v for v in r)))
        return errs

    x0 = np.zeros(6)
    sol = least_squares(resid, x0, x_scale="jac")
    if max(per_mate_error(sol.x)) > _MATE_TOL:
        sol = least_squares(resid, x0 + np.asarray(_MATE_RETRY_PERTURB), x_scale="jac")
    errs = per_mate_error(sol.x)
    if max(errs) > _MATE_TOL:
        detalle = ", ".join(
            f"'{m['name']}' queda a {e:.2f} mm de satisfacerse"
            for m, e in zip(child_mates, errs) if e > _MATE_TOL
        )
        raise MateError(
            f"No se pueden satisfacer a la vez los mates del sólido '{child_fid}': {detalle}"
        )

    t, Rm = _rt(sol.x)
    trans = c - Rm @ c + t  # traslación efectiva del delta (rotación sobre el centro c)
    delta = [
        [float(Rm[0][0]), float(Rm[0][1]), float(Rm[0][2]), float(trans[0])],
        [float(Rm[1][0]), float(Rm[1][1]), float(Rm[1][2]), float(trans[1])],
        [float(Rm[2][0]), float(Rm[2][1]), float(Rm[2][2]), float(trans[2])],
        [0.0, 0.0, 0.0, 1.0],
    ]
    euler = euler_from_matrix(delta)
    feat_b.shape = Pos(float(trans[0]), float(trans[1]), float(trans[2])) * Rotation(*euler) * feat_b.shape
    if feat_b.matrix is not None:
        feat_b.matrix = multiply(delta, feat_b.matrix)


def solve_mates(scene: dict, mates: dict) -> None:
    """Recoloca las piezas mateadas en orden de dependencia (padres antes que hijos). El grafo
    hijo→padres es un DAG multi-padre garantizado sin ciclos por `register_mate`. Un hijo con
    UN mate va por el camino cerrado exacto (`_solve_one`); con ≥2 mates, por `_solve_multi`
    (least_squares acoplado). Orden topológico determinista (Kahn, empates por id de sólido)."""
    if not mates:
        return
    by_child: dict[str, list] = {}
    for m in mates.values():
        by_child.setdefault(m["feature_b"], []).append(m)
    pending = set(by_child)
    while pending:
        # un hijo está listo cuando TODOS sus padres ya están resueltos (no pendientes)
        ready = sorted(
            c for c in pending
            if all(m["feature_a"] not in pending for m in by_child[c])
        )
        if not ready:
            raise MateError("No se pudieron resolver los mates (ciclo de ensamblaje)")
        for child in ready:
            cms = by_child[child]
            if len(cms) == 1:
                _solve_one(scene, cms[0])
            else:
                _solve_multi(scene, child, cms)
            pending.discard(child)
