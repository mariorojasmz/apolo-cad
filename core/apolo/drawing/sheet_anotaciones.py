"""Anotaciones de la lámina: tablas con globos (BOM, DESPIECE, cédula de herraje), la semilla
de notas de montaje y los símbolos de soldadura ISO 2553 del conjunto. Sale de `sheet.py`
(plan partir-nucleo-congelado-ii, F4), que lo re-exporta por IDENTIDAD.
"""

from __future__ import annotations

from .dimensions import weld_symbol
from .projection import world_to_view
from .sheet_primitivas import Circle, Label, Line, SheetModel
from .texto_medido import celda_fila


def _draw_table_with_balloons(
    model: SheetModel, *, ax0: float, aw: float, ah: float, ay0: float,
    placed: dict, scene: dict, center3: tuple, title: str,
    columns: list[tuple[str, float]], rows: list[dict], cell_values,
    planta_dim_rows: int = 0, anchor_view: str = "planta", top_y: float | None = None,
    max_rows: int = 12,
) -> float:
    """Tabla (BOM/DESPIECE/CÉDULA) en el cuadrante del perfil + globos numerados enlazados a
    `anchor_view`. `columns`=[(cabecera, ancho)...]; `cell_values(i, row)` devuelve la tupla de
    celdas, ENTERAS: cada una se mide en su columna (un renglón, o dos más chicos; «…» de último
    recurso) y la fila no crece. `top_y` = borde superior (para apilar tablas); devuelve el borde INFERIOR de la tabla.
    Reutilizado por `bom` (anchor planta), `cutlist` (anchor alzado) y la cédula de herraje (sin globos)."""
    headers = [h for h, _ in columns]
    col_w = [w for _, w in columns]
    tw = sum(col_w)
    tx0b = ax0 + aw * 0.52
    tyb = (ay0 + ah - 6) if top_y is None else top_y
    row_h = 6.0
    n_shown = min(len(rows), max_rows)
    bottom = tyb - (n_shown + 1) * row_h
    model.rect(tx0b, bottom, tw, (n_shown + 1) * row_h)
    xcols = [tx0b]
    for w in col_w[:-1]:
        xcols.append(xcols[-1] + w)
        model.lines.append(Line(xcols[-1], tyb - (n_shown + 1) * row_h, xcols[-1], tyb, "frame"))
    for j, head in enumerate(headers):
        model.labels.append(Label(xcols[j] + 1.5, tyb - row_h + 1.8, head, 2.8, anchor="start"))
    model.lines.append(Line(tx0b, tyb - row_h, tx0b + tw, tyb - row_h, "frame"))
    for i, row in enumerate(rows[:n_shown]):
        yr = tyb - (i + 2) * row_h + 1.8
        model.lines.append(Line(tx0b, tyb - (i + 2) * row_h, tx0b + tw, tyb - (i + 2) * row_h, "frame"))
        for j, val in enumerate(cell_values(i, row)):  # medida en su celda (V8.9, cortes fijos)
            celda_fila(model, xcols[j] + 1.5, yr, col_w[j] - 3.0, 2.6, val,
                       fila_abajo=tyb - (i + 2) * row_h, alto_fila=row_h)
    if len(rows) > n_shown:
        model.labels.append(Label(tx0b, tyb - (n_shown + 1) * row_h - 3.5, f"… y {len(rows) - n_shown} más", 2.6, anchor="start"))
    model.labels.append(Label(tx0b, tyb + 2.2, title, 3.2, anchor="start"))

    # globos: enlazan cada fila con la pieza representante en la vista `anchor_view`
    if anchor_view not in placed:
        return bottom
    (rx, ry, rw, rh), ptx = placed[anchor_view]
    reps = []
    for i, row in enumerate(rows[:n_shown]):
        feat = scene.get(row.get("_rep", ""))
        if feat is None:
            continue
        bb = feat.shape.bounding_box()
        wc = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
        ax_, ay_ = ptx(world_to_view(anchor_view, wc, center3))
        reps.append((i, ax_, ay_))
    n = len(reps)
    if anchor_view == "planta":
        # planta (ancha y baja): FILA ordenada por X, por encima de la planta (sobre las cotas)
        reps.sort(key=lambda r: r[1])
        row_w = max(rw, n * 7.0)
        x0 = rx + rw / 2 - row_w / 2
        ring_y = ry + rh + 8.0 + planta_dim_rows * 6.5
        for slot, (i, ax_, ay_) in enumerate(reps):
            bx_ = x0 + row_w * (slot + 0.5) / max(n, 1)
            by_ = ring_y + (slot % 2) * 7.0
            model.lines.append(Line(ax_, ay_, bx_, by_ - 3.2, "dim"))
            model.circles.append(Circle(bx_, by_, 3.2, "globo"))
            model.labels.append(Label(bx_, by_ - 1.1, str(i + 1), 3.0))
    else:
        # alzado (alta y angosta): COLUMNA ordenada por Z, a la derecha de la vista
        reps.sort(key=lambda r: -r[2])
        col_h = max(rh, n * 7.0)
        y0 = ry + rh / 2 + col_h / 2
        ring_x = rx + rw + 9.0
        for slot, (i, ax_, ay_) in enumerate(reps):
            by_ = y0 - col_h * (slot + 0.5) / max(n, 1)
            bx_ = ring_x + (slot % 2) * 7.0
            model.lines.append(Line(ax_, ay_, bx_ - 3.2, by_, "dim"))
            model.circles.append(Circle(bx_, by_, 3.2, "globo"))
            model.labels.append(Label(bx_, by_ - 1.1, str(i + 1), 3.0))
    return bottom


def _assembly_notes_auto(scene: dict) -> list[str]:
    """Semilla de NOTAS DE MONTAJE derivada del herraje del modelo. NO inventa pares de apriete
    (el catálogo no los lleva): cita la norma cuando existe y remite a la explosionada para la
    secuencia. Devuelve [] si no hay herraje (entonces el bloque no se dibuja)."""
    from apolo.library.cutlist import hardware_schedule

    out: list[str] = []
    for r in hardware_schedule(scene)[:6]:
        norma = f" ({r['norma']})" if r.get("norma") else ""
        out.append(f"Apretar {r['cantidad']}× {r['ref']}{norma} según par de norma.")
    if out:
        out.append("Secuencia de montaje: ver vista explosionada / despiece.")
    return out


def _bbox_vol(feat) -> float:
    """Volumen del bbox de una feature (para elegir la pieza representante de una lámina)."""
    try:
        bb = feat.shape.bounding_box()
        return (bb.max.X - bb.min.X) * (bb.max.Y - bb.min.Y) * (bb.max.Z - bb.min.Z)
    except Exception:
        return 0.0


def _weld_anchor(fa, fb) -> tuple[float, float, float]:
    """Punto aproximado del cordón entre dos piezas: centro del solape de sus bboxes;
    si no solapan en un eje, punto medio de los centros de ese eje."""
    ba, bb = fa.shape.bounding_box(), fb.shape.bounding_box()

    def mid(a0, a1, b0, b1):
        lo, hi = max(a0, b0), min(a1, b1)
        return (lo + hi) / 2 if lo <= hi else ((a0 + a1) + (b0 + b1)) / 4

    return (
        mid(ba.min.X, ba.max.X, bb.min.X, bb.max.X),
        mid(ba.min.Y, ba.max.Y, bb.min.Y, bb.max.Y),
        mid(ba.min.Z, ba.max.Z, bb.min.Z, bb.max.Z),
    )


def _place_weld_symbols(model, fasteners, scene, placed, center3, *, max_symbols=6):
    """Símbolos de soldadura ISO 2553 en la vista de CONJUNTO (alzado). Agrupa los
    cordones tipo 'soldadura' por (garganta, longitud) → UN símbolo «típ. ×N» por grupo
    anclado al centro del solape del par representante. Solo dibuja pares con AMBAS
    piezas en la escena mostrada → NO-OP en las láminas por pieza (a/b no coinciden con
    el id sintético). Cap `max_symbols`; el resto lo declara el llamador en una nota.
    Devuelve (n_grupos_dibujados, n_grupos_total, hay_sin_cota, n_cordones)."""
    if not fasteners or "alzado" not in placed:
        return (0, 0, False, 0)
    welds = [f for f in fasteners.values()
             if f.get("kind") == "soldadura" and f.get("a") in scene and f.get("b") in scene]
    if not welds:
        return (0, 0, False, 0)
    (_rect, tx) = placed["alzado"]
    groups: dict[tuple, list] = {}
    for f in welds:
        groups.setdefault((f.get("throat_mm"), f.get("length_mm")), []).append(f)
    # OJO: (throat, length) puede traer None (cordón sin dimensionar) — el sort key usa
    # centinelas (None al final entre empates) para no comparar None < float (TypeError).
    ordered = sorted(groups.items(), key=lambda kv: (
        -len(kv[1]), kv[0][0] is None, kv[0][0] or 0.0, kv[0][1] is None, kv[0][1] or 0.0))
    hay_sin_cota = any(k[0] is None for k in groups)
    for i, ((throat, length), members) in enumerate(ordered[:max_symbols]):
        rep = members[0]
        try:
            pt = _weld_anchor(scene[rep["a"]], scene[rep["b"]])
            wx, wy = tx(world_to_view("alzado", pt, center3))
        except Exception:
            continue
        # abanica la directriz en diagonal (una posición POR símbolo, i<max_symbols=6)
        # para separar símbolos con anclas co-ubicadas; con %4 los pares (0,4) y (1,5)
        # compartían offset y se solapaban exactamente
        lead = (9.0 + i * 5.0, 7.0 + i * 5.5)
        weld_symbol(model, wx, wy, throat=throat, length=length, count=len(members), lead=lead)
    return (min(len(groups), max_symbols), len(groups), hay_sin_cota, len(welds))
