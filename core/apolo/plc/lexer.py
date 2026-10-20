"""Lexer de ST (IEC 61131-3, 3.ª ed.): fuente → tokens con línea y columna.

ST no distingue mayúsculas: las palabras clave se normalizan a MAYÚSCULAS y los
identificadores guardan su escritura original (para los mensajes y la tabla de tags);
quien los compara usa `.lower()`. Un identificador con `__` se rechaza aquí (la norma
no lo permite y así nada del programa puede nombrar un atributo dunder de Python, D6).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction

from .errores import ErrorST, ErrorSintaxis

PALABRAS = frozenset("""
PROGRAM END_PROGRAM FUNCTION END_FUNCTION FUNCTION_BLOCK END_FUNCTION_BLOCK
VAR VAR_INPUT VAR_OUTPUT VAR_GLOBAL END_VAR RETAIN CONSTANT AT ARRAY OF
IF THEN ELSIF ELSE END_IF CASE END_CASE FOR TO BY DO END_FOR WHILE END_WHILE
REPEAT UNTIL END_REPEAT EXIT RETURN AND OR XOR NOT MOD TRUE FALSE
BOOL INT DINT REAL TIME
""".split())

#: Palabras de IEC 61131-3 que existen pero quedan fuera del subconjunto de V8.3 (D5).
FUERA_DEL_SUBCONJUNTO = frozenset("""
STRUCT END_STRUCT TYPE END_TYPE STRING WSTRING CHAR WCHAR POINTER REF_TO REF
VAR_IN_OUT VAR_EXTERNAL VAR_TEMP VAR_ACCESS VAR_CONFIG NON_RETAIN PERSISTENT
CONFIGURATION END_CONFIGURATION RESOURCE END_RESOURCE TASK WITH ON
SINT USINT UINT UDINT LINT ULINT LREAL BYTE WORD DWORD LWORD LTIME
DATE TIME_OF_DAY TOD DATE_AND_TIME DT CONTINUE JMP METHOD END_METHOD INTERFACE
END_INTERFACE PROPERTY END_PROPERTY EXTENDS IMPLEMENTS SUPER THIS NAMESPACE
INITIAL_STEP STEP END_STEP TRANSITION END_TRANSITION ACTION END_ACTION
""".split())

_OPERADORES = (":=", "=>", "<=", ">=", "<>", "**", "..", "+", "-", "*", "/", "(", ")",
               "[", "]", ",", ";", ":", ".", "=", "<", ">", "&")

_RE_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_RE_REAL = re.compile(r"\d[\d_]*\.\d[\d_]*(?:[eE][+-]?\d+)?|\d[\d_]*[eE][+-]?\d+", re.ASCII)
_RE_ENTERO = re.compile(r"(\d[\d_]*)(?:#([0-9A-Fa-f_]+))?", re.ASCII)
_RE_DIR = re.compile(r"%[A-Za-z]+\d+(?:\.\d+)?", re.ASCII)
_RE_TIEMPO = re.compile(r"(-)?((?:\d[\d_]*(?:\.\d+)?(?:ms|us|ns|d|h|m|s)_?)+)", re.IGNORECASE | re.ASCII)
_RE_TRAMO = re.compile(r"(\d[\d_]*(?:\.\d+)?)(ms|us|ns|d|h|m|s)", re.IGNORECASE | re.ASCII)
_MS_POR_UNIDAD = {"d": Fraction(86_400_000), "h": Fraction(3_600_000), "m": Fraction(60_000),
                  "s": Fraction(1000), "ms": Fraction(1), "us": Fraction(1, 1000),
                  "ns": Fraction(1, 1_000_000)}


@dataclass(frozen=True)
class Token:
    tipo: str        # ID, KW, ENTERO, REAL, TIEMPO, DIR, OP, FIN
    valor: object    # texto original, palabra en mayúsculas, número, ms o símbolo
    linea: int
    col: int

    def es(self, *valores: str) -> bool:
        return self.tipo in ("KW", "OP") and self.valor in valores


def _error(linea: int, col: int, mensaje: str) -> ErrorSintaxis:
    return ErrorSintaxis(ErrorST(linea, col, mensaje))


def _tiempo_ms(texto: str, linea: int, col: int) -> int:
    m = _RE_TIEMPO.fullmatch(texto)
    if not m:
        raise _error(linea, col, f"literal de tiempo inválido «T#{texto}»: escribe por ejemplo "
                     "T#1s500ms, T#2m30s o T#100ms")
    total = sum((Fraction(n.replace("_", "")) * _MS_POR_UNIDAD[u.lower()]
                 for n, u in _RE_TRAMO.findall(m.group(2))), Fraction(0))
    if total.denominator != 1:
        raise _error(linea, col, f"«T#{texto}» no es un número entero de milisegundos: el "
                     "PLC cuenta el tiempo en ms")
    valor = -int(total) if m.group(1) else int(total)
    if not -2**31 <= valor < 2**31:
        raise _error(linea, col, f"«T#{texto}» no cabe en un TIME (32 bits de ms, ±24 días)")
    return valor


def tokenizar(fuente: str) -> list[Token]:
    """Los tokens de la fuente, terminados en FIN. Corta en el primer error."""
    tokens: list[Token] = []
    i, linea, ini_linea, n = 0, 1, 0, len(fuente)
    while i < n:
        c = fuente[i]
        col = i - ini_linea + 1
        if c == "\n":
            linea, ini_linea, i = linea + 1, i + 1, i + 1
            continue
        if c in " \t\r\f":
            i += 1
            continue
        if fuente.startswith("(*", i) or fuente.startswith("/*", i):
            cierre = "*)" if c == "(" else "*/"
            fin = fuente.find(cierre, i + 2)
            if fin < 0:
                raise _error(linea, col, f"comentario sin cerrar: falta «{cierre}»")
            trozo = fuente[i:fin + 2]
            if trozo.count("\n"):
                linea += trozo.count("\n")
                ini_linea = i + trozo.rfind("\n") + 1
            i = fin + 2
            continue
        if fuente.startswith("//", i):
            fin = fuente.find("\n", i)
            i = n if fin < 0 else fin
            continue
        if c.isalpha() and not c.isascii():
            raise _error(linea, col, f"«{c}»: los identificadores de ST van sin tildes ni ñ "
                         "(sólo A–Z, 0–9 y _)")
        if c.isalpha() or c == "_":
            m = _RE_ID.match(fuente, i)
            texto = m.group(0)
            i = m.end()
            if i < n and fuente[i] == "#":
                if texto.upper() not in ("T", "TIME"):
                    raise _error(linea, col, f"el literal tipado «{texto}#…» queda fuera del "
                                 "subconjunto: escribe el número solo o usa una conversión")
                m2 = re.compile(r"-?[0-9A-Za-z_.]+").match(fuente, i + 1)
                cuerpo = m2.group(0) if m2 else ""
                tokens.append(Token("TIEMPO", _tiempo_ms(cuerpo, linea, col), linea, col))
                i = (m2.end() if m2 else i + 1)
                continue
            if "__" in texto:
                raise _error(linea, col, f"«{texto}»: un identificador no lleva dos guiones "
                             "bajos seguidos (IEC 61131-3)")
            arriba = texto.upper()
            if arriba in PALABRAS:
                tokens.append(Token("KW", arriba, linea, col))
            elif arriba in FUERA_DEL_SUBCONJUNTO:
                raise _error(linea, col, f"«{arriba}» queda fuera del subconjunto de ST de "
                             "V8.3 (BOOL, INT, DINT, REAL, TIME y ARRAY simple)")
            else:
                tokens.append(Token("ID", texto, linea, col))
            continue
        if c in "0123456789":
            m = _RE_REAL.match(fuente, i)
            if m:
                real = float(m.group(0).replace("_", ""))
                if not math.isfinite(real):
                    raise _error(linea, col, f"«{m.group(0)}» no cabe en un REAL")
                tokens.append(Token("REAL", real, linea, col))
                i = m.end()
                continue
            m = _RE_ENTERO.match(fuente, i)
            base, cifras = m.group(1).replace("_", ""), m.group(2)
            try:
                if cifras and base not in ("2", "8", "10", "16"):
                    raise ValueError
                valor = int(cifras.replace("_", ""), int(base)) if cifras else int(base)
            except ValueError:
                raise _error(linea, col, f"número inválido «{m.group(0)}»: las bases son "
                             "2#, 8# y 16#") from None
            tokens.append(Token("ENTERO", valor, linea, col))
            i = m.end()
            continue
        if c == "%":
            m = _RE_DIR.match(fuente, i)
            if not m:
                raise _error(linea, col, "dirección incompleta: escribe por ejemplo %IX0.0")
            tokens.append(Token("DIR", m.group(0).upper(), linea, col))
            i = m.end()
            continue
        if c in "'\"":
            raise _error(linea, col, "STRING queda fuera del subconjunto de ST de V8.3")
        for op in _OPERADORES:
            if fuente.startswith(op, i):
                tokens.append(Token("OP", op, linea, col))
                i += len(op)
                break
        else:
            raise _error(linea, col, f"carácter inesperado «{c}»")
    tokens.append(Token("FIN", None, linea, i - ini_linea + 1))
    return tokens
