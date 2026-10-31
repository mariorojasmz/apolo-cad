"""Los datos puros que la seguridad y la reparabilidad leen de un documento.

`services/calidad_seguridad.py` los arma (roles de `services/roles.py`, cajas y redondez de
OCCT); aquí no hay OCCT ni `Document`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

Caja = tuple[tuple[float, float, float], tuple[float, float, float]]

_ARANDELA_RE = re.compile(r"\b(arandelas?|washers?|seeger|anillos?\s+de\s+retenci[oó]n|"
                          r"anillo\s+seeger)\b", re.I)
_CADENA_RE = re.compile(r"\b(cadenas?|chains?|correas?|v-?belts?)\b", re.I)
_BANDA_RE = re.compile(r"\b(bandas?|fajas?|cintas?|belts?)\b", re.I)
SOLDADAS = ("soldadura", "pegado")


@dataclass
class Redondo:
    """Pieza de revolución (por su caja): dos lados iguales; el tercero es el eje."""
    eje: int                                  # 0 = X, 1 = Y, 2 = Z
    centro: tuple[float, float, float]
    radio: float
    largo: float


@dataclass
class Pieza:
    id: str
    nombre: str
    rol: str = ""                             # `roles.rol_union`
    categoria: str | None = None              # categoría del catálogo
    nombre_catalogo: str | None = None
    caja: Caja = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    redondo: Redondo | None = None
    anclada: bool = False                     # tiene `ground`
    extra: dict = field(default_factory=dict)

    @property
    def centro(self) -> tuple[float, float, float]:
        lo, hi = self.caja
        return tuple((lo[i] + hi[i]) / 2.0 for i in range(3))


def es_tornilleria(p: Pieza) -> bool:
    """Perno, tuerca, arandela o anillo de retención: herraje, no nodo de la estructura."""
    return p.rol in ("perno", "tuerca") or bool(_ARANDELA_RE.search(p.nombre))


def clase_flexible(p: Pieza) -> str | None:
    """«banda» (la banda del transportador: superficie de trabajo), «transmision» (cadena o
    correa de transmisión) o None. Lo ANCLADO a tierra no es un lazo que se mueve (una «Correa»
    de techo existente; plan puerta-fuera-de-catalogo D3)."""
    if (p.rol != "flexible" and p.categoria != "transmision") or getattr(p, "anclada", False):
        return None
    if p.categoria == "transmision":
        return "transmision" if p.rol == "flexible" else None
    if _CADENA_RE.search(p.nombre):
        return "transmision"
    return "banda" if _BANDA_RE.search(p.nombre) else None


def redondo_de_caja(caja: Caja, tol: float = 0.06) -> Redondo | None:
    """Revolución por la caja: dos lados iguales (±6 %) y ≥ 20 mm. El eje es el tercero."""
    lo, hi = caja
    lados = [hi[i] - lo[i] for i in range(3)]
    for eje in range(3):
        a, b = (lados[i] for i in range(3) if i != eje)
        if min(a, b) >= 20.0 and abs(a - b) <= tol * max(a, b):
            centro = tuple((lo[i] + hi[i]) / 2.0 for i in range(3))
            return Redondo(eje, centro, (a + b) / 4.0, lados[eje])
    return None


def vecinos(uniones: list[dict], tipos=None) -> dict[str, set[str]]:
    """Adyacencia de las uniones declaradas (`fasten`), opcionalmente sólo de ciertos tipos."""
    adj: dict[str, set[str]] = {}
    for u in uniones:
        if tipos is not None and u.get("kind") not in tipos:
            continue
        adj.setdefault(u["a"], set()).add(u["b"])
        adj.setdefault(u["b"], set()).add(u["a"])
    return adj


def componentes(ids, adj: dict[str, set[str]]) -> list[set[str]]:
    """Componentes conexos de `ids` usando sólo aristas entre miembros de `ids`."""
    ids = set(ids)
    out, vistos = [], set()
    for semilla in sorted(ids):
        if semilla in vistos:
            continue
        comp, pila = set(), [semilla]
        while pila:
            n = pila.pop()
            if n in comp:
                continue
            comp.add(n)
            pila.extend(m for m in adj.get(n, ()) if m in ids and m not in comp)
        vistos |= comp
        out.append(comp)
    return out


def item(id_: str, titulo: str, estado: str, modo_de_falla: str, norma: str,
         evidencia: dict | None = None, piezas=(), detalle: str = "") -> dict:
    """Un ítem de la ficha de calidad con el esquema del registro (F1)."""
    assert estado in ("OK", "FALLA", "SIN_EVALUAR", "NO_APLICA")
    return {"id": id_, "titulo": titulo, "estado": estado, "modo_de_falla": modo_de_falla,
            "norma": norma, "evidencia": evidencia or {}, "piezas": sorted(set(piezas)),
            "detalle": detalle}
