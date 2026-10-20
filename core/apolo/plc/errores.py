"""Errores del PLC: de compilación (con línea y columna) y fallas de ejecución.

Los textos son para quien programa el PLC (tuteo neutro, en español) y dicen qué hacer:
«¿quisiste decir…?» sale de `difflib` sobre los nombres visibles en ese punto.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorST:
    """Un error del programa ST, ubicado en la fuente (línea y columna desde 1)."""

    linea: int
    columna: int
    mensaje: str

    def __str__(self) -> str:
        return f"línea {self.linea}, columna {self.columna}: {self.mensaje}"

    def a_dict(self) -> dict:
        return {"linea": self.linea, "columna": self.columna, "mensaje": self.mensaje}


class ErrorCompilacion(Exception):
    """El programa no compila. `errores` trae al menos uno, en orden de aparición."""

    def __init__(self, errores: list[ErrorST]):
        self.errores = sorted(errores, key=lambda e: (e.linea, e.columna))
        super().__init__("\n".join(str(e) for e in self.errores))


class ErrorSintaxis(Exception):
    """Uso interno del parser: corta en el primer error de sintaxis."""

    def __init__(self, error: ErrorST):
        self.error = error
        super().__init__(str(error))


class FallaPLC(Exception):
    """Falla en ejecución: el PLC pasa a STOP y sus salidas caen (D6)."""

    def __init__(self, tipo: str, mensaje: str):
        self.tipo = tipo
        self.mensaje = mensaje
        super().__init__(mensaje)


def sugerir(nombre: str, candidatos: Iterable[str]) -> str:
    """« ¿Quisiste decir «x»?» con el candidato más parecido, o '' si ninguno se parece."""
    por_minuscula = {c.lower(): c for c in candidatos}
    cerca = difflib.get_close_matches(nombre.lower(), list(por_minuscula), n=1, cutoff=0.6)
    return f" ¿Quisiste decir «{por_minuscula[cerca[0]]}»?" if cerca else ""
