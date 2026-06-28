"""Restricciones cinemáticas de LAZO CERRADO (espejo de ``assembly/mates.py``).

El árbol de juntas de Apolo resuelve cinemática DIRECTA (cadena abierta
padre→hijo). Un mecanismo real como una puerta plegable top-hung es un lazo
CERRADO: una hoja pivota en la jamba y, a la vez, su borde de ataque va cautivo
deslizando por un riel. Esa condición acopla dos juntas y quita 1 grado de
libertad.

Una ``rail_constraint`` declara: el punto ancla ``anchor`` (rígidamente unido al
hijo de ``joint``) debe permanecer SOBRE la recta ``(point, axis)``. El valor de
``joint`` deja de ser libre y se RESUELVE (búsqueda 1D acotada) para cumplirlo,
mientras la otra junta de la cadena actúa de driver. No teselamos geometría:
solo posamos el punto ancla con la FK (``feature_location``), así el solve es de
milisegundos y sirve para arrastre en vivo.
"""

from __future__ import annotations

from build123d import Pos, Vector

from apolo.robotics.pose import feature_location


class ConstraintError(Exception):
    pass


# tipos de restricción soportados (residuo = error a minimizar)
CONSTRAINT_TYPES = ("punto_en_recta", "punto_en_plano", "punto_coincidente", "distancia")


def register_constraint(constraints: dict, cmd_id: str, spec: dict) -> None:
    """Valida y registra una restricción en el diccionario del documento.

    La existencia de la junta referenciada se valida tras regenerar (igual que
    los mates validan sus features), porque la junta puede definirse después.
    """
    name = spec["name"]
    if name in constraints:
        raise ConstraintError(f"Ya existe una restricción llamada '{name}'")
    tipo = spec.get("tipo", "punto_en_recta")
    if tipo not in CONSTRAINT_TYPES:
        raise ConstraintError(f"Tipo de restricción desconocido: '{tipo}'")
    # recta/plano necesitan dirección (eje del riel / normal del plano) no nula
    if tipo in ("punto_en_recta", "punto_en_plano"):
        ax = spec.get("axis") or (0, 0, 0)
        if abs(ax[0]) + abs(ax[1]) + abs(ax[2]) < 1e-9:
            raise ConstraintError(
                "La dirección (eje del riel / normal del plano) no puede ser el vector nulo"
            )
    constraints[name] = {**spec, "command_id": cmd_id}


def _anchor_world(joints: dict, values: dict, child_fid: str, anchor) -> Vector:
    loc = feature_location(joints, values, child_fid)
    if loc is None:
        return Vector(*anchor)
    return (loc * Pos(anchor[0], anchor[1], anchor[2])).position


def _dist_to_line(p: Vector, q, direction) -> float:
    n = Vector(*direction)
    length = n.length
    if length < 1e-9:
        return (p - Vector(*q)).length
    n = n / length
    w = p - Vector(*q)
    return (w - n * w.dot(n)).length


def _residual(joints: dict, values: dict, con: dict) -> float:
    """Error (mm) de una restricción en la pose `values`. 0 = satisfecha."""
    joint = joints[con["joint"]]
    p = _anchor_world(joints, values, joint["child"], con["anchor"])
    tipo = con.get("tipo", "punto_en_recta")
    if tipo == "punto_en_recta":
        return _dist_to_line(p, con["point"], con["axis"])
    q = Vector(*con["point"])
    if tipo == "punto_en_plano":
        n = Vector(*con["axis"])
        length = n.length or 1.0
        return abs((p - q).dot(n / length))
    if tipo == "punto_coincidente":
        return (p - q).length
    if tipo == "distancia":
        return abs((p - q).length - float(con.get("value", 0.0)))
    return _dist_to_line(p, con["point"], con["axis"])


def solve_constraints(joints: dict, constraints: dict, free_values: dict) -> dict[str, float]:
    """Devuelve los valores de junta con las DEPENDIENTES resueltas para cumplir TODAS las
    restricciones a la vez (minimización N-D global acotada a los rangos de junta), no una
    a una. Las demás juntas se mantienen tal cual. Sin restricciones, es la identidad.

    Generaliza el caso 1-GDL (riel = `punto_en_recta`, una junta) a multi-restricción /
    N-GDL: varias juntas dependientes resueltas simultáneamente y tipos de restricción
    `punto_en_recta`/`punto_en_plano`/`punto_coincidente`/`distancia`. Equivalente al
    solver previo cuando hay una sola restricción 1-GDL."""
    values: dict[str, float] = {k: float(v) for k, v in free_values.items()}
    if not constraints:
        return values

    active = []
    for con in constraints.values():
        joint = joints.get(con["joint"])
        if joint is None:
            continue
        lo, hi = float(joint["lower"]), float(joint["upper"])
        if hi <= lo:
            continue
        active.append((con, lo, hi))
    if not active:
        return values

    # juntas dependientes únicas + sus límites (una junta puede salir en varias restricciones)
    dep: list[str] = []
    los: list[float] = []
    his: list[float] = []
    for con, lo, hi in active:
        j = con["joint"]
        if j not in dep:
            dep.append(j)
            los.append(lo)
            his.append(hi)

    from scipy.optimize import least_squares

    x0 = [min(max(float(values.get(j, 0.0)), los[i]), his[i]) for i, j in enumerate(dep)]

    def resid(x):
        trial = dict(values)
        for i, j in enumerate(dep):
            trial[j] = float(x[i])
        return [_residual(joints, trial, con) for con, _, _ in active]

    try:
        sol = least_squares(resid, x0, bounds=(los, his))
        for i, j in enumerate(dep):
            values[j] = float(sol.x[i])
    except Exception:
        pass  # si el solver no converge, deja los valores libres (no rompe el render/pose)
    return values
