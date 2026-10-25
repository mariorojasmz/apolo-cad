"""Lecturas acotadas del costeo (`GET /api/costing.json?resumen&categoria`, tool `get_costing`).

El costeo entero (`cobros.costeo`) trae una fila por partida: a una máquina real son ~50 kB. Como
las otras lecturas filtrables, el modo corto es opt-in y sin parámetros el dict es el de siempre:

  - `categoria`: sólo las filas de esa categoría del BOM (la de `totales.por_categoria`; una fila
    sin categoría es «otros»), sin distinguir mayúsculas, y `filtro` con cuántas filas y cuánto
    suman. Una categoría que ninguna fila tiene es 400 con las que hay.
  - `resumen`: todo menos `rows` (totales, avisos de cobro, notas y versiones de extensiones) +
    `n_filas`; con `categoria`, el `filtro` de esa categoría.

Puro sobre el dict del costeo: no toca el documento.
"""

from __future__ import annotations

from .errors import ServiceError


def _categoria(r: dict) -> str:
    return r.get("categoria") or "otros"


def acotar(data: dict, *, resumen: bool = False, categoria: str | None = None) -> dict:
    """El costeo `data` acotado (ver el docstring del módulo); sin filtros, `data` tal cual."""
    if not resumen and not categoria:
        return data
    rows = data["rows"]
    out = {k: v for k, v in data.items() if k != "rows"}
    if categoria:
        buscada = categoria.strip().lower()
        rows = [r for r in rows if _categoria(r).lower() == buscada]
        if not rows:
            hay = sorted({_categoria(r) for r in data["rows"]})
            raise ServiceError(400, f"la categoría «{categoria}» no está en el costeo; categorías: "
                                    f"{', '.join(hay) or '(ninguna)'}")
        out["filtro"] = {"categoria": _categoria(rows[0]), "n_filas": len(rows),
                         "total_usd": round(sum(r.get("costo_total_usd") or 0.0 for r in rows), 2),
                         "n_filas_sin_costo": sum(r.get("costo_total_usd") is None for r in rows)}
    if resumen:
        out["n_filas"] = len(data["rows"])
        return out
    return {"rows": rows, **out}
