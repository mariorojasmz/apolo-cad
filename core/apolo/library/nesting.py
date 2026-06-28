"""Nesting heurístico (optimización de corte) para minimizar desperdicio.

1D para barras/largueros/perfiles (First-Fit-Decreasing); 2D para tableros/vidrio
(estantería / shelf next-fit, ordenando por altura). Heurístico — sin dependencias —;
la optimalidad exacta (ILP) queda como follow-up. Produce además un `SheetModel` del
acomodo, exportable a SVG/DXF para CNC.
"""

from __future__ import annotations


def nest_1d(lengths: list[float], stock_len: float, kerf: float = 3.0) -> list[list[tuple[float, float]]]:
    """First-Fit-Decreasing: acomoda cortes `lengths` en barras de `stock_len`.
    Devuelve lista de barras; cada barra = lista de ``(offset, largo)`` sin solape."""
    items = sorted((round(float(l), 1) for l in lengths if 0 < l <= stock_len), reverse=True)
    bars: list[dict] = []
    for length in items:
        for bar in bars:
            extra = kerf if bar["cuts"] else 0.0
            if bar["used"] + extra + length <= stock_len + 1e-6:
                off = bar["used"] + extra
                bar["cuts"].append((off, length))
                bar["used"] = off + length
                break
        else:
            bars.append({"used": length, "cuts": [(0.0, length)]})
    return [b["cuts"] for b in bars]


def nest_2d(
    rects: list[tuple[float, float]], stock_w: float, stock_h: float, kerf: float = 3.0
) -> list[list[tuple[float, float, float, float]]]:
    """Estantería (shelf next-fit, alto descendente): acomoda rectángulos ``(w,h)`` en
    planchas ``stock_w×stock_h``. Devuelve lista de planchas; cada plancha = lista de
    ``(x, y, w, h)`` sin solape."""
    items = sorted(
        ((round(float(w), 1), round(float(h), 1)) for (w, h) in rects
         if 0 < w <= stock_w and 0 < h <= stock_h),
        key=lambda r: -r[1],
    )
    sheets: list[dict] = []
    cur: dict | None = None
    for (w, h) in items:
        if cur is None:
            cur = {"placed": [], "x": 0.0, "shelf_y": 0.0, "shelf_h": 0.0}
            sheets.append(cur)
        if cur["x"] + w <= stock_w + 1e-6:  # cabe en la estantería actual
            cur["placed"].append((cur["x"], cur["shelf_y"], w, h))
            cur["x"] += w + kerf
            cur["shelf_h"] = max(cur["shelf_h"], h)
            continue
        ny = cur["shelf_y"] + cur["shelf_h"] + kerf  # nueva estantería en la misma plancha
        if ny + h <= stock_h + 1e-6:
            cur["shelf_y"], cur["shelf_h"], cur["x"] = ny, h, w + kerf
            cur["placed"].append((0.0, ny, w, h))
            continue
        cur = {"placed": [(0.0, 0.0, w, h)], "x": w + kerf, "shelf_y": 0.0, "shelf_h": h}
        sheets.append(cur)  # nueva plancha
    return [s["placed"] for s in sheets]


def waste_2d(sheets: list, stock_w: float, stock_h: float) -> float:
    """% de desperdicio del conjunto de planchas usadas."""
    used = sum(w * h for s in sheets for (_, _, w, h) in s)
    total = len(sheets) * stock_w * stock_h
    return round(100.0 * (1 - used / total), 1) if total else 0.0


def waste_1d(bars: list, stock_len: float) -> float:
    used = sum(length for b in bars for (_, length) in b)
    total = len(bars) * stock_len
    return round(100.0 * (1 - used / total), 1) if total else 0.0


def _new_sheet(page):
    from apolo.drawing.sheet import Label, SheetModel

    m = SheetModel(page[0], page[1])
    m.rect(8, 8, page[0] - 16, page[1] - 16, "frame")
    return m, Label


def nesting_sheet_2d(sheets, stock_w, stock_h, *, title="NESTING", page=(420.0, 297.0)) -> "SheetModel":
    """Lámina del acomodo 2D: cada plancha apilada, con los recortes rotulados."""
    m, Label = _new_sheet(page)
    W, H = page
    m.labels.append(Label(12, H - 13, f"{title} · {len(sheets)} plancha(s) {stock_w:g}×{stock_h:g} mm · "
                                      f"desperdicio {waste_2d(sheets, stock_w, stock_h)}%", 3.6, anchor="start"))
    if not sheets:
        return m
    ax, ay, aw, ah = 12, 12, W - 24, H - 28
    cell_h = ah / len(sheets)
    scale = min(aw / stock_w, (cell_h - 9) / stock_h)
    for i, placed in enumerate(sheets):
        ox = ax
        oy = ay + (len(sheets) - 1 - i) * cell_h
        m.rect(ox, oy, stock_w * scale, stock_h * scale, "frame")
        m.labels.append(Label(ox, oy + stock_h * scale + 1.5, f"Plancha {i + 1}", 2.8, anchor="start"))
        for (x, y, w, h) in placed:
            rx, ry = ox + x * scale, oy + y * scale
            m.rect(rx, ry, w * scale, h * scale, "visible")
            m.labels.append(Label(rx + w * scale / 2, ry + h * scale / 2 - 1.0,
                                  f"{w:g}×{h:g}", max(1.4, min(2.6, w * scale / 14))))
    return m


def nesting_sheet_1d(bars, stock_len, *, title="NESTING (barras)", page=(420.0, 297.0)) -> "SheetModel":
    """Lámina del acomodo 1D: cada barra una fila, con los cortes rotulados."""
    m, Label = _new_sheet(page)
    W, H = page
    m.labels.append(Label(12, H - 13, f"{title} · {len(bars)} barra(s) L={stock_len:g} mm · "
                                      f"desperdicio {waste_1d(bars, stock_len)}%", 3.6, anchor="start"))
    if not bars:
        return m
    ax, ay, aw, ah = 12, 12, W - 24, H - 28
    scale = aw / stock_len
    row_h = min(16.0, (ah) / len(bars))
    for i, cuts in enumerate(bars):
        oy = ay + (len(bars) - 1 - i) * row_h
        m.rect(ax, oy, stock_len * scale, row_h - 4, "frame")
        m.labels.append(Label(ax - 1.5, oy + (row_h - 4) / 2, str(i + 1), 2.6, anchor="end"))
        for (off, length) in cuts:
            rx = ax + off * scale
            m.rect(rx, oy, length * scale, row_h - 4, "visible")
            m.labels.append(Label(rx + length * scale / 2, oy + (row_h - 4) / 2 - 1.0, f"{length:g}", 2.2))
    return m
