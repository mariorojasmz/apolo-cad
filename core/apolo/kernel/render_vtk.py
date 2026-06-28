"""Render de la escena a PNG con VTK (off-screen), sombreado SUAVE como el viewport web.

A diferencia de `render.py` (matplotlib, que sombrea cara plana por cara plana → bandas de
brillo / "rayas" en cilindros), VTK **interpola las normales** (`vtkPolyDataNormals`, ángulo
de arista 35° = suave en lo curvo, vivo en las aristas — igual que el `toCreasedNormals` del
viewport three.js) y usa **buffer de profundidad real** → capturas limpias, sin rayas ni
transparencias falsas. Reusa las MISMAS vistas/colores/sección que `render.py` para que la
captura coincida con lo que ya espera el agente/usuario.

Es la vía "bonita" (parecida al web) para `/api/render.png` cuando se pide sombreado de una
sola vista; las combinaciones que VTK no cubre aquí (multivista `views`, etiquetas `labels`)
siguen por matplotlib. Si VTK falla (p. ej. sin contexto OpenGL), el endpoint cae a matplotlib.
"""

from __future__ import annotations

import math

from .render import PALETTE, VIEW_ANGLES, _clip_to_section, _shape_of


def _hex_to_rgb(c: str | None) -> tuple[float, float, float]:
    c = (c or "#8a8f99").lstrip("#")
    if len(c) != 6:
        return (0.55, 0.58, 0.62)
    return tuple(int(c[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _polydata(vertices, triangles):
    import vtk

    pts = vtk.vtkPoints()
    pts.SetNumberOfPoints(len(vertices))
    for k, v in enumerate(vertices):
        pts.SetPoint(k, v.X, v.Y, v.Z)
    cells = vtk.vtkCellArray()
    for t in triangles:
        cells.InsertNextCell(3)
        cells.InsertCellPoint(int(t[0]))
        cells.InsertCellPoint(int(t[1]))
        cells.InsertCellPoint(int(t[2]))
    pd = vtk.vtkPolyData()
    pd.SetPoints(pts)
    pd.SetPolys(cells)
    return pd


def _outline_actor(lo, hi):
    import vtk

    src = vtk.vtkOutlineSource()
    src.SetBounds(lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])
    m = vtk.vtkPolyDataMapper()
    m.SetInputConnection(src.GetOutputPort())
    a = vtk.vtkActor()
    a.SetMapper(m)
    a.GetProperty().SetColor(0.78, 0.37, 0.49)
    a.GetProperty().SetLineWidth(1.5)
    a.GetProperty().LightingOff()
    return a


def _axes_actor(length: float):
    import vtk

    ax = vtk.vtkAxesActor()
    ax.SetTotalLength(length, length, length)
    ax.SetShaftTypeToCylinder()
    ax.SetCylinderRadius(0.012)
    ax.AxisLabelsOff()
    return ax


def render_scene_vtk(
    scene: dict,
    view: str = "iso",
    *,
    size_px: int = 900,
    highlight_ids: list[str] | None = None,
    shapes_override: dict | None = None,
    fit_ids: list[str] | None = None,
    zoom: float = 1.0,
    section: str | None = None,
    show_axes: bool = False,
    show_bbox: bool = False,
    colors: dict | None = None,
    ignore_visibility: bool = False,
) -> bytes:
    """Render off-screen sombreado suave → PNG (bytes). Mismas semánticas que
    `render.render_scene_png` para vista/fit/zoom/sección/highlight/colores (sin `views`
    ni `labels`, que quedan en matplotlib). `proportional` no aplica: VTK siempre usa
    proporciones reales. Lanza ValueError si la escena está vacía."""
    import numpy as np
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    feats = (
        list(scene.values()) if ignore_visibility
        else [f for f in scene.values() if getattr(f, "visible", True)]
    )
    if not feats:
        raise ValueError("Escena vacía: nada que renderizar")
    highlight = set(highlight_ids or [])
    fit = set(fit_ids or [])

    # bbox de escena (solo si hay sección, para recortar)
    lo = np.array([np.inf] * 3)
    hi = np.array([-np.inf] * 3)
    if section:
        for f in feats:
            bb = _shape_of(f, shapes_override).bounding_box()
            lo = np.minimum(lo, [bb.min.X, bb.min.Y, bb.min.Z])
            hi = np.maximum(hi, [bb.max.X, bb.max.Y, bb.max.Z])

    ren = vtk.vtkRenderer()
    ren.SetBackground(0.965, 0.97, 0.985)   # fondo claro tipo "papel" (degradado sutil)
    ren.SetBackground2(0.86, 0.89, 0.94)
    ren.GradientBackgroundOn()

    smins = np.array([np.inf] * 3)
    smaxs = np.array([-np.inf] * 3)
    fmins = np.array([np.inf] * 3)
    fmaxs = np.array([-np.inf] * 3)
    hmins = np.array([np.inf] * 3)
    hmaxs = np.array([-np.inf] * 3)

    for i, feat in enumerate(feats):
        shape = _shape_of(feat, shapes_override)
        if section:
            shape = _clip_to_section(shape, section, lo, hi)
            if shape is None:
                continue
        vertices, triangles = shape.tessellate(0.5, 0.25)
        if not len(vertices) or not len(triangles):
            continue
        nrm = vtk.vtkPolyDataNormals()
        nrm.SetInputData(_polydata(vertices, triangles))
        nrm.SetFeatureAngle(35.0)   # = toCreasedNormals del viewport web
        nrm.SplittingOn()
        nrm.ConsistencyOn()
        nrm.ComputePointNormalsOn()
        nrm.Update()

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(nrm.GetOutputPort())
        mapper.ScalarVisibilityOff()
        actor = vtk.vtkActor()
        actor.SetMapper(mapper)
        prop = actor.GetProperty()
        is_hi = feat.id in highlight
        if not highlight or is_hi:
            prop.SetColor(*_hex_to_rgb((colors or {}).get(feat.id) or PALETTE[i % len(PALETTE)]))
            prop.SetOpacity(1.0)
        else:  # hay resaltados y este no → atenuado (gris translúcido)
            prop.SetColor(0.62, 0.66, 0.70)
            prop.SetOpacity(0.18)
        prop.SetInterpolationToPhong()   # sombreado SUAVE (normales interpoladas)
        prop.SetAmbient(0.34)
        prop.SetDiffuse(0.70)
        prop.SetSpecular(0.16)
        prop.SetSpecularPower(22)
        ren.AddActor(actor)

        b = actor.GetBounds()  # (xmin,xmax,ymin,ymax,zmin,zmax)
        bmn = np.array([b[0], b[2], b[4]])
        bmx = np.array([b[1], b[3], b[5]])
        smins = np.minimum(smins, bmn)
        smaxs = np.maximum(smaxs, bmx)
        if feat.id in fit:
            fmins = np.minimum(fmins, bmn)
            fmaxs = np.maximum(fmaxs, bmx)
        if is_hi:
            hmins = np.minimum(hmins, bmn)
            hmaxs = np.maximum(hmaxs, bmx)

    if ren.GetActors().GetNumberOfItems() == 0:
        raise ValueError("Nada que renderizar (¿sección vacía?)")

    # iluminación agradable tipo estudio (key + fill + back), como el IBL del web
    lk = vtk.vtkLightKit()
    lk.SetKeyLightIntensity(0.9)
    lk.AddLightsToRenderer(ren)

    if show_bbox:
        bb_lo = hmins if np.isfinite(hmins).all() else smins
        bb_hi = hmaxs if np.isfinite(hmaxs).all() else smaxs
        ren.AddActor(_outline_actor(bb_lo, bb_hi))
    if show_axes:
        ren.AddActor(_axes_actor(float(np.max(smaxs - smins)) * 0.3))

    # caja de encuadre: fit_ids si se pidió, si no toda la escena
    if fit and np.isfinite(fmins).all():
        bmins, bmaxs = fmins, fmaxs
    else:
        bmins, bmaxs = smins, smaxs
    center = (bmins + bmaxs) / 2.0

    cam = ren.GetActiveCamera()
    cam.ParallelProjectionOn()   # ortográfico (como matplotlib; sin distorsión de perspectiva)
    elev, azim = VIEW_ANGLES.get(view, VIEW_ANGLES["iso"])
    e, a = math.radians(elev), math.radians(azim)
    d = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
    up = (0, 1, 0) if abs(d[2]) > 0.98 else (0, 0, 1)   # planta mira casi recto en Z
    dist = float(np.linalg.norm(bmaxs - bmins)) or 1000.0
    cam.SetFocalPoint(*center)
    cam.SetPosition(*(center + d * dist * 2.0))
    cam.SetViewUp(*up)
    ren.ResetCamera(bmins[0], bmaxs[0], bmins[1], bmaxs[1], bmins[2], bmaxs[2])
    cam.Zoom(max(zoom, 1e-6))
    ren.ResetCameraClippingRange()

    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.AddRenderer(ren)
    rw.SetMultiSamples(8)   # antialiasing
    rw.SetSize(int(size_px), int(size_px * 0.78))
    rw.Render()

    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(rw)
    w2i.ReadFrontBufferOff()
    w2i.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetWriteToMemory(1)
    writer.SetInputConnection(w2i.GetOutputPort())
    writer.Write()
    return vtk_to_numpy(writer.GetResult()).tobytes()
