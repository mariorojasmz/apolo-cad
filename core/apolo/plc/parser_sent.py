"""Parser de descenso recursivo de ST: cursor, sentencias y expresiones.

Precedencia de IEC 61131-3 3.ª ed. (tabla 71), de mayor a menor: paréntesis y llamada,
unarios (`-`, `+`, `NOT`), `**`, `* / MOD`, `+ -`, `< > <= >=`, `= <>`, `AND &`, `XOR`, `OR`.
Todas asocian a la izquierda (también `**`, como dice la norma). Las declaraciones y las
POU están en `parser.py`.
"""

from __future__ import annotations

from . import ast_st as A
from .errores import ErrorST, ErrorSintaxis
from .lexer import Token

_CMP = ("<", ">", "<=", ">=")


def describir(tok: Token) -> str:
    if tok.tipo == "FIN":
        return "el final del programa"
    if tok.tipo == "TIEMPO":
        return "un literal de tiempo"
    return f"«{tok.valor}»"


class ParserBase:
    """Cursor sobre los tokens y las sentencias y expresiones de ST."""

    def __init__(self, tokens: list[Token]):
        self.t = tokens
        self.i = 0

    # ── cursor ───────────────────────────────────────────────────────────
    @property
    def act(self) -> Token:
        return self.t[self.i]

    def sig(self, k: int = 1) -> Token:
        return self.t[min(self.i + k, len(self.t) - 1)]

    def avanzar(self) -> Token:
        tok = self.t[self.i]
        if tok.tipo != "FIN":
            self.i += 1
        return tok

    def es(self, *valores: str) -> bool:
        return self.act.es(*valores)

    def acepta(self, *valores: str) -> Token | None:
        return self.avanzar() if self.es(*valores) else None

    def error(self, tok: Token, mensaje: str) -> ErrorSintaxis:
        return ErrorSintaxis(ErrorST(tok.linea, tok.col, mensaje))

    def espera(self, valor: str, contexto: str = "") -> Token:
        if self.es(valor):
            return self.avanzar()
        extra = f" {contexto}" if contexto else ""
        raise self.error(self.act, f"se esperaba «{valor}»{extra} y encontré "
                         f"{describir(self.act)}")

    def ident(self, que: str) -> Token:
        if self.act.tipo == "ID":
            return self.avanzar()
        raise self.error(self.act, f"se esperaba {que} y encontré {describir(self.act)}")

    # ── sentencias ───────────────────────────────────────────────────────
    def sentencias(self, *fin: str) -> list:
        """Sentencias hasta una de las palabras `fin` (que no se consume)."""
        out = []
        while not self.es(*fin):
            if self.act.tipo == "FIN":
                raise self.error(self.act, f"falta «{fin[-1]}» antes del final del programa")
            if self.act.tipo == "KW" and (self.act.valor.startswith("END_")
                                          or self.act.valor in ("ELSE", "ELSIF", "UNTIL")):
                raise self.error(self.act, f"falta «{fin[-1]}» antes de «{self.act.valor}»")
            s = self.sentencia()
            if s is not None:
                out.append(s)
        return out

    def sentencia(self):
        tok = self.act
        try:
            return self._sentencia()
        except RecursionError:
            raise self.error(tok, "la sentencia está demasiado anidada: pártela en varias "
                             "asignaciones") from None

    def _sentencia(self):
        tok = self.act
        if self.acepta(";"):
            return None
        if tok.tipo == "KW":
            metodo = {"IF": self._si, "CASE": self._caso, "FOR": self._para,
                      "WHILE": self._mientras, "REPEAT": self._repetir}.get(tok.valor)
            if metodo:
                self.avanzar()
                return metodo(tok)
            if tok.valor in ("EXIT", "RETURN"):
                self.avanzar()
                self.espera(";", f"después de {tok.valor}")
                cls = A.Salir if tok.valor == "EXIT" else A.Retornar
                return cls(tok.linea, tok.col)
        if tok.tipo == "ID" and self.sig().es("("):
            llamada = self._llamada()
            self.espera(";", "al final de la llamada")
            return A.LlamadaSent(llamada, tok.linea, tok.col)
        if tok.tipo in ("ID", "DIR"):
            destino = self.lvalor()
            if self.es("="):
                raise self.error(self.act, "para asignar se usa «:=», no «=»")
            self.espera(":=", "para asignar")
            valor = self.expr()
            self.espera(";", "al final de la asignación")
            return A.Asignacion(destino, valor, tok.linea, tok.col)
        raise self.error(tok, f"se esperaba una sentencia y encontré {describir(tok)}")

    def _fin_bloque(self, palabra: str) -> None:
        self.espera(palabra)
        self.acepta(";")

    def _si(self, tok: Token):
        ramas = []
        cond = self.expr()
        self.espera("THEN", "después de la condición del IF")
        ramas.append((cond, self.sentencias("ELSIF", "ELSE", "END_IF")))
        while self.acepta("ELSIF"):
            cond = self.expr()
            self.espera("THEN", "después de la condición del ELSIF")
            ramas.append((cond, self.sentencias("ELSIF", "ELSE", "END_IF")))
        sino = self.sentencias("END_IF") if self.acepta("ELSE") else None
        self._fin_bloque("END_IF")
        return A.Si(ramas, sino, tok.linea, tok.col)

    def _etiqueta_entera(self) -> A.Literal:
        tok = self.act
        signo = -1 if self.acepta("-") else 1
        if self.act.tipo != "ENTERO":
            raise self.error(self.act, "una etiqueta de CASE es un entero (o un rango a..b)")
        return A.Literal(signo * self.avanzar().valor, "LIT_INT", tok.linea, tok.col)

    def _empieza_etiqueta(self) -> bool:
        return self.act.tipo == "ENTERO" or (self.es("-") and self.sig().tipo == "ENTERO")

    def _caso(self, tok: Token):
        selector = self.expr()
        self.espera("OF", "después del selector del CASE")
        ramas = []
        while self._empieza_etiqueta():
            etiquetas = []
            while True:
                t0 = self.act
                lo = self._etiqueta_entera()
                hi = self._etiqueta_entera() if self.acepta("..") else None
                etiquetas.append(A.Etiqueta(lo, hi, t0.linea, t0.col))
                if not self.acepta(","):
                    break
            self.espera(":", "después de las etiquetas del CASE")
            cuerpo = []
            while not (self._empieza_etiqueta() or self.es("ELSE", "END_CASE")):
                if self.act.tipo == "FIN":
                    raise self.error(self.act, "falta «END_CASE» antes del final del programa")
                s = self.sentencia()
                if s is not None:
                    cuerpo.append(s)
            ramas.append((etiquetas, cuerpo))
        if not ramas and not self.es("ELSE"):
            raise self.error(self.act, "un CASE necesita al menos una rama `valor: …;`")
        sino = self.sentencias("END_CASE") if self.acepta("ELSE") else None
        self._fin_bloque("END_CASE")
        return A.Caso(selector, ramas, sino, tok.linea, tok.col)

    def _para(self, tok: Token):
        v = self.ident("la variable de control del FOR")
        self.espera(":=", "en el FOR")
        desde = self.expr()
        self.espera("TO", "en el FOR")
        hasta = self.expr()
        paso = self.expr() if self.acepta("BY") else None
        self.espera("DO", "en el FOR")
        cuerpo = self.sentencias("END_FOR")
        self._fin_bloque("END_FOR")
        return A.Para(A.Nombre(v.valor, v.linea, v.col), desde, hasta, paso, cuerpo,
                      tok.linea, tok.col)

    def _mientras(self, tok: Token):
        cond = self.expr()
        self.espera("DO", "después de la condición del WHILE")
        cuerpo = self.sentencias("END_WHILE")
        self._fin_bloque("END_WHILE")
        return A.Mientras(cond, cuerpo, tok.linea, tok.col)

    def _repetir(self, tok: Token):
        cuerpo = self.sentencias("UNTIL")
        self.espera("UNTIL")
        cond = self.expr()
        self._fin_bloque("END_REPEAT")
        return A.Repetir(cuerpo, cond, tok.linea, tok.col)

    # ── l-valores y llamadas ─────────────────────────────────────────────
    def lvalor(self):
        tok = self.act
        if tok.tipo == "DIR":
            self.avanzar()
            return A.DirExpr(tok.valor, tok.linea, tok.col)
        base = A.Nombre(self.ident("una variable").valor, tok.linea, tok.col)
        return self._sufijos(base)

    def _sufijos(self, base):
        while True:
            tok = self.act
            if self.acepta("."):
                campo = self.ident("el nombre de una entrada o salida del bloque")
                base = A.Miembro(base, campo.valor, tok.linea, tok.col)
            elif self.acepta("["):
                indice = self.expr()
                if self.es(","):
                    raise self.error(self.act, "los ARRAY de V8.3 tienen una sola dimensión")
                self.espera("]", "al cerrar el índice")
                base = A.Indice(base, indice, tok.linea, tok.col)
            else:
                return base

    def _llamada(self) -> A.Llamada:
        nombre = self.ident("el nombre de una función o de un bloque")
        self.espera("(")
        args: list[A.Arg] = []
        if not self.es(")"):
            while True:
                t0 = self.act
                if t0.tipo == "ID" and self.sig().es(":=", "=>"):
                    self.avanzar()
                    if self.avanzar().valor == ":=":
                        args.append(A.Arg(t0.valor, self.expr(), None, t0.linea, t0.col))
                    else:
                        args.append(A.Arg(t0.valor, None, self.lvalor(), t0.linea, t0.col))
                else:
                    args.append(A.Arg(None, self.expr(), None, t0.linea, t0.col))
                if not self.acepta(","):
                    break
        self.espera(")", "al cerrar la llamada")
        return A.Llamada(nombre.valor, args, nombre.linea, nombre.col)

    # ── expresiones ──────────────────────────────────────────────────────
    def expr(self):
        return self._binaria(0)

    _NIVELES = (("OR",), ("XOR",), ("AND", "&"), ("=", "<>"), _CMP, ("+", "-"),
                ("*", "/", "MOD"), ("**",))

    def _binaria(self, nivel: int):
        if nivel == len(self._NIVELES):
            return self._unaria()
        izq = self._binaria(nivel + 1)
        while self.es(*self._NIVELES[nivel]):
            tok = self.avanzar()
            op = "AND" if tok.valor == "&" else tok.valor
            der = self._binaria(nivel + 1)
            izq = A.Binaria(op, izq, der, tok.linea, tok.col)
        return izq

    def _unaria(self):
        tok = self.act
        if self.es("-", "+", "NOT"):
            self.avanzar()
            e = self._unaria()
            if tok.valor == "-" and isinstance(e, A.Literal) and e.tipo in ("LIT_INT", "REAL",
                                                                              "TIME"):
                return A.Literal(-e.valor, e.tipo, tok.linea, tok.col)
            if tok.valor == "+" and isinstance(e, A.Literal):
                return e
            return A.Unaria(tok.valor, e, tok.linea, tok.col)
        return self._primaria()

    def _primaria(self):
        tok = self.act
        if tok.tipo == "ENTERO":
            self.avanzar()
            return A.Literal(tok.valor, "LIT_INT", tok.linea, tok.col)
        if tok.tipo == "REAL":
            self.avanzar()
            return A.Literal(tok.valor, "REAL", tok.linea, tok.col)
        if tok.tipo == "TIEMPO":
            self.avanzar()
            return A.Literal(tok.valor, "TIME", tok.linea, tok.col)
        if self.es("TRUE", "FALSE"):
            self.avanzar()
            return A.Literal(tok.valor == "TRUE", "BOOL", tok.linea, tok.col)
        if self.acepta("("):
            e = self.expr()
            self.espera(")", "al cerrar el paréntesis")
            return e
        if tok.tipo == "DIR":
            self.avanzar()
            return A.DirExpr(tok.valor, tok.linea, tok.col)
        if tok.tipo == "ID":
            if self.sig().es("("):
                return self._llamada()
            self.avanzar()
            return self._sufijos(A.Nombre(tok.valor, tok.linea, tok.col))
        raise self.error(tok, f"se esperaba un valor o una variable y encontré {describir(tok)}")
