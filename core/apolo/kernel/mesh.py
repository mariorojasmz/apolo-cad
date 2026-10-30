"""Teselado de formas B-rep a mallas para el viewport.

Zonas de acabado (plan seta-de-emergencia, D2): `Shape.tessellate` concatena los triángulos
cara por cara en el orden de `faces()` pero no dice cuántos aporta cada una (F0).
`teselar_caras` los cuenta en la MISMA llamada (otro mallado entre medio, con otra tolerancia,
cambiaría los conteos) y `agrupar_por_zona` reordena los triángulos para que cada zona quede en
un rango contiguo `[desde, hasta)` de índices de triángulo. Una pieza sin zonas sale igual que
siempre.
"""

from __future__ import annotations


def triangulos_por_cara(shape) -> tuple[int, ...]:
    """Triángulos de la malla ACTUAL de cada cara de `shape`, en el orden de `faces()` (el que
    concatena `Shape.tessellate`). Una cara sin malla cuenta 0."""
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location

    out = []
    for cara in shape.faces():
        tri = BRep_Tool.Triangulation_s(cara.wrapped, TopLoc_Location())
        out.append(tri.NbTriangles() if tri is not None else 0)
    return tuple(out)


def teselar_caras(shape, tolerance: float, angular_tolerance: float):
    """`(vertices, triangulos, por_cara)`: el teselado de siempre más los triángulos de cada
    cara. `por_cara` es None si los conteos no suman el total (no se puede partir por zonas)."""
    vertices, triangles = shape.tessellate(tolerance, angular_tolerance)
    por_cara = triangulos_por_cara(shape)
    if sum(por_cara) != len(triangles):
        por_cara = None
    return vertices, triangles, por_cara


def agrupar_por_zona(triangles, por_cara, zona_por_cara) -> tuple[list, list[dict]]:
    """Reordena `triangles` (estable) para que los de cada zona queden juntos, en el orden en
    que aparece cada zona en `zona_por_cara`, y devuelve `(triangulos, rangos)` con
    `rangos = [{"zona", "desde", "hasta"}]` en índices de TRIÁNGULO (hasta excluido). Los
    índices de vértice no cambian. Lanza ValueError si `por_cara` y `zona_por_cara` no
    describen las mismas caras. Con `triangles` numpy (m, 3) (la malla de render,
    `malla_render`) devuelve numpy; con una lista, una lista."""
    if len(por_cara) != len(zona_por_cara) or sum(por_cara) != len(triangles):
        raise ValueError("Las zonas no corresponden a las caras de esta malla")
    grupos: dict[str, list] = {}   # zona → [(inicio, fin)] de sus caras, en orden
    inicio = 0
    for n, zona in zip(por_cara, zona_por_cara):
        grupos.setdefault(zona, []).append((inicio, inicio + n))
        inicio += n
    trozos: list = []
    rangos: list[dict] = []
    total = 0
    for zona, tramos in grupos.items():
        n = sum(b - a for a, b in tramos)
        if not n:
            continue
        rangos.append({"zona": zona, "desde": total, "hasta": total + n})
        trozos += [triangles[a:b] for a, b in tramos if b > a]
        total += n
    if hasattr(triangles, "ndim"):
        import numpy as np

        salida = np.concatenate(trozos) if trozos else triangles[:0]
        salida.setflags(write=False)
        return salida, rangos
    return [t for trozo in trozos for t in trozo], rangos


def mesh_payload(shape, tolerance: float = 0.4, angular_tolerance: float = 0.3,
                 zona_por_cara: tuple[str, ...] | None = None) -> dict:
    """`{positions, indices}` del shape. Con `zona_por_cara` (la zona de cada cara, D1) los
    triángulos van agrupados por zona y se agrega `zonas` (rangos de `agrupar_por_zona`); si no
    corresponden a las caras de la malla, sale el payload sin zonas. Sin ese argumento, el de
    siempre."""
    por_cara = None
    if zona_por_cara is None:
        vertices, triangles = shape.tessellate(tolerance, angular_tolerance)
    else:
        vertices, triangles, por_cara = teselar_caras(shape, tolerance, angular_tolerance)
    rangos = None
    if por_cara is not None and len(por_cara) == len(zona_por_cara):
        triangles, rangos = agrupar_por_zona(triangles, por_cara, zona_por_cara)
    positions: list[float] = []
    for v in vertices:
        positions.extend((round(v.X, 4), round(v.Y, 4), round(v.Z, 4)))
    indices: list[int] = []
    for tri in triangles:
        indices.extend(tri)
    out = {"positions": positions, "indices": indices}
    if rangos is not None:
        out["zonas"] = rangos
    return out


def bbox_payload(shape) -> dict:
    from .caja import caja

    bb = caja(shape)
    return {
        "min": [round(bb.min.X, 3), round(bb.min.Y, 3), round(bb.min.Z, 3)],
        "max": [round(bb.max.X, 3), round(bb.max.Y, 3), round(bb.max.Z, 3)],
    }
