"""Render servidor de la escena a PNG (sin GPU, vía matplotlib).

Suficiente para que el agente IA "mire" el modelo con visión y para
miniaturas. No pretende ser fotorrealista.
"""

from __future__ import annotations

import io

VIEW_ANGLES = {
    "iso": (22, -55),
    "frente": (0, -90),
    "planta": (89, -90),
    "lateral": (0, 0),
}

PALETTE = ["#5b8def", "#46b58a", "#c77d4f", "#8e6fd8", "#d8a03a", "#5fa8c9", "#c75f7c"]

_AXIS_IDX = {"x": 0, "y": 1, "z": 2}


def _shape_of(feat, shapes_override):
    return shapes_override.get(feat.id, feat.shape) if shapes_override else feat.shape


def resolve_angles(
    view: str = "iso", azimuth: float | None = None, elevation: float | None = None
) -> tuple[float, float]:
    """Resuelve los ángulos (elev, azim) de cámara en GRADOS (convención de view_init de
    matplotlib). Parte del preset nombrado `view` y, si se pasan, `elevation`/`azimuth` los
    ANULAN (override parcial permitido: dar solo uno conserva el otro del preset). Fuente única
    compartida por apply_camera (matplotlib) y render_scene_vtk (VTK) → mismo punto de vista."""
    base_elev, base_azim = VIEW_ANGLES.get(view, VIEW_ANGLES["iso"])
    elev = base_elev if elevation is None else float(elevation)
    azim = base_azim if azimuth is None else float(azimuth)
    return elev, azim


def apply_camera(
    ax,
    bmins,
    bmaxs,
    *,
    zoom: float = 1.0,
    proportional: bool = False,
    view: str = "iso",
    azimuth: float | None = None,
    elevation: float | None = None,
    roll: float = 0.0,
):
    """Fija límites/box_aspect/ángulos del Axes3D para una caja envolvente dada. ÚNICA
    fuente de verdad de la cámara → la comparten render_scene_png y el pick (kernel/pick.py),
    de modo que proyectar mundo→pantalla coincida con lo que se dibuja. `azimuth`/`elevation`
    (grados) anulan el ángulo del preset `view` si se pasan; `roll` (grados) gira sobre el eje de
    visión. Devuelve (half, center)."""
    import numpy as np

    bmins = np.asarray(bmins, dtype=float)
    bmaxs = np.asarray(bmaxs, dtype=float)
    center = (bmins + bmaxs) / 2
    z = max(zoom, 1e-6)
    if proportional:
        half_axes = np.maximum(bmaxs - bmins, 1e-6) / 2 * 1.05 / z
        ax.set_xlim(center[0] - half_axes[0], center[0] + half_axes[0])
        ax.set_ylim(center[1] - half_axes[1], center[1] + half_axes[1])
        ax.set_zlim(max(0.0, center[2] - half_axes[2]), center[2] + half_axes[2])
        ax.set_box_aspect(tuple(np.maximum(bmaxs - bmins, 1e-6)))
        half = float(max(half_axes))
    else:
        half = float(max(bmaxs - bmins)) / 2 * 1.05 / z
        ax.set_xlim(center[0] - half, center[0] + half)
        ax.set_ylim(center[1] - half, center[1] + half)
        ax.set_zlim(max(0.0, center[2] - half), center[2] + half)
        ax.set_box_aspect((1, 1, 1))
    elev, azim = resolve_angles(view, azimuth, elevation)
    try:
        ax.view_init(elev=elev, azim=azim, roll=roll)   # roll: matplotlib ≥3.6
    except TypeError:
        ax.view_init(elev=elev, azim=azim)
    return half, center


def _clip_to_section(shape, section: str, lo, hi):
    """Recorta `shape` a la mitad con coord ≤ centro del eje `section` (booleana con
    una semicaja, misma técnica que drawing/projection.py) → deja ver el interior.
    Devuelve el sólido recortado, o None si la intersección queda vacía."""
    import numpy as np
    from build123d import Box, Pos

    idx = _AXIS_IDX.get(section)
    if idx is None:
        return shape
    center = (lo + hi) / 2.0
    cut = float(center[idx])
    margin = 10.0
    size = (hi - lo) + 2 * margin
    keep = size.copy()
    keep[idx] = max(cut - (lo[idx] - margin), 1e-3)  # de lo-margen hasta el corte
    bc = center.copy()
    bc[idx] = (lo[idx] - margin + cut) / 2.0
    box = Pos(float(bc[0]), float(bc[1]), float(bc[2])) * Box(
        float(keep[0]), float(keep[1]), float(keep[2])
    )
    try:
        out = shape & box
        if out is None or float(out.volume) < 1e-6:
            return None
    except Exception:
        return shape
    return out


def _draw_view(
    ax,
    feats,
    view: str,
    *,
    shapes_override,
    highlight: set,
    fit: set,
    show_axes: bool,
    show_bbox: bool,
    zoom: float,
    proportional: bool,
    labels: bool,
    section,
    scene_lohi,
    title: str,
    colors: dict | None = None,
    frame_bbox=None,
    azimuth: float | None = None,
    elevation: float | None = None,
    roll: float = 0.0,
) -> None:
    """Dibuja UNA vista de la escena en el Axes3D `ax` (extraído para reusarlo en
    subplots multivista). Replica el comportamiento histórico de render_scene_png."""
    import numpy as np
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    mins = np.array([np.inf] * 3)
    maxs = np.array([-np.inf] * 3)
    hmins = np.array([np.inf] * 3)
    hmaxs = np.array([-np.inf] * 3)
    fmins = np.array([np.inf] * 3)
    fmaxs = np.array([-np.inf] * 3)
    lo, hi = scene_lohi
    label_pts: list[tuple] = []
    for i, feat in enumerate(feats):
        shape = _shape_of(feat, shapes_override)
        if section:
            shape = _clip_to_section(shape, section, lo, hi)
            if shape is None:
                continue
        vertices, triangles = shape.tessellate(0.5, 0.25)
        pts = np.array([[v.X, v.Y, v.Z] for v in vertices])
        if len(pts) == 0:
            continue
        mins = np.minimum(mins, pts.min(axis=0))
        maxs = np.maximum(maxs, pts.max(axis=0))
        if feat.id in fit:
            fmins = np.minimum(fmins, pts.min(axis=0))
            fmaxs = np.maximum(fmaxs, pts.max(axis=0))
        polys = pts[np.array(triangles)]
        is_hi = feat.id in highlight
        if not highlight or is_hi:  # resaltado o sin resaltado → color vivo
            # color por pieza (mismo que el viewport web: DOC.colors o paleta) si se pasó el mapa
            color = (colors or {}).get(feat.id) or PALETTE[i % len(PALETTE)]
            alpha = 1.0
            if is_hi:
                hmins = np.minimum(hmins, pts.min(axis=0))
                hmaxs = np.maximum(hmaxs, pts.max(axis=0))
        else:  # hay resaltados y este no lo es → atenuado
            color, alpha = "#9aa3ad", 0.18
        ax.add_collection3d(
            Poly3DCollection(
                polys, facecolors=color, edgecolors=color, linewidths=0, shade=True, alpha=alpha
            )
        )
        if labels and (not highlight or is_hi):
            label_pts.append((feat.id, pts.mean(axis=0)))

    # encuadre: frame_bbox fija la cámara a una caja externa (p. ej. el modelo COMPLETO en
    # cada paso de un manual → cámara estable, las piezas aparecen en su sitio final); si no,
    # fit_ids ciñe a esos sólidos; si tampoco, a lo dibujado.
    if frame_bbox is not None:
        bmins, bmaxs = np.asarray(frame_bbox[0], float), np.asarray(frame_bbox[1], float)
    elif fit and np.isfinite(fmins).all():
        bmins, bmaxs = fmins, fmaxs
    else:
        bmins, bmaxs = mins, maxs
    half, _ = apply_camera(
        ax, bmins, bmaxs, zoom=zoom, proportional=proportional, view=view,
        azimuth=azimuth, elevation=elevation, roll=roll,
    )

    if show_axes:
        axlen = half * 0.6
        ax.plot([0, axlen], [0, 0], [0, 0], color="#e0524d", linewidth=2.0)  # X rojo
        ax.plot([0, 0], [0, axlen], [0, 0], color="#46b58a", linewidth=2.0)  # Y verde
        ax.plot([0, 0], [0, 0], [0, axlen], color="#5b8def", linewidth=2.0)  # Z azul

    if show_bbox:
        bb_min = hmins if np.isfinite(hmins).all() else mins
        bb_max = hmaxs if np.isfinite(hmaxs).all() else maxs
        _draw_bbox(ax, bb_min, bb_max)

    if label_pts:
        for fid, c in label_pts:
            # matplotlib proyecta el texto 3D según la cámara (Axes3D.text)
            ax.text(
                float(c[0]), float(c[1]), float(c[2]), fid,
                fontsize=6, color="#10161d", ha="center", va="center", zorder=10,
            )

    ax.set_xlabel("X mm")
    ax.set_ylabel("Y mm")
    ax.set_zlabel("Z mm")
    ax.set_title(title)


def render_scene_png(
    scene: dict,
    view: str = "iso",
    size_px: int = 880,
    highlight_ids: list[str] | None = None,
    show_axes: bool = False,
    show_bbox: bool = False,
    shapes_override: dict | None = None,
    fit_ids: list[str] | None = None,
    zoom: float = 1.0,
    proportional: bool = False,
    views: list[str] | None = None,
    labels: bool = False,
    section: str | None = None,
    clean: bool = False,
    colors: dict | None = None,
    frame_bbox=None,
    ignore_visibility: bool = False,
    azimuth: float | None = None,
    elevation: float | None = None,
    roll: float = 0.0,
) -> bytes:
    """`fit_ids` encuadra la cámara solo en esos sólidos (primer plano; el resto se
    sigue dibujando). `zoom>1` acerca (`<1` aleja). `proportional=True` ciñe los ejes
    al bbox con proporciones REALES (en vez del cubo).

    `views` (≥2) compone varias vistas en una sola imagen (subplots 2 columnas) — menos
    oclusión en una sola llamada. `labels=True` rotula el id de cada sólido (o solo los
    `highlight_ids`) sobre la imagen. `section` ∈ {x,y,z} recorta cada sólido a la mitad
    coord ≤ centro de ese eje para VER DENTRO.

    `azimuth`/`elevation` (grados) anulan el ángulo del preset `view` (override parcial
    permitido). Solo se aplican en vista ÚNICA; en multivista (`views`) se ignoran (cada
    vista nombrada conserva su preset)."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    feats = list(scene.values()) if ignore_visibility else [f for f in scene.values() if f.visible]
    if not feats:
        raise ValueError("Escena vacía: nada que renderizar")
    highlight = set(highlight_ids or [])
    fit = set(fit_ids or [])

    # bbox de escena (barato, sin teselar) — necesario solo para recortar la sección
    lo = np.array([np.inf] * 3)
    hi = np.array([-np.inf] * 3)
    if section:
        for feat in feats:
            bb = _shape_of(feat, shapes_override).bounding_box()
            lo = np.minimum(lo, [bb.min.X, bb.min.Y, bb.min.Z])
            hi = np.maximum(hi, [bb.max.X, bb.max.Y, bb.max.Z])
    scene_lohi = (lo, hi)

    view_list = [v.strip() for v in views if v.strip()] if views else [view]
    if not view_list:
        view_list = [view]
    n = len(view_list)
    cols = 1 if n == 1 else 2
    rows = (n + cols - 1) // cols
    fig = plt.figure(figsize=(size_px / 100 * cols, size_px / 100 * 0.75 * rows), dpi=100)

    n_hi = len(highlight & {f.id for f in feats})
    extra = f" · {n_hi} resaltados" if highlight else ""
    sec_tag = f" · corte {section}" if section else ""
    for vi, v in enumerate(view_list):
        ax = fig.add_subplot(rows, cols, vi + 1, projection="3d")
        title = "" if clean else (
            f"vista {v} · {len(feats)} sólidos{extra}{sec_tag} · mm" if n == 1 else f"vista {v}"
        )
        _draw_view(
            ax, feats, v,
            shapes_override=shapes_override, highlight=highlight, fit=fit,
            show_axes=show_axes, show_bbox=show_bbox, zoom=zoom, proportional=proportional,
            labels=labels, section=section, scene_lohi=scene_lohi, title=title, colors=colors,
            frame_bbox=frame_bbox,
            # az/el solo en vista única; en multivista cada vista mantiene su preset
            azimuth=azimuth if n == 1 else None,
            elevation=elevation if n == 1 else None,
            roll=roll if n == 1 else 0.0,
        )
        if clean:  # sin ejes/grid/etiquetas (para embeber el sombreado en una lámina)
            ax.set_axis_off()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight",
                transparent=clean, pad_inches=0.0 if clean else 0.1)
    plt.close(fig)
    return buf.getvalue()


def _draw_bbox(ax, lo, hi) -> None:
    """Dibuja las 12 aristas de la caja [lo, hi] en línea discontinua."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    corners = [
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
    ]
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),  # base
        (4, 5), (5, 6), (6, 7), (7, 4),  # tope
        (0, 4), (1, 5), (2, 6), (3, 7),  # verticales
    ]
    for a, b in edges:
        xs, ys, zs = zip(corners[a], corners[b])
        ax.plot(xs, ys, zs, color="#c75f7c", linewidth=0.9, linestyle="--")
