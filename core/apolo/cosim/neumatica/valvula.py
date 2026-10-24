"""Qué vías une una válvula en cada posición (plan V8.9 D6), por la numeración de ISO 5599-3.

1 alimentación, 2 y 4 trabajo, 3 y 5 escape; la bobina (o el pilotaje) 14 conecta 1→4 y la 12
conecta 1→2. `conexion(valvula, puerto)` dice a qué vía va un puerto de TRABAJO en la posición
actual: «1» (alimentación), «3» / «5» (su escape) o None (bloqueado).

  5/2           «14»: 1→4, 2→3        «12»: 1→2, 4→5
  5/3 «0»       centro cerrado: 2 y 4 bloqueados · a escape: 2→3, 4→5 · a presión: 1→2, 1→4
  3/2 NC        «12»: 1→2             «0»: 2→3 (1 bloqueado)
  3/2 NA        «0»: 1→2              «12»: 2→3 (1 bloqueado)
  2/2 NC / NA   como la 3/2 sin escape (el 2 queda bloqueado en vez de descargar)

La conductancia de cada vía es la de la ficha: `caudal` para 1→2 / 1→4 y `escape` para 2→3 /
4→5; una ficha sin `escape` usa el de alimentación y lo declara (`HIPOTESIS_ESCAPE`).

Puro.
"""

from __future__ import annotations

HIPOTESIS_ESCAPE = "la vía de escape de la válvula con el C y b de su alimentación (la ficha no trae `escape`)"

_5 = {"14": {"4": "1", "2": "3"}, "12": {"2": "1", "4": "5"}}
_CENTRO = {"centro_cerrado": {"2": None, "4": None}, "centro_escape": {"2": "3", "4": "5"},
           "centro_presion": {"2": "1", "4": "1"}}


def tabla(vias: int, mando: str, reposo: str | None, posicion: str) -> dict:
    """{puerto de trabajo: «1» | «3» | «5» | None} de una válvula en `posicion`."""
    if vias == 5:
        return _CENTRO[mando] if posicion == "0" else _5[posicion]
    escape = "3" if vias == 3 else None
    une = (posicion == "12") == (reposo != "NA")
    return {"2": "1" if une else escape}


def conexion(m, puerto: str) -> str | None:
    """A qué vía va el `puerto` de trabajo de la electroválvula `m` (modelo con `vias`, `mando`,
    `aire` y `posicion`)."""
    return tabla(m.vias, m.mando, (m.aire or {}).get("reposo"), m.posicion).get(puerto)


def puertos_trabajo(vias: int) -> tuple[str, ...]:
    return ("2", "4") if vias == 5 else ("2",)
