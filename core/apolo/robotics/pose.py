"""Cinemática directa en el servidor: posa los sólidos según valores de junta.

Para comprobar colisiones del mecanismo en una pose concreta (lo mismo que el
viewport hace visualmente). Soporta los ejes de junta alineados con X/Y/Z
(los que generan nuestras plantillas); ejes arbitrarios se reportan como
no soportados en lugar de calcular mal.
"""

from __future__ import annotations

from build123d import Pos, Rotation


def _axis_char(axis: list[float]) -> str | None:
    ax, ay, az = (abs(axis[0]), abs(axis[1]), abs(axis[2]))
    if ax > 1e-6 and ay < 1e-6 and az < 1e-6:
        return "x"
    if ay > 1e-6 and ax < 1e-6 and az < 1e-6:
        return "y"
    if az > 1e-6 and ax < 1e-6 and ay < 1e-6:
        return "z"
    return None


def _joint_location(joint: dict, value: float):
    """Location local de la junta: T(o)·R(eje, v)·T(-o) o deslizamiento."""
    o = joint["origin"]
    axis = joint["axis"]
    char = _axis_char(axis)
    if char is None:
        raise ValueError(f"La junta '{joint['name']}' tiene eje no alineado con X/Y/Z")
    sign = 1.0 if axis[{"x": 0, "y": 1, "z": 2}[char]] >= 0 else -1.0
    v = value * sign
    if joint["type"] == "prismatica":
        vec = {"x": (v, 0, 0), "y": (0, v, 0), "z": (0, 0, v)}[char]
        return Pos(*vec)
    euler = {"x": (v, 0, 0), "y": (0, v, 0), "z": (0, 0, v)}[char]
    return Pos(o[0], o[1], o[2]) * Rotation(*euler) * Pos(-o[0], -o[1], -o[2])


def feature_location(
    joints: dict,
    values: dict[str, float],
    fid: str,
    _by_child: dict | None = None,
    _cache: dict | None = None,
    _depth: int = 0,
):
    """Location compuesta (FK) de un feature según la cadena de juntas, o None
    si no cuelga de ninguna. `joints` es el dict ``doc.joints``. Reutilizable
    por el solver de restricciones para posar un punto sin teselar geometría."""
    by_child = _by_child if _by_child is not None else {j["child"]: j for j in joints.values()}
    cache = _cache if _cache is not None else {}
    if fid in cache:
        return cache[fid]
    joint = by_child.get(fid)
    loc = None
    if joint is not None and _depth <= 64:
        parent_loc = feature_location(joints, values, joint["parent"], by_child, cache, _depth + 1)
        value = float(values.get(joint["name"], 0.0))
        local = None
        if value != 0.0 and joint["type"] != "fija":
            try:
                local = _joint_location(joint, value)
            except ValueError:
                local = None
        if parent_loc is not None and local is not None:
            loc = parent_loc * local
        else:
            loc = local if local is not None else parent_loc
    cache[fid] = loc
    return loc


def posed_shapes(doc, joint_values: dict[str, float]) -> tuple[dict, list[str]]:
    """Devuelve ({feature_id: shape posado}, avisos). Las features sin cadena
    cinemática o con valor 0 mantienen su forma original."""
    warnings: list[str] = [
        f"La junta '{j['name']}' tiene eje no alineado con X/Y/Z"
        for j in doc.joints.values()
        if j["type"] != "fija"
        and float(joint_values.get(j["name"], 0.0)) != 0.0
        and _axis_char(j["axis"]) is None
    ]
    by_child = {j["child"]: j for j in doc.joints.values()}
    cache: dict[str, object] = {}
    out: dict = {}
    for fid, feat in doc.scene.items():
        if not feat.visible:
            continue
        loc = feature_location(doc.joints, joint_values, fid, by_child, cache)
        out[fid] = (loc * feat.shape) if loc is not None else feat.shape
    return out, warnings
