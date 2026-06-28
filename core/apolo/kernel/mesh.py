"""Teselado de formas B-rep a mallas para el viewport."""

from __future__ import annotations


def mesh_payload(shape, tolerance: float = 0.4, angular_tolerance: float = 0.3) -> dict:
    vertices, triangles = shape.tessellate(tolerance, angular_tolerance)
    positions: list[float] = []
    for v in vertices:
        positions.extend((round(v.X, 4), round(v.Y, 4), round(v.Z, 4)))
    indices: list[int] = []
    for tri in triangles:
        indices.extend(tri)
    return {"positions": positions, "indices": indices}


def bbox_payload(shape) -> dict:
    bb = shape.bounding_box()
    return {
        "min": [round(bb.min.X, 3), round(bb.min.Y, 3), round(bb.min.Z, 3)],
        "max": [round(bb.max.X, 3), round(bb.max.Y, 3), round(bb.max.Z, 3)],
    }
