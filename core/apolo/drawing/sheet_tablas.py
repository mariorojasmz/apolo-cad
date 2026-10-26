"""Bloque de `compose_sheet` (plan partir-nucleo-congelado-ii, F4, D4) de las TABLAS con
globos: lista de materiales, despiece (con la columna «Hoja») y cédula de herraje. El
cuerpo es el del original, verbatim; el estado viaja en `LaminaEnCurso`.
"""

from __future__ import annotations

from .sheet_anotaciones import _draw_table_with_balloons
from .sheet_lamina import LaminaEnCurso


def dibujar_tablas(ctx: LaminaEnCurso) -> dict:
    ah, aw, ax0, ay0, bom, center3 = ctx.ah, ctx.aw, ctx.ax0, ctx.ay0, ctx.bom, ctx.center3
    cutlist, hardware, include_hidden = ctx.cutlist, ctx.hardware, ctx.include_hidden
    meta, model, placed, planta_dim_rows = ctx.meta, ctx.model, ctx.placed, ctx.planta_dim_rows
    scene, sheet_refs = ctx.scene, ctx.sheet_refs
    # tabla (cuadrante del perfil) + globos: BOM (sin dims, globos en planta) o
    # DESPIECE (L×A×E por tabla, globos en el alzado). Respeta la visibilidad.
    visible_scene = scene if include_hidden else {fid: f for fid, f in scene.items() if f.visible}
    if bom:
        from apolo.library.bom import bom_from_scene

        _draw_table_with_balloons(
            model, ax0=ax0, aw=aw, ah=ah, ay0=ay0, placed=placed, scene=scene, center3=center3,
            title="LISTA DE MATERIALES",
            columns=[("N.º", 10), ("Ref", 34), ("Descripción", 102), ("Cant", 14)],
            rows=bom_from_scene(visible_scene, (meta or {}).get("material_vertical")),
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
            title="DESPIECE", columns=_cl_cols, rows=cut_list(visible_scene, (meta or {}).get("material_vertical")),
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
    return visible_scene
