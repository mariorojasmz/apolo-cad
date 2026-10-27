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

from contextlib import contextmanager
from contextvars import ContextVar

from apolo.kernel.shapes import is_surface

from ..catalog import CATALOG
from ..materials import density, resolve_material
from ..peso_ficha import FUENTE as PARTE_FUENTE
from ..peso_ficha import partes_de_cilindros, peso_de_ficha


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


#: El memo de la GEOMETRÍA de masa (volumen, caja, COM) de UNA corrida (`memo_de_geometria`): la
#: puerta de publicación pide `feature_mass` ~20 000 veces sobre las mismas formas (cada prueba de
#: sobrantes rehace las reglas de estructura; medido: 229 s en un elevador de 325 piezas). Sólo la
#: geometría: el material, la ficha y la masa se resuelven en cada llamada (cambian sin cambiar la
#: forma). Por `id(shape)` guardando la referencia y verificando `is` (core/apolo/CLAUDE.md); vive
#: lo que dura el `with` del hilo que lo abrió (ContextVar), nunca como estado global.
_MEMO_GEOMETRIA: ContextVar[dict | None] = ContextVar("memo_geometria_masa", default=None)


@contextmanager
def memo_de_geometria():
    """Mientras dura, la geometría de masa de cada forma se calcula una vez (anidable: el de
    afuera manda). Quien lo abre garantiza que ninguna forma se muta adentro (regla del
    regenerate: ningún executor muta un shape in situ)."""
    if _MEMO_GEOMETRIA.get() is not None:
        yield
        return
    token = _MEMO_GEOMETRIA.set({})
    try:
        yield
    finally:
        _MEMO_GEOMETRIA.reset(token)


def _geometria(shape) -> tuple[float, list[float], list[float], list[float] | None]:
    """(volumen, mínimos, máximos, COM real o None) de la forma, del memo si hay uno abierto."""
    memo = _MEMO_GEOMETRIA.get()
    if memo is not None:
        hit = memo.get(id(shape))
        if hit is not None and hit[0] is shape:
            return hit[1]
    try:
        volume = float(shape.volume)
    except Exception:
        volume = 0.0
    mins, maxs = _bbox(shape)
    val = (volume, mins, maxs, _shape_com(shape))
    if memo is not None:
        memo[id(shape)] = (shape, val)
    return val


def feature_mass(feat, catalog: dict | None = None, default_material: str | None = None,
                 parte: float | None = None) -> dict:
    """Propiedades de masa de UNA pieza: masa (catálogo o volumen×densidad),
    material resuelto, COM real y bbox. `parte` = la de la pieza en
    `peso_ficha.partes_de_cilindros(escena)`: el cuerpo y el vástago de un cilindro neumático
    pesan su parte de la ficha (sin ella, el cuerpo pesa el cilindro entero y el vástago su
    volumen; quien SUMA piezas la pasa, o contaría el vástago dos veces)."""
    catalog = catalog if catalog is not None else CATALOG
    material = resolve_material(feat, catalog, default=default_material)
    volume, mins, maxs, com = _geometria(feat.shape)

    comp = catalog.get(getattr(feat, "component", None) or "")
    if parte is not None:
        masa, fuente = parte, PARTE_FUENTE
    elif comp is not None:
        masa = peso_de_ficha(comp, getattr(feat, "cut_length", None))
        fuente = "catálogo"
    else:
        masa = volume * density(material)
        fuente = "volumen"

    com = list(com) if com else [round((mins[i] + maxs[i]) / 2.0, 2) for i in range(3)]
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
    default_material: str | None = None,
    include_hidden: bool = False,
) -> dict:
    """Masa/COM/bbox por pieza y agregado. `ids=None` → todas las VISIBLES
    (coherente con scene_weight_kg); con `ids` explícitos se incluyen aunque
    estén ocultas. `include_hidden=True` → también las ocultas: lo piden los
    CÁLCULOS (vuelco, cargas de anclaje), donde ocultar una pieza para mirar
    dentro no le quita peso a la máquina. Id inexistente → KeyError (el
    endpoint lo vuelve 404)."""
    if ids is not None:
        missing = [i for i in ids if i not in scene]
        if missing:
            raise KeyError(f"Sólido(s) inexistente(s): {', '.join(missing)}")
        items = [(i, scene[i]) for i in ids]
    else:
        items = [(i, f) for i, f in scene.items()
                 if (include_hidden or getattr(f, "visible", True))
                 and not is_surface(f.shape)
                 and not getattr(f, "is_guide", False)]

    piezas = []
    total_m = 0.0
    cx = cy = cz = 0.0
    gmin = [float("inf")] * 3
    gmax = [float("-inf")] * 3
    partes = partes_de_cilindros(scene)
    for fid, feat in items:
        row = {"id": fid, **feature_mass(feat, catalog, default_material, partes.get(fid))}
        piezas.append(row)
        m = row["masa_kg"]
        total_m += m
        cx += m * row["com_mm"][0]
        cy += m * row["com_mm"][1]
        cz += m * row["com_mm"][2]
        mins, maxs = (_geometria(feat.shape)[1:3] if _MEMO_GEOMETRIA.get() is not None
                      else _bbox(feat.shape))  # con el memo, ya está (feature_mass la midió)
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
