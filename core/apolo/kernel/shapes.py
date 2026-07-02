"""Construcción de geometría con build123d (OCCT).

Convenciones del kernel:
- Unidades en milímetros, eje Z hacia arriba.
- Todas las primitivas se construyen centradas en el origen; ``place``
  aplica rotación (grados, intrínseca XYZ) y luego traslación.
- Los perfiles estructurales se extruyen a lo largo de Z, centrados.
"""

from __future__ import annotations

from build123d import (
    Box,
    Circle,
    Compound,
    Cylinder,
    Pos,
    Rectangle,
    Rotation,
    extrude,
)

# Secciones soportadas: nombre -> (ancho, alto) en mm. La serie modular se
# deduce del lado menor (módulos de ese tamaño con ranura en cada módulo).
PROFILE_SIZES: dict[str, tuple[float, float]] = {
    "20x20": (20.0, 20.0),
    "30x30": (30.0, 30.0),
    "40x40": (40.0, 40.0),
    "40x80": (80.0, 40.0),
    "45x45": (45.0, 45.0),
}


def place(shape, position: tuple[float, float, float], rotation: tuple[float, float, float]):
    """Rota (grados) y traslada una forma construida en el origen."""
    rx, ry, rz = rotation
    px, py, pz = position
    return Pos(px, py, pz) * Rotation(rx, ry, rz) * shape


def make_box(width: float, depth: float, height: float):
    return Box(width, depth, height)


def make_cylinder(radius: float, height: float):
    return Cylinder(radius, height)


def _module_centers(dimension: float, module: float) -> list[float]:
    n = max(1, round(dimension / module))
    start = -(dimension - module) / 2.0
    return [start + i * module for i in range(n)]


def _t_slot_cuts(width: float, height: float, module: float) -> list:
    """Caras 2D a restar de la sección: ranuras en T en las 4 caras y taladros."""
    open_w = 0.21 * module
    open_h = 0.14 * module
    cav_w = 0.48 * module
    cav_h = 0.20 * module
    bore_r = 0.105 * module

    cuts = []
    xs = _module_centers(width, module)
    ys = _module_centers(height, module)

    for cx in xs:
        for sign in (1.0, -1.0):
            edge = sign * height / 2.0
            cuts.append(Pos(cx, edge - sign * open_h / 2.0) * Rectangle(open_w, open_h * 1.02))
            cuts.append(
                Pos(cx, edge - sign * (open_h + cav_h / 2.0)) * Rectangle(cav_w, cav_h)
            )
    for cy in ys:
        for sign in (1.0, -1.0):
            edge = sign * width / 2.0
            cuts.append(Pos(edge - sign * open_h / 2.0, cy) * Rectangle(open_h * 1.02, open_w))
            cuts.append(
                Pos(edge - sign * (open_h + cav_h / 2.0), cy) * Rectangle(cav_h, cav_w)
            )
    for cx in xs:
        for cy in ys:
            cuts.append(Pos(cx, cy) * Circle(bore_r))
    return cuts


def make_structural_profile(profile: str, length: float):
    """Perfil de aluminio ranurado paramétrico, extruido a lo largo de Z."""
    if profile not in PROFILE_SIZES:
        raise ValueError(
            f"Perfil desconocido '{profile}'. Disponibles: {', '.join(PROFILE_SIZES)}"
        )
    width, height = PROFILE_SIZES[profile]
    module = min(width, height)

    section = Rectangle(width, height)
    for cut in _t_slot_cuts(width, height, module):
        section = section - cut

    solid = extrude(section, length)
    return Pos(0, 0, -length / 2.0) * solid


def make_rect_tube(width: float, height: float, wall: float, length: float):
    """Tubo estructural rectangular HUECO, extruido a lo largo de Z y centrado.

    width × height = sección exterior (mm); wall = espesor de pared. Con wall ≤ 0
    o pared mayor que media sección, se devuelve macizo. Es la pareja de ACERO de
    ``make_structural_profile`` (aluminio ranurado); misma convención de extrusión.
    """
    section = Rectangle(width, height)
    iw, ih = width - 2.0 * wall, height - 2.0 * wall
    if wall > 0 and iw > 0 and ih > 0:
        section = section - Rectangle(iw, ih)
    solid = extrude(section, length)
    return Pos(0, 0, -length / 2.0) * solid


def make_revolution(profile_pts, angle: float = 360.0):
    """Sólido de revolución alrededor de Z desde un perfil 2D [r, z] (r ≥ 0).

    El perfil es un polígono cerrado en el plano XZ (x = radio, z = altura). Lo
    usan el comando create_revolve y los builders del catálogo (rodamientos,
    tornillos, poleas).
    """
    from build123d import Axis, Plane, Polygon, revolve

    profile = Plane.XZ * Polygon(*[tuple(pt) for pt in profile_pts], align=None)
    return revolve(profile, Axis.Z, revolution_arc=angle)


def boolean_op(operation: str, target, tools: list):
    result = target
    for tool in tools:
        if operation == "union":
            result = result + tool
        elif operation == "cut":
            result = result - tool
        elif operation == "intersect":
            result = result & tool
        else:
            raise ValueError(f"Operación booleana desconocida: {operation}")
    return result


def move_rotated_about(shape, translate: tuple[float, float, float],
                       rotate: tuple[float, float, float],
                       center: tuple[float, float, float]):
    """Rota la forma alrededor de un CENTRO explícito (no el suyo) y la traslada.
    Para mover un GRUPO como cuerpo rígido: todas sus piezas giran sobre el mismo
    punto (el centro del bbox conjunto), no cada una sobre sí misma."""
    rx, ry, rz = rotate
    if rx or ry or rz:
        cx, cy, cz = center
        shape = Pos(cx, cy, cz) * Rotation(rx, ry, rz) * Pos(-cx, -cy, -cz) * shape
    tx, ty, tz = translate
    if tx or ty or tz:
        shape = Pos(tx, ty, tz) * shape
    return shape


def move_rotated_about_center(shape, translate: tuple[float, float, float], rotate: tuple[float, float, float]):
    """Rota la forma alrededor del centro de su caja envolvente y la traslada."""
    rx, ry, rz = rotate
    if rx or ry or rz:
        bb = shape.bounding_box()
        center = (bb.min + bb.max) * 0.5
        shape = (
            Pos(center.X, center.Y, center.Z)
            * Rotation(rx, ry, rz)
            * Pos(-center.X, -center.Y, -center.Z)
            * shape
        )
    tx, ty, tz = translate
    if tx or ty or tz:
        shape = Pos(tx, ty, tz) * shape
    return shape


def linear_copy(shape, index: int, spacing: tuple[float, float, float]):
    dx, dy, dz = spacing
    return Pos(dx * index, dy * index, dz * index) * shape


def compound_of(shapes: list) -> Compound:
    return Compound(children=list(shapes))
