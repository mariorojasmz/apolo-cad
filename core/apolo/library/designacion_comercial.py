"""Pieza COMERCIAL modelada a mano (F6 de la puerta de publicación): «Perno tensor de cola
M12x150 DIN 933», «Arandela cuña DIN 434», «Seeger DIN 472-52» salían en la BOM como A-MEDIDA con
la norma vacía y en la categoría de FABRICAR. Su nombre ya dice cómo se compra: la NORMA
(DIN/ISO/ASME/ANSI + número) va a la columna de norma y la pieza va a la categoría de COMPRA que la
BOM usa para el catálogo («pernos», «tuercas», «tornilleria»…), en BOM, cotización y cédula. Puro:
lee el nombre, nunca un `Document`.

Guarda (un plano cita normas que no se compran: «ISO 2768-mK», «ISO 286»): la norma cuenta si el
nombre trae además una DESIGNACIÓN (rosca «M12», «M12x150», «Ø4.8x10» o el sufijo de la norma
«472-52») o si el ROL es de compra (perno, arandela, seeger…: `ROL_COMPRA`); y nunca una norma de
PLANO, de perfil o de seguridad (`_NORMAS_NO_DE_COMPRA`), aunque el nombre traiga una rosca.
"""

from __future__ import annotations

import re

from .materials import piece_role

#: ROL de COMPRA (herraje/consumible a medida): se COMPRA, no se corta ni se mecaniza. Anclado al
#: inicio del rol: «Tensor de cola · Eje fijo (roscado p/ perno)» NO es compra (lo usa la lista de
#: corte, `cutlist._is_purchased_custom`).
ROL_COMPRA = re.compile(
    r"^(pernos?|tornill\w*|arandelas?|tuercas?|esp[áa]rragos?|prisioneros?|"
    r"pies?\s+nivelador\w*|nivelador\w*|seegers?|circlips?|anillos?\s+(?:seeger|el[áa]stic\w*|de\s+retenci[óo]n)|"
    r"silent[\s-]?blocks?|remaches?|rodamientos?|bandas?|correas?)\b", re.I)

_NORMA_RE = re.compile(r"\b(DIN|ISO|ASME|ANSI)\s*-?\s*(B?\d+(?:\.\d+)*)(-\d+(?:[.,]\d+)?)?\b",
                       re.I)
_ROSCA_RE = re.compile(r"(?<![A-Za-z])M\s*\d+(?:[.,]\d+)?\b|Ø\s*\d+(?:[.,]\d+)?\s*[x×]\s*\d+")

#: normas que un nombre cita sin que la pieza se compre: de PLANO (tolerancias, acabado, soldadura,
#: GD&T), de PERFIL (la pieza se corta de una barra) y de SEGURIDAD. «Placa (taladros M12) ISO
#: 2768-mK» se fabrica aunque traiga una rosca.
_NORMAS_NO_DE_COMPRA = frozenset({
    "ISO 128", "ISO 129", "ISO 286", "ISO 1101", "ISO 1302", "ISO 2553", "ISO 2768", "ISO 4287",
    "ISO 5459", "ISO 8015", "ISO 9013", "ISO 13715", "ISO 13920", "ISO 12100", "ISO 13849",
    "ISO 13857", "ISO 14120", "ISO 14122", "DIN 1025", "DIN 1026", "DIN 1028", "DIN 59410",
})

#: rol → categoría de COMPRA, la misma que la BOM usa para la ficha de catálogo equivalente
_CATEGORIAS = (
    (re.compile(r"^(pernos?|tornill|esp[áa]rrago|prisionero)", re.I), "pernos"),
    (re.compile(r"^tuercas?", re.I), "tuercas"),
    (re.compile(r"^(arandela|seeger|circlip|anillos?\s|remache)", re.I), "tornilleria"),
    (re.compile(r"^(pies?\s+nivelador|nivelador)", re.I), "pies_niveladores"),
    (re.compile(r"^rodamiento", re.I), "rodamientos"),
    (re.compile(r"^(banda|correa)", re.I), "bandas"),
)
#: la que no casa con ninguna (silentblock, una pieza con norma y designación sin rol conocido)
COMERCIALES = "comerciales"

#: sufijos de UBICACIÓN al final del nombre: «Arandela cuña DIN 434 M8 (guarda cabeza +Y, 1)»
_UBICACION_RE = re.compile(r"(?:\s*\([^()]*\))+\s*$")


def norma_del_nombre(nombre: str | None) -> str:
    """«DIN 933» si el nombre trae una norma comercial con designación o un rol de compra; ''
    si no."""
    nombre = nombre or ""
    designado_rosca = bool(_ROSCA_RE.search(nombre))
    compra = bool(ROL_COMPRA.match(piece_role(nombre)))
    for m in _NORMA_RE.finditer(nombre):
        norma = f"{m.group(1).upper()} {m.group(2).upper()}"
        if norma in _NORMAS_NO_DE_COMPRA:
            continue
        if bool(m.group(3)) or designado_rosca or compra:
            return norma
    return ""


def es_comercial(nombre: str | None) -> bool:
    """¿La pieza modelada a mano se COMPRA? Rol de compra o norma comercial con designación."""
    return bool(ROL_COMPRA.match(piece_role(nombre))) or bool(norma_del_nombre(nombre))


def categoria_de_compra(nombre: str | None) -> str:
    """La categoría de compra de una pieza comercial a mano («pernos», «tornilleria»…)."""
    rol = piece_role(nombre)
    return next((cat for rx, cat in _CATEGORIAS if rx.match(rol)), COMERCIALES)


def nombre_de_compra(nombre: str | None) -> str:
    """El nombre sin la ubicación final entre paréntesis: lo que se pide en el mostrador. Las
    piezas iguales de lugares distintos se juntan en una fila (la BOM conserva la firma
    geométrica en la clave: dos piezas distintas no se confunden). Sólo con NORMA: la
    designación identifica la compra; sin ella el paréntesis puede ser la especificación
    («Banda PVC … (grapas articuladas)») y se queda."""
    nombre = (nombre or "").strip()
    if not norma_del_nombre(nombre):
        return nombre
    return _UBICACION_RE.sub("", nombre).strip() or nombre
