"""Las isométricas SOMBREADAS de los planos, con la regla de los dos locks (plan manual-rapido F2b).

Antes `compose_sheet(shaded=True)` dibujaba la isométrica con `render.render_scene_png`
(matplotlib) en medio de la composición, y la API compone bajo `STATE_LOCK`: el juego de planos
de la piloto (16 fotos) dejaba la API tomada 1 073 s y la hoja GA 1 140 s. Ahora:

1. `compose_sheet(..., foto_diferida=True)` compone la lámina entera (vistas HLR, cotas, tablas,
   cajetín: siguen bajo el lock) y deja RESERVADO el lugar de la foto en `model.hueco_iso`
   (`HuecoIso`: centro, caja máxima, si lleva rótulo, dónde insertar imagen y rótulo, y la
   escena a fotografiar).
2. `extraer(modelos, ...)`, en la MISMA toma del lock: una `foto_escena.FotoExtraida` por hueco
   (sin teselar). Una lámina por pieza fotografía su sólido aislado con la apariencia de la
   pieza del documento (`HuecoIso.origen`), sin zonas: el sólido puede ser sólo una parte.
3. `revelar(extraidas, candado)`: tesela tomando `candado` pieza por pieza (en la API,
   `STATE_LOCK`), dibuja TODAS las fotos fuera, en UNA `EscenaViva` bajo `RENDER_LOCK` (cada foto
   cambia el encuadre y lo visible; la ventana se crea una vez) y las pega en su lugar. Sin
   OpenGL, matplotlib sobre las mismas mallas con aviso en el log, como la isométrica de antes.

Fondo blanco y recorte al modelo: en el papel la isométrica ocupa el cuadrante como la de
matplotlib (fondo transparente, `bbox_inches="tight"`), sin el degradado de `render_view`.
Sin `foto_diferida`, `compose_sheet` hace las tres fases de corrido (quien es dueño del
documento: tests, scripts).
"""

from __future__ import annotations

import io
import logging
import struct
from dataclasses import dataclass, replace

from . import foto_escena

log = logging.getLogger(__name__)

#: Ancho de la foto, el de la isométrica de matplotlib de antes.
SIZE_PX = 760
BLANCO = (1.0, 1.0, 1.0)
ROTULO = "ISOMÉTRICA · sombreado"


@dataclass
class HuecoIso:
    """El lugar reservado de la isométrica sombreada en una lámina (mm, origen abajo-izquierda)."""

    cx: float
    cy: float
    ancho: float                 # caja máxima de la foto
    alto: float
    rotulo: bool                 # el cuadrante de arriba está libre (el conjunto: sin perfil)
    i_rotulo: int                # dónde insertar el rótulo y la imagen: el orden de antes
    i_imagen: int
    escena: dict                 # id → Feature: lo que se fotografía (ya filtrado por visible)
    colors: dict | None = None   # los colores que recibió `compose_sheet`
    origen: dict | None = None   # lámina por pieza: {id sintético: id de la pieza del documento}


def reservar(model, centro, ancho: float, alto: float, rotulo: bool, escena: dict,
             colors: dict | None) -> HuecoIso:
    """`compose_sheet`: deja el hueco en `model.hueco_iso` (no dibuja)."""
    model.hueco_iso = HuecoIso(centro[0], centro[1], ancho, alto, rotulo, len(model.labels),
                               len(model.images), escena, colors)
    return model.hueco_iso


def poner(model, png: bytes | None) -> None:
    """Pega `png` en el hueco de `model` (encajado en su caja, con su aspecto) y libera el hueco.
    Sin foto, la lámina queda sin isométrica ni rótulo, como cuando fallaba el render."""
    from .sheet import Image, Label

    hueco, model.hueco_iso = model.hueco_iso, None
    if hueco is None or not png:
        return
    pw, ph = struct.unpack(">II", png[16:24])
    aspect = (pw / ph) if ph else 1.33
    bw, bh = hueco.ancho, hueco.alto
    if bw / bh > aspect:
        bw = bh * aspect
    else:
        bh = bw / aspect
    model.images.insert(hueco.i_imagen, Image(hueco.cx - bw / 2, hueco.cy - bh / 2, bw, bh, png))
    if hueco.rotulo:
        model.labels.insert(hueco.i_rotulo, Label(hueco.cx, hueco.cy + bh / 2 + 3, ROTULO, 3.0))


def extraer(modelos, *, apariencias: dict | None = None,
            definiciones: dict | None = None) -> list[tuple]:
    """FASE 1 (bajo `STATE_LOCK` en la API, sin teselar): [(lámina, FotoExtraida | None)] de las
    láminas con hueco. `apariencias` = `services.apariencia.apariencias_render(doc)`;
    `definiciones` = `services.definiciones.definiciones_de(doc.scene)`."""
    out = []
    for model in modelos:
        hueco = getattr(model, "hueco_iso", None)
        if hueco is None:
            continue
        aps, defs = apariencias, definiciones
        if hueco.origen:   # lámina por pieza: la apariencia de SU pieza, sin zonas
            aps = {sid: {k: v for k, v in apariencias[fid].items() if k != "zonas"}
                   for sid, fid in hueco.origen.items() if apariencias and fid in apariencias}
            defs = None
        try:
            ex = foto_escena.extraer_foto(hueco.escena, colors=hueco.colors,
                                          apariencias=aps or None, definiciones=defs,
                                          size_px=SIZE_PX)
        except Exception:  # noqa: BLE001 — sin foto la lámina sigue valiendo (como antes)
            log.warning("Isométrica sombreada: no se pudo extraer", exc_info=True)
            ex = None
        out.append((model, ex))
    return out


def revelar(extraidas: list[tuple], candado=None) -> None:
    """FASES 2 y 3 (fuera de `STATE_LOCK`): tesela con `candado` pieza por pieza, dibuja y pega
    cada foto en su lámina. VTK toma `RENDER_LOCK`: no lo sostengas al llamar."""
    fotos = []
    for _model, ex in extraidas:
        if ex is not None:
            try:
                foto_escena.teselar_foto(ex, candado)
            except Exception:  # noqa: BLE001
                log.warning("Isométrica sombreada: no se pudo teselar", exc_info=True)
                ex = None
        fotos.append(ex)
    for (model, _ex), png in zip(extraidas, dibujar(fotos)):
        poner(model, png)


def dibujar(fotos: list) -> list:
    """Un PNG (o None) por foto ya teselada: VTK en una sola ventana; sin OpenGL, matplotlib."""
    pngs: list = [None] * len(fotos)
    validas = [(i, ex) for i, ex in enumerate(fotos)
               if ex is not None and ex.piezas and ex.bbox is not None]
    if not validas:
        return pngs
    try:
        for i, png in _fotos_vtk(validas):
            pngs[i] = png
    except Exception:  # noqa: BLE001 — sin contexto OpenGL u otro fallo de VTK
        log.warning("Isométricas de los planos: VTK falló (¿sin contexto OpenGL?); se dibujan "
                    "con matplotlib", exc_info=True)
        for i, ex in validas:
            try:
                pngs[i] = foto_escena._foto_matplotlib(ex)
            except Exception:  # noqa: BLE001 — una foto que falla no tumba el juego
                log.warning("Isométrica sombreada: matplotlib falló", exc_info=True)
    return pngs


def _fotos_vtk(validas: list[tuple]) -> list[tuple]:
    """Todas las fotos en UNA `EscenaViva`: los ids llevan el prefijo de su foto (las láminas por
    pieza repiten el id sintético) y cada foto muestra sólo lo suyo con su encuadre."""
    from apolo.kernel.render_vivo import EscenaViva
    from apolo.kernel.render_vtk import RENDER_LOCK

    colores, aps, piezas, propios = {}, {}, [], []
    for k, (_i, ex) in enumerate(validas):
        pre = f"{k}:"
        colores.update({pre + fid: c for fid, c in ex.colores.items()})
        aps.update({pre + fid: ap for fid, ap in (ex.apariencias or {}).items()})
        mias = [replace(p, id=pre + p.id) for p in ex.piezas]
        piezas += mias
        propios.append([p.id for p in mias])
    out = []
    with RENDER_LOCK:
        with EscenaViva(validas[0][1].bbox, colores, ancho=foto_escena.lado_par(SIZE_PX),
                        alto=foto_escena.lado_par(SIZE_PX * foto_escena.ASPECTO),
                        apariencias=aps or None, fondo=BLANCO) as esc:
            esc.aplicar(piezas)
            for (i, ex), ids in zip(validas, propios):
                esc.encuadrar(ex.bbox)
                esc.mostrar(plenas=ids)
                out.append((i, _recortar(esc.fotograma())))
    return out


def _recortar(rgb, margen: int = 4) -> bytes:
    """PNG del fotograma recortado a lo que no es fondo blanco (más `margen` px)."""
    import numpy as np
    from PIL import Image

    ys, xs = np.nonzero((rgb < 250).any(axis=2))
    if len(xs):
        h, w = rgb.shape[:2]
        rgb = rgb[max(ys.min() - margen, 0):min(ys.max() + margen + 1, h),
                  max(xs.min() - margen, 0):min(xs.max() + margen + 1, w)]
    buf = io.BytesIO()
    Image.fromarray(np.ascontiguousarray(rgb)).save(buf, format="PNG")
    return buf.getvalue()
