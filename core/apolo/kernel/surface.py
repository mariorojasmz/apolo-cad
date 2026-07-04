"""Superficies básicas: contorno (boundary), parche sobre aristas (fill) y engrosado
(thicken). Funciones puras que envuelven build123d/OCCT con validación y errores
ACCIONABLES (nunca el crudo C++ de OCCT).

Una superficie es una Face/Shell de volumen 0: geometría de CONSTRUCCIÓN, no fabricable,
hasta que `thicken` la vuelve un sólido (pared de chapa). El caso de uso del vertical es
chute/tolva/deflector/guarda curva: boundary_surface|fill_surface → thicken.
"""

from __future__ import annotations


class SurfaceError(Exception):
    pass


def _wire_from_curves(curve_list, what):
    """Encadena una lista de curvas ({points, smooth}) en UN wire. Reusa
    path_from_points (Polyline/Spline; cierra el lazo si primer≈último punto)."""
    from build123d import Wire

    from apolo.kernel.sweep import SweepError, path_from_points

    edges = []
    for c in curve_list or []:
        pts = c.get("points") if isinstance(c, dict) else getattr(c, "points", None)
        smooth = bool(c.get("smooth", False)) if isinstance(c, dict) else bool(getattr(c, "smooth", False))
        try:
            w = path_from_points(pts, smooth=smooth, closed=False)
        except SweepError as exc:
            raise SurfaceError(f"{what}: {exc}") from exc
        edges.extend(w.edges())
    if not edges:
        raise SurfaceError(f"{what}: no se dio ninguna curva")
    try:
        return Wire(edges)
    except Exception as exc:  # noqa: BLE001
        raise SurfaceError(
            f"{what}: las curvas no conectan; el fin de cada tramo debe coincidir con el "
            f"inicio del siguiente (y el último con el primero para cerrar el lazo)"
        ) from exc


def boundary_surface(curves, points=None, holes=None):
    """Superficie (Face) acotada por un contorno cerrado.

    curves: lista de curvas {points:[[x,y,z],...], smooth:bool} que juntas forman UN
        lazo cerrado (una sola curva cerrada también vale).
    points: puntos 3D que la superficie debe tocar → parche NO plano (opcional).
    holes: lista de lazos interiores (cada uno una lista de curvas) → agujeros.
    """
    from build123d import Face, Vector

    exterior = _wire_from_curves(curves, "Contorno")
    interior_wires = [_wire_from_curves(h, "Hueco") for h in (holes or [])]
    surface_points = [Vector(*p) for p in (points or [])] or None
    try:
        face = Face.make_surface(
            exterior=exterior,
            surface_points=surface_points,
            interior_wires=interior_wires or None,
        )
    except Exception as exc:  # noqa: BLE001
        raise SurfaceError(
            "No se pudo construir la superficie: revisa que el contorno CIERRE, no se "
            "auto-cruce y que los puntos de forma queden cerca del contorno"
        ) from exc
    if face is None or face.area <= 0:
        raise SurfaceError("La superficie del contorno resultó vacía (área cero)")
    return face


def _edge_face_constraints(shape, edges):
    """Para cada arista seleccionada, su primera cara vecina en `shape` → constraint de
    continuidad G1 (ContinuityLevel.C1). Idioma OCP como en kernel/direct.py."""
    from build123d import ContinuityLevel, Face
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE
    from OCP.TopExp import TopExp
    from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

    m = TopTools_IndexedDataMapOfShapeListOfShape()
    TopExp.MapShapesAndAncestors_s(shape.wrapped, TopAbs_EDGE, TopAbs_FACE, m)
    constraints = []
    for e in edges:
        try:
            neighbours = list(m.FindFromKey(e.wrapped))
        except Exception:  # noqa: BLE001  # arista no presente en el mapa
            neighbours = []
        if not neighbours:
            raise SurfaceError(
                "Una arista seleccionada no pertenece al sólido; no hay cara de apoyo "
                "para la tangencia (usa tangent=false)"
            )
        constraints.append((e, Face(neighbours[0]), ContinuityLevel.C1))
    return constraints


def fill_surface_from_edges(shape, edges, tangent=False):
    """Parche (Face) que cubre la región acotada por `edges` (aristas YA resueltas de
    `shape`). tangent=True busca continuidad G1 con las caras vecinas — solo posible en
    geometría de continuación suave; en paredes perpendiculares OCCT no puede y se avisa.
    """
    from build123d import Face, Wire

    if not edges:
        raise SurfaceError("No se seleccionó ninguna arista para el parche")
    if tangent:
        constraints = _edge_face_constraints(shape, edges)
        try:
            face = Face.make_surface_patch(edge_face_constraints=constraints)
        except Exception as exc:  # noqa: BLE001
            raise SurfaceError(
                "No se pudo lograr continuidad tangente en este contorno (¿las caras "
                "vecinas son perpendiculares al parche?). Usa tangent=false para un "
                "parche simple"
            ) from exc
    else:
        try:
            face = Face.make_surface(exterior=Wire(edges))
        except Exception as exc:  # noqa: BLE001
            raise SurfaceError(
                "Las aristas seleccionadas no acotan una región cerrada; elige el lazo "
                "completo del hueco o borde a tapar"
            ) from exc
    if face is None or face.area <= 0:
        raise SurfaceError("El parche resultó vacío (área cero)")
    return face


def thicken_surface(surface_shape, thickness, both=False, flip=False):
    """Da espesor a una superficie (Face/Shell) a lo largo de su normal → sólido.

    thickness: espesor de pared (mm). flip invierte el lado. both engruesa `thickness`
    a CADA lado (espesor total 2×thickness), centrado en la superficie.
    """
    from functools import reduce

    from build123d import thicken

    faces = list(surface_shape.faces())
    if not faces:
        raise SurfaceError("El objeto a engrosar no tiene caras (no es una superficie)")
    amount = -float(thickness) if flip else float(thickness)
    try:
        solids = [thicken(to_thicken=f, amount=amount, both=bool(both)) for f in faces]
    except Exception as exc:  # noqa: BLE001
        raise SurfaceError(
            "No se pudo engrosar la superficie (¿doble curvatura que se auto-interseca "
            "con ese espesor?): prueba un espesor menor"
        ) from exc
    solid = solids[0] if len(solids) == 1 else reduce(lambda a, b: a + b, solids)
    if solid is None or not hasattr(solid, "volume") or solid.volume <= 0:
        raise SurfaceError("El engrosado produjo un sólido vacío (revisa espesor/normal)")
    return solid
