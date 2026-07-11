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


def _min_extent(feat) -> float | None:
    """Espesor mínimo del bbox (mm) — señal de chapa. None si no se puede medir."""
    try:
        bb = feat.shape.bounding_box()
        return round(min(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z), 1)
    except Exception:
        return None


def infer_process(feat, component=None) -> dict:
    """Proceso de fabricación de `feat` → {"key", "label", "ra"}.

    Orden de señales (la primera que aplica gana): catálogo perfil/tubo → corte en
    sierra (o en inglete si `feat.miter`); nombre con ajuste ISO 286 → torneado;
    espesor mínimo del bbox ≤6 mm SIN componente de catálogo → corte láser + plegado
    (chapa); resto → mecanizado/corte general."""
    name = getattr(feat, "name", "") or ""
    cat = getattr(component, "category", None)
    if cat in _PROFILE_CATS:
        ingl = bool(getattr(feat, "miter", None))
        return {"key": "sierra", "ra": _RA["sierra"],
                "label": "corte en inglete" if ingl else "corte en sierra"}
    if _FIT_RE.search(name):
        return {"key": "torneado", "label": "torneado", "ra": _RA["torneado"]}
    tmin = _min_extent(feat)
    if component is None and tmin is not None and tmin <= 6.0:
        return {"key": "laser_pliegue", "label": "corte láser + plegado", "ra": _RA["laser_pliegue"]}
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
