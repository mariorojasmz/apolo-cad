"""Composición de la lámina: disposición en primer diedro, escala normalizada,
cotas generales y cajetín.

El modelo de lámina (líneas + rótulos en mm, origen abajo-izquierda, Y hacia
arriba) es la fuente común de los exportadores SVG, PDF y DXF.

Módulos (plan partir-nucleo-congelado-ii, F4): `sheet_primitivas` (constantes y primitivas
del modelo), `sheet_auxiliares` (escala, vistas, rótulos de agujeros, cotas, marco),
`sheet_anotaciones` (tablas con globos, notas de montaje, soldadura) y los bloques de
`compose_sheet` en `sheet_vistas`, `sheet_cotas`, `sheet_tablas` y `sheet_cajetin`, con su
estado en `LaminaEnCurso` (`sheet_lamina`). Aquí queda el orquestador y la ruta vieja:
re-exporta por IDENTIDAD todo nombre de nivel superior de antes, también los importados
(`tests/test_rutas_viejas.py`). Lo nuevo de una lámina va a su `sheet_*`, no aquí.
"""

from __future__ import annotations

from dataclasses import dataclass, field  # noqa: F401
from datetime import date  # noqa: F401

from .dimensions import (  # noqa: F401
    baseline_dims, center_mark, linear_dim, notes_block, weld_symbol,
)
from .projection import (  # noqa: F401
    ViewProjection, detail_view, project_views, real_dims, section_projection, view_center,
    world_to_view,
)
from .sheet_anotaciones import (  # noqa: F401
    _draw_table_with_balloons, _assembly_notes_auto, _bbox_vol, _weld_anchor,
    _place_weld_symbols,
)
from .sheet_auxiliares import (  # noqa: F401
    _pick_scale, _place_view, _fit_for_dia, _hole_callouts, _dim_h_at, _dim_h, _dim_v,
    _zone_grid, _scale_bar,
)
from .sheet_cajetin import dibujar_cajetin, dibujar_notas, reunir_notas_de_taller
from .sheet_cotas import (
    acotar_desde_datum, acotar_solidos, dibujar_detalle_de_pieza,
    dibujar_simbolos_de_soldadura,
)
from .sheet_lamina import LaminaEnCurso
from .sheet_primitivas import (  # noqa: F401
    SHEETS, MARGIN, TITLE_W, TITLE_H, CELL_PAD, STANDARD_SCALES, VIEW_DIMS, VIEW_TITLES,
    Line, Label, Circle, Arc, Polygon, Image, SheetModel,
)
from .sheet_tablas import dibujar_tablas
from .sheet_vistas import dibujar_cuadrante_iso, dibujar_vistas, preparar_lamina


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
    foto_diferida: bool = False,  # con shaded: sólo RESERVA la foto (model.hueco_iso); la dibuja fotos_planos fuera del lock
    hole_fits: dict[float, str] | None = None,  # {Ø_nominal → "H7"}: callouts con clase+límites ISO 286 (V5.4)
    hole_threads: dict[float, str] | None = None,  # {Ø_broca → "M8"}: callout de rosca + cosmético ISO 6410 (V5.7)
    colors: dict | None = None,  # color por pieza para el sombreado (= viewport web: DOC.colors+paleta)
    sheet_refs: dict | None = None,  # {_rep id → nº de hoja} → columna "Hoja" en el DESPIECE (cross-ref globo→lámina de detalle)
    fasteners: dict | None = None,  # DOC.fasteners → símbolos de soldadura ISO 2553 en el conjunto (V7.2 A); NO-OP en láminas por pieza
    shop_notes: bool = False,  # notas de taller de lámina por pieza: tolerancia ISO 2768 + proceso/acabado ISO 1302 + protección (V7.2 B/C)
    datum_side: "str | list[str] | None" = None,  # "+z"/"-x"/… o LISTA por peso (de fasteners, V7.5): cada vista usa el primer lado que proyecte como BORDE → el datum «A» y las posiciones se miden desde esa arista
    datum_frame: "list[tuple[str, str, str]] | None" = None,  # [(letra, lado, motivo)] (V7.6): sistema de referencia A-B-C para el marco GD&T + su leyenda
    pos_tols: "dict[float, float] | None" = None,  # {Ø → tolerancia de posición mm} (V7.6): presupuesto de ensamble del perno → marco ⌖
    dim_tols: "dict[str, tuple] | None" = None,  # {"X"|"Y"|"Z" → (±t, cadena, fuente)} (V7.6 B): la cota general rotula la tolerancia que EXIGE la cadena declarada, no la genérica
) -> SheetModel:
    # un bloque por sección de la lámina, en el orden de siempre (sheet_vistas, sheet_cotas,
    # sheet_tablas, sheet_cajetin; plan partir-nucleo-congelado-ii D4): lo que un bloque
    # produce para otro vuelve a `ctx`
    ctx = LaminaEnCurso(
        scene=scene, sheet=sheet, include_hidden=include_hidden, project_name=project_name,
        dims_features=dims_features, section=section, bom=bom, detail=detail, meta=meta,
        datum_dims=datum_dims, cutlist=cutlist, member_detail=member_detail, auto_dims=auto_dims,
        interface_dims=interface_dims, hardware=hardware, explode=explode, notes=notes,
        assembly_notes=assembly_notes, show_iso=show_iso, shaded=shaded,
        foto_diferida=foto_diferida, hole_fits=hole_fits, hole_threads=hole_threads, colors=colors,
        sheet_refs=sheet_refs, fasteners=fasteners, shop_notes=shop_notes, datum_side=datum_side,
        datum_frame=datum_frame, pos_tols=pos_tols, dim_tols=dim_tols,
    )
    (
        ctx.views, ctx.dims, ctx.center3, ctx.model, ctx.ax0, ctx.ay0, ctx.aw, ctx.ah, ctx.cell_w,
        ctx.cell_h, ctx.scale, ctx.scale_label, ctx.centers, ctx.iso_cell_h,
    ) = preparar_lamina(ctx)
    ctx._gdt_frames, ctx._chain_notes, ctx.placed = dibujar_vistas(ctx)
    ctx.planta_dim_rows = acotar_solidos(ctx)
    acotar_desde_datum(ctx)
    ctx._weld_stats = dibujar_simbolos_de_soldadura(ctx)
    dibujar_cuadrante_iso(ctx)
    ctx.visible_scene = dibujar_tablas(ctx)
    dibujar_detalle_de_pieza(ctx)
    ctx._rep_finish, ctx._auto_notes = reunir_notas_de_taller(ctx)
    dibujar_notas(ctx)
    dibujar_cajetin(ctx)
    return ctx.model
