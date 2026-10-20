"""Tensiones del catálogo eléctrico: texto ↔ forma estructurada, y la tensión entre dos polos.

Una tensión del YAML se escribe como en una placa:
  - «24 VDC», «10-30 VDC» (rango), «0-10 VDC»;
  - «220 VAC», «100-240 VAC», «24 VAC/DC» (universal, `UC`);
  - «220 VAC 3F 60 Hz» (trifásica sin neutro), «380/220 VAC 3F+N 60 Hz» (con neutro: la mayor
    es la de línea, la menor la de fase);
  - «220 VAC 2F 60 Hz»: dos fases de una red trifásica sin neutro (la monofásica habitual en
    Lima, plan V8.3 D15), polos L1 y L2; «220 VAC 60 Hz» (1F) es fase–neutro, polos L y N;
  - «220/380 VAC 3F» en una CARGA: tensiones aceptadas (el motor en triángulo o en estrella).

La tolerancia de una tensión nominal única es 0,9–1,1 Un (IEC 60204-1 §4.3, tensión de régimen).
Un rango ya ES la tolerancia del aparato: se compara tal cual.

Puro: no conoce el documento ni el catálogo.
"""

from __future__ import annotations

import cmath
import math
import re
from dataclasses import dataclass

#: Tolerancia de régimen de una tensión nominal única (IEC 60204-1 §4.3).
TOLERANCIA = (0.9, 1.1)

#: Polos válidos por tipo de fuente. «-», N y PE son polos de REFERENCIA (ver `es_referencia`).
POLOS_DC = ("+", "-")
POLOS_1F = ("L", "N", "PE")
POLOS_3F = ("L1", "L2", "L3", "N", "PE")
POLOS_2F = ("L1", "L2", "PE")
REFERENCIAS = ("-", "N", "PE")

_EJEMPLOS = "«24 VDC», «220 VAC 3F 60 Hz», «380/220 VAC 3F+N 60 Hz», «100-240 VAC» o «24 VAC/DC»"
_NUM = r"\d+(?:\.\d+)?"
_RE = re.compile(
    rf"^(?P<v>{_NUM}(?:\s*[/-]\s*{_NUM})*)\s*V\s*(?P<tipo>AC/DC|DC/AC|AC|DC|UC)"
    rf"(?:\s+(?P<fases>3F\+N|3F|2F|1F))?"
    rf"(?:\s+(?P<f>{_NUM}(?:\s*[/-]\s*{_NUM})?)\s*HZ)?$"
)


@dataclass(frozen=True)
class Tension:
    """Tensión estructurada. `valores` son las nominales aceptadas (una o varias); `rango`, un
    intervalo (mín, máx) cuando el texto es «a-b». `tipo`: AC, DC o UC (AC o DC)."""

    tipo: str
    valores: tuple[float, ...] = ()
    rango: tuple[float, float] | None = None
    fases: int | None = None
    neutro: bool = False
    frecuencia_hz: tuple[float, ...] = ()
    texto: str = ""

    def __str__(self) -> str:
        return self.texto

    @property
    def linea(self) -> float | None:
        """Tensión entre fases (3F) o la única nominal (1F/DC). None si es un rango."""
        return max(self.valores) if self.valores else None

    @property
    def fase(self) -> float | None:
        """Tensión fase–neutro de una fuente trifásica: la menor de «380/220», o U/√3."""
        if self.fases != 3 or not self.valores:
            return None
        if self.neutro and len(self.valores) > 1:
            return min(self.valores)
        return max(self.valores) / math.sqrt(3)


def _numeros(texto: str) -> list[float]:
    return [float(x) for x in re.split(r"\s*[/-]\s*", texto.strip())]


def parse_tension(texto) -> Tension:
    """Texto de placa → `Tension`. Un texto ilegible levanta ValueError con un ejemplo."""
    if not isinstance(texto, str) or not texto.strip():
        raise ValueError(f"tensión vacía o no textual ({texto!r}): se espera p. ej. {_EJEMPLOS}")
    norm = " ".join(texto.replace(",", ".").upper().split())
    m = _RE.match(norm)
    if not m:
        raise ValueError(f"tensión ilegible «{texto}»: se espera p. ej. {_EJEMPLOS}")
    tipo = {"AC/DC": "UC", "DC/AC": "UC"}.get(m["tipo"], m["tipo"])
    crudo = m["v"]
    nums = _numeros(crudo)
    valores: tuple[float, ...] = ()
    rango = None
    if "-" in crudo:
        if len(nums) != 2 or "/" in crudo or nums[0] >= nums[1]:
            raise ValueError(f"tensión «{texto}»: un rango es «mín-máx» con mín < máx (p. ej. «10-30 VDC»)")
        rango = (nums[0], nums[1])
    else:
        valores = tuple(nums)
    fases_txt = m["fases"]
    if tipo != "AC" and fases_txt:
        raise ValueError(f"tensión «{texto}»: «{fases_txt}» sólo vale en alterna (VAC)")
    fases = None
    neutro = False
    if tipo == "AC":
        fases = 3 if fases_txt and fases_txt.startswith("3F") else 2 if fases_txt == "2F" else 1
        neutro = fases_txt == "3F+N"
    if m["f"] and tipo == "DC":
        raise ValueError(f"tensión «{texto}»: una tensión continua no lleva frecuencia")
    frecuencia = tuple(_numeros(m["f"])) if m["f"] else ()
    if neutro and len(valores) == 2 and not math.isclose(max(valores) / min(valores), math.sqrt(3), rel_tol=0.03):
        raise ValueError(f"tensión «{texto}»: en «línea/fase» la mayor debe ser √3 veces la menor (380/220)")
    return Tension(tipo=tipo, valores=valores, rango=rango, fases=fases, neutro=neutro,
                   frecuencia_hz=frecuencia, texto=texto.strip())


def polos_validos(t: Tension) -> tuple[str, ...]:
    """Polos que puede imponer una FUENTE con esta tensión."""
    if t.tipo == "DC":
        return POLOS_DC
    if t.tipo == "AC" and t.fases == 3:
        return POLOS_3F if t.neutro else ("L1", "L2", "L3", "PE")
    if t.tipo == "AC" and t.fases == 2:
        return POLOS_2F
    if t.tipo == "AC":
        return POLOS_1F
    return ()


def polos_obligatorios(t: Tension) -> tuple[str, ...]:
    """Polos que una fuente con esta tensión DEBE mapear a un borne."""
    if t.tipo == "DC":
        return POLOS_DC
    if t.tipo == "AC" and t.fases == 3:
        return ("L1", "L2", "L3", "N") if t.neutro else ("L1", "L2", "L3")
    if t.tipo == "AC" and t.fases == 2:
        return ("L1", "L2")
    return ("L", "N")


def es_referencia(polo: str) -> bool:
    """«-», N y PE: unir referencias de fuentes distintas no es un cortocircuito (es el 0 V común
    o la masa); unir un polo ACTIVO a otro sistema, sí."""
    return polo in REFERENCIAS


def _fasor(t: Tension, polo: str) -> complex | None:
    if t.fases == 3:
        # el módulo sale de la tensión de LÍNEA (la de placa: 380 en «380/220», cuya fase exacta
        # es 219,4 V): así L-L da la nominal y L-N queda dentro de su tolerancia
        uf = (t.linea or 0.0) / math.sqrt(3)
        ang = {"L1": 0.0, "L2": -120.0, "L3": 120.0}
        if polo in ang:
            return cmath.rect(uf, math.radians(ang[polo]))
        if polo == "N":
            return 0j
        # PE = neutro sólo si la red lo trae (esquema TN supuesto y DECLARADO); sin neutro, la
        # tensión fase–tierra depende del esquema de la red y no se infiere.
        return 0j if polo == "PE" and t.neutro else None
    if t.fases == 2:
        # dos fases de una red trifásica sin neutro: L1–L2 da la de línea; a tierra no se infiere
        uf = (t.linea or 0.0) / math.sqrt(3)
        ang = {"L1": 0.0, "L2": -120.0}
        return cmath.rect(uf, math.radians(ang[polo])) if polo in ang else None
    u = t.linea or 0.0
    return {"L": complex(u, 0.0), "N": 0j, "PE": 0j}.get(polo)


def tension_entre(t: Tension, polo_a: str, polo_b: str) -> float | None:
    """Tensión del polo A respecto del B de UNA misma fuente. En DC lleva signo (+24 si A es el
    «+»); en AC es el módulo de la diferencia de fasores. None si no se puede inferir."""
    if t.tipo == "DC":
        u = t.linea
        if u is None:
            return None
        v = {"+": u, "-": 0.0}
        if polo_a not in v or polo_b not in v:
            return None
        return v[polo_a] - v[polo_b]
    fa, fb = _fasor(t, polo_a), _fasor(t, polo_b)
    if fa is None or fb is None:
        return None
    return round(abs(fa - fb), 6)


def admite(nominal: Tension, tipo: str, valor: float, *, polar: bool = False,
           preferida: float | None = None) -> bool:
    """¿Una carga de tensión `nominal` admite `valor` (V) de tipo AC/DC? `polar`: en DC exige
    el signo (+ en el primer borne). `preferida`: la nominal elegida por un ajuste (el motor en
    triángulo toma la menor de «220/380»)."""
    if nominal.tipo != "UC" and nominal.tipo != tipo:
        return False
    if tipo == "DC" and polar and valor < 0:
        return False
    v = abs(valor)
    if nominal.rango is not None:
        lo, hi = nominal.rango
        return lo - 1e-9 <= v <= hi + 1e-9
    candidatas = (preferida,) if preferida is not None else nominal.valores
    return any(TOLERANCIA[0] * u - 1e-9 <= v <= TOLERANCIA[1] * u + 1e-9 for u in candidatas)


def formato_valor(tipo: str, valor: float) -> str:
    """«220 VAC», «24 VDC», «-24 VDC» (polaridad invertida)."""
    redondo = round(valor, 1)
    num = f"{redondo:g}"
    return f"{num} V{'DC' if tipo == 'DC' else 'AC'}"
