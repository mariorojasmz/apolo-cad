"""Vista EXPLOSIONADA (Fase 3 de planos pro).

`explode_scene` devuelve una COPIA de la escena con cada sólido separado a lo largo de un eje
(para ver cómo se arma el ensamblaje). NO toca el documento: clona los shapes con
`move_rotated_about_center`. Amplía la separación existente a lo largo del eje (`factor`>1 las
aleja del centro); si las piezas están casi coplanares en ese eje, las reparte por ORDEN con un
hueco uniforme. La composición (compose_sheet) lo proyecta como una vista más + globos de secuencia.
"""

from __future__ import annotations


def _axis_center(shape, i: int) -> float:
    bb = shape.bounding_box()
    return ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)[i]


def _axis_extent(shape, i: int) -> float:
    bb = shape.bounding_box()
    return (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)[i]


def explode_scene(scene: dict, axis: str = "z", factor: float = 2.0) -> dict:
    """Copia de `scene` con los sólidos VISIBLES separados a lo largo de `axis`. Por defecto
    AMPLÍA su separación desde el centro (`factor`×); si son casi coplanares en el eje, los reparte
    por orden con hueco uniforme (≈1.8× la mayor pieza). Devuelve {id: Feature} con shapes nuevos."""
    from apolo.commands.registry import Feature
    from apolo.kernel.shapes import move_rotated_about_center

    i_ax = {"x": 0, "y": 1, "z": 2}.get(axis, 2)
    vis = [(fid, f) for fid, f in scene.items() if getattr(f, "visible", True)]
    if len(vis) < 2:
        return {fid: f for fid, f in vis}

    centers = {fid: _axis_center(f.shape, i_ax) for fid, f in vis}
    lo, hi = min(centers.values()), max(centers.values())

    def _moved(fid, f, off):
        t = [0.0, 0.0, 0.0]
        t[i_ax] = off
        shape = move_rotated_about_center(f.shape, tuple(t), (0.0, 0.0, 0.0))
        return Feature(fid, f.name, shape, f.command_id, component=f.component)

    if (hi - lo) < 1.0:  # coplanares en el eje → reparto por orden (rank) con hueco uniforme
        order = sorted(vis, key=lambda kv: (_axis_center(kv[1].shape, (i_ax + 1) % 3),
                                            _axis_center(kv[1].shape, (i_ax + 2) % 3)))
        n = len(order)
        gap = max((_axis_extent(f.shape, i_ax) for _, f in order), default=50.0) * 1.8 * max(factor, 0.5)
        mid_rank = (n - 1) / 2.0
        return {fid: _moved(fid, f, (rank - mid_rank) * gap - centers[fid])
                for rank, (fid, f) in enumerate(order)}

    mid = (lo + hi) / 2.0  # amplía la separación desde el centro del ensamblaje
    return {fid: _moved(fid, f, (centers[fid] - mid) * (factor - 1.0)) for fid, f in vis}
