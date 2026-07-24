"""Lámina de INSTALACIÓN e interfaz (V7.6 fase C).

El plano que el CLIENTE lleva a la obra civil ANTES de que llegue la máquina: dónde van
los anclajes (huella acotada desde el origen de máquina), cuánto carga cada apoyo, qué
holgura hay que dejar para el servicio y qué suministro hace falta. Un despacho de máquina
entrega GA + láminas de pieza + cédula + lista de corte; esta hoja es la que casi nunca
acompaña al paquete y la que el constructor pide primero.

Se compone con los mismos primitivos que el resto del sistema (`SheetModel` + `Label`/
`Line` + `draw_title_block`), así que exporta a SVG/PDF/DXF sin tocar los exportadores.
"""

from __future__ import annotations

from .dimensions import center_mark, linear_dim, notes_block
from .sheet import SHEETS, Label, Line, SheetModel
from .titleblock import draw_title_block


def _place(model: SheetModel, view, cx: float, cy: float, scale: float):
    """Dibuja la proyección `view` centrada en (cx, cy) a `scale`. Devuelve (rect, tx)
    igual que el compositor principal: rect = caja en papel, tx = mm-mundo → mm-papel."""
    minx, miny, maxx, maxy = view.bounds
    w, h = (maxx - minx) * scale, (maxy - miny) * scale
    x0, y0 = cx - w / 2, cy - h / 2

    def tx(p):
        return (x0 + (p[0] - minx) * scale, y0 + (p[1] - miny) * scale)

    for poly in view.visible:
        for a, b in zip(poly, poly[1:]):
            (ax, ay), (bx, by) = tx(a), tx(b)
            model.lines.append(Line(ax, ay, bx, by, "visible"))
    return (x0, y0, w, h), tx


def installation_sheet(scene: dict, data: dict, *, project_name: str = "Sin título",
                       sheet: str = "A3", meta: dict | None = None) -> SheetModel:
    """Lámina de instalación de `scene` (las piezas ANCLADAS al piso) con los datos de
    `data` (los arma la capa API + `engineering/installation.py`).

    Contenido: PLANTA de la huella con los ejes de anclaje acotados y una marca por
    apoyo · tabla DATOS DE INSTALACIÓN (masa, carga por apoyo con su hipótesis, huella,
    alturas de interfaz, holguras de servicio, suministro) · notas de obra."""
    from apolo.library.engineering.installation import installation_rows

    from .projection import project_views

    W, H = SHEETS.get(sheet, SHEETS["A3"])
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    m.labels.append(Label(16, H - 22, "PLANTA DE INSTALACIÓN Y ANCLAJE", 5.0, anchor="start"))

    anclaje = data.get("anclaje") or {}
    apoyos = anclaje.get("apoyos") or []

    # --- PLANTA de la huella (mitad izquierda), a escala que quepa
    if scene:
        view = project_views(scene, ["planta"]).get("planta")
        if view is not None and view.width > 0 and view.height > 0:
            avail_w, avail_h = W * 0.50 - 40, H - 120
            scale = min(avail_w / view.width, avail_h / view.height, 1.0)
            rect, tx = _place(m, view, W * 0.27, H * 0.55, scale)
            rx, ry, rw, rh = rect
            # marca de centro en cada apoyo + su etiqueta de carga
            for i, a in enumerate(apoyos):
                px, py = tx((a["x_mm"], a["y_mm"]))
                center_mark(m, px, py, 3.0)
                m.labels.append(Label(px + 3.2, py + 1.6, f"{a['carga_kg']:g} kg", 2.4,
                                      anchor="start"))
            # cotas de la huella: entre ejes de anclaje extremos (lo que replantea la obra)
            if len(apoyos) >= 2:
                xs = sorted({round(a["x_mm"], 1) for a in apoyos})
                ys = sorted({round(a["y_mm"], 1) for a in apoyos})
                if len(xs) >= 2:
                    p1, p2 = tx((xs[0], ys[0])), tx((xs[-1], ys[0]))
                    linear_dim(m, (p1[0], ry), (p2[0], ry), vertical=False, offset=12.0,
                               value=round(xs[-1] - xs[0], 1))
                if len(ys) >= 2:
                    q1, q2 = tx((xs[0], ys[0])), tx((xs[0], ys[-1]))
                    linear_dim(m, (rx, q1[1]), (rx, q2[1]), vertical=True, offset=12.0,
                               value=round(ys[-1] - ys[0], 1))
            m.labels.append(Label(rx + rw / 2, ry - 20.0, "PLANTA (huella de anclaje)", 3.6))

    # --- tabla DATOS DE INSTALACIÓN (mitad derecha)
    rows = installation_rows(data)
    x0, top = W * 0.55, H - 40.0
    col_w = [58.0, 34.0, 46.0]
    row_h = 5.6
    n = min(len(rows), int((top - 70) / row_h))
    m.labels.append(Label(x0, top + 4.0, "DATOS DE INSTALACIÓN", 3.6, anchor="start"))
    xcols = [x0]
    for w in col_w:
        xcols.append(xcols[-1] + w)
    if n:
        m.rect(x0, top - n * row_h, sum(col_w), n * row_h)
        for cx in xcols[1:-1]:
            m.lines.append(Line(cx, top - n * row_h, cx, top, "frame"))
        for i, row in enumerate(rows[:n]):
            yr = top - (i + 1) * row_h + 1.7
            m.lines.append(Line(x0, top - (i + 1) * row_h, x0 + sum(col_w),
                                top - (i + 1) * row_h, "frame"))
            for j, val in enumerate(row):
                m.labels.append(Label(xcols[j] + 1.4, yr, str(val)[:34], 2.5, anchor="start"))

    # --- notas de obra: la hipótesis del reparto va SIEMPRE (nunca implícita)
    notas = []
    if anclaje.get("hipotesis"):
        notas.append(f"Carga por apoyo: {anclaje['hipotesis']}.")
    if anclaje.get("hay_traccion"):
        notas.append("Algún apoyo trabaja a TRACCIÓN: el anclaje debe resistir arranque.")
    notas += list(data.get("notas") or [])
    if notas:
        notes_block(m, x0, top - n * row_h - 10.0, notas, title="NOTAS DE INSTALACIÓN")

    base = dict(meta or {})
    base.setdefault("material", "—")
    draw_title_block(m, {**base, "project": f"{project_name} · INSTALACIÓN",
                         "scale": "", "sheet": sheet, "units": "mm"})
    return m
