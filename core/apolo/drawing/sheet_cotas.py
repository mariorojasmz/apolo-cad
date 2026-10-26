"""Bloques de `compose_sheet` (plan partir-nucleo-congelado-ii, F4, D4) de COTAS y
símbolos sobre las vistas: por sólido en la planta, de posición desde el datum, símbolos
de soldadura del conjunto y el detalle acotado de una pieza. Cada cuerpo es el del
original, verbatim; el estado viaja en `LaminaEnCurso`.
"""

from __future__ import annotations

from .dimensions import baseline_dims
from .projection import project_views, view_center, world_to_view
from .sheet_anotaciones import _place_weld_symbols
from .sheet_auxiliares import _dim_h, _dim_h_at, _dim_v, _place_view
from .sheet_lamina import LaminaEnCurso
from .sheet_primitivas import Label


def acotar_solidos(ctx: LaminaEnCurso) -> int:
    center3, dims_features, model, placed = ctx.center3, ctx.dims_features, ctx.model, ctx.placed
    scene = ctx.scene
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
    return planta_dim_rows


def acotar_desde_datum(ctx: LaminaEnCurso) -> None:
    center3, datum_dims, dims, model = ctx.center3, ctx.datum_dims, ctx.dims, ctx.model
    placed, scene = ctx.placed, ctx.scene
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


def dibujar_simbolos_de_soldadura(ctx: LaminaEnCurso) -> tuple:
    center3, fasteners, include_hidden = ctx.center3, ctx.fasteners, ctx.include_hidden
    model, placed, scene = ctx.model, ctx.placed, ctx.scene
    # SÍMBOLOS DE SOLDADURA ISO 2553 (V7.2 A): cordones tipo 'soldadura' del modelo,
    # agrupados «típ. ×N» sobre el alzado del conjunto. NO-OP en láminas por pieza.
    # Solo pares con AMBAS piezas VISIBLES (un cordón hacia una pieza oculta anclaría
    # su símbolo a geometría que no está dibujada).
    _weld_scene = scene if include_hidden else {fid: f for fid, f in scene.items() if f.visible}
    _weld_stats = _place_weld_symbols(model, fasteners, _weld_scene, placed, center3)
    return _weld_stats


def dibujar_detalle_de_pieza(ctx: LaminaEnCurso) -> None:
    cell_h, cell_w, centers, member_detail = ctx.cell_h, ctx.cell_w, ctx.centers, ctx.member_detail
    model, scene = ctx.model, ctx.scene
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
