"""COTIZACIÓN del proyecto (Frente B): el entregable comercial.

PDF A4 multipágina: página de RESUMEN (totales por categoría, margen, impuesto,
PRECIO DE VENTA, ítem más costoso, notas comerciales) + páginas de DETALLE DE
PARTIDAS (el BOM costeado completo, paginado). Consume `library/costing.py`
(no calcula precios por su cuenta) y reusa `_table_sheet` (sheetset) +
`draw_title_block` + `sheets_to_pdf`.

Honestidad comercial: los precios de catálogo son REFERENCIALES y las piezas a
medida se estiman por peso×material×factor — las notas lo declaran siempre.
"""

from __future__ import annotations

from datetime import date

from .assembly_manual import SHEETS, _wrap
from .sheet import Label, Line, SheetModel
from .sheetset import _table_sheet
from .titleblock import draw_title_block

_ROWS_PER_PAGE = 18


def _money(x: float | None, currency: str) -> str:
    return f"{x:,.2f} {currency}" if x is not None else "—"


def _summary_page(W: float, H: float, *, project_name: str, requirements: dict,
                  totals: dict, margin_pct: float, tax_pct: float, currency: str,
                  n_rows: int, base_meta: dict) -> SheetModel:
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    m.labels.append(Label(16, H - 24, "COTIZACIÓN", 8.0, anchor="start"))
    m.labels.append(Label(16, H - 34, str(project_name)[:54], 4.6, anchor="start"))
    m.labels.append(Label(W - 16, H - 24, f"N° {base_meta.get('drawing_no', '—')}", 4.0, anchor="end"))
    m.labels.append(Label(W - 16, H - 31, str(base_meta.get("date", "")), 3.0, anchor="end"))
    m.lines.append(Line(14, H - 39, W - 14, H - 39, "frame"))

    # columna izquierda: alcance + desglose por categoría
    y = H - 48
    producto = requirements.get("producto")
    if producto:
        m.labels.append(Label(16, y, f"Alcance: {str(producto)[:50]}", 3.0, anchor="start"))
        y -= 6
    m.labels.append(Label(16, y, "DESGLOSE POR CATEGORÍA", 3.4, anchor="start"))
    y -= 6
    for cat, val in list(totals.get("por_categoria", {}).items())[:12]:
        m.labels.append(Label(18, y, str(cat)[:34], 2.7, anchor="start"))
        m.labels.append(Label(120, y, _money(val, currency), 2.7, anchor="end"))
        y -= 4.4
    top = totals.get("item_mas_costoso")
    if top:
        y -= 3
        m.labels.append(Label(16, y, "Ítem más costoso:", 3.0, anchor="start"))
        y -= 4.6
        m.labels.append(Label(18, y, f"{top['descripcion'][:44]} — {_money(top['costo_total_usd'], currency)}",
                              2.7, anchor="start"))

    # columna derecha: totales → precio de venta
    rx = W * 0.55
    yy = H - 48
    m.labels.append(Label(rx, yy, "RESUMEN ECONÓMICO", 3.4, anchor="start"))
    yy -= 7
    directo = totals.get("total_usd", 0.0)
    margen = directo * margin_pct / 100.0
    base = directo + margen
    impuesto = base * tax_pct / 100.0
    venta = base + impuesto
    filas = [
        ("Componentes de catálogo", totals.get("catalogo_usd")),
        ("Fabricación a medida", totals.get("fabricacion_usd")),
        ("Costo directo", directo),
        (f"Margen ({margin_pct:g}%)", margen),
    ]
    if tax_pct:
        filas.append((f"Impuesto ({tax_pct:g}%)", impuesto))
    for label, val in filas:
        m.labels.append(Label(rx, yy, label, 3.0, anchor="start"))
        m.labels.append(Label(W - 18, yy, _money(val, currency), 3.0, anchor="end"))
        yy -= 5.2
    m.lines.append(Line(rx, yy + 2, W - 18, yy + 2, "frame"))
    yy -= 2
    m.labels.append(Label(rx, yy, "PRECIO DE VENTA", 4.2, anchor="start"))
    m.labels.append(Label(W - 18, yy, _money(venta, currency), 4.2, anchor="end"))

    # notas comerciales (honestidad + condiciones)
    ny = 92
    m.labels.append(Label(16, ny, "NOTAS", 3.2, anchor="start"))
    ny -= 5
    notas = [
        "Precios de catálogo REFERENCIALES y fabricación estimada por peso×material×factor — "
        "confirmar con proveedores antes de comprometer.",
        f"Detalle de las {n_rows} partidas en las hojas siguientes (con la fuente de cada precio).",
        "No incluye transporte, instalación ni puesta en marcha, salvo pacto expreso.",
        "Validez de la oferta: 15 días calendario.",
    ]
    # wrap a 60 chars: las notas quedan a la izquierda de la tabla de revisiones
    # del cajetín (x ≥ 107) — sin solaparse aunque el proyecto tenga muchas revisiones
    idx = 1
    for nota in notas:
        for ln in _wrap(f"{idx}. {nota}", 60):
            m.labels.append(Label(18, ny, ln, 2.5, anchor="start"))
            ny -= 3.8
        idx += 1
    draw_title_block(m, {**base_meta, "sheet_no": 1})
    return m


def quotation_pages(scene: dict, *, project_name: str = "Sin título",
                    requirements: dict | None = None, margin_pct: float = 25.0,
                    tax_pct: float = 0.0, currency: str = "USD",
                    meta: dict | None = None, sheet: str = "A4") -> list[SheetModel]:
    """Cotización multipágina: [resumen económico + N hojas de detalle de partidas]."""
    from apolo.library.costing import scene_costing

    W, H = SHEETS.get(sheet, SHEETS["A4"])
    data = scene_costing(scene)
    rows, totals = data["rows"], data["totales"]

    detail = [
        [r["ref"], str(r["descripcion"])[:36], r["cantidad"],
         _money(r.get("costo_ud_usd"), ""), _money(r.get("costo_total_usd"), ""),
         str(r.get("costo_fuente", ""))[:34]]
        for r in rows
    ]
    n_detail_pages = max(1, -(-len(detail) // _ROWS_PER_PAGE))
    n_pages = 1 + n_detail_pages
    base_meta = {
        "project": project_name,
        "drawing_no": (meta or {}).get("drawing_no", "COT-001"),
        "scale": "—", "sheet": sheet, "material": "—", "finish": "—",
        "weight_kg": (meta or {}).get("weight_kg"), "tolerance": "—", "units": "mm",
        "drawn_by": (meta or {}).get("drawn_by", "Apolo · agente IA"),
        "checked_by": "", "approved_by": "",
        "date": (meta or {}).get("date", date.today().isoformat()),
        "revisions": (meta or {}).get("revisions", []),
        "n_sheets": n_pages,
    }
    pages = [_summary_page(W, H, project_name=project_name,
                           requirements=requirements or {}, totals=totals,
                           margin_pct=margin_pct, tax_pct=tax_pct, currency=currency,
                           n_rows=len(rows), base_meta=base_meta)]
    headers = ["Ref", "Descripción", "Cant", f"{currency}/ud", f"{currency} total", "Fuente del precio"]
    col_w = [26.0, 78.0, 12.0, 24.0, 28.0, 70.0]
    for k in range(n_detail_pages):
        chunk = detail[k * _ROWS_PER_PAGE:(k + 1) * _ROWS_PER_PAGE]
        pages.append(_table_sheet(
            f"DETALLE DE PARTIDAS ({k + 1}/{n_detail_pages})", headers, chunk, col_w,
            sheet=sheet, meta={**base_meta, "sheet_no": k + 2},
        ))
    return pages
