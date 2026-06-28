"""Cajetín profesional + bloque de revisiones para la lámina (Fase C).

Dibuja un cajetín de ingeniería completo (nº de plano, material, acabado, tolerancia
general, escala, hoja N/M, símbolo de diedro, dibujó/revisó/aprobó, peso, logo) y una
tabla de revisiones, escribiendo `Line`/`Label`/`Circle` en el `SheetModel`. Es una capa
de presentación: no calcula nada del modelo (recibe `fields` ya resueltos).
"""

from __future__ import annotations

TITLE_W, TITLE_H = 180.0, 40.0     # cajetín
REV_ROW_H = 4.5
REV_W = 90.0


def _txt(model, x, y, s, val, anchor="start"):
    from .sheet import Label

    model.labels.append(Label(x, y, str(val), s, anchor=anchor))


def projection_symbol(model, x: float, y: float, s: float = 7.0, first_angle: bool = True) -> None:
    """Símbolo de proyección en primer diedro (cono truncado: trapecio + 2 círculos)."""
    from .sheet import Circle, Line

    # trapecio (perfil del cono)
    model.lines += [
        Line(x, y, x + s, y + s * 0.32, "frame"),
        Line(x, y + s, x + s, y + s * 0.68, "frame"),
        Line(x, y, x, y + s, "frame"),
        Line(x + s, y + s * 0.32, x + s, y + s * 0.68, "frame"),
    ]
    # vista frontal (2 círculos concéntricos) a la derecha (1er diedro)
    cx = x + s * 1.9
    model.circles.append(Circle(cx, y + s * 0.5, s * 0.5, "dim"))
    model.circles.append(Circle(cx, y + s * 0.5, s * 0.22, "dim"))


def draw_title_block(model, fields: dict) -> None:
    """Cajetín 180×40 mm abajo-derecha + tabla de revisiones encima. `fields`:
    project, drawing_no, scale, sheet, sheet_no, n_sheets, material, finish, tolerance,
    weight_kg, drawn_by, checked_by, approved_by, date, units, revisions[{rev,date,note}]."""
    from .sheet import Line

    W = model.width
    x0 = W - 10.0 - TITLE_W
    y0 = 10.0
    f = fields

    # --- tabla de revisiones (encima del cajetín, alineada a la derecha) ---
    revs = list(f.get("revisions") or [])[-6:]
    if revs:
        rx = W - 10.0 - REV_W
        ry = y0 + TITLE_H + 1.0
        n = len(revs)
        model.rect(rx, ry, REV_W, (n + 1) * REV_ROW_H)
        cols = [rx, rx + 12, rx + 34, rx + REV_W]
        for cx in cols[1:-1]:
            model.lines.append(Line(cx, ry, cx, ry + (n + 1) * REV_ROW_H, "frame"))
        _txt(model, rx + 1, ry + n * REV_ROW_H + 1.4, 2.4, "Rev")
        _txt(model, cols[1] + 1, ry + n * REV_ROW_H + 1.4, 2.4, "Fecha")
        _txt(model, cols[2] + 1, ry + n * REV_ROW_H + 1.4, 2.4, "Descripción")
        model.lines.append(Line(rx, ry + n * REV_ROW_H, rx + REV_W, ry + n * REV_ROW_H, "frame"))
        for i, r in enumerate(revs):
            yy = ry + (n - 1 - i) * REV_ROW_H + 1.3
            model.lines.append(Line(rx, ry + (n - i) * REV_ROW_H, rx + REV_W, ry + (n - i) * REV_ROW_H, "frame"))
            _txt(model, rx + 1, yy, 2.2, r.get("rev", i + 1))
            _txt(model, cols[1] + 1, yy, 2.2, str(r.get("date", ""))[:10])
            _txt(model, cols[2] + 1, yy, 2.2, str(r.get("note", r.get("desc", "")))[:26])

    # --- cajetín ---
    model.rect(x0, y0, TITLE_W, TITLE_H)
    # filas horizontales
    rows = [y0 + TITLE_H * k for k in (0.25, 0.5, 0.75)]
    for ry in rows:
        model.lines.append(Line(x0, ry, x0 + TITLE_W, ry, "frame"))
    # columnas verticales del tercio inferior (material/acabado/peso/tol/escala/hoja)
    c1 = x0 + TITLE_W * 0.30
    c2 = x0 + TITLE_W * 0.55
    c3 = x0 + TITLE_W * 0.78
    for cx in (c1, c2, c3):
        model.lines.append(Line(cx, y0, cx, y0 + TITLE_H * 0.5, "frame"))
    # columna del bloque dibujó/revisó/aprobó (mitad superior izq)
    cdiv = x0 + TITLE_W * 0.62
    model.lines.append(Line(cdiv, y0 + TITLE_H * 0.5, cdiv, y0 + TITLE_H, "frame"))

    # fila 1 (arriba): título + nº de plano
    _txt(model, x0 + 2, y0 + TITLE_H * 0.84, 4.0, str(f.get("project", "Sin título"))[:34])
    _txt(model, x0 + TITLE_W - 2, y0 + TITLE_H * 0.84, 3.4, f"Plano {f.get('drawing_no', '—')}", anchor="end")
    # fila 2: dibujó/revisó/aprobó | empresa + símbolo de diedro
    _txt(model, x0 + 2, y0 + TITLE_H * 0.66, 2.3, f"Dib. {f.get('drawn_by', '')}  {str(f.get('date', ''))[:10]}")
    _txt(model, x0 + 2, y0 + TITLE_H * 0.56, 2.3, f"Rev. {f.get('checked_by', '')}   Apr. {f.get('approved_by', '')}")
    _txt(model, cdiv + 2, y0 + TITLE_H * 0.66, 2.8, "Genix Apolo CAD")
    projection_symbol(model, cdiv + 3, y0 + TITLE_H * 0.52, 5.5)
    # tercio inferior: material | acabado/peso | tol/unidades | escala/hoja
    _txt(model, x0 + 2, y0 + TITLE_H * 0.34, 2.3, "Material")
    _txt(model, x0 + 2, y0 + TITLE_H * 0.10, 3.0, str(f.get("material", "—"))[:18])
    _txt(model, c1 + 2, y0 + TITLE_H * 0.34, 2.3, "Acabado / Peso")
    _txt(model, c1 + 2, y0 + TITLE_H * 0.10, 2.6, f"{f.get('finish', '—')} · {f.get('weight_kg', 0)} kg")
    _txt(model, c2 + 2, y0 + TITLE_H * 0.34, 2.3, "Tol. gral / Unid.")
    _txt(model, c2 + 2, y0 + TITLE_H * 0.10, 2.6, f"{f.get('tolerance', '±0.5')} · {f.get('units', 'mm')}")
    _txt(model, c3 + 2, y0 + TITLE_H * 0.34, 2.3, "Escala / Hoja")
    _txt(model, c3 + 2, y0 + TITLE_H * 0.10, 2.6,
         f"{f.get('scale', '')} · {f.get('sheet_no', 1)}/{f.get('n_sheets', 1)} {f.get('sheet', '')}")
