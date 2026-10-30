"""Las siglas de NORMA y el patrón «sigla + número» que las reconoce en un nombre. Una fuente para
`designacion_comercial` (la norma con la que se compra una pieza modelada a mano) y
`services/rotulos` (el número que sigue a una sigla es la norma, no la instancia: «DIN 933»).

La sigla va en MAYÚSCULA, como se escribe, y seguida de su número («EN 733», «EN 10088-2»,
«ASTM A36», «IEC 60204-1», «ASME B16.11»): así «tubo en 3 tramos» no es una norma. DIN, ISO, ASME
y ANSI se leen además en minúscula, como antes de unificar (un nombre viejo «din 933» sigue
dando su norma). El número admite la letra de serie de ASTM, ASME y JIS (A/B) y nada más: «EN M12»
no es la norma «EN M12». Puro: lee texto.
"""

from __future__ import annotations

import re

#: siglas de organismos de norma (nacionales, regionales e internacionales)
SIGLAS_NORMA = frozenset({
    "DIN", "ISO", "EN", "ASTM", "AISI", "SAE", "ANSI", "ASME", "UNE", "JIS", "IEC", "NTP", "BS",
    "GB", "NFPA", "AWS", "API", "IRAM", "ABNT", "NCh", "NOM"})
#: las que ya se leían sin distinguir mayúsculas
_SIN_MAYUSCULA = ("DIN", "ISO", "ASME", "ANSI")

_SIGLAS_EXACTAS = sorted(SIGLAS_NORMA - set(_SIN_MAYUSCULA), key=len, reverse=True)
#: grupos: 1 = sigla, 2 = número («733», «A36», «B16.11»), 3 = sufijo de parte («-2», «-52»)
NORMA_RE = re.compile(
    rf"\b((?i:{'|'.join(_SIN_MAYUSCULA)})|{'|'.join(_SIGLAS_EXACTAS)})"
    r"\s*-?\s*([AB]?\d+(?:\.\d+)*)(-\d+(?:[.,]\d+)?)?\b")


def sigla(m: re.Match) -> str:
    """La sigla de un `NORMA_RE` como se escribe la norma («din» → «DIN», «NCh» queda)."""
    s = m.group(1)
    return s.upper() if s.upper() in _SIN_MAYUSCULA else s


def norma(m: re.Match) -> str:
    """«EN 10088» de un `NORMA_RE` sobre «EN 10088-2»: sigla y número, sin la parte."""
    return f"{sigla(m)} {m.group(2).upper()}"
