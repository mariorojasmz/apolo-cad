"""Compilación de expresiones y l-valores de ST a código Python, con chequeo de tipos.

Cada expresión da un `Val`: el código (siempre entre paréntesis si es compuesto, así la
precedencia de Python no importa), su tipo, si hace aritmética entera (entonces se envuelve
al ancho del destino al guardarse, como el desborde de un PLC) y su valor si es constante.
Un error se anota y devuelve tipo ERROR, que es compatible con todo para no encadenar avisos.
"""

from __future__ import annotations

import re

from . import ast_st as A
from .errores import ErrorST, sugerir
from .tipos import (BOOL, CONVERSIONES, DINT, ENTEROS, ERROR, FB_ESTANDAR, FUNCIONES_ESTANDAR,
                    INT, LIT_INT, NUMERICOS, RANGO, REAL, TIME, Arreglo, InterfazFB, asignable,
                    comun, nombre, pista_conversion, pista_mezcla)

_RE_CONV = re.compile(r"^(BOOL|INT|DINT|REAL|TIME)_TO_(BOOL|INT|DINT|REAL|TIME)$", re.IGNORECASE)
_CMP = ("<", ">", "<=", ">=")
_RE_SIMPLE = re.compile(r"^[A-Za-z_][\w.]*$|^-?\d+$", re.ASCII)


def _simple(code: str) -> bool:
    """Una variable o un entero literal: se puede repetir en el código sin costo ni efectos."""
    return bool(_RE_SIMPLE.match(code))


def _divisor_positivo(a, b) -> bool:
    """`a / k` o `a MOD k` con k entero positivo constante y `a` simple: va en línea, sin
    llamar a `_div`/`_mod` (truncar hacia cero = el signo del dividendo, como la norma)."""
    return isinstance(b.const, int) and not isinstance(b.const, bool) and b.const > 0 \
        and _simple(a.code)


class Val:
    __slots__ = ("code", "tipo", "arit", "const")

    def __init__(self, code: str, tipo, arit: bool = False, const=None):
        self.code, self.tipo, self.arit, self.const = code, tipo, arit, const


def envolver(code: str, tipo) -> str:
    """El código que lleva un entero al ancho de `tipo` (desborde con vuelta, como un PLC)."""
    if tipo == INT:
        return f"((({code} + 32768) & 65535) - 32768)"
    return f"((({code} + 2147483648) & 4294967295) - 2147483648)"


def texto(n) -> str:
    """El l-valor como lo escribió la persona, para los mensajes."""
    if isinstance(n, A.Nombre):
        return n.texto
    if isinstance(n, A.DirExpr):
        return n.texto
    if isinstance(n, A.Miembro):
        return f"{texto(n.base)}.{n.campo}"
    if isinstance(n, A.Indice):
        return f"{texto(n.base)}[…]"
    return "…"


class Expresiones:
    """Mixin del compilador de una POU: necesita `self.u` (la unidad), `self.pou` y
    `self.para_activos`."""

    # ── utilidades ───────────────────────────────────────────────────────
    def err(self, nodo, mensaje: str) -> Val:
        self.u.errores.append(ErrorST(nodo.linea, nodo.col, mensaje))
        return Val("0", ERROR)

    def buscar(self, nombre_: str):
        k = nombre_.lower()
        return self.pou.vars.get(k) or self.u.globales.get(k)

    def visibles(self) -> list[str]:
        return ([v.nombre for v in self.pou.vars.values()]
                + [v.nombre for v in self.u.globales.values()])

    def coaccionar(self, v: Val, destino, nodo, que: str) -> str:
        if ERROR in (v.tipo, destino):
            return v.code
        if not asignable(destino, v.tipo):
            self.err(nodo, f"{que} es {nombre(destino)} y le das {nombre(v.tipo)}."
                     + pista_conversion(destino, v.tipo))
            return v.code
        if v.tipo == LIT_INT and v.const is not None and destino in RANGO:
            lo, hi = RANGO[destino]
            if not lo <= v.const <= hi:
                extra = " Declárala DINT." if destino == INT else ""
                self.err(nodo, f"{v.const} no cabe en {destino} ({lo} … {hi}).{extra}")
        if destino == REAL and v.tipo != REAL:
            return repr(float(v.const)) if v.const is not None else f"({v.code} + 0.0)"
        if v.arit and destino in (INT, DINT, TIME):
            return envolver(v.code, destino)
        return v.code

    def condicion(self, e, que: str) -> str:
        v = self.expr(e)
        if v.tipo not in (BOOL, ERROR):
            self.err(e, f"{que} es BOOL y aquí hay {nombre(v.tipo)}: compara, p. ej. «x > 0»")
        return v.code

    # ── expresiones ──────────────────────────────────────────────────────
    def expr(self, e) -> Val:
        return getattr(self, "_e_" + type(e).__name__)(e)

    def _e_Literal(self, e: A.Literal) -> Val:
        if e.tipo == BOOL:
            return Val("True" if e.valor else "False", BOOL, const=e.valor)
        return Val(repr(e.valor), e.tipo, const=e.valor)

    def _desconocido(self, e: A.Nombre) -> Val:
        k = e.texto.lower()
        if (k in self.u.pous or k in FB_ESTANDAR or e.texto.upper() in FUNCIONES_ESTANDAR
                or _RE_CONV.match(e.texto)):
            return self.err(e, f"«{e.texto}» no es una variable sino una función o un bloque")
        return self.err(e, f"no existe la variable «{e.texto}»."
                        + sugerir(e.texto, self.visibles()))

    def _e_Nombre(self, e: A.Nombre) -> Val:
        v = self.buscar(e.texto)
        if v is None:
            return self._desconocido(e)
        if isinstance(v.tipo, InterfazFB):
            salida = next(iter(v.tipo.salidas.values()), ("Q",))[0]
            return self.err(e, f"«{v.nombre}» es un bloque {v.tipo.nombre}: lee una salida, "
                            f"p. ej. «{v.nombre}.{salida}»")
        if isinstance(v.tipo, Arreglo):
            return self.err(e, f"«{v.nombre}» es un ARRAY: lee un elemento, p. ej. "
                            f"«{v.nombre}[{v.tipo.lo}]»")
        return Val(v.acceso, v.tipo)

    def _e_DirExpr(self, e: A.DirExpr) -> Val:
        d = self.u.usar_direccion(e.texto, e, escritura=False)
        if d is None:
            return Val("0", ERROR)
        return Val(f"_G.{d.ident}", d.tipo)

    def _instancia(self, base):
        if not isinstance(base, A.Nombre):
            self.err(base, "sólo las instancias de bloque tienen «.entrada» o «.salida»")
            return None
        v = self.buscar(base.texto)
        if v is None:
            self._desconocido(base)
            return None
        if not isinstance(v.tipo, InterfazFB):
            self.err(base, f"«{v.nombre}» es {nombre(v.tipo)}: sólo las instancias de bloque "
                     "tienen «.entrada» o «.salida»")
            return None
        return v

    def _miembro(self, e: A.Miembro, escritura: bool):
        v = self._instancia(e.base)
        if v is None:
            return None
        fb, k = v.tipo, e.campo.lower()
        if k in fb.salidas:
            if escritura:
                self.err(e, f"«{fb.salidas[k][0]}» es una salida de {fb.nombre}: la escribe el "
                         "bloque")
                return None
            return f"{v.acceso}.v_{k}", fb.salidas[k][1]
        if k in fb.entradas:
            return f"{v.acceso}.v_{k}", fb.entradas[k][1]
        miembros = [o for o, _ in (*fb.entradas.values(), *fb.salidas.values())]
        self.err(e, f"{fb.nombre} no tiene «{e.campo}» ({fb.miembros()})."
                 + sugerir(e.campo, miembros))
        return None

    def _e_Miembro(self, e: A.Miembro) -> Val:
        r = self._miembro(e, escritura=False)
        return Val(*r) if r else Val("0", ERROR)

    def _indice(self, e: A.Indice):
        if not isinstance(e.base, A.Nombre):
            self.err(e, "sólo un ARRAY lleva índice")
            return None
        v = self.buscar(e.base.texto)
        if v is None:
            self._desconocido(e.base)
            return None
        if not isinstance(v.tipo, Arreglo):
            self.err(e, f"«{v.nombre}» es {nombre(v.tipo)}: sólo un ARRAY lleva índice")
            return None
        arr, i = v.tipo, self.expr(e.indice)
        if i.tipo not in (*ENTEROS, ERROR):
            self.err(e.indice, f"el índice de «{v.nombre}» es entero y aquí hay {nombre(i.tipo)}")
            return None
        if i.const is not None:
            if not arr.lo <= i.const <= arr.hi:
                self.err(e.indice, f"el índice {i.const} está fuera de «{v.nombre}» "
                         f"({arr.lo} … {arr.hi})")
                return None
            return v, f"{v.acceso}[{i.const - arr.lo}]", arr.elem
        ix = f"_ix({i.code}, {arr.lo}, {arr.hi})"
        if _simple(i.code):       # en línea: el camino feliz no llama a nada
            dentro = i.code if arr.lo == 0 else f"({i.code} - {arr.lo})"
            ix = f"{dentro} if {arr.lo} <= {i.code} <= {arr.hi} else {ix}"
        return v, f"{v.acceso}[{ix}]", arr.elem

    def _e_Indice(self, e: A.Indice) -> Val:
        r = self._indice(e)
        return Val(r[1], r[2]) if r else Val("0", ERROR)

    def _e_Unaria(self, e: A.Unaria) -> Val:
        v = self.expr(e.expr)
        if e.op == "NOT":
            if v.tipo not in (BOOL, ERROR):
                return self.err(e, f"NOT niega un BOOL y aquí hay {nombre(v.tipo)}")
            return Val(f"(not {v.code})", BOOL)
        if v.tipo not in (*NUMERICOS, TIME, ERROR):
            return self.err(e, f"«{e.op}» va delante de un número y aquí hay {nombre(v.tipo)}")
        if e.op == "+":
            return v
        return Val(f"(-{v.code})", v.tipo, arit=v.tipo != REAL)

    def _e_Binaria(self, e: A.Binaria) -> Val:
        a, b, op = self.expr(e.izq), self.expr(e.der), e.op
        if ERROR in (a.tipo, b.tipo):
            return Val("0", ERROR)
        mezcla = f"{nombre(a.tipo)} y {nombre(b.tipo)}"
        if op in ("AND", "OR", "XOR"):
            if a.tipo != BOOL or b.tipo != BOOL:
                return self.err(e, f"{op} une dos BOOL y aquí hay {mezcla}")
            py = {"AND": "and", "OR": "or", "XOR": "!="}[op]
            return Val(f"({a.code} {py} {b.code})", BOOL)
        t = comun(a.tipo, b.tipo)
        if op in ("=", "<>", *_CMP):
            if t is None:
                return self.err(e, f"no se comparan {mezcla}." + pista_mezcla(a.tipo, b.tipo))
            if t == BOOL and op in _CMP:
                return self.err(e, "un BOOL sólo se compara con «=» o «<>»")
            py = {"=": "==", "<>": "!="}.get(op, op)
            return Val(f"({a.code} {py} {b.code})", BOOL)
        if TIME in (a.tipo, b.tipo):
            return self._con_tiempo(e, a, b, mezcla)
        if t is None or t not in NUMERICOS:
            return self.err(e, f"«{op}» opera números y aquí hay {mezcla}."
                            + pista_mezcla(a.tipo, b.tipo))
        if op in ("+", "-", "*"):
            return Val(f"({a.code} {op} {b.code})", t, arit=t != REAL)
        if op == "/":
            if t == REAL:
                if b.const not in (None, 0, 0.0):
                    return Val(f"({a.code} / {b.code})", REAL)
                return Val(f"_rdiv({a.code}, {b.code})", REAL)
            if _divisor_positivo(a, b):
                return Val(f"(({a.code} // {b.code}) if {a.code} >= 0 else "
                           f"-((-{a.code}) // {b.code}))", t, arit=True)
            return Val(f"_div({a.code}, {b.code})", t, arit=True)
        if op == "MOD":
            if t == REAL:
                return self.err(e, "MOD opera enteros (INT o DINT)")
            if _divisor_positivo(a, b):
                return Val(f"(({a.code} % {b.code}) if {a.code} >= 0 else "
                           f"-((-{a.code}) % {b.code}))", t)
            return Val(f"_mod({a.code}, {b.code})", t)
        return Val(f"_expt({a.code}, {b.code})", REAL)      # **

    def _con_tiempo(self, e, a: Val, b: Val, mezcla: str) -> Val:
        op = e.op
        if op in ("+", "-"):
            if a.tipo != TIME or b.tipo != TIME:
                return self.err(e, f"a un TIME se le suma o resta otro TIME (p. ej. T#1s) y "
                                f"aquí hay {mezcla}")
            return Val(f"({a.code} {op} {b.code})", TIME, arit=True)
        if op in ("*", "/"):
            tiempo, k = (a, b) if a.tipo == TIME else (b, a)
            if op == "/" and tiempo is b:
                return self.err(e, "un número no se divide por un TIME")
            if k.tipo in ENTEROS:
                if op == "*":
                    return Val(f"({a.code} * {b.code})", TIME, arit=True)
                return Val(f"_div({a.code}, {b.code})", TIME, arit=True)
            if k.tipo == REAL and op == "*":
                return Val(f"_tmul({tiempo.code}, {k.code})", TIME)
        return self.err(e, f"«{op}» no opera {mezcla}: un TIME se suma con TIME y se "
                        "multiplica o divide por un entero")

    # ── llamadas a funciones ─────────────────────────────────────────────
    def _e_Llamada(self, e: A.Llamada) -> Val:
        k, arriba = e.nombre.lower(), e.nombre.upper()
        v = self.buscar(e.nombre)
        if v is not None:
            if isinstance(v.tipo, InterfazFB):
                return self.err(e, f"un bloque se llama como sentencia: «{v.nombre}(…);» y "
                                f"después se lee su salida, p. ej. «{v.nombre}."
                                f"{next(iter(v.tipo.salidas.values()), ('Q',))[0]}»")
            return self.err(e, f"«{v.nombre}» es una variable, no una función")
        info = self.u.pous.get(k)
        if info is not None and info.clase == "FUNCTION":
            return self._llamar_funcion(info, e)
        if info is not None or k in FB_ESTANDAR:
            if info is not None and info.clase == "PROGRAM":
                return self.err(e, f"«{e.nombre}» es un PROGRAM: los programas no se llaman")
            return self.err(e, f"«{e.nombre}» es un bloque: declara una instancia (p. ej. "
                            f"«mi_{k} : {e.nombre};») y llámala «mi_{k}(…);»")
        if any(a.nombre is not None or a.destino is not None for a in e.args):
            return self.err(e, f"llama a {arriba} con argumentos posicionales: {arriba}(a, b)")
        args = [self.expr(a.valor) for a in e.args]
        if ERROR in (a.tipo for a in args):
            return Val("0", ERROR)
        m = _RE_CONV.match(e.nombre)
        if m:
            return self._conversion(e, m.group(1).upper(), m.group(2).upper(), args)
        if arriba in FUNCIONES_ESTANDAR:
            return self._estandar(e, arriba, args)
        candidatos = ([i.nombre for i in self.u.pous.values() if i.clase == "FUNCTION"]
                      + list(FUNCIONES_ESTANDAR) + [f"{x}_TO_{y}" for x, y in CONVERSIONES])
        return self.err(e, f"no existe la función «{e.nombre}»." + sugerir(e.nombre, candidatos))

    def _aridad(self, e, n: int, args: list, minimo: int | None = None) -> bool:
        if (minimo is None and len(args) != n) or (minimo is not None and len(args) < minimo):
            cuantos = f"al menos {minimo}" if minimo is not None else str(n)
            self.err(e, f"{e.nombre.upper()} recibe {cuantos} argumento(s) y le das {len(args)}")
            return False
        return True

    def _conversion(self, e, de: str, a: str, args: list[Val]) -> Val:
        plantilla = CONVERSIONES.get((de, a))
        if plantilla is None:
            return self.err(e, f"{de}_TO_{a} no existe en el subconjunto de V8.3")
        if not self._aridad(e, 1, args):
            return Val("0", ERROR)
        code = self.coaccionar(args[0], de, e, f"el argumento de {de}_TO_{a}")
        if plantilla == "W16":
            return Val(envolver(code, INT), a)
        return Val(plantilla.format(code), a)

    def _estandar(self, e, f: str, args: list[Val]) -> Val:
        if f in ("ABS", "SQRT", "TRUNC"):
            if not self._aridad(e, 1, args):
                return Val("0", ERROR)
            x = args[0]
            if f == "ABS":
                if x.tipo not in NUMERICOS:
                    return self.err(e, f"ABS recibe un número y aquí hay {nombre(x.tipo)}")
                return Val(f"_abs({x.code})", x.tipo, arit=x.tipo != REAL)
            code = self.coaccionar(x, REAL, e, f"el argumento de {f}")
            return Val(f"_sqrt({code})", REAL) if f == "SQRT" else Val(f"_trunc({code})", DINT)
        if f == "EXPT":
            if not self._aridad(e, 2, args):
                return Val("0", ERROR)
            if any(x.tipo not in NUMERICOS for x in args):
                return self.err(e, "EXPT recibe dos números")
            return Val(f"_expt({args[0].code}, {args[1].code})", REAL)
        if f == "SEL":
            if not self._aridad(e, 3, args):
                return Val("0", ERROR)
            g, x0, x1 = args
            if g.tipo != BOOL:
                return self.err(e, "el primer argumento de SEL es el BOOL que elige")
            t = comun(x0.tipo, x1.tipo)
            if t is None:
                return self.err(e, f"SEL elige entre dos valores del mismo tipo y aquí hay "
                                f"{nombre(x0.tipo)} y {nombre(x1.tipo)}")
            return Val(f"({x1.code} if {g.code} else {x0.code})", t, arit=x0.arit or x1.arit)
        if not self._aridad(e, 3, args, None if f == "LIMIT" else 2):
            return Val("0", ERROR)
        t = args[0].tipo
        for x in args[1:]:
            t = comun(t, x.tipo) if t is not None else None
        if t is None or t not in (*NUMERICOS, TIME):
            return self.err(e, f"{f} recibe números (o TIME) del mismo tipo")
        codes = [self.coaccionar(x, t, e, f"el argumento de {f}") if t != LIT_INT else x.code
                 for x in args]
        py = {"MIN": "_min", "MAX": "_max", "LIMIT": "_limit"}[f]
        return Val(f"{py}({', '.join(codes)})", t)

    def _llamar_funcion(self, info, e: A.Llamada) -> Val:
        self.pou.llama.add(info.nodo.nombre.lower())
        params = info.parametros
        firma = f"{info.nombre}({', '.join(p.nombre + ' := …' for p in params)})"
        if any(a.destino is not None for a in e.args):
            return self.err(e, f"una FUNCTION no tiene salidas «=>»: devuelve su valor ({firma})")
        nombrados = [a.nombre is not None for a in e.args]
        if any(nombrados) and not all(nombrados):
            return self.err(e, f"no mezcles argumentos con nombre y posicionales: {firma}")
        por_param: dict[str, A.Arg] = {}
        if e.args and all(nombrados):
            claves = {p.nombre.lower(): p for p in params}
            for a in e.args:
                k = a.nombre.lower()
                if k not in claves:
                    self.err(a, f"{info.nombre} no tiene la entrada «{a.nombre}» ({firma})."
                             + sugerir(a.nombre, [p.nombre for p in params]))
                elif k in por_param:
                    self.err(a, f"la entrada «{a.nombre}» va dos veces")
                por_param[k] = a
        elif e.args:
            if len(e.args) != len(params):
                return self.err(e, f"{info.nombre} recibe {len(params)} argumento(s) y le das "
                                f"{len(e.args)}: {firma}")
            por_param = {p.nombre.lower(): a for p, a in zip(params, e.args)}
        codes = []
        for p in params:
            a = por_param.get(p.nombre.lower())
            if a is None:
                codes.append(p.inicial_py)
            else:
                codes.append(self.coaccionar(self.expr(a.valor), p.tipo, a,
                                             f"la entrada «{p.nombre}» de {info.nombre}"))
        return Val(f"{info.py}({', '.join(codes)})", info.tipo_ret)

    # ── l-valores ────────────────────────────────────────────────────────
    def lvalor(self, n):
        """(código, tipo) del destino de una asignación, o None si no se puede escribir."""
        en_funcion = self.pou.clase == "FUNCTION"
        if isinstance(n, A.DirExpr):
            d = self.u.usar_direccion(n.texto, n, escritura=True)
            if d is None:
                return None
            if en_funcion:
                self.err(n, "una FUNCTION no escribe salidas: devuelve el valor y asígnalo en "
                         "el PROGRAM o el FUNCTION_BLOCK")
                return None
            return f"_G.{d.ident}", d.tipo
        if isinstance(n, A.Miembro):
            return self._miembro(n, escritura=True)
        base = n.base if isinstance(n, A.Indice) else n
        if not isinstance(base, A.Nombre):
            self.err(n, "no se puede asignar a esto")
            return None
        v = self.buscar(base.texto)
        if v is None:
            self._desconocido(base)
            return None
        problema = None
        if v.constante:
            problema = f"«{v.nombre}» es CONSTANT: no se escribe"
        elif v.direccion is not None and v.direccion.es_entrada:
            problema = (f"«{v.nombre}» está en la entrada {v.direccion.texto}: el programa la "
                        "lee, no la escribe")
        elif en_funcion and v.clase == "global":
            problema = ("una FUNCTION no escribe variables globales: devuelve el valor o usa "
                        "un FUNCTION_BLOCK")
        elif v.acceso in self.para_activos:
            problema = f"«{v.nombre}» es la variable de control del FOR: no se escribe en el bucle"
        if problema:
            self.err(n, problema)
            return None
        if isinstance(n, A.Indice):
            r = self._indice(n)
            return (r[1], r[2]) if r else None
        if isinstance(v.tipo, (Arreglo, InterfazFB)):
            self.err(n, f"«{v.nombre}» es {nombre(v.tipo)}: se asigna elemento por elemento")
            return None
        return v.acceso, v.tipo
