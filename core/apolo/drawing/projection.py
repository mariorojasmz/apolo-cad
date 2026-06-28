"""Proyección 2D de la escena por eliminación de líneas ocultas (HLR/OCCT).

Cada vista se proyecta con build123d `project_to_viewport` y las aristas se
discretizan a polilíneas en coordenadas de la vista (mm reales del modelo).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from build123d import Box, Compound, GeomType, Pos

# origen del observador (dirección), vector "arriba" de cada vista
VIEW_SETUP = {
    "alzado": ((0, -1, 0), (0, 0, 1)),
    "lateral": ((1, 0, 0), (0, 0, 1)),
    "planta": ((0, 0, 1), (0, 1, 0)),
    "iso": ((1, -1, 0.8), (0, 0, 1)),
}

# dimensiones reales (ancho, alto) de cada vista ortográfica sobre el bbox 3D
VIEW_REAL_DIMS = {
    "alzado": (("X", "Z")),
    "lateral": (("Y", "Z")),
    "planta": (("X", "Y")),
}

CURVE_SAMPLES = 24


@dataclass
class ViewProjection:
    name: str
    visible: list[list[tuple[float, float]]] = field(default_factory=list)
    hidden: list[list[tuple[float, float]]] = field(default_factory=list)
    circles: list[tuple[float, float, float]] = field(default_factory=list)  # (cx, cy, r) en coords de vista
    bounds: tuple[float, float, float, float] = (0, 0, 0, 0)  # min_x, min_y, max_x, max_y

    @property
    def width(self) -> float:
        return self.bounds[2] - self.bounds[0]

    @property
    def height(self) -> float:
        return self.bounds[3] - self.bounds[1]


def _edge_to_polyline(edge) -> list[tuple[float, float]]:
    try:
        is_line = str(getattr(edge, "geom_type", "")).upper().endswith("LINE")
    except Exception:
        is_line = False
    n = 1 if is_line else CURVE_SAMPLES
    points = []
    for i in range(n + 1):
        try:
            p = edge @ (i / n)
        except Exception:
            continue
        points.append((float(p.X), float(p.Y)))
    return points if len(points) >= 2 else []


def _scene_compound(scene: dict):
    shapes = [f.shape for f in scene.values() if f.visible]
    if not shapes:
        raise ValueError("Escena vacía: no hay sólidos que proyectar")
    return shapes[0] if len(shapes) == 1 else Compound(children=shapes)


def _collect_circles(proj: ViewProjection, visible_edges) -> None:
    for edge in visible_edges:
        try:
            if edge.geom_type == GeomType.CIRCLE and edge.is_closed:
                c = edge.arc_center
                proj.circles.append((float(c.X), float(c.Y), float(edge.radius)))
        except Exception:
            continue


def view_center(scene: dict) -> tuple[float, float, float]:
    """Centro del bbox del modelo = origen de coordenadas de todas las vistas."""
    bb = _scene_compound(scene).bounding_box()
    return ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)


def world_to_view(name: str, p: tuple[float, float, float], center: tuple[float, float, float]) -> tuple[float, float]:
    """Mapea un punto 3D a coordenadas 2D de la vista (verificado empíricamente: sin espejo)."""
    dx, dy, dz = p[0] - center[0], p[1] - center[1], p[2] - center[2]
    if name == "planta":
        return dx, dy
    if name == "alzado":
        return dx, dz
    if name in ("lateral", "corte"):
        return dy, dz
    raise ValueError(f"Vista sin mapeo directo: '{name}'")


def project_views(
    scene: dict,
    views: list[str] | None = None,
    include_hidden: bool = False,
) -> dict[str, ViewProjection]:
    """Proyecta los sólidos visibles de la escena a las vistas pedidas."""
    compound = _scene_compound(scene)

    bb = compound.bounding_box()
    diag = max(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z, 1.0)
    center = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
    distance = diag * 12.0  # observador lejano ≈ proyección ortográfica

    out: dict[str, ViewProjection] = {}
    for name in views or list(VIEW_SETUP.keys()):
        direction, up = VIEW_SETUP[name]
        origin = tuple(center[i] + direction[i] * distance for i in range(3))
        visible_edges, hidden_edges = compound.project_to_viewport(
            viewport_origin=origin, viewport_up=up, look_at=center
        )
        proj = ViewProjection(name=name)
        _collect_circles(proj, visible_edges)
        for edge in visible_edges:
            poly = _edge_to_polyline(edge)
            if poly:
                proj.visible.append(poly)
        if include_hidden:
            for edge in hidden_edges:
                poly = _edge_to_polyline(edge)
                if poly:
                    proj.hidden.append(poly)
        xs = [x for poly in proj.visible + proj.hidden for x, _ in poly]
        ys = [y for poly in proj.visible + proj.hidden for _, y in poly]
        if xs:
            proj.bounds = (min(xs), min(ys), max(xs), max(ys))
        out[name] = proj
    return out


# eje de corte → (índice de coord, vista de proyección, plano build123d, mapeo 3D→2D)
_SECTION = {
    "x": (0, "lateral", "YZ", lambda d: (d[1], d[2])),
    "y": (1, "alzado", "XZ", lambda d: (d[0], d[2])),
    "z": (2, "planta", "XY", lambda d: (d[0], d[1])),
}


def section_projection(
    scene: dict, axis: str = "x", offset: float | None = None, include_hidden: bool = False
) -> tuple[ViewProjection, list[tuple[list[list[tuple[float, float]]], str]], float, str]:
    """CORTE perpendicular a `axis` ∈ {x,y,z} en `offset` (centro por defecto). Vista de la
    mitad coord ≤ offset; las caras de corte se devuelven con su MATERIAL (rayado).

    Devuelve (proyección 'corte', [(anillos, material), ...], coord del plano, eje). El
    primer anillo de cada polígono es el contorno; los siguientes, agujeros.
    """
    from build123d import Plane, section

    from apolo.library.catalog import CATALOG
    from apolo.library.materials import resolve_material

    idx, viewname, plane_name, to2d = _SECTION[axis]
    compound = _scene_compound(scene)
    bb = compound.bounding_box()
    center = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
    los = (bb.min.X, bb.min.Y, bb.min.Z)
    cut = center[idx] if offset is None else float(offset)

    margin = 10.0
    dims = [bb.max.X - bb.min.X + margin, bb.max.Y - bb.min.Y + margin, bb.max.Z - bb.min.Z + margin]
    keep = list(dims)
    keep[idx] = max(cut - (los[idx] - margin), 1e-3)  # de lo-margen hasta el corte
    bc = list(center)
    bc[idx] = (los[idx] - margin + cut) / 2
    half = compound & (Pos(*bc) * Box(*keep))
    if half is None or not half.solids():
        raise ValueError(f"El corte {axis.upper()}-{axis.upper()} no interseca el modelo")

    diag = max(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z, 1.0)
    direction, up = VIEW_SETUP[viewname]
    origin = tuple(center[i] + direction[i] * diag * 12.0 for i in range(3))
    visible_edges, hidden_edges = half.project_to_viewport(
        viewport_origin=origin, viewport_up=up, look_at=center
    )
    proj = ViewProjection(name="corte")
    _collect_circles(proj, visible_edges)
    for edge in visible_edges:
        poly = _edge_to_polyline(edge)
        if poly:
            proj.visible.append(poly)
    if include_hidden:
        for edge in hidden_edges:
            poly = _edge_to_polyline(edge)
            if poly:
                proj.hidden.append(poly)
    xs = [x for poly in proj.visible + proj.hidden for x, _ in poly]
    ys = [y for poly in proj.visible + proj.hidden for _, y in poly]
    if xs:
        proj.bounds = (min(xs), min(ys), max(xs), max(ys))

    plane = getattr(Plane, plane_name).offset(cut)

    def ring(wire) -> list[tuple[float, float]]:
        n = 64
        pts = []
        for i in range(n):
            p = wire @ (i / n)
            d = (float(p.X) - center[0], float(p.Y) - center[1], float(p.Z) - center[2])
            pts.append(to2d(d))
        return pts

    # sección POR FEATURE → cada cara de corte lleva el material de su pieza (rayado)
    polygons: list[tuple[list[list[tuple[float, float]]], str]] = []
    for feat in scene.values():
        if not getattr(feat, "visible", True):
            continue
        try:
            cross = section(feat.shape, section_by=plane)
        except Exception:
            continue
        if cross is None:
            continue
        mat = resolve_material(feat, CATALOG)
        for face in cross.faces():
            try:
                rings = [ring(face.outer_wire())] + [ring(w) for w in face.inner_wires()]
                polygons.append((rings, mat))
            except Exception:
                continue
    return proj, polygons, cut, axis


def detail_view(
    parent: ViewProjection, center: tuple[float, float], radius: float, scale: float = 2.0
) -> ViewProjection:
    """Vista de DETALLE: recorta la región circular (`center`,`radius`) de `parent` y la
    amplía ×`scale` (recentrada en el origen). Aproximada (conserva polilíneas con algún
    punto dentro del radio); suficiente para una burbuja de detalle."""
    cx, cy = center
    r2 = radius * radius

    def _seg_near(p1, p2):
        (x1, y1), (x2, y2) = p1, p2
        dx, dy = x2 - x1, y2 - y1
        ll = dx * dx + dy * dy
        if ll < 1e-12:
            return (x1 - cx) ** 2 + (y1 - cy) ** 2 <= r2
        t = max(0.0, min(1.0, ((cx - x1) * dx + (cy - y1) * dy) / ll))
        px, py = x1 + t * dx, y1 + t * dy
        return (px - cx) ** 2 + (py - cy) ** 2 <= r2

    def inside(poly):
        if any((px - cx) ** 2 + (py - cy) ** 2 <= r2 for px, py in poly):
            return True
        return any(_seg_near(poly[i], poly[i + 1]) for i in range(len(poly) - 1))

    out = ViewProjection(name="detalle")
    for poly in parent.visible:
        if inside(poly):
            out.visible.append([((px - cx) * scale, (py - cy) * scale) for px, py in poly])
    for poly in parent.hidden:
        if inside(poly):
            out.hidden.append([((px - cx) * scale, (py - cy) * scale) for px, py in poly])
    for (ccx, ccy, rr) in parent.circles:
        if (ccx - cx) ** 2 + (ccy - cy) ** 2 <= r2:
            out.circles.append(((ccx - cx) * scale, (ccy - cy) * scale, rr * scale))
    xs = [x for p in out.visible + out.hidden for x, _ in p]
    ys = [y for p in out.visible + out.hidden for _, y in p]
    if xs:
        out.bounds = (min(xs), min(ys), max(xs), max(ys))
    return out


def real_dims(scene: dict) -> dict[str, float]:
    """Dimensiones generales reales del modelo (para las cotas)."""
    shapes = [f.shape for f in scene.values() if f.visible]
    compound = shapes[0] if len(shapes) == 1 else Compound(children=shapes)
    bb = compound.bounding_box()
    return {
        "X": round(bb.max.X - bb.min.X, 1),
        "Y": round(bb.max.Y - bb.min.Y, 1),
        "Z": round(bb.max.Z - bb.min.Z, 1),
    }
