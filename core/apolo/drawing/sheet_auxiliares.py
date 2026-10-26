"""Auxiliares de la lámina: escala normalizada, colocar una vista, rótulos de agujeros (ajuste,
rosca, posición GD&T), cotas generales, rejilla de zonas y barra de escala. Sale de
`sheet.py` (plan partir-nucleo-congelado-ii, F4), que lo re-exporta por IDENTIDAD.
"""

from __future__ import annotations

from .dimensions import linear_dim
from .projection import ViewProjection
from .sheet_primitivas import MARGIN, STANDARD_SCALES, Arc, Label, Line, SheetModel


def _pick_scale(views: dict[str, ViewProjection], cell_w: float, cell_h: float) -> tuple[float, str]:
    needed = 1e-9
    for name in ("alzado", "planta", "lateral"):
        v = views.get(name)
        if v and v.width > 0:
            needed = max(needed, v.width / cell_w, v.height / cell_h)
    fit = 1.0 / needed
    for factor, label in STANDARD_SCALES:
        if factor <= fit:
            return factor, label
    return STANDARD_SCALES[-1]


def _place_view(model: SheetModel, view: ViewProjection, cx: float, cy: float, scale: float):
    """Dibuja la vista centrada en (cx, cy); devuelve (rectángulo en lámina, transform vista→lámina)."""
    vx = (view.bounds[0] + view.bounds[2]) / 2
    vy = (view.bounds[1] + view.bounds[3]) / 2

    def tx(p):
        return cx + (p[0] - vx) * scale, cy + (p[1] - vy) * scale

    for kind, polys in (("visible", view.visible), ("hidden", view.hidden)):
        for poly in polys:
            pts = [tx(p) for p in poly]
            for a, b in zip(pts, pts[1:]):
                model.lines.append(Line(a[0], a[1], b[0], b[1], kind))
    w, h = view.width * scale, view.height * scale
    return (cx - w / 2, cy - h / 2, w, h), tx


def _fit_for_dia(dia: float, hole_fits: dict[float, str] | None) -> str | None:
    """Ajuste ISO 286 del Ø detectado (matching por distancia mínima ≤ 0.11 —
    el diámetro de la vista viene redondeado a 0.1, nunca comparar por igualdad)."""
    if not hole_fits:
        return None
    best = min(hole_fits.items(), key=lambda kv: abs(kv[0] - dia), default=None)
    if best is not None and abs(best[0] - dia) <= 0.11:
        return best[1]
    return None


def _hole_callouts(
    model: SheetModel, view: ViewProjection, tx, scale: float,
    hole_fits: dict[float, str] | None = None,
    hole_threads: dict[float, str] | None = None,
    *, min_r_paper: float = 0.8, max_groups: int = 4,
    pos_tols: dict[float, float] | None = None,
    datum_letters: tuple = (),
) -> int:
    """Agrupa los círculos de la vista por diámetro y rotula 'n×Ød' con directriz.
    Con `hole_fits` {Ø_nominal → clase ISO 286} el rótulo incluye clase y límites:
    "4×Ø20 H7 (+0.021/0)". Con `hole_threads` {Ø_broca → designación M…} el rótulo
    es de ROSCA ("4×M8 - 6H (broca Ø6.8)") + arco cosmético ISO 6410 al Ø nominal
    (3/4 de vuelta, trazo fino); thread se evalúa ANTES que fit (si una broca
    coincide con un Ø liso mapeado, gana la rosca — mismo caveat que los fits).

    `min_r_paper` = radio mínimo en papel (mm) para rotular; en una lámina de taller
    por pieza se baja (V7.2 D1: nunca silenciar un barreno funcional de una pieza larga
    a escala pequeña). Un barreno con fit/rosca mapeada rotula SIEMPRE (piso 0.2).
    `max_groups` = nº de diámetros distintos rotulados (se sube en láminas por pieza).
    Devuelve el nº de MARCOS de control GD&T dibujados (V7.6 A): el llamador solo emite la
    leyenda de datums si hubo alguno — una leyenda sin marco confunde al taller."""
    n_frames = 0
    groups: dict[float, list[tuple[float, float, float]]] = {}
    for c in view.circles:
        groups.setdefault(round(2 * c[2], 1), []).append(c)
    for i, (dia, circles) in enumerate(sorted(groups.items())[:max_groups]):
        cx_v, cy_v, r = circles[0]
        n = len(circles)
        thread = _fit_for_dia(dia, hole_threads)  # mismo matching por distancia
        fit = None if thread else _fit_for_dia(dia, hole_fits)
        floor = 0.2 if (thread or fit) else min_r_paper  # los funcionales rotulan siempre
        if r * scale < floor:
            continue  # demasiado pequeño en papel para rotular (y no es funcional)
        sx, sy = tx((cx_v + r * 0.7071, cy_v + r * 0.7071))
        ex, ey = sx + 4.5 + i * 1.5, sy + 4.5 + i * 1.5
        model.lines.append(Line(sx, sy, ex, ey, "dim"))
        if thread:
            from apolo.library.engineering.threads import (
                format_thread_label, thread_spec,
            )

            text = format_thread_label(thread, n)
            r_nom = thread_spec(thread)["nominal_mm"] / 2.0 * scale
            if r_nom >= 0.9:  # cosmético ISO 6410 sobre CADA agujero del grupo
                for (hx, hy, _hr) in circles:
                    px, py = tx((hx, hy))
                    model.arcs.append(Arc(px, py, r_nom, 0.0, 270.0, "thread"))
        elif fit:
            from apolo.library.engineering.fits import format_fit_label

            base = format_fit_label(dia, fit)
            text = f"{n}×{base}" if n > 1 else base
        else:
            text = f"{n}×Ø{dia:g}" if n > 1 else f"Ø{dia:g}"
        model.labels.append(Label(ex + 0.8, ey, text, 2.8, anchor="start"))
        tw = len(text) * 2.8 * 0.55  # ancho aprox. del rótulo → lo que va a su derecha
        if fit:  # V7.2 C3: asiento ISO 286 = superficie mecanizada fina → Ra 1.6 TRAS el callout
            from .dimensions import surface_finish
            surface_finish(model, ex + 0.8 + tw + 1.5, ey - 0.8, "1.6", size=2.6)
        # V7.6 A: control de POSICIÓN bajo el callout — la tolerancia sale del presupuesto
        # de ensamble del perno que atraviesa el barreno (nunca de una tabla genérica) y
        # el marco de referencia, de las caras funcionales derivadas de las uniones
        t_pos = (pos_tols or {}).get(round(dia, 1))
        if t_pos and datum_letters:
            from .dimensions import feature_control_frame
            feature_control_frame(model, ex + 0.8, ey - 5.2, "posicion",
                                  f"Ø{t_pos:g} M", tuple(datum_letters), size=3.4)
            n_frames += 1
    return n_frames


def _dim_h_at(model: SheetModel, x1: float, x2: float, y: float, value: float, name: str = "") -> None:
    """Cota horizontal flotante a la altura y (para cotas por sólido), con flechas."""
    linear_dim(model, (x1, y), (x2, y), vertical=False, offset=0.0, value=value, name=name)


def _dim_h(model: SheetModel, x: float, y: float, w: float, value: float, offset: float = 8.0,
           tol: float | None = None) -> None:
    """Cota horizontal bajo el rectángulo (x, y, w), con líneas testigo y flechas.
    `tol` (V7.6 B) = media-tolerancia de la CADENA que la justifica → «1200 ±0.8»."""
    linear_dim(model, (x, y), (x + w, y), vertical=False, offset=offset, value=value, tol=tol)


def _dim_v(model: SheetModel, x: float, y: float, h: float, value: float, offset: float = 8.0,
           tol: float | None = None) -> None:
    """Cota vertical a la izquierda del rectángulo (x, y, h), con líneas testigo y flechas.
    `tol` (V7.6 B) = media-tolerancia de la CADENA que la justifica."""
    linear_dim(model, (x, y), (x, y + h), vertical=True, offset=offset, value=value, tol=tol)


def _zone_grid(model: SheetModel, width: float, height: float) -> None:
    """Rejilla de zonas de referencia: 1–8 (horizontal), A–D (vertical) en el marco."""
    cols, rows = 8, 4
    for i in range(cols):
        x = MARGIN + (width - 2 * MARGIN) * (i + 0.5) / cols
        model.labels += [Label(x, height - MARGIN + 1.6, str(i + 1), 2.6),
                         Label(x, MARGIN - 3.6, str(i + 1), 2.6)]
        if i:
            xx = MARGIN + (width - 2 * MARGIN) * i / cols
            model.lines += [Line(xx, height - MARGIN, xx, height - MARGIN - 2.5, "frame"),
                            Line(xx, MARGIN, xx, MARGIN + 2.5, "frame")]
    for j in range(rows):
        y = MARGIN + (height - 2 * MARGIN) * (j + 0.5) / rows
        letter = "ABCD"[j]
        model.labels += [Label(MARGIN - 3.6, y, letter, 2.6), Label(width - MARGIN + 2.2, y, letter, 2.6)]
        if j:
            yy = MARGIN + (height - 2 * MARGIN) * j / rows
            model.lines += [Line(MARGIN, yy, MARGIN + 2.5, yy, "frame"),
                            Line(width - MARGIN, yy, width - MARGIN - 2.5, yy, "frame")]


def _scale_bar(model: SheetModel, x: float, y: float, scale: float) -> None:
    """Barra de escala gráfica (regla de mm reales) — robusta a fotocopia/reescalado."""
    target = 40.0 / max(scale, 1e-9)
    nice = [10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000]
    div = min(nice, key=lambda d: abs(d * 5 - target))
    seg = div * scale
    model.lines.append(Line(x, y, x + 5 * seg, y, "frame"))
    for i in range(6):
        kx = x + i * seg
        model.lines.append(Line(kx, y, kx, y + 1.6, "frame"))
        model.labels.append(Label(kx, y - 2.0, f"{div * i:g}", 2.0))
    model.labels.append(Label(x, y + 2.2, "ESCALA (mm)", 2.0, anchor="start"))
