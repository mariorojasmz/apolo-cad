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
import re

from .render import PALETTE, _clip_to_section, _shape_of, resolve_angles

_H = 0.78  # factor alto/ancho de la ventana de render (aspecto); lo comparten render y pick

_GLASS_RE = re.compile(r"vidrio|cristal|glass|templado", re.I)


def _is_glass(feat) -> bool:
    """¿La pieza es vidrio? (material override o nombre — espejo del `isGlass` del viewport web)."""
    if _GLASS_RE.search(getattr(feat, "material", None) or ""):
        return True
    return bool(_GLASS_RE.search(getattr(feat, "name", "") or ""))


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


def _dimension_actors(p1, p2, label: str, scale: float):
    """Actores de una COTA: línea p1↔p2 + marcas en los extremos + etiqueta (billboard, siempre
    de cara a la cámara) con el valor. `scale` (diagonal de la escena) dimensiona las marcas."""
    import vtk

    dark = (0.05, 0.05, 0.08)
    actors = []
    line = vtk.vtkLineSource()
    line.SetPoint1(*p1)
    line.SetPoint2(*p2)
    lm = vtk.vtkPolyDataMapper()
    lm.SetInputConnection(line.GetOutputPort())
    la = vtk.vtkActor()
    la.SetMapper(lm)
    la.GetProperty().SetColor(*dark)
    la.GetProperty().SetLineWidth(2.5)
    la.GetProperty().LightingOff()
    actors.append(la)

    r = max(scale * 0.006, 1e-6)
    for p in (p1, p2):
        s = vtk.vtkSphereSource()
        s.SetCenter(*p)
        s.SetRadius(r)
        s.SetThetaResolution(14)
        s.SetPhiResolution(14)
        sm = vtk.vtkPolyDataMapper()
        sm.SetInputConnection(s.GetOutputPort())
        sa = vtk.vtkActor()
        sa.SetMapper(sm)
        sa.GetProperty().SetColor(*dark)
        sa.GetProperty().LightingOff()
        actors.append(sa)

    mid = [(p1[i] + p2[i]) / 2.0 for i in range(3)]
    txt = vtk.vtkBillboardTextActor3D()
    txt.SetInput(label)
    txt.SetPosition(*mid)
    tp = txt.GetTextProperty()
    tp.SetFontSize(20)
    tp.SetBold(True)
    tp.SetColor(*dark)
    tp.SetJustificationToCentered()
    tp.SetVerticalJustificationToCentered()
    tp.SetBackgroundColor(1.0, 1.0, 1.0)
    tp.SetBackgroundOpacity(0.78)
    tp.SetFrame(True)
    tp.SetFrameColor(*dark)
    actors.append(txt)
    return actors


def _label_actor(text: str, pos):
    """Etiqueta de id (billboard, siempre de cara a la cámara) anclada en el centroide de una pieza,
    para LEER el id directamente sobre el render (cierra ver→identificar→editar)."""
    import vtk

    txt = vtk.vtkBillboardTextActor3D()
    txt.SetInput(text)
    txt.SetPosition(float(pos[0]), float(pos[1]), float(pos[2]))
    tp = txt.GetTextProperty()
    tp.SetFontSize(15)
    tp.SetBold(True)
    tp.SetColor(0.05, 0.05, 0.08)
    tp.SetJustificationToCentered()
    tp.SetVerticalJustificationToCentered()
    tp.SetBackgroundColor(1.0, 1.0, 0.86)   # post-it claro para contraste sobre cualquier pieza
    tp.SetBackgroundOpacity(0.82)
    tp.SetFrame(True)
    tp.SetFrameColor(0.55, 0.55, 0.2)
    return txt


def _edges_actor(vertices, triangles):
    """Actor de aristas de FEATURE (creases) + borde, sobre la malla → separa visualmente
    piezas adyacentes del mismo color (equivalente al toCreasedNormals del viewport web)."""
    import vtk

    fe = vtk.vtkFeatureEdges()
    fe.SetInputData(_polydata(vertices, triangles))
    fe.BoundaryEdgesOn()
    fe.FeatureEdgesOn()
    fe.SetFeatureAngle(35.0)   # mismo ángulo que las normales suaves
    fe.ManifoldEdgesOff()
    fe.NonManifoldEdgesOff()
    m = vtk.vtkPolyDataMapper()
    m.SetInputConnection(fe.GetOutputPort())
    m.SetResolveCoincidentTopologyToPolygonOffset()  # evita z-fighting con la superficie
    a = vtk.vtkActor()
    a.SetMapper(m)
    a.GetProperty().SetColor(0.12, 0.12, 0.15)
    a.GetProperty().SetLineWidth(1.0)
    a.GetProperty().LightingOff()
    return a


def _setup_camera(ren, bmins, bmaxs, *, view, azimuth, elevation, zoom, roll=0.0, pan=None):
    """Cámara ortográfica ÚNICA (la comparten el render y el pick): dirección desde
    `resolve_angles`, encuadre `ResetCamera` al bbox dado, zoom. Devuelve la vtkCamera.
    `roll` (grados) gira la cámara sobre su eje de visión (3.er GDL rotacional, complementa
    azimuth/elevation que dan la dirección). `pan` = [px, py] desplaza el encuadre en el PLANO de
    vista (fracción de la semialtura: +px → derecha, +py → arriba) para enfocar un detalle fuera del
    centro del bbox sin aislar — en proyección ortográfica esto ES la 'posición de cámara' lateral
    (la distancia del ojo es irrelevante). Importante: el aspecto lo toma `ResetCamera` del tamaño de
    la ventana → fija el size ANTES."""
    import numpy as np

    bmins = np.asarray(bmins, dtype=float)
    bmaxs = np.asarray(bmaxs, dtype=float)
    center = (bmins + bmaxs) / 2.0
    cam = ren.GetActiveCamera()
    cam.ParallelProjectionOn()
    elev, azim = resolve_angles(view, azimuth, elevation)
    e, a = math.radians(elev), math.radians(azim)
    d = np.array([math.cos(e) * math.cos(a), math.cos(e) * math.sin(a), math.sin(e)])
    up = (0, 1, 0) if abs(d[2]) > 0.98 else (0, 0, 1)
    dist = float(np.linalg.norm(bmaxs - bmins)) or 1000.0
    cam.SetFocalPoint(*center)
    cam.SetPosition(*(center + d * dist * 2.0))
    cam.SetViewUp(*up)
    ren.ResetCamera(bmins[0], bmaxs[0], bmins[1], bmaxs[1], bmins[2], bmaxs[2])
    cam.Zoom(max(zoom, 1e-6))
    if roll:
        cam.Roll(float(roll))   # gira sobre el eje de visión (rota el view-up)
    if pan:
        pscale = cam.GetParallelScale()  # semialtura del viewport en unidades-mundo (orto)
        dop = np.array(cam.GetDirectionOfProjection())
        vup = np.array(cam.GetViewUp())
        right = np.cross(dop, vup)
        n = np.linalg.norm(right)
        right = right / n if n else right
        off = right * (float(pan[0]) * pscale) + vup * (float(pan[1]) * pscale)
        cam.SetFocalPoint(*(np.array(cam.GetFocalPoint()) + off))
        cam.SetPosition(*(np.array(cam.GetPosition()) + off))
    ren.ResetCameraClippingRange()
    return cam


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
    azimuth: float | None = None,
    elevation: float | None = None,
    dimension: dict | None = None,
    edges: bool = True,
    xray: bool = False,
    labels: bool = False,
    roll: float = 0.0,
    pan: list | None = None,
) -> bytes:
    """Render off-screen sombreado suave → PNG (bytes). Mismas semánticas que
    `render.render_scene_png` para vista/fit/zoom/sección/highlight/colores (sin `views`
    ni `labels`, que quedan en matplotlib). `proportional` no aplica: VTK siempre usa
    proporciones reales. `dimension={"p1","p2","label"}` dibuja una COTA (línea + etiqueta)
    en una capa overlay ENCIMA de la geometría. `edges` (def. True) superpone aristas de feature
    (creases/borde) → separa piezas adyacentes del mismo color.
    `xray` (rayos-X): lo NO resaltado se vuelve translúcido EN SU COLOR (no gris, no oculto) para
    ver una pieza interna en su contexto sin cortar; sin highlight, TODO traslúcido. El VIDRIO sale
    siempre translúcido (no gris opaco). Cuando hay translucidez se activa depth-peeling (transparencia
    correcta). `labels`=True rotula el id de cada pieza (billboard) sobre el render → lees el id en la
    imagen. `roll`/`pan` ajustan la cámara (ver `_setup_camera`). Lanza ValueError si vacía."""
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
    any_translucent = False   # ¿hay alguna pieza traslúcida? → activar depth-peeling
    label_actors = []         # rótulos de id → se pintan en la capa overlay (siempre encima)

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
        col = _hex_to_rgb((colors or {}).get(feat.id) or PALETTE[i % len(PALETTE)])
        if highlight and is_hi:
            op = 1.0                              # pieza resaltada → sólida, color pleno
        elif highlight and not is_hi:
            if xray:
                op = 0.16                         # rayos-X: el contexto translúcido EN SU COLOR
            else:
                col, op = (0.62, 0.66, 0.70), 0.18  # fantasma gris (de-énfasis)
        elif _is_glass(feat):
            op = 0.34                             # vidrio translúcido (como el viewport web)
        elif xray:
            op = 0.22                             # rayos-X sin highlight → todo translúcido
        else:
            op = 1.0                              # caso normal: opaco
        prop.SetColor(*col)
        prop.SetOpacity(op)
        if op < 1.0:
            any_translucent = True
        prop.SetInterpolationToPhong()   # sombreado SUAVE (normales interpoladas)
        prop.SetAmbient(0.34)
        prop.SetDiffuse(0.70)
        prop.SetSpecular(0.16)
        prop.SetSpecularPower(22)
        ren.AddActor(actor)
        if edges and op > 0.25:  # aristas nítidas (no en los fantasmas muy tenues)
            ren.AddActor(_edges_actor(vertices, triangles))

        b = actor.GetBounds()  # (xmin,xmax,ymin,ymax,zmin,zmax)
        bmn = np.array([b[0], b[2], b[4]])
        bmx = np.array([b[1], b[3], b[5]])
        if labels and op > 0.25:  # rotula el id (no en los fantasmas muy tenues)
            label_actors.append(_label_actor(feat.id, (bmn + bmx) / 2.0))
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

    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.AddRenderer(ren)
    rw.SetSize(int(size_px), int(size_px * _H))   # aspecto ANTES de ResetCamera
    cam = _setup_camera(
        ren, bmins, bmaxs, view=view, azimuth=azimuth, elevation=elevation, zoom=zoom,
        roll=roll, pan=pan,
    )

    # CAPA OVERLAY (comparte la cámara, se dibuja ENCIMA): cota + rótulos de id. Los billboards de
    # texto en el renderer principal crasheaban VTK off-screen; en esta capa propia funcionan y, de
    # paso, los rótulos/cota nunca quedan ocluidos por la geometría.
    if dimension or label_actors:
        overlay = vtk.vtkRenderer()
        overlay.SetLayer(1)
        overlay.InteractiveOff()
        overlay.SetActiveCamera(cam)        # mismo punto de vista que la geometría
        overlay.PreserveColorBufferOn()     # no borra el color de la capa 0 (geometría)
        overlay.PreserveDepthBufferOff()    # borra depth → la cota/rótulos no se ocluyen
        if dimension:
            diag = float(np.linalg.norm(smaxs - smins)) or 1000.0
            for act in _dimension_actors(dimension["p1"], dimension["p2"], dimension["label"], diag):
                overlay.AddActor(act)
        for la in label_actors:
            overlay.AddActor(la)
        rw.SetNumberOfLayers(2)
        rw.AddRenderer(overlay)

    if any_translucent:
        # transparencia CORRECTA (orden-independiente): depth peeling. Exige planos alfa y SIN MSAA.
        rw.SetAlphaBitPlanes(1)
        rw.SetMultiSamples(0)
        ren.SetUseDepthPeeling(1)
        ren.SetMaximumNumberOfPeels(8)
        ren.SetOcclusionRatio(0.0)
        ren.SetUseFXAA(True)    # AA de post-proceso: recupera bordes nítidos sin MSAA (xray/vidrio)
    else:
        rw.SetMultiSamples(8)   # antialiasing (sin translucidez no hace falta peeling)
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
