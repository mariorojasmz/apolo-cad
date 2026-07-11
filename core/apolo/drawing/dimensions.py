"""Motor de cotas profesional sobre el `SheetModel`.

Genera cotas REALES (líneas testigo + línea de cota + flechas + texto con tolerancia),
cotas **desde un datum** (línea base / posición), y **marcas de centro** en agujeros.
Opera en coordenadas de PAPEL (mm de lámina): el llamador ya proyectó mundo→vista→papel
con `world_to_view` + el transform de `_place_view`. Emite `Line(kind="dim"|"center")` y
`Label`, así que se exporta solo a SVG/PDF/DXF sin tocar los exportadores.
"""

from __future__ import annotations

import math

ARROW = 1.8   # largo de la flecha (mm de papel)
GAP = 1.0     # hueco entre la pieza y el arranque de la línea testigo
EXT = 1.5     # cuánto sobresale la testigo más allá de la línea de cota


def _arrow(model: "SheetModel", tip_x: float, tip_y: float, dx: float, dy: float) -> None:
    """Punta de flecha en (tip), abierta hacia (dx,dy) unitario (sentido de la línea de cota)."""
    from .sheet import Line

    n = math.hypot(dx, dy) or 1.0
    dx, dy = dx / n, dy / n
    ang = math.radians(20)
    for s in (1, -1):
        ca, sa = math.cos(s * ang), math.sin(s * ang)
        bx = tip_x + (dx * ca - dy * sa) * ARROW
        by = tip_y + (dx * sa + dy * ca) * ARROW
        model.lines.append(Line(tip_x, tip_y, bx, by, "dim"))


def _fmt(value: float, tol: float | None, name: str) -> str:
    txt = f"{value:g}" if abs(value - round(value)) > 1e-6 else f"{round(value):g}"
    if tol:
        txt += f" ±{tol:g}"
    return f"{name} {txt}".strip() if name else txt


def linear_dim(
    model: SheetModel,
    p1: tuple[float, float],
    p2: tuple[float, float],
    *,
    vertical: bool = False,
    offset: float = 8.0,
    value: float | None = None,
    tol: float | None = None,
    name: str = "",
) -> None:
    """Cota lineal entre dos puntos de papel `p1`,`p2` con líneas testigo, flechas y texto.
    `vertical=True` saca la cota a la izquierda (offset>0); horizontal, hacia abajo."""
    from .sheet import Label, Line

    x1, y1 = p1
    x2, y2 = p2
    if value is None:
        value = abs((y2 - y1) if vertical else (x2 - x1))
    if vertical:
        xd = min(x1, x2) - offset
        model.lines += [
            Line(x1 - GAP, y1, xd - EXT, y1, "dim"),
            Line(x2 - GAP, y2, xd - EXT, y2, "dim"),
            Line(xd, y1, xd, y2, "dim"),
        ]
        _arrow(model, xd, y1, 0, (y2 - y1))
        _arrow(model, xd, y2, 0, (y1 - y2))
        model.labels.append(Label(xd - 1.4, (y1 + y2) / 2, _fmt(value, tol, name), 2.8, rotation=90))
    else:
        yd = min(y1, y2) - offset
        model.lines += [
            Line(x1, y1 - GAP, x1, yd - EXT, "dim"),
            Line(x2, y2 - GAP, x2, yd - EXT, "dim"),
            Line(x1, yd, x2, yd, "dim"),
        ]
        _arrow(model, x1, yd, (x2 - x1), 0)
        _arrow(model, x2, yd, (x1 - x2), 0)
        model.labels.append(Label((x1 + x2) / 2, yd + 1.0, _fmt(value, tol, name), 2.8))


def baseline_dims(
    model: SheetModel,
    datum: float,
    entries: list[tuple[float, float, str]],
    *,
    vertical: bool = True,
    along: float = 0.0,
    offset_step: float = 6.0,
    base_offset: float = 8.0,
    tol: float | None = None,
) -> None:
    """Cotas desde un DATUM (línea base), apiladas. `datum` = coord del origen (papel) en el
    eje a cotar; cada entry = (coord_papel, valor_real, etiqueta). `along` = coord fija del
    otro eje (dónde arranca la testigo). vertical=True cota en Y desde abajo."""
    for i, (coord, value, label) in enumerate(entries):
        off = base_offset + i * offset_step
        if vertical:
            linear_dim(model, (along, datum), (along, coord), vertical=True,
                       offset=off, value=value, tol=tol, name=label)
        else:
            linear_dim(model, (datum, along), (coord, along), vertical=False,
                       offset=off, value=value, tol=tol, name=label)


def center_mark(model: "SheetModel", cx: float, cy: float, r: float, extend: float = 1.5) -> None:
    """Marca de centro (cruz de ejes) en un agujero/círculo de radio `r` (papel)."""
    from .sheet import Line

    a = r + extend
    model.lines += [
        Line(cx - a, cy, cx + a, cy, "center"),
        Line(cx, cy - a, cx, cy + a, "center"),
    ]


# ----------------------------------------------------------------- anotaciones / GD&T (Fase 5)
def notes_block(model: "SheetModel", x: float, y_top: float, lines: list[str],
                *, title: str = "NOTAS", size: float = 2.4) -> float:
    """Bloque de notas generales (título + lista numerada). Devuelve la `y` del borde inferior."""
    from .sheet import Label

    row = size * 1.9
    model.labels.append(Label(x, y_top, title, size + 0.8, anchor="start"))
    y = y_top - row * 1.2
    for i, ln in enumerate(lines[:8]):
        model.labels.append(Label(x, y, f"{i + 1}. {str(ln)[:60]}", size, anchor="start"))
        y -= row
    return y


def surface_finish(model: "SheetModel", x: float, y: float, ra: float | str = "", *, size: float = 4.0) -> None:
    """Símbolo de acabado superficial (✓) con valor Ra opcional, anclado en (x, y) de papel."""
    from .sheet import Label, Line

    s = size
    model.lines += [  # la "marca de visto" alargada
        Line(x, y, x + s * 0.32, y - s * 0.45, "visible"),
        Line(x + s * 0.32, y - s * 0.45, x + s * 0.95, y + s * 0.65, "visible"),
    ]
    if ra != "":
        model.labels.append(Label(x + s * 0.45, y + s * 0.95, f"Ra {ra}", size * 0.7, anchor="start"))


def datum_flag(model: "SheetModel", x: float, y: float, letter: str, *, size: float = 5.0) -> None:
    """Marca de datum: letra en recuadro + triángulo (símbolo de elemento de referencia)."""
    from .sheet import Label, Line

    s = size
    model.rect(x, y, s, s, "frame")
    model.labels.append(Label(x + s / 2, y + s * 0.28, str(letter)[:2], s * 0.6))
    cx = x + s / 2  # triángulo debajo del recuadro
    model.lines += [
        Line(cx, y, cx - s * 0.42, y - s * 0.72, "visible"),
        Line(cx, y, cx + s * 0.42, y - s * 0.72, "visible"),
        Line(cx - s * 0.42, y - s * 0.72, cx + s * 0.42, y - s * 0.72, "visible"),
    ]


def weld_symbol(
    model: "SheetModel", ax: float, ay: float, *,
    throat: float | None = None, length: float | None = None, count: int = 1,
    lead: tuple[float, float] = (9.0, 7.0), ref_len: float = 16.0, size: float = 3.0,
) -> None:
    """Símbolo de soldadura ISO 2553 anclado al punto de la unión `(ax, ay)` (papel).

    Dibuja: directriz con FLECHA al punto de unión + línea de referencia horizontal +
    triángulo de FILETE (lado flecha) sobre ella + texto «aX» (garganta) · «L»
    (longitud) · «×N típ.» (cordón típico agrupado). `throat=None` → sin cota numérica
    (cordón sin dimensionar; el llamador añade la nota general «ver memoria»).

    Compuesto de Line(kind="dim"|"visible")+Label → exporta a SVG/PDF/DXF sin tocar
    los exportadores (mismo patrón que `datum_flag`/`surface_finish`)."""
    from .sheet import Label, Line

    kx, ky = ax + lead[0], ay + lead[1]  # codo de la directriz
    model.lines.append(Line(ax, ay, kx, ky, "dim"))
    _arrow(model, ax, ay, kx - ax, ky - ay)  # flecha en el punto de unión
    model.lines.append(Line(kx, ky, kx + ref_len, ky, "dim"))  # línea de referencia
    t0, th = kx + 1.5, size * 1.25  # triángulo de filete junto al codo
    model.lines += [
        Line(t0, ky, t0, ky + th, "visible"),         # cateto vertical
        Line(t0, ky + th, t0 + size, ky, "visible"),  # hipotenusa
        Line(t0, ky, t0 + size, ky, "visible"),       # base
    ]
    parts: list[str] = []
    if throat:
        parts.append(f"a{throat:g}")
    if length:
        parts.append(f"{length:g}")
    if count > 1:
        parts.append(f"×{count} típ.")
    if parts:
        model.labels.append(Label(t0 + size + 1.2, ky + 0.4, " ".join(parts), size * 0.82, anchor="start"))


def feature_control_frame(model: "SheetModel", x: float, y: float, symbol: str, tol: str,
                          datums: tuple = (), *, size: float = 5.0) -> float:
    """Marco de control de feature GD&T: [símbolo | tolerancia | datum...]. Devuelve el ancho total."""
    from .sheet import Label

    h = size
    cells = [str(symbol), str(tol)] + [str(d) for d in datums]
    cx = x
    for k, c in enumerate(cells):
        w = h if k == 0 else max(h, len(c) * h * 0.55 + 2.2)
        model.rect(cx, y, w, h, "frame")
        model.labels.append(Label(cx + w / 2, y + h * 0.28, c, h * 0.52))
        cx += w
    return cx - x
