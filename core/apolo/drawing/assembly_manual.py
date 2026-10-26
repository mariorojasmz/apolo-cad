"""Manual de ENSAMBLAJE paso a paso (instructivo de montaje, estilo Inventor/IKEA).

A diferencia del plano de conjunto (GA: despiece + cédula + globos, una sola lámina), el
manual EXPLICA el armado: una página por PASO, con el render 3D sombreado de lo que va
montado hasta ahí (las piezas NUEVAS del paso resaltadas en color, lo previo en gris fantasma),
las piezas/herraje que se añaden y la instrucción.

Con la estructura DECLARADA, la secuencia llega hecha (`stages`): la de montaje de
`services/montaje.py`, la misma del video de la tienda. Si no, se deriva del propio modelo:
- **orden de construcción** = el log de comandos (`Document.commands`): lo que el usuario modeló
  primero es la base; respeta ese orden de armado real.
- **agrupación en pasos humanos**: el herraje se agrupa por familia de catálogo (todas las
  bisagras juntas, todas las correderas…); las piezas a medida por el token inicial de su nombre
  (Marco / H1 / Vidrio / Parteluz / Tornillería…). Cada grupo = un paso, ordenado por su primera
  aparición en el log. Heurística transparente y refinable.

Las fotos las dibuja UNA escena VTK viva con cámara ESTABLE (las piezas aparecen en su sitio
final), fuera de `STATE_LOCK`: las tres fases están en `manual_fotos.py` (plan manual-rapido).
"""

from __future__ import annotations

import re
import struct

from .sheet import Image, Label, Line, SheetModel
from .tabla import alto_linea_mm, piso_tabla
from .texto_medido import Parrafo, columna, encajar
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


def order_by_support(scene: dict, stages: list[dict], catalog=None) -> list[dict]:
    """Reordena los PASOS por el grafo de soporte dirigido (V7.2b): una pieza se monta
    DESPUÉS de todo lo que la soporta (tierra → arriba), así las chumaceras van antes
    que su eje y el eje antes que el motor que cuelga de él. Dentro del mismo nivel
    topológico DESEMPATA por familia (V7.2c): rodamientos/chumaceras ANTES que
    motores/reductores — el motor de eje hueco desliza sobre un eje que las chumaceras
    ya sostienen, y detect_structure los deja al MISMO nivel (el eje cruza el bore →
    mismo_nivel, no soporte). A igual familia, conserva el orden por sub-ensamblaje
    (sort ESTABLE). Fusiona los pasos HUÉRFANOS (una pieza suelta a-medida) al paso del
    sub-ensamblaje al que se une en el grafo. Sin estructura (ni soporte ni soldadura
    lateral) devuelve los pasos intactos → fallback al orden del log."""
    from apolo.assembly.autodetect import detect_structure

    if catalog is None:
        from apolo.library.catalog import CATALOG
        catalog = CATALOG
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

    # a IGUAL rango de soporte, la familia decide: rodamientos/chumaceras (0) antes que
    # lo neutro (1) antes que motores/reductores (2) — criterio de montaje real
    return sorted(survivors, key=lambda st: (rank(st), _family_order(st, scene, catalog)))


_MOTOR_TOKENS = ("motor", "reductor", "nmrv", "sinfín", "sinfin", "gearmotor")
_BEARING_TOKENS = ("chumacera", "rodamiento", "ucp", "ucf", "ucfl")


def _family_order(stage: dict, scene: dict, catalog) -> int:
    """Prioridad de montaje por familia para DESEMPATAR pasos al mismo nivel de soporte
    (V7.2c): 0 = rodamientos/chumaceras (se montan primero, sostienen el eje), 1 =
    neutro, 2 = motores/reductores (cuelgan del eje que las chumaceras ya sostienen).

    Guarda de BRACKET (cierre de la re-auditoría V7.2c): la clasificación es POR PIEZA y
    una ménsula/soporte nombrada por lo que sostiene («Ménsula soporte motorreductor» en
    la Estructura) NO clasifica el paso como la familia de lo sostenido — sin la guarda,
    la Estructura del 38 caía a familia «motores» y la Tornillería de anclaje le ganaba
    el desempate (paso 1 con texto físicamente imposible). Misma doctrina que el
    _BRACKET_RE de infer_process."""
    from apolo.drawing.process import _BRACKET_RE

    cats: set = set()
    for fid in stage["ids"]:
        comp = catalog.get(getattr(scene.get(fid), "component", None) or "")
        if comp is not None:
            cats.add(comp.category)

    def hit(s: str, tokens) -> bool:
        return any(k in s for k in tokens) and not _BRACKET_RE.search(s)

    label = (stage.get("label") or "").lower()
    names = [(getattr(scene.get(fid), "name", "") or "").lower() for fid in stage["ids"]]
    if bool(cats & _BEARING_CATS) or hit(label, _BEARING_TOKENS) or any(
            hit(n, _BEARING_TOKENS) for n in names):
        return 0
    if hit(label, _MOTOR_TOKENS) or any(hit(n, _MOTOR_TOKENS) for n in names):
        return 2
    return 1


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
# tornillería MODELADA a-medida (no catálogo): en la faja 38 los pernos de anclaje son
# boolean_op «Perno anclaje M12 + arandela», sin `component` → el paso NO es is_hw y el
# texto genérico se colaba (faltaba «apretar en cruz»). Amplía el matcher por nombre.
_BOLT_TOKENS = ("torniller", "perno", "tornillo", "tuerca", "arandela", "anclaje")
# el matcher de TORNILLERÍA va ANCLADO al inicio del nombre (cierre re-auditoría V7.2c):
# «Perno anclaje M12» ES tornillería; «Eje fijo (roscado p/ perno)» o «Placa portapernos»
# solo la MENCIONAN — con substring heredaban «apretar en cruz» sin serlo.
_BOLT_START_RE = re.compile(r"^\s*(?:torniller|perno|tornillo|tuerca|arandela)", re.IGNORECASE)
_STRUCT_TOKENS = ("larguero", "travesa", "perfil", "tubo", "poste", "pata", "marco",
                  "bastidor", "viga", "columna", "miembro", "cordón", "cordon")
# componentes ATORNILLADOS que suelen viajar en un paso estructural (soldar) pero se
# fijan con pernos: se les añade una línea de «apretar en cruz» sin robar la instrucción
_MIXED_BOLTED_TOKENS = _BOLT_TOKENS + ("nivelador", "anti-giro", "antigiro", "anti giro")


def _family_head(stage: dict, scene: dict, catalog) -> str:
    """Texto de instrucción según la FAMILIA del paso (V7.2b A.2, ampliado V7.2c):
    perfiles soldados, herraje/tornillería apernado (catálogo O a-medida por nombre),
    chumaceras, catálogo o genérico — leído de nombres y catálogo. Un paso estructural
    que además trae piezas atornilladas (pies niveladores, disco anti-giro) suma una
    línea de «apretar en cruz» sin perder su instrucción de soldadura."""
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
    # tornillería SOLO si alguna pieza (o el label) EMPIEZA por un token de tornillería
    # (cierre re-auditoría V7.2c: «Eje fijo (roscado p/ perno)» no es tornillería)
    bolt = bool(cats & _BOLT_CATS) or _BOLT_START_RE.match(stage.get("label") or "") is not None or any(
        _BOLT_START_RE.match(getattr(scene.get(fid), "name", "") or "") for fid in ids)
    structure = bool(cats & _PROFILE_CATS) or any(k in text for k in _STRUCT_TOKENS)
    if stage["is_hw"]:
        if bolt:
            return _INSTR["apernado"]
        if bearing:
            return _INSTR["chumacera"]
        return _INSTR["herraje"]
    if bearing:
        return _INSTR["chumacera"]
    if structure:  # estructura primero: un paso mayormente soldado no lo roba un perno
        base = _INSTR["estructura"]
        if any(k in text for k in _MIXED_BOLTED_TOKENS):  # paso mixto: hay atornillados
            base += " Los componentes atornillados (pies, disco anti-giro) se fijan con pernos: apretar en cruz al par."
        return base
    if bolt:  # tornillería a-medida (sin catálogo, no is_hw): también «apretar en cruz»
        return _INSTR["apernado"]
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
    """Líneas «N× descripción · norma» de las piezas/herraje que se añaden en el paso,
    ordenadas de ABAJO hacia ARRIBA (V7.6 E5): dentro de un paso el montador coloca
    primero lo que queda debajo — el residual «orden fino intra-grupo» que el manual
    declaraba desde V7.2b. El criterio es la z de la BASE de cada pieza (no su centro:
    una pieza alta con base baja se monta antes que una plana apoyada encima)."""
    from apolo.library.bom import bom_from_scene

    def _z_base(fid: str) -> float:
        try:
            return float(stage_scene[fid].shape.bounding_box().min.Z)
        except Exception:
            return 0.0

    orden = {fid: i for i, fid in enumerate(sorted(stage_scene, key=_z_base))}
    rows = []
    for r in bom_from_scene(stage_scene):
        norma = f" · {r['norma']}" if r.get("norma") else ""
        rows.append((orden.get(r.get("_rep"), 1 << 20),
                     f"{r['cantidad']}x  {r['descripcion']}{norma}"))  # entera: la lámina la parte
    return [txt for _k, txt in sorted(rows, key=lambda t: t[0])]


_SIZE_RE = re.compile(r"\bM(\d{1,2})\b")


def _torque_note(stage: dict, scene: dict, catalog) -> str:
    """«Par de apriete: M12 → 91 N·m (llave 18 mm)» para las métricas presentes en el
    paso (V7.6 E5): el par se CALCULA de la precarga de diseño, no se copia de una tabla
    genérica. Sin métrica identificable no se emite nota — un par inventado aprieta de
    más o de menos, y ambas cosas rompen la unión. Métricas ordenadas y sin repetir."""
    from apolo.library.engineering.bolts import tightening_torque_nm, wrench_size_mm

    sizes: set[str] = set()
    for fid in stage["ids"]:
        feat = scene.get(fid)
        nombre = getattr(feat, "name", "") or ""
        comp = catalog.get(getattr(feat, "component", None) or "")
        cand = f"{nombre} {getattr(comp, 'ref', '') if comp is not None else ''}"
        m = _SIZE_RE.search(cand)
        if m:
            sizes.add(f"M{m.group(1)}")
    partes = []
    for s in sorted(sizes, key=lambda x: int(x[1:]))[:3]:
        try:
            partes.append(f"{s} → {tightening_torque_nm(s):.0f} N·m "
                          f"(llave {wrench_size_mm(s):g} mm)")
        except KeyError:
            continue                      # métrica sin tabla → se omite, no se inventa
    if not partes:
        return ""
    return " Par de apriete (8.8, rosca seca): " + " · ".join(partes) + "."


def _instruction(stage: dict, scene: dict, catalog, n_new: int, n_done: int, n_total: int) -> str:
    head = _family_head(stage, scene, catalog)
    union = f" {stage['union']}" if stage.get("union") else ""  # secuencia de montaje (D8)
    return (f"{head}{union}{_torque_note(stage, scene, catalog)} "
            f"Se añaden {n_new} pieza(s); montadas {n_done} de {n_total}.")


def _cover_page(W: float, H: float, *, project_name: str, png: bytes, stages: list[dict],
                totals: dict, base_meta: dict, sheet: str) -> SheetModel:
    m = SheetModel(W, H)
    m.rect(10, 10, W - 20, H - 20, "frame")
    m.labels.append(Label(16, H - 26, "MANUAL DE ENSAMBLAJE", 9.0, anchor="start"))
    size, (titulo,) = encajar(str(project_name), W - 32.0, 5.0)  # medido (antes, cortado a 54)
    m.labels.append(Label(16, H - 38, titulo, size, anchor="start"))
    _embed(m, png, (16, 56, (W - 20) * 0.55, H - 108))
    rx = 16 + (W - 20) * 0.55 + 12
    m.labels.append(Label(rx, H - 52, "SECUENCIA DE MONTAJE", 4.2, anchor="start"))
    # la secuencia y el total, medidos y SOBRE el cajetín (antes, un manual largo en A4 bajaba
    # hasta la tabla de revisiones): si no entran, la columna baja de escala
    pasos = [Parrafo(f"Paso {i + 1}.  {s['label']}  ({len(s['ids'])} pza)", 3.0, 5.4)
             for i, s in enumerate(stages)]
    pasos.append(Parrafo(f"Total: {totals['piezas']} piezas · {totals['herraje']} de herraje"
                         f" · {len(stages)} pasos", 3.0, 5.4, antes=4))
    columna(m, rx, H - 62, pasos, W - 14 - rx, piso_tabla(base_meta))
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
    ancho = W - 14 - rx
    # el rótulo de la etapa, MEDIDO (antes, cortado a 34): un renglón a 5 si cabe; si no, dos
    # renglones entre «PASO N DE M» y la raya
    size, lineas = encajar(str(stage["label"]), ancho, 5.0, 2, alto=2 * alto_linea_mm(4.5))
    for k, ln in enumerate(lineas):
        m.labels.append(Label(rx, H - 39 + (len(lineas) - 1 - k) * alto_linea_mm(size), ln, size,
                              anchor="start"))
    m.lines.append(Line(rx, H - 43, W - 14, H - 43, "frame"))
    y = H - 52
    for ln in _wrap(instruction, 42):
        m.labels.append(Label(rx, y, ln, 3.0, anchor="start"))
        y -= 4.6
    y -= 3
    m.labels.append(Label(rx, y, "PIEZAS DE ESTE PASO", 3.4, anchor="start"))
    y -= 6
    _filas_del_paso(m, rx, y, ancho, rows, piso_tabla(base_meta))
    draw_title_block(m, {**base_meta, "sheet_no": page_no, "n_sheets": n_pages})
    return m


def _filas_del_paso(m: SheetModel, x: float, y: float, ancho: float, rows: list[str],
                    piso: float, tope: int = 14) -> None:
    """Las filas «N×  descripción · norma» del paso, ENTERAS: partidas por ancho medido (lo que
    sigue, bajo la descripción) y, hasta `tope`, mientras entren sobre el cajetín; lo que no,
    «… y N más» (antes cada descripción se cortaba a 30 y la lista a 14 sin mirar el piso)."""
    from .tabla import ancho_mm, partir

    paso, aviso = 4.6, 2.6
    puestas = 0
    for r in rows[:tope]:
        cab = r.split("  ", 1)[0] + "  " if "  " in r else ""
        primera = [r] if ancho_mm(r, 2.7) <= ancho else partir(r, ancho, 2.7)  # cabe: tal cual
        lineas = primera[:1] + (partir(" ".join(primera[1:]), ancho - ancho_mm(cab, 2.7), 2.7)
                                if len(primera) > 1 else [])
        resto = len(rows) - puestas - 1
        if y - (len(lineas) - 1) * paso - (paso if resto else 0.0) < piso:
            break
        for k, ln in enumerate(lineas):
            m.labels.append(Label(x + (ancho_mm(cab, 2.7) if k else 0.0), y, ln, 2.7, anchor="start"))
            y -= paso
        puestas += 1
    if len(rows) > puestas:
        m.labels.append(Label(x, y, f"… y {len(rows) - puestas} más", aviso, anchor="start"))


def assembly_manual(scene: dict, *, commands: list[dict], project_name: str = "Sin título",
                    sheet: str = "A3", meta: dict | None = None, colors: dict | None = None,
                    size_px: int = 700, stages: list[dict] | None = None,
                    apariencias: dict | None = None,
                    definiciones: dict | None = None) -> list[SheetModel]:
    """Manual de ensamblaje paso a paso: [portada con secuencia + 1 lámina por PASO]. Cada paso
    muestra el render acumulado (lo nuevo resaltado, lo previo en gris) + piezas/herraje + nota.
    `stages` = la secuencia de montaje ya derivada del grafo de uniones ({label, ids, is_hw,
    union}: `services/montaje.py`, D8 de video-montaje-pulido); sin ella, del log de comandos +
    familias de catálogo + soporte autodetectado.

    Atajo de las fases de `manual_fotos` para quien es dueño de su documento (tests, CLI).
    Dentro de la API NO se usa: el endpoint extrae bajo `STATE_LOCK` y dibuja fuera (llamar a
    esto sosteniendo `STATE_LOCK` tomaría `RENDER_LOCK` en el orden prohibido)."""
    from .manual_fotos import componer_manual, extraer_manual, fotos_manual, teselar_manual

    ex = extraer_manual(scene, commands=commands, project_name=project_name, sheet=sheet,
                        meta=meta, colors=colors, size_px=size_px, stages=stages,
                        apariencias=apariencias, definiciones=definiciones)
    teselar_manual(ex)
    return componer_manual(ex, fotos_manual(ex))
