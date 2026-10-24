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
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from .electrico.ficha import FichaElectrica
    from .electrico.ficha_tablero import FichaTablero
    from .neumatica.ficha import FichaNeumatica


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
    # anclas LOCALES de la FAMILIA, calculadas por el loader desde los params del builder
    # (`loader.ANCLAS`; p. ej. eje/hileras/fase de un piñón). None = la familia no publica.
    anchors: dict | None = field(repr=False, default=None)
    # ficha eléctrica (bornes, caminos, cargas, fuentes, modelo) del bloque `electrico:` del
    # YAML (`electrico/ficha.py`, plan V8.1 D5). None = pieza mecánica.
    electrico: FichaElectrica | None = field(repr=False, default=None)
    # ficha de ARMADO del bloque `tablero:` (`electrico/ficha_tablero.py`, plan V8.5 A2–A4):
    # interior del gabinete, cara de apoyo, mando de puerta, accesorio acoplado, riel, canaleta.
    tablero: FichaTablero | None = field(repr=False, default=None)
    # ficha NEUMÁTICA del bloque `neumatico:` (`neumatica/ficha.py`, plan V8.9 D2): puertos ISO
    # 5599-3, modelo por tipo con su caudal ISO 6358, o el tubo por metro. None = sin aire.
    neumatico: FichaNeumatica | None = field(repr=False, default=None)
    # NOMBRE del builder y sus params tal como los declara el YAML: los lee la sección de una
    # viga (`engineering/secciones.seccion_catalogo`, plan flecha-de-bastidor F2). Metadato:
    # no cambia la geometría.
    familia: str | None = field(repr=False, default=None)
    params: dict | None = field(repr=False, default=None)
    # zonas de acabado del YAML (`library/zonas.py`, plan seta-de-emergencia D1): la pieza es
    # UN sólido y cada cara sabe su zona (`zonas.zona_por_cara`). None = un solo acabado.
    zonas: tuple | None = field(repr=False, default=None)


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
    "garruchas",
    # catálogo eléctrico de la faja piloto (plan V8.1 D6); pulsadores, pilotos, sensores y
    # gabinetes van en sus categorías de siempre (mandos, sensores, tableros)
    "alimentacion_electrica", "proteccion_electrica", "maniobra_control", "conexion_electrica",
    # catálogo neumático genérico (plan V8.9 D16)
    "cilindros_neumaticos", "valvulas_neumaticas", "aire_comprimido",
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


# Anclas de conexión LOCALES (coords en el frame propio del builder, antes de colocar) por
# CATEGORÍA de catálogo (V6.3b). El executor `insert_component` las transforma a mundo con la
# pose. Las que dependen de los params de cada ref (un piñón: d0, hileras) NO van aquí: las
# calcula el loader por familia (`Component.anchors`, plan cadenas-pinones D6) y
# `component_anchors` las suma a éstas (la de familia gana si repiten nombre).
#  - chumaceras UCP/UCF/UCFL (pillow_block/flange_bearing): eje del rodamiento a lo largo de Y
#    local, origen en el centro del barreno → "centro".
#  - motorreductores sinfín NMRV (worm_gearmotor): eje hueco de salida a lo largo de Y local,
#    origen en el centro → "bore".
#  - garruchas (caster): origen en el centro de la cara SUPERIOR de la placa, la que se atornilla
#    a la máquina; eje +Z = normal saliente de esa cara → "placa" (plan garruchas-catalogo D6).
_CATEGORY_ANCHORS: dict[str, dict] = {
    "chumaceras": {"centro": {"origin": [0.0, 0.0, 0.0], "axis": [0.0, 1.0, 0.0]}},
    "motorreductores_sinfin": {"bore": {"origin": [0.0, 0.0, 0.0], "axis": [0.0, 1.0, 0.0]}},
    "garruchas": {"placa": {"origin": [0.0, 0.0, 0.0], "axis": [0.0, 0.0, 1.0]}},
}


def component_anchors(comp: "Component") -> dict | None:
    """Anclas LOCALES (frame del builder) del componente: las de su categoría más las de su
    familia (calculadas desde sus params), o None si no publica ninguna. Devuelve una COPIA
    fresca (el executor la transforma a mundo y la asigna a la Feature)."""
    tmpl = {**_CATEGORY_ANCHORS.get(comp.category, {}), **(comp.anchors or {})}
    if not tmpl:
        return None
    return {n: {"origin": list(a["origin"]), "axis": list(a["axis"])} for n, a in tmpl.items()}


def refs_in_category(category: str) -> list[str]:
    """Referencias de una categoría, en orden de definición del catálogo."""
    return [ref for ref, c in CATALOG.items() if c.category == category]


def category_refs_sorted(category: str, spec_key: str) -> list[str]:
    """Referencias de una categoría ordenadas ascendentemente por una spec numérica."""
    refs = refs_in_category(category)
    return sorted(refs, key=lambda r: CATALOG[r].specs.get(spec_key, 0))


def catalog_payload(category: str | None = None, names_only: bool = False) -> list[dict]:
    """Catálogo completo o filtrado. `category` filtra por categoría;
    `names_only` devuelve solo ref/name/category (payload ligero). Un componente con ficha
    eléctrica trae además `electrico` (bornes, caminos, cargas y fuentes: lo que el agente
    necesita para cablear con `add_wire`, plan V8.1 F3); lo mecánico no la lleva. La tornillería
    de largo A MEDIDA trae `largos_mm`: los largos que se compran y que `insert_component(length)`
    acepta (F6: el agente no encontraba cómo pedir un M6x20)."""
    from .electrico.ficha import ficha_payload
    from .largos_perno import largos_catalogo
    from .neumatica.ficha import ficha_payload as ficha_neumatica

    def _largos(c) -> dict:
        if c.cuttable or (c.specs or {}).get("length") is not None:
            return {}
        largos = largos_catalogo(c.ref)
        return {"largos_mm": largos} if largos else {}

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
            **({"electrico": ficha_payload(c.electrico)} if c.electrico is not None else {}),
            **({"neumatico": ficha_neumatica(c.neumatico)} if c.neumatico is not None else {}),
            **_largos(c),
        }
        for c in comps
    ]
