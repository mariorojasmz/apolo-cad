"""Propiedades de masa por pieza y del conjunto (para el agente y el vuelco).

Coherente con ``cutlist.scene_weight_kg``: una pieza de CATÁLOGO pesa lo que
dice su ficha (peso/ud, o kg/m × largo si es cortable) — el dato de placa es
más fiel que el volumen del modelo simplificado —; una pieza A MEDIDA pesa
volumen OCCT × densidad de su material (``resolve_material`` + ``density``,
10 materiales — más fino que la densidad por categoría de ``_link_physics``,
que NO se toca porque calibra URDF/MuJoCo).

El COM por pieza es el del sólido real (``shape.center(CenterOf.MASS)``, con
fallback al centro del bbox); el del conjunto, la media ponderada por masa.
Unidades: mm, kg.
"""

from __future__ import annotations

from apolo.kernel.shapes import is_surface

from ..catalog import CATALOG
from ..materials import density, resolve_material


def _shape_com(shape) -> list[float] | None:
    """Centro de masas real del sólido (mm) o None si OCCT no puede."""
    try:
        from build123d import CenterOf

        c = shape.center(CenterOf.MASS)
        return [round(float(c.X), 2), round(float(c.Y), 2), round(float(c.Z), 2)]
    except Exception:
        return None


def _bbox(shape) -> tuple[list[float], list[float]]:
    bb = shape.bounding_box()
    return (
        [float(bb.min.X), float(bb.min.Y), float(bb.min.Z)],
        [float(bb.max.X), float(bb.max.Y), float(bb.max.Z)],
    )


def feature_mass(feat, catalog: dict | None = None, default_material: str = "acero") -> dict:
    """Propiedades de masa de UNA pieza: masa (catálogo o volumen×densidad),
    material resuelto, COM real y bbox."""
    catalog = catalog if catalog is not None else CATALOG
    material = resolve_material(feat, catalog, default=default_material)
    try:
        volume = float(feat.shape.volume)
    except Exception:
        volume = 0.0

    comp = catalog.get(getattr(feat, "component", None) or "")
    if comp is not None:
        cut = getattr(feat, "cut_length", None)
        masa = comp.weight * (cut / 1000.0) if (comp.cuttable and cut) else comp.weight
        fuente = "catálogo"
    else:
        masa = volume * density(material)
        fuente = "volumen"

    mins, maxs = _bbox(feat.shape)
    com = _shape_com(feat.shape) or [round((mins[i] + maxs[i]) / 2.0, 2) for i in range(3)]
    return {
        "name": getattr(feat, "name", ""),
        "material": material,
        "fuente": fuente,
        "volumen_mm3": round(volume, 1),
        "masa_kg": round(float(masa), 4),
        "com_mm": com,
        "bbox_mm": [round(maxs[i] - mins[i], 1) for i in range(3)],
    }


def scene_mass_properties(
    scene: dict,
    catalog: dict | None = None,
    ids: list[str] | None = None,
    default_material: str = "acero",
) -> dict:
    """Masa/COM/bbox por pieza y agregado. `ids=None` → todas las VISIBLES
    (coherente con scene_weight_kg); con `ids` explícitos se incluyen aunque
    estén ocultas. Id inexistente → KeyError (el endpoint lo vuelve 404)."""
    if ids is not None:
        missing = [i for i in ids if i not in scene]
        if missing:
            raise KeyError(f"Sólido(s) inexistente(s): {', '.join(missing)}")
        items = [(i, scene[i]) for i in ids]
    else:
        items = [(i, f) for i, f in scene.items()
                 if getattr(f, "visible", True) and not is_surface(f.shape)]

    piezas = []
    total_m = 0.0
    cx = cy = cz = 0.0
    gmin = [float("inf")] * 3
    gmax = [float("-inf")] * 3
    for fid, feat in items:
        row = {"id": fid, **feature_mass(feat, catalog, default_material)}
        piezas.append(row)
        m = row["masa_kg"]
        total_m += m
        cx += m * row["com_mm"][0]
        cy += m * row["com_mm"][1]
        cz += m * row["com_mm"][2]
        mins, maxs = _bbox(feat.shape)
        for k in range(3):
            gmin[k] = min(gmin[k], mins[k])
            gmax[k] = max(gmax[k], maxs[k])

    com = (
        [round(cx / total_m, 2), round(cy / total_m, 2), round(cz / total_m, 2)]
        if total_m > 0
        else [0.0, 0.0, 0.0]
    )
    return {
        "piezas": piezas,
        "total": {
            "n_piezas": len(piezas),
            "masa_kg": round(total_m, 3),
            "com_mm": com,
            "bbox_mm": [round(gmax[k] - gmin[k], 1) for k in range(3)] if piezas else [0, 0, 0],
        },
    }
