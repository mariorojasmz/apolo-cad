"""Compilador de ST a Python (D4–D6): `compilar(fuente, bornes=…)` → `Compilado`.

Pasos: parsear → registrar las POU → declarar variables (tipos, AT, RETAIN, valores
iniciales, disposición de memoria) → compilar cada cuerpo → chequear recursión y bloques que
se contienen → armar las funciones de la imagen de E/S → verificar el Python con la lista
blanca → `compile`. Los errores de declaración y de tipos se juntan (todos a la vez); los de
sintaxis cortan en el primero.

`bornes` es el conjunto de bornes del PLC del catálogo (`I0.0`, `Q0.0`, `AI0`…): una
dirección que el PLC no tiene es error de compilación (D4). `plc/` no lee el catálogo: quien
compila le pasa los bornes. `None` = sin validar (pruebas del lenguaje).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from . import ast_st as A
from . import direcciones as D
from .compilador_expr import _RE_CONV
from .compilador_sent import Emisor, Sentencias
from .errores import ErrorCompilacion, ErrorSintaxis, ErrorST, sugerir
from .parser import parsear
from .simbolos import Campo, InfoPOU, Var
from .simbolos import tabla as tabla_simbolos
from .tipos import (DEFECTO, ELEMENTALES, ERROR, FB_ESTANDAR, FUNCIONES_ESTANDAR, INT, DINT,
                    LIT_INT, RANGO, REAL, Arreglo, InterfazFB, nombre)
from .verificador import verificar

ARCHIVO_PY = "<plc>"
_PREFIJO = {"PROGRAM": "_p_", "FUNCTION": "_f_", "FUNCTION_BLOCK": "_fb_"}
_CLASE_VAR = {"VAR_GLOBAL": "global", "VAR_INPUT": "entrada", "VAR_OUTPUT": "salida",
              "VAR": "local"}
_DEMASIADO = "la expresión es demasiado larga o anidada: pártela en varias asignaciones"
_RE_BIT = re.compile(r"^([IQ])(\d+)\.(\d)$", re.ASCII)
_RE_PALABRA = re.compile(r"^A([IQ])(\d+)$", re.ASCII)


@dataclass
class Compilado:
    """Un programa compilado: el Python verificado y lo que el runtime necesita para correrlo.

    Es picklable (el código objeto se rearma y se RE-VERIFICA al pedirlo): así viaja al worker
    de la co-simulación (V8.3 D11)."""

    fuente_py: str
    programas: list[tuple[str, str, str]]            # (nombre, clave, función)
    disposiciones: dict[str, list[Campo]]            # «<global>», PROGRAM y FB del usuario
    rutas: dict[str, dict[str, tuple]]               # ámbito → var → (attr, fb, en_global, lo)
    tags: list[dict]
    entradas: list[str]                              # bornes que lee el programa
    salidas: list[tuple[str, str]]                   # (borne, tipo) que escribe
    mapa_lineas: list[int]                           # línea Python - 1 → línea ST
    pous_py: dict[str, str]                          # función generada → POU de ST
    simbolos: dict[str, tuple[str, bool]] = field(default_factory=dict)  # ruta → (tipo, escribible)
    _codigo: object = field(default=None, repr=False, compare=False)

    @property
    def codigo(self):
        if self._codigo is None:
            verificar(self.fuente_py)
            self._codigo = compile(self.fuente_py, ARCHIVO_PY, "exec")
        return self._codigo

    def __getstate__(self):
        estado = dict(self.__dict__)
        estado["_codigo"] = None
        return estado


class _CompiladorPOU(Sentencias):
    def __init__(self, u: _Unidad, pou: InfoPOU):
        self.u, self.pou = u, pou
        self.em = Emisor()
        self.bucles: list[str] = []
        self.temporales = 0
        self.para_activos: set[str] = set()
        self.retorno = f"v_{pou.nodo.nombre.lower()}" if pou.clase == "FUNCTION" else ""

    def compilar(self) -> Emisor:
        nodo, em = self.pou.nodo, self.em
        if self.pou.clase != "FUNCTION":
            em(f"def {self.pou.py}(s, t):", nodo.linea)
            self.bloque(nodo.cuerpo, nodo.linea)
            return em
        em(f"def {self.pou.py}({', '.join(p.acceso for p in self.pou.parametros)}):",
           nodo.linea)
        em.nivel += 1
        em(f"{self.retorno} = {DEFECTO.get(self.pou.tipo_ret, 0)!r}", nodo.linea)
        for v in self.pou.vars.values():
            if v.clase == "local":
                em(f"{v.acceso} = {v.inicial_py}", v.linea)
        em.nivel -= 1
        self.bloque(nodo.cuerpo, nodo.linea)
        em.nivel += 1
        em(f"return {self.retorno}", nodo.linea)
        em.nivel -= 1
        return em


def _codigo_inicial(valor) -> str:
    if isinstance(valor, list):
        if all(x == valor[0] for x in valor):
            return f"[{valor[0]!r}] * {len(valor)}"
        return "[" + ", ".join(repr(x) for x in valor) + "]"
    return repr(valor)


class _Unidad:
    def __init__(self, arbol: A.Unidad, bornes: Iterable[str] | None):
        self.arbol = arbol
        self.errores: list[ErrorST] = []
        self.bornes = None if bornes is None else {str(b) for b in bornes}
        self.globales: dict[str, Var] = {}
        self.pous: dict[str, InfoPOU] = {}
        self.disposiciones: dict[str, list[Campo]] = {"<global>": []}
        self.dirs: dict[str, dict] = {}

    def err(self, linea: int, col: int, mensaje: str) -> None:
        self.errores.append(ErrorST(linea, col, mensaje))

    # ── POU y tipos ──────────────────────────────────────────────────────
    def registrar_pous(self) -> None:
        for p in self.arbol.pous:
            k = p.nombre.lower()
            if k in self.pous:
                self.err(p.linea, p.col, f"ya hay una POU «{p.nombre}» en la línea "
                         f"{self.pous[k].nodo.linea}")
                continue
            if k in FB_ESTANDAR or p.nombre.upper() in FUNCIONES_ESTANDAR or _RE_CONV.match(k):
                self.err(p.linea, p.col, f"«{p.nombre}» es un nombre estándar de IEC 61131-3: "
                         "elige otro")
                continue
            info = InfoPOU(p.clase, p.nombre, _PREFIJO[p.clase] + k, p)
            if p.clase == "FUNCTION_BLOCK":
                info.interfaz = InterfazFB(p.nombre, info.py)
                self.disposiciones[k] = []
            elif p.clase == "PROGRAM":
                self.disposiciones[k] = []
            else:
                info.tipo_ret = p.tipo_ret.nombre
            self.pous[k] = info
        if not any(p.clase == "PROGRAM" for p in self.pous.values()):
            p = self.arbol.pous[0]
            self.err(p.linea, p.col, "falta un PROGRAM: es lo que corre el PLC en cada ciclo")

    def tipo_de(self, t):
        if isinstance(t, A.TipoArreglo):
            return Arreglo(t.elem.nombre, t.lo, t.hi)
        if t.nombre in ELEMENTALES:
            return t.nombre
        k = t.nombre.lower()
        if k in FB_ESTANDAR:
            return FB_ESTANDAR[k]
        info = self.pous.get(k)
        if info is not None and info.clase == "FUNCTION_BLOCK":
            return info.interfaz
        if info is not None:
            self.err(t.linea, t.col, f"«{t.nombre}» es un {info.clase}, no un tipo de variable")
        else:
            fbs = [i.nombre for i in self.pous.values() if i.clase == "FUNCTION_BLOCK"]
            self.err(t.linea, t.col, f"no existe el tipo «{t.nombre}»."
                     + sugerir(t.nombre, [*ELEMENTALES, *(f.nombre for f in
                                                          FB_ESTANDAR.values()), *fbs]))
        return ERROR

    # ── declaraciones ────────────────────────────────────────────────────
    def declarar(self) -> None:
        for b in self.arbol.globales:
            self.declarar_bloque(b, None)
        for k, info in self.pous.items():
            if info.clase == "FUNCTION":       # el valor que devuelve: `Nombre := …;`
                info.vars[k] = Var(info.nombre, info.tipo_ret, "retorno", f"v_{k}",
                                   linea=info.nodo.linea, col=info.nodo.col)
            for b in info.nodo.bloques:
                self.declarar_bloque(b, info)

    def declarar_bloque(self, b: A.BloqueVar, pou: InfoPOU | None) -> None:
        clase = pou.clase if pou else None
        problema = None
        if b.clase == "VAR_GLOBAL" and clase in ("FUNCTION", "FUNCTION_BLOCK"):
            problema = "VAR_GLOBAL va fuera de las POU o dentro de un PROGRAM"
        elif b.clase in ("VAR_INPUT", "VAR_OUTPUT") and clase == "PROGRAM":
            problema = "un PROGRAM no tiene VAR_INPUT ni VAR_OUTPUT: usa VAR o VAR_GLOBAL"
        elif b.clase == "VAR_OUTPUT" and clase == "FUNCTION":
            problema = ("una FUNCTION devuelve un solo valor: asígnalo a su nombre "
                        f"(«{pou.nombre} := …;»)")
        elif b.retain and clase == "FUNCTION":
            problema = ("una FUNCTION no guarda estado: RETAIN va en un PROGRAM, un "
                        "FUNCTION_BLOCK o VAR_GLOBAL")
        elif b.constante and b.clase in ("VAR_INPUT", "VAR_OUTPUT"):
            problema = "CONSTANT va en VAR o VAR_GLOBAL"
        if problema:
            self.err(b.linea, b.col, problema)
            return
        for d in b.decls:
            tipo = self.tipo_de(d.tipo)
            for nombre_, ln, col in d.nombres:
                self.declarar_var(nombre_, ln, col, d, tipo, b, pou)

    def declarar_var(self, nom: str, ln: int, col: int, d: A.Decl, tipo, b: A.BloqueVar,
                     pou: InfoPOU | None) -> None:
        k = nom.lower()
        es_global = b.clase == "VAR_GLOBAL"
        tabla = self.globales if es_global else pou.vars
        if k in tabla:
            self.err(ln, col, f"«{nom}» ya está declarada en la línea {tabla[k].linea}")
            return
        if k in self.pous or k in FB_ESTANDAR or nom.upper() in FUNCIONES_ESTANDAR \
                or _RE_CONV.match(k):
            self.err(ln, col, f"«{nom}» ya es el nombre de una POU o de un bloque o función "
                     "estándar: elige otro")
            return
        es_fb, es_arr = isinstance(tipo, InterfazFB), isinstance(tipo, Arreglo)
        en_funcion = pou is not None and pou.clase == "FUNCTION"
        if es_fb and en_funcion:
            self.err(ln, col, "una FUNCTION no tiene instancias de bloques (no guarda estado): "
                     "usa un FUNCTION_BLOCK")
            return
        if (es_fb or es_arr) and b.clase in ("VAR_INPUT", "VAR_OUTPUT"):
            self.err(ln, col, "las entradas y salidas son de tipo elemental (BOOL, INT, DINT, "
                     "REAL o TIME)")
            return
        if es_fb and b.constante:
            self.err(ln, col, "un bloque no es CONSTANT")
            return
        direccion = self._direccion_de(nom, ln, col, d, tipo, b, pou, es_fb or es_arr)
        inicial = self.valor_inicial(d.inicial, tipo, nom, d)
        if direccion is not None:
            acceso = f"_G.{direccion.ident}"
            if d.inicial is not None:
                if direccion.es_entrada:
                    self.err(ln, col, "una entrada no lleva valor inicial: lo da el borne")
                else:
                    self.dirs[direccion.texto]["inicial"] = inicial
        elif es_global:
            acceso = f"_G.v_{k}"
        elif en_funcion:
            acceso = f"v_{k}"
        else:
            acceso = f"s.v_{k}"
        v = Var(nom, tipo, _CLASE_VAR[b.clase], acceso, b.retain, b.constante, direccion,
                _codigo_inicial(inicial) if inicial is not None else "", ln, col)
        tabla[k] = v
        if direccion is None and not en_funcion:
            ambito = "<global>" if es_global else pou.nodo.nombre.lower()
            fb = None
            if es_fb:
                fb = tipo.nombre.lower()
            self.disposiciones[ambito].append(Campo(f"v_{k}", inicial, b.retain, fb))
        if pou is not None and pou.clase == "FUNCTION_BLOCK" and b.clase != "VAR":
            lado = pou.interfaz.entradas if b.clase == "VAR_INPUT" else pou.interfaz.salidas
            lado[k] = (nom, tipo)
        if en_funcion and b.clase == "VAR_INPUT":
            pou.parametros.append(v)

    def _direccion_de(self, nom, ln, col, d, tipo, b, pou, compuesto):
        if d.direccion is None:
            return None
        texto_, dl, dc = d.direccion
        if pou is not None and pou.clase != "PROGRAM":
            self.err(dl, dc, "las direcciones (AT) van en VAR_GLOBAL o en el VAR de un PROGRAM")
            return None
        if b.retain:
            self.err(dl, dc, "una variable con AT no lleva RETAIN: su valor es el del borne")
            return None
        if compuesto:
            self.err(dl, dc, "AT va en una variable elemental (BOOL o INT)")
            return None
        nombre_tag = nom if pou is None or b.clase == "VAR_GLOBAL" else f"{pou.nombre}.{nom}"
        direccion = self.usar_direccion(texto_, A.DirExpr(texto_, dl, dc), escritura=False,
                                        declarada=nombre_tag)
        if direccion is not None and tipo not in (direccion.tipo, ERROR):
            self.err(ln, col, f"«{nom}» está en {direccion.texto}, que es {direccion.tipo}: "
                     f"declárala {direccion.tipo}")
        return direccion

    def valor_inicial(self, e, tipo, nom: str, d: A.Decl):
        if isinstance(tipo, InterfazFB):
            if e is not None:
                self.err(d.linea, d.col, "un bloque no lleva valor inicial")
            return None
        if isinstance(tipo, Arreglo):
            base = DEFECTO[tipo.elem]
            if e is None:
                return [base] * tipo.n
            if not isinstance(e, A.InicialArreglo):
                self.err(e.linea, e.col, "un ARRAY se inicia con [v1, v2, …] o [n(v)]")
                return [base] * tipo.n
            valores = []
            for rep, x in e.elementos:
                valores += [self._constante(x, tipo.elem, nom)] * rep
            if len(valores) > tipo.n:
                self.err(e.linea, e.col, f"«{nom}» tiene {tipo.n} elementos y le das "
                         f"{len(valores)} valores iniciales")
            return (valores + [base] * tipo.n)[:tipo.n]
        if tipo == ERROR:
            return 0
        if e is None:
            return DEFECTO[tipo]
        if isinstance(e, A.InicialArreglo):
            self.err(e.linea, e.col, "sólo un ARRAY se inicia con [ … ]")
            return DEFECTO[tipo]
        return self._constante(e, tipo, nom)

    def _constante(self, e, tipo: str, nom: str):
        if not isinstance(e, A.Literal):
            self.err(e.linea, e.col, "el valor inicial es un literal (p. ej. 0, 1.5, TRUE o "
                     "T#2s)")
            return DEFECTO[tipo]
        if e.tipo == LIT_INT and tipo in (INT, DINT, REAL):
            if tipo in RANGO and not RANGO[tipo][0] <= e.valor <= RANGO[tipo][1]:
                self.err(e.linea, e.col, f"{e.valor} no cabe en {tipo} ({RANGO[tipo][0]} … "
                         f"{RANGO[tipo][1]})." + (" Declárala DINT." if tipo == INT else ""))
                return DEFECTO[tipo]
            return float(e.valor) if tipo == REAL else e.valor
        if e.tipo != tipo:
            self.err(e.linea, e.col, f"el valor inicial de «{nom}» es {tipo} y le das "
                     f"{nombre(e.tipo)}")
            return DEFECTO[tipo]
        return e.valor

    # ── direcciones ──────────────────────────────────────────────────────
    def _validas(self, d: D.Direccion) -> list[str]:
        """Las direcciones del mismo tipo que sí tiene el PLC, en orden."""
        out = []
        for b in self.bornes or ():
            m = _RE_BIT.match(b) if d.tamano == "X" else _RE_PALABRA.match(b)
            if m and m.group(1) == d.area:
                byte, bit = int(m.group(2)), int(m.group(3)) if d.tamano == "X" else 0
                texto_ = f"%{d.area}X{byte}.{bit}" if d.tamano == "X" else f"%{d.area}W{byte}"
                out.append((byte, bit, texto_))
        return [x[2] for x in sorted(out)]

    def usar_direccion(self, texto_: str, nodo, escritura: bool, declarada: str | None = None):
        d = D.parsear(texto_)
        if isinstance(d, str):
            self.err(nodo.linea, nodo.col, d)
            return None
        if self.bornes is not None and d.borne not in self.bornes:
            validas = self._validas(d)
            rango = (f" Tiene {validas[0]} … {validas[-1]}." if validas
                     else " Este PLC no tiene ese tipo de E/S.")
            self.err(nodo.linea, nodo.col, f"«{d.texto}» no existe en este PLC (sería su borne "
                     f"{d.borne})." + sugerir(d.texto, validas) + rango)
            return None
        if escritura and d.es_entrada:
            self.err(nodo.linea, nodo.col, f"{d.texto} es una entrada: el programa la lee, no "
                     "la escribe")
            return None
        rec = self.dirs.setdefault(d.texto, {"dir": d, "vars": [], "inicial": None})
        if declarada is not None:
            if not d.es_entrada and rec["vars"]:
                self.err(nodo.linea, nodo.col, f"la salida {d.texto} ya es de «{rec['vars'][0]}»: "
                         "una salida tiene un solo dueño")
                return None
            rec["vars"].append(declarada)
        return d

    # ── chequeos globales ────────────────────────────────────────────────
    def _ciclos(self, sucesores, que: str) -> None:
        estado: dict[str, int] = {}

        def visitar(k: str, camino: list[str]) -> None:
            estado[k] = 1
            for s in sucesores(k):
                if estado.get(s) == 1:
                    ciclo = camino[camino.index(s):] + [s] if s in camino else [k, s]
                    p = self.pous[s].nodo
                    nombres = " → ".join(self.pous[x].nombre for x in ciclo)
                    self.err(p.linea, p.col, que.format(self.pous[s].nombre, nombres))
                elif s not in estado:
                    visitar(s, camino + [s])
            estado[k] = 2

        for k in self.pous:
            if k not in estado:
                visitar(k, [k])

    def chequear_contencion(self) -> None:
        def sucesores(k):
            if self.pous[k].clase != "FUNCTION_BLOCK":
                return []
            return [c.fb for c in self.disposiciones[k] if c.fb in self.pous]
        self._ciclos(sucesores, "el bloque «{0}» se contiene a sí mismo ({1}): un "
                     "FUNCTION_BLOCK no puede tener una instancia de sí mismo")

    def chequear_recursion(self) -> None:
        self._ciclos(lambda k: sorted(self.pous[k].llama), "la FUNCTION «{0}» se llama a sí "
                     "misma ({1}): ST no admite recursión")

    # ── armado ───────────────────────────────────────────────────────────
    def armar(self) -> Compilado:
        lineas: list[str] = []
        mapa: list[int] = []
        for info in self.pous.values():
            em = _CompiladorPOU(self, info).compilar()
            lineas += em.lineas
            mapa += em.mapa
        self.chequear_recursion()
        if self.errores:
            raise ErrorCompilacion(self.errores)
        dirs = sorted((r["dir"] for r in self.dirs.values()),
                      key=lambda d: (not d.es_entrada, d.tamano, d.byte, d.bit or 0))
        ent = [d for d in dirs if d.es_entrada]
        sal = [d for d in dirs if not d.es_entrada]
        for nombre_fn, lista, plantilla in (("_entradas(e)", ent, "_G.{0} = e[{1!r}]"),
                                            ("_salidas(o)", sal, "o[{1!r}] = _G.{0}")):
            lineas.append(f"def {nombre_fn}:")
            lineas += [f"    {plantilla.format(d.ident, d.borne)}" for d in lista] or ["    pass"]
            mapa += [0] * (1 + max(1, len(lista)))
        for d in dirs:
            inicial = self.dirs[d.texto]["inicial"]
            self.disposiciones["<global>"].append(
                Campo(d.ident, DEFECTO[d.tipo] if inicial is None else inicial))
        fuente_py = "\n".join(lineas) + "\n"
        try:
            verificar(fuente_py)
        except (SyntaxError, RecursionError, MemoryError) as e:   # p. ej. > 200 paréntesis
            n = getattr(e, "lineno", None) or 0
            raise ErrorCompilacion([ErrorST(mapa[n - 1] if 0 < n <= len(mapa) else 1, 1,
                                            _DEMASIADO)]) from None
        return Compilado(
            fuente_py=fuente_py,
            programas=[(i.nombre, k, i.py) for k, i in self.pous.items()
                       if i.clase == "PROGRAM"],
            disposiciones=self.disposiciones,
            rutas=self._rutas(),
            tags=self._tags(dirs),
            entradas=[d.borne for d in ent],
            salidas=[(d.borne, d.tipo) for d in sal],
            mapa_lineas=mapa,
            pous_py={i.py: i.nombre for i in self.pous.values()},
            simbolos=tabla_simbolos(self.globales, self.pous),
        )

    def _rutas(self) -> dict[str, dict[str, tuple]]:
        def entrada(v: Var):
            attr = v.acceso.split(".")[-1]
            fb = v.tipo.nombre.lower() if isinstance(v.tipo, InterfazFB) else None
            lo = v.tipo.lo if isinstance(v.tipo, Arreglo) else None
            return attr, fb, v.acceso.startswith("_G."), lo
        rutas = {"<global>": {k: entrada(v) for k, v in self.globales.items()}}
        for k, info in self.pous.items():
            if info.clase != "FUNCTION":
                rutas[k] = {kv: entrada(v) for kv, v in info.vars.items()}
        return rutas

    def _tags(self, dirs: list[D.Direccion]) -> list[dict]:
        tags = []
        for d in dirs:
            variables = self.dirs[d.texto]["vars"] or [None]
            for v in variables:
                tags.append({"variable": v, "direccion": d.texto, "borne": d.borne,
                             "tipo": d.tipo, "sentido": "entrada" if d.es_entrada else "salida"})
        return tags


def compilar(fuente: str, *, bornes: Iterable[str] | None = None) -> Compilado:
    """Compila un programa ST. Lanza `ErrorCompilacion` con línea, columna y mensaje."""
    try:
        arbol = parsear(fuente)
    except ErrorSintaxis as e:
        raise ErrorCompilacion([e.error]) from None
    u = _Unidad(arbol, bornes)
    u.registrar_pous()
    u.declarar()
    u.chequear_contencion()
    if u.errores:
        raise ErrorCompilacion(u.errores)
    return u.armar()


__all__ = ["Compilado", "compilar", "ARCHIVO_PY"]
