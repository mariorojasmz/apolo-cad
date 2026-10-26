"""El peso de una pieza de CATÁLOGO según su ficha (plan V8.9, § Presostato y masa por carrera con
ficha; pendiente 9 de la F7). PURO: lee la escena y el catálogo, nunca un `Document`.

- `peso_de_ficha(comp, cut)`: la pieza ENTERA. Cortable → kg/m × largo; con `specs.peso_por_mm_kg`
  (un cilindro neumático: la ficha da el peso en carrera 0 y lo que suma cada mm) → `weight` +
  por_mm × carrera (`cut_length` = la carrera); si no, `weight`.
- `partes_de_cilindros(scene)`: el peso de la ficha de un cilindro es el del cilindro COMPLETO
  (cuerpo, pistón y vástago: la masa móvil que publica Festo por 10 mm es un vástago macizo de
  acero). `create_pneumatic_cylinder` lo parte en `{cmd}_cuerpo` (con la ref) y `{cmd}_vastago`
  (sin ref, que antes pesaba por volumen → el vástago se contaba dos veces). Aquí el vástago pesa
  la masa MÓVIL de la ficha (`masa_movil_base_kg` + `masa_movil_por_mm_kg` × carrera) y el cuerpo
  el resto: la suma es la ficha, cada parte con su centro de masa.

La BOM no usa `partes_de_cilindros`: compra el cilindro entero en la fila del cuerpo (el vástago
va en su `incluye`, `incluidas.py`). Las masas del conjunto (`engineering/mass.py`,
`cutlist.scene_weight_kg`) sí.
"""

from __future__ import annotations

from .catalog import CATALOG
from .incluidas import vastagos_incluidos

#: `fuente` de la masa de las dos partes de un cilindro (la que lee `feature_mass`)
FUENTE = "catálogo"


def peso_de_ficha(comp, cut) -> float:
    """kg de UNA pieza de catálogo entera, según su ficha."""
    if comp.cuttable and cut:
        return comp.weight * (cut / 1000.0)
    por_mm = (comp.specs or {}).get("peso_por_mm_kg")
    if por_mm and cut:
        return comp.weight + float(por_mm) * float(cut)
    return comp.weight


def masa_movil(comp, carrera) -> float | None:
    """kg que se mueven con el vástago (pistón + vástago) de un cilindro con esa carrera, de su
    ficha neumática; None si la ref no es un cilindro."""
    neu = getattr(comp, "neumatico", None)
    if neu is None or neu.tipo != "cilindro":
        return None
    m = neu.modelo
    return float(m["masa_movil_base_kg"]) + float(m["masa_movil_por_mm_kg"]) * float(carrera or 0.0)


def partes_de_cilindros(scene: dict) -> dict[str, float]:
    """{id: kg} del cuerpo y del vástago de cada cilindro de la escena cuya ficha da el peso por
    carrera: cuerpo = ficha − masa móvil, vástago = masa móvil. Un cilindro sin `peso_por_mm_kg`
    (o con una masa móvil que no cabe en su peso) no entra: sus piezas pesan como antes."""
    out: dict[str, float] = {}
    for vastago, cuerpo in vastagos_incluidos(scene).items():
        f = scene[cuerpo]
        comp = CATALOG[f.component]
        if not (comp.specs or {}).get("peso_por_mm_kg"):
            continue
        total = peso_de_ficha(comp, f.cut_length)
        movil = masa_movil(comp, f.cut_length)
        if movil is None or not 0.0 < movil < total:
            continue
        out[cuerpo] = total - movil
        out[vastago] = movil
    return out
