"""Largo de COMPRA de la tornillería de catálogo en la BOM (F6 de la puerta de publicación): un
perno se pide «M10×40», no «M10». Puro (lee el sólido y la ficha, nunca un `Document`).

La ficha `PERNO-HEX-*` / `PERNO-M*` / `REMACHE-*` / `TIRAFONDO-HEX-*` es de largo A MEDIDA (lo
fija quien la usa: `join_bolted`, el tensor), así que su fila salía sin largo y todos los largos de
una métrica colapsaban en una sola fila. El largo sale, en este orden:

1. de la FICHA si es de largo fijo (`specs.length`: `DIN912-M8`, los tirafondos avellanados);
2. de la GEOMETRÍA si tiene cabeza reconocible (`fijadores_geom`): hexagonal → del asiento de la
   cabeza a la punta; Allen → la extensión axial menos el alto de cabeza de la ficha;
3. del NOMBRE que escribió el comando («Perno M8×20 DIN 933», «Remache ciego Ø4.8×10 DIN
   7337»): el remache COLOCADO ya no mide lo que se compra (la cabeza ciega está recalcada).

Sin ninguno → None (la fila sale sin largo, como antes). Caché por `id(shape)` que guarda la
referencia y verifica `is` (regla de [core/apolo](../CLAUDE.md)).
"""

from __future__ import annotations

import re

#: categorías del catálogo cuya pieza se compra por su largo
CATEGORIAS = ("pernos", "tornilleria", "tornilleria_madera")
_LARGO_RE = re.compile(r"(?:\bM|Ø)\s*\d+(?:[.,]\d+)?\s*[x×]\s*(\d+(?:[.,]\d+)?)", re.I)
_CACHE: dict[int, tuple[object, float | None]] = {}
_CACHE_MAX = 4096


def _de_geometria(shape, specs: dict) -> float | None:
    from .fijadores_geom import reconocer_fijadores

    try:
        solidos = list(shape.solids())
    except Exception:  # noqa: BLE001
        return None
    if len(solidos) != 1:
        return None
    solido = solidos[0]
    cab = next((f for f in reconocer_fijadores(solido) if f.tipo in ("cabeza_hex", "allen")), None)
    if cab is None:
        return None
    hacia = (-cab.eje[0], -cab.eje[1], -cab.eje[2])  # del asiento hacia la punta
    largo = max(sum((c - b) * h for c, b, h in zip((v.X, v.Y, v.Z), cab.base, hacia, strict=True))
                for v in solido.vertices())
    if cab.tipo == "allen":  # `base` es la cara de ARRIBA de la cabeza
        alto = specs.get("head_h") or specs.get("d")
        if not alto:
            return None
        largo -= float(alto)
    return round(largo, 1) if largo > 0 else None


def _del_nombre(nombre: str) -> float | None:
    m = _LARGO_RE.search(nombre or "")
    return float(m.group(1).replace(",", ".")) if m else None


def largo_de_compra(feat, comp) -> float | None:
    """Largo (mm) con el que se compra la tornillería `feat` de la ficha `comp`, o None si no
    es tornillería de largo o no se puede saber."""
    if comp is None or comp.category not in CATEGORIAS:
        return None
    specs = comp.specs or {}
    if specs.get("length") is not None:
        return float(specs["length"])
    shape = getattr(feat, "shape", None)
    if shape is None:
        return _del_nombre(getattr(feat, "name", ""))
    hit = _CACHE.get(id(shape))
    if hit is not None and hit[0] is shape:
        return hit[1]
    largo = None
    if specs.get("herramienta") != "remachadora":
        largo = _de_geometria(shape, specs)
    if largo is None:
        largo = _del_nombre(getattr(feat, "name", ""))
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[id(shape)] = (shape, largo)
    return largo
