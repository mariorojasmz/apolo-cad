"""Estabilidad al vuelco: casco convexo 2D de la base de apoyo y margen del COG.

Geometría 2D pura (plano XY, mm). La regla de vuelco proyecta el centro de
gravedad del conjunto sobre la huella de las piezas ancladas al piso: si cae
fuera (margen negativo), la máquina vuelca; el margen positivo es la distancia
al borde más cercano de la base (cuánto puede desplazarse la carga antes de
comprometer el equilibrio).
"""

from __future__ import annotations

import math

Point = tuple[float, float]


def convex_hull_2d(points: list[Point]) -> list[Point]:
    """Casco convexo (monotone chain), en sentido antihorario, sin repetir el
    primer punto. Degenerados: 0/1/2 puntos (o colineales) devuelven la lista
    reducida tal cual."""
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) <= 2:
        return pts

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    hull = lower[:-1] + upper[:-1]
    return hull if len(hull) >= 3 else pts


def _seg_dist(p: Point, a: Point, b: Point) -> float:
    """Distancia de un punto a un segmento."""
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    if ll <= 1e-12:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def hull_margin_mm(point_xy: Point, hull: list[Point]) -> float:
    """Margen del punto respecto al casco: POSITIVO = dentro (distancia al borde
    más cercano), NEGATIVO = fuera (−distancia al casco). Cascos degenerados
    (<3 puntos = sin área de apoyo) siempre dan margen ≤ 0."""
    if not hull:
        return float("-inf")
    if len(hull) < 3:
        if len(hull) == 1:
            return -math.hypot(point_xy[0] - hull[0][0], point_xy[1] - hull[0][1])
        return -_seg_dist(point_xy, hull[0], hull[1])

    px, py = float(point_xy[0]), float(point_xy[1])
    inside = True
    dist = float("inf")
    n = len(hull)
    for i in range(n):
        a, b = hull[i], hull[(i + 1) % n]
        cross = (b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0])
        if cross < 0:  # hull antihorario → dentro = todo cross ≥ 0
            inside = False
        dist = min(dist, _seg_dist((px, py), a, b))
    return dist if inside else -dist
