"""Costeo del modelo: BOM costeado + totales para la cotización (Frente B).

Tres fuentes de costo, en orden de fiabilidad (cada fila declara la suya):
1. **`specs.cost`** del catálogo (USD/unidad; en cortables `specs.cost_por_m` USD/m) —
   precios REFERENCIALES anotados en el YAML, a confirmar con proveedor.
2. **Estimación de hardware**: componente de catálogo sin precio → peso × costo del
   material (USD/kg) × factor de manufactura (una pieza comercial vale más que su
   materia prima).
3. **Fabricación a medida**: volumen × densidad × USD/kg del material × factor de
   fabricación (corte + soldadura + acabado + merma).

Excepciones honestas (V8.1 F4 y F4c): una ref ELÉCTRICA sin `cost` no se estima por peso (una
seta de 0,15 kg salía a 0,67 USD) y queda «sin precio», igual que una pieza a medida con ROL
eléctrico (clavija, toma, prensaestopa: `piezas_electricas.es_rol_electrico`); y un cable
modelado en 3D (material «cable») no se fabrica: se compra por metro con `add_cable`, así que su
fila va sin costo para no cobrarlo dos veces. Si ningún `add_cable` lo cubre (lo decide
`services/cobros.py`), la fila lo DICE: ese cable no se cobra en ninguna parte.

Los factores son hipótesis DECLARADAS (aparecen en la fila y en las notas de la
cotización), no números escondidos. Construye sobre `bom_from_scene` (misma
agrupación que el BOM de siempre); no muta nada.
"""

from __future__ import annotations

from .bom import bom_from_scene
from .catalog import CATALOG
from .materials import CABLE, cost_per_kg
from .piezas_electricas import es_rol_electrico

# factor de manufactura para hardware de catálogo SIN precio explícito (una pieza
# comercial — rodamiento, bisagra, tornillo — cuesta ~3× su peso en materia prima)
HW_FACTOR = 3.0
# factor de fabricación para piezas A MEDIDA (corte + soldadura + acabado + merma
# sobre el costo de materia prima)
FAB_FACTOR = 2.5
# piso de precio de un ítem comercial (nada se compra por menos de esto)
MIN_HW_COST = 0.5
SIN_PRECIO_ELECTRICO = ("sin precio: ref eléctrica sin `cost` en el catálogo (no se estima por "
                        "peso); pide cotización al proveedor")
CABLE_3D = ("cable modelado en 3D: se compra por metro (add_cable con ref y largo_m); sin costo "
            "aquí para no cobrarlo dos veces")
CABLE_3D_SIN_CUBRIR = ("cable modelado en 3D SIN add_cable que lo cubra: no se cobra en ninguna "
                       "parte; declara add_cable (ref y largo_m) o lígalo con `piezas`")
SIN_PRECIO_ROL_ELECTRICO = ("sin precio: pieza eléctrica sin ref de catálogo (no se estima por peso "
                            "como {material}); usa una ref del catálogo o pide cotización al proveedor")


def _recorrido(row: dict) -> str:
    largo = row.get("longitud_mm")
    return f" (recorrido {largo / 1000.0:.2f} m)" if largo else ""


def costo_unitario_ref(ref: str) -> float | None:
    """USD por unidad de una ref de catálogo NO cortable (un dispositivo del tablero), o None si
    no tiene precio: lo que se cobraría dos veces si no se liga."""
    comp = CATALOG.get(ref)
    cost = (comp.specs or {}).get("cost") if comp is not None else None
    return float(cost) if cost is not None else None


def _catalog_cost(row: dict) -> tuple[float | None, str]:
    """(costo unitario, fuente) de una fila de catálogo del BOM."""
    comp = CATALOG.get(row.get("ref") or "")
    if comp is None:
        return None, ""
    specs = comp.specs or {}
    cut = row.get("longitud_mm")
    if comp.cuttable and cut and specs.get("cost_por_m"):
        return float(specs["cost_por_m"]) * cut / 1000.0, "catálogo (USD/m)"
    if specs.get("cost") is not None:
        cost = float(specs["cost"])
        if comp.cuttable and cut:
            # `cost` en un cortable sin cost_por_m se interpreta por METRO
            return cost * cut / 1000.0, "catálogo (USD/m)"
        return cost, "catálogo"
    if getattr(comp, "electrico", None) is not None:
        return None, SIN_PRECIO_ELECTRICO
    peso = row.get("peso_unitario_kg") or 0.0
    est = max(peso * cost_per_kg(row.get("material")) * HW_FACTOR, MIN_HW_COST)
    return est, f"estimado (peso × material × {HW_FACTOR:g})"


def _custom_cost(row: dict, sin_cubrir: set | None = None) -> tuple[float | None, str]:
    """(costo unitario, fuente) de una pieza a medida: materia prima × factor. Un cable 3D no se
    fabrica (y dice si algún add_cable lo cobra); una pieza de ROL eléctrico, sin precio."""
    if row.get("material") == CABLE:
        sin = sin_cubrir is not None and row.get("_rep") in sin_cubrir
        return None, (CABLE_3D_SIN_CUBRIR if sin else CABLE_3D) + _recorrido(row)
    if es_rol_electrico(row.get("descripcion")):
        return None, SIN_PRECIO_ROL_ELECTRICO.format(material=row.get("material") or "acero")
    peso = row.get("peso_unitario_kg")
    if peso is None:
        return None, ""
    est = peso * cost_per_kg(row.get("material")) * FAB_FACTOR
    return est, f"fabricación (peso × material × {FAB_FACTOR:g})"


def costed_bom(scene: dict, default_material: str | None = None,
               extra: list[dict] | None = None,
               cables_sin_cubrir: set | None = None) -> list[dict]:
    """Filas del BOM (misma agrupación de `bom_from_scene`) + `costo_ud_usd`,
    `costo_total_usd` y `costo_fuente` por fila. `extra` = filas que la escena no tiene (las
    del tablero eléctrico, `bom_electrico.filas_electricas`), al final; una `sin_largo` queda
    sin costo (no se estima un largo que nadie declaró). `cables_sin_cubrir` = ids de cables 3D
    que ningún add_cable cobra (`services/cobros.py`): su fila lo dice. Sin `extra` ni
    `cables_sin_cubrir`, lo de antes."""
    rows = bom_from_scene(scene, default_material) + [dict(r) for r in extra or ()]
    for row in rows:
        if row.get("sin_largo"):
            cost, fuente = None, "sin largo declarado"
        elif row.get("ref") != "A-MEDIDA":
            cost, fuente = _catalog_cost(row)
        else:
            cost, fuente = _custom_cost(row, cables_sin_cubrir)
        row["costo_ud_usd"] = round(cost, 2) if cost is not None else None
        row["costo_total_usd"] = (
            round(cost * row["cantidad"], 2) if cost is not None else None
        )
        row["costo_fuente"] = fuente
    return rows


def costing_totals(rows: list[dict]) -> dict:
    """Totales del costeo: por categoría, catálogo vs fabricación, y el ítem más
    costoso (la pregunta clásica de optimización)."""
    por_categoria: dict[str, float] = {}
    catalogo = fabricacion = 0.0
    sin_costo = 0
    top = None
    for r in rows:
        total = r.get("costo_total_usd")
        if total is None:
            sin_costo += 1
            continue
        cat = r.get("categoria") or "otros"
        por_categoria[cat] = round(por_categoria.get(cat, 0.0) + total, 2)
        if r.get("ref") != "A-MEDIDA":
            catalogo += total
        else:
            fabricacion += total
        if top is None or total > top["costo_total_usd"]:
            top = r
    return {
        "catalogo_usd": round(catalogo, 2),
        "fabricacion_usd": round(fabricacion, 2),
        "total_usd": round(catalogo + fabricacion, 2),
        "por_categoria": dict(sorted(por_categoria.items(), key=lambda kv: -kv[1])),
        "n_filas_sin_costo": sin_costo,
        "item_mas_costoso": (
            {"ref": top["ref"], "descripcion": top["descripcion"],
             "costo_total_usd": top["costo_total_usd"]} if top else None
        ),
    }


def scene_costing(scene: dict, default_material: str | None = None,
                  extra: list[dict] | None = None,
                  cables_sin_cubrir: set | None = None) -> dict:
    """Costeo completo de la escena (+ las filas `extra` del tablero): filas + totales (lo
    consumen el endpoint `/api/costing.json`, el agente y la cotización)."""
    rows = costed_bom(scene, default_material, extra, cables_sin_cubrir)
    return {"rows": rows, "totales": costing_totals(rows)}
