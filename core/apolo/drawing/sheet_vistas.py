"""Bloques de `compose_sheet` (plan partir-nucleo-congelado-ii, F4, D4) de las VISTAS:
preparar la lámina (vistas, marco, escala, cuadrantes), las tres vistas con sus cotas y
rótulos de agujeros, y el cuadrante de la isométrica (corte, detalle, explosionada, foto
sombreada o alambre). Cada cuerpo es el del original, verbatim; el estado viaja en
`LaminaEnCurso`.
"""

from __future__ import annotations

from .dimensions import center_mark
from .projection import (
    detail_view, project_views, real_dims, section_projection, view_center, world_to_view,
)
from .sheet_auxiliares import (
    _dim_h, _dim_v, _hole_callouts, _pick_scale, _place_view, _scale_bar, _zone_grid,
)
from .sheet_lamina import LaminaEnCurso
from .sheet_primitivas import (
    CELL_PAD, MARGIN, SHEETS, VIEW_DIMS, VIEW_TITLES, Circle, Label, Line, Polygon, SheetModel,
)


def preparar_lamina(ctx: LaminaEnCurso) -> tuple:
    bom, cutlist, include_hidden = ctx.bom, ctx.cutlist, ctx.include_hidden
    member_detail, meta, scene, section = ctx.member_detail, ctx.meta, ctx.scene, ctx.section
    shaded, sheet, show_iso = ctx.shaded, ctx.sheet, ctx.show_iso
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
    from .titleblock import TITLE_H as ALTO_CAJETIN  # 40 (el TITLE_H de sheet_primitivas es otro)
    from .titleblock import alto_revisiones

    # borde superior cajetín+revisiones (una descripción larga hace crecer su fila)
    tb_top = MARGIN + ALTO_CAJETIN + alto_revisiones((meta or {}).get("revisions")) + 4.0
    iso_band_top = ay0 + ah * 0.52
    iso_cell_h = max(iso_band_top - tb_top, 28.0)
    centers["iso"] = (ax0 + aw * 0.75, (tb_top + iso_band_top) / 2)
    return (
        views, dims, center3, model, ax0, ay0, aw, ah, cell_w, cell_h, scale, scale_label, centers,
        iso_cell_h,
    )


def dibujar_vistas(ctx: LaminaEnCurso) -> tuple[int, list[str], dict[str, tuple]]:
    auto_dims, centers, datum_frame = ctx.auto_dims, ctx.centers, ctx.datum_frame
    datum_side, dim_tols, dims, hole_fits = ctx.datum_side, ctx.dim_tols, ctx.dims, ctx.hole_fits
    hole_threads, interface_dims, model = ctx.hole_threads, ctx.interface_dims, ctx.model
    pos_tols, scale, shop_notes, views = ctx.pos_tols, ctx.scale, ctx.shop_notes, ctx.views
    _gdt_frames = 0                # marcos de control dibujados (V7.6 A) → gate de la leyenda
    _chain_notes: list[str] = []   # cadenas de cotas que rotularon una cota (V7.6 B)
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
        # V7.6 B: si la cota participa en una cadena DECLARADA, rotula la tolerancia que
        # el análisis exige (±t de la cadena) en vez de caer a la general ISO 2768
        _th = (dim_tols or {}).get(h_axis)
        _tv = (dim_tols or {}).get(v_axis)
        _dim_h(model, rx, ry, rw, dims[h_axis], tol=_th[0] if _th else None)
        _dim_v(model, rx, ry, rh, dims[v_axis], tol=_tv[0] if _tv else None)
        for _t in (_th, _tv):
            if _t and _t[1] not in _chain_notes:
                _chain_notes.append(_t[1])
        model.labels.append(Label(cx, ry - 14.5, VIEW_TITLES[name], 3.6))
        # láminas de taller por pieza: no silenciar barrenos funcionales de piezas largas
        # a escala pequeña, y admitir más diámetros distintos (V7.2 D1)
        _gdt_frames += _hole_callouts(
            model, view, tx, scale, hole_fits, hole_threads,
            min_r_paper=0.2 if shop_notes else 0.8,
            max_groups=8 if shop_notes else 4,
            pos_tols=pos_tols,
            datum_letters=tuple(d[0] for d in (datum_frame or []))) or 0
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
    return _gdt_frames, _chain_notes, placed


def dibujar_cuadrante_iso(ctx: LaminaEnCurso) -> None:
    cell_w, center3, centers, colors = ctx.cell_w, ctx.center3, ctx.centers, ctx.colors
    detail, explode, foto_diferida = ctx.detail, ctx.explode, ctx.foto_diferida
    include_hidden, iso_cell_h, model = ctx.include_hidden, ctx.iso_cell_h, ctx.model
    placed, scale, scene, section = ctx.placed, ctx.scale, ctx.scene, ctx.section
    shaded, show_iso, views = ctx.shaded, ctx.show_iso, ctx.views
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
            for f in exp.values():
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
        # ISOMÉTRICA SOMBREADA A COLOR (estilo Inventor): foto 3D en el cuadrante, reservada y
        # dibujada fuera de STATE_LOCK (fotos_planos, manual-rapido F2b). Rótulo sólo si el
        # cuadrante de arriba está libre (en las láminas por pieza lo ocupa el perfil).
        from . import fotos_planos

        fotos_planos.reservar(model, centers["iso"], cell_w, iso_cell_h, "lateral" not in placed,
                              scene if include_hidden else
                              {fid: f for fid, f in scene.items() if f.visible}, colors)
        if not foto_diferida:  # dueño del documento: las tres fases de corrido
            fotos_planos.revelar(fotos_planos.extraer([model]))
    elif "iso" in views and views["iso"].width > 0:
        iso = views["iso"]
        iso_scale = min(cell_w / iso.width, iso_cell_h / iso.height) * 0.9
        cx, cy = centers["iso"]
        rect, _ = _place_view(model, iso, cx, cy, iso_scale)
        model.labels.append(Label(cx, rect[1] + rect[3] + 3, "ISOMÉTRICA (sin escala)", 3.0))
