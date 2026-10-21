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

import threading
from dataclasses import dataclass

from .malla_render import definicion_de
from .render import _clip_to_section, _shape_of
from .render_comun import (
    GRIS_FANTASMA,
    OPACIDAD_FANTASMA,
    OPACIDAD_VIDRIO,
    actor_aristas,
    actores_superficie,
    bounds_malla,
    color_pieza,
    es_vidrio,
    hex_a_rgb,
    modo_transparencia,
    polydata,
    poner_camara,
    poner_fondo,
    poner_luces,
    teselar_con_zonas,
)

_H = 0.78  # factor alto/ancho de la ventana de render (aspecto); lo comparten render y pick

# Dos-locks del render (V6.2c). RENDER_LOCK serializa los renders VTK off-screen entre sí
# (el contexto no está garantizado re-entrante); NO se toma contra el doc. La regla de oro:
# `extract_render_scene` (OCCT: teselado + recorte) corre bajo STATE_LOCK y produce datos
# PUROS; `render_snapshot_vtk` (solo VTK) corre fuera, bajo RENDER_LOCK. El teselado con caché,
# el material, las aristas, el fondo, las luces y la cámara viven en `render_comun` (los comparte
# el render vivo del video, `render_vivo`: la foto y el video se ven igual).
RENDER_LOCK = threading.Lock()


@dataclass
class _RenderItem:
    """Una pieza YA teselada + su apariencia decidida (datos PUROS, sin OCCT ni VTK)."""
    vertices: object
    triangles: object
    color: tuple
    opacity: float
    draw_edges: bool
    label_pos: object | None
    label_text: str
    pbr: tuple | None = None   # (metalness, roughness) del acabado; None = Phong genérico
    partes: list | None = None  # zonas de acabado (`render_comun.teselar_con_zonas`) o None


@dataclass
class RenderSnapshot:
    """Todo lo que `render_snapshot_vtk` necesita para pintar SIN tocar OCCT (V6.2c)."""
    items: list
    view: str
    size_px: int
    show_axes: bool
    show_bbox: bool
    azimuth: object
    elevation: object
    zoom: float
    roll: float
    pan: object
    dimension: object
    any_translucent: bool
    smins: object
    smaxs: object
    fmins: object
    fmaxs: object
    hmins: object
    hmaxs: object


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


#: Lado del triedro de `show_axes` como fracción del ANCHO de la imagen (esquina inf. izquierda).
LADO_TRIEDRO = 0.16


def _triedro(cam):
    """Renderer del triedro de ejes (X rojo, Y verde, Z azul) en la esquina inferior izquierda,
    con la ORIENTACIÓN de la cámara principal y su propia escala: dice hacia dónde va cada eje
    del mundo sin entrar al encuadre (antes los ejes salían del origen, a menudo fuera de
    cuadro; plan mcp-sin-friccion D5). Va en la capa overlay: no lo tapa la geometría."""
    import numpy as np
    import vtk

    esquina = vtk.vtkRenderer()
    esquina.SetLayer(1)
    esquina.InteractiveOff()
    esquina.SetViewport(0.0, 0.0, LADO_TRIEDRO, LADO_TRIEDRO / _H)
    esquina.PreserveColorBufferOn()
    esquina.PreserveDepthBufferOff()
    ax = vtk.vtkAxesActor()
    ax.SetTotalLength(1.0, 1.0, 1.0)
    ax.SetShaftTypeToCylinder()
    ax.SetCylinderRadius(0.04)
    ax.AxisLabelsOff()
    esquina.AddActor(ax)
    c = esquina.GetActiveCamera()
    c.ParallelProjectionOn()
    centro = np.array([0.5, 0.5, 0.5])
    c.SetFocalPoint(*centro)
    c.SetPosition(*(centro - np.array(cam.GetDirectionOfProjection()) * 10.0))
    c.SetViewUp(*cam.GetViewUp())
    esquina.ResetCamera(-0.1, 1.1, -0.1, 1.1, -0.1, 1.1)
    return esquina


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


_RENDER_DOC = """Render off-screen sombreado suave → PNG (bytes). Mismas semánticas que
    `render.render_scene_png` para vista/fit/zoom/sección/highlight/colores (sin `views`
    ni `labels`, que quedan en matplotlib). `proportional` no aplica: VTK siempre usa
    proporciones reales. `dimension={"p1","p2","label"}` dibuja una COTA (línea + etiqueta)
    en una capa overlay ENCIMA de la geometría. `edges` (def. True) superpone aristas de feature
    (creases/borde) → separa piezas adyacentes del mismo color.
    `xray` (rayos-X): lo NO resaltado se vuelve translúcido EN SU COLOR (no gris, no oculto) para
    ver una pieza interna en su contexto sin cortar; sin highlight, TODO traslúcido. El VIDRIO sale
    siempre translúcido (no gris opaco). Cuando hay translucidez se activa depth-peeling (transparencia
    correcta). `labels`=True rotula el id de cada pieza (billboard) sobre el render → lees el id en la
    imagen. `roll`/`pan` ajustan la cámara (ver `render_comun.poner_camara`). Lanza ValueError si
    vacía."""


def extract_render_scene(
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
    apariencias: dict | None = None,
    definiciones: dict | None = None,
) -> RenderSnapshot:
    """FASE OCCT del render (V6.2c, bajo STATE_LOCK): tesela (con caché) + recorta la
    sección + decide color/opacidad por pieza → un RenderSnapshot de datos PUROS. NO toca
    VTK. Lanza ValueError si la escena queda vacía (sin nada que renderizar). `apariencias` =
    {id: apariencia} de la tabla de acabados (`library/apariencia.apariencias_escena`, la del
    visor): da el color, el brillo y la opacidad de cada pieza; sin ella, `colors` + paleta y
    el Phong genérico. `definiciones` = `commands.registry.DEFINITIONS`: una instancia se
    dibuja con la malla de su definición, teselada una vez (teselado-rapido D1); sin ella,
    cada pieza se tesela sola."""
    import numpy as np

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

    items: list[_RenderItem] = []
    smins = np.array([np.inf] * 3)
    smaxs = np.array([-np.inf] * 3)
    fmins = np.array([np.inf] * 3)
    fmaxs = np.array([-np.inf] * 3)
    hmins = np.array([np.inf] * 3)
    hmaxs = np.array([-np.inf] * 3)
    any_translucent = False   # ¿hay alguna pieza traslúcida? → activar depth-peeling

    for i, feat in enumerate(feats):
        shape = entera = _shape_of(feat, shapes_override)
        if section:
            shape = _clip_to_section(shape, section, lo, hi)
            if shape is None:
                continue
        ap = (apariencias or {}).get(feat.id)
        # zonas de acabado (seta-de-emergencia F3): sólo sobre la forma entera; cortada, no calza
        zonas = (ap or {}).get("zonas") if shape is entera else None
        # la malla de la definición sólo para la forma del documento (no una pose ni un corte)
        defn, matriz = definicion_de(feat, definiciones, shape)
        vertices, triangles, partes = teselar_con_zonas(shape, zonas, defn, matriz)
        if not len(vertices) or not len(triangles):
            continue
        is_hi = feat.id in highlight
        col = hex_a_rgb(ap["color"]) if ap else color_pieza(feat.id, i, colors)
        pbr = (ap["metalness"], ap["roughness"]) if ap else None
        op_vidrio = ap["opacidad"] if ap else (OPACIDAD_VIDRIO if es_vidrio(feat) else 1.0)
        if highlight and is_hi:
            op = 1.0                              # pieza resaltada → sólida, color pleno
        elif highlight and not is_hi:
            if xray:
                op = 0.16                         # rayos-X: el contexto translúcido EN SU COLOR
            else:
                col, op, pbr, partes = GRIS_FANTASMA, OPACIDAD_FANTASMA, None, None  # fantasma
        elif op_vidrio < 1.0:
            op = op_vidrio                        # vidrio translúcido (como el viewport web)
        elif xray:
            op = 0.22                             # rayos-X sin highlight → todo translúcido
        else:
            op = 1.0                              # caso normal: opaco
        if op < 1.0:
            any_translucent = True
        draw_edges = bool(edges and op > 0.25)   # aristas nítidas (no en fantasmas muy tenues)

        bmn, bmx = bounds_malla(vertices)
        label_pos = ((bmn + bmx) / 2.0) if (labels and op > 0.25) else None
        items.append(_RenderItem(vertices, triangles, col, op, draw_edges, label_pos, feat.id,
                                 pbr, partes))
        smins = np.minimum(smins, bmn)
        smaxs = np.maximum(smaxs, bmx)
        if feat.id in fit:
            fmins = np.minimum(fmins, bmn)
            fmaxs = np.maximum(fmaxs, bmx)
        if is_hi:
            hmins = np.minimum(hmins, bmn)
            hmaxs = np.maximum(hmaxs, bmx)

    if not items:
        raise ValueError("Nada que renderizar (¿sección vacía?)")

    return RenderSnapshot(
        items=items, view=view, size_px=size_px, show_axes=show_axes, show_bbox=show_bbox,
        azimuth=azimuth, elevation=elevation, zoom=zoom, roll=roll, pan=pan,
        dimension=dimension, any_translucent=any_translucent,
        smins=smins, smaxs=smaxs, fmins=fmins, fmaxs=fmaxs, hmins=hmins, hmaxs=hmaxs,
    )


def render_snapshot_vtk(snap: RenderSnapshot) -> bytes:
    """FASE VTK del render (V6.2c, fuera de STATE_LOCK, bajo RENDER_LOCK): construye los
    actores desde los datos PUROS del snapshot y renderiza off-screen → PNG. NO toca OCCT."""
    import numpy as np
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    ren = vtk.vtkRenderer()
    poner_fondo(ren)

    label_actors = []  # rótulos de id → se pintan en la capa overlay (siempre encima)
    for item in snap.items:
        pd = polydata(item.vertices, item.triangles)
        for actor in actores_superficie(item.vertices, item.triangles, pd, item.color,
                                        item.opacity, item.pbr, item.partes):
            ren.AddActor(actor)
        if item.draw_edges:
            ren.AddActor(actor_aristas(pd))
        if item.label_pos is not None:
            label_actors.append(_label_actor(item.label_text, item.label_pos))
    poner_luces(ren)

    smins, smaxs = snap.smins, snap.smaxs
    if snap.show_bbox:
        bb_lo = snap.hmins if np.isfinite(snap.hmins).all() else smins
        bb_hi = snap.hmaxs if np.isfinite(snap.hmaxs).all() else smaxs
        ren.AddActor(_outline_actor(bb_lo, bb_hi))

    # caja de encuadre: fit_ids si se pidió (fmins finito), si no toda la escena; los ejes de
    # `show_axes` NO entran (van en su esquina, `_triedro`)
    if np.isfinite(snap.fmins).all():
        bmins, bmaxs = snap.fmins, snap.fmaxs
    else:
        bmins, bmaxs = smins, smaxs

    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.AddRenderer(ren)
    rw.SetSize(int(snap.size_px), int(snap.size_px * _H))   # aspecto ANTES de ResetCamera
    cam = poner_camara(
        ren, bmins, bmaxs, view=snap.view, azimuth=snap.azimuth, elevation=snap.elevation,
        zoom=snap.zoom, roll=snap.roll, pan=snap.pan,
    )

    # CAPA OVERLAY (comparte la cámara, se dibuja ENCIMA): cota + rótulos de id. Los billboards de
    # texto en el renderer principal crasheaban VTK off-screen; en esta capa propia funcionan y, de
    # paso, los rótulos/cota nunca quedan ocluidos por la geometría.
    if snap.dimension or label_actors:
        overlay = vtk.vtkRenderer()
        overlay.SetLayer(1)
        overlay.InteractiveOff()
        overlay.SetActiveCamera(cam)        # mismo punto de vista que la geometría
        overlay.PreserveColorBufferOn()     # no borra el color de la capa 0 (geometría)
        overlay.PreserveDepthBufferOff()    # borra depth → la cota/rótulos no se ocluyen
        if snap.dimension:
            diag = float(np.linalg.norm(smaxs - smins)) or 1000.0
            for act in _dimension_actors(
                snap.dimension["p1"], snap.dimension["p2"], snap.dimension["label"], diag
            ):
                overlay.AddActor(act)
        for la in label_actors:
            overlay.AddActor(la)
        rw.SetNumberOfLayers(2)
        rw.AddRenderer(overlay)
    if snap.show_axes:
        rw.SetNumberOfLayers(2)
        rw.AddRenderer(_triedro(cam))

    modo_transparencia(rw, ren, snap.any_translucent)   # depth peeling (xray/vidrio) o MSAA
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


def render_scene_vtk(scene: dict, view: str = "iso", **kwargs) -> bytes:
    """Wrapper de conveniencia (extract + render en una sola llamada). La API usa las dos
    mitades por separado para el patrón dos-locks (extract bajo STATE_LOCK, render bajo
    RENDER_LOCK). Aquí toma RENDER_LOCK; el caller debe sostener STATE_LOCK (OCCT).
    OJO: toma RENDER_LOCK SOSTENIENDO STATE_LOCK (orden STATE_LOCK→RENDER_LOCK, opuesto al
    dos-locks) → footgun si algo tomara STATE_LOCK bajo RENDER_LOCK; hoy no hay call sites de
    producción (solo tests/compat), por eso es seguro. Producción usa extract+render por
    separado."""
    snap = extract_render_scene(scene, view, **kwargs)
    with RENDER_LOCK:
        return render_snapshot_vtk(snap)


render_scene_vtk.__doc__ = _RENDER_DOC + "\n\n    " + (render_scene_vtk.__doc__ or "")
