"""Los tipos de la colocación del tablero (plan V8.5 D2): lo que entra (`Aparato`, `Gabinete`,
`Reglas`) y lo que sale (`Layout` con sus `Colocado`, `Riel`, `Canaleta`, `FilaRiel`). Puros,
sin OCCT ni catálogo; las reglas están en `colocacion.py` y la puerta en `colocacion_puerta.py`.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

CLASES = ("alimentacion", "potencia", "control", "bornera")
_CLASE_POR_TIPO = {"seccionador": "alimentacion", "itm": "alimentacion", "fusible": "alimentacion",
                   "guardamotor": "potencia", "contactor": "potencia", "rele_termico": "potencia",
                   "variador": "potencia"}
MONTAJES = ("din", "placa", "puerta")
CLAVES_OVERRIDE = ("fila", "orden", "posicion", "acopla")


class ColocacionError(ValueError):
    """No se puede colocar: el mensaje dice qué sobra, cuánto falta y cómo seguir."""


@dataclass(frozen=True)
class Reglas:
    canaleta_ancho_mm: float = 25.0   # huella de CANALETA-25X40 en la placa
    canaleta_alto_mm: float = 40.0    # lo que sale de la placa
    riel_alto_mm: float = 7.5         # RIEL-DIN-TH35-7.5 (EN 60715)
    reserva: float = 0.20             # riel libre por fila (A13)
    holgura_puerta_mm: float = 10.0   # entre lo de detrás de la puerta y lo de la placa
    paso_puerta_mm: tuple = (70.0, 80.0)   # cuadrícula de la puerta (u, v)
    borde_puerta_mm: tuple = (40.0, 60.0)  # del lado opuesto a la bisagra y de arriba al 1.er centro

    def supuestos(self) -> dict:
        return {k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(self).items()}


@dataclass(frozen=True)
class Acople:
    simbolos: tuple[str, ...]
    cara: str  # frente | abajo | arriba | izquierda | derecha
    orden: int = 1


@dataclass(frozen=True)
class Aparato:
    designacion: str
    ref: str
    montaje: str          # din | placa | puerta
    ancho: float          # u (a lo largo del riel; una bornera: × cantidad)
    alto: float           # v
    fondo: float          # w: lo que sale de su apoyo; en la puerta, lo de DETRÁS (chapa incluida)
    clase: str = "control"
    funcion: str = ""     # letra IEC 81346-2 de su ficha (ordena la puerta)
    simbolo: str = ""
    delante: float = 0.0  # en la puerta: lo que asoma delante
    acopla: Acople | None = None
    pieza: str | None = None

    def __post_init__(self) -> None:
        if self.montaje not in MONTAJES:
            raise ColocacionError(f"{self.designacion}: montaje «{self.montaje}» no va dentro del "
                                  f"tablero (válidos: {', '.join(MONTAJES)})")
        if min(self.ancho, self.alto, self.fondo) <= 0:
            raise ColocacionError(f"{self.designacion} ({self.ref}): cotas no positivas "
                                  f"{self.ancho:g}×{self.alto:g}×{self.fondo:g}")


@dataclass(frozen=True)
class Gabinete:
    ref: str
    placa_ancho: float
    placa_alto: float
    fondo_util: float
    espesor_puerta: float
    bisagra: str  # izquierda | derecha (vista de frente)

    @property
    def area(self) -> float:
        return self.placa_ancho * self.placa_alto


@dataclass(frozen=True)
class Colocado:
    designacion: str
    ref: str
    zona: str             # placa | puerta
    u0: float
    v0: float
    ancho: float
    alto: float
    w0: float             # profundidad trasera (desde el frente de la placa)
    w1: float             # profundidad delantera
    fila: str             # «alimentacion», «control 2», «columna», «puerta», «fija»
    acoplado_a: str | None = None
    pieza: str | None = None

    def solapa(self, u0, v0, u1, v1) -> bool:
        return self.u0 < u1 and u0 < self.u0 + self.ancho and self.v0 < v1 and v0 < self.v0 + self.alto


@dataclass(frozen=True)
class Riel:
    fila: str
    u0: float
    u1: float
    v: float  # eje del riel


@dataclass(frozen=True)
class Canaleta:
    orientacion: str  # h | v
    u0: float
    u1: float
    v0: float
    v1: float


@dataclass(frozen=True)
class FilaRiel:
    nombre: str
    riel_mm: float
    ocupado_mm: float

    @property
    def reserva(self) -> float:
        return 1.0 - self.ocupado_mm / self.riel_mm if self.riel_mm > 0 else 0.0


@dataclass(frozen=True)
class Layout:
    gabinete: str
    aparatos: tuple[Colocado, ...]
    rieles: tuple[Riel, ...]
    canaletas: tuple[Canaleta, ...]
    filas: tuple[FilaRiel, ...]
    avisos: tuple[str, ...] = ()
    supuestos: dict = field(default_factory=dict)

    def de(self, designacion: str) -> Colocado:
        return next(a for a in self.aparatos if a.designacion == designacion)


class _NoEntra(Exception):
    def __init__(self, problemas: list[str]):
        super().__init__("; ".join(problemas))
        self.problemas = problemas


def clase_de(tipo: str | None, bornera: bool) -> str:
    """La fila de riel de un aparato por el `modelo.tipo` de su ficha (D2)."""
    if bornera:
        return "bornera"
    return _CLASE_POR_TIPO.get(tipo or "", "control")


def orden_natural(designacion: str) -> tuple:
    """«-Q2» antes que «-Q10»: letra, número y lo que sigue."""
    m = re.match(r"^(.*?)(\d+)(.*)$", designacion)
    return (m[1], int(m[2]), m[3]) if m else (designacion, -1, "")


def ordenar(aparatos: list[Aparato], overrides: dict, clave=None) -> list[Aparato]:
    """Por `clave` (designación por defecto) y después cada `orden` pedido en su lugar."""
    base = sorted(aparatos, key=clave or (lambda a: orden_natural(a.designacion)))
    pedidos = sorted((a for a in base if "orden" in (overrides.get(a.designacion) or {})),
                     key=lambda a: overrides[a.designacion]["orden"])
    resto = [a for a in base if a not in pedidos]
    for a in pedidos:
        resto.insert(min(overrides[a.designacion]["orden"] - 1, len(resto)), a)
    return resto
