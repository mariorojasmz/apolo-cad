"""Medición geométrica exacta — distancia mínima y consulta espacial.

Hasta ahora el motor solo reportaba SOLAPE (interferencias); no había forma de medir
un hueco/gap ni preguntar "¿qué hay cerca de este punto?". Esto cubre ese vacío de
percepción para el agente. Read-only: no toca el documento.
"""

from __future__ import annotations


def measure_distance(shape_a, shape_b) -> dict:
    """Distancia mínima entre dos shapes (sólido, cara, arista) + los puntos más
    cercanos en cada uno, vía OCCT `BRepExtrema_DistShapeShape`. Si los shapes se tocan
    o solapan, la distancia es 0."""
    from OCP.BRepExtrema import BRepExtrema_DistShapeShape

    dss = BRepExtrema_DistShapeShape(shape_a.wrapped, shape_b.wrapped)
    if not dss.IsDone() or dss.NbSolution() < 1:
        raise ValueError("No se pudo calcular la distancia entre los elementos")
    p1 = dss.PointOnShape1(1)
    p2 = dss.PointOnShape2(1)
    return {
        "dist_mm": round(float(dss.Value()), 4),
        "punto_a": [round(p1.X(), 4), round(p1.Y(), 4), round(p1.Z(), 4)],
        "punto_b": [round(p2.X(), 4), round(p2.Y(), 4), round(p2.Z(), 4)],
    }


def _aabb_gap(amin, amax, bmin, bmax) -> float:
    """Distancia mínima entre dos AABB (0 si se solapan). Un punto es un AABB degenerado
    (amin == amax); así la consulta por punto/feature/caja comparte una sola fórmula."""
    d2 = 0.0
    for i in range(3):
        if amax[i] < bmin[i]:
            sep = bmin[i] - amax[i]
        elif bmax[i] < amin[i]:
            sep = amin[i] - bmax[i]
        else:
            sep = 0.0
        d2 += sep * sep
    return d2 ** 0.5


def _near_from_box(
    scene: dict, qmin, qmax, radius: float, exclude: set | None = None, limit: int | None = None
) -> list[dict]:
    """Features visibles cuya AABB queda a ≤ `radius` mm de la caja de consulta [qmin,qmax],
    ordenadas de más cerca a más lejos. Barrido O(n) sobre AABBs (sin índice espacial)."""
    exclude = exclude or set()
    out: list[dict] = []
    for fid, f in scene.items():
        if fid in exclude or not getattr(f, "visible", True):
            continue
        bb = f.shape.bounding_box()
        d = _aabb_gap(
            qmin, qmax,
            [bb.min.X, bb.min.Y, bb.min.Z], [bb.max.X, bb.max.Y, bb.max.Z],
        )
        if d <= radius:
            out.append({"id": fid, "nombre": f.name, "dist_mm": round(d, 3)})
    out.sort(key=lambda e: e["dist_mm"])
    return out[:limit] if limit is not None else out


def features_near(scene: dict, point, radius: float, limit: int | None = None) -> list[dict]:
    """Features visibles cuya caja envolvente queda a ≤ `radius` mm de `point` (distancia
    del punto a la AABB), ordenadas de más cerca a más lejos. Consulta espacial barata."""
    p = [float(point[0]), float(point[1]), float(point[2])]
    return _near_from_box(scene, p, p, radius, limit=limit)


def features_near_feature(
    scene: dict, feature_id: str, radius: float, limit: int | None = None
) -> list[dict]:
    """«¿Qué rodea a X?»: features cuya AABB queda a ≤ `radius` mm de la AABB del sólido
    `feature_id`, EXCLUYÉNDOLO. Distancia AABB-AABB, ordenada por cercanía."""
    f = scene.get(feature_id)
    if f is None:
        raise KeyError(feature_id)
    bb = f.shape.bounding_box()
    return _near_from_box(
        scene,
        [bb.min.X, bb.min.Y, bb.min.Z], [bb.max.X, bb.max.Y, bb.max.Z],
        radius, exclude={feature_id}, limit=limit,
    )


def features_near_box(scene: dict, box, radius: float, limit: int | None = None) -> list[dict]:
    """«¿Qué hay en esta región?»: features cuya AABB queda a ≤ `radius` mm de la caja
    `box` = [[min_x,min_y,min_z],[max_x,max_y,max_z]] (radius=0 = solo lo que la toca)."""
    (mn, mx) = box
    qmin = [float(mn[0]), float(mn[1]), float(mn[2])]
    qmax = [float(mx[0]), float(mx[1]), float(mx[2])]
    return _near_from_box(scene, qmin, qmax, radius, limit=limit)
