"""Rutas de entregables: catálogo, BOM y costeo, lista de corte, nesting, memoria, cotización y manual.

Router de la API (F6c del plan `docs/plans/partir-api-main.md`): movidas tal cual desde
`main.py`. La memoria de cálculo comparte con `/api/checks` SÓLO lo idéntico
(`services.engineering_rules`); sus diferencias son deliberadas (D7) y se quedan aquí.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from apolo.library import bom_from_scene, bom_to_csv, catalog_payload
from apolo.services.engineering_rules import (
    conveyor_params_from_doc,
    inherit_inclination,
    requirement_inputs,
    structure_rules,
)
from apolo.state import STATE_LOCK

from ..common import _drawing_meta, _expand_ids, _stackup_rules
from ..scene import _feature_colors
from ..session import S

router = APIRouter()


@router.get("/api/catalog")
def get_catalog(category: str | None = None, names_only: bool = False) -> list[dict]:
    return catalog_payload(category, names_only)


@router.get("/api/bom")
def get_bom(by_group: bool = False) -> list[dict]:
    """Con `by_group=true` cada fila lleva su `grupo` (sub-ensamblaje) y las piezas
    iguales de grupos distintos salen separadas — subtotales por grupo/instancia."""
    with STATE_LOCK:
        return bom_from_scene(S.doc.scene, S.doc.default_material(), by_group=by_group)


@router.get("/api/costing.json")
def get_costing() -> dict:
    """BOM COSTEADO (misma agrupación del BOM + costo_ud/costo_total USD por fila con su
    fuente: catálogo referencial / estimación hardware / fabricación) + totales por
    categoría, catálogo vs fabricación e ítem más costoso. Read-only."""
    from apolo.library.costing import scene_costing

    with STATE_LOCK:
        return scene_costing(S.doc.scene, S.doc.default_material())


@router.get("/api/bom.csv")
def get_bom_csv() -> Response:
    with STATE_LOCK:
        csv_text = bom_to_csv(bom_from_scene(S.doc.scene, S.doc.default_material()))
    return Response(
        content=csv_text.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "proyecto"}-bom.csv"'},
    )


@router.get("/api/cutlist.json")
def cutlist_json() -> dict:
    """Lista de corte (a-medida + catálogo cortable, agrupada por material/dimensiones) +
    totales por material + cédula de herraje. Read-only."""
    from apolo.library.cutlist import cut_list, cut_list_totals, hardware_schedule

    with STATE_LOCK:
        rows = cut_list(S.doc.scene)
        return {
            "lista_de_corte": rows,
            "totales": cut_list_totals(rows),
            "herraje": hardware_schedule(S.doc.scene),
        }


@router.get("/api/cutlist.csv")
def cutlist_csv_endpoint() -> Response:
    from apolo.library.cutlist import cut_list, cut_list_csv, cut_list_totals

    with STATE_LOCK:
        rows = cut_list(S.doc.scene)
        text = cut_list_csv(rows, cut_list_totals(rows))
    return Response(
        content=text, media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=lista-de-corte.csv"},
    )


def _nesting_model(mode: str, stock_w: float, stock_h: float, material: str | None, kerf: float):
    from apolo.library.cutlist import cut_list
    from apolo.library.nesting import nest_1d, nest_2d, nesting_sheet_1d, nesting_sheet_2d

    with STATE_LOCK:
        rows = [r for r in cut_list(S.doc.scene) if not material or r["material"] == material]
    if mode == "1d":
        lengths = [r["largo_mm"] for r in rows for _ in range(r["cantidad"])]
        bars = nest_1d(lengths, stock_w, kerf)
        return nesting_sheet_1d(bars, stock_w, title=f"NESTING 1D · {material or 'todos'}")
    rects = [(r["ancho_mm"], r["largo_mm"]) for r in rows for _ in range(r["cantidad"])]
    sheets = nest_2d(rects, stock_w, stock_h, kerf)
    return nesting_sheet_2d(sheets, stock_w, stock_h, title=f"NESTING 2D · {material or 'todos'}")


@router.get("/api/nesting.svg")
def nesting_svg(
    mode: str = "2d", stock_w: float = 2440.0, stock_h: float = 1220.0,
    material: str | None = None, kerf: float = 3.0,
) -> Response:
    """Plano de nesting (acomodo de corte). mode=2d (tableros/vidrio, stock_w×stock_h) o
    1d (barras de largo stock_w). `material` filtra (madera/vidrio/acero...). Read-only."""
    from apolo.drawing import sheet_to_svg

    model = _nesting_model(mode, stock_w, stock_h, material, kerf)
    return Response(content=sheet_to_svg(model), media_type="image/svg+xml")


@router.get("/api/nesting.dxf")
def nesting_dxf(
    mode: str = "2d", stock_w: float = 2440.0, stock_h: float = 1220.0,
    material: str | None = None, kerf: float = 3.0,
) -> Response:
    from apolo.drawing import sheet_to_dxf

    model = _nesting_model(mode, stock_w, stock_h, material, kerf)
    return Response(
        content=sheet_to_dxf(model), media_type="application/dxf",
        headers={"Content-Disposition": "attachment; filename=nesting.dxf"},
    )


@router.get("/api/nesting.json")
def nesting_json(
    mode: str = "2d", stock_w: float = 2440.0, stock_h: float = 1220.0,
    material: str | None = None, kerf: float = 3.0,
) -> dict:
    """Resumen del nesting: nº de planchas/barras, desperdicio % y nº de piezas. Read-only."""
    from apolo.library.cutlist import cut_list
    from apolo.library.nesting import nest_1d, nest_2d, waste_1d, waste_2d

    with STATE_LOCK:
        rows = [r for r in cut_list(S.doc.scene) if not material or r["material"] == material]
    if mode == "1d":
        lengths = [r["largo_mm"] for r in rows for _ in range(r["cantidad"])]
        bars = nest_1d(lengths, stock_w, kerf)
        return {"mode": "1d", "stock_len_mm": stock_w, "n_barras": len(bars),
                "desperdicio_pct": waste_1d(bars, stock_w), "n_piezas": len(lengths)}
    rects = [(r["ancho_mm"], r["largo_mm"]) for r in rows for _ in range(r["cantidad"])]
    sheets = nest_2d(rects, stock_w, stock_h, kerf)
    return {"mode": "2d", "stock_mm": [stock_w, stock_h], "n_planchas": len(sheets),
            "desperdicio_pct": waste_2d(sheets, stock_w, stock_h), "n_piezas": len(rects)}


@router.get("/api/calc-report.pdf")
def calc_report_pdf(
    carga_kg: float | None = None,
    largo_paquete_mm: float | None = None,
    ancho_paquete_mm: float | None = None,
    velocidad_m_s: float | None = None,
    rev: str = "A",
    sheet: str = "A4",
) -> Response:
    """MEMORIA DE CÁLCULO en PDF multipágina: portada (bases de diseño + índice +
    veredicto) + una página por verificación con su fórmula, sustitución, criterio y
    factor de seguridad. Sin parámetros usa los REQUISITOS guardados del proyecto;
    los explícitos ganan. Read-only."""
    from datetime import date

    from apolo.drawing import sheets_to_pdf
    from apolo.drawing.calc_report import calc_report
    from apolo.kernel.render import render_scene_png
    from apolo.library.rules import conveyor_engineering_check as conv_check
    from apolo.library.rules import detect_conveyor

    with STATE_LOCK:
        req, carga, largo_paq, ancho_paq = requirement_inputs(
            S.doc, carga_kg, largo_paquete_mm, ancho_paquete_mm)
        velocidad = velocidad_m_s if velocidad_m_s is not None else float(req.get("velocidad_m_s") or 0)
        # carga/largo de paquete son requisitos del VERTICAL transportadores: sin ellos se
        # omiten las reglas de conveyor y la memoria se emite igual con las verificaciones
        # UNIVERSALES (estructura/uniones/vuelco + FEA + cadenas de cotas). Exigirlos para
        # todo bloqueaba la memoria de cualquier proyecto que no fuera una faja — hallazgo
        # del SEGUNDO testigo (puerta de carpintería, 2026-07-24).
        sin_req_conveyor = not carga or not largo_paq
        rules: list[dict] = []
        conveyor = None if sin_req_conveyor else (
            conveyor_params_from_doc(S.doc) or detect_conveyor(S.doc.scene, S.doc.variables_resolved))
        if conveyor:
            inherit_inclination(conveyor, req)
            rules += conv_check(conveyor, carga_kg=carga, largo_paquete_mm=largo_paq,
                                velocidad_m_s=velocidad, ancho_paquete_mm=ancho_paq)
        # estructura/uniones/vuelco + página FEA en la memoria (con chequeo de vigencia)
        rules += structure_rules(S.doc, carga, conveyor)
        rules += _stackup_rules()  # V7.3: cadenas de cotas (stack-up) declaradas/auto
        if sin_req_conveyor:
            # DECLARAR lo omitido: una memoria que calla lo que no verificó miente por
            # ausencia. Va como regla-aviso, así viaja a la misma página que el resto.
            rules.append({
                "regla": "alcance de la memoria",
                "estado": "aviso",
                "detalle": "Sin `carga_kg` / `largo_paquete_mm` declarados: se OMITEN las "
                           "verificaciones de transportador (arrastre, adherencia del tambor, "
                           "capacidad, velocidad). Lo verificado aquí es estructural y de "
                           "uniones.",
                "recomendacion": "Declara los requisitos con set_requirements si el equipo "
                                 "transporta producto.",
            })
        hay_piezas = any(getattr(f, "visible", True) for f in S.doc.scene.values())
        if not rules or not hay_piezas:
            raise HTTPException(
                status_code=400,
                detail="No hay nada que documentar: el modelo está vacío o no declara "
                       "uniones, apoyos ni requisitos. Modela/declara y reintenta.",
            )
        png = None
        try:
            vis = {fid: f for fid, f in S.doc.scene.items() if getattr(f, "visible", True)}
            if vis:
                png = render_scene_png(vis, view="iso", size_px=620, clean=True,
                                       colors=_feature_colors())
        except Exception:
            png = None  # sin render la memoria sigue valiendo
        meta = _drawing_meta()
        meta["revisions"] = (meta.get("revisions") or []) + [
            {"rev": rev, "date": date.today().isoformat(), "note": "Memoria de cálculo"}
        ]
        # los requisitos completos van a la portada; los efectivos ganan
        # sin requisitos de transportador NO se inyectan claves vacías a la portada (un
        # «carga_kg: None» impreso es peor que la ausencia del renglón)
        req_efectivos = dict(req)
        if carga:
            req_efectivos["carga_kg"] = carga
        if largo_paq:
            req_efectivos["largo_paquete_mm"] = largo_paq
        if ancho_paq:
            req_efectivos["ancho_paquete_mm"] = ancho_paq
        if velocidad:
            req_efectivos["velocidad_m_s"] = velocidad
        pages = calc_report(S.doc.scene, rules=rules, requirements=req_efectivos,
                            project_name=S.doc.name or "Sin título", png=png, meta=meta,
                            sheet=sheet)
    return Response(
        content=sheets_to_pdf(pages), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "proyecto"}-memoria-calculo.pdf"'},
    )


@router.get("/api/quote.pdf")
def quote_pdf(margin_pct: float = 25.0, tax_pct: float = 0.0,
              currency: str | None = None, fx: float | None = None,
              sheet: str = "A4") -> Response:
    """COTIZACIÓN en PDF multipágina: resumen económico (desglose por categoría, margen,
    impuesto opcional, PRECIO DE VENTA, ítem más costoso, notas comerciales) + detalle
    de partidas (BOM costeado completo con la fuente de cada precio). `currency`/`fx`
    (tipo de cambio sobre USD, solo presentación) caen a los requisitos del proyecto
    (claves `moneda`/`tipo_cambio`); los params explícitos ganan. Read-only."""
    from apolo.drawing import sheets_to_pdf
    from apolo.drawing.quote import quotation_pages

    with STATE_LOCK:
        req = S.doc.requirements or {}
        cur = currency or str(req.get("moneda") or "USD")
        fx_eff = fx if fx is not None else float(req.get("tipo_cambio") or 1.0)
        pages = quotation_pages(
            S.doc.scene, project_name=S.doc.name or "Sin título",
            requirements=S.doc.requirements, margin_pct=margin_pct, tax_pct=tax_pct,
            currency=cur, fx=fx_eff, meta=_drawing_meta(),
        )
    return Response(
        content=sheets_to_pdf(pages), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{S.doc.name or "proyecto"}-cotizacion.pdf"'},
    )


@router.get("/api/assembly-manual.pdf")
def assembly_manual_pdf(sheet: str = "A3", size_px: int = 700, isolate: str = "",
                        title: str = "") -> Response:
    """MANUAL DE ENSAMBLAJE paso a paso (PDF multipágina): portada con la secuencia + 1 lámina por
    PASO (render 3D acumulado con las piezas nuevas resaltadas y lo previo en gris, cámara estable,
    lista de piezas/herraje + instrucción). La secuencia se deriva del log de comandos (orden de
    armado real) + familias de catálogo. `isolate` (CSV de ids) acota el manual a un SUB-ENSAMBLAJE
    (p. ej. una hoja) sin tocar el documento. Read-only."""
    from apolo.drawing import assembly_manual, sheets_to_pdf

    with STATE_LOCK:
        scene = S.doc.scene
        if isolate:
            ids = _expand_ids(isolate) or []  # acepta NOMBRES de grupo (V5.2)
            scene = {fid: S.doc.scene[fid] for fid in ids if fid in S.doc.scene}
            if not scene:
                raise HTTPException(status_code=400, detail="isolate: ningún id existe en la escena")
        try:
            pages = assembly_manual(scene, commands=S.doc.commands, project_name=title or S.doc.name,
                                    sheet=sheet, meta=_drawing_meta(), colors=_feature_colors(),
                                    size_px=size_px)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    fname = (title or S.doc.name or "manual").encode("ascii", "ignore").decode() or "manual"
    return Response(
        content=sheets_to_pdf(pages), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}-ensamblaje.pdf"'},
    )
