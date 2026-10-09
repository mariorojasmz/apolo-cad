"""Referencias a bornes: `[=función][+ubicación]-dispositivo:borne` (V8.1 D4, IEC 81346).

  - «-K1:A1» basta dentro de una máquina;
  - «+TAB1-K1:A1» fija además el lugar (debe coincidir con la `ubicacion` del dispositivo);
  - «=Faja1-K1:A1» lleva el aspecto de función que pone `insert_project` (D9).

`parse_referencia` da una `Referencia` o un `ReferenciaError` que dice qué falta, con la forma
correcta. `sugerir` es el «¿quisiste decir…?» por difflib (mismo umbral que
`services/lookup.suggest_ids`, que no se importa: esta capa no conoce el documento).
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

FORMA = "[=función][+ubicación]-dispositivo:borne, p. ej. «-K1:A1» o «+TAB1-K1:A1»"
_ASPECTO = r"[A-Za-z0-9_.]+"
_RE = re.compile(
    rf"^(?:=(?P<f>{_ASPECTO}))?(?:\+(?P<u>{_ASPECTO}))?-(?P<d>[A-Za-z][A-Za-z0-9_.]*)"
    r"(?::(?P<b>[^:\s]+))?$"
)
#: Mismo umbral que `services/lookup.suggest_ids`.
CORTE = 0.55


class ReferenciaError(ValueError):
    """Una referencia mal escrita: el mensaje dice la forma correcta."""


@dataclass(frozen=True)
class Referencia:
    dispositivo: str  # sin el «-»: «K1»
    borne: str | None = None
    funcion: str | None = None  # sin el «=»
    ubicacion: str | None = None  # sin el «+»

    @property
    def designacion(self) -> str:
        """Designación del dispositivo con su aspecto de función («=Faja1-K1» o «-K1»)."""
        return (f"={self.funcion}" if self.funcion else "") + f"-{self.dispositivo}"

    @property
    def producto(self) -> str:
        """Sólo el aspecto de producto: «-K1»."""
        return f"-{self.dispositivo}"

    def __str__(self) -> str:
        return formatear(self)


def formatear(ref: Referencia) -> str:
    """Forma canónica: «=F+U-D:B» (cada parte sólo si existe)."""
    out = f"={ref.funcion}" if ref.funcion else ""
    out += f"+{ref.ubicacion}" if ref.ubicacion else ""
    out += f"-{ref.dispositivo}"
    return out + (f":{ref.borne}" if ref.borne else "")


def _diagnostico(t: str) -> str:
    if any(c.isspace() for c in t):
        return f"«{t}» lleva espacios; una referencia va junta: {FORMA}"
    if t.count(":") > 1:
        return f"«{t}» tiene más de un «:»; el borne va una sola vez al final: {FORMA}"
    cabeza = t.split(":", 1)[0]
    if "-" not in cabeza:
        sugerida = f"-{t}" if t[:1].isalpha() else None
        pista = f" ¿Quisiste decir «{sugerida}»?" if sugerida else ""
        return f"a «{t}» le falta el dispositivo con su «-»: {FORMA}.{pista}"
    if t.endswith(":"):
        return f"«{t}» termina en «:» sin borne: {FORMA}"
    return f"«{t}» no es una referencia válida: {FORMA}"


def parse_referencia(texto, *, exige_borne: bool = False) -> Referencia:
    """Texto → `Referencia`. `exige_borne`: un extremo de conductor necesita el «:borne»."""
    if not isinstance(texto, str) or not texto.strip():
        raise ReferenciaError(f"referencia vacía: {FORMA}")
    t = texto.strip()
    m = _RE.match(t)
    if not m:
        raise ReferenciaError(_diagnostico(t))
    ref = Referencia(dispositivo=m["d"], borne=m["b"], funcion=m["f"], ubicacion=m["u"])
    if exige_borne and not ref.borne:
        raise ReferenciaError(f"a «{t}» le falta el borne: «{formatear(ref)}:<borne>», p. ej. «-K1:A1»")
    return ref


def parse_designacion(texto) -> Referencia:
    """Designación de un dispositivo («-K1», «=Faja1-K1»): sin ubicación ni borne."""
    ref = parse_referencia(texto)
    if ref.borne or ref.ubicacion:
        raise ReferenciaError(
            f"«{texto}» es una referencia, no una designación: la designación es «{ref.designacion}» "
            "(la ubicación va aparte y el borne sólo en los conductores)")
    return ref


def sugerir(faltante: str, candidatos, limite: int = 3) -> list[str]:
    """Candidatos parecidos (difflib), sin el propio faltante. Un id corto («A3») se compara
    con un umbral algo menor (con dos caracteres, uno en común da 0,5) y, a igual parecido, van
    primero los que comparten el prefijo no numérico («A1», «A2» antes que «3»)."""
    faltante = str(faltante)
    pool = [c for c in dict.fromkeys(str(c) for c in candidatos) if c != faltante]
    corte = CORTE if len(faltante) > 3 else 0.5
    prefijo = re.match(r"\D*", faltante).group()
    puntaje = {c: difflib.SequenceMatcher(None, faltante, c).ratio() for c in pool}
    hits = [c for c in pool if puntaje[c] >= corte]
    hits.sort(key=lambda c: (not (prefijo and c.startswith(prefijo)), -puntaje[c], c))
    return hits[:limite]


def sufijo_sugerencia(faltante: str, candidatos, limite: int = 3) -> str:
    """« ¿Quisiste decir: -K1, -K2?» o '' si nada se parece."""
    hits = sugerir(faltante, candidatos, limite)
    return " ¿Quisiste decir: " + ", ".join(hits) + "?" if hits else ""
