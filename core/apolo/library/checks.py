"""Detección de interferencias entre sólidos de la escena.

Prefiltro por solape de cajas envolventes y después intersección booleana
OCCT solo en las parejas candidatas. El contacto cara-a-cara (volumen ~0)
no se considera interferencia.
"""

from __future__ import annotations

MIN_VOLUME_MM3 = 1.0
MAX_PAIRS = 400


def _bboxes_overlap(a, b, margin: float = 0.01) -> bool:
    return (
        a.min.X <= b.max.X + margin and b.min.X <= a.max.X + margin
        and a.min.Y <= b.max.Y + margin and b.min.Y <= a.max.Y + margin
        and a.min.Z <= b.max.Z + margin and b.min.Z <= a.max.Z + margin
    )


def interference_report(
    scene: dict,
    only: list[str] | None = None,
    shapes_override: dict | None = None,
    exclude_pairs: set[frozenset] | None = None,
    exclude_ids: set[str] | None = None,
) -> dict:
    """shapes_override permite analizar formas posadas (colisión en pose).
    exclude_pairs descarta parejas que se tocan por diseño (eslabones unidos
    por una junta). exclude_ids saca features del análisis por completo
    (p. ej. tornillería/rodamientos asentados en su alojamiento)."""
    feats = [f for f in scene.values()
             if f.visible and not getattr(f, "is_guide", False) and (only is None or f.id in only)]
    if exclude_ids:
        feats = [f for f in feats if f.id not in exclude_ids]

    def shape_of(f):
        return shapes_override.get(f.id, f.shape) if shapes_override else f.shape

    boxes = {f.id: shape_of(f).bounding_box() for f in feats}

    candidates = []
    for i, a in enumerate(feats):
        for b in feats[i + 1:]:
            if exclude_pairs and frozenset((a.id, b.id)) in exclude_pairs:
                continue
            if _bboxes_overlap(boxes[a.id], boxes[b.id]):
                candidates.append((a, b))
    truncated = len(candidates) > MAX_PAIRS
    candidates = candidates[:MAX_PAIRS]

    collisions = []
    for a, b in candidates:
        try:
            inter = shape_of(a) & shape_of(b)
            volume = float(inter.volume) if inter is not None else 0.0
        except Exception:
            volume = 0.0
        if volume > MIN_VOLUME_MM3:
            collisions.append(
                {
                    "a": a.id,
                    "nombre_a": a.name,
                    "b": b.id,
                    "nombre_b": b.name,
                    "volumen_mm3": round(volume, 1),
                }
            )

    collisions.sort(key=lambda c: -c["volumen_mm3"])
    return {
        "solidos": len(feats),
        "parejas_analizadas": len(candidates),
        "truncado": truncated,
        "interferencias": collisions,
    }


def joint_pairs(doc) -> set[frozenset]:
    """Parejas padre-hijo de las juntas: contacto por diseño, no interferencia."""
    return {frozenset((j["parent"], j["child"])) for j in getattr(doc, "joints", {}).values()}


EXCESS_TOL_MM3 = 50.0  # exceso de solape tolerado sobre el contacto de diseño


def _overlap_volume(sa, sb) -> float:
    if sa is None or sb is None:
        return 0.0
    try:
        if not _bboxes_overlap(sa.bounding_box(), sb.bounding_box()):
            return 0.0
        inter = sa & sb
        return float(inter.volume) if inter is not None else 0.0
    except Exception:
        return 0.0


def interpenetration_report(scene: dict, posed: dict, pairs: set[frozenset],
                            tol: float = EXCESS_TOL_MM3) -> list[dict]:
    """Punto ciego cerrado: para parejas que COMPARTEN junta (excluidas del chequeo
    normal porque se tocan en el conector), detecta si los CUERPOS se interpenetran.
    Compara el solape en la pose actual contra el de la pose de DISEÑO (junta=0, el
    contacto intencional del conector = línea base) y reporta solo el EXCESO. Así un
    par de junta ya no puede esconder dos cuerpos cruzándose (p. ej. dos hojas en una
    bisagra que pivota mal, o una hoja mordiendo la jamba en el pivote)."""
    out: list[dict] = []
    for pair in pairs:
        a, b = tuple(pair)
        fa, fb = scene.get(a), scene.get(b)
        if fa is None or fb is None or not fa.visible or not fb.visible:
            continue
        base = _overlap_volume(fa.shape, fb.shape)
        cur = _overlap_volume(posed.get(a, fa.shape), posed.get(b, fb.shape))
        excess = cur - base
        if excess > tol:
            out.append({
                "a": a, "nombre_a": fa.name, "b": b, "nombre_b": fb.name,
                "volumen_mm3": round(excess, 1), "tipo": "interpenetracion",
            })
    out.sort(key=lambda c: -c["volumen_mm3"])
    return out


HARDWARE_CATS = {"tornilleria", "rodamientos"}


def hardware_ids(doc) -> set[str]:
    """Features cuyo componente es hardware normalizado (tornillería/rodamientos):
    se asientan en su alojamiento por diseño, así que se EXCLUYEN del chequeo de
    interferencias (convención estándar para piezas normalizadas)."""
    from apolo.library.catalog import CATALOG

    out: set[str] = set()
    for fid, feat in getattr(doc, "scene", {}).items():
        ref = getattr(feat, "component", None)
        comp = CATALOG.get(ref) if ref else None
        if comp is not None and comp.category in HARDWARE_CATS:
            out.add(fid)
    return out


def same_command_pairs(doc) -> set[frozenset]:
    """Parejas de sólidos creados por el MISMO super-comando (bastidor,
    transportador, brazo): se tocan/solapan por diseño, no son interferencia."""
    by_cmd: dict[str, list[str]] = {}
    for fid, feat in getattr(doc, "scene", {}).items():
        by_cmd.setdefault(feat.command_id, []).append(fid)
    pairs: set[frozenset] = set()
    for fids in by_cmd.values():
        if len(fids) < 2:
            continue
        for i, a in enumerate(fids):
            for b in fids[i + 1:]:
                pairs.add(frozenset((a, b)))
    return pairs
