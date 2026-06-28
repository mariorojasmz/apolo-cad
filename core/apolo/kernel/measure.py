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


def features_near(scene: dict, point, radius: float) -> list[dict]:
    """Features visibles cuya caja envolvente queda a ≤ `radius` mm de `point` (distancia
    del punto a la AABB), ordenadas de más cerca a más lejos. Consulta espacial barata."""
    px, py, pz = (float(point[0]), float(point[1]), float(point[2]))
    out: list[dict] = []
    for fid, f in scene.items():
        if not getattr(f, "visible", True):
            continue
        bb = f.shape.bounding_box()
        cx = min(max(px, bb.min.X), bb.max.X)
        cy = min(max(py, bb.min.Y), bb.max.Y)
        cz = min(max(pz, bb.min.Z), bb.max.Z)
        d = ((cx - px) ** 2 + (cy - py) ** 2 + (cz - pz) ** 2) ** 0.5
        if d <= radius:
            out.append({"id": fid, "nombre": f.name, "dist_mm": round(d, 3)})
    out.sort(key=lambda e: e["dist_mm"])
    return out
