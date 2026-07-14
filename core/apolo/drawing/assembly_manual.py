"""Manual de ENSAMBLAJE paso a paso (instructivo de montaje, estilo Inventor/IKEA).

A diferencia del plano de conjunto (GA: despiece + cédula + globos, una sola lámina), el
manual EXPLICA el armado: una página por PASO, con el render 3D sombreado de lo que va
montado hasta ahí (las piezas NUEVAS del paso resaltadas en color, lo previo en gris fantasma),
las piezas/herraje que se añaden y la instrucción.

La SECUENCIA se deriva del propio modelo (el moat agente-nativo):
- **orden de construcción** = el log de comandos (`Document.commands`): lo que el usuario modeló
  primero es la base; respeta ese orden de armado real.
- **agrupación en pasos humanos**: el herraje se agrupa por familia de catálogo (todas las
  bisagras juntas, todas las correderas…); las piezas a medida por el token inicial de su nombre
  (Marco / H1 / Vidrio / Parteluz / Tornillería…). Cada grupo = un paso, ordenado por su primera
  aparición en el log. Heurística transparente y refinable.

Reusa `render_scene_png` (con `highlight_ids` para resaltar lo nuevo y `frame_bbox` para una
cámara ESTABLE: las piezas aparecen en su sitio final) y `sheets_to_pdf` (multipágina).
"""

from __future__ import annotations

import re
import struct
from datetime import date

from .sheet import Image, Label, Line, SheetModel
from .titleblock import draw_title_block

SHEETS = {"A3": (420.0, 297.0), "A4": (297.0, 210.0)}

# etiquetas amistosas para tokens/categorías frecuentes (fallback: capitaliza el token)
_LABELS = {
    "marco": "Marco / bastidor", "hoja": "Hojas (bastidores)", "vidrio": "Vidrios",
    "parteluz": "Parteluces", "tirador": "Tiradores", "pomo": "Pomos", "torn": "Tornillería",
    "tornillo": "Tornillería", "clavija": "Clavijas", "bisagras": "Bisagras",
    "rieles_corredera": "Riel superior", "correderas_colgantes": "Correderas colgantes",
    "correderas": "Correderas", "tornilleria": "Tornillería", "rodamientos": "Rodamientos",
    "tiradores": "Tiradores", "cerraduras": "Cerraduras", "imanes_topes": "Imanes / topes",
    "perfiles": "Perfiles", "tubos_estructurales": "Tubos estructurales",
}


def _pretty(tok: str, is_hw: bool) -> str:
    low = tok.lower()
    if low in _LABELS:
        return _LABELS[low]
    m = re.match(r"^h(\d+)$", low)          # H1, H2… → refuerzos de la hoja N
    if m:
        return f"Refuerzos hoja {m.group(1)}"
    return tok[:1].upper() + tok[1:] if tok else "Piezas"


def assembly_steps(scene: dict, commands: list[dict], catalog) -> list[dict]:
    """Deriva los PASOS de montaje. Las features con GRUPO declarado (sub-ensamblaje
    V5.2, `feat.group`) forman un paso por grupo (label = nombre del grupo); las no
    agrupadas caen a la heurística de siempre (herraje por familia de catálogo; a medida
    por token inicial del nombre). Todo ordenado por primera aparición en el log.
    Devuelve [{label, ids, first, is_hw}] ya ordenado."""
    cmd_index = {c["id"]: i for i, c in enumerate(commands)}
    groups: dict[tuple, dict] = {}
    for fid, f in scene.items():
        if not getattr(f, "visible", True):
            continue
        declared = getattr(f, "group", None)
        if declared:                          # sub-ensamblaje declarado: un paso por grupo
            key, tok, is_hw = ("grp", declared), declared, False
        else:
            comp = catalog.get(getattr(f, "component", None) or "")
            if comp is not None:              # herraje: agrupa por familia
                key, tok, is_hw = ("hw", comp.category), comp.category, True
            else:                             # a medida: token inicial del nombre (split _ y espacio)
                name = (f.name or fid).strip()
                tok = (name.split() or [name])[0].split("_")[0]
                key, is_hw = ("p", tok.lower()), False
        g = groups.get(key)
        if g is None:
            label = tok if key[0] == "grp" else _pretty(tok, is_hw)
            g = groups[key] = {"label": label, "ids": [], "first": 1 << 30, "is_hw": is_hw,
                               "declared": key[0] == "grp"}
        g["ids"].append(fid)
        g["first"] = min(g["first"], cmd_index.get(getattr(f, "command_id", ""), 1 << 30))
    return sorted(groups.values(), key=lambda g: (g["first"], g["label"]))


# --------------------------------------------------------------- orden por soporte (V7.2b A)
def _support_depth(scene: dict, grounded: set, supports: list, level: list) -> dict:
    """Profundidad de SOPORTE por pieza (0 = toca el piso). Relajación de camino más
    largo: una pieza va 1 nivel por encima de su soporte más profundo; una unión de
    mismo-nivel (soldadura lateral) iguala. Solo alcanza las piezas con camino a tierra."""
    depth = {fid: 0 for fid in grounded}
    for _ in range(len(scene) + 1):
        changed = False
        for lo, hi in supports:
            base = depth.get(lo)
            if base is not None and depth.get(hi, -1) < base + 1:
                depth[hi] = base + 1
                changed = True
        for a, b in level:
            da, db = depth.get(a), depth.get(b)
            if da is not None and (db is None or db < da):
                depth[b] = da
                changed = True
            elif db is not None and (da is None or da < db):
                depth[a] = db
                changed = True
        if not changed:
            break
    return depth


def order_by_support(scene: dict, stages: list[dict]) -> list[dict]:
    """Reordena los PASOS por el grafo de soporte dirigido (V7.2b): una pieza se monta
    DESPUÉS de todo lo que la soporta (tierra → arriba), así las chumaceras van antes
    que su eje y el eje antes que el motor que cuelga de él. Dentro del mismo nivel
    topológico conserva el orden por sub-ensamblaje (sort ESTABLE). Fusiona los pasos
    HUÉRFANOS (una pieza suelta a-medida) al paso del sub-ensamblaje al que se une en
    el grafo. Sin estructura (ni soporte ni soldadura lateral) devuelve los pasos
    intactos → fallback al orden del log."""
    from apolo.assembly.autodetect import detect_structure

    det = detect_structure(scene)
    supports = [(f["a"], f["b"]) for f in det["fasteners"] if f.get("direction") == "soporte"]
    level = [(f["a"], f["b"]) for f in det["fasteners"] if f.get("direction") == "mismo_nivel"]
    if not supports and not level:
        return stages  # sin señal de estructura: no reordenar
    grounded = {g["feature"] for g in det["grounds"]}
    depth = _support_depth(scene, grounded, supports, level)
    neigh: dict[str, set] = {}
    for a, b in supports + level:
        neigh.setdefault(a, set()).add(b)
        neigh.setdefault(b, set()).add(a)
    stage_of = {fid: st for st in stages for fid in st["ids"]}

    def _is_subassembly(st: dict) -> bool:
        # destino de fusión válido: un sub-ensamblaje REAL (grupo declarado o paso de
        # varias piezas), nunca otra pieza suelta ni una familia de herraje (accesoria)
        return bool(st.get("declared") or (len(st["ids"]) > 1 and not st["is_hw"]))

    survivors: list[dict] = []
    for st in stages:
        if len(st["ids"]) == 1 and not st["is_hw"] and not st.get("declared"):
            fid = st["ids"][0]
            cands = [stage_of[n] for n in neigh.get(fid, ())
                     if n in stage_of and stage_of[n] is not st and _is_subassembly(stage_of[n])]
            if cands:  # fusiona al vecino-soporte de menor rango (declarado gana)
                target = min(cands, key=lambda c: (
                    0 if c.get("declared") else 1,
                    min((depth.get(i, 1 << 30) for i in c["ids"]), default=1 << 30),
                ))
                target["ids"].append(fid)
                continue  # el huérfano deja de ser un paso propio
        survivors.append(st)

    maxd = max(depth.values(), default=0)

    def rank(st: dict) -> int:
        ds = [depth[i] for i in st["ids"] if i in depth]
        return min(ds) if ds else maxd + 1  # piezas sin soporte conocido → al final

    return sorted(survivors, key=rank)  # estable: mismo rango conserva el orden previo


# --------------------------------------------------------------- instrucción por familia (V7.2b A)
_INSTR = {
    "estructura": "Presentar, escuadrar y soldar al conjunto (cordón de filete donde esté dimensionado).",
    "chumacera": "Montar sobre el eje, alinear y atornillar la chumacera/rodamiento a su base.",
    "apernado": "Atornillar a las piezas ya montadas y apretar en cruz al par indicado.",
    "catalogo": "Instalar el componente según las indicaciones del fabricante.",
    "herraje": "Instala el herraje de este paso y fíjalo a las piezas ya montadas según el modelo.",
    "generico": "Monta y fija estas piezas sobre el conjunto, respetando las cotas del despiece.",
}
_BEARING_CATS = {"rodamientos", "chumaceras"}
_PROFILE_CATS = {"perfiles", "perfiles_abiertos", "tubos_estructurales", "tubos_circulares"}
_BOLT_CATS = {"pernos", "tornilleria"}


def _family_head(stage: dict, scene: dict, catalog) -> str:
    """Texto de instrucción según la FAMILIA del paso (V7.2b A.2): perfiles soldados,
    herraje apernado, chumaceras, catálogo o genérico — leído de nombres y catálogo."""
    ids = stage["ids"]
    cats: set = set()
    for fid in ids:
        comp = catalog.get(getattr(scene.get(fid), "component", None) or "")
        if comp is not None:
            cats.add(comp.category)
    text = (stage.get("label") or "").lower() + " " + " ".join(
        (getattr(scene.get(fid), "name", "") or "").lower() for fid in ids)
    bearing = bool(cats & _BEARING_CATS) or any(
        k in text for k in ("chumacera", "rodamiento", "ucp", "ucf", "ucfl"))
    if stage["is_hw"]:
        if cats & _BOLT_CATS or "torniller" in text or "perno" in text:
            return _INSTR["apernado"]
        if bearing:
            return _INSTR["chumacera"]
        return _INSTR["herraje"]
    if bearing:
        return _INSTR["chumacera"]
    if cats & _PROFILE_CATS or any(k in text for k in (
            "larguero", "travesa", "perfil", "tubo", "poste", "pata", "marco",
            "bastidor", "viga", "columna", "miembro", "cordón", "cordon")):
        return _INSTR["estructura"]
    if cats:
        return _INSTR["catalogo"]
    return _INSTR["generico"]


def _scene_bbox(scene: dict):
    """Caja envolvente del modelo visible (para la cámara estable del manual)."""
    import numpy as np

    lo = np.array([np.inf] * 3)
    hi = np.array([-np.inf] * 3)
    for f in scene.values():
        if not getattr(f, "visible", True):
            continue
        bb = f.shape.bounding_box()
        lo = np.minimum(lo, [bb.min.X, bb.min.Y, bb.min.Z])
        hi = np.maximum(hi, [bb.max.X, bb.max.Y, bb.max.Z])
    return (lo, hi)


def _embed(model: SheetModel, png: bytes, box: tuple) -> None:
    """Embebe el PNG centrado en `box`=(x,y,w,h) respetando su aspecto (lee el IHDR)."""
    pw, ph = struct.unpack(">II", png[16:24])
    aspect = (pw / ph) if ph else 1.0
    bx, by, bw, bh = box
    if bw / bh > aspect:
        w, h = bh * aspect, bh
    else:
        w, h = bw, bw / aspect
    model.images.append(Image(bx + (bw - w) / 2, by + (bh - h) / 2, w, h, png))


def _wrap(text: str, width: int) -> list[str]:
    out, line = [], ""
    for w in text.split():
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        out.append(line)
    return out


def _step_rows(stage_scene: dict) -> list[str]:
    """Líneas «N× descripción · norma» de las piezas/herraje que se añaden en el paso."""
    from apolo.library.bom import bom_from_scene

    rows = []
    for r in bom_from_scene(stage_scene):
        norma = f" · {r['norma']}" if r.get("norma") else ""
        rows.append(f"{r['cantidad']}x  {str(r['descripcion'])[:30]}{norma}")
    return rows


def _instruction(stage: dict, scene: dict, catalog, n_new: int, n_done: int, n_total: int) -> str:
    head = _family_head(stage, scene, catalog)
    return f"{head} Se añaden {n_new} pieza(s); montadas {n_done} de {n_total}."


def _cover_page(W: float, H: float, *, project_name: str, png: bytes, stages: list[dict],
                totals: dict, base_meta: dict, sheet: str) -> SheetModel:
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    m.labels.append(Label(16, H - 26, "MANUAL DE ENSAMBLAJE", 9.0, anchor="start"))
    m.labels.append(Label(16, H - 38, str(project_name)[:54], 5.0, anchor="start"))
    _embed(m, png, (16, 56, (W - 20) * 0.55, H - 108))
    rx = 16 + (W - 20) * 0.55 + 12
    m.labels.append(Label(rx, H - 52, "SECUENCIA DE MONTAJE", 4.2, anchor="start"))
    y = H - 62
    for i, s in enumerate(stages):
        m.labels.append(Label(rx, y, f"Paso {i + 1}.  {s['label']}  ({len(s['ids'])} pza)", 3.0, anchor="start"))
        y -= 5.4
    y -= 4
    m.labels.append(Label(rx, y, f"Total: {totals['piezas']} piezas · {totals['herraje']} de herraje"
                                  f" · {len(stages)} pasos", 3.0, anchor="start"))
    draw_title_block(m, {**base_meta, "sheet_no": 1, "n_sheets": len(stages) + 1})
    return m


def _step_page(W: float, H: float, *, step_no: int, n_steps: int, page_no: int, n_pages: int,
               stage: dict, rows: list[str], instruction: str, png: bytes,
               base_meta: dict) -> SheetModel:
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    _embed(m, png, (16, 54, (W - 20) * 0.58, H - 70))
    rx = 16 + (W - 20) * 0.58 + 10
    m.labels.append(Label(rx, H - 28, f"PASO {step_no} DE {n_steps}", 6.5, anchor="start"))
    m.labels.append(Label(rx, H - 39, str(stage["label"])[:34], 5.0, anchor="start"))
    m.lines.append(Line(rx, H - 43, W - 14, H - 43, "frame"))
    y = H - 52
    for ln in _wrap(instruction, 42):
        m.labels.append(Label(rx, y, ln, 3.0, anchor="start"))
        y -= 4.6
    y -= 3
    m.labels.append(Label(rx, y, "PIEZAS DE ESTE PASO", 3.4, anchor="start"))
    y -= 6
    for r in rows[:14]:
        m.labels.append(Label(rx, y, r, 2.7, anchor="start"))
        y -= 4.6
    if len(rows) > 14:
        m.labels.append(Label(rx, y, f"… y {len(rows) - 14} más", 2.6, anchor="start"))
    draw_title_block(m, {**base_meta, "sheet_no": page_no, "n_sheets": n_pages})
    return m


def assembly_manual(scene: dict, *, commands: list[dict], project_name: str = "Sin título",
                    sheet: str = "A3", meta: dict | None = None, colors: dict | None = None,
                    size_px: int = 700) -> list[SheetModel]:
    """Manual de ensamblaje paso a paso: [portada con secuencia + 1 lámina por PASO]. Cada paso
    muestra el render acumulado (lo nuevo resaltado, lo previo en gris) + piezas/herraje + nota.
    Deriva la secuencia del log de comandos (orden de armado) + familias de catálogo."""
    from apolo.library.catalog import CATALOG
    from apolo.library.cutlist import dominant_material, hardware_schedule, scene_weight_kg
    from ..kernel.render import render_scene_png

    W, H = SHEETS.get(sheet, SHEETS["A3"])
    vis = {fid: f for fid, f in scene.items() if getattr(f, "visible", True)}
    if not vis:
        raise ValueError("Escena vacía: nada que ensamblar")
    stages = assembly_steps(scene, commands, CATALOG)
    stages = order_by_support(vis, stages)  # V7.2b A: orden por soporte + fusión de huérfanos
    if not stages:
        raise ValueError("No se pudo derivar la secuencia de ensamblaje")
    bbox = _scene_bbox(vis)

    base_meta = {
        "project": project_name, "drawing_no": (meta or {}).get("drawing_no", "—"),
        "scale": "—", "sheet": sheet, "material": dominant_material(vis) or "—",
        "finish": "—", "weight_kg": scene_weight_kg(vis), "tolerance": "—", "units": "mm",
        "drawn_by": "", "checked_by": "", "approved_by": "",
        "date": (meta or {}).get("date", date.today().isoformat()),
        "revisions": (meta or {}).get("revisions", []),
    }

    pages: list[SheetModel] = []
    # portada: render del modelo COMPLETO + tabla de contenidos
    cover_png = render_scene_png(vis, view="iso", size_px=size_px, clean=True, colors=colors,
                                 frame_bbox=bbox)
    totals = {"piezas": len(vis), "herraje": sum(h["cantidad"] for h in hardware_schedule(vis))}
    pages.append(_cover_page(W, H, project_name=project_name, png=cover_png, stages=stages,
                             totals=totals, base_meta=base_meta, sheet=sheet))

    # un paso por grupo: render acumulado con lo nuevo resaltado y cámara estable
    n = len(stages)
    cumulative: dict = {}
    for k, st in enumerate(stages, start=1):
        for fid in st["ids"]:
            cumulative[fid] = scene[fid]
        png = render_scene_png(dict(cumulative), view="iso", size_px=size_px,
                               highlight_ids=list(st["ids"]), clean=True, colors=colors,
                               frame_bbox=bbox)
        stage_scene = {fid: scene[fid] for fid in st["ids"]}
        instr = _instruction(st, scene, CATALOG, len(st["ids"]), len(cumulative), len(vis))
        pages.append(_step_page(
            W, H, step_no=k, n_steps=n, page_no=k + 1, n_pages=n + 1, stage=st,
            rows=_step_rows(stage_scene), instruction=instr, png=png, base_meta=base_meta,
        ))
    return pages
