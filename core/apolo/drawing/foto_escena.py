"""Una foto 3D de la escena para una lámina, con la regla de los dos locks (plan manual-rapido).

Es el camino de las fotos del manual de ensamblaje (`manual_fotos.py`, F1) para UNA foto: la
portada de la memoria de cálculo (F2). Antes era `render.render_scene_png` (matplotlib) bajo
`STATE_LOCK`: 2 322 s en la piloto 74 con la API congelada (F0).

1. `extraer_foto` (bajo `STATE_LOCK` en la API): colores, apariencias, definiciones y una FOTO
   (id, shape, nombre) de cada pieza visible. No tesela.
2. `teselar_foto(ex, candado)`: las mallas con sus zonas, tomando el candado PIEZA POR PIEZA (en
   la API, `STATE_LOCK`): una mutación espera, como mucho, una pieza. Las instancias usan la
   malla de su definición (teselado-rapido D1). Las formas son las de la foto de la fase 1
   (ningún executor muta un shape en sitio).
3. `dibujar_foto` (fuera de `STATE_LOCK`): una `EscenaViva` bajo `RENDER_LOCK`, con el aspecto
   de `render_view` (D3). Sin contexto OpenGL, matplotlib sobre las MISMAS mallas, con aviso en
   el log (D4): no vuelve a tomar el lock.

`formas_de` y `teselar_formas` los comparte el manual.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from types import SimpleNamespace

log = logging.getLogger(__name__)

#: Alto/ancho de las fotos: el mismo de la foto de `render_view` (`render_vtk._H`).
ASPECTO = 0.78


def lado_par(x: float) -> int:
    """El lado más cercano par y ≥ 2 (la `EscenaViva` exige lados pares)."""
    return max(2, int(round(x / 2.0)) * 2)


def formas_de(vis: dict) -> list:
    """La FOTO de cada pieza de `vis` que necesitan las fases sin documento: datos y el shape (que
    no se muta en sitio). OCCT no se toca: es barata bajo el lock."""
    return [SimpleNamespace(id=fid, shape=f.shape, visible=True, name=getattr(f, "name", ""),
                            material=getattr(f, "material", None),
                            mesh_key=getattr(f, "mesh_key", None),
                            matrix=getattr(f, "matrix", None)) for fid, f in vis.items()]


def definiciones_usadas(formas: list, definiciones: dict | None) -> dict | None:
    """mesh_key → shape de la definición de las instancias de `formas`, tomado en la fase 1
    (`DEFINITIONS` es una LRU: podría desalojarla mientras se tesela)."""
    defs = {f.mesh_key: definiciones[f.mesh_key] for f in formas
            if definiciones and f.mesh_key and f.matrix and f.mesh_key in definiciones}
    return defs or None


def teselar_formas(formas: list, apariencias: dict | None, definiciones: dict | None,
                   candado=None):
    """(piezas, bbox) de `formas`: cada una teselada con la caché de render y sus zonas, tomando
    `candado` (un context manager; en la API, `STATE_LOCK`) UNA vez por pieza. `bbox` = (min,
    max) de las mallas, o None si ninguna dejó malla."""
    import numpy as np

    from apolo.kernel import render_vivo
    from apolo.kernel.render_comun import bounds_malla

    tomar = candado if candado is not None else contextlib.nullcontext()
    piezas = []
    for forma in formas:
        with tomar:
            piezas += render_vivo.extraer_piezas({forma.id: forma}, apariencias, zonas=True,
                                                 definiciones=definiciones)
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for p in piezas:
        mn, mx = bounds_malla(p.vertices)
        lo, hi = np.minimum(lo, mn), np.maximum(hi, mx)
    return piezas, ((lo, hi) if np.isfinite(lo).all() else None)


@dataclass
class FotoExtraida:
    """Lo que las fases 2 y 3 necesitan; tras `teselar_foto`, `piezas` y `bbox` son datos puros
    (el shape de cada pieza sólo sirve de identidad)."""

    formas: list
    colores: dict          # id → hex fijado con la escena entera (la regla del viewport)
    apariencias: dict | None
    definiciones: dict | None
    size_px: int
    piezas: list | None = None
    bbox: tuple | None = None


def extraer_foto(scene: dict, *, colors: dict | None = None, apariencias: dict | None = None,
                 definiciones: dict | None = None, size_px: int = 620) -> FotoExtraida | None:
    """FASE 1, sin teselar. `colors` = los colores del documento (ganan a la paleta);
    `apariencias` = `services.apariencia.apariencias_render` (acabados y zonas, D3);
    `definiciones` = `services.definiciones.definiciones_de(scene)`. None si no hay nada
    visible (la lámina sale sin foto)."""
    from apolo.kernel.render_vivo import colores_fijos

    vis = {fid: f for fid, f in scene.items() if getattr(f, "visible", True)}
    if not vis:
        return None
    formas = formas_de(vis)
    aps = {fid: ap for fid, ap in apariencias.items() if fid in vis} if apariencias else None
    return FotoExtraida(formas, colores_fijos(scene, colors), aps,
                        definiciones_usadas(formas, definiciones), int(size_px))


def teselar_foto(ex: FotoExtraida, candado=None) -> FotoExtraida:
    """FASE 2: las mallas, con `candado` tomado una vez por pieza (sin él, de corrido)."""
    ex.piezas, ex.bbox = teselar_formas(ex.formas, ex.apariencias, ex.definiciones, candado)
    return ex


def _foto_vtk(ex: FotoExtraida) -> bytes:
    from apolo.kernel.render_vivo import EscenaViva
    from apolo.kernel.render_vtk import RENDER_LOCK

    with RENDER_LOCK:
        with EscenaViva(ex.bbox, ex.colores, ancho=lado_par(ex.size_px),
                        alto=lado_par(ex.size_px * ASPECTO), apariencias=ex.apariencias) as esc:
            esc.aplicar(ex.piezas)
            return esc.png()


def _foto_matplotlib(ex: FotoExtraida) -> bytes:
    from apolo.kernel.render import render_mallas_png

    colores = {fid: (ex.apariencias or {}).get(fid, {}).get("color") or hexa
               for fid, hexa in ex.colores.items()}
    return render_mallas_png([(p.id, p.vertices, p.triangulos) for p in ex.piezas], ex.bbox,
                             size_px=ex.size_px, colors=colores)


def dibujar_foto(ex: FotoExtraida) -> bytes | None:
    """FASE 3, fuera de `STATE_LOCK` y tras `teselar_foto`: el PNG, o None si ninguna pieza dejó
    malla. VTK toma `RENDER_LOCK` (no lo sostengas al llamar); sin OpenGL, matplotlib."""
    if ex.piezas is None:
        raise ValueError("Faltan las mallas de la foto: llama a teselar_foto antes")
    if not ex.piezas or ex.bbox is None:
        return None
    try:
        return _foto_vtk(ex)
    except Exception:  # noqa: BLE001 — sin contexto OpenGL u otro fallo de VTK
        log.warning("Foto de la lámina: VTK falló (¿sin contexto OpenGL?); se dibuja con "
                    "matplotlib", exc_info=True)
        return _foto_matplotlib(ex)
