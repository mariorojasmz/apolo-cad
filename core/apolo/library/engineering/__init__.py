"""Motor de cálculo de ingeniería (analítico, puro) — Frente A.

Paquete de funciones PURAS de dimensionamiento/verificación con factores de
seguridad: faja sobre cama (belt), uniones apernadas (bolts), cordones de
soldadura (welds), vida de rodamientos (bearings), pandeo de columnas
(buckling), estabilidad al vuelco (stability), reparto de cargas por el grafo
de conectividad (loads) y propiedades de masa (mass).

Filosofía: analítico barato y HONESTO (hipótesis declaradas), no FEA. Ninguna
función recibe `Document` — solo dicts/escena — para respetar la frontera
library ⟂ doc. Las consume `rules.py` (conveyor) y `engineering/report.py`
(chequeo estructural universal).

`structural.py` (viga/eje) queda aparte y sin cambios: estas funciones lo
complementan, no lo reemplazan.
"""

from __future__ import annotations

from .bearings import L10_MIN_H, L10_TARGET_H, l10_hours
from .belt import (
    BED_FRICTION,
    STARTUP_FACTOR,
    belt_power_kw,
    belt_pull_n,
    belt_startup_torque_nm,
    estimate_belt_kg,
)
from .bolts import (
    GRADES,
    TENSILE_AREA_MM2,
    bolt_shear_capacity_n,
    bolt_tension_capacity_n,
    bolt_utilization,
)
from .buckling import BUCKLING_FS, euler_critical_load_n, rect_tube_min_inertia_mm4
from .fits import (
    SEAT_RECOMMENDATIONS,
    bearing_seat_check,
    fit_check,
    fit_limits,
    format_fit_label,
    parse_fit,
)
from .loads import hanging_load_kg
from .stability import convex_hull_2d, hull_margin_mm
from .welds import weld_allowable_mpa, weld_throat_stress_mpa

__all__ = [
    "BED_FRICTION",
    "BUCKLING_FS",
    "GRADES",
    "L10_MIN_H",
    "L10_TARGET_H",
    "STARTUP_FACTOR",
    "SEAT_RECOMMENDATIONS",
    "TENSILE_AREA_MM2",
    "bearing_seat_check",
    "belt_power_kw",
    "belt_pull_n",
    "belt_startup_torque_nm",
    "bolt_shear_capacity_n",
    "bolt_tension_capacity_n",
    "bolt_utilization",
    "convex_hull_2d",
    "estimate_belt_kg",
    "euler_critical_load_n",
    "fit_check",
    "fit_limits",
    "format_fit_label",
    "parse_fit",
    "hanging_load_kg",
    "hull_margin_mm",
    "l10_hours",
    "rect_tube_min_inertia_mm4",
    "weld_allowable_mpa",
    "weld_throat_stress_mpa",
]
