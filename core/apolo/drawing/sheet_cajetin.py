"""Bloques de `compose_sheet` (plan partir-nucleo-congelado-ii, F4, D4) del cierre de la
lámina: notas automáticas de taller (tolerancia, acabado, datums, cadenas, soldadura),
bloques de notas y cajetín con su `meta`. Cada cuerpo es el del original, verbatim; el
estado viaja en `LaminaEnCurso`.
"""

from __future__ import annotations

from datetime import date

from .dimensions import notes_block
from .sheet_anotaciones import _assembly_notes_auto, _bbox_vol
from .sheet_lamina import LaminaEnCurso
from .sheet_primitivas import MARGIN


def reunir_notas_de_taller(ctx: LaminaEnCurso) -> tuple[str | None, list[str]]:
    _chain_notes, _gdt_frames, _weld_stats = ctx._chain_notes, ctx._gdt_frames, ctx._weld_stats
    datum_frame, shop_notes, visible_scene = ctx.datum_frame, ctx.shop_notes, ctx.visible_scene
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
    # V7.6 A: LEYENDA de datums — sin ella el marco de control es decorativo. Cada letra
    # nombra la unión REAL que la justifica (derivada de los fasteners, no del nombre).
    if datum_frame and _gdt_frames:
        _EJE = {"x": "X", "y": "Y", "z": "Z"}
        for letra, lado, motivo in datum_frame[:3]:
            cara = f"cara {lado[0]}{_EJE.get(lado[1].lower(), lado[1])}"
            _auto_notes.append(f"Datum {letra}: {cara} — {motivo}.")
        _auto_notes.append("Posición: máx. material (M); tol. = holgura de paso.")
    # V7.6 B: la cota rotulada con ±t no es un número suelto — remite a la cadena que la
    # justifica, que el revisor puede reproducir en la memoria (tolerancia JUSTIFICADA)
    for _cn in _chain_notes[:2]:
        _auto_notes.append(f"Cota crítica: cadena «{_cn}» (ver memoria).")  # entera: notes_block la parte
    _wn_drawn, _wn_groups, _wn_sincota, _wn_total = _weld_stats
    if _wn_total:  # honestidad: declara agrupación y cordones sin dimensionar
        _auto_notes.append("Soldadura: símbolos ISO 2553 · a = garganta de filete (mm).")
        # tolerancias de FABRICACIÓN soldada: la norma de weldments que casi ningún
        # despacho de máquina rotula (las de ISO 2768 son de mecanizado, no de soldeo)
        _auto_notes.append("Tol. de construcción soldada: ISO 13920-BF.")
        if _wn_groups > _wn_drawn:
            _auto_notes.append("Resto de cordones: ver despiece/memoria de cálculo.")
        if _wn_sincota:
            _auto_notes.append("Cordones sin dimensionar: ver memoria de cálculo.")
    return _rep_finish, _auto_notes


def dibujar_notas(ctx: LaminaEnCurso) -> None:
    _auto_notes, ah, assembly_notes, ay0 = ctx._auto_notes, ctx.ah, ctx.assembly_notes, ctx.ay0
    model, notes, visible_scene = ctx.model, ctx.notes, ctx.visible_scene
    # bloques de NOTAS (hueco medio-izquierdo): generales (NOTAS + auto de taller) y de
    # montaje (NOTAS DE MONTAJE), apilados sin solaparse (notes_block devuelve su borde inf).
    notes_y = ay0 + ah * 0.50
    _general = list(notes or []) + _auto_notes
    if _general:
        notes_y = notes_block(model, MARGIN + 6, notes_y, _general, piso=MARGIN + 3.0) - 4.0
    if assembly_notes is not None:
        am = list(assembly_notes) if assembly_notes else _assembly_notes_auto(visible_scene)
        if am:
            notes_block(model, MARGIN + 6, notes_y, am, title="NOTAS DE MONTAJE", piso=MARGIN + 3.0)


def dibujar_cajetin(ctx: LaminaEnCurso) -> None:
    _rep_finish, bom, cutlist, dims = ctx._rep_finish, ctx.bom, ctx.cutlist, ctx.dims
    member_detail, meta, model = ctx.member_detail, ctx.meta, ctx.model
    project_name, scale, scale_label = ctx.project_name, ctx.scale, ctx.scale_label
    scene, section, sheet = ctx.scene, ctx.section, ctx.sheet
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
