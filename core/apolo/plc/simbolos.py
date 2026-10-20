"""Símbolos del compilador (variables y POU) y la disposición de memoria que usa el runtime."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import ast_st as A
from .direcciones import Direccion
from .tipos import InterfazFB


@dataclass
class Var:
    nombre: str                 # escritura original
    tipo: object                # elemental (str), `Arreglo` o `InterfazFB`
    clase: str                  # local, entrada, salida, global, retorno
    acceso: str                 # cómo se lee/escribe en el código generado: `s.v_x`, `_G.v_x`
    retain: bool = False
    constante: bool = False
    direccion: Direccion | None = None
    inicial_py: str = ""        # el valor inicial como código (entradas de una FUNCTION)
    linea: int = 0
    col: int = 0


@dataclass
class InfoPOU:
    clase: str                  # PROGRAM, FUNCTION, FUNCTION_BLOCK
    nombre: str
    py: str                     # nombre de la función generada
    nodo: A.POU
    vars: dict[str, Var] = field(default_factory=dict)
    interfaz: InterfazFB | None = None
    parametros: list[Var] = field(default_factory=list)   # VAR_INPUT de una FUNCTION, en orden
    tipo_ret: str | None = None
    llama: set[str] = field(default_factory=set)          # FUNCTION que llama (recursión)


@dataclass(frozen=True)
class Campo:
    """Un campo de la memoria de una instancia (PROGRAM, FB o globales), para el runtime."""

    attr: str                   # `v_x` o `d_ix0_0`
    inicial: object             # valor inicial (lista para un ARRAY; None para un FB)
    retain: bool = False
    fb: str | None = None       # clave del bloque si el campo es una instancia
