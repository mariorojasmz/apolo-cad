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

COMPRA DECLARADA (F6, tanque de inox 2026-10-27): el modelador que modela a mano lo que se compra
(«Válvula de bola DN40 … (compra)», «Bisagra de la boca 1 (pala 63 mm AISI 304, compra)») lo
DECLARA con «compra» entre paréntesis (sola o como un ítem de la lista: `compra_declarada`). Es
una declaración, no una adivinanza por rol: gana a `_FABRICADO`, su norma cuenta aunque esté
fuera de la cabeza, y la marca no sale en lo que se pide (`nombre_de_compra`). Sin la marca, un
rol que no es de `ROL_COMPRA` sigue siendo a medida (una válvula o una bisagra se pueden fabricar).
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
    (re.compile(r"^bisagra", re.I), "bisagras"),  # la de la ficha BIS-63 (compra declarada)
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

#: la marca de COMPRA DECLARADA: «compra» (o «comprada/o», «de compra») como un ítem entero de un
#: paréntesis: «(compra)», «(pala 63 mm, compra)», «(compra; DN40)». «(compra local de 2 m)» no.
_ITEM_COMPRA = re.compile(r"^(?:de\s+)?compra(?:d[oa]s?)?$", re.I)
_PARENTESIS = re.compile(r"\s*\(([^()]*)\)")
_SEPARADOR = re.compile(r"\s*[,;]\s*")


def _sin_item_compra(m: re.Match) -> str:
    todos = _SEPARADOR.split(m.group(1).strip())
    items = [i for i in todos if not _ITEM_COMPRA.match(i)]
    if len(items) == len(todos):
        return m.group(0)  # un paréntesis sin la marca se queda tal cual
    return f" ({', '.join(items)})" if items else ""


def compra_declarada(nombre: str | None) -> bool:
    """¿El modelador declaró que la pieza se COMPRA («… (compra)», «(…, compra)»)?"""
    return any(_ITEM_COMPRA.match(i) for m in _PARENTESIS.finditer(nombre or "")
               for i in _SEPARADOR.split(m.group(1).strip()))


def sin_marca_de_compra(nombre: str | None) -> str:
    """El nombre sin la marca de compra declarada (lo demás del paréntesis se queda)."""
    if not compra_declarada(nombre):
        return (nombre or "").strip()
    return _PARENTESIS.sub(_sin_item_compra, nombre or "").strip()


def cabeza(nombre: str | None) -> str:
    """El rol hasta su primer complemento: lo que DESIGNA a la pieza."""
    rol = piece_role(nombre or "")
    m = _COMPLEMENTO_RE.search(rol)
    return (rol[:m.start()] if m else rol).strip()


def norma_del_nombre(nombre: str | None) -> str:
    """«DIN 933» si la CABEZA del nombre trae una norma comercial con designación o un rol de
    compra; '' si no (también en una pieza que se fabrica por su rol). Con la compra DECLARADA,
    la primera norma comercial de todo el nombre («Retén … (DIN 3760 25x40x7, compra)»)."""
    rol = piece_role(nombre or "")
    declarada = compra_declarada(rol)
    compra = declarada or bool(ROL_COMPRA.match(rol))
    if not compra and _FABRICADO.match(rol):
        return ""
    nombre = sin_marca_de_compra(rol) if declarada else cabeza(nombre)
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
    """¿La pieza modelada a mano se COMPRA? Rol de compra, compra declarada («(compra)») o norma
    comercial con designación."""
    rol = piece_role(nombre)
    return bool(ROL_COMPRA.match(rol)) or compra_declarada(rol) or bool(norma_del_nombre(nombre))


def categoria_de_compra(nombre: str | None) -> str:
    """La categoría de compra de una pieza comercial a mano («pernos», «tornilleria»…)."""
    rol = piece_role(nombre)
    return next((cat for rx, cat in _CATEGORIAS if rx.match(rol)), COMERCIALES)


def nombre_de_compra(nombre: str | None) -> str:
    """El nombre sin la ubicación final entre paréntesis: lo que se pide en el mostrador. Las
    piezas iguales de lugares distintos se juntan en una fila (la BOM conserva la firma
    geométrica en la clave: dos piezas distintas no se confunden). Sólo con NORMA: la
    designación identifica la compra; sin ella el paréntesis puede ser la especificación
    («Banda PVC … (grapas articuladas)») y se queda. La marca de compra declarada nunca va."""
    nombre = sin_marca_de_compra(nombre)
    if not norma_del_nombre(nombre):
        return nombre
    return _UBICACION_RE.sub("", nombre).strip() or nombre


#: hallazgos-del-revisor D4: el CÓDIGO DE FABRICANTE de una compra sin norma, declarado como
#: «tipo Marca código» («tipo Ganter GN 343.1 o eq.») o «(compra, Marca código)», o tras «ref.» /
#: «código». La marca va con mayúscula y no es una sigla de norma; el código lleva un dígito.
_SIGLAS_NO_MARCA = frozenset({
    "DIN", "ISO", "EN", "ASTM", "AISI", "SAE", "ANSI", "ASME", "DN", "NPT", "BSP", "UNE", "NTP",
    "JIS", "IEC", "IP", "PN", "NEMA", "UNC", "UNF", "M", "AWG", "HP", "PE", "PP", "PVC", "HDPE"})
_MARCA = r"(?P<marca>[A-ZÄÖÜÁÉÍÓÚÑ][\wäöüáéíóúñ&.\-]*)"
_CODIGO = r"(?P<codigo>(?:[A-Z]{1,5}[\s-]?)?\d[\w./\-]*)"
_TIPO_RE = re.compile(rf"\btipo\s+{_MARCA}\s+{_CODIGO}")
_ITEM_MARCA_RE = re.compile(rf"^{_MARCA}\s+{_CODIGO}(?:\s+o\s+(?:eq\w*\.?|similar))?$")
_REF_RE = re.compile(r"\b(?:ref\.?|c[óo]d(?:igo|\.))\s*:?\s*(?P<codigo>[A-Z0-9][\w./\-]*\d[\w./\-]*)")
#: el rol de una compra que se pide POR LARGO (D4): la varilla roscada, la barra, el perfil
ROL_POR_LARGO = re.compile(r"^(varillas?|barras?|perfil\w*|tubos?|pletinas?|platinas?|cables?|"
                           r"cadenas?|listones?)\b", re.I)


def codigo_de_fabricante(nombre: str | None) -> str:
    """«Ganter GN 343.1» si el nombre declara la marca y el código de lo que se compra (D4 de
    hallazgos-del-revisor), '' si no. Nunca de una sigla de norma («AISI 304», «DN 40»)."""
    texto = nombre or ""
    for m in _TIPO_RE.finditer(texto):
        if m.group("marca").upper() not in _SIGLAS_NO_MARCA:
            return f"{m.group('marca')} {m.group('codigo')}"
    for p in _PARENTESIS.finditer(texto):  # sólo junto a la marca: «(Tornillo 4x40)» no es código
        items = _SEPARADOR.split(p.group(1).strip())
        if not any(_ITEM_COMPRA.match(i) for i in items):
            continue
        for item in items:
            m = _ITEM_MARCA_RE.match(item)
            if m and m.group("marca").upper() not in _SIGLAS_NO_MARCA:
                return f"{m.group('marca')} {m.group('codigo')}"
    m = _REF_RE.search(texto)
    return m.group("codigo") if m else ""


def se_pide_por_largo(nombre: str | None) -> bool:
    """¿La compra se pide por su largo (varilla, barra, perfil…)? Su fila lleva el largo (D4)."""
    return bool(ROL_POR_LARGO.match(piece_role(nombre or "")))


def designacion(nombre: str | None) -> str | None:
    """Lo que se pide en el mostrador: la cabeza hasta su última medida o número de norma
    («Perno M10x25 DIN 933 del tensado» → «Perno M10x25 DIN 933»; «Tornillo M6x16 DIN 933 tapa
    del eje» → «Tornillo M6x16 DIN 933»). Sólo con norma (si no, None: sin norma el nombre puede
    ser la especificación). La compra declarada no la cambia: designa la norma de la CABEZA."""
    nombre = sin_marca_de_compra(nombre)
    if not norma_del_nombre(nombre):
        return None
    palabras = cabeza(nombre).split()
    ultima = max((i for i, w in enumerate(palabras) if any(c.isdigit() for c in w)), default=-1)
    return " ".join(palabras[: ultima + 1]) if ultima >= 0 else " ".join(palabras)
