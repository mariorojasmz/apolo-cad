"""Composición de la lámina: disposición en primer diedro, escala normalizada,
cotas generales y cajetín.

El modelo de lámina (líneas + rótulos en mm, origen abajo-izquierda, Y hacia
arriba) es la fuente común de los exportadores SVG, PDF y DXF.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .dimensions import baseline_dims, center_mark, linear_dim, notes_block, weld_symbol
from .projection import (
    ViewProjection,
    detail_view,
    project_views,
    real_dims,
    section_projection,
    view_center,
    world_to_view,
)

SHEETS = {
    "A0": (1189.0, 841.0), "A1": (841.0, 594.0), "A2": (594.0, 420.0),
    "A3": (420.0, 297.0), "A4": (297.0, 210.0),
}
MARGIN = 10.0
TITLE_W, TITLE_H = 160.0, 26.0
CELL_PAD = 17.0  # espacio reservado para cotas alrededor de cada vista
# escalas normalizadas (ISO 5455: preferidas + intermedias permitidas 1:2.5/1:4/1:25/1:40)
# en orden DESCENDENTE de factor → _pick_scale toma la MAYOR que entra en la celda
STANDARD_SCALES = [
    (1.0, "1:1"), (0.5, "1:2"), (0.4, "1:2.5"), (0.25, "1:4"), (0.2, "1:5"),
    (0.1, "1:10"), (0.05, "1:20"), (0.04, "1:25"), (0.025, "1:40"), (0.02, "1:50"),
    (0.01, "1:100"), (0.005, "1:200"),
]

# qué dimensiones reales (bbox 3D) acota cada vista: (horizontal, vertical)
VIEW_DIMS = {"alzado": ("X", "Z"), "planta": ("X", "Y"), "lateral": ("Y", "Z")}
VIEW_TITLES = {"alzado": "ALZADO", "planta": "PLANTA", "lateral": "PERFIL", "iso": "ISOMÉTRICA"}


@dataclass
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    kind: str  # visible | hidden | frame | dim


@dataclass
class Label:
    x: float
    y: float
    text: str
    size: float = 3.2
    anchor: str = "middle"  # start | middle | end
    rotation: float = 0.0


@dataclass
class Circle:
    x: float
    y: float
    r: float
    kind: str  # globo | dim


@dataclass
class Arc:
    """Arco de circunferencia (grados CCW desde +X). Hoy lo usa el cosmético de
    ROSCA (ISO 6410: 3/4 de vuelta en trazo fino al Ø nominal, capa DXF ROSCA)."""

    x: float
    y: float
    r: float
    a1: float
    a2: float
    kind: str = "thread"


@dataclass
class Polygon:
    rings: list[list[tuple[float, float]]]  # anillo 0 = contorno; resto = agujeros
    kind: str = "corte"
    material: str = ""  # para el rayado de sección por material (madera/vidrio/acero)


@dataclass
class Image:
    """Imagen raster (PNG) embebida — p. ej. un render 3D sombreado a color. Coords mm,
    origen abajo-izquierda (como el resto). Solo la sirven SVG/PDF; DXF (línea) la omite."""
    x: float
    y: float
    w: float
    h: float
    png: bytes


@dataclass
class SheetModel:
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    circles: list[Circle] = field(default_factory=list)
    arcs: list[Arc] = field(default_factory=list)
    polygons: list[Polygon] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    def rect(self, x: float, y: float, w: float, h: float, kind: str = "frame") -> None:
        self.lines += [
            Line(x, y, x + w, y, kind), Line(x + w, y, x + w, y + h, kind),
            Line(x + w, y + h, x, y + h, kind), Line(x, y + h, x, y, kind),
        ]


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
) -> None:
    """Agrupa los círculos de la vista por diámetro y rotula 'n×Ød' con directriz.
    Con `hole_fits` {Ø_nominal → clase ISO 286} el rótulo incluye clase y límites:
    "4×Ø20 H7 (+0.021/0)". Con `hole_threads` {Ø_broca → designación M…} el rótulo
    es de ROSCA ("4×M8 - 6H (broca Ø6.8)") + arco cosmético ISO 6410 al Ø nominal
    (3/4 de vuelta, trazo fino); thread se evalúa ANTES que fit (si una broca
    coincide con un Ø liso mapeado, gana la rosca — mismo caveat que los fits).

    `min_r_paper` = radio mínimo en papel (mm) para rotular; en una lámina de taller
    por pieza se baja (V7.2 D1: nunca silenciar un barreno funcional de una pieza larga
    a escala pequeña). Un barreno con fit/rosca mapeada rotula SIEMPRE (piso 0.2).
    `max_groups` = nº de diámetros distintos rotulados (se sube en láminas por pieza)."""
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
        if fit:  # V7.2 C3: asiento ISO 286 = superficie mecanizada fina → Ra 1.6 TRAS el callout
            from .dimensions import surface_finish
            tw = len(text) * 2.8 * 0.55  # ancho aprox. del rótulo → coloca el ✓ a su derecha
            surface_finish(model, ex + 0.8 + tw + 1.5, ey - 0.8, "1.6", size=2.6)


def _dim_h_at(model: SheetModel, x1: float, x2: float, y: float, value: float, name: str = "") -> None:
    """Cota horizontal flotante a la altura y (para cotas por sólido), con flechas."""
    linear_dim(model, (x1, y), (x2, y), vertical=False, offset=0.0, value=value, name=name)


def _dim_h(model: SheetModel, x: float, y: float, w: float, value: float, offset: float = 8.0) -> None:
    """Cota horizontal bajo el rectángulo (x, y, w), con líneas testigo y flechas."""
    linear_dim(model, (x, y), (x + w, y), vertical=False, offset=offset, value=value)


def _dim_v(model: SheetModel, x: float, y: float, h: float, value: float, offset: float = 8.0) -> None:
    """Cota vertical a la izquierda del rectángulo (x, y, h), con líneas testigo y flechas."""
    linear_dim(model, (x, y), (x, y + h), vertical=True, offset=offset, value=value)


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


def _draw_table_with_balloons(
    model: SheetModel, *, ax0: float, aw: float, ah: float, ay0: float,
    placed: dict, scene: dict, center3: tuple, title: str,
    columns: list[tuple[str, float]], rows: list[dict], cell_values,
    planta_dim_rows: int = 0, anchor_view: str = "planta", top_y: float | None = None,
    max_rows: int = 12,
) -> float:
    """Tabla (BOM/DESPIECE/CÉDULA) en el cuadrante del perfil + globos numerados enlazados a
    `anchor_view`. `columns`=[(cabecera, ancho)...]; `cell_values(i, row)` devuelve la tupla de
    celdas. `top_y` = borde superior (para apilar tablas); devuelve el borde INFERIOR de la tabla.
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
        for j, val in enumerate(cell_values(i, row)):
            model.labels.append(Label(xcols[j] + 1.5, yr, str(val), 2.6, anchor="start"))
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


def compose_sheet(
    scene: dict,
    sheet: str = "A3",
    include_hidden: bool = False,
    project_name: str = "Sin título",
    dims_features: list[str] | None = None,
    section: "bool | str" = False,  # True/"x"→A-A, "y"→B-B, "z"→C-C
    bom: bool = False,
    detail: dict | None = None,  # {"view","u","v","radius","scale"} → burbuja DETALLE
    meta: dict | None = None,  # cajetín: drawing_no, material, revisions[], drawn_by, ...
    datum_dims: list[str] | None = None,  # ids → cotas de POSICIÓN desde el datum (base) en alzado
    cutlist: bool = False,  # tabla DESPIECE (L×A×E por tabla) en vez de BOM sin dimensiones
    member_detail: dict | None = None,  # {member, pick:[t,w,l], locate:[ids], scale, name} → detalle de 1 tabla
    auto_dims: bool = False,  # acota SOLO la posición de los agujeros (Fase 2: acotado automático)
    interface_dims: bool = False,  # cotas de MONTAJE: pitch centro-a-centro del patrón de agujeros + luz total
    hardware: bool = False,  # añade tabla CÉDULA DE HERRAJE bajo el DESPIECE (Fase 4: herraje en la lámina)
    explode: dict | None = None,  # {axis,factor} → VISTA EXPLOSIONADA en el cuadrante iso (Fase 3)
    notes: list[str] | None = None,  # bloque de NOTAS generales en la lámina (Fase 5: anotaciones)
    assembly_notes: list[str] | None = None,  # bloque NOTAS DE MONTAJE: None=off · []=auto-semilla del herraje · [..]=explícitas
    show_iso: bool = True,  # incluir la isométrica (las láminas por pieza la omiten: 3 vistas bastan)
    shaded: bool = False,  # isométrica SOMBREADA a color (estilo Inventor) en vez del alambre
    hole_fits: dict[float, str] | None = None,  # {Ø_nominal → "H7"}: callouts con clase+límites ISO 286 (V5.4)
    hole_threads: dict[float, str] | None = None,  # {Ø_broca → "M8"}: callout de rosca + cosmético ISO 6410 (V5.7)
    colors: dict | None = None,  # color por pieza para el sombreado (= viewport web: DOC.colors+paleta)
    sheet_refs: dict | None = None,  # {_rep id → nº de hoja} → columna "Hoja" en el DESPIECE (cross-ref globo→lámina de detalle)
    fasteners: dict | None = None,  # DOC.fasteners → símbolos de soldadura ISO 2553 en el conjunto (V7.2 A); NO-OP en láminas por pieza
    shop_notes: bool = False,  # notas de taller de lámina por pieza: tolerancia ISO 2768 + proceso/acabado ISO 1302 + protección (V7.2 B/C)
    datum_side: "str | list[str] | None" = None,  # "+z"/"-x"/… o LISTA por peso (de fasteners, V7.5): cada vista usa el primer lado que proyecte como BORDE → el datum «A» y las posiciones se miden desde esa arista
) -> SheetModel:
    if sheet not in SHEETS:
        raise ValueError(f"Lámina desconocida '{sheet}' (usa A3 o A4)")
    width, height = SHEETS[sheet]
    # planta: se omite si un member_detail ocupa ese cuadrante (su astilla no aporta en una pieza plana)
    wanted = (["alzado"] + ([] if member_detail else ["planta"])
              + ([] if (bom or cutlist) else ["lateral"])
              + ([] if (section or not show_iso or shaded) else ["iso"]))
    views = project_views(scene, wanted, include_hidden)
    dims = real_dims(scene)
    center3 = view_center(scene)
    n_solidos = sum(1 for f in scene.values() if f.visible)

    model = SheetModel(width, height)
    model.rect(MARGIN, MARGIN, width - 2 * MARGIN, height - 2 * MARGIN)
    _zone_grid(model, width, height)

    # área de dibujo en rejilla 2x2 (primer diedro: planta bajo alzado, perfil a la derecha)
    ax0, ay0 = MARGIN + 6, MARGIN + 6
    aw = width - 2 * MARGIN - 12
    ah = height - 2 * MARGIN - 12
    cell_w = aw / 2 - 2 * CELL_PAD
    cell_h = ah / 2 - 2 * CELL_PAD
    scale, scale_label = _pick_scale(views, cell_w, cell_h)
    _scale_bar(model, MARGIN + 5, MARGIN + 6, scale)

    centers = {
        "alzado": (ax0 + aw * 0.25, ay0 + ah * 0.72),
        "lateral": (ax0 + aw * 0.75, ay0 + ah * 0.72),
        "planta": (ax0 + aw * 0.25, ay0 + ah * 0.26),
        "iso": (ax0 + aw * 0.75, ay0 + ah * 0.28),
    }
    # el cuadrante iso (abajo-derecha) comparte sitio con el cajetín (180×40) + bloque de
    # revisiones: acotar su banda vertical POR ENCIMA de ellos para que la iso/explosión/detalle
    # no se solapen con el texto del cajetín ni la tabla de revisiones.
    _n_revs = min(len((meta or {}).get("revisions") or []), 6)
    tb_top = (51.0 + (_n_revs + 1) * 4.5 + 4.0) if _n_revs else 54.0  # borde superior cajetín+revisiones
    iso_band_top = ay0 + ah * 0.52
    iso_cell_h = max(iso_band_top - tb_top, 28.0)
    centers["iso"] = (ax0 + aw * 0.75, (tb_top + iso_band_top) / 2)

    placed: dict[str, tuple] = {}  # name -> (rect, tx)
    for name in ("alzado", "lateral", "planta"):
        if name not in views:
            continue
        view = views[name]
        cx, cy = centers[name]
        rect, tx = _place_view(model, view, cx, cy, scale)
        placed[name] = (rect, tx)
        rx, ry, rw, rh = rect
        h_axis, v_axis = VIEW_DIMS[name]
        _dim_h(model, rx, ry, rw, dims[h_axis])
        _dim_v(model, rx, ry, rh, dims[v_axis])
        model.labels.append(Label(cx, ry - 14.5, VIEW_TITLES[name], 3.6))
        # láminas de taller por pieza: no silenciar barrenos funcionales de piezas largas
        # a escala pequeña, y admitir más diámetros distintos (V7.2 D1)
        _hole_callouts(model, view, tx, scale, hole_fits, hole_threads,
                       min_r_paper=0.2 if shop_notes else 0.8,
                       max_groups=8 if shop_notes else 4)
        for cv in view.circles:  # marca de centro (cruz de ejes) en cada agujero
            ccx, ccy = tx((cv[0], cv[1]))
            center_mark(model, ccx, ccy, cv[2] * scale)
        if auto_dims and view.circles:  # acotado automático: posición x/y de cada agujero
            from .autodim import auto_hole_dims
            # datum «A» marcado en las láminas de taller por pieza (V7.2 D2). Con señal de
            # cara FUNCIONAL (V7.5, derivada de los fasteners) las posiciones se miden desde
            # ESA arista — la vista usa el PRIMER lado (por peso) que proyecte como borde;
            # una cara ⊥ a la vista no da borde (la del perno siempre lo es en la vista de
            # sus círculos) → se prueba el siguiente lado o cae al fallback de esquina.
            d_edges = None
            _sides = [datum_side] if isinstance(datum_side, str) else (datum_side or [])
            for _s in _sides:
                if not _s or len(_s) != 2:
                    continue
                _sgn, _ax = _s[0], _s[1].upper()
                if _ax == h_axis:
                    d_edges = {"x": "max" if _sgn == "+" else "min"}
                    break
                if _ax == v_axis:
                    d_edges = {"y": "max" if _sgn == "+" else "min"}
                    break
            auto_hole_dims(model, view, rect, tx, datum=shop_notes, datum_edges=d_edges)
        if interface_dims and len(view.circles) >= 2:  # patrón de montaje: pitch centro-a-centro
            from .autodim import mounting_pattern_dims
            # si auto_dims también está, empujar el pitch más afuera para no solaparse con sus escaleras
            mounting_pattern_dims(model, view, rect, tx, base_offset=52.0 if auto_dims else 20.0)

    # cotas por sólido seleccionado: extensión X sobre la planta, apiladas
    planta_dim_rows = 0  # nº de cotas de tamaño dibujadas encima de la planta (→ globos van arriba de ellas)
    if dims_features and "planta" in placed:
        (rx, ry, rw, rh), tx = placed["planta"]
        for fid in dims_features:
            feat = scene.get(fid)
            if feat is None or planta_dim_rows >= 3:
                continue
            bb = feat.shape.bounding_box()
            x1, _ = tx(world_to_view("planta", (bb.min.X, 0, 0), center3))
            x2, _ = tx(world_to_view("planta", (bb.max.X, 0, 0), center3))
            y = ry + rh + 5.5 + planta_dim_rows * 6.5
            _dim_h_at(model, x1, x2, y, round(bb.max.X - bb.min.X, 1), feat.name[:16])
            planta_dim_rows += 1

    # cotas de POSICIÓN desde el DATUM (base del modelo), en el alzado, apiladas a la izq
    if datum_dims and "alzado" in placed:
        (arx, ary, arw, arh), atx = placed["alzado"]
        model_min_z = center3[2] - dims["Z"] / 2
        _, datum_y = atx(world_to_view("alzado", (0, 0, model_min_z), center3))
        entries = []
        for fid in datum_dims[:6]:
            feat = scene.get(fid)
            if feat is None:
                continue
            bb = feat.shape.bounding_box()
            _, py = atx(world_to_view("alzado", (0, 0, bb.min.Z), center3))
            entries.append((py, round(bb.min.Z - model_min_z, 1), feat.name[:10]))
        baseline_dims(model, datum_y, entries, vertical=True, along=arx - 2,
                      base_offset=6.0, offset_step=6.0)

    # SÍMBOLOS DE SOLDADURA ISO 2553 (V7.2 A): cordones tipo 'soldadura' del modelo,
    # agrupados «típ. ×N» sobre el alzado del conjunto. NO-OP en láminas por pieza.
    # Solo pares con AMBAS piezas VISIBLES (un cordón hacia una pieza oculta anclaría
    # su símbolo a geometría que no está dibujada).
    _weld_scene = scene if include_hidden else {fid: f for fid, f in scene.items() if f.visible}
    _weld_stats = _place_weld_symbols(model, fasteners, _weld_scene, placed, center3)

    # CORTE (A-A / B-B / C-C según eje) en el cuadrante de la isométrica
    if section:
        sec_axis = section if isinstance(section, str) else "x"
        corte, cut_polys, cut_coord, axis = section_projection(
            scene, axis=sec_axis, include_hidden=include_hidden
        )
        letter = {"x": "A", "y": "B", "z": "C"}.get(axis, "A")
        cxs, cys = centers["iso"]
        rect, tx = _place_view(model, corte, cxs, cys, scale)
        for rings, material in cut_polys:
            model.polygons.append(
                Polygon([[tx(p) for p in ring] for ring in rings], "corte", material)
            )
        model.labels.append(Label(cxs, rect[1] + rect[3] + 3, f"CORTE {letter}-{letter}", 3.6))
        # traza del plano de corte en la planta (solo eje X: línea vertical en x=cut)
        if axis == "x" and "planta" in placed:
            (rx, ry, rw, rh), ptx = placed["planta"]
            tx_cut, _ = ptx(world_to_view("planta", (cut_coord, 0, 0), center3))
            y0, y1 = ry - 4, ry + rh + 4
            model.lines.append(Line(tx_cut, y0, tx_cut, y1, "dim"))
            for ya in (y0, y1):
                model.lines += [
                    Line(tx_cut, ya, tx_cut - 4, ya, "dim"),
                    Line(tx_cut - 4, ya, tx_cut - 2.6, ya + 1.1, "dim"),
                    Line(tx_cut - 4, ya, tx_cut - 2.6, ya - 1.1, "dim"),
                ]
                model.labels.append(Label(tx_cut + 1.2, ya - 1.0, letter, 3.4, anchor="start"))
    elif detail and detail.get("view") in placed:
        # vista de DETALLE (burbuja) en el cuadrante de la isométrica
        pv = detail["view"]
        u, v = float(detail.get("u", 0.0)), float(detail.get("v", 0.0))
        radius = float(detail.get("radius", 40.0))
        dscale = float(detail.get("scale", 2.0))
        dv = detail_view(views[pv], (u, v), radius, dscale)
        cx, cy = centers["iso"]
        if dv.width > 0 and dv.height > 0:
            ds = min(cell_w / dv.width, iso_cell_h / dv.height) * 0.85
            rect, _ = _place_view(model, dv, cx, cy, ds)
            model.labels.append(Label(cx, rect[1] + rect[3] + 3, f"DETALLE A · escala {dscale:g}:1", 3.0))
        # marca de la región fuente en la vista madre
        (prx, pry, prw, prh), ptx = placed[pv]
        sx, sy = ptx((u, v))
        model.circles.append(Circle(sx, sy, radius * scale, "dim"))
        model.labels.append(Label(sx + radius * scale + 0.8, sy, "A", 2.8, anchor="start"))
    elif explode:
        # VISTA EXPLOSIONADA: piezas separadas a lo largo de un eje, con globos de secuencia.
        # Se proyecta ortográfica (alzado, o planta si el eje es Y) para poder situar los globos.
        from .explode import explode_scene

        eax = str(explode.get("axis", "z"))
        exp = explode_scene(scene, axis=eax, factor=float(explode.get("factor", 1.0)))
        vname = "planta" if eax == "y" else "alzado"
        ev = project_views(exp, [vname], include_hidden).get(vname)
        cxs, cys = centers["iso"]
        if ev is not None and ev.width > 0 and ev.height > 0:
            es = min(cell_w / ev.width, iso_cell_h / ev.height) * 0.82
            rect, etx = _place_view(model, ev, cxs, cys, es)
            model.labels.append(Label(cxs, rect[1] + rect[3] + 3, "VISTA EXPLOSIONADA", 3.0))
            ecenter = view_center(exp)
            i_ax = {"x": 0, "y": 1, "z": 2}.get(eax, 2)
            items = []
            for fid, f in exp.items():
                if not getattr(f, "visible", True):
                    continue
                bb = f.shape.bounding_box()
                c = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
                items.append((c[i_ax], etx(world_to_view(vname, c, ecenter))))
            items.sort(key=lambda it: it[0])
            if len(items) >= 2:  # línea de explosión (eje-punto) a lo largo del recorrido
                (_, p0), (_, pn) = items[0], items[-1]
                model.lines.append(Line(p0[0], p0[1], pn[0], pn[1], "center"))
            for k, (_, (px, py)) in enumerate(items[:20]):  # globos de secuencia 1..n
                model.circles.append(Circle(px, py, 2.8, "globo"))
                model.labels.append(Label(px, py - 1.0, str(k + 1), 2.8))
    elif shaded and show_iso:
        # VISTA ISOMÉTRICA SOMBREADA A COLOR (estilo Inventor): render 3D embebido en la lámina
        import struct

        from ..kernel.render import render_scene_png

        try:
            vscene = scene if include_hidden else {fid: f for fid, f in scene.items() if f.visible}
            png = render_scene_png(vscene, view="iso", size_px=760, clean=True, colors=colors)
            pw, ph = struct.unpack(">II", png[16:24])
            aspect = (pw / ph) if ph else 1.33
            cxs, cys = centers["iso"]
            bw, bh = cell_w, iso_cell_h
            if bw / bh > aspect:
                bw = bh * aspect
            else:
                bh = bw / aspect
            model.images.append(Image(cxs - bw / 2, cys - bh / 2, bw, bh, png))
            # rótulo solo si el cuadrante superior-derecho está libre (el conjunto no lleva perfil);
            # en las láminas por pieza el perfil ocupa esa banda → se omite para no solaparse.
            if "lateral" not in placed:
                model.labels.append(Label(cxs, cys + bh / 2 + 3, "ISOMÉTRICA · sombreado", 3.0))
        except Exception:  # si falta matplotlib o el render falla, no rompemos la lámina
            pass
    elif "iso" in views and views["iso"].width > 0:
        iso = views["iso"]
        iso_scale = min(cell_w / iso.width, iso_cell_h / iso.height) * 0.9
        cx, cy = centers["iso"]
        rect, _ = _place_view(model, iso, cx, cy, iso_scale)
        model.labels.append(Label(cx, rect[1] + rect[3] + 3, "ISOMÉTRICA (sin escala)", 3.0))

    # tabla (cuadrante del perfil) + globos: BOM (sin dims, globos en planta) o
    # DESPIECE (L×A×E por tabla, globos en el alzado). Respeta la visibilidad.
    visible_scene = scene if include_hidden else {fid: f for fid, f in scene.items() if f.visible}
    if bom:
        from apolo.library.bom import bom_from_scene

        _draw_table_with_balloons(
            model, ax0=ax0, aw=aw, ah=ah, ay0=ay0, placed=placed, scene=scene, center3=center3,
            title="LISTA DE MATERIALES",
            columns=[("N.º", 10), ("Ref", 34), ("Descripción", 102), ("Cant", 14)],
            rows=bom_from_scene(visible_scene),
            cell_values=lambda i, row: (str(i + 1), row["ref"], row["descripcion"][:44], str(row["cantidad"])),
            planta_dim_rows=planta_dim_rows, anchor_view="planta",
        )
    elif cutlist:
        from apolo.library.cutlist import cut_list

        if sheet_refs:  # cross-reference: cada renglón apunta a su lámina de detalle ("Hoja k")
            _cl_cols = [("N.º", 8), ("Pieza", 36), ("Material", 30), ("L×A×E (mm)", 58),
                        ("Hoja", 14), ("Cant", 14)]
            _cl_cells = lambda i, row: (
                str(i + 1), str(row["nombre"])[:16], str(row["material"])[:13],
                f"{row['largo_mm']:g}×{row['ancho_mm']:g}×{row['espesor_mm']:g}",
                # clave por FILA (multi-sólido comparte _rep); fallback compat al _rep pelado
                str(sheet_refs.get((row["_rep"], row["largo_mm"], row["ancho_mm"],
                                    row["espesor_mm"]), sheet_refs.get(row["_rep"], ""))),
                str(row["cantidad"]),
            )
        else:
            _cl_cols = [("N.º", 8), ("Pieza", 40), ("Material", 34), ("L×A×E (mm)", 64), ("Cant", 14)]
            _cl_cells = lambda i, row: (
                str(i + 1), str(row["nombre"])[:18], str(row["material"])[:15],
                f"{row['largo_mm']:g}×{row['ancho_mm']:g}×{row['espesor_mm']:g}", str(row["cantidad"]),
            )
        table_bottom = _draw_table_with_balloons(
            model, ax0=ax0, aw=aw, ah=ah, ay0=ay0, placed=placed, scene=scene, center3=center3,
            title="DESPIECE", columns=_cl_cols, rows=cut_list(visible_scene),
            cell_values=_cl_cells,
            planta_dim_rows=planta_dim_rows, anchor_view="alzado",
        )
        # CÉDULA DE HERRAJE bajo el DESPIECE (catálogo no cortable: bisagras/correderas/tornillos)
        if hardware:
            from apolo.library.cutlist import hardware_schedule

            hw = hardware_schedule(visible_scene)
            if hw:
                _draw_table_with_balloons(
                    model, ax0=ax0, aw=aw, ah=ah, ay0=ay0, placed=placed, scene=scene, center3=center3,
                    title="CÉDULA DE HERRAJE",
                    columns=[("Ref", 24), ("Descripción", 46), ("Norma", 24), ("Cant", 12), ("Peso", 14)],
                    rows=hw,
                    cell_values=lambda i, row: (
                        str(row["ref"])[:12], str(row["nombre"])[:24], str(row.get("norma", ""))[:14],
                        str(row["cantidad"]), f"{row['peso_total_kg']:g}kg",
                    ),
                    anchor_view="none", top_y=table_bottom - 5.0, max_rows=8,
                )

    # DETALLE de una tabla (p. ej. un larguero) en el cuadrante de la planta, con sus
    # mortajas/bisagras acotadas desde la base de la pieza. Reemplaza la planta-astilla.
    if member_detail:
        from apolo.commands.registry import Feature

        from .sheetset import _pick_solid

        mfeat = scene.get(member_detail.get("member", ""))
        shape = mfeat.shape if mfeat is not None else None
        pick = member_detail.get("pick")
        if shape is not None and pick:
            shape = _pick_solid(shape, *pick) or shape
        if shape is not None:
            mname = member_detail.get("name") or (mfeat.name if mfeat else "Pieza")
            msyn = {"M": Feature("M", mname, shape, mfeat.command_id if mfeat else "M")}
            mviews = project_views(msyn, ["alzado"], True)
            mv = mviews.get("alzado")
            if mv is not None and mv.width > 0 and mv.height > 0:
                mcenter = view_center(msyn)
                cxm, cym = centers["planta"]
                dscale = float(member_detail.get("scale") or 0) or (
                    min(cell_w / mv.width, cell_h / mv.height) * 0.78
                )
                (mrx, mry, mrw, mrh), mtx = _place_view(model, mv, cxm, cym, dscale)
                _dim_v(model, mrx, mry, mrh, round(mv.height, 1))
                _dim_h(model, mrx, mry, mrw, round(mv.width, 1))
                ratio = (1.0 / dscale) if dscale else 0.0
                model.labels.append(Label(cxm, mry - 14.5, f"DETALLE · {mname[:16]} (1:{ratio:.0f})", 3.6))
                # cotas de posición de cada mortaja/bisagra desde la base de la pieza
                mbb = shape.bounding_box()
                m_min_z = mbb.min.Z
                _, mdatum_y = mtx(world_to_view("alzado", (mcenter[0], 0, m_min_z), mcenter))
                entries = []
                for fid in (member_detail.get("locate") or [])[:6]:
                    lf = scene.get(fid)
                    if lf is None:
                        continue
                    lbb = lf.shape.bounding_box()
                    zc = (lbb.min.Z + lbb.max.Z) / 2
                    _, py = mtx(world_to_view("alzado", (mcenter[0], 0, zc), mcenter))
                    entries.append((py, round(zc - m_min_z, 1), lf.name[:10]))
                baseline_dims(model, mdatum_y, entries, vertical=True, along=mrx - 2,
                              base_offset=6.0, offset_step=6.0)

    # V7.2 — notas AUTO de taller: (B/C) tolerancia ISO 2768 + proceso/acabado ISO 1302
    # + protección, inferidos de la pieza REPRESENTANTE (mayor bbox entre las visibles;
    # en una lámina por pieza es la única); (A) leyenda de soldadura del conjunto.
    _rep_finish: str | None = None
    _auto_notes: list[str] = []
    if shop_notes and visible_scene:
        from apolo.library.catalog import CATALOG
        from apolo.library.materials import resolve_material

        from .process import finish_label, infer_process
        from .process import shop_notes as _shop_note_lines

        rep = max(visible_scene.values(), key=_bbox_vol)
        comp = CATALOG.get(getattr(rep, "component", None) or "")
        _rep_finish = finish_label(infer_process(rep, comp)["ra"])
        _auto_notes += _shop_note_lines(rep, comp, resolve_material(rep, CATALOG))
    _wn_drawn, _wn_groups, _wn_sincota, _wn_total = _weld_stats
    if _wn_total:  # honestidad: declara agrupación y cordones sin dimensionar
        _auto_notes.append("Soldadura: símbolos ISO 2553 · a = garganta de filete (mm).")
        if _wn_groups > _wn_drawn:
            _auto_notes.append("Resto de cordones: ver despiece/memoria de cálculo.")
        if _wn_sincota:
            _auto_notes.append("Cordones sin dimensionar: ver memoria de cálculo.")

    # bloques de NOTAS (hueco medio-izquierdo): generales (NOTAS + auto de taller) y de
    # montaje (NOTAS DE MONTAJE), apilados sin solaparse (notes_block devuelve su borde inf).
    notes_y = ay0 + ah * 0.50
    _general = list(notes or []) + _auto_notes
    if _general:
        notes_y = notes_block(model, MARGIN + 6, notes_y, _general) - 4.0
    if assembly_notes is not None:
        am = list(assembly_notes) if assembly_notes else _assembly_notes_auto(visible_scene)
        if am:
            notes_block(model, MARGIN + 6, notes_y, am, title="NOTAS DE MONTAJE")

    # cajetín profesional + bloque de revisiones
    from apolo.library.cutlist import dominant_material, scene_weight_kg

    from .titleblock import draw_title_block

    m = meta or {}
    fields = {
        "project": project_name,
        "drawing_no": m.get("drawing_no", "—"),
        "scale": scale_label, "sheet": sheet,
        "sheet_no": m.get("sheet_no", 1), "n_sheets": m.get("n_sheets", 1),
        "material": m.get("material") or dominant_material(scene) or "—",
        "finish": m.get("finish") or _rep_finish or "—",
        "weight_kg": m["weight_kg"] if m.get("weight_kg") is not None else scene_weight_kg(scene),
        "tolerance": m.get("tolerance", "ISO 2768-mK"), "units": "mm",
        "drawn_by": m.get("drawn_by", ""), "checked_by": m.get("checked_by", ""),
        "approved_by": m.get("approved_by", ""),
        "date": m.get("date", date.today().isoformat()),
        "revisions": m.get("revisions", []),
    }
    draw_title_block(model, fields)

    model.meta = {
        "scale": scale, "scale_label": scale_label, "sheet": sheet, "dims": dims,
        "section": bool(section), "bom": bom, "cutlist": cutlist,
        "member_detail": bool(member_detail), "title": fields,
    }
    return model
