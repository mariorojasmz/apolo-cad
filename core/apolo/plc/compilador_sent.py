"""Compilación de sentencias de ST a Python estructurado (D6).

Sólo se emite: asignación, `if/elif/else`, `while` con contador, `break`, `return` y llamadas
a funciones del runtime o generadas. Cada bucle lleva su contador local contra el
presupuesto del watchdog (`_wd.resto`) y lo descuenta al salir: el scan entero no puede dar
más vueltas que las que equivalen a su tiempo de vigilancia.
"""

from __future__ import annotations

from . import ast_st as A
from .compilador_expr import Expresiones, Val, texto
from .tipos import ENTEROS, ERROR, INT, DINT, InterfazFB, nombre
from .errores import sugerir


class Emisor:
    """Líneas de Python con su sangría y la línea ST de la que salen (para las fallas)."""

    def __init__(self) -> None:
        self.lineas: list[str] = []
        self.mapa: list[int] = []
        self.nivel = 0

    def __call__(self, codigo: str, linea_st: int) -> None:
        self.lineas.append("    " * self.nivel + codigo)
        self.mapa.append(linea_st)


class Sentencias(Expresiones):
    """Mixin: necesita además `self.em` (Emisor), `self.bucles` y `self.temporales`."""

    def nuevo(self, prefijo: str) -> str:
        self.temporales += 1
        return f"{prefijo}{self.temporales}"

    def bloque(self, cuerpo: list, linea: int) -> None:
        self.em.nivel += 1
        antes = len(self.em.lineas)
        for s in cuerpo:
            try:
                getattr(self, "_s_" + type(s).__name__)(s)
            except RecursionError:
                self.err(s, "la expresión es demasiado larga o anidada: pártela en varias "
                         "asignaciones")
        if len(self.em.lineas) == antes:
            self.em("pass", linea)
        self.em.nivel -= 1

    def _s_Asignacion(self, s: A.Asignacion) -> None:
        destino = self.lvalor(s.destino)
        v = self.expr(s.valor)
        if destino is None:
            return
        code = self.coaccionar(v, destino[1], s.valor, f"«{texto(s.destino)}»")
        self.em(f"{destino[0]} = {code}", s.linea)

    def _s_LlamadaSent(self, s: A.LlamadaSent) -> None:
        ll = s.llamada
        v = self.buscar(ll.nombre)
        if v is not None and isinstance(v.tipo, InterfazFB):
            self._llamar_bloque(v, ll)
            return
        r = self.expr(ll)
        if r.tipo != ERROR:
            self.em(r.code, s.linea)

    def _llamar_bloque(self, v, ll: A.Llamada) -> None:
        fb = v.tipo
        miembros = [o for o, _ in (*fb.entradas.values(), *fb.salidas.values())]
        self.em(f"_i = {v.acceso}", ll.linea)
        salidas, vistos = [], set()
        posicional = next((a for a in ll.args if a.nombre is None), None)
        if posicional is not None:
            ejemplo = ", ".join(f"{o} := …" for o, _ in fb.entradas.values())
            self.err(posicional, f"en la llamada a un bloque nombra cada entrada: "
                     f"«{v.nombre}({ejemplo})»")
        for a in ll.args:
            if a.nombre is None:
                continue
            k = a.nombre.lower()
            if k in vistos:
                self.err(a, f"«{a.nombre}» va dos veces en la llamada")
                continue
            vistos.add(k)
            if a.destino is None:
                if k in fb.entradas:
                    orig, tipo = fb.entradas[k]
                    code = self.coaccionar(self.expr(a.valor), tipo, a,
                                           f"la entrada {orig} de «{v.nombre}»")
                    self.em(f"_i.v_{k} = {code}", a.linea)
                elif k in fb.salidas:
                    self.err(a, f"«{fb.salidas[k][0]}» es una salida de {fb.nombre}: se lee con "
                             f"«{fb.salidas[k][0]} => variable»")
                else:
                    self.err(a, f"{fb.nombre} no tiene «{a.nombre}» ({fb.miembros()})."
                             + sugerir(a.nombre, miembros))
            elif k in fb.salidas:
                salidas.append((k, a))
            elif k in fb.entradas:
                self.err(a, f"«{fb.entradas[k][0]}» es una entrada: se asigna con "
                         f"«{fb.entradas[k][0]} := valor»")
            else:
                self.err(a, f"{fb.nombre} no tiene «{a.nombre}» ({fb.miembros()})."
                         + sugerir(a.nombre, miembros))
        self.em(f"{fb.py}(_i, t)", ll.linea)
        for k, a in salidas:
            destino = self.lvalor(a.destino)
            if destino is not None:
                orig, tipo = fb.salidas[k]
                code = self.coaccionar(Val(f"_i.v_{k}", tipo), destino[1], a,
                                       f"«{texto(a.destino)}»")
                self.em(f"{destino[0]} = {code}", a.linea)

    def _s_Si(self, s: A.Si) -> None:
        for n, (cond, cuerpo) in enumerate(s.ramas):
            c = self.condicion(cond, "la condición del IF" if n == 0 else "la del ELSIF")
            self.em(("if " if n == 0 else "elif ") + c + ":", cond.linea)
            self.bloque(cuerpo, cond.linea)
        if s.sino is not None:
            self.em("else:", s.linea)
            self.bloque(s.sino, s.linea)

    def _s_Caso(self, s: A.Caso) -> None:
        sel = self.expr(s.selector)
        if sel.tipo not in (*ENTEROS, ERROR):
            self.err(s.selector, f"el selector del CASE es un entero (INT o DINT) y aquí hay "
                     f"{nombre(sel.tipo)}")
        tmp = self.nuevo("_c")
        self.em(f"{tmp} = {sel.code}", s.linea)
        vistos: list[tuple[int, int, int]] = []
        for n, (etiquetas, cuerpo) in enumerate(s.ramas):
            partes = []
            for et in etiquetas:
                lo = et.lo.valor
                hi = et.hi.valor if et.hi is not None else lo
                if hi < lo:
                    self.err(et, f"el rango {lo}..{hi} está al revés: escribe {hi}..{lo}")
                for a, b, ln in vistos:
                    if lo <= b and a <= hi:
                        self.err(et, f"la etiqueta {lo if lo == hi else f'{lo}..{hi}'} ya está "
                                 f"en la rama de la línea {ln}")
                        break
                vistos.append((lo, hi, et.linea))
                partes.append(f"{tmp} == {lo}" if lo == hi else f"{lo} <= {tmp} <= {hi}")
            self.em(("if " if n == 0 else "elif ") + " or ".join(partes) + ":", etiquetas[0].linea)
            self.bloque(cuerpo, etiquetas[0].linea)
        if s.sino is not None:
            if s.ramas:
                self.em("else:", s.linea)
                self.bloque(s.sino, s.linea)
            else:
                self.em("if True:", s.linea)
                self.bloque(s.sino, s.linea)

    def _abrir_bucle(self, cond: str, linea: int) -> str:
        n = self.nuevo("_n")
        self.em(f"{n} = 0", linea)
        self.em(f"while {cond}:", linea)
        self.em.nivel += 1
        self.em(f"{n} += 1", linea)
        self.em(f"if {n} > _wd.resto: _falla_wd()", linea)
        self.em.nivel -= 1
        self.bucles.append(n)
        return n

    def _cerrar_bucle(self, n: str, linea: int) -> None:
        self.bucles.pop()
        self.em(f"_wd.resto -= {n}", linea)

    def _s_Para(self, s: A.Para) -> None:
        destino = self.lvalor(s.var)
        desde, hasta = self.expr(s.desde), self.expr(s.hasta)
        paso = self.expr(s.paso) if s.paso is not None else Val("1", "LIT_INT", const=1)
        if destino is None:
            return
        acc, tipo = destino
        if tipo not in (INT, DINT, ERROR):
            self.err(s.var, f"la variable de control del FOR es INT o DINT y «{s.var.texto}» "
                     f"es {nombre(tipo)}")
            return
        que = f"el FOR de «{s.var.texto}»"
        self.em(f"{acc} = {self.coaccionar(desde, tipo, s.desde, que)}", s.linea)
        fin = self.coaccionar(hasta, tipo, s.hasta, que)
        if hasta.const is None:
            f = self.nuevo("_f")
            self.em(f"{f} = {fin}", s.linea)
            fin = f
        p = self.coaccionar(paso, tipo, s.paso or s, que)
        if paso.const is not None:
            if paso.const == 0:
                self.err(s.paso, "el paso (BY) del FOR no puede ser 0")
            cond = f"{acc} {'<=' if paso.const > 0 else '>='} {fin}"
        else:
            pv = self.nuevo("_p")
            self.em(f"{pv} = {p}", s.linea)
            p = pv
            cond = f"(({acc} <= {fin}) if {pv} >= 0 else ({acc} >= {fin}))"
        n = self._abrir_bucle(cond, s.linea)
        self.para_activos.add(acc)
        self.bloque(s.cuerpo, s.linea)
        self.em.nivel += 1
        self.em(f"{acc} = {acc} + {p}", s.linea)
        self.em.nivel -= 1
        self.para_activos.discard(acc)
        self._cerrar_bucle(n, s.linea)

    def _s_Mientras(self, s: A.Mientras) -> None:
        c = self.condicion(s.cond, "la condición del WHILE")
        n = self._abrir_bucle(c, s.linea)
        self.bloque(s.cuerpo, s.linea)
        self._cerrar_bucle(n, s.linea)

    def _s_Repetir(self, s: A.Repetir) -> None:
        n = self._abrir_bucle("True", s.linea)
        self.bloque(s.cuerpo, s.linea)
        c = self.condicion(s.cond, "la condición del UNTIL")
        self.em.nivel += 1
        self.em(f"if {c}: break", s.cond.linea)
        self.em.nivel -= 1
        self._cerrar_bucle(n, s.linea)

    def _s_Salir(self, s: A.Salir) -> None:
        if not self.bucles:
            self.err(s, "EXIT sólo va dentro de un FOR, WHILE o REPEAT")
            return
        self.em("break", s.linea)

    def _s_Retornar(self, s: A.Retornar) -> None:
        if self.bucles:
            self.em(f"_wd.resto -= {' + '.join(self.bucles)}", s.linea)
        self.em("return" + (f" {self.retorno}" if self.retorno else ""), s.linea)
