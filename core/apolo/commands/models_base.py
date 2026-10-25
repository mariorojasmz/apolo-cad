"""Base de los params: `Vec3`, `Rot3`, el truncado a entero de los campos `int` que
aceptan '=expresión' y las listas de catálogo que publican los enums.

Sale de `models.py` (fachada) por tamaño; no importa ninguna otra familia.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field


def _floor_to_int(v: Any) -> Any:
    """Trunca a entero (floor) un número ya resuelto, dejando pasar lo demás.

    Permite que un campo entero acepte '=expresión': resolve_params convierte la
    expresión a float ANTES de validar, y este before-validator lo lleva a int
    (p. ej. '=largo/paso' = 13.33 → 13). Un int literal pasa intacto."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return math.floor(v)
    return v


class Vec3(BaseModel):
    x: float = Field(0, description="mm")
    y: float = Field(0, description="mm")
    z: float = Field(0, description="mm")

    def tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


class Rot3(BaseModel):
    x: float = Field(0, ge=-360, le=360, description="grados")
    y: float = Field(0, ge=-360, le=360, description="grados")
    z: float = Field(0, ge=-360, le=360, description="grados")

    def tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


def _roller_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("rodillos")


def _profile_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("perfiles")


def _motor_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("motorreductores")
