"""El ítem de la puerta de publicación (plan puerta-de-publicacion, D1): la unidad de la ficha
de calidad. Puro.

Un ítem dice QUÉ se controló (`id`, `titulo`), qué MODO DE FALLA previene (DFMEA), con qué
NORMA o «criterio de diseño», su ESTADO y la EVIDENCIA (números, nunca adjetivos):

- `OK`: se midió y cumple;
- `FALLA`: se midió y no cumple;
- `SIN_EVALUAR`: aplica pero no se pudo medir (falta un dato o la geometría no se reconoce) —
  bloquea igual que FALLA (D1: el VERDE de hoy mezclaba «no se pudo ver» con «está bien»);
- `NO_APLICA`: no aplica a esta máquina, con el porqué en `detalle`.

Se publica sólo si TODO ítem aplicable está OK (`aprobado`).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

OK = "OK"
FALLA = "FALLA"
SIN_EVALUAR = "SIN_EVALUAR"
NO_APLICA = "NO_APLICA"
ESTADOS = (OK, FALLA, SIN_EVALUAR, NO_APLICA)

#: De peor a mejor: el estado de un conjunto es el peor de sus partes (NO_APLICA no cuenta).
_GRAVEDAD = {FALLA: 0, SIN_EVALUAR: 1, OK: 2, NO_APLICA: 3}

#: Cuántos casos concretos lleva la evidencia de un ítem que agrega muchos (el resto, contado).
MAX_CASOS = 20


@dataclass
class Item:
    id: str
    titulo: str
    estado: str
    modo_de_falla: str
    norma: str
    evidencia: dict = field(default_factory=dict)
    piezas: list[str] = field(default_factory=list)
    detalle: str = ""

    def __post_init__(self) -> None:
        if self.estado not in ESTADOS:
            raise ValueError(f"estado '{self.estado}' inválido: {', '.join(ESTADOS)}")

    def to_dict(self) -> dict:
        return asdict(self)


def peor(estados) -> str:
    """El peor estado aplicable de `estados`; NO_APLICA si no hay ninguno aplicable."""
    aplicables = [e for e in estados if e != NO_APLICA]
    if not aplicables:
        return NO_APLICA
    return min(aplicables, key=_GRAVEDAD.__getitem__)


def aprobado(items) -> bool:
    """D1: TODO ítem aplicable está OK (SIN_EVALUAR bloquea como FALLA). Sin ítems aplicables,
    no hay nada que aprobar: False (una puerta vacía no es una puerta aprobada)."""
    estados = [i.estado if isinstance(i, Item) else i["estado"] for i in items]
    aplicables = [e for e in estados if e != NO_APLICA]
    return bool(aplicables) and all(e == OK for e in aplicables)


def recortar(casos: list, n: int = MAX_CASOS) -> dict:
    """`{casos, casos_omitidos?}`: nunca un recorte silencioso."""
    out: dict = {"casos": casos[:n]}
    if len(casos) > n:
        out["casos_omitidos"] = len(casos) - n
    return out
