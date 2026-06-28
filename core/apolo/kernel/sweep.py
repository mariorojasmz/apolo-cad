"""Barridos (sweep) y transiciones (loft) desde perfiles de croquis.

El perfil lo aporta el sketcher (sketch_geom.sketch_to_face → cara 2D local). El
path del sweep se construye de una lista de puntos [x, y, z] (Polyline recta o
Spline suave); el perfil se orienta perpendicular al inicio del path. El loft
transiciona entre varias caras ya colocadas en sus planos.
"""

from __future__ import annotations


class SweepError(Exception):
    pass


def path_from_points(points, smooth: bool = False, closed: bool = False):
    """Wire del path desde puntos [x, y, z] (≥2). Polyline (recto) o Spline (suave).
    closed=True (o primer punto ≈ último) cierra el lazo: Polyline(close) / Spline
    periódica → el barrido produce un sólido en lazo (p. ej. una banda)."""
    from build123d import Polyline, Spline

    pts = [tuple(float(c) for c in p) for p in (points or [])]
    if len(pts) < 2:
        raise SweepError("La trayectoria del barrido necesita al menos 2 puntos [x, y, z]")
    for a, b in zip(pts, pts[1:]):
        if abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2]) < 1e-9:
            raise SweepError("La trayectoria tiene puntos consecutivos coincidentes")
    repeated_end = sum(abs(pts[0][i] - pts[-1][i]) for i in range(3)) < 1e-6
    loop = bool(closed) or repeated_end
    if smooth:
        spline_pts = pts[:-1] if repeated_end else pts  # spline periódica no duplica el cierre
        if len(spline_pts) < 2:
            raise SweepError("La trayectoria del barrido necesita al menos 2 puntos [x, y, z]")
        return Spline(*spline_pts, periodic=loop)
    return Polyline(*pts, close=loop)


def helix_path(radius: float, pitch: float, turns: float, lefthand: bool = False):
    """Hélice como trayectoria de barrido (resortes, roscas, espirales). pitch =
    avance por vuelta; altura total = pitch · turns."""
    from build123d import Helix

    radius, pitch, turns = float(radius), float(pitch), float(turns)
    if radius <= 0 or pitch <= 0 or turns <= 0:
        raise SweepError("La hélice necesita radius, pitch y turns positivos")
    return Helix(pitch=pitch, height=pitch * turns, radius=radius, lefthand=bool(lefthand))


def make_sweep(face_local, path, is_frenet: bool = False):
    """Barre el perfil (cara 2D local) a lo largo de un path ya construido (Wire/Edge,
    abierto, cerrado o hélice). El perfil se coloca en el inicio del path, perpendicular
    a su tangente inicial. is_frenet mantiene la orientación estable en lazos/hélices."""
    from build123d import Plane, Transition, sweep

    start = path @ 0  # posición en el parámetro 0
    tangent = path % 0  # tangente en el parámetro 0
    section = Plane(origin=(start.X, start.Y, start.Z), z_dir=(tangent.X, tangent.Y, tangent.Z)) * face_local
    try:
        # RIGHT = esquinas a inglete: necesario para que el barrido siga TODOS los
        # tramos de una polilínea (el default TRANSFORMED trunca en quiebros vivos).
        solid = sweep(section, path, transition=Transition.RIGHT, is_frenet=is_frenet)
    except Exception as exc:  # noqa: BLE001
        raise SweepError(
            "No se pudo barrer el perfil (¿la trayectoria gira más cerrado que el tamaño del perfil?)"
        ) from exc
    if solid is None or solid.volume <= 0:
        raise SweepError("El barrido produjo un sólido vacío")
    return solid


def make_loft(faces, ruled: bool = False):
    """Transición (loft) entre caras ya colocadas en sus planos. ruled=True usa
    superficies regladas (rectas); False, splines suaves."""
    from build123d import loft

    if len(faces) < 2:
        raise SweepError("La transición necesita al menos 2 secciones")
    try:
        solid = loft(faces, ruled=ruled)
    except Exception as exc:  # noqa: BLE001
        raise SweepError("No se pudo crear la transición entre las secciones") from exc
    if solid is None or solid.volume <= 0:
        raise SweepError("La transición produjo un sólido vacío")
    return solid
