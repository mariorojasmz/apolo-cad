"""Lo EXISTENTE del sitio no se compra: la pieza que el modelador DECLARA existente, del cliente o
no suministrada («Calamina existente» bajo una estructura de paneles, «Correa delantera
existente» del techo, «Mesa del cliente», «Tanque (no suministrado)») está en la escena para el
apoyo, la gravedad y los planos, pero la máquina no la suministra: no sale en la BOM de compra
(ni en el costeo que la usa), ni en la lista de corte, ni en la cédula de herraje, y no cuenta en
`bom.comprable`. Puro: lee el nombre, nunca un `Document`.

Se lee del ROL y de su complemento inmediato, nunca de cualquier palabra suelta. En cada tramo
« · » del nombre (el primero puede nombrar el conjunto: «Techo existente · Correa (1)»):

- la CABEZA (hasta el primer complemento: «(», «de», «del», «a», «sobre», «para»…) califica al
  rol: «Calamina existente», «Correa delantera existente», «Viga no suministrada»;
- el PRIMER complemento dice de quién es: «Mesa del cliente», «Losa de la obra», «Poste del
  sitio», «Tanque por el cliente», «… de terceros»;
- un ítem entre paréntesis lo declara: «(existente)», «(no suministrado)», «(del cliente, 2)»,
  «(existente en obra)».

Lo que sólo MENCIONA algo existente en un complemento lateral se compra: «Ménsula a correa
existente», «Soporte de calamina existente», «Placa (sobre losa existente)». Por lo mismo, «Losa
de concreto existente» no se reconoce (el «de» abre un complemento, como en «Soporte de calamina
existente»): se escribe «Losa existente de concreto» o «Losa de concreto (existente)». Errar hacia
comprar sólo pide una designación de más; errar hacia no comprar deja la máquina sin una pieza.
"""

from __future__ import annotations

import re

_CALIFICA = re.compile(r"\s(?:existentes?|existing|no\s+suministrad[oa]s?|not\s+supplied)\b",
                       re.I)
_DE_QUIEN = r"(?:del|de\s+la)\s+(?:cliente|sitio|obra)|por\s+(?:el\s+)?cliente|(?:de|por)\s+terceros"
_COMPLEMENTO_DE_QUIEN = re.compile(rf"^\s+(?:{_DE_QUIEN})\b", re.I)
_ITEM = re.compile(rf"^(?:existentes?|existing|no\s+suministrad[oa]s?|no\s+incluid[oa]s?|"
                   rf"not\s+supplied|by\s+others|suministr\w*\s+(?:del|por\s+el)\s+cliente|"
                   rf"{_DE_QUIEN})\b", re.I)
#: dónde termina la cabeza del rol (como `designacion_comercial._COMPLEMENTO_RE`, más «de» suelto,
#: «a» y las preposiciones de lugar: «Placa de anclaje a losa existente» no es existente)
_COMPLEMENTO = re.compile(r"\s*\(|\s+(?:con|para|sin|y|e|de|del|al|a|por|sobre|bajo|entre|tras|"
                          r"contra|hacia|junto|desde|hasta|en|encima|debajo|on|over|under|to|"
                          r"for|with)\b", re.I)
_PARENTESIS = re.compile(r"\(([^()]*)\)")
_SEPARADOR = re.compile(r"\s*[,;]\s*")


def _tramo_existente(tramo: str) -> bool:
    for m in _PARENTESIS.finditer(tramo):
        if any(_ITEM.match(i) for i in _SEPARADOR.split(m.group(1).strip())):
            return True
    m = _COMPLEMENTO.search(tramo)
    cabeza = tramo[:m.start()] if m else tramo
    if _CALIFICA.search(cabeza):
        return True
    return m is not None and bool(_COMPLEMENTO_DE_QUIEN.match(tramo[m.start():]))


def no_suministrada(nombre: str | None) -> bool:
    """¿El nombre declara que la pieza es existente, del cliente o no suministrada (ver el
    módulo)? Entonces no se compra, no se corta ni se cotiza."""
    return any(_tramo_existente(t.strip()) for t in (nombre or "").split("·"))
