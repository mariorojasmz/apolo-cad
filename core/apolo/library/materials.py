"""Registro de materiales: densidad, patrón de rayado de sección y resolución del
material de una pieza (catálogo o a-medida).

Fuente ÚNICA para BOM enriquecido, lista de corte, peso del cajetín y el rayado de
los cortes en los planos. Para piezas de catálogo el material sale de
``Component.specs['material']``; para piezas a-medida (carpintería, cordones, etc.)
se infiere por palabras clave del nombre, con `madera`/`acero` como defaults del
vertical. Es una heurística honesta: el agente o el usuario pueden anular el material.
"""

from __future__ import annotations

import re

# kg/mm³ (densidad). Acero como referencia ISO; madera/vidrio nuevos respecto a
# robotics/model.py (que solo tenía acero y aluminio por categoría).
DENSITY_KG_MM3 = {
    "acero": 7.85e-6,
    "acero inoxidable": 8.0e-6,
    "aluminio": 2.70e-6,
    "laton": 8.5e-6,
    "zinc": 7.1e-6,
    "madera": 5.0e-7,   # ~500 kg/m³ (pino/MDF aprox.)
    "vidrio": 2.5e-6,   # ~2500 kg/m³
    "pvc": 1.4e-6,      # ~1400 kg/m³ (banda transportadora PVC, perfil plástico)
    "caucho": 1.5e-6,   # ~1500 kg/m³ (engomado/lagging de tambor, goma)
    "carton": 1.4e-7,   # ~140 kg/m³ densidad a granel de un bulto/paquete (caja+contenido)
}
DEFAULT_DENSITY = 7.85e-6  # acero

# patrón de rayado de sección por material (lo consumen los exportadores)
HATCH = {
    "madera": "madera",      # veta/diagonal suave
    "vidrio": "vidrio",      # líneas finas muy juntas
    "acero": "ansi31",       # diagonal 45 estándar
    "acero inoxidable": "ansi31",
    "aluminio": "ansi31",
    "laton": "ansi31",
}
DEFAULT_HATCH = "ansi31"

# módulo de Young E (MPa = N/mm²) y límite elástico (MPa) por material, para los
# chequeos estructurales (flecha de viga, flexión de eje). Valores nominales típicos.
YOUNG_MPA = {
    "acero": 200000.0,
    "acero inoxidable": 193000.0,
    "aluminio": 69000.0,
    "laton": 100000.0,
    "zinc": 108000.0,
    "madera": 11000.0,   # pino/MDF aprox. (flexión)
    "vidrio": 70000.0,
    "pvc": 3000.0,
    "caucho": 50.0,
}
DEFAULT_YOUNG = 200000.0  # acero
YIELD_MPA = {
    "acero": 250.0,             # A36
    "acero inoxidable": 215.0,  # AISI 304
    "aluminio": 240.0,          # 6061-T6 aprox.
    "laton": 200.0,
    "madera": 40.0,
}
DEFAULT_YIELD = 250.0  # acero A36

# palabras clave para inferir el material de piezas a-medida (sin componente de catálogo)
_GLASS_WORDS = ("vidrio", "cristal", "glass")
_STEEL_WORDS = (
    "acero", "perfil", "tubo", "tornillo", "eje", "tambor", "rodillo", "motor",
    "riel", "corredera", "cordon", "soldadura", "chapa", "pasador", "clavija",
)
_WOOD_WORDS = (
    "larguero", "travesa", "peinazo", "hoja", "tablero", "tabla", "marco", "jamba",
    "dintel", "junquillo", "duela", "montante", "parteluz", "batiente", "moldura",
)
# polímeros/goma: banda PVC y engomado de tambor son plástico/caucho, no acero
_PVC_WORDS = ("pvc", "poliuretano", "polimero")
_RUBBER_WORDS = ("engomado", "lagging", "caucho", "goma")
# señales de metalurgia que ganan sobre las palabras de carpintería: grado de
# acero, inox, o una sección de tubo de 3 cotas (p. ej. 80x40x3, 50x50x2).
_METAL_HINT = re.compile(r"\b(a36|ss400|st37|sae\s*1045|1045)\b|inox|\d+\s*[x×]\s*\d+\s*[x×]\s*\d+")


def _norm(material: str | None) -> str:
    """Normaliza una cadena de material a una clave conocida ('' si no se reconoce)."""
    m = (material or "").lower()
    if "inox" in m:
        return "acero inoxidable"
    for key in DENSITY_KG_MM3:
        if key in m:
            return key
    return ""


def density(material: str | None) -> float:
    """Densidad kg/mm³ del material (DEFAULT_DENSITY si no se reconoce)."""
    return DENSITY_KG_MM3.get(_norm(material), DEFAULT_DENSITY)


def hatch_pattern(material: str | None) -> str:
    """Nombre del patrón de rayado de sección para el material dado."""
    return HATCH.get(_norm(material), DEFAULT_HATCH)


def young_modulus(material: str | None) -> float:
    """Módulo de Young E (MPa) del material (DEFAULT_YOUNG si no se reconoce)."""
    return YOUNG_MPA.get(_norm(material), DEFAULT_YOUNG)


def yield_strength(material: str | None) -> float:
    """Límite elástico (MPa) del material (DEFAULT_YIELD si no se reconoce)."""
    return YIELD_MPA.get(_norm(material), DEFAULT_YIELD)


def resolve_material(feat, catalog: dict | None = None, default: str = "acero") -> str:
    """Material de una feature. Prioridad: override explícito (``feat.material`` /
    set_material) → material de catálogo (``specs['material']``) → heurística por
    nombre. `default` para lo no reconocido (lo fija el vertical del proyecto)."""
    override = getattr(feat, "material", None)
    if override:
        return override
    component = getattr(feat, "component", None)
    if component and catalog:
        comp = catalog.get(component)
        specs = getattr(comp, "specs", None) if comp is not None else None
        mat = (specs or {}).get("material") if specs else None
        if mat:
            return mat
    name = (getattr(feat, "name", "") or "").lower()
    if any(w in name for w in _GLASS_WORDS):
        return "vidrio"
    if any(w in name for w in _RUBBER_WORDS):
        return "caucho"
    if any(w in name for w in _PVC_WORDS):
        return "pvc"
    # una señal explícita de metal (grado/inox/sección de tubo) gana sobre las
    # palabras de carpintería: "Larguero 80x40x3 A36" es acero, no madera.
    if _METAL_HINT.search(name):
        return _norm(name) or "acero"
    if any(w in name for w in _STEEL_WORDS):
        return "acero"
    if any(w in name for w in _WOOD_WORDS):
        return "madera"
    return default
