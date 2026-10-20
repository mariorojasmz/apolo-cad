"""Direcciones IEC directas (D4): `%IX0.0` ↔ borne `I0.0`, `%QX0.0` ↔ `Q0.0`, `%IW0` ↔ `AI0`.

La correspondencia es la del PLC del catálogo (bornes `I0.0…I1.5`, `Q0.0…Q1.1`, `AI0/AI1`).
La analógica entra como INT 0–27648 para 0–10 V, como S7: la conversión de voltios a
cuentas es del modelo del dispositivo (F2), no del programa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_RE = re.compile(r"^%([IQ])([XW])(\d+)(?:\.(\d+))?$", re.IGNORECASE)

#: Escala de la entrada analógica: 0–10 V → 0–27648 (S7; plan V8.3 D4).
ESCALA_AI = 27648


@dataclass(frozen=True)
class Direccion:
    texto: str      # canónico, en mayúsculas: «%IX0.0»
    area: str       # «I» (entrada) o «Q» (salida)
    tamano: str     # «X» (bit) o «W» (palabra)
    byte: int
    bit: int | None

    @property
    def tipo(self) -> str:
        return "BOOL" if self.tamano == "X" else "INT"

    @property
    def es_entrada(self) -> bool:
        return self.area == "I"

    @property
    def borne(self) -> str:
        if self.tamano == "X":
            return f"{self.area}{self.byte}.{self.bit}"
        return f"A{self.area}{self.byte}"

    @property
    def ident(self) -> str:
        """Nombre del hueco de la imagen de E/S en el código generado (`d_ix0_0`)."""
        sufijo = f"{self.byte}_{self.bit}" if self.bit is not None else f"{self.byte}"
        return f"d_{self.area.lower()}{self.tamano.lower()}{sufijo}"


def parsear(texto: str) -> Direccion | str:
    """La dirección, o el motivo por el que no vale (texto para el error)."""
    m = _RE.match(texto)
    if not m:
        return (f"«{texto}» no es una dirección del subconjunto: usa %IX<byte>.<bit>, "
                "%QX<byte>.<bit> o %IW<n>")
    area, tamano, byte, bit = m.group(1).upper(), m.group(2).upper(), m.group(3), m.group(4)
    if tamano == "X":
        if bit is None:
            return f"«{texto}» lleva bit: %{area}X{byte}.0 … %{area}X{byte}.7"
        if int(bit) > 7:
            return f"«{texto}»: el bit va de 0 a 7"
    elif bit is not None:
        return f"«{texto}»: una palabra no lleva bit (%{area}W{byte})"
    if area == "Q" and tamano == "W":
        return f"«{texto}»: las salidas analógicas quedan fuera de V8.3"
    d = Direccion(f"%{area}{tamano}{byte}" + (f".{bit}" if bit is not None else ""),
                  area, tamano, int(byte), int(bit) if bit is not None else None)
    return d
