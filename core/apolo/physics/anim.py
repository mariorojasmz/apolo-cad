"""Render del drop-test a GIF animado (matplotlib + Pillow).

Reutiliza el dibujo de escena de `kernel/render.py` (teselado matplotlib): tesela la
escena ESTÁTICA una sola vez y, por fotograma, pinta las cajas de producto en la pose
que devolvió `sim.drop_test`. Es entrega visual (como `render_view`), no geometría.
"""

from __future__ import annotations

import io

from ..kernel.render import PALETTE, VIEW_ANGLES

# vértices unitarios del cubo por bits (x=bit0, y=bit1, z=bit2) y sus 6 caras (quads)
_CUBE_SIGNS = [((1 if i & 1 else -1), (1 if i & 2 else -1), (1 if i & 4 else -1)) for i in range(8)]
_CUBE_FACES = [(0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)]


def _box_faces(size, pose):
    """6 caras (en mm) de una caja `size`=(w,d,h) transformada por la pose 4×4 (filas)."""
    w, d, h = size
    corners = []
    for sx, sy, sz in _CUBE_SIGNS:
        px, py, pz = sx * w / 2, sy * d / 2, sz * h / 2
        corners.append([
            pose[0][0] * px + pose[0][1] * py + pose[0][2] * pz + pose[0][3],
            pose[1][0] * px + pose[1][1] * py + pose[1][2] * pz + pose[1][3],
            pose[2][0] * px + pose[2][1] * py + pose[2][2] * pz + pose[2][3],
        ])
    return [[corners[idx] for idx in face] for face in _CUBE_FACES]


def render_drop_gif(scene, products, frames, view: str = "iso", size_px: int = 720, fps: int = 20) -> bytes:
    """Ensambla un GIF de la caída. `products` y `frames` son la salida de drop_test."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Pillow no está instalado: `pip install pillow` para el GIF") from exc

    # 1) teselar la escena estática una sola vez (color atenuado, es el fondo)
    static_polys = []
    mins = np.array([np.inf] * 3)
    maxs = np.array([-np.inf] * 3)
    for feat in scene.values():
        if not getattr(feat, "visible", True):
            continue
        try:
            vertices, triangles = feat.shape.tessellate(1.5, 0.7)
        except Exception:  # noqa: BLE001
            continue
        pts = np.array([[v.X, v.Y, v.Z] for v in vertices])
        if len(pts) == 0:
            continue
        mins = np.minimum(mins, pts.min(axis=0))
        maxs = np.maximum(maxs, pts.max(axis=0))
        static_polys.append(pts[np.array(triangles)])

    size_by_name = {p["name"]: (p["w"], p["d"], p["h"]) for p in products}

    # 2) límites: escena + todas las poses de producto (caen desde arriba)
    for fr in frames:
        for name, pose in fr["poses"].items():
            w, d, h = size_by_name[name]
            r = max(w, d, h)
            c = np.array([pose[0][3], pose[1][3], pose[2][3]])
            mins = np.minimum(mins, c - r)
            maxs = np.maximum(maxs, c + r)
    if not np.all(np.isfinite(mins)):
        raise ValueError("Nada que animar: escena y productos vacíos")
    center = (mins + maxs) / 2
    half = float(max(maxs - mins)) / 2 * 1.05
    elev, azim = VIEW_ANGLES.get(view, VIEW_ANGLES["iso"])

    pngs = []
    for fr in frames:
        fig = plt.figure(figsize=(size_px / 100, size_px / 100 * 0.75), dpi=100)
        ax = fig.add_subplot(111, projection="3d")
        for polys in static_polys:
            ax.add_collection3d(
                Poly3DCollection(polys, facecolors="#b9c2cf", edgecolors="#9aa6b5",
                                 linewidths=0.05, alpha=0.55, shade=True)
            )
        for i, (name, pose) in enumerate(fr["poses"].items()):
            faces = _box_faces(size_by_name[name], pose)
            color = PALETTE[i % len(PALETTE)]
            ax.add_collection3d(
                Poly3DCollection(faces, facecolors=color, edgecolors="#1b2330",
                                 linewidths=0.6, alpha=0.95, shade=True)
            )
        ax.set_xlim(center[0] - half, center[0] + half)
        ax.set_ylim(center[1] - half, center[1] + half)
        ax.set_zlim(max(0.0, center[2] - half), center[2] + half)
        ax.set_box_aspect((1, 1, 1))
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()
        ax.set_title(f"drop-test · t={fr['t']:.2f}s · {len(fr['poses'])} producto(s)")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        pngs.append(Image.open(buf).convert("RGB"))

    out = io.BytesIO()
    pngs[0].save(out, format="GIF", save_all=True, append_images=pngs[1:],
                 duration=max(1, int(1000 / max(1, fps))), loop=0, optimize=True)
    return out.getvalue()
