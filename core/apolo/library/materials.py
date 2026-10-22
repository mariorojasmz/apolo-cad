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
    # las especies van ANTES de "madera": `_norm` devuelve la primera clave que sea
    # subcadena, así "madera copaiba" resuelve a copaiba y no al genérico.
    "copaiba": 6.5e-7,  # ~650 kg/m³ (Copaifera sp., IIAP Perú 0.61-0.65)
    "madera": 5.0e-7,   # ~500 kg/m³ (pino/MDF aprox.)
    "vidrio": 2.5e-6,   # ~2500 kg/m³
    "pvc": 1.4e-6,      # ~1400 kg/m³ (banda transportadora PVC, perfil plástico)
    "caucho": 1.5e-6,   # ~1500 kg/m³ (engomado/lagging de tambor, goma)
    "carton": 1.4e-7,   # ~140 kg/m³ densidad a granel de un bulto/paquete (caja+contenido)
    # cable flexible modelado en 3D: cobre + aislamiento y cubierta de PVC. Criterio de diseño:
    # ~2300 kg/m³ medio (el CABLE-4G2.5 del catálogo, 0,18 kg/m con Ø 10,5 mm, da ~2100; un
    # unipolar H07V-K 2,5 mm², ~2700). Un cable no se fabrica: el costeo no lo cobra (V8.1 F4).
    "cable": 2.3e-6,
}
DEFAULT_DENSITY = 7.85e-6  # acero

# patrón de rayado de sección por material (lo consumen los exportadores)
HATCH = {
    "copaiba": "madera",
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
    "copaiba": 11000.0,  # MOE flexión medido 112 000 kg/cm² (IIAP Perú)
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
    # La madera no fluye: rompe. Para las especies tabulamos el MOR (tensión de
    # ROTURA en flexión), así que el "FS" que reportan los chequeos es contra
    # rotura y el criterio de aceptación es FS >= 4 (no >= 1.5 como en acero).
    "copaiba": 72.0,     # MOR flexión 736 kg/cm² (IIAP Perú) → σ_adm = MOR/4 ≈ 18 MPa
    "madera": 40.0,
}
DEFAULT_YIELD = 250.0  # acero A36

# costo de MATERIA PRIMA (USD/kg) por material — REFERENCIAL (mercado LatAm aprox.,
# 2026): actualizar con el proveedor/región para cotizar en firme. Lo consume
# `library/costing.py` (costeo de piezas a medida y fallback de catálogo sin `cost`).
COST_PER_KG_USD = {
    "acero": 1.5,
    "acero inoxidable": 5.5,
    "aluminio": 4.5,
    "laton": 8.0,
    "zinc": 3.0,
    "copaiba": 1.6,     # aserrada y seca, referencial LatAm
    "madera": 1.2,
    "vidrio": 2.0,
    "pvc": 2.5,
    "caucho": 3.5,
    "carton": 0.5,
}
DEFAULT_COST_PER_KG = 1.5  # acero

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
#: ROL cable eléctrico («Cable motor 4x2.5 mm2 …», «Cable setas 4x1 mm2: tablero -> seta»): ni
#: acero por «motor» ni madera por «tablero» (V8.1 F4). Anclado al inicio del rol («Soporte del
#: cable» no es cable); un cable de acero (de izar, de un tensor) es acero.
CABLE = "cable"
_CABLE_ROLE = re.compile(r"^cables?\b")
_CABLE_METAL = re.compile(r"acero|inox|alambre|galvaniz")
#: caucho por el ROL (F6 de la puerta de publicación): el recubrimiento de un tambor se llama
#: «Engomado…», «Lagging…» o «Recubrimiento/Revestimiento/Forro del tambor…» (este último salía
#: ACERO por «tambor»). Anclado al inicio del rol: «Tambor motriz engomado» es el TAMBOR (acero);
#: un recubrimiento cerámico, metálico o de poliuretano no es caucho.
_RUBBER_WORDS = re.compile(r"\b(caucho|gomas?|neopreno)\b")  # «goma» no muerde «engomado»
_RUBBER_ROLE = re.compile(r"^(engomad\w*|lagging)\b")
_LINING_ROLE = re.compile(r"^(recubrimiento|revestimiento|forro)s?\b.*\b(tambor|polea|rodillo)")
_LINING_OTHER = re.compile(r"cer[aá]mic|acero|inox|met[aá]l|poliuretano|pvc|uhmw")
# ROL banda (transportadora) = polímero aunque el nombre no diga «PVC». Se mira el ROL, no el
# nombre entero: «Faja de banda · Larguero (1)» trae «banda» del super-comando y «Cama de la
# banda» sólo la MENCIONA. Un metal explícito gana («Banda de malla de acero»).
_BELT_ROLE = re.compile(r"^bandas?\b")
_BELT_METAL = re.compile(r"acero|inox|met[aá]l|alambre")
# señales de metalurgia que ganan sobre las palabras de carpintería: grado de
# acero, inox, o una sección de tubo de 3 cotas (p. ej. 80x40x3, 50x50x2).
_METAL_HINT = re.compile(r"\b(a36|ss400|st37|sae\s*1045|1045)\b|inox|\d+\s*[x×]\s*\d+\s*[x×]\s*\d+")


def piece_role(name: str | None) -> str:
    """ROL de una pieza: lo que sigue al último « · » (convención rol-primero; un
    super-comando nombra «{comando} · {rol}» e `insert_project` antepone la instancia)."""
    return (name or "").split("·")[-1].strip()


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


def has_yield(material: str | None) -> bool:
    """True si el límite elástico del material está TABULADO (no un default). El FEA
    lo exige: caer a 250 MPa en silencio sería mentir en el factor de seguridad."""
    return _norm(material) in YIELD_MPA


def cost_per_kg(material: str | None) -> float:
    """Costo de materia prima (USD/kg) del material — referencial."""
    return COST_PER_KG_USD.get(_norm(material), DEFAULT_COST_PER_KG)


def _es_caucho(rol: str) -> bool:
    if _RUBBER_ROLE.match(rol) or _RUBBER_WORDS.search(rol):
        return True
    return bool(_LINING_ROLE.match(rol)) and not _LINING_OTHER.search(rol)


def resolve_material(feat, catalog: dict | None = None, default: str | None = None) -> str:
    """Material de una feature. Prioridad: override explícito (``feat.material`` /
    set_material) → material de catálogo (``specs['material']``) → heurística por
    nombre → `default`, el material del VERTICAL (`Document.default_material()`).

    Guarda del vertical (una sola fuente: BOM, masa, costeo, apariencia, sello de `join_bolted`):
    la palabra de CARPINTERÍA del nombre («Larguero», «Travesaño», «Marco», «Tablero») no decide
    madera cuando el vertical se CONOCE: en madera ya es el default y en una máquina de acero
    esos roles son acero («Escuadra desmontable del travesaño de cama» salía madera en la BOM de
    una faja, F6). `default=None` = vertical DESCONOCIDO (quien no tiene el documento): la
    palabra de carpintería decide como siempre y lo no reconocido es acero.

    Los matchers de polímero, caucho y vidrio miran el ROL (`piece_role`), no el nombre entero:
    el prefijo de un super-comando o de un `insert_project` («Faja PVC · Tapa…») no decide."""
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
    rol = piece_role(name)
    if _CABLE_ROLE.match(rol) and not _CABLE_METAL.search(name):
        return CABLE
    if any(w in rol for w in _GLASS_WORDS):
        return "vidrio"
    if _es_caucho(rol):
        return "caucho"
    if any(w in rol for w in _PVC_WORDS):
        return "pvc"
    # antes que las palabras de acero que sólo MENCIONA («Banda (sobre tambor motriz)») y que
    # la sección de 3 cotas («Banda 500x6000x4»)
    if _BELT_ROLE.match(rol) and not _BELT_METAL.search(name):
        return "pvc"
    # una señal explícita de metal (grado/inox/sección de tubo) gana sobre las
    # palabras de carpintería: "Larguero 80x40x3 A36" es acero, no madera.
    if _METAL_HINT.search(name):
        return _norm(name) or "acero"
    if any(w in name for w in _STEEL_WORDS):
        return "acero"
    if default is None and any(w in name for w in _WOOD_WORDS):
        return "madera"
    return default or "acero"


def resolve_material_vertical(feat, catalog: dict | None = None, default: str = "acero") -> str:
    """`resolve_material` con el vertical CONOCIDO (alias histórico: la guarda vive allí). La
    usan la apariencia y el sello de `join_bolted` (plan union-en-perfil-hueco, D4)."""
    return resolve_material(feat, catalog, default or "acero")


def es_madera(material: str | None) -> bool:
    """¿Es una madera (genérica o especie)? La que se raya como madera en los planos."""
    return HATCH.get(_norm(material)) == "madera"
