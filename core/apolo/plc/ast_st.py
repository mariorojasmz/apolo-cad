"""Árbol sintáctico de ST: lo que el parser produce y el compilador recorre.

Cada nodo lleva `linea` y `col` de su primer token, para los errores (D3: línea y columna).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ── tipos escritos en la fuente ─────────────────────────────────────────────


@dataclass
class TipoRef:
    nombre: str                      # BOOL/INT/DINT/REAL/TIME o el nombre de un FB
    linea: int = 0
    col: int = 0


@dataclass
class TipoArreglo:
    lo: int
    hi: int
    elem: TipoRef
    linea: int = 0
    col: int = 0


# ── expresiones ──────────────────────────────────────────────────────────────


@dataclass
class Literal:
    valor: object
    tipo: str                        # BOOL, LIT_INT, REAL, TIME
    linea: int = 0
    col: int = 0


@dataclass
class Nombre:
    texto: str
    linea: int = 0
    col: int = 0


@dataclass
class DirExpr:
    texto: str                       # «%IX0.0»
    linea: int = 0
    col: int = 0


@dataclass
class Miembro:
    base: object
    campo: str
    linea: int = 0
    col: int = 0


@dataclass
class Indice:
    base: object
    indice: object
    linea: int = 0
    col: int = 0


@dataclass
class Binaria:
    op: str                          # + - * / MOD ** < > <= >= = <> AND XOR OR
    izq: object
    der: object
    linea: int = 0
    col: int = 0


@dataclass
class Unaria:
    op: str                          # - + NOT
    expr: object
    linea: int = 0
    col: int = 0


@dataclass
class Arg:
    nombre: str | None               # None = posicional
    valor: object | None             # `x := valor`
    destino: object | None = None    # `q => destino`
    linea: int = 0
    col: int = 0


@dataclass
class Llamada:
    nombre: str
    args: list[Arg]
    linea: int = 0
    col: int = 0


# ── sentencias ───────────────────────────────────────────────────────────────


@dataclass
class Asignacion:
    destino: object
    valor: object
    linea: int = 0
    col: int = 0


@dataclass
class LlamadaSent:
    llamada: Llamada
    linea: int = 0
    col: int = 0


@dataclass
class Si:
    ramas: list[tuple[object, list]]  # (condición, cuerpo); la primera es el IF
    sino: list | None
    linea: int = 0
    col: int = 0


@dataclass
class Etiqueta:
    lo: object
    hi: object | None                # `lo..hi`, o None si es un valor
    linea: int = 0
    col: int = 0


@dataclass
class Caso:
    selector: object
    ramas: list[tuple[list[Etiqueta], list]]
    sino: list | None
    linea: int = 0
    col: int = 0


@dataclass
class Para:
    var: Nombre
    desde: object
    hasta: object
    paso: object | None
    cuerpo: list
    linea: int = 0
    col: int = 0


@dataclass
class Mientras:
    cond: object
    cuerpo: list
    linea: int = 0
    col: int = 0


@dataclass
class Repetir:
    cuerpo: list
    cond: object
    linea: int = 0
    col: int = 0


@dataclass
class Salir:
    linea: int = 0
    col: int = 0


@dataclass
class Retornar:
    linea: int = 0
    col: int = 0


# ── declaraciones y unidades ─────────────────────────────────────────────────


@dataclass
class InicialArreglo:
    elementos: list[tuple[int, object]]   # (repeticiones, valor): `[3(0), 1]`
    linea: int = 0
    col: int = 0


@dataclass
class Decl:
    nombres: list[tuple[str, int, int]]   # (texto, línea, columna)
    tipo: TipoRef | TipoArreglo
    inicial: object | None = None
    direccion: tuple[str, int, int] | None = None
    linea: int = 0
    col: int = 0


@dataclass
class BloqueVar:
    clase: str                        # VAR, VAR_INPUT, VAR_OUTPUT, VAR_GLOBAL
    retain: bool
    constante: bool
    decls: list[Decl]
    linea: int = 0
    col: int = 0


@dataclass
class POU:
    clase: str                        # PROGRAM, FUNCTION, FUNCTION_BLOCK
    nombre: str
    tipo_ret: TipoRef | None
    bloques: list[BloqueVar]
    cuerpo: list
    linea: int = 0
    col: int = 0


@dataclass
class Comentario:
    """Un comentario de la fuente (plan plc-en-el-lazo, D2). No es parte del programa: el
    compilador no lo mira. `texto` es lo de adentro, sin los delimitadores ni el «\\r» final;
    `estilo` es el delimitador que lo abre: «(*», «/*» o «//». `linea_fin` es la línea del
    cierre (la misma en «//»). Los nodos sólo llevan su línea de inicio: quien imprime el
    programa intercala los comentarios por línea."""
    texto: str
    linea: int
    col: int
    linea_fin: int
    estilo: str


@dataclass
class Unidad:
    globales: list[BloqueVar] = field(default_factory=list)
    pous: list[POU] = field(default_factory=list)
    #: los comentarios de la fuente, en orden (D2); vacío si quien parsea no los juntó
    comentarios: list[Comentario] = field(default_factory=list)
