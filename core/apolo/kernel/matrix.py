"""Álgebra de matrices 4x4 (filas) para las instancias de ensamblaje.

Convención idéntica a build123d: ``place()`` aplica T(pos)·R(rot) con rotación
intrínseca XYZ en grados (R = Rx·Ry·Rz). ``to_column_major16`` exporta en el
orden que espera three.js (Matrix4.fromArray).
"""

from __future__ import annotations

import math

Mat = list[list[float]]


def identity() -> Mat:
    return [[1.0, 0, 0, 0], [0, 1.0, 0, 0], [0, 0, 1.0, 0], [0, 0, 0, 1.0]]


def translation(x: float, y: float, z: float) -> Mat:
    m = identity()
    m[0][3], m[1][3], m[2][3] = x, y, z
    return m


def rotation_xyz(rx: float, ry: float, rz: float) -> Mat:
    """Rotación intrínseca XYZ en grados: R = Rx·Ry·Rz (como build123d Rotation)."""
    ax, ay, az = math.radians(rx), math.radians(ry), math.radians(rz)
    cx, sx = math.cos(ax), math.sin(ax)
    cy, sy = math.cos(ay), math.sin(ay)
    cz, sz = math.cos(az), math.sin(az)
    rx_m = [[1, 0, 0, 0], [0, cx, -sx, 0], [0, sx, cx, 0], [0, 0, 0, 1]]
    ry_m = [[cy, 0, sy, 0], [0, 1, 0, 0], [-sy, 0, cy, 0], [0, 0, 0, 1]]
    rz_m = [[cz, -sz, 0, 0], [sz, cz, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    return multiply(multiply(rx_m, ry_m), rz_m)


def multiply(a: Mat, b: Mat) -> Mat:
    return [
        [sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)]
        for i in range(4)
    ]


def compose_place(position: tuple[float, float, float], rotation: tuple[float, float, float]) -> Mat:
    """Matriz de place(): T(position) · R(rotation)."""
    return multiply(translation(*position), rotation_xyz(*rotation))


def axis_rotation_about_point(point: tuple[float, float, float], axis: str, angle_deg: float) -> Mat:
    """T(p) · R_eje(ángulo) · T(-p) para ejes globales x|y|z."""
    euler = {"x": (angle_deg, 0, 0), "y": (0, angle_deg, 0), "z": (0, 0, angle_deg)}[axis]
    return multiply(
        multiply(translation(*point), rotation_xyz(*euler)),
        translation(-point[0], -point[1], -point[2]),
    )


def rotation_about_center(center: tuple[float, float, float], rotation: tuple[float, float, float]) -> Mat:
    return multiply(
        multiply(translation(*center), rotation_xyz(*rotation)),
        translation(-center[0], -center[1], -center[2]),
    )


_AXIS_VEC = {"x": (1.0, 0.0, 0.0), "y": (0.0, 1.0, 0.0), "z": (0.0, 0.0, 1.0)}


def euler_between_axes(axis_from: str, axis_to: str) -> tuple[float, float, float]:
    """Euler XYZ (grados) de la rotación que lleva el eje global `axis_from`
    al eje `axis_to` (Rodrigues + extracción, exacta para giros de 90°)."""
    a = _AXIS_VEC[axis_from]
    b = _AXIS_VEC[axis_to]
    if a == b:
        return (0.0, 0.0, 0.0)
    # eje = a×b; si son antiparalelos (no ocurre entre ejes distintos) no aplica
    k = (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
    # ángulo = 90° entre ejes distintos; matriz de Rodrigues con cos=0, sin=1
    kx, ky, kz = k
    r = [
        [kx * kx, kx * ky - kz, kx * kz + ky],
        [kx * ky + kz, ky * ky, ky * kz - kx],
        [kx * kz - ky, ky * kz + kx, kz * kz],
    ]
    # extracción euler XYZ de R = Rx·Ry·Rz
    sy = max(-1.0, min(1.0, r[0][2]))
    ry = math.asin(sy)
    if abs(sy) < 0.999999:
        rx = math.atan2(-r[1][2], r[2][2])
        rz = math.atan2(-r[0][1], r[0][0])
    else:
        rx = math.atan2(r[2][1], r[1][1])
        rz = 0.0
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))


def frame(origin: tuple[float, float, float], x_axis, y_axis, z_axis) -> Mat:
    """Frame rígido 4x4 con columnas = ejes base (en mundo) y traslación = origen."""
    ox, oy, oz = origin
    return [
        [x_axis[0], y_axis[0], z_axis[0], ox],
        [x_axis[1], y_axis[1], z_axis[1], oy],
        [x_axis[2], y_axis[2], z_axis[2], oz],
        [0.0, 0.0, 0.0, 1.0],
    ]


def translation_of(m: Mat) -> tuple[float, float, float]:
    return (m[0][3], m[1][3], m[2][3])


def invert_rigid(m: Mat) -> Mat:
    """Inversa de una transformación rígida (R|t): (Rᵀ | -Rᵀt)."""
    rt = [[m[j][i] for j in range(3)] for i in range(3)]  # transpuesta de la 3x3
    t = (m[0][3], m[1][3], m[2][3])
    nt = [-(rt[i][0] * t[0] + rt[i][1] * t[1] + rt[i][2] * t[2]) for i in range(3)]
    return [
        [rt[0][0], rt[0][1], rt[0][2], nt[0]],
        [rt[1][0], rt[1][1], rt[1][2], nt[1]],
        [rt[2][0], rt[2][1], rt[2][2], nt[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


def euler_from_matrix(m: Mat) -> tuple[float, float, float]:
    """Euler XYZ (grados) de la 3x3 de R = Rx·Ry·Rz (inverso de rotation_xyz)."""
    sy = max(-1.0, min(1.0, m[0][2]))
    ry = math.asin(sy)
    if abs(sy) < 0.999999:
        rx = math.atan2(-m[1][2], m[2][2])
        rz = math.atan2(-m[0][1], m[0][0])
    else:
        rx = math.atan2(m[2][1], m[1][1])
        rz = 0.0
    return (math.degrees(rx), math.degrees(ry), math.degrees(rz))


def direction_frame(direction) -> tuple[tuple, tuple, tuple]:
    """Frame ortonormal (x, y, z) con Z = `direction` normalizada (Gram-Schmidt
    contra el eje de mundo menos alineado). Es la ÚNICA fuente del marco local de
    un miembro (perfil extruido en Z): la librería de ingletes proyecta al vecino
    en este mismo frame para que el azimut del corte case con el place."""
    dx, dy, dz = (float(c) for c in direction)
    n = math.sqrt(dx * dx + dy * dy + dz * dz)
    if n < 1e-9:
        raise ValueError("Dirección nula")
    z = (dx / n, dy / n, dz / n)
    ref = min(_AXIS_VEC.values(), key=lambda w: abs(w[0] * z[0] + w[1] * z[1] + w[2] * z[2]))
    x = (ref[1] * z[2] - ref[2] * z[1], ref[2] * z[0] - ref[0] * z[2], ref[0] * z[1] - ref[1] * z[0])
    xn = math.sqrt(x[0] ** 2 + x[1] ** 2 + x[2] ** 2)
    x = (x[0] / xn, x[1] / xn, x[2] / xn)
    y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
    return x, y, z


def direction_to_euler(direction) -> tuple[float, float, float]:
    """Euler XYZ (grados) que lleva el eje Z a `direction` (vector 3D arbitrario) —
    para orientar perfiles (extruidos en Z) a lo largo de aristas en cualquier
    dirección. Usa el frame de `direction_frame` (fuente única)."""
    x, y, z = direction_frame(direction)
    return euler_from_matrix(frame((0.0, 0.0, 0.0), x, y, z))


def to_column_major16(m: Mat) -> list[float]:
    """Para three.js Matrix4.fromArray (orden por columnas)."""
    return [round(m[row][col], 6) for col in range(4) for row in range(4)]


def transform_anchors(m: Mat, anchors: dict | None) -> dict | None:
    """Nuevo dict de anclas (V6.3b) con origin/axis transformados por la rígida `m` (origin =
    punto: R·o+t; axis = dirección: R·a). REEMPLAZA — no muta el dict de entrada (los
    checkpoints del regenerate comparten la referencia por el shallow copy de Feature)."""
    if not anchors:
        return anchors

    def _pt(p):
        x, y, z = float(p[0]), float(p[1]), float(p[2])
        return [m[i][0] * x + m[i][1] * y + m[i][2] * z + m[i][3] for i in range(3)]

    def _dir(v):
        x, y, z = float(v[0]), float(v[1]), float(v[2])
        return [m[i][0] * x + m[i][1] * y + m[i][2] * z for i in range(3)]

    return {
        name: {"origin": _pt(a["origin"]), "axis": _dir(a["axis"])}
        for name, a in anchors.items()
    }
