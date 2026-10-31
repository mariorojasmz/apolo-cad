"""¿Entra el DESTORNILLADOR? El acceso de herramienta de lo que no tiene hexágono (plan
puerta-fuera-de-catalogo D4; el de la llave, `acceso_herramienta.py`).

- **Por la impronta**: Torx, Pozidriv/Phillips, ranura y Allen se aprietan con una punta EN
  LÍNEA con el eje. La impronta la DECLARA la ficha (`specs.huella`) o el nombre («… avellanado TX
  3x30», «Allen», DIN 912); la geometría sólo da el eje y la cara de la cabeza
  (`cabeza_revolucion.py`: la impronta no se dibuja). Los fantasmas son cilindros coaxiales
  (hoja, mango y mano: `herramientas.destornilladores`; Allen, el brazo corto de ISO 2936). Basta
  UNO libre (D2 de acceso-de-herramienta).
- **Por su perno**: la tuerca martillo, la de barril y el inserto roscado no tienen llave propia:
  los aprieta la cabeza del perno con el que trabajan, que se evalúa aparte. Se cuentan si un
  perno modelado los atraviesa; si no, no evaluados.

Lo que sigue sin evaluar se puede JUSTIFICAR por escrito con la herramienta (`calidad/puerta.py`).
PURO: recibe sólidos y fichas, nunca un `Document`; el llamador sostiene `STATE_LOCK`.
"""

from __future__ import annotations

import math
import re

#: lo que aprieta la cabeza de su perno (rol que ENCABEZA el nombre)
_POR_SU_PERNO_RE = re.compile(
    r"^\s*(tuercas?\s+(?:martillo|en\s+t|de\s+barril|barril|de\s+ranura|deslizantes?|"
    r"cuadradas?\s+de\s+ranura)|insertos?\s+roscad\w*|insertos?\s+de\s+rosca|cross\s+dowel|"
    r"hammer\s+nuts?|t-?nuts?|threaded\s+inserts?)\b", re.I)


def por_su_perno(nombre: str | None) -> bool:
    """¿La pieza la aprieta la cabeza de su perno (tuerca martillo, de barril, inserto)?"""
    from .materials import piece_role

    return bool(_POR_SU_PERNO_RE.match(piece_role(nombre)))


def impronta(feat, catalog) -> tuple[str, int | None] | None:
    """(huella, tamaño) que declara la ficha o el nombre, o None."""
    from .tornillo_madera import huella_del_nombre, tamano_del_nombre

    comp = catalog.get(getattr(feat, "component", None) or "") if catalog else None
    specs = (comp.specs or {}) if comp is not None else {}
    nombre = getattr(feat, "name", "") or ""
    huella = specs.get("huella") or huella_del_nombre(nombre)
    if huella is None:
        return None
    return huella, tamano_del_nombre(str(specs.get("punta") or "")) or tamano_del_nombre(nombre)


def herramientas(huella: str, tamano: int | None, cab: dict, holgura: float) -> list:
    """[(nombre, ((radio, z0, z1), …))] de las herramientas de la impronta, coaxiales desde la
    cara de la cabeza (z = 0), o [] si la impronta no tiene tabla (Allen fuera de ISO 2936)."""
    from .herramientas import ALLEN_ISO4762, brazo_allen, destornilladores

    if huella == "allen":
        s = next((v for d, v in ALLEN_ISO4762.items() if abs(d - cab["d"]) <= 0.35), None)
        largo = brazo_allen(s) if s is not None else None
        if largo is None:
            return []
        e = 1.14 * s  # ISO 2936 Tabla 1: e_max = 1,14·s − 0,03
        return [(f"llave Allen {s:g} (brazo corto {largo:g} mm, ISO 2936)",
                 ((e / 2.0 + 0.5, holgura, largo),))]
    return [(t.nombre, t.tramos) for t in destornilladores(huella, cab["d"], cab["s"], tamano,
                                                           holgura)]


def alcance(tramos) -> float:
    """Hasta dónde llega la herramienta (caja de vecinos)."""
    return max(max(z1, r) for r, _z0, z1 in tramos) + 2.0


def eje_x(eje) -> tuple[float, float, float]:
    """Una dirección ⟂ al eje (el marco de los fantasmas; un cilindro no depende de ella)."""
    otro = (1.0, 0.0, 0.0) if abs(eje[0]) < 0.9 else (0.0, 1.0, 0.0)
    x = (eje[1] * otro[2] - eje[2] * otro[1], eje[2] * otro[0] - eje[0] * otro[2],
         eje[0] * otro[1] - eje[1] * otro[0])
    n = math.sqrt(sum(c * c for c in x))
    return (x[0] / n, x[1] / n, x[2] / n)


def atraviesa(perno_bbox, otro_bbox, tol: float = 0.5) -> bool:
    """¿Se cruzan las cajas? (el perno pasa por la tuerca martillo o el inserto)."""
    return (perno_bbox.min.X - tol <= otro_bbox.max.X and otro_bbox.min.X - tol <= perno_bbox.max.X
            and perno_bbox.min.Y - tol <= otro_bbox.max.Y and otro_bbox.min.Y - tol <= perno_bbox.max.Y
            and perno_bbox.min.Z - tol <= otro_bbox.max.Z and otro_bbox.min.Z - tol <= perno_bbox.max.Z)
