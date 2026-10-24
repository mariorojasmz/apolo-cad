"""Filas del costeo que suma una extensión (`Extension.costeo`; plan
puntos-de-extension-entregables, D2). Puro: guarda lo declarado y valida las filas; quien llama a
`FuenteCosteo.filas(doc)` es `services/cobros.py`, bajo el lock del llamador.

Una fila de extensión llega YA COSTEADA (la extensión sabe su precio y la `fuente` lo declara):
`costing.costed_bom` no la re-costea y `costing_totals` la suma a `extensiones_usd`, ni comprada
ni fabricada. Sin extensiones con costeo, `DE_EXTENSION` está vacío y nada cambia.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

#: `origen` de una fila de extensión: «extension:<nombre>».
ORIGEN = "extension:"
#: Las claves de una fila (más `categoria`, opcional); ninguna otra.
CAMPOS = ("descripcion", "cantidad", "unidad", "costo_unit", "fuente")
CATEGORIA = "servicios"  # la de una fila que no declara la suya


@dataclass(frozen=True)
class FuenteCosteo:
    """Una fuente de filas del costeo: `id` «prefijo.x» (la ref de sus filas) y `filas(doc)` →
    iterable de `{descripcion, cantidad, unidad, costo_unit, fuente[, categoria]}`."""

    id: str
    filas: Callable


#: nombre de la extensión → (version_costeo, (FuenteCosteo, …)); lo llena `extensiones.cargar`.
DE_EXTENSION: dict[str, tuple[int, tuple[FuenteCosteo, ...]]] = {}


def vigentes() -> list[tuple[str, FuenteCosteo]]:
    """(nombre de la extensión, fuente) de cada fuente cargada, en el orden de carga."""
    return [(nombre, f) for nombre, (_v, fuentes) in DE_EXTENSION.items() for f in fuentes]


def versiones() -> dict[str, int]:
    """{nombre: version_costeo} de las extensiones con costeo (lo publica el dict del costeo)."""
    return {nombre: v for nombre, (v, _f) in DE_EXTENSION.items()}


def _numero(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _texto(x) -> bool:
    return isinstance(x, str) and bool(x.strip())


def fila(nombre: str, fuente: FuenteCosteo, d) -> dict:
    """La fila costeada de `d`, o `ValueError` con el motivo (la fila no se cobra)."""
    if not isinstance(d, dict):
        raise ValueError(f"una fila no es un dict: {d!r}"[:200])
    faltan = [k for k in CAMPOS if k not in d]
    sobran = sorted(set(d) - set(CAMPOS) - {"categoria"})
    if faltan or sobran:
        raise ValueError("una fila es {descripcion, cantidad, unidad, costo_unit, fuente"
                         "[, categoria]}" + (f"; faltan {', '.join(faltan)}" if faltan else "")
                         + (f"; sobran {', '.join(sobran)}" if sobran else ""))
    for k in ("descripcion", "unidad", "fuente"):
        if not _texto(d[k]):
            raise ValueError(f"`{k}` es un texto no vacío, no {d[k]!r}")
    if "categoria" in d and not _texto(d["categoria"]):
        raise ValueError(f"`categoria` es un texto no vacío, no {d['categoria']!r}")
    if not _numero(d["cantidad"]) or d["cantidad"] <= 0:
        raise ValueError(f"`cantidad` es un número finito > 0, no {d['cantidad']!r}")
    if not _numero(d["costo_unit"]) or d["costo_unit"] < 0:
        raise ValueError(f"`costo_unit` es un número finito ≥ 0 (USD), no {d['costo_unit']!r}")
    cantidad, costo = float(d["cantidad"]), float(d["costo_unit"])
    return {
        "ref": fuente.id, "descripcion": d["descripcion"].strip(),
        "categoria": (d.get("categoria") or CATEGORIA).strip(), "material": "", "norma": "",
        "cantidad": int(cantidad) if cantidad.is_integer() else cantidad,
        "unidad": d["unidad"].strip(), "longitud_mm": None, "peso_unitario_kg": None,
        "peso_total_kg": None, "origen": ORIGEN + nombre,
        "costo_ud_usd": round(costo, 2), "costo_total_usd": round(costo * cantidad, 2),
        "costo_fuente": d["fuente"].strip(),
    }


def es_de_extension(row: dict) -> bool:
    return str(row.get("origen") or "").startswith(ORIGEN)
