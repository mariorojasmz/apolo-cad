"""Schema de `fasten` (el fijador estructural A↔B).

Sale de `models.py` (congelado por el trinquete de tamaño) al ganar los CONJUNTOS del plan
`uniones-en-lote` (D1): `a` y `b` siguen siendo texto (un log viejo trae un id de pieza y
regenera igual), y el executor en `exec_uniones.py` los expande.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

_CONJUNTO = (
    "id de feature, o un CONJUNTO de piezas: la raíz de un patrón (el id del comando "
    "pattern_linear/pattern_circular, p. ej. 'c57' = sus copias c57_1, c57_2…), varios "
    "unidos con '+' ('c11+c57' = la fuente del patrón y sus copias) y, opcional, un corte "
    "por posición a la Python sobre el conjunto entero ('(c15+c61)[::2]' = una de cada dos)"
)


class FastenParams(BaseModel):
    """Fijador PERSISTENTE que declara que dos sólidos están unidos (perno, soldadura,
    pegado o contacto). NO mueve geometría ni corta nada: solo registra la unión para la
    validación de ensamblaje (¿cada pieza tiene sujeción hasta el piso?). Espejo de
    add_mate, pero estructural. El tipo 'contacto' lo emite la auto-detección (apoyo más
    débil); perno/soldadura/pegado los declara el usuario.

    EN LOTE (piezas repetidas): `a` y/o `b` aceptan un CONJUNTO y UN comando declara una
    unión por instancia. Conjunto + pieza = cada instancia a esa pieza (a='c11+c57',
    b='c9': cada eje a su larguero). Conjunto + conjunto = se emparejan por POSICIÓN (eje k
    ↔ tuerca k) y deben tener el mismo largo (si no, error con los dos conteos). La raíz
    de un patrón cubre sólo las COPIAS que creó ese comando: la pieza fuente es otra (su
    propio id); súmala con '+' para incluirla. El conjunto se re-expande en cada
    regenerate: si cambia el `count` del patrón (p. ej. una variable n_rod), las uniones
    lo siguen. Cada unión expandida se llama `{name}[k]` (k desde 0, en el orden del
    conjunto); con dos piezas sueltas sigue siendo una sola unión `name`."""

    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=40, title="Nombre")
    a: str = Field(..., title="Sólido A", description=_CONJUNTO)
    b: str = Field(..., title="Sólido B", description=_CONJUNTO)
    kind: Literal["perno", "soldadura", "pegado", "contacto"] = Field("perno", title="Tipo de unión")
    size: str | None = Field(
        None, pattern=r"^M\d{1,2}$", title="Métrica del perno",
        description="solo kind='perno' (M3–M24, ISO 898-1); si falta, el chequeo la reporta como no "
        "verificable",
    )
    qty: int | None = Field(None, ge=1, le=100, title="Nº de pernos de la unión")
    throat_mm: float | None = Field(
        None, gt=0, title="Garganta del cordón (mm)",
        description="solo kind='soldadura'; garganta a = 0.707·cateto",
    )
    length_mm: float | None = Field(None, gt=0, title="Longitud total de cordón (mm)")
    nota: str = Field(
        "", max_length=500, title="Nota",
        description="kind='perno' sin tornillería modelada: la BOM la compra leyendo la nota "
        "(«M8x40 DIN 933 + tuerca», «autorroscante», «prisionero», «punta roscada» = sin perno; "
        "«tuerca»/«pasante» suma la tuerca; «incluido»/«sin perno» = nada que comprar); sin largo, "
        "la fila lo pide",
    )
    material_tornilleria: str | None = Field(
        None, max_length=60, title="Material de la tornillería",
        description="kind='perno' sin tornillería modelada: el material del perno y la tuerca que "
        "compra la BOM («acero inoxidable A2-70», «acero 8.8 zincado»); sin él, el de la nota "
        "(A2/A4, AISI 304/316, inox) o el de la ficha (acero 8.8). El de las piezas unidas es "
        "set_material",
    )
