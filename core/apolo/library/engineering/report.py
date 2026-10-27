"""Chequeo estructural UNIVERSAL del ensamblaje (Frente A, Fase 4).

A diferencia de `rules.conveyor_engineering_check` (que exige una faja y una
carga), estas reglas aplican a CUALQUIER ensamblaje con uniones declaradas:
- uniones apernadas (utilización del perno vs su capacidad ISO 898-1),
- cordones de soldadura (tensión en garganta vs 0.6·σy del material base),
- vida L10 de rodamientos/chumaceras (C_kN del catálogo),
- pandeo de Euler de las patas,
- estabilidad al vuelco (COG vs huella de apoyo).

La CARGA de cada unión sale del grafo de conectividad (`hanging_load_kg`:
masa que pierde tierra al quitar la arista) — honesto: una unión DIMENSIONADA en
camino redundante se reporta "ok" con nota (la redundancia es favorable y no es
accionable; el reparto exacto exigiría FEA), nunca con un número inventado. Mismo
formato de regla que rules.py ({regla, estado, detalle, recomendacion?, calc?}).

Orquestador puro: recibe dicts (scene/fasteners/grounds/joints/mates), nunca
`Document` — frontera library ⟂ doc. Como en rules.py, cuentan TODAS las piezas,
también las ocultas: la visibilidad es estado de vista, no de diseño.
"""

from __future__ import annotations

# Cada verificación vive en su módulo (partir-nucleo-congelado-ii, D3); esta ruta las
# re-exporta por IDENTIDAD (D6, `tests/test_rutas_viejas.py`).
from ..peso_ficha import partes_de_cilindros
from .mass import feature_mass
from .report_ajustes import _fit_checks  # noqa: F401
from .report_comun import _BEARING_CATS, G, _name  # noqa: F401
from .report_estructura import (  # noqa: F401
    _bearing_checks,
    _buckling_checks,
    _tipping_check,
)
from .report_uniones import _fastener_checks, _weaker_yield  # noqa: F401


def __getattr__(nombre: str):
    """`_SHAFT_FIT_NAME_RE` se compila perezoso en `report_ajustes` (lo reasigna con
    `global`): servirlo por valor dejaría aquí el `None` de antes de compilarlo."""
    if nombre == "_SHAFT_FIT_NAME_RE":
        from . import report_ajustes

        return report_ajustes._SHAFT_FIT_NAME_RE
    raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")


def structure_engineering_check(
    scene: dict,
    fasteners: dict,
    grounds: dict,
    joints: dict,
    mates: dict,
    *,
    catalog: dict | None = None,
    carga_kg: float = 0.0,
    rpm: float | None = None,
    belt_radial_n: float | None = None,
    default_material: str | None = None,
    rodamientos: dict | None = None,
) -> list[dict]:
    """Chequeo estructural del ensamblaje completo (no exige que sea una faja).
    Devuelve reglas en el MISMO formato que conveyor_engineering_check."""
    from ..catalog import CATALOG
    from apolo.assembly.connectivity import build_graph

    catalog = catalog if catalog is not None else CATALOG
    if not scene:
        return []
    graph = build_graph(scene, joints, mates, fasteners, grounds)
    partes = partes_de_cilindros(scene)  # el vástago de un cilindro no pesa dos veces (V8.9)
    masses = {
        fid: feature_mass(f, catalog, default_material, partes.get(fid))["masa_kg"]
        for fid, f in scene.items()
    }
    checks: list[dict] = []
    checks += _fastener_checks(scene, graph, masses, fasteners, catalog)
    checks += _bearing_checks(scene, catalog, carga_kg, rpm, belt_radial_n, rodamientos)
    checks += _fit_checks(scene, fasteners, joints, mates, catalog)
    checks += _buckling_checks(scene, masses, catalog, carga_kg)
    checks += _tipping_check(scene, grounds, catalog, carga_kg, default_material)
    return checks
