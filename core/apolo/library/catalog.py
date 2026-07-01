"""Catálogo de componentes del vertical (manejo de materiales).

Data-driven: las definiciones viven en `library/data/*.yaml` y se cargan con
`loader.load_catalog()`. La geometría la producen los builders genéricos de
`library/builders.py`. Es la base de la BOM y del comando insert_component. Los
componentes "cortables" (cuttable) aceptan una longitud a medida; su peso es
kg/m, el resto kg/unidad.

Convenciones de geometría (las mismas del kernel): centrado en el origen,
eje Z hacia arriba; los elementos alargados se extruyen a lo largo de Z.

Esta capa expone una interfaz estable (Component, CATALOG, build_component,
catalog_payload, CATEGORIES) para que los consumidores (API, agente, BOM,
conveyor, models) no dependan de cómo se almacenan los datos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Component:
    ref: str
    name: str
    category: str
    description: str
    specs: dict
    weight: float  # kg/ud, o kg/m si cuttable
    cuttable: bool = False
    default_length: float | None = None
    builder: Callable = field(repr=False, default=None)  # (length|None) -> shape


from .loader import load_catalog  # noqa: E402  (necesita Component ya definido)

CATALOG: dict[str, Component] = load_catalog()

# Orden de presentación de categorías. Las originales primero; las nuevas al
# final para no reordenar la UI/tests existentes.
CATEGORIES = [
    "perfiles", "rodillos", "tambores", "motorreductores", "patas", "guardas", "sensores",
    "rodamientos", "tornilleria", "guias_lineales", "transmision",
    "chumaceras", "topes", "pies_niveladores",
    "tubos_estructurales", "tubos_circulares", "perfiles_abiertos",
    "tensores_trotadora", "variadores", "tableros", "mandos",
    "bisagras", "tiradores", "correderas", "tornilleria_madera",
    "cerraduras", "imanes_topes",
    "rieles_corredera", "correderas_colgantes",
    "motorreductores_sinfin",
]


def build_component(ref: str, length: float | None = None):
    """Construye la geometría de un componente del catálogo (centrada en origen)."""
    comp = CATALOG.get(ref)
    if comp is None:
        raise ValueError(f"No existe el componente '{ref}' en el catálogo")
    if comp.cuttable:
        cut = float(length if length is not None else comp.default_length)
        if cut <= 0:
            raise ValueError(f"Longitud inválida para {ref}: {cut}")
        return comp.builder(cut), cut
    return comp.builder(None), None


def refs_in_category(category: str) -> list[str]:
    """Referencias de una categoría, en orden de definición del catálogo."""
    return [ref for ref, c in CATALOG.items() if c.category == category]


def category_refs_sorted(category: str, spec_key: str) -> list[str]:
    """Referencias de una categoría ordenadas ascendentemente por una spec numérica."""
    refs = refs_in_category(category)
    return sorted(refs, key=lambda r: CATALOG[r].specs.get(spec_key, 0))


def catalog_payload(category: str | None = None, names_only: bool = False) -> list[dict]:
    """Catálogo completo o filtrado. `category` filtra por categoría;
    `names_only` devuelve solo ref/name/category (payload ligero)."""
    comps = [c for c in CATALOG.values() if not category or c.category == category]
    if names_only:
        return [{"ref": c.ref, "name": c.name, "category": c.category} for c in comps]
    return [
        {
            "ref": c.ref,
            "name": c.name,
            "category": c.category,
            "description": c.description,
            "specs": c.specs,
            "weight": c.weight,
            "cuttable": c.cuttable,
            "default_length": c.default_length,
        }
        for c in comps
    ]
