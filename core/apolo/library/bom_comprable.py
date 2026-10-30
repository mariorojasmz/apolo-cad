"""¿La fila de la BOM alcanza para COMPRAR o CORTAR la pieza? (D4 del plan
hallazgos-del-revisor-en-la-puerta, con los ajustes de su F0). Puro: juzga una fila de
`bom.bom_from_scene`, nunca un `Document`; lo usa el ítem `bom.comprable` de la puerta.

Por tipo de fila:
- **compra** (ref `COMPRA`, comercial modelada a mano o grupo «(compra)»): su norma o designación
  (`norma_del_nombre`), la designación MEDIDA (la banda sin fin) o el código de fabricante
  declarado («tipo Marca código», «(compra, Marca código)»). Si se pide por largo (varilla, barra:
  `se_pide_por_largo`), además su largo;
- **ref de catálogo**: la ref ES el código; la cortable (perfil, tubo), además su largo;
- **chapa** con ficha: espesor y desarrollo;
- **a medida** de METAL o de MADERA: la norma del material (D3: el grado o la del genérico por
  forma; la madera, la norma o la clase que escribe su material). El caucho, la lona o el plástico
  sólo piden un material conocido (`material.conocido`, D1). Una fila sin medida, tampoco se corta.

Una ref de catálogo con OTRO material ya sale «… pedir la equivalente» (R2 del plan) y alcanza.
"""

from __future__ import annotations

from .bom_compra import es_de_madera, es_de_metal
from .designacion_comercial import se_pide_por_largo

COMPRA = "COMPRA"
A_MEDIDA = "A-MEDIDA"


def motivo(fila: dict) -> str | None:
    """Por qué la fila NO alcanza para comprar o cortar la pieza, o None si alcanza."""
    from .catalog import CATALOG
    from .materials import CABLE

    ref = fila.get("ref") or ""
    desc = fila.get("descripcion") or ""
    if ref == COMPRA:
        if not (fila.get("norma") or fila.get("designacion") or fila.get("codigo")):
            return ("compra sin norma, designación ni código de fabricante: nombra la norma "
                    "(«… DIN 976-1») o el fabricante y su código («tipo Marca código»)")
        if se_pide_por_largo(desc) and not fila.get("longitud_mm"):
            return "compra que se pide por largo, sin largo"
        return None
    if ref == A_MEDIDA:
        material = fila.get("material") or ""
        if material == CABLE:
            return None  # se compra por metro con su `add_cable` (V8.1)
        if "espesor_mm" in fila and not fila.get("desarrollo_mm"):
            return "chapa sin desarrollo"
        if not fila.get("longitud_mm"):
            return "pieza a medida sin medida de corte"
        if es_de_metal(material) and not fila.get("norma"):
            return (f"a medida de «{material}» sin norma ni grado: declara el acero base («acero "
                    "A36», «inox AISI 304») o compra la pieza «(compra, Marca código)»")
        if es_de_madera(material) and not fila.get("norma"):
            return (f"madera «{material}» sin norma ni clase resistente: declárala en el material "
                    "(«pino radiata C16 (EN 338)», «triplay EN 636-2»)")
        return None
    comp = CATALOG.get(ref)
    if comp is not None and comp.cuttable and not fila.get("longitud_mm"):
        return "perfil de catálogo sin largo"
    return None
