"""`LaminaEnCurso`: el estado de `compose_sheet` mientras compone una lámina (plan
partir-nucleo-congelado-ii, F4, D4). Lleva los argumentos de la llamada tal cual y los locales
que un bloque (`sheet_vistas`, `sheet_cotas`, `sheet_tablas`, `sheet_cajetin`) produce para
otro, con su MISMO nombre; los pone el orquestador con lo que cada bloque devuelve. No es API:
nadie fuera de `compose_sheet` lo construye."""

from __future__ import annotations

from dataclasses import dataclass

from .projection import ViewProjection
from .sheet_primitivas import SheetModel


@dataclass
class LaminaEnCurso:
    # los argumentos de `compose_sheet`, en su orden
    scene: dict
    sheet: str
    include_hidden: bool
    project_name: str
    dims_features: list[str] | None
    section: bool | str
    bom: bool
    detail: dict | None
    meta: dict | None
    datum_dims: list[str] | None
    cutlist: bool
    member_detail: dict | None
    auto_dims: bool
    interface_dims: bool
    hardware: bool
    explode: dict | None
    notes: list[str] | None
    assembly_notes: list[str] | None
    show_iso: bool
    shaded: bool
    foto_diferida: bool
    hole_fits: dict[float, str] | None
    hole_threads: dict[float, str] | None
    colors: dict | None
    sheet_refs: dict | None
    fasteners: dict | None
    shop_notes: bool
    datum_side: str | list[str] | None
    datum_frame: list[tuple[str, str, str]] | None
    pos_tols: dict[float, float] | None
    dim_tols: dict[str, tuple] | None
    # lo que produce un bloque para los siguientes, en el orden en que se produce
    views: dict[str, ViewProjection] | None = None
    dims: dict | None = None
    center3: tuple | None = None
    model: SheetModel | None = None
    ax0: float | None = None
    ay0: float | None = None
    aw: float | None = None
    ah: float | None = None
    cell_w: float | None = None
    cell_h: float | None = None
    scale: float | None = None
    scale_label: str | None = None
    centers: dict[str, tuple[float, float]] | None = None
    iso_cell_h: float | None = None
    _gdt_frames: int | None = None
    _chain_notes: list[str] | None = None
    placed: dict[str, tuple] | None = None
    planta_dim_rows: int | None = None
    _weld_stats: tuple | None = None
    visible_scene: dict | None = None
    _rep_finish: str | None = None
    _auto_notes: list[str] | None = None
