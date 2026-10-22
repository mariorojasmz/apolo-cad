"""Medidas de una BANDA transportadora sobre su sólido (F6 de la puerta de publicación). Puro:
recibe el shape, nunca un `Document`.

- **Lazo cerrado** = un anillo de ancho w: sus dos caras laterales son PLANAS y con agujero
  (`caras_laterales`). Con espesor t y línea media P: V = P·t·w y A = 2·P·w + 2·P·t, así que
  P = (A − 2V/w) / (2w), exacto para el lazo de pista de `create_belt_conveyor` (la misma
  medida que `services/calidad_tensores.largo_de_banda` le pasa al control del tensor).
- La banda se COMPRA por ese desarrollo (la BOM), no por la mayor cota de su caja: el lazo de una
  faja de 2 m entre tambores mide ≈ 4,6 m. Una banda recta abierta no es lazo: su largo sigue
  siendo el de su caja.
- El ANCHO de la banda (lo que ve el paquete): la distancia entre las caras laterales del lazo;
  sin lazo, la menor cota horizontal de su caja.
"""

from __future__ import annotations

import re

#: el ROL banda (sobre `materials.piece_role`, tras el último « · »): «Faja de banda · Banda»
ROL_BANDA = re.compile(r"^(bandas?|cintas?)\b", re.I)


def es_banda(nombre: str | None) -> bool:
    from .materials import piece_role

    return bool(ROL_BANDA.match(piece_role(nombre or "")))


def caras_laterales(shape) -> list[tuple[tuple, tuple]]:
    """(normal, centro) de las caras planas con agujero: las dos de un lazo cerrado."""
    out = []
    try:
        caras = shape.faces()
    except Exception:  # noqa: BLE001
        return out
    for f in caras:
        try:
            if len(f.wires()) < 2 or "PLANE" not in str(f.geom_type).upper():
                continue
            n, c = f.normal_at(), f.center()
            out.append(((n.X, n.Y, n.Z), (c.X, c.Y, c.Z)))
        except Exception:  # noqa: BLE001
            continue
    return out


def _ancho_lazo(laterales) -> float | None:
    if len(laterales) < 2:
        return None
    (n, c0), (_, c1) = laterales[0], laterales[1]
    w = abs(sum(n[k] * (c1[k] - c0[k]) for k in range(3)))
    return w if w > 1.0 else None


def largo_de_lazo(shape) -> float | None:
    """Línea media del lazo cerrado (mm), o None si la banda no es un lazo o no se mide."""
    w = _ancho_lazo(caras_laterales(shape))
    if w is None:
        return None
    try:
        area, vol = float(shape.area), float(shape.volume)
    except Exception:  # noqa: BLE001
        return None
    largo = (area - 2.0 * vol / w) / (2.0 * w)
    return largo if largo > 0 else None


def ancho_de_banda(shape) -> float | None:
    """Ancho (mm) de la banda: entre las caras laterales del lazo o, sin lazo, la menor cota
    horizontal de su caja."""
    w = _ancho_lazo(caras_laterales(shape))
    if w is not None:
        return w
    try:
        bb = shape.bounding_box()
    except Exception:  # noqa: BLE001
        return None
    return min(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y)
