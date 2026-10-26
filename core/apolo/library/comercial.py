"""La identificación COMERCIAL de un proyecto (plan cotizacion-identificada-y-ajustes-por-escenario,
D1): a quién va la cotización, con qué número y revisión. Puro: valida lo que llega y limpia el
nombre interno del proyecto; quien la lee de un documento es `services/identificacion.py`.

Es metadato del manifest (`Document.comercial`), no comando (regla «Metadato ≠ comando» de la
raíz): ni firma ni regenera. La CARGA no valida (un manifest viejo abre tal cual, como los
requisitos); el setter y una extensión que la aporte (`IdentificacionCosteo`) sí.
"""

from __future__ import annotations

import re

#: Los campos, todos texto opcional; ningún otro.
CAMPOS = ("titulo", "cliente", "numero", "revision")
TEXTO_MAX = 80  # caracteres por campo: el título más largo cabe a 3.4 mm sin recortarse

_COPIA = re.compile(r"(?:\s*\(copia\))+\s*$", re.IGNORECASE)


def normalizar(fields) -> dict:
    """`{campo: texto}` limpio (sin espacios de más; un vacío o `None` se quita), o `ValueError`
    con el motivo: una clave que no es de `CAMPOS`, un valor que no es texto, de varias líneas o
    de más de `TEXTO_MAX` caracteres. `{}` vale (borra la identificación)."""
    if fields is None:
        return {}
    if not isinstance(fields, dict):
        raise ValueError(f"la identificación comercial es un objeto {{{', '.join(CAMPOS)}}}, "
                         f"no {type(fields).__name__}")
    sobran = sorted(str(k) for k in fields if k not in CAMPOS)
    if sobran:
        raise ValueError(f"campos desconocidos en `comercial`: {', '.join(sobran)} "
                         f"(válidos: {', '.join(CAMPOS)})")
    out: dict = {}
    for k in CAMPOS:
        v = fields.get(k)
        if v is None:
            continue
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            v = f"{v:g}" if isinstance(v, float) else str(v)  # «numero: 125» también vale
        if not isinstance(v, str):
            raise ValueError(f"`comercial.{k}` es un texto, no {v!r}"[:200])
        v = v.strip()
        if not v:
            continue
        if len(v.splitlines()) > 1:
            raise ValueError(f"`comercial.{k}` es de una sola línea")
        if len(v) > TEXTO_MAX:
            raise ValueError(f"`comercial.{k}` tiene {len(v)} caracteres (máximo {TEXTO_MAX})")
        out[k] = v
    return out


def titulo_limpio(nombre) -> str:
    """El nombre del proyecto sin los sufijos «(copia)» que deja duplicar (uno o varios)."""
    limpio = _COPIA.sub("", str(nombre or "")).strip()
    return limpio or "Sin título"
