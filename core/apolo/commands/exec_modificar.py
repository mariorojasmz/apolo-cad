"""Executors que modifican una pieza EN SITIO: modelado directo de caras (borrar, empujar),
redondeo, chaflán, vaciado, taladro (`_drill_tool`) y uniones de ebanistería.

Salieron de `registry.py` (plan partir-nucleo-congelado, F3) SIN cambiar su código: la huella de
`tests/test_contrato_comandos.py` es la misma. `registry` los re-exporta por IDENTIDAD
(`_drill_tool` lo usan `exec_union` y `union_taller`); params de la fachada `.models`.
"""

from __future__ import annotations

from .errors import CommandError
from .escena import Feature, _require, _resolve_sel
from .exec_colocacion import _planar_face_frame
from .models import (
    AddJoineryParams,
    ChamferParams,
    DeleteFacesParams,
    DrillHoleParams,
    FilletParams,
    PushFaceParams,
    ShellParams,
)
from .state import ExecContext


def _exec_delete_faces(ctx: ExecContext, cmd_id: str, p: DeleteFacesParams) -> None:
    """Modelado directo (V5.3): borra caras y cura el hueco. Muta EN SITIO
    (conserva feature_id — mates/juntas sobreviven)."""
    from apolo.kernel.direct import DirectError, expand_tangent, remove_faces

    feat = _require(ctx.scene, p.feature)
    if p.faces.mode == "todas":
        raise CommandError(
            "Borrar TODAS las caras destruiría el sólido: usa delete_feature, o un "
            "selector acotado (cerca/cara/direccion)"
        )
    faces = _resolve_sel(feat.shape, p.faces, "face")
    try:
        if p.tangentes:
            faces = expand_tangent(feat.shape, faces)
        result = remove_faces(feat.shape, faces)
    except DirectError as exc:
        raise CommandError(
            f"No se pudo curar el hueco de {len(faces)} cara(s): {exc}"
        ) from exc
    feat.shape = result
    feat.make_unique()


def _exec_push_face(ctx: ExecContext, cmd_id: str, p: PushFaceParams) -> None:
    """Modelado directo (V5.3): empuja/jala una cara plana. Muta EN SITIO."""
    from apolo.kernel.direct import DirectError, push_pull

    feat = _require(ctx.scene, p.feature)
    faces = _resolve_sel(feat.shape, p.face, "face")
    if len(faces) != 1:
        raise CommandError(
            f"push_face necesita EXACTAMENTE una cara y tu selector devolvió "
            f"{len(faces)}: usa cerca con count=1 o cara del bbox"
        )
    try:
        result = push_pull(feat.shape, faces[0], p.distance)
    except DirectError as exc:
        raise CommandError(str(exc)) from exc
    feat.shape = result
    feat.make_unique()


def _shortest_edge_mm(edges) -> float | None:
    """Longitud de la arista más corta de la selección (None si no se puede medir).
    Da el TOPE accionable de un radio/distancia cuando OCCT rechaza la operación."""
    try:
        return min(e.length for e in edges)
    except Exception:
        return None


def _exec_fillet(ctx: ExecContext, cmd_id: str, p: FilletParams) -> None:
    from build123d import fillet

    feat = _require(ctx.scene, p.feature)
    edges = _resolve_sel(feat.shape, p.edges, "edge")
    try:
        result = fillet(edges, radius=p.radius)
    except Exception as exc:
        # Fix H (V6.1): mensaje accionable con el tope real en vez del crudo C++
        short = _shortest_edge_mm(edges)
        tope = (f" La arista más corta seleccionada mide {short:.1f} mm; el radio debe ser "
                f"bastante menor que eso.") if short else ""
        raise CommandError(
            f"Redondeo imposible (radio {p.radius:g} mm en {len(edges)} aristas): prueba un radio "
            f"menor o menos aristas.{tope}"
        ) from exc
    feat.shape = result
    feat.make_unique()


def _exec_chamfer(ctx: ExecContext, cmd_id: str, p: ChamferParams) -> None:
    from build123d import chamfer

    feat = _require(ctx.scene, p.feature)
    edges = _resolve_sel(feat.shape, p.edges, "edge")
    try:
        result = chamfer(edges, length=p.distance)
    except Exception as exc:
        short = _shortest_edge_mm(edges)
        tope = (f" La arista más corta seleccionada mide {short:.1f} mm; la distancia debe ser "
                f"menor.") if short else ""
        raise CommandError(
            f"Chaflán imposible (distancia {p.distance:g} mm en {len(edges)} aristas): prueba una "
            f"distancia menor.{tope}"
        ) from exc
    feat.shape = result
    feat.make_unique()


def _exec_shell(ctx: ExecContext, cmd_id: str, p: ShellParams) -> None:
    from build123d import offset

    feat = _require(ctx.scene, p.feature)
    # Fix H (V6.1): pre-check barato — un espesor que se come más de la mitad de la
    # dimensión MENOR deja la pieza sin cavidad (condición NECESARIA, sin falsos
    # positivos: solo rechaza lo que igual saldría vacío). Mensaje limpio antes de OCCT.
    bb = feat.shape.bounding_box()
    min_dim = min(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
    if 2 * p.thickness >= min_dim:
        raise CommandError(
            f"Vaciado imposible: un espesor de {p.thickness:g} mm no cabe en la pieza "
            f"(su dimensión menor es {min_dim:.1f} mm; el espesor debe ser < {min_dim / 2:.1f} mm)"
        )
    openings = _resolve_sel(feat.shape, p.openings, "face")
    try:
        result = offset(feat.shape, amount=-p.thickness, openings=openings)
    except Exception as exc:
        raise CommandError(
            f"Vaciado imposible con espesor {p.thickness:g} mm: prueba un espesor menor. Detalle: {exc}"
        ) from exc
    if result.volume <= 0:
        raise CommandError("El vaciado produjo un sólido vacío")
    feat.shape = result
    feat.make_unique()


_DRILL_DIRS = {
    "x": (1, 0, 0), "-x": (-1, 0, 0),
    "y": (0, 1, 0), "-y": (0, -1, 0),
    "z": (0, 0, 1), "-z": (0, 0, -1),
}


def _drill_tool(diameter: float, length: float, entry, direction):
    from build123d import Cylinder, Pos, Rotation

    cyl = Cylinder(diameter / 2.0, length)
    dx, dy, dz = (abs(direction[0]), abs(direction[1]), abs(direction[2]))
    if dx > 1e-9 and dy < 1e-9 and dz < 1e-9:
        cyl = Rotation(0, 90, 0) * cyl
    elif dy > 1e-9 and dx < 1e-9 and dz < 1e-9:
        cyl = Rotation(90, 0, 0) * cyl
    elif dx > 1e-9 or dy > 1e-9:  # dirección ARBITRARIA (V6.8-E: drill por cara rotada)
        from apolo.kernel.matrix import direction_to_euler

        cyl = Rotation(*direction_to_euler(direction)) * cyl
    center = tuple(entry[i] + direction[i] * length / 2.0 for i in range(3))
    return Pos(*center) * cyl


def _exec_drill_hole(ctx: ExecContext, cmd_id: str, p: DrillHoleParams) -> None:
    feat = _require(ctx.scene, p.feature)
    bb = feat.shape.bounding_box()
    through = (
        abs(bb.max.X - bb.min.X) + abs(bb.max.Y - bb.min.Y) + abs(bb.max.Z - bb.min.Z) + 10
    )
    if p.cara is not None:  # entrada DECLARATIVA por cara (V6.8-E)
        face, o, n, u, v = _planar_face_frame(
            feat, p.cara.model_dump(exclude_none=True), quien="cara del taladro"
        )
        du, dv = p.en_cara.u, p.en_cara.v
        entry = tuple(o[i] + u[i] * du + v[i] * dv for i in range(3))
        from build123d import Vertex

        from apolo.kernel.measure import measure_distance

        fuera = measure_distance(Vertex(*entry), face)["dist_mm"]
        if fuera > 1e-6:
            raise CommandError(
                f"en_cara (u={du}, v={dv}) cae FUERA de la cara (a {round(fuera, 3)} mm "
                "de su borde) — el taladro entraría al aire; u/v se miden desde el "
                "CENTRO de la cara (u = eje mayor)"
            )
        # −normal = perpendicular a la cara; un `axis` EXPLÍCITO gana
        if "axis" in p.model_fields_set:
            direction = _DRILL_DIRS[p.axis]
        else:
            direction = (-n[0], -n[1], -n[2])
    else:
        entry = p.position.tuple()
        direction = _DRILL_DIRS[p.axis]
    depth = p.depth if p.depth > 0 else through
    if p.thread:  # roscado: el 3D lleva la BROCA de machuelado (diameter se ignora)
        from apolo.library.engineering.threads import thread_spec

        dia = thread_spec(p.thread)["broca_mm"]
    else:
        dia = p.diameter
    tools = [_drill_tool(dia, depth + 0.01, entry, direction)]
    if p.counterbore_d and p.counterbore_depth:
        if p.counterbore_d <= dia:
            raise CommandError("El caladrillo debe ser mayor que el diámetro del taladro")
        tools.append(_drill_tool(p.counterbore_d, p.counterbore_depth, entry, direction))
    result = feat.shape
    for tool in tools:
        result = result - tool
    if result is None or result.volume <= 0:
        raise CommandError("El taladro eliminó todo el material del sólido")
    if abs(result.volume - feat.shape.volume) < 1e-6:
        raise CommandError("El taladro no toca el sólido: revisa el punto de entrada y el eje")
    feat.shape = result
    feat.make_unique()


def _exec_add_joinery(ctx: ExecContext, cmd_id: str, p: AddJoineryParams) -> None:
    from build123d import Box, Cylinder, Pos, Rotation

    if p.feature_a == p.feature_b:
        raise CommandError("Una unión no puede ser de una pieza consigo misma")
    a = _require(ctx.scene, p.feature_a)
    b = _require(ctx.scene, p.feature_b)
    ax = p.axis.tuple()
    m = max(abs(ax[0]), abs(ax[1]), abs(ax[2]))
    if m < 1e-9:
        raise CommandError("El eje de inserción no puede ser el vector nulo")
    if abs(ax[0]) == m:
        char, au = "x", (1.0 if ax[0] > 0 else -1.0, 0.0, 0.0)
    elif abs(ax[1]) == m:
        char, au = "y", (0.0, 1.0 if ax[1] > 0 else -1.0, 0.0)
    else:
        char, au = "z", (0.0, 0.0, 1.0 if ax[2] > 0 else -1.0)
    pos = p.position.tuple()

    def obox(u, v, d):  # caja: u,v perpendiculares; d a lo largo del eje
        return {"x": lambda: Box(d, u, v), "y": lambda: Box(u, d, v), "z": lambda: Box(u, v, d)}[char]()

    def cyl_axis(r, length, c):  # cilindro a lo largo del eje, centrado en c
        cy = Cylinder(r, length)
        if char == "y":
            cy = Rotation(90, 0, 0) * cy
        elif char == "x":
            cy = Rotation(0, 90, 0) * cy
        return Pos(*c) * cy

    def center(sh):
        bb = sh.bounding_box()
        return ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)

    def toward_b():  # dirección de A hacia B a lo largo del eje
        ca, cb = center(a.shape), center(b.shape)
        d = sum((cb[i] - ca[i]) * au[i] for i in range(3))
        s = 1.0 if d >= 0 else -1.0
        return (au[0] * s, au[1] * s, au[2] * s)

    try:
        if p.type == "espiga_mortaja":
            tw = toward_b()
            tc = tuple(pos[i] + tw[i] * p.depth / 2 for i in range(3))
            tenon = Pos(*tc) * obox(p.width, p.height, p.depth)
            mort = Pos(*tc) * obox(p.width + 2 * p.clearance, p.height + 2 * p.clearance, p.depth + p.clearance)
            a.shape = a.shape + tenon
            b.shape = b.shape - mort
            a.make_unique()
            b.make_unique()
        elif p.type == "dado":
            tw = toward_b()
            gc = tuple(pos[i] + tw[i] * p.depth / 2 for i in range(3))
            groove = Pos(*gc) * obox(p.width, p.height, p.depth)
            b.shape = b.shape - groove
            b.make_unique()
        elif p.type == "dowel":
            perp = (0.0, 0.0, 1.0) if char in ("x", "y") else (1.0, 0.0, 0.0)
            n = max(1, int(p.count))
            for i in range(n):
                off = (i - (n - 1) / 2.0) * p.spacing
                c = tuple(pos[k] + perp[k] * off for k in range(3))
                hole = cyl_axis(p.width / 2.0, p.depth, c)
                a.shape = a.shape - hole
                b.shape = b.shape - hole
                pin = cyl_axis(max(0.5, p.width / 2.0 - p.clearance), p.depth * 0.95, c)
                fid = f"{cmd_id}_pin{i + 1}"
                ctx.scene[fid] = Feature(fid, f"{p.name} clavija {i + 1}", pin, cmd_id)
            a.make_unique()
            b.make_unique()
        elif p.type == "rebaje":
            # corte de caja EN SITIO en B (galce de vidrio): X=width, Y=height, Z=depth.
            cut = Pos(*pos) * Box(p.width, p.height, p.depth)
            b.shape = b.shape - cut
            b.make_unique()
    except CommandError:
        raise
    except Exception as exc:
        raise CommandError(f"Unión '{p.type}' imposible: {exc}") from exc
    for feat in (a, b):
        if getattr(feat.shape, "volume", 1.0) <= 0:
            raise CommandError("La unión dejó una pieza vacía: revisa posición/medidas")
