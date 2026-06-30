"""Píxel→3D: "señalar" un punto del render y obtener la pieza/cara/coordenada más cercana.

La visión deja de ser solo SALIDA: el agente mira un render, indica un punto (u,v)
normalizado de la imagen, y aquí resolvemos qué geometría hay ahí. No es desproyección
con profundidad (ambigua) sino *snap a geometría*: proyectamos los puntos candidatos
(centroide de cada feature y centro de cada cara) con la MISMA cámara del render
(`apply_camera`) y devolvemos el más cercano al punto pedido. Determinista y suficiente
para "elegir una cara/pieza apuntando". Read-only.
"""

from __future__ import annotations


def _resolved_shapes(scene: dict, shapes_override, isolate, section):
    """[(fid, feat, shape)] de las piezas a considerar, COHERENTE con el render:
    `isolate` (lista de ids) restringe a esas piezas (forzando mostrarlas, como el render aislado);
    si no, solo las visibles. `section` ∈ {x,y,z} recorta cada shape con la misma semicaja que el
    render (centro = bbox de lo considerado) → mismo subconjunto/encuadre que la foto. Salta lo
    recortado a nada."""
    if isolate:
        items = [(fid, scene[fid]) for fid in isolate if fid in scene]
        if not items:
            raise ValueError("isolate: ningún id existe en la escena")
    else:
        items = [(fid, f) for fid, f in scene.items() if getattr(f, "visible", True)]

    def _shape(fid, f):
        return shapes_override.get(fid, f.shape) if shapes_override else f.shape

    if not section:
        return [(fid, f, _shape(fid, f)) for fid, f in items]

    import numpy as np

    from apolo.kernel.render import _clip_to_section

    lo = np.array([np.inf] * 3)
    hi = np.array([-np.inf] * 3)
    raw = []
    for fid, f in items:
        s = _shape(fid, f)
        bb = s.bounding_box()
        lo = np.minimum(lo, [bb.min.X, bb.min.Y, bb.min.Z])
        hi = np.maximum(hi, [bb.max.X, bb.max.Y, bb.max.Z])
        raw.append((fid, f, s))
    out = []
    for fid, f, s in raw:
        cs = _clip_to_section(s, section, lo, hi)
        if cs is not None:
            out.append((fid, f, cs))
    return out


def _candidates(items):
    """Puntos 3D candidatos: centroide (AABB) de cada feature + centro de cada cara.
    `items` = lista (fid, feat, shape) YA resuelta (override/isolate/sección)."""
    from apolo.kernel.topology import feature_topology

    cands: list[tuple] = []  # (feature_id, face_idx|None, (x,y,z), kind)
    for fid, _f, shape in items:
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


def _nearest(cands, proj, u, v):
    """De los candidatos, el más cercano al punto (u,v) tras proyectarlos con `proj`."""
    best = None
    for fid, fidx, p, kind in cands:
        nx, ny = proj(p)
        d = (nx - u) ** 2 + (ny - v) ** 2
        if best is None or d < best[0]:
            best = (d, fid, fidx, p, kind)
    return best


def _vtk_projector(bmins, bmaxs, view, azimuth, elevation, zoom, roll=0.0, pan=None):
    """Closure punto3D→(u,v) con la matriz EXACTA de la cámara VTK (mismo encuadre que el
    render `render_scene_vtk`: ortográfica, ResetCamera al bbox, zoom, aspecto de la ventana).
    Pura matriz: NO llama Render() → sin contexto OpenGL. Devuelve None si VTK no está disponible
    (entonces el pick cae a matplotlib, que coincide con el render-fallback de matplotlib)."""
    try:
        import numpy as np
        import vtk

        from apolo.kernel.render_vtk import _H, _setup_camera

        ren = vtk.vtkRenderer()
        rw = vtk.vtkRenderWindow()
        rw.SetOffScreenRendering(1)
        rw.AddRenderer(ren)
        size = 900
        h = int(size * _H)
        rw.SetSize(size, h)   # aspecto ANTES de ResetCamera (igual que el render)
        _setup_camera(
            ren, np.asarray(bmins, float), np.asarray(bmaxs, float),
            view=view, azimuth=azimuth, elevation=elevation, zoom=zoom, roll=roll, pan=pan,
        )
        m = ren.GetActiveCamera().GetCompositeProjectionTransformMatrix(size / float(h), -1, 1)

        def proj(p):
            c = m.MultiplyPoint((float(p[0]), float(p[1]), float(p[2]), 1.0))
            w = c[3] if c[3] != 0 else 1.0
            return (c[0] / w + 1.0) / 2.0, (1.0 - c[1] / w) / 2.0  # NDC→(u,v) origen arriba-izq

        return proj
    except Exception:  # noqa: BLE001 — sin VTK/OpenGL → fallback matplotlib
        return None


def pick_point(
    scene: dict,
    view: str,
    u: float,
    v: float,
    *,
    shapes_override: dict | None = None,
    fit_ids: list[str] | None = None,
    zoom: float = 1.0,
    proportional: bool = True,
    azimuth: float | None = None,
    elevation: float | None = None,
    isolate: list[str] | None = None,
    section: str | None = None,
    roll: float = 0.0,
    pan: list | None = None,
) -> dict:
    """Devuelve la feature/cara cuyo centro PROYECTADO queda más cerca del punto (u,v)
    NORMALIZADO de la imagen (0,0 = arriba-izquierda; 1,1 = abajo-derecha). Usa la cámara EXACTA
    del render VTK (matriz de proyección ortográfica, mismo encuadre) — incluido el ÁNGULO LIBRE
    `azimuth`/`elevation` — para que el píxel coincida sub-píxel con lo que se ve. Si VTK no está
    disponible, cae a matplotlib (orto, que coincide con el render-fallback de matplotlib).
    Para COINCIDIR con un render aislado o seccionado, pasa los MISMOS `isolate`/`section` (y
    `fit_ids`/`zoom`/`azimuth`/`elevation`) que usaste en `render_view`: el pick solo considera ese
    subconjunto y proyecta con el mismo encuadre."""
    import numpy as np

    items = _resolved_shapes(scene, shapes_override, isolate, section)
    if not items:
        raise ValueError("Nada que pickear (¿escena vacía o sección vacía?)")
    cands = _candidates(items)
    if not cands:
        raise ValueError("Nada que pickear: sin candidatos")

    # caja envolvente (barata, sin teselar): todos los items o solo los fit_ids
    fit = set(fit_ids or [])
    mins = np.array([np.inf] * 3)
    maxs = np.array([-np.inf] * 3)
    fmins = np.array([np.inf] * 3)
    fmaxs = np.array([-np.inf] * 3)
    for fid, _f, shape in items:
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

    # proyección EXACTA con la matriz de cámara VTK; si no hay VTK, fallback matplotlib (orto)
    proj = _vtk_projector(bmins, bmaxs, view, azimuth, elevation, zoom, roll, pan)
    if proj is not None:
        best = _nearest(cands, proj, u, v)
    else:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import proj3d

        from apolo.kernel.render import apply_camera

        fig = plt.figure(figsize=(8.8, 8.8 * 0.78), dpi=100)  # mismo aspecto que la ventana VTK
        ax = fig.add_subplot(111, projection="3d")
        ax.set_proj_type("ortho")
        apply_camera(
            ax, bmins, bmaxs, zoom=zoom, proportional=proportional, view=view,
            azimuth=azimuth, elevation=elevation, roll=roll,
        )
        fig.canvas.draw()
        proj_m = ax.get_proj()
        width, height = fig.canvas.get_width_height()

        def _mproj(p):
            xs, ys, _ = proj3d.proj_transform(p[0], p[1], p[2], proj_m)
            px, py = ax.transData.transform((xs, ys))
            return px / width, 1.0 - py / height

        best = _nearest(cands, _mproj, u, v)
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
