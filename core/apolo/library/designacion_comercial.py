"""Pieza COMERCIAL modelada a mano (F6 de la puerta de publicación): «Perno tensor de cola
M12x150 DIN 933», «Arandela cuña DIN 434», «Seeger DIN 472-52» salían en la BOM como A-MEDIDA con
la norma vacía. Su nombre ya dice cómo se compra: la NORMA (DIN/ISO/ASME/ANSI + número) va a la
columna de norma. Puro: lee el nombre, nunca un `Document`.

Guarda (un plano cita normas que no se compran: «ISO 2768-mK», «ISO 286»): la norma cuenta si el
nombre trae además una DESIGNACIÓN (rosca «M12», «M12x150», «Ø4.8x10» o el sufijo de la norma
«472-52») o si el ROL es de compra (perno, arandela, seeger…: `ROL_COMPRA`).
"""

from __future__ import annotations

import re

from .materials import piece_role

#: ROL de COMPRA (herraje/consumible a medida): se COMPRA, no se corta ni se mecaniza. Anclado al
#: inicio del rol: «Tensor de cola · Eje fijo (roscado p/ perno)» NO es compra (lo usa la lista de
#: corte, `cutlist._is_purchased_custom`).
ROL_COMPRA = re.compile(
    r"^(pernos?|tornill\w*|arandelas?|tuercas?|esp[áa]rragos?|prisioneros?|"
    r"pies?\s+nivelador\w*|nivelador\w*|seegers?|circlips?|bandas?|correas?)\b", re.I)

_NORMA_RE = re.compile(r"\b(DIN|ISO|ASME|ANSI)\s*-?\s*(B?\d+(?:\.\d+)*)(-\d+(?:[.,]\d+)?)?\b",
                       re.I)
_ROSCA_RE = re.compile(r"(?<![A-Za-z])M\s*\d+(?:[.,]\d+)?\b|Ø\s*\d+(?:[.,]\d+)?\s*[x×]\s*\d+")


def norma_del_nombre(nombre: str | None) -> str:
    """«DIN 933» si el nombre trae una norma comercial con designación o un rol de compra; ''
    si no."""
    nombre = nombre or ""
    m = _NORMA_RE.search(nombre)
    if m is None:
        return ""
    designado = bool(m.group(3)) or bool(_ROSCA_RE.search(nombre))
    if not (designado or ROL_COMPRA.match(piece_role(nombre))):
        return ""
    return f"{m.group(1).upper()} {m.group(2).upper()}"
