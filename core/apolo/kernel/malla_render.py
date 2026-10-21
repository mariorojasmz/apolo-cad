"""Malla de render rápida (plan teselado-rapido, D1 y D2).

D2. `triangular` lee la `Poly_Triangulation` de cada cara con `BRep_Tool.Triangulation_s` y la
pasa a numpy con la ubicación de la cara, en lugar de `Shape.tessellate` de build123d, que crea
un `Vector` por nodo (medido en la F0: casi todo el costo de teselar una cadena). Mismo mallado
(`Shape.mesh` con la misma deflexión: si la forma ya tiene una malla igual o más fina, la usa),
mismo orden de caras (`faces()`), mismos nodos y mismos triángulos, con la orientación invertida
en las caras REVERSED, como build123d. Cuenta además los triángulos de cada cara EN LA MISMA
llamada: lo que necesitan las zonas de acabado (plan seta-de-emergencia).

D1. `malla_instancia` dibuja una pieza que instancia una definición (`Feature.mesh_key` +
`matrix`) con la malla de la DEFINICIÓN, teselada UNA vez (`malla_local`, caché por identidad
del shape de la definición) y llevada al mundo con la matriz. Una matriz con determinante
negativo (espejo) invierte el orden de los triángulos para que las normales sigan hacia afuera.

Todo es OCCT (el mallado guarda la triangulación en la forma): en la API corre bajo
`STATE_LOCK`, como el `teselar` de `render_comun`. No toma ningún lock.
"""

from __future__ import annotations

#: Deflexión lineal (relativa) y angular de la malla de render: la de siempre de `render_comun`.
TOL_RENDER = 0.5
ANG_RENDER = 0.25

# Caché de la malla LOCAL de cada definición por IDENTIDAD de su shape (guarda la referencia y
# verifica `is`: un id reciclado no recibe la malla ajena).
_LOCAL_CACHE: dict = {}
_LOCAL_CAP = 512


def _solo_lectura(*arreglos):
    for a in arreglos:
        a.setflags(write=False)
    return arreglos


def triangular(shape, tolerance: float = TOL_RENDER, angular_tolerance: float = ANG_RENDER):
    """`(xyz, tri, por_cara)`: vértices (n, 3) float64 en el marco de `shape`, triángulos (m, 3)
    int64 y los triángulos de cada cara en el orden de `faces()` (una cara sin malla cuenta 0 y
    no aporta nodos). Los arreglos son de sólo lectura (se comparten entre cachés)."""
    import numpy as np
    from OCP.BRep import BRep_Tool
    from OCP.TopAbs import TopAbs_REVERSED
    from OCP.TopLoc import TopLoc_Location

    shape.mesh(tolerance, angular_tolerance)
    nodos, tris, por_cara = [], [], []
    base = 0
    for cara in shape.faces():
        loc = TopLoc_Location()
        poly = BRep_Tool.Triangulation_s(cara.wrapped, loc)
        if poly is None:
            por_cara.append(0)
            continue
        n, m = poly.NbNodes(), poly.NbTriangles()
        xyz = np.array([poly.Node(i).Coord() for i in range(1, n + 1)],
                       dtype=float).reshape(-1, 3)
        if not loc.IsIdentity():
            trsf = loc.Transformation()
            mat = np.array([[trsf.Value(r, c) for c in range(1, 5)] for r in range(1, 4)])
            xyz = xyz @ mat[:, :3].T + mat[:, 3]
        t = np.array([poly.Triangle(i).Get() for i in range(1, m + 1)],
                     dtype=np.int64).reshape(-1, 3) + (base - 1)
        if cara.wrapped.Orientation() == TopAbs_REVERSED:
            t = t[:, [0, 2, 1]]
        nodos.append(xyz)
        tris.append(t)
        por_cara.append(m)
        base += n
    xyz = np.concatenate(nodos) if nodos else np.zeros((0, 3))
    tri = np.concatenate(tris) if tris else np.zeros((0, 3), dtype=np.int64)
    _solo_lectura(xyz, tri)
    return xyz, tri, tuple(por_cara)


def malla_local(definicion):
    """`triangular(definicion)` con caché por identidad del shape de la definición."""
    key = id(definicion)
    hit = _LOCAL_CACHE.get(key)
    if hit is None or hit[0] is not definicion:
        if len(_LOCAL_CACHE) > _LOCAL_CAP:
            _LOCAL_CACHE.clear()
        hit = (definicion, *triangular(definicion))
        _LOCAL_CACHE[key] = hit
    return hit[1], hit[2], hit[3]


def malla_instancia(definicion, matriz):
    """`(xyz, tri, por_cara)` de una instancia: la malla local de `definicion` llevada al mundo
    con `matriz` (4×4 por filas, `Feature.matrix`). Los triángulos son los de la definición (el
    mismo arreglo) salvo con espejo (determinante < 0), que invierte su orden."""
    import numpy as np

    xyz, tri, por_cara = malla_local(definicion)
    m = np.asarray(matriz, dtype=float)
    rot = m[:3, :3]
    mundo = xyz @ rot.T + m[:3, 3]
    if np.linalg.det(rot) < 0:
        tri = tri[:, [0, 2, 1]]
        _solo_lectura(tri)
    _solo_lectura(mundo)
    return mundo, tri, por_cara


def definicion_de(feat, definiciones, forma=None):
    """`(definicion, matriz)` si la pieza se dibuja con la malla de su definición: tiene
    `mesh_key` y `matrix`, la definición está en `definiciones` (`commands.registry.DEFINITIONS`,
    que el caller pasa como dato: el kernel no importa `commands`) y la forma que se dibuja es
    la suya (`forma` = la de una pose o una sección es otra: se tesela ella). Si no, `(None,
    None)`."""
    if not definiciones or forma is not None and forma is not feat.shape:
        return None, None
    clave, matriz = getattr(feat, "mesh_key", None), getattr(feat, "matrix", None)
    if not clave or not matriz:
        return None, None
    definicion = definiciones.get(clave)
    return (definicion, matriz) if definicion is not None else (None, None)
