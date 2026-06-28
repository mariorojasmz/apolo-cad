"""Píxel→3D: "señalar" un punto del render y obtener la pieza/cara/coordenada más cercana.

La visión deja de ser solo SALIDA: el agente mira un render, indica un punto (u,v)
normalizado de la imagen, y aquí resolvemos qué geometría hay ahí. No es desproyección
con profundidad (ambigua) sino *snap a geometría*: proyectamos los puntos candidatos
(centroide de cada feature y centro de cada cara) con la MISMA cámara del render
(`apply_camera`) y devolvemos el más cercano al punto pedido. Determinista y suficiente
para "elegir una cara/pieza apuntando". Read-only.
"""

from __future__ import annotations


def _candidates(scene: dict, shapes_override):
    """Puntos 3D candidatos: centroide (AABB) de cada feature + centro de cada cara."""
    from apolo.kernel.topology import feature_topology

    cands: list[tuple] = []  # (feature_id, face_idx|None, (x,y,z), kind)
    for fid, f in scene.items():
        if not getattr(f, "visible", True):
            continue
        shape = shapes_override.get(fid, f.shape) if shapes_override else f.shape
        bb = shape.bounding_box()
        c = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
        cands.append((fid, None, c, "feature"))
        try:
            for face in feature_topology(shape)["faces"]:
                ctr = face.get("center")
                if ctr:
                    cands.append((fid, face["idx"], (ctr[0], ctr[1], ctr[2]), "face"))
        except Exception:
            pass
    return cands


def pick_point(
    scene: dict,
    view: str,
    u: float,
    v: float,
    *,
    shapes_override: dict | None = None,
    fit_ids: list[str] | None = None,
    zoom: float = 1.0,
    proportional: bool = False,
) -> dict:
    """Devuelve la feature/cara cuyo centro PROYECTADO queda más cerca del punto (u,v)
    NORMALIZADO de la imagen (0,0 = arriba-izquierda; 1,1 = abajo-derecha). Reproduce la
    cámara del render (misma vista/encuadre) para que coincida con lo que se ve."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from mpl_toolkits.mplot3d import proj3d

    from apolo.kernel.render import apply_camera

    cands = _candidates(scene, shapes_override)
    if not cands:
        raise ValueError("Escena vacía: nada que pickear")

    # caja envolvente (barata, sin teselar): todos o solo los fit_ids
    fit = set(fit_ids or [])
    mins = np.array([np.inf] * 3)
    maxs = np.array([-np.inf] * 3)
    fmins = np.array([np.inf] * 3)
    fmaxs = np.array([-np.inf] * 3)
    for fid, f in scene.items():
        if not getattr(f, "visible", True):
            continue
        shape = shapes_override.get(fid, f.shape) if shapes_override else f.shape
        bb = shape.bounding_box()
        lo = np.array([bb.min.X, bb.min.Y, bb.min.Z])
        hi = np.array([bb.max.X, bb.max.Y, bb.max.Z])
        mins = np.minimum(mins, lo)
        maxs = np.maximum(maxs, hi)
        if fid in fit:
            fmins = np.minimum(fmins, lo)
            fmaxs = np.maximum(fmaxs, hi)
    if fit and np.isfinite(fmins).all():
        bmins, bmaxs = fmins, fmaxs
    else:
        bmins, bmaxs = mins, maxs

    fig = plt.figure(figsize=(8.8, 6.6), dpi=100)
    ax = fig.add_subplot(111, projection="3d")
    apply_camera(ax, bmins, bmaxs, zoom=zoom, proportional=proportional, view=view)
    fig.canvas.draw()  # asegura que get_proj()/transData estén actualizados
    proj = ax.get_proj()
    width, height = fig.canvas.get_width_height()

    best = None
    for fid, fidx, p, kind in cands:
        xs, ys, _ = proj3d.proj_transform(p[0], p[1], p[2], proj)
        px, py = ax.transData.transform((xs, ys))
        nx, ny = px / width, 1.0 - py / height  # normalizado, origen arriba-izquierda
        d = (nx - u) ** 2 + (ny - v) ** 2
        if best is None or d < best[0]:
            best = (d, fid, fidx, p, kind)
    plt.close(fig)

    d, fid, fidx, p, kind = best
    res: dict = {
        "feature_id": fid,
        "nombre": scene[fid].name,
        "tipo": kind,
        "world_point": [round(p[0], 4), round(p[1], 4), round(p[2], 4)],
        "dist_norm": round(float(d) ** 0.5, 4),
    }
    if fidx is not None:
        res["face_idx"] = fidx
    return res
