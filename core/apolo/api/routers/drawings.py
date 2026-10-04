"""Rutas de planos: lámina simple, desplegado de chapa, juego de planos, plano por intención.

Router de la API (F6b del plan `docs/plans/partir-api-main.md`): movidas tal cual desde
`main.py`. Los mapas por pieza (fits, roscas, datum, GD&T, tolerancias) son de
`apolo.services.drawing_maps`; el cajetín (`_drawing_meta`) y los colores del viewport
(`_feature_colors`), de la API. Fits y roscas se consultan aquí porque los rotulan los planos.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from apolo.services.drawing_maps import (
    hole_thread_map as _hole_thread_map,
    scene_fit_map as _scene_fit_map,
    sheet_set_maps,
)
from apolo.state import STATE_LOCK

from ..common import _drawing_meta, _expand_ids
from ..scene import _feature_colors
from ..session import S

router = APIRouter()


def _sheet_model(sheet: str, hidden: bool, dims: str = "", section: bool = False, bom: bool = False):
    from apolo.drawing import compose_sheet

    dims_features = [s for s in dims.split(",") if s] or None
    with STATE_LOCK:
        try:
            return compose_sheet(
                S.doc.scene, sheet=sheet, include_hidden=hidden, project_name=S.doc.name,
                dims_features=dims_features, section=section, bom=bom, meta=_drawing_meta(),
                fasteners=S.doc.fasteners,  # V7.2 A: símbolos de soldadura ISO 2553 (no-op sin cordones)
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/drawing.svg")
def drawing_svg(sheet: str = "A3", hidden: bool = False, dims: str = "", section: bool = False, bom: bool = False) -> Response:
    from apolo.drawing import sheet_to_svg

    return Response(
        content=sheet_to_svg(_sheet_model(sheet, hidden, dims, section, bom)),
        media_type="image/svg+xml",
    )


@router.get("/api/drawing.dxf")
def drawing_dxf(sheet: str = "A3", hidden: bool = False, dims: str = "", section: bool = False, bom: bool = False) -> Response:
    from apolo.drawing import sheet_to_dxf

    return Response(
        content=sheet_to_dxf(_sheet_model(sheet, hidden, dims, section, bom)),
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "plano"}.dxf"'},
    )


def _sheetmetal_flat(feature_id: str):
    """Localiza el comando create_sheet_metal que generó la feature y devuelve su
    SheetModel desplegado (resolviendo expresiones del proyecto)."""
    from apolo.commands import resolve_params
    from apolo.commands.models import SheetMetalParams
    from apolo.library.sheetmetal import flat_pattern

    with STATE_LOCK:
        feat = S.doc.scene.get(feature_id)
        if feat is None:
            raise HTTPException(status_code=404, detail=f"No existe el sólido '{feature_id}'")
        cmd = next((c for c in S.doc.commands if c["id"] == feat.command_id), None)
        if cmd is None or cmd["type"] != "create_sheet_metal":
            raise HTTPException(status_code=400, detail=f"'{feature_id}' no es una chapa metálica")
        try:
            from apolo.library.catalog import CATALOG
            from apolo.library.materials import resolve_material
            from apolo.library.sheetmetal import flaps_from_specs, k_for_material

            p = SheetMetalParams.model_validate(resolve_params(cmd["params"], S.doc.variables_resolved))
            # K-factor: explícito gana; si no, por MATERIAL de la pieza (V5.5)
            k = p.k_factor if p.k_factor is not None else k_for_material(
                resolve_material(feat, CATALOG, S.doc.default_material())
            )
            return p.name, flat_pattern(
                p.name, p.ancho, p.fondo, p.espesor, p.lados,
                p.altura_pestana, p.angulo, p.radio, k,
                holes=[(h.x, h.y, h.d) for h in p.holes],
                flaps=flaps_from_specs(p.flaps),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/sheetmetal/{feature_id}/flat.svg")
def sheetmetal_flat_svg(feature_id: str) -> Response:
    from apolo.drawing import sheet_to_svg

    _, model = _sheetmetal_flat(feature_id)
    return Response(content=sheet_to_svg(model), media_type="image/svg+xml")


@router.get("/api/sheetmetal/{feature_id}/flat.dxf")
def sheetmetal_flat_dxf(feature_id: str) -> Response:
    from apolo.drawing import sheet_to_dxf

    name, model = _sheetmetal_flat(feature_id)
    return Response(
        content=sheet_to_dxf(model),
        media_type="application/dxf",
        headers={"Content-Disposition": f'attachment; filename="{name or "chapa"}-flat.dxf"'},
    )


@router.get("/api/sheetmetal/{feature_id}/flat.dwg")
def sheetmetal_flat_dwg(feature_id: str) -> Response:
    """Desplegado en DWG (V5.9) — requiere ODA File Converter instalado."""
    from apolo.drawing import DwgError, sheet_to_dwg

    name, model = _sheetmetal_flat(feature_id)
    try:
        data = sheet_to_dwg(model)
    except DwgError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type="application/acad",
        headers={"Content-Disposition": f'attachment; filename="{name or "chapa"}-flat.dwg"'},
    )


@router.get("/api/drawing.pdf")
def drawing_pdf(sheet: str = "A3", hidden: bool = False, dims: str = "", section: bool = False, bom: bool = False) -> Response:
    from apolo.drawing import sheet_to_pdf

    return Response(
        content=sheet_to_pdf(_sheet_model(sheet, hidden, dims, section, bom)),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "plano"}.pdf"'},
    )


@router.get("/api/drawingset.pdf")
def drawingset_pdf(template: str = "generico", sheet: str = "A3", shaded: bool = False) -> Response:
    """Juego de planos en PDF MULTIPÁGINA: conjunto (con BOM) + 1 lámina por pieza acotada +
    cédula de corte/herraje. `template`: carpinteria/weldment/chapa/generico. `shaded`: el
    conjunto lleva isométrica SOMBREADA a color (estilo Inventor)."""
    from apolo.drawing import sheet_set, sheets_to_pdf

    with STATE_LOCK:
        try:
            pages = sheet_set(S.doc.scene, project_name=S.doc.name, template=template,
                              meta=_drawing_meta(), sheet=sheet, shaded=shaded,
                              colors=_feature_colors(), **sheet_set_maps(S.doc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=sheets_to_pdf(pages), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "juego"}-planos.pdf"'},
    )


@router.get("/api/drawingset.dwg")
def drawingset_dwg(template: str = "generico", sheet: str = "A3") -> Response:
    """Juego de planos en DWG (V5.9): como DWG no es multipágina, devuelve un ZIP con
    un DWG por lámina. Requiere ODA File Converter instalado."""
    import io as _io
    import zipfile

    from apolo.drawing import DwgError, sheet_set, sheet_to_dwg

    with STATE_LOCK:
        try:
            pages = sheet_set(S.doc.scene, project_name=S.doc.name, template=template,
                              meta=_drawing_meta(), sheet=sheet,
                              colors=_feature_colors(), **sheet_set_maps(S.doc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        base = (S.doc.name or "juego").replace("/", "-")
    buf = _io.BytesIO()
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for i, page in enumerate(pages, start=1):
                zf.writestr(f"{base}-hoja-{i:02d}.dwg", sheet_to_dwg(page))
    except DwgError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{base}-planos-dwg.zip"'},
    )


class DrawingSpecIn(BaseModel):
    sheet: str = "A3"
    section: str = ""          # "x"/"y"/"z" o "" (sin corte)
    detail: dict | None = None  # {view,u,v,radius,scale}
    dims: list[str] = []        # ids a acotar (tamaño en planta)
    datum_dims: list[str] = []  # ids → cotas de posición desde la base (alzado)
    bom: bool = False
    isolate: list[str] = []     # solo estas piezas (aislado, sin tocar el documento)
    include_hidden: bool = False
    format: str = "pdf"         # pdf | svg | dxf
    meta: dict | None = None
    cutlist: bool = False       # tabla DESPIECE (L×A×E por tabla) en vez del BOM sin dimensiones
    member_detail: dict | None = None  # {member, pick:[t,w,l], locate:[ids], scale, name} → detalle de 1 tabla
    auto_dims: bool = False     # acota SOLO la posición de los agujeros (Fase 2)
    interface_dims: bool = False  # cotas de MONTAJE: pitch centro-a-centro del patrón de agujeros
    hardware: bool = False      # añade tabla CÉDULA DE HERRAJE bajo el DESPIECE (Fase 4)
    explode: dict | None = None  # {axis,factor} → VISTA EXPLOSIONADA (Fase 3)
    notes: list[str] = []        # bloque de NOTAS generales en la lámina (Fase 5)
    assembly_notes: list[str] | None = None  # NOTAS DE MONTAJE: null=off · []=auto del herraje · [..]=explícitas
    shaded: bool = False         # isométrica SOMBREADA a color (estilo Inventor)
    hole_fits: dict[str, str] = {}  # {"20": "H7"} Ø_nominal→clase ISO 286; se mergea SOBRE el mapa automático (V5.4)
    hole_threads: dict[str, str] = {}  # {"6.8": "M8"} Ø_broca→rosca; se mergea SOBRE el mapa automático (V5.7)


@router.get("/api/fits")
def get_fits(nominal: float, hole: str = "", shaft: str = "") -> dict:
    """Límites ISO 286 (V5.4): con `hole` y `shaft` devuelve el análisis del ajuste
    (juego/transición/apriete); con uno solo, sus límites. Read-only."""
    from apolo.library.engineering.fits import fit_check, fit_limits

    try:
        if hole and shaft:
            return fit_check(nominal, hole, shaft)
        if hole or shaft:
            return fit_limits(nominal, hole or shaft)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip("'\"")) from exc
    raise HTTPException(status_code=400, detail="Indica hole (H7) y/o shaft (g6)")


@router.get("/api/threads")
def get_threads(size: str) -> dict:
    """Ficha de una rosca métrica ISO 261/262 (V5.7): paso, broca de machuelado
    publicada, área resistente y norma. Read-only."""
    from apolo.library.engineering.threads import thread_spec

    try:
        return thread_spec(size)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc).strip("'\"")) from exc


@router.post("/api/drawing/spec")
def drawing_spec(spec: DrawingSpecIn) -> Response:
    """Plano profesional por INTENCIÓN: una sola spec declara vistas/corte/detalle/cotas/
    BOM/aislado/cajetín y el motor lo compone. format = pdf|svg|dxf. Read-only (el aislado
    filtra la escena sin tocar la visibilidad del documento)."""
    from apolo.drawing import compose_sheet, sheet_to_dxf, sheet_to_pdf, sheet_to_svg

    with STATE_LOCK:
        scene = S.doc.scene
        if spec.isolate:
            iso = _expand_ids(spec.isolate) or []  # acepta NOMBRES de grupo (V5.2)
            scene = {fid: scene[fid] for fid in iso if fid in scene}
            if not scene:
                raise HTTPException(status_code=400, detail="isolate: ningún id existe en la escena")
        # el mapa de fits se construye desde la escena EFECTIVA (post-isolate): aislar un
        # solo eje muestra SU fit sin conflicto con otro Ø igual del resto (V7.2c)
        fits_map = _scene_fit_map(S.doc, scene)
        for k, v in (spec.hole_fits or {}).items():  # override del agente encima del auto
            try:
                fits_map[float(k)] = v
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"hole_fits: clave '{k}' no es un Ø numérico") from None
        threads_map = _hole_thread_map(S.doc)
        for k, v in (spec.hole_threads or {}).items():  # override espejo (V5.7)
            try:
                threads_map[float(k)] = v
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"hole_threads: clave '{k}' no es un Ø numérico") from None
        try:
            model = compose_sheet(
                scene, sheet=spec.sheet, include_hidden=spec.include_hidden, project_name=S.doc.name,
                dims_features=spec.dims or None, section=spec.section or False, bom=spec.bom,
                detail=spec.detail, datum_dims=spec.datum_dims or None,
                cutlist=spec.cutlist, member_detail=spec.member_detail,
                auto_dims=spec.auto_dims, interface_dims=spec.interface_dims,
                hardware=spec.hardware, explode=spec.explode,
                notes=spec.notes or None, assembly_notes=spec.assembly_notes,
                shaded=spec.shaded, colors=_feature_colors(),
                hole_fits=fits_map or None, hole_threads=threads_map or None,
                fasteners=S.doc.fasteners,  # V7.2 A: símbolos de soldadura ISO 2553 en el conjunto/GA
                meta={**_drawing_meta(), **(spec.meta or {})},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if spec.format == "svg":
        return Response(content=sheet_to_svg(model), media_type="image/svg+xml")
    if spec.format == "dxf":
        return Response(content=sheet_to_dxf(model), media_type="application/dxf",
                        headers={"Content-Disposition": "attachment; filename=plano.dxf"})
    if spec.format == "dwg":  # V5.9: DXF convertido con ODA File Converter
        from apolo.drawing import DwgError, sheet_to_dwg

        try:
            data = sheet_to_dwg(model)
        except DwgError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(content=data, media_type="application/acad",
                        headers={"Content-Disposition": "attachment; filename=plano.dwg"})
    return Response(content=sheet_to_pdf(model), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "plano"}.pdf"'})
