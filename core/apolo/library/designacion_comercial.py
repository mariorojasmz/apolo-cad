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

La norma tiene que DESIGNAR a la pieza (F6): sólo cuenta la de la CABEZA del rol (`cabeza`: hasta
el primer complemento, «(», «con», «para», «del», «de la»…), y nunca en una pieza que se FABRICA
por su rol (eje, placa, soporte…: `_FABRICADO`). «Eje fijo del rodillo Ø17 h6 (topes axiales con
anillos DIN 471)» es una barra mecanizada, no un anillo: salía «COMPRA» sin largo.

`designacion` es lo que se pide en el mostrador («Perno M10x25 DIN 933»: rol, medida y norma, sin
la ubicación «del tensado»): la BOM agrupa por ella (F6: el mismo artículo salía en dos líneas).
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

_MEDIDA_RE = re.compile(r"\b\d+(?:[.,]\d+)?\s*[x×]\s*\d+")
#: dónde empieza el COMPLEMENTO del rol: lo que sigue ya no designa a la pieza
_COMPLEMENTO_RE = re.compile(r"\s*\(|\s+(?:con|para|sin|y|e|del|al|por|sobre|bajo|entre|tras|"
                             r"contra|en|de\s+(?:la|las|los|el|un|una))\b", re.I)
#: roles que se FABRICAN aunque nombren una norma (la de otra pieza o la de su plano)
_FABRICADO = re.compile(r"^(ejes?|placas?|soportes?|m[ée]nsulas?|chapas?|tapas?|guardas?|"
                        r"bastidor\w*|largueros?|travesa[ñn]os?|perfil\w*|tubos?|barras?|bridas?|"
                        r"camas?|bandejas?|cajas?|marcos?|patas?|bases?|tambor\w*|rodillos?|"
                        r"carcasas?|cuerpos?|horquillas?|orejas?|escuadras?|topes?)\b", re.I)

#: sufijos de UBICACIÓN al final del nombre: «Arandela cuña DIN 434 M8 (guarda cabeza +Y, 1)»
_UBICACION_RE = re.compile(r"(?:\s*\([^()]*\))+\s*$")


def cabeza(nombre: str | None) -> str:
    """El rol hasta su primer complemento: lo que DESIGNA a la pieza."""
    rol = piece_role(nombre or "")
    m = _COMPLEMENTO_RE.search(rol)
    return (rol[:m.start()] if m else rol).strip()


def norma_del_nombre(nombre: str | None) -> str:
    """«DIN 933» si la CABEZA del nombre trae una norma comercial con designación o un rol de
    compra; '' si no (también en una pieza que se fabrica por su rol)."""
    rol = piece_role(nombre or "")
    compra = bool(ROL_COMPRA.match(rol))
    if not compra and _FABRICADO.match(rol):
        return ""
    nombre = cabeza(nombre)
    # designación: una rosca, o una medida «17x1», «8x7x40» junto a la norma en la cabeza
    designado_rosca = bool(_ROSCA_RE.search(nombre) or _MEDIDA_RE.search(nombre))
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


def designacion(nombre: str | None) -> str | None:
    """Lo que se pide en el mostrador: la cabeza hasta su última medida o número de norma
    («Perno M10x25 DIN 933 del tensado» → «Perno M10x25 DIN 933»; «Tornillo M6x16 DIN 933 tapa
    del eje» → «Tornillo M6x16 DIN 933»). Sólo con norma (si no, None: sin norma el nombre puede
    ser la especificación)."""
    if not norma_del_nombre(nombre):
        return None
    palabras = cabeza(nombre).split()
    ultima = max((i for i, w in enumerate(palabras) if any(c.isdigit() for c in w)), default=-1)
    return " ".join(palabras[: ultima + 1]) if ultima >= 0 else " ".join(palabras)
