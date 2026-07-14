"""Inferencia del PROCESO de fabricación de una pieza y su acabado superficial
(ISO 1302) — para poblar el cajetín («Acabado») y las notas de taller de la lámina
por pieza (V7.2 «último kilómetro del plano»).

Funciones PURAS: reciben una Feature y su Component de catálogo (o None), NUNCA un
Document. No hay campo canónico de proceso en el modelo → se INFIERE de señales que
ya existen: categoría de catálogo (perfil/tubo → sierra), ajuste ISO 286 en el nombre
(«Ø35 h7» → torneado), espesor mínimo del bbox (≤6 mm sin catálogo → chapa) y el
material resuelto (para la nota de protección superficial).
"""

from __future__ import annotations

import re

# categorías de catálogo que se cortan a medida en sierra (perfiles y tubos)
_PROFILE_CATS = {"perfiles", "perfiles_abiertos", "tubos_estructurales", "tubos_circulares"}
# ajuste ISO 286 en el nombre («Ø35 h7», «Ø 20 k6») → superficie torneada de asiento
_FIT_RE = re.compile(r"Ø\s*\d+(?:\.\d+)?\s+(?:js|[gfhkmnp])\d", re.I)

# Ra (µm) representativo por familia de proceso (ISO 1302, acabado GENERAL)
_RA = {"torneado": 3.2, "mecanizado": 6.3, "sierra": 12.5, "laser_pliegue": 12.5}


def _sorted_dims(feat) -> tuple[float, float, float] | None:
    """Dimensiones del bbox ordenadas (mm), (menor, media, mayor). None si no mide."""
    try:
        bb = feat.shape.bounding_box()
        d = sorted((bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z))
        return (round(d[0], 1), round(d[1], 1), round(d[2], 1))
    except Exception:
        return None


def _is_profile_box(dims: tuple[float, float, float]) -> bool:
    """Un sólido a-medida (sin catálogo) con UNA dimensión mucho mayor que las otras
    dos y una sección estructural (≤ 200 mm) es un PERFIL/barra cortado a medida →
    se aserra (no se mecaniza). Umbrales conservadores para no morder bloques macizos:
    largo ≥ 300 mm, esbeltez largo/sección ≥ 4, sección ≤ 200 mm."""
    s0, s1, s2 = dims
    return s2 >= 300.0 and s1 > 0.0 and s2 / s1 >= 4.0 and s1 <= 200.0


def _wall_thickness(feat) -> float | None:
    """Espesor de pared EFECTIVO (mm) = 2·V/A — robusto para chapa PLEGADA, cuyo
    bbox mínimo es la altura de la pestaña, no el espesor del material. Una placa
    plana da su espesor; un bloque macizo da un valor grande. None si no mide."""
    try:
        vol = float(feat.shape.volume)
        area = float(feat.shape.area)
        return (2.0 * vol / area) if area > 0 else None
    except Exception:
        return None


def _sheet_is_bent(feat) -> bool:
    """Chapa CON pliegue real: su volumen llena mucho menos que su bbox (forma en
    L/U/C). Una placa PLANA llena su bbox (fill ≈ 1) → corte láser sin plegado."""
    try:
        bb = feat.shape.bounding_box()
        bbvol = (bb.max.X - bb.min.X) * (bb.max.Y - bb.min.Y) * (bb.max.Z - bb.min.Z)
        vol = float(feat.shape.volume)
        return bbvol > 0.0 and (vol / bbvol) < 0.75
    except Exception:
        return False


def infer_process(feat, component=None, *, has_fit: bool = False) -> dict:
    """Proceso de fabricación de `feat` → {"key", "label", "ra"}.

    Orden de señales (la primera que aplica gana): catálogo perfil/tubo → corte en
    sierra (o en inglete si `feat.miter`); ajuste ISO 286 (en el nombre o `has_fit`
    de la capa API) → torneado; espesor mínimo del bbox ≤6 mm SIN catálogo → corte
    láser (+ plegado SOLO si el sólido está plegado de verdad); sección esbelta
    constante SIN catálogo → perfil aserrado (V7.2b E: cazan los largueros/patas
    modelados como `create_box`, que antes caían a «mecanizado»); resto → mecanizado."""
    name = getattr(feat, "name", "") or ""
    cat = getattr(component, "category", None)
    if cat in _PROFILE_CATS:
        ingl = bool(getattr(feat, "miter", None))
        return {"key": "sierra", "ra": _RA["sierra"],
                "label": "corte en inglete" if ingl else "corte en sierra"}
    if has_fit or _FIT_RE.search(name):
        return {"key": "torneado", "label": "torneado", "ra": _RA["torneado"]}
    dims = _sorted_dims(feat)
    twall = _wall_thickness(feat)  # espesor efectivo 2·V/A (robusto a chapa plegada)
    if component is None and twall is not None and twall <= 6.0:
        bent = _sheet_is_bent(feat)  # E2: «+ plegado» solo con pliegue real
        return {"key": "laser_pliegue", "ra": _RA["laser_pliegue"],
                "label": "corte láser + plegado" if bent else "corte láser"}
    if component is None and dims is not None and _is_profile_box(dims):
        return {"key": "sierra", "label": "corte en sierra · perfil laminado", "ra": _RA["sierra"]}
    return {"key": "mecanizado", "label": "mecanizado / corte general", "ra": _RA["mecanizado"]}


def finish_label(ra: float) -> str:
    """Rótulo de acabado general para el cajetín («Ra 12.5»)."""
    return f"Ra {ra:g}"


def shop_notes(feat, component, material: str) -> list[str]:
    """Notas de taller de una lámina por pieza (V7.2): tolerancia general ISO 2768 +
    proceso/acabado ISO 1302 + romper aristas + protección superficial según material.
    Todas < 60 caracteres (el bloque de notas trunca ahí). Criterio simple, 3-4 notas."""
    proc = infer_process(feat, component)
    out = [
        "Tolerancias sin indicar: ISO 2768-mK · cotas en mm.",
        f"Proceso: {proc['label']} · acabado gral Ra {proc['ra']:g}.",
        "Romper aristas vivas 0.5×45°, sin rebabas.",
    ]
    name = (getattr(feat, "name", "") or "").lower()
    mat = (material or "").lower()
    if "inox" in mat or "galv" in name:
        out.append("Material inox/galvanizado: no pintar.")
    elif mat == "acero" or "a36" in name:
        out.append("Protección: primer + esmalte (acero estructural).")
    return out
