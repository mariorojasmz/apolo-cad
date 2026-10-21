"""El manual de ensamblaje por fases, con la regla de los dos locks (plan manual-rapido, D2).

1. `extraer_manual` (OCCT, bajo `STATE_LOCK` en la API): la secuencia, los textos de cada paso,
   el cajetín, las apariencias y una FOTO del estado (id, shape, nombre) de cada pieza visible.
2. `teselar_manual(ex, candado)`: las mallas, teseladas UNA vez con sus zonas de acabado, tomando
   el candado PIEZA POR PIEZA (en la API, `STATE_LOCK`). Medido en la F0: teselar en frío la
   piloto 74 cuesta ~280 s (19 cadenas de ~12 s, casi todo el Python de `Shape.tessellate`); de
   un tirón congelaría la API casi 5 min. Así una mutación espera, como mucho, una pieza. Las
   formas son las de la foto de la fase 1 (ningún executor muta un shape en sitio): el manual es
   del documento tal como estaba al pedirlo.
3. `fotos_manual` (fuera de `STATE_LOCK`; VTK bajo `RENDER_LOCK`): UNA `EscenaViva` dibuja la
   portada y cada paso cambiando sólo qué se ve (D1): lo nuevo con su acabado, lo ya montado en
   gris fantasma; la cámara es la misma en todas. Sin contexto OpenGL cae a matplotlib sobre las
   mismas mallas y lo dice en el log (D4): el entregable no desaparece.
4. `componer_manual` (puro): las láminas `SheetModel`, con los mismos textos de siempre (D5).

La secuencia y los textos salen de `assembly_manual.py`; aquí sólo cambia dónde y con qué se
dibujan las fotos.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

log = logging.getLogger(__name__)

#: Alto/ancho de las fotos: el mismo de la foto de `render_view` (`render_vtk._H`).
_ASPECTO = 0.78


@dataclass
class ManualExtraido:
    """Lo que las fases siguientes necesitan. `formas` = la foto de cada pieza visible (id,
    shape, nombre, material) que consume `teselar_manual`; después, `piezas` y `bbox` son datos
    puros (las piezas llevan el shape sólo como identidad)."""

    W: float
    H: float
    sheet: str
    project_name: str
    base_meta: dict
    stages: list          # [{label, ids, is_hw, …}] en orden de montaje
    instrucciones: list   # una por paso
    filas: list           # [[«N× descripción»]] por paso
    totals: dict
    colores: dict         # id → hex fijado con la escena entera
    apariencias: dict | None
    size_px: int
    formas: list          # [SimpleNamespace(id, shape, name, material)] de las visibles
    piezas: list | None = None   # [render_vivo.PiezaViva], tras `teselar_manual`
    bbox: tuple | None = None    # (min, max) en mm: la cámara de TODAS las fotos


def extraer_manual(scene: dict, *, commands: list[dict], project_name: str = "Sin título",
                   sheet: str = "A3", meta: dict | None = None, colors: dict | None = None,
                   size_px: int = 700, stages: list[dict] | None = None,
                   apariencias: dict | None = None) -> ManualExtraido:
    """FASE OCCT sin teselar. `stages` = la secuencia de montaje ya derivada
    (`services/montaje.py`); sin ella, la del log + familias de catálogo + soporte.
    `apariencias` = la tabla de acabados del documento con sus zonas
    (`services.apariencia.apariencias_render`); sin ella, `colors` y la paleta. Lanza ValueError
    si no hay nada que ensamblar."""
    from apolo.kernel.render_vivo import colores_fijos
    from apolo.library.catalog import CATALOG
    from apolo.library.cutlist import dominant_material, hardware_schedule, scene_weight_kg

    from .assembly_manual import (
        SHEETS,
        _instruction,
        _step_rows,
        assembly_steps,
        order_by_support,
    )

    W, H = SHEETS.get(sheet, SHEETS["A3"])
    vis = {fid: f for fid, f in scene.items() if getattr(f, "visible", True)}
    if not vis:
        raise ValueError("Escena vacía: nada que ensamblar")
    if stages is None:
        stages = assembly_steps(scene, commands, CATALOG)
        stages = order_by_support(vis, stages, CATALOG)  # V7.2b A: soporte + fusión de huérfanos
    if not stages:
        raise ValueError("No se pudo derivar la secuencia de ensamblaje")
    stages = [{**st, "ids": list(st["ids"])} for st in stages]

    base_meta = {
        "project": project_name, "drawing_no": (meta or {}).get("drawing_no", "—"),
        "scale": "—", "sheet": sheet, "material": dominant_material(vis) or "—",
        "finish": "—", "weight_kg": scene_weight_kg(vis), "tolerance": "—", "units": "mm",
        "drawn_by": "", "checked_by": "", "approved_by": "",
        "date": (meta or {}).get("date", date.today().isoformat()),
        "revisions": (meta or {}).get("revisions", []),
    }
    totals = {"piezas": len(vis), "herraje": sum(h["cantidad"] for h in hardware_schedule(vis))}
    instrucciones, filas, montadas = [], [], set()
    for st in stages:
        montadas.update(st["ids"])
        instrucciones.append(_instruction(st, scene, CATALOG, len(st["ids"]), len(montadas),
                                          len(vis)))
        filas.append(_step_rows({fid: scene[fid] for fid in st["ids"]}))

    aps = {fid: ap for fid, ap in apariencias.items() if fid in vis} if apariencias else None
    formas = [SimpleNamespace(id=fid, shape=f.shape, visible=True, name=getattr(f, "name", ""),
                              material=getattr(f, "material", None)) for fid, f in vis.items()]
    return ManualExtraido(W, H, sheet, project_name, base_meta, stages, instrucciones, filas,
                          totals, colores_fijos(vis, colors), aps, int(size_px), formas)


def teselar_manual(ex: ManualExtraido, candado=None) -> ManualExtraido:
    """FASE OCCT por pieza: tesela cada forma de `ex.formas` (con la caché de render) tomando
    `candado` (un context manager; en la API, `STATE_LOCK`) UNA vez por pieza, y fija la caja de
    la cámara con las mallas. Sin candado, de corrido (quien es dueño del documento)."""
    import numpy as np

    from apolo.kernel import render_vivo
    from apolo.kernel.render_comun import bounds_malla

    tomar = candado if candado is not None else contextlib.nullcontext()
    piezas = []
    for forma in ex.formas:
        with tomar:
            piezas += render_vivo.extraer_piezas({forma.id: forma}, ex.apariencias, zonas=True)
    lo, hi = np.full(3, np.inf), np.full(3, -np.inf)
    for p in piezas:
        mn, mx = bounds_malla(p.vertices)
        lo, hi = np.minimum(lo, mn), np.maximum(hi, mx)
    if not np.isfinite(lo).all():   # ninguna pieza dejó malla: la caja OCCT de siempre
        from .assembly_manual import _scene_bbox

        with tomar:
            lo, hi = _scene_bbox({f.id: f for f in ex.formas})
    ex.piezas, ex.bbox = piezas, (lo, hi)
    return ex


def _estados(ex: ManualExtraido):
    """(plenas, fantasmas) de cada foto: la portada (todo pleno) y luego cada paso, con lo
    montado antes en gris."""
    yield None, []
    hechas: list = []
    for st in ex.stages:
        yield list(st["ids"]), list(hechas)
        hechas += st["ids"]


def _par(x: float) -> int:
    return max(2, int(round(x / 2.0)) * 2)


def _fotos_vtk(ex: ManualExtraido) -> list[bytes]:
    from apolo.kernel.render_vivo import EscenaViva
    from apolo.kernel.render_vtk import RENDER_LOCK

    with RENDER_LOCK:
        with EscenaViva(ex.bbox, ex.colores, ancho=_par(ex.size_px),
                        alto=_par(ex.size_px * _ASPECTO), apariencias=ex.apariencias) as esc:
            esc.aplicar(ex.piezas)
            fotos = []
            for plenas, fantasmas in _estados(ex):
                esc.mostrar(plenas, fantasmas)
                fotos.append(esc.png())
            return fotos


def _fotos_matplotlib(ex: ManualExtraido) -> list[bytes]:
    from apolo.kernel.render import render_mallas_png

    por_id = {p.id: p for p in ex.piezas}
    colores = {fid: (ex.apariencias or {}).get(fid, {}).get("color") or hexa
               for fid, hexa in ex.colores.items()}
    fotos = []
    for plenas, fantasmas in _estados(ex):
        ids = list(por_id) if plenas is None else [*fantasmas, *plenas]
        mallas = [(f, por_id[f].vertices, por_id[f].triangulos) for f in ids if f in por_id]
        fotos.append(render_mallas_png(mallas, ex.bbox, size_px=ex.size_px,
                                       highlight_ids=plenas, colors=colores))
    return fotos


def fotos_manual(ex: ManualExtraido) -> list[bytes]:
    """FASE DE DIBUJO, fuera de `STATE_LOCK` y tras `teselar_manual`: los PNG de la portada y de
    cada paso, en orden. VTK toma `RENDER_LOCK` (no lo sostengas al llamar: el respaldo no lo
    necesita)."""
    if ex.piezas is None:
        raise ValueError("Faltan las mallas del manual: llama a teselar_manual antes")
    try:
        return _fotos_vtk(ex)
    except Exception:  # noqa: BLE001 — sin contexto OpenGL u otro fallo de VTK
        log.warning("Fotos del manual: VTK falló (¿sin contexto OpenGL?); se dibujan con "
                    "matplotlib", exc_info=True)
        return _fotos_matplotlib(ex)


def componer_manual(ex: ManualExtraido, fotos: list[bytes]) -> list:
    """FASE PURA: [portada con la secuencia + una lámina por PASO] como `SheetModel`."""
    from .assembly_manual import _cover_page, _step_page

    if len(fotos) != len(ex.stages) + 1:
        raise ValueError(f"El manual tiene {len(ex.stages)} pasos y llegaron {len(fotos)} fotos")
    pages = [_cover_page(ex.W, ex.H, project_name=ex.project_name, png=fotos[0],
                         stages=ex.stages, totals=ex.totals, base_meta=ex.base_meta,
                         sheet=ex.sheet)]
    n = len(ex.stages)
    for k, st in enumerate(ex.stages, start=1):
        pages.append(_step_page(
            ex.W, ex.H, step_no=k, n_steps=n, page_no=k + 1, n_pages=n + 1, stage=st,
            rows=ex.filas[k - 1], instruction=ex.instrucciones[k - 1], png=fotos[k],
            base_meta=ex.base_meta,
        ))
    return pages
