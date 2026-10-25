"""Executors de croquis y superficies: barrido, transición (loft), superficie de contorno,
parche, engrosar, revolución, polígono extruido, croquis extruido y revolucionado, e importar
STEP.

Salieron de `registry.py` (plan partir-nucleo-congelado, F4) SIN cambiar su código: la huella de
`tests/test_contrato_comandos.py` es la misma. `registry` los re-exporta por IDENTIDAD; params
de la fachada `.models`.
"""

from __future__ import annotations

from apolo.kernel import place

from .errors import CommandError
from .escena import Feature, _orient_axis, _require, _resolve_sel
from .models import (
    BoundarySurfaceParams,
    CreateExtrudePolyParams,
    CreateRevolveParams,
    FillSurfaceParams,
    ImportStepParams,
    SketchExtrudeParams,
    SketchLoftParams,
    SketchRevolveParams,
    SketchSweepParams,
    ThickenParams,
)
from .state import ExecContext


def _exec_sketch_sweep(ctx: ExecContext, cmd_id: str, p: SketchSweepParams) -> None:
    from apolo.kernel.sketch_geom import SketchError, sketch_to_face
    from apolo.kernel.sweep import SweepError, helix_path, make_sweep, path_from_points

    try:
        face, _ = sketch_to_face(p.sketch)
        if p.helix is not None:
            path = helix_path(p.helix.radius, p.helix.pitch, p.helix.turns, p.helix.lefthand)
            base = make_sweep(face, path, is_frenet=True)
        else:
            path = path_from_points(p.path, p.smooth, p.closed)
            base = make_sweep(face, path, is_frenet=p.closed)
    except (SketchError, SweepError) as exc:
        raise CommandError(f"Barrido: {exc}") from exc
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_sketch_loft(ctx: ExecContext, cmd_id: str, p: SketchLoftParams) -> None:
    from build123d import Plane

    from apolo.kernel.sketch_geom import SketchError, sketch_to_face
    from apolo.kernel.sweep import SweepError, make_loft

    try:
        faces = []
        for sec in p.sections:
            face, _ = sketch_to_face(sec.sketch)
            faces.append(Plane.XY.offset(sec.z) * face)
        base = make_loft(faces, p.ruled)
    except (SketchError, SweepError) as exc:
        raise CommandError(f"Transición: {exc}") from exc
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_boundary_surface(ctx: ExecContext, cmd_id: str, p: BoundarySurfaceParams) -> None:
    from apolo.kernel.surface import SurfaceError, boundary_surface

    try:
        base = boundary_surface(p.curves, points=p.points, holes=p.holes)
    except SurfaceError as exc:
        raise CommandError(f"Superficie: {exc}") from exc
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_fill_surface(ctx: ExecContext, cmd_id: str, p: FillSurfaceParams) -> None:
    from apolo.kernel.surface import SurfaceError, fill_surface_from_edges

    feat = _require(ctx.scene, p.feature)
    edges = _resolve_sel(feat.shape, p.edges, "edge")
    try:
        patch = fill_surface_from_edges(feat.shape, edges, tangent=p.tangent)
    except SurfaceError as exc:
        raise CommandError(f"Parche: {exc}") from exc
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, patch, cmd_id)


def _exec_thicken(ctx: ExecContext, cmd_id: str, p: ThickenParams) -> None:
    from apolo.kernel.shapes import is_surface
    from apolo.kernel.surface import SurfaceError, thicken_surface

    feat = _require(ctx.scene, p.feature)
    if not is_surface(feat.shape):
        raise CommandError(
            f"Engrosar necesita una SUPERFICIE (de boundary_surface o fill_surface); "
            f"'{feat.name}' no lo es (¿ya es un sólido?)"
        )
    try:
        solid = thicken_surface(feat.shape, p.thickness, both=p.both, flip=p.flip)
    except SurfaceError as exc:
        raise CommandError(f"Engrosar: {exc}") from exc
    feat.shape = solid
    feat.make_unique()


def _exec_create_revolve(ctx: ExecContext, cmd_id: str, p: CreateRevolveParams) -> None:
    from apolo.kernel.shapes import make_revolution

    try:
        base = make_revolution(p.profile, p.angle)
    except Exception as exc:
        raise CommandError(f"Perfil de revolución inválido: {exc}") from exc
    if base.volume <= 0:
        raise CommandError("La revolución produjo un sólido vacío")
    base = _orient_axis(base, p.axis)
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_create_extrude_poly(ctx: ExecContext, cmd_id: str, p: CreateExtrudePolyParams) -> None:
    from build123d import Polygon, Pos, extrude

    try:
        face = Polygon(*[tuple(pt) for pt in p.points], align=None)
        base = Pos(0, 0, -p.height / 2.0) * extrude(face, p.height)
    except Exception as exc:
        raise CommandError(f"Polígono inválido (¿auto-intersecciones?): {exc}") from exc
    if base.volume <= 0:
        raise CommandError("La extrusión produjo un sólido vacío")
    base = _orient_axis(base, p.axis)
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_sketch_extrude(ctx: ExecContext, cmd_id: str, p: SketchExtrudeParams) -> None:
    from build123d import extrude

    from apolo.kernel.sketch_geom import SketchError, place_sketch_on_plane, sketch_to_face

    try:
        face, _ = sketch_to_face(p.sketch)
        placed = place_sketch_on_plane(face, p.plane)
        base = extrude(placed, p.height)
    except SketchError as exc:
        raise CommandError(f"Croquis: {exc}") from exc
    except Exception as exc:
        raise CommandError(f"No se pudo extruir el croquis: {exc}") from exc
    if base.volume <= 0:
        raise CommandError("La extrusión del croquis produjo un sólido vacío")
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_sketch_revolve(ctx: ExecContext, cmd_id: str, p: SketchRevolveParams) -> None:
    from build123d import Axis, revolve

    from apolo.kernel.sketch_geom import SketchError, place_sketch_on_plane, sketch_to_face

    try:
        face, solved = sketch_to_face(p.sketch)
        min_x = min(v[0] for v in solved["points"].values())
        if min_x < -1e-6:
            raise SketchError(f"Para revolucionar, todas las x deben ser ≥ 0 (radio); hay x={min_x:g}")
        placed = place_sketch_on_plane(face, "xz")
        base = revolve(placed, Axis.Z, revolution_arc=p.angle)
    except SketchError as exc:
        raise CommandError(f"Croquis: {exc}") from exc
    except Exception as exc:
        raise CommandError(f"No se pudo revolucionar el croquis: {exc}") from exc
    if base.volume <= 0:
        raise CommandError("La revolución del croquis produjo un sólido vacío")
    shape = place(base, p.position.tuple(), p.rotation.tuple())
    ctx.scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)


def _exec_import_step(ctx: ExecContext, cmd_id: str, p: ImportStepParams) -> None:
    from apolo.sandbox import step_bytes_to_shape

    scene = ctx.scene
    data = ctx.attachments.get(p.attachment)
    if data is None:
        raise CommandError(f"No existe el adjunto '{p.attachment}' en el documento")
    try:
        imported = step_bytes_to_shape(data)
    except Exception as exc:
        raise CommandError(f"STEP inválido: {exc}") from exc

    solids = list(getattr(imported, "solids", lambda: [])()) if p.split else []
    if p.split and len(solids) > 1:
        for i, solid in enumerate(solids, start=1):
            shape = place(solid, p.position.tuple(), p.rotation.tuple())
            fid = f"{cmd_id}_{i}"
            scene[fid] = Feature(fid, f"{p.name} ({i})", shape, cmd_id)
    else:
        shape = place(imported, p.position.tuple(), p.rotation.tuple())
        scene[cmd_id] = Feature(cmd_id, p.name, shape, cmd_id)
