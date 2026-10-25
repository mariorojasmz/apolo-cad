"""Parser de ST, nivel de unidad: VAR_GLOBAL, PROGRAM, FUNCTION, FUNCTION_BLOCK y sus VAR.

Sentencias y expresiones: `parser_sent.py`. Corta en el primer error de sintaxis (no hay
recuperación: el error lleva línea, columna y qué se esperaba).
"""

from __future__ import annotations

from . import ast_st as A
from .lexer import tokenizar
from .parser_sent import ParserBase, describir

_BLOQUES = ("VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_GLOBAL")
_ELEMENTALES = ("BOOL", "INT", "DINT", "REAL", "TIME")
_FIN_POU = {"PROGRAM": "END_PROGRAM", "FUNCTION": "END_FUNCTION",
            "FUNCTION_BLOCK": "END_FUNCTION_BLOCK"}


class Parser(ParserBase):

    def unidad(self) -> A.Unidad:
        u = A.Unidad()
        while self.act.tipo != "FIN":
            tok = self.act
            if self.es("VAR_GLOBAL"):
                u.globales.append(self.bloque_var())
            elif self.es(*_FIN_POU):
                u.pous.append(self.pou())
            else:
                raise self.error(tok, "se esperaba PROGRAM, FUNCTION, FUNCTION_BLOCK o "
                                 f"VAR_GLOBAL y encontré {describir(tok)}")
        if not u.pous:
            raise self.error(self.act, "el programa está vacío: falta al menos un "
                             "PROGRAM … END_PROGRAM")
        return u

    def pou(self) -> A.POU:
        tok = self.avanzar()
        clase = tok.valor
        nombre = self.ident(f"el nombre del {clase}")
        tipo_ret = None
        if clase == "FUNCTION":
            self.espera(":", "y el tipo que devuelve la FUNCTION")
            tipo_ret = self.tipo()
            if not isinstance(tipo_ret, A.TipoRef) or tipo_ret.nombre not in _ELEMENTALES:
                raise self.error(self.t[self.i - 1], "una FUNCTION devuelve BOOL, INT, DINT, "
                                 "REAL o TIME")
        bloques = []
        while self.es(*_BLOQUES):
            bloques.append(self.bloque_var())
        cuerpo = self.sentencias(_FIN_POU[clase])
        self.avanzar()
        self.acepta(";")
        return A.POU(clase, nombre.valor, tipo_ret, bloques, cuerpo, tok.linea, tok.col)

    def bloque_var(self) -> A.BloqueVar:
        tok = self.avanzar()
        retain = constante = False
        while self.es("RETAIN", "CONSTANT"):
            if self.avanzar().valor == "RETAIN":
                retain = True
            else:
                constante = True
        decls = []
        while not self.es("END_VAR"):
            if self.act.tipo == "FIN":
                raise self.error(self.act, "falta «END_VAR» antes del final del programa")
            decls.append(self.decl())
        self.avanzar()
        self.acepta(";")
        return A.BloqueVar(tok.valor, retain, constante, decls, tok.linea, tok.col)

    def decl(self) -> A.Decl:
        primero = self.act
        nombres = []
        while True:
            t = self.ident("el nombre de una variable")
            nombres.append((t.valor, t.linea, t.col))
            if not self.acepta(","):
                break
        direccion = None
        if self.acepta("AT"):
            if self.act.tipo != "DIR":
                raise self.error(self.act, "después de AT va una dirección, p. ej. %IX0.0")
            d = self.avanzar()
            direccion = (d.valor, d.linea, d.col)
        self.espera(":", "y el tipo de la variable")
        tipo = self.tipo()
        inicial = None
        if self.acepta(":="):
            inicial = self._inicial_arreglo() if self.es("[") else self.expr()
        self.espera(";", "al final de la declaración")
        return A.Decl(nombres, tipo, inicial, direccion, primero.linea, primero.col)

    def tipo(self):
        tok = self.act
        if self.es(*_ELEMENTALES):
            self.avanzar()
            return A.TipoRef(tok.valor, tok.linea, tok.col)
        if self.acepta("ARRAY"):
            self.espera("[", "después de ARRAY")
            lo = self._entero_con_signo("el límite inferior del ARRAY")
            self.espera("..", "entre los límites del ARRAY")
            hi = self._entero_con_signo("el límite superior del ARRAY")
            if self.es(","):
                raise self.error(self.act, "los ARRAY de V8.3 tienen una sola dimensión")
            self.espera("]", "al cerrar los límites del ARRAY")
            self.espera("OF", "en el ARRAY")
            elem = self.tipo()
            if not isinstance(elem, A.TipoRef) or elem.nombre not in _ELEMENTALES:
                raise self.error(tok, "un ARRAY de V8.3 es de BOOL, INT, DINT, REAL o TIME")
            if hi < lo:
                raise self.error(tok, f"ARRAY[{lo}..{hi}]: el límite superior es menor que el "
                                 "inferior")
            if hi - lo >= 65536:
                raise self.error(tok, "un ARRAY de V8.3 tiene a lo sumo 65536 elementos")
            return A.TipoArreglo(lo, hi, elem, tok.linea, tok.col)
        if tok.tipo == "ID":
            self.avanzar()
            return A.TipoRef(tok.valor, tok.linea, tok.col)
        raise self.error(tok, f"se esperaba un tipo y encontré {describir(tok)}")

    def _entero_con_signo(self, que: str) -> int:
        signo = -1 if self.acepta("-") else 1
        if self.act.tipo != "ENTERO":
            raise self.error(self.act, f"{que} es un entero literal")
        return signo * self.avanzar().valor

    def _inicial_arreglo(self) -> A.InicialArreglo:
        tok = self.avanzar()
        elems = []
        while True:
            if self.act.tipo == "ENTERO" and self.sig().es("("):
                n = self.avanzar().valor
                self.avanzar()
                valor = self.expr()
                self.espera(")", "al cerrar la repetición")
                elems.append((n, valor))
            else:
                elems.append((1, self.expr()))
            if not self.acepta(","):
                break
        self.espera("]", "al cerrar los valores iniciales")
        return A.InicialArreglo(elems, tok.linea, tok.col)


def parsear(fuente: str) -> A.Unidad:
    """La unidad de la fuente, con sus comentarios en `Unidad.comentarios` (plan plc-en-el-lazo,
    D2: los tokens son los mismos que sin juntarlos). Lanza `ErrorSintaxis` en el primer error."""
    comentarios: list[A.Comentario] = []
    u = Parser(tokenizar(fuente, comentarios)).unidad()
    u.comentarios = comentarios
    return u
