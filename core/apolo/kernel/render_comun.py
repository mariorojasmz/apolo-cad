"""Lo que comparten los dos renderers VTK para que se vean IGUAL (plan publicacion-tienda, F2).

`render_vtk` pinta una foto por llamada (la del `render_view`); `render_vivo` mantiene una ventana
viva durante todo un video. Los dos sacan de aquí el teselado (con caché), la apariencia de cada
pieza (paleta, vidrio, material Phong, aristas de feature), el fondo degradado, las luces de
estudio, la cámara y el modo de transparencia. Un cambio de aspecto se hace AQUÍ y vale para los
dos; si se hiciera en uno, la foto y el video dejarían de coincidir.

Todo es VTK sobre datos puros salvo `teselar`, que es OCCT: en la API corre bajo `STATE_LOCK`
(regla dos-locks del CLAUDE.md raíz). Este módulo no toma ningún lock.
"""

from __future__ import annotations

import math
import re

from .render import PALETTE, resolve_angles

# Caché de teselado a resolución de render (0.5/0.25) por IDENTIDAD del shape, con ref
# fuerte (como _SHAPE_CACHE del payload) → un segundo render de la MISMA escena no re-tesela
# (antes se re-teselaba TODO en cada foto). En la API se llena bajo STATE_LOCK. Shapes de
# sección/pose son objetos nuevos → miss (aceptable). `.tessellate` muta el shape guardando la
# malla: por eso en la API SOLO se llama bajo STATE_LOCK (sin carrera con otro hilo).
_RENDER_MESH_CACHE: dict = {}
_RENDER_MESH_CAP = 2048

# Material de las piezas (Phong): el mismo en la foto y en el video.
AMBIENTE = 0.34
DIFUSO = 0.70
ESPECULAR = 0.16
POTENCIA_ESPECULAR = 22
OPACIDAD_VIDRIO = 0.34       # vidrio translúcido (como el viewport web)
ANGULO_ARISTA = 35.0         # = toCreasedNormals del viewport web: suave en lo curvo, vivo en aristas

# Fondo claro tipo "papel" con un degradado sutil. Convención VTK: `SetBackground` es el color
# de ABAJO y `SetBackground2` el de ARRIBA.
FONDO_ABAJO = (0.965, 0.97, 0.985)
FONDO_ARRIBA = (0.86, 0.89, 0.94)

_GLASS_RE = re.compile(r"vidrio|cristal|glass|templado", re.I)


def teselar(shape):
    """(vertices, triangulos) del shape a resolución de render, con caché por `id(shape)` que
    guarda la REFERENCIA y verifica `is` (un id reciclado no recibe la malla ajena)."""
    key = id(shape)
    hit = _RENDER_MESH_CACHE.get(key)
    if hit is None or hit[0] is not shape:
        if len(_RENDER_MESH_CACHE) > _RENDER_MESH_CAP:
            _RENDER_MESH_CACHE.clear()
        vertices, triangles = shape.tessellate(0.5, 0.25)
        hit = (shape, vertices, triangles)
        _RENDER_MESH_CACHE[key] = hit
    return hit[1], hit[2]


def es_vidrio(feat) -> bool:
    """¿La pieza es vidrio? (material override o nombre — espejo del `isGlass` del viewport web)."""
    if _GLASS_RE.search(getattr(feat, "material", None) or ""):
        return True
    return bool(_GLASS_RE.search(getattr(feat, "name", "") or ""))


def hex_a_rgb(c: str | None) -> tuple[float, float, float]:
    c = (c or "#8a8f99").lstrip("#")
    if len(c) != 6:
        return (0.55, 0.58, 0.62)
    return tuple(int(c[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def hex_de_paleta(indice: int) -> str:
    """Color de paleta de la pieza que ocupa `indice` en la escena (regla del viewport web)."""
    return PALETTE[indice % len(PALETTE)]


def color_pieza(fid: str, indice: int, colores: dict | None) -> tuple[float, float, float]:
    """RGB 0..1 de una pieza: el color asignado gana; si no, la paleta por índice."""
    return hex_a_rgb((colores or {}).get(fid) or hex_de_paleta(indice))


def bounds_malla(vertices):
    """(min, max) de los vértices = `actor.GetBounds()` de la malla (build123d Vector: .X/.Y/.Z)."""
    import numpy as np

    xs = [v.X for v in vertices]
    ys = [v.Y for v in vertices]
    zs = [v.Z for v in vertices]
    return np.array([min(xs), min(ys), min(zs)]), np.array([max(xs), max(ys), max(zs)])


def polydata(vertices, triangles):
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


def phong_de_pbr(metalness: float, roughness: float, color) -> dict:
    """Traduce un acabado PBR (metálico-rugoso, la tabla `library/apariencia.py`) al Phong de
    VTK, que no tiene luz de ambiente por imagen: lo rugoso apaga y ensancha el brillo, lo
    metálico lo sube y lo TIÑE con su color (el brillo de un dieléctrico es blanco) y le resta
    algo de difuso. Calibrado para que el acero pintado (0.15 / 0.55) dé el Phong de siempre
    (`ESPECULAR`, `POTENCIA_ESPECULAR`)."""
    m = min(max(float(metalness), 0.0), 1.0)
    liso = 1.0 - min(max(float(roughness), 0.0), 1.0)
    return {
        "ambiente": AMBIENTE,
        "difuso": DIFUSO * (1.0 - 0.35 * m),
        "especular": 0.06 + 0.5 * liso * (0.3 + 0.7 * m),
        "potencia": 4.0 + 96.0 * liso * liso,
        "color_especular": tuple(1.0 + (c - 1.0) * m for c in color),
    }


def actor_superficie(pd, color, opacidad: float, pbr: tuple[float, float] | None = None):
    """Actor sombreado SUAVE de una malla: normales interpoladas con ángulo de arista 35° y
    material Phong. No modifica `pd` (se puede compartir con `actor_aristas`). `pbr` =
    (metalness, roughness) del acabado de la pieza; None = el Phong genérico de siempre."""
    import vtk

    nrm = vtk.vtkPolyDataNormals()
    nrm.SetInputData(pd)
    nrm.SetFeatureAngle(ANGULO_ARISTA)
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
    prop.SetColor(*color)
    prop.SetOpacity(opacidad)
    prop.SetInterpolationToPhong()   # sombreado SUAVE (normales interpoladas)
    if pbr is None:
        prop.SetAmbient(AMBIENTE)
        prop.SetDiffuse(DIFUSO)
        prop.SetSpecular(ESPECULAR)
        prop.SetSpecularPower(POTENCIA_ESPECULAR)
    else:
        ph = phong_de_pbr(pbr[0], pbr[1], color)
        prop.SetAmbient(ph["ambiente"])
        prop.SetDiffuse(ph["difuso"])
        prop.SetSpecular(ph["especular"])
        prop.SetSpecularPower(ph["potencia"])
        prop.SetSpecularColor(*ph["color_especular"])
    return actor


def actor_aristas(pd):
    """Actor de aristas de FEATURE (creases) + borde, sobre la malla → separa visualmente
    piezas adyacentes del mismo color (equivalente al toCreasedNormals del viewport web)."""
    import vtk

    fe = vtk.vtkFeatureEdges()
    fe.SetInputData(pd)
    fe.BoundaryEdgesOn()
    fe.FeatureEdgesOn()
    fe.SetFeatureAngle(ANGULO_ARISTA)   # mismo ángulo que las normales suaves
    fe.ManifoldEdgesOff()
    fe.NonManifoldEdgesOff()
    # vtkFeatureEdges colorea por TIPO de arista (escalares por celda: borde/feature) y el mapper
    # los pinta con su LUT → aristas ROJAS en VTK 9.3. Sin escalares manda el color del actor.
    fe.ColoringOff()
    m = vtk.vtkPolyDataMapper()
    m.SetInputConnection(fe.GetOutputPort())
    m.ScalarVisibilityOff()
    m.SetResolveCoincidentTopologyToPolygonOffset()  # evita z-fighting con la superficie
    a = vtk.vtkActor()
    a.SetMapper(m)
    a.GetProperty().SetColor(0.12, 0.12, 0.15)
    a.GetProperty().SetLineWidth(1.0)
    a.GetProperty().LightingOff()
    return a


def poner_fondo(ren) -> None:
    ren.SetBackground(*FONDO_ABAJO)
    ren.SetBackground2(*FONDO_ARRIBA)
    ren.GradientBackgroundOn()


def poner_luces(ren) -> None:
    """Iluminación de estudio (key + fill + back), como el IBL del web. Las luces del kit son de
    cámara: siguen a la cámara cuando orbita."""
    import vtk

    lk = vtk.vtkLightKit()
    lk.SetKeyLightIntensity(0.9)
    lk.AddLightsToRenderer(ren)


def modo_transparencia(rw, ren, translucido: bool) -> None:
    """Con translucidez: depth peeling (transparencia correcta, independiente del orden), que
    exige planos alfa y SIN MSAA, más FXAA para recuperar bordes nítidos. Sin translucidez: MSAA
    8× y nada de peeling. VTK 9.3 acepta el cambio en una ventana viva (medido en la F2)."""
    if translucido:
        rw.SetAlphaBitPlanes(1)
        rw.SetMultiSamples(0)
        ren.SetUseDepthPeeling(1)
        ren.SetMaximumNumberOfPeels(8)
        ren.SetOcclusionRatio(0.0)
        ren.SetUseFXAA(True)
    else:
        rw.SetAlphaBitPlanes(0)
        rw.SetMultiSamples(8)
        ren.SetUseDepthPeeling(0)
        ren.SetUseFXAA(False)


def poner_camara(ren, bmins, bmaxs, *, view, azimuth, elevation, zoom, roll=0.0, pan=None):
    """Cámara ortográfica ÚNICA (la comparten el render, el video y el pick): dirección desde
    `resolve_angles`, encuadre `ResetCamera` al bbox dado, zoom. Devuelve la vtkCamera.
    `roll` (grados) gira la cámara sobre su eje de visión (3.er GDL rotacional, complementa
    azimuth/elevation que dan la dirección). `pan` = [px, py] desplaza el encuadre en el PLANO de
    vista (fracción de la semialtura: +px → derecha, +py → arriba) para enfocar un detalle fuera del
    centro del bbox sin aislar — en proyección ortográfica esto ES la 'posición de cámara' lateral
    (la distancia del ojo es irrelevante). Importante: el aspecto lo toma `ResetCamera` del tamaño de
    la ventana → fija el size ANTES. `ResetCamera` encuadra la ESFERA del bbox: la escala no cambia
    con la dirección (una órbita no «respira»)."""
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
