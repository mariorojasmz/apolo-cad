"""Juego de planos (sheet set): conjunto + 1 lámina por pieza + cédula (Fase E).

Compone varios `SheetModel` que un exportador multipágina (`sheets_to_pdf`) vuelca a un
PDF. La lámina por pieza AÍSLA cada tabla física (un sólido de la lista de corte) en una
escena sintética de un solo sólido y la acota. La cédula es una tabla con la lista de
corte. Reusa compose_sheet (vistas+cotas+cajetín), cut_list y el cajetín de la Fase C.
"""

from __future__ import annotations

from datetime import date

from .sheet import SheetModel, compose_sheet
from .titleblock import draw_title_block

SHEETS = {"A3": (420.0, 297.0), "A4": (297.0, 210.0)}


def _pick_solid(shape, t: float, w: float, l: float):
    """Sólido de `shape` cuyas dimensiones ordenadas == (t,w,l) (descompone compounds)."""
    try:
        cands = list(shape.solids()) or [shape]
    except Exception:
        cands = [shape]
    for s in cands:
        bb = s.bounding_box()
        d = sorted((round(bb.max.X - bb.min.X, 1), round(bb.max.Y - bb.min.Y, 1), round(bb.max.Z - bb.min.Z, 1)))
        if d == [t, w, l]:
            return s
    return cands[0]


def _table_sheet(title: str, headers: list[str], rows: list[list], col_w: list[float],
                 *, sheet: str, meta: dict) -> SheetModel:
    """Lámina con una tabla (cédula/lista de corte) + cajetín."""
    from .sheet import Label, Line

    W, H = SHEETS.get(sheet, SHEETS["A3"])
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    m.labels.append(Label(16, H - 22, title, 5.0, anchor="start"))

    x0, top = 16.0, H - 30.0
    row_h = 6.0
    tw = sum(col_w)
    n = min(len(rows), int((top - 60) / row_h))
    xcols = [x0]
    for w in col_w:
        xcols.append(xcols[-1] + w)
    m.rect(x0, top - (n + 1) * row_h, tw, (n + 1) * row_h)
    for cx in xcols[1:-1]:
        m.lines.append(Line(cx, top - (n + 1) * row_h, cx, top, "frame"))
    for j, head in enumerate(headers):
        m.labels.append(Label(xcols[j] + 1.5, top - row_h + 1.8, str(head), 2.8, anchor="start"))
    m.lines.append(Line(x0, top - row_h, x0 + tw, top - row_h, "frame"))
    for i, row in enumerate(rows[:n]):
        yr = top - (i + 2) * row_h + 1.8
        m.lines.append(Line(x0, top - (i + 2) * row_h, x0 + tw, top - (i + 2) * row_h, "frame"))
        for j, val in enumerate(row):
            m.labels.append(Label(xcols[j] + 1.5, yr, str(val)[:40], 2.6, anchor="start"))
    if len(rows) > n:
        m.labels.append(Label(x0, top - (n + 1) * row_h - 3.5, f"… y {len(rows) - n} más", 2.6, anchor="start"))
    draw_title_block(m, meta)
    return m


def sheet_set(scene: dict, project_name: str = "Sin título", *, template: str = "generico",
              meta: dict | None = None, sheet: str = "A3", shaded: bool = False,
              colors: dict | None = None,
              hole_fits: dict[float, str] | None = None,
              hole_threads: dict[float, str] | None = None,
              thread_rows: list[dict] | None = None) -> list[SheetModel]:
    """Juego de planos PRO (paquete de fabricación): [conjunto con DESPIECE+globos,
    1 lámina por pieza acotada, LISTA DE CORTE, CÉDULA DE HERRAJE]. `template` =
    carpinteria/weldment/chapa/generico (carpinteria/generico incluyen la cédula de
    herraje). `hole_threads` rotula roscas en las láminas; `thread_rows` (V5.7,
    de `_thread_schedule`) añade las roscas a la CÉDULA — y la fuerza aunque no
    haya herraje: la lista de machuelos es dato de compra/taller."""
    from apolo.commands.registry import Feature
    from apolo.library.cutlist import cut_list, cut_list_totals, hardware_schedule

    base = dict(meta or {})
    base.setdefault("date", date.today().isoformat())
    rows = cut_list(scene)
    hw = hardware_schedule(scene)
    want_hw = (bool(hw) and template in ("carpinteria", "generico")) or bool(thread_rows)
    n = 1 + len(rows) + 1 + (1 if want_hw else 0)
    pages: list[SheetModel] = []

    def page_meta(i):
        return {**base, "sheet_no": i, "n_sheets": n, "scale": "", "sheet": sheet}

    # cross-reference globo→hoja: cada pieza del despiece tiene su lámina de detalle (conjunto=1,
    # luego una por fila válida). El mismo orden que el bucle de abajo → la columna "Hoja" del
    # DESPIECE coincide con el nº de hoja real de cada pieza.
    sheet_refs: dict = {}
    _pg = 2
    for r in rows:
        if scene.get(r["_rep"]) is None:
            continue
        sheet_refs[r["_rep"]] = _pg
        _pg += 1

    # 1) CONJUNTO con DESPIECE (L×A×E) + globos + columna Hoja + CÉDULA DE HERRAJE + NOTAS DE
    # MONTAJE (auto-semilla del herraje) + (opcional) iso sombreada.
    # interface_dims NO va por defecto: en un conjunto con muchas piezas (p. ej. 86) el alzado
    # superpone decenas de círculos de herraje y el pitch auto-detectado satura; es una opción
    # para placas/bridas de interfaz simples (spec interface_dims=true).
    pages.append(compose_sheet(scene, cutlist=True, hardware=True, assembly_notes=[],
                               shaded=shaded, colors=colors, sheet_refs=sheet_refs,
                               hole_fits=hole_fits, hole_threads=hole_threads,
                               project_name=f"{project_name} · CONJUNTO", sheet=sheet, meta=page_meta(1)))
    # 2..) una lámina por pieza (sólido aislado, acotado overall + agujeros Ø)
    for r in rows:
        rep = scene.get(r["_rep"])
        if rep is None:
            continue
        solid = _pick_solid(rep.shape, r["espesor_mm"], r["ancho_mm"], r["largo_mm"])
        feat = Feature(id="P", name=r["nombre"], shape=solid, command_id="P")
        title = f"{r['nombre']} · {r['cantidad']}× · {r['material']}"
        pm = {**page_meta(len(pages) + 1), "material": r["material"]}
        # color de la pieza para su iso sombreada (= el color de su feature representante en el web)
        pc = {"P": colors.get(r["_rep"])} if colors else None
        pages.append(compose_sheet({"P": feat}, auto_dims=True, show_iso=shaded, shaded=shaded,
                                   colors=pc, sheet=sheet, project_name=title, meta=pm,
                                   hole_fits=hole_fits, hole_threads=hole_threads))
    # LISTA DE CORTE (solo lo cortable, L×An×Esp en orden de carpintería)
    def _dims_cell(r):
        base = f"{r['largo_mm']:g}×{r['ancho_mm']:g}×{r['espesor_mm']:g}"
        if r.get("corte") == "inglete":  # V5.8: el taller ve el ángulo por extremo
            angs = "/".join(f"{a:g}°" if a is not None else "0°"
                            for a in (r.get("angulo_1"), r.get("angulo_2")))
            return f"{base} ∠{angs}"
        return base

    cl_rows = [[r["material"], _dims_cell(r), r["cantidad"], r["nombre"]] for r in rows]
    totals = cut_list_totals(rows)
    fin = " · ".join(f"{k}:{v['area_m2']}m²" for k, v in totals.items()) or "—"
    pages.append(_table_sheet("LISTA DE CORTE", ["Material", "L×An×Esp (mm)", "Cant", "Pieza"],
                              cl_rows, [30, 48, 14, 78], sheet=sheet,
                              meta={**page_meta(len(pages) + 1), "finish": fin[:24]}))
    # CÉDULA DE HERRAJE (catálogo no cortable: bisagras/tornillos/correderas…) — página propia
    if want_hw:
        hw_rows = [[h["ref"], h["nombre"], h["categoria"], h["cantidad"], f"{h['peso_total_kg']:g} kg"]
                   for h in hw]
        for t in thread_rows or []:  # roscas (V5.7): operación de taller con norma
            piezas = ", ".join(t.get("piezas", [])[:2])
            hw_rows.append([t["designacion"],
                            f"Rosca interior {t['etiqueta']}", "rosca",
                            t["cantidad"], f"{piezas} · {t['norma']}"])
        pages.append(_table_sheet("CÉDULA DE HERRAJE", ["Ref", "Descripción", "Categoría", "Cant", "Peso"],
                                  hw_rows, [28, 60, 32, 14, 36], sheet=sheet,
                                  meta=page_meta(len(pages) + 1)))
    return pages
