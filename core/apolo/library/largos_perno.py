"""Largos COMERCIALES de un perno: la serie de la norma y lo que el catálogo trae (plan
puerta-de-publicacion, D3). Puro (lee el catálogo, nunca un `Document`).

- **Serie**: los largos nominales preferidos de ISO 4017/4014 (cabeza hexagonal, rosca total o
  parcial) y de ISO 4762 (cabeza cilíndrica Allen); un perno de 47 mm no existe aunque quepa.
- **Catálogo**: la ficha de un perno «a medida» (`PERNO-HEX-*`, `PERNO-M*`) declara el rango
  que se compra (`largo_min_mm`/`largo_max_mm` en su YAML); una ficha de largo fijo
  (`DIN912-M8`: `length`) sólo trae ése. Lo que la ficha no declara no se compra.

Lo usan el sello de `join_bolted` (criterio 3: ningún respaldo silencioso a 200 mm) y el control
de agarre de la puerta de publicación.
"""

from __future__ import annotations

#: Largos nominales preferidos (mm) de ISO 4017 / ISO 4014 / ISO 4762.
SERIE_ISO = [8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100, 110, 120,
             130, 140, 150, 160, 180, 200, 220, 240]
_TOL = 0.5  # mm: un largo medido de la geometría «es» el nominal a ±0,5 mm


def _es_madera(comp) -> bool:
    return comp is not None and comp.category == "tornilleria_madera"


def serie(ref: str | None = None, catalog=None) -> list[float]:
    """La serie nominal: la de ISO para pernos; la de DIN 571 para el tornillo para madera."""
    from .catalog import CATALOG
    from .fijacion import TIRAFONDO_LARGOS

    catalog = catalog if catalog is not None else CATALOG
    if _es_madera(catalog.get(ref or "") if ref else None):
        return [float(s) for s in TIRAFONDO_LARGOS]
    return [float(s) for s in SERIE_ISO]


def en_serie(largo: float, ref: str | None = None, catalog=None) -> bool:
    return any(abs(largo - s) <= _TOL for s in serie(ref, catalog))


def largos_catalogo(ref: str | None, catalog=None) -> list[float]:
    """Los largos que el catálogo vende para `ref` ([] si la ficha no existe o no lo dice)."""
    from .catalog import CATALOG

    catalog = catalog if catalog is not None else CATALOG
    comp = catalog.get(ref or "") if ref else None
    if comp is None:
        return []
    if _es_madera(comp):  # DIN 571: los largos de `fijacion.TIRAFONDO_LARGOS` (espejo del YAML)
        return serie(ref, catalog)
    specs = comp.specs or {}
    if specs.get("length") is not None:
        return [float(specs["length"])]
    lo, hi = specs.get("largo_min_mm"), specs.get("largo_max_mm")
    if lo is None or hi is None:
        return []
    return [float(s) for s in SERIE_ISO if float(lo) - _TOL <= s <= float(hi) + _TOL]


def en_catalogo(ref: str | None, largo: float, catalog=None) -> bool:
    return any(abs(largo - s) <= _TOL for s in largos_catalogo(ref, catalog))


def ref_para(d: float, cabeza: str) -> str:
    """La ficha de catálogo de un perno a medida por su Ø y su cabeza («hex» → DIN 933,
    «allen» → DIN 912 de largo a medida)."""
    m = f"M{d:g}"
    return f"PERNO-HEX-{m}" if cabeza == "hex" else f"PERNO-{m}"


def largo_comercial(ref: str, minimo: float, catalog=None) -> float | None:
    """El largo de catálogo más corto ≥ `minimo`, o None si ninguno alcanza."""
    return next((s for s in largos_catalogo(ref, catalog) if s >= minimo - 1e-6), None)
