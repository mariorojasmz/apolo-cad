"""Cascos convexos para la colisión física (fidelidad, no AABB).

Tesela cada sólido OCCT y reduce sus vértices al casco convexo → un conjunto de
puntos que MuJoCo usa como geometría de colisión (MuJoCo construye el casco
convexo de los vértices de una malla). Es el salto de fidelidad sobre la caja
envolvente del drop-test: un eje encaja en su alojamiento y un rodillo apoya en
el larguero por su forma real, no por su bbox.

Cacheado por IDENTIDAD del shape OCCT (las features no mutan el shape in-place
→ seguro), igual que la caché de mesh/render.
"""

from __future__ import annotations

# id(shape) -> (shape, vértices). Guardamos la REFERENCIA al shape (no solo el id):
# sin ella el shape se recolecta y Python REUSA su id → otra pieza recibiría este
# casco (bug real visto en la suite). Con la ref fuerte el id no se puede reusar, y
# además verificamos identidad en el lookup. Igual que la caché de mesh del render.
_HULL_CACHE: dict[int, tuple] = {}
_HULL_CAP = 4096


def _convex_hull(pts: list[tuple]) -> list[tuple]:
    """Vértices del casco convexo de una nube de puntos (scipy). Si hay <4 puntos
    o son degenerados/coplanares, devuelve la nube tal cual (MuJoCo igual hace el
    casco; un caso degenerado no debe romper la simulación)."""
    if len(pts) < 4:
        return pts
    try:
        import numpy as np
        from scipy.spatial import ConvexHull

        arr = np.asarray(pts, dtype=float)
        hull = ConvexHull(arr)
        return [tuple(float(c) for c in arr[i]) for i in sorted(set(int(i) for i in hull.vertices))]
    except Exception:  # noqa: BLE001 — degenerado/coplanar → nube original
        return pts


def hull_vertices(shape) -> list[tuple[float, float, float]]:
    """Vértices (mm) del casco convexo del sólido, cacheados por identidad del shape."""
    key = id(shape)
    cached = _HULL_CACHE.get(key)
    if cached is not None and cached[0] is shape:
        return cached[1]
    try:
        verts, _ = shape.tessellate(1.5, 0.8)
        pts = [(float(v.X), float(v.Y), float(v.Z)) for v in verts]
    except Exception:  # noqa: BLE001
        pts = []
    hull = _convex_hull(pts)
    if len(_HULL_CACHE) > _HULL_CAP:
        _HULL_CACHE.clear()
    _HULL_CACHE[key] = (shape, hull)
    return hull


# id(shape) -> (shape, [vértices por sólido]): misma regla de identidad que `_HULL_CACHE`.
_CASCOS_CACHE: dict[int, tuple] = {}


def cascos(shape) -> list[list[tuple[float, float, float]]]:
    """Un casco convexo POR SÓLIDO de la pieza (V8.9 F7b, defecto 6): un `run_script` que
    devuelve un túnel en U como tres sólidos (techo y dos laterales) es UNA pieza, y su casco
    único tapaba la boca del túnel (la caja quedaba contra ella). Con un solo sólido es
    exactamente `[hull_vertices(shape)]`. Un sólido CÓNCAVO sigue siendo un casco (la
    descomposición convexa queda fuera)."""
    key = id(shape)
    cached = _CASCOS_CACHE.get(key)
    if cached is not None and cached[0] is shape:
        return cached[1]
    try:
        solidos = list(shape.solids())
    except Exception:  # noqa: BLE001
        solidos = []
    if len(solidos) <= 1:
        out = [hull_vertices(shape)]
    else:
        out = [hull_vertices(s) for s in solidos]
    if len(_CASCOS_CACHE) > _HULL_CAP:
        _CASCOS_CACHE.clear()
    _CASCOS_CACHE[key] = (shape, out)
    return out
