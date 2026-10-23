"""El Ø de TRABAJO del tambor de una faja hecha a mano, medido en el modelo (plan
puerta-de-publicacion, F6). La velocidad de banda (v = n·π·Ø), el par y la tensión de
`rules.conveyor_engineering_check` usan el Ø de la superficie donde abraza la banda.

Antes salía del menor lado de la caja de toda pieza con «tambor» en el nombre: la «Guarda del
tambor de cabeza» (325 × 120) daba Ø120 y la memoria decía 21,2 m/min con el tambor motriz
engomado de Ø113,6 (20,1 m/min). Ahora cuenta sólo lo REDONDO y LARGO (dos lados de la caja
iguales a ±3 % —el Ø— y el tercero, el largo, ≥ el Ø: un tubo o un engomado; no una guarda,
una tapa ni un rodamiento), salvo que su ROL (tras el último « · ») sea un eje, un rodamiento,
una tapa o una guarda: nunca son la cara de la banda. Si alguno se llama «motriz» (el que mueve
la banda), sólo esos. El mayor Ø de lo que queda es el exterior: el engomado sobre el tubo. Sin
nada redondo y largo, el criterio de antes (no se pierde una faja que hoy se detecta).
"""

from __future__ import annotations

import re

_MOTRIZ_RE = re.compile(r"\bmotri(z|ces)\b", re.I)
#: Roles (tras el último « · ») que no son la superficie de la banda aunque sean redondos.
_NO_ES_CARA_RE = re.compile(r"^(ejes?|shafts?|rodamientos?|pernos?|tornillos?|anillos?|"
                            r"chavetas?|bujes?|tapas?|guardas?|soportes?)\b", re.I)
_TOL = 0.03


def _lados(f):
    try:
        bb = f.shape.bounding_box()
    except Exception:  # noqa: BLE001
        return None
    return (bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)


def diametro_redondo(f) -> float | None:
    """El Ø de una pieza redonda y larga (la caja: dos lados iguales y el tercero ≥ ellos)."""
    lados = _lados(f)
    if lados is None:
        return None
    for i, j, k in ((0, 2, 1), (0, 1, 2), (1, 2, 0)):
        a, b, largo = lados[i], lados[j], lados[k]
        if a > 0 and abs(a - b) <= _TOL * max(a, b) and largo >= max(a, b):
            return (a + b) / 2.0
    return None


def diametro_tambor(piezas) -> float | None:
    from .materials import piece_role

    piezas = list(piezas)
    redondos = [(f, d) for f in piezas if (d := diametro_redondo(f))
                and not _NO_ES_CARA_RE.match(piece_role(getattr(f, "name", "") or ""))]
    if redondos:
        motrices = [d for f, d in redondos if _MOTRIZ_RE.search(getattr(f, "name", "") or "")]
        return round(max(motrices or [d for _f, d in redondos]), 1)
    ds = [min(x, z) for f in piezas if (lados := _lados(f)) for x, _y, z in [lados]]
    return round(max(ds), 1) if ds else None
