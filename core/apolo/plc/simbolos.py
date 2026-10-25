"""Símbolos del compilador (variables y POU), la disposición de memoria que usa el runtime y la
tabla de símbolos del programa compilado con su regla de ESCRITURA (plan plc-en-el-lazo, D10).

`tabla(globales, pous)` arma `Compilado.simbolos`: {ruta: (tipo, escribible)} con las rutas de
`PLC.variables()` (`x` global, `Main.x` de un PROGRAM) más cada instancia de bloque y sus miembros
(`Main.t1`, `Main.t1.q`). Escribibles: las elementales y los ARRAY (por elemento: `a[2]`) de las
globales y de cada PROGRAM; nunca una CONSTANT, una variable con `AT %I…`/`%Q…` ni un bloque o sus
miembros. `escritura(compilado, ruta, valor)` resuelve la ruta como `PLC.leer` y valida el valor
por tipo; la comparten `PLC.escribir` y la agenda de la co-simulación (con un PLC externo, antes de
pasarle la escritura a su conector). No se persiste: se rearma al compilar.
"""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass, field

from . import ast_st as A
from .direcciones import Direccion
from .direcciones import parsear as parsear_direccion
from .tipos import BOOL, ELEMENTALES, RANGO, REAL, TIME, InterfazFB, nombre

GLOBAL = "<global>"
RE_SEGMENTO = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(-?\d+)\])?$")
_RE_ARREGLO = re.compile(r"^ARRAY\[(-?\d+)\.\.(-?\d+)\] OF (\w+)$")


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


# ── la tabla de símbolos (D10) ──────────────────────────────────────────────────────────────

def tabla(globales: dict[str, Var], pous: dict[str, InfoPOU]) -> dict[str, tuple[str, bool]]:
    """{ruta: (tipo, escribible)}: las globales y las variables de cada PROGRAM, en orden de
    declaración, y los miembros de cada instancia de bloque (nunca escribibles)."""
    out: dict[str, tuple[str, bool]] = {}

    def poner(ruta: str, v_tipo, escribible: bool) -> None:
        if not isinstance(v_tipo, InterfazFB):
            out[ruta] = (nombre(v_tipo), escribible)
            return
        out[ruta] = (v_tipo.nombre, False)
        if v_tipo.estandar:
            for k, (_, t) in {**v_tipo.entradas, **v_tipo.salidas}.items():
                out[f"{ruta}.{k}"] = (t, False)
        else:
            for k, v in pous[v_tipo.nombre.lower()].vars.items():
                poner(f"{ruta}.{k}", v.tipo, False)

    for k, v in globales.items():
        poner(k, v.tipo, not v.constante and v.direccion is None)
    for info in pous.values():
        if info.clase == "PROGRAM":
            for k, v in info.vars.items():
                poner(f"{info.nombre}.{k}", v.tipo, not v.constante and v.direccion is None)
    return out


# ── resolver una ruta (la de `PLC.leer`) ────────────────────────────────────────────────────

def ambito_de(rutas: dict, programas: list, ruta: str) -> tuple[str, list[str]]:
    """El ámbito de `ruta` («<global>» o la clave de un PROGRAM) y sus segmentos dentro de él: una
    global, `Prog.x` o `x` de un único PROGRAM. `KeyError` si no existe o es ambigua."""
    partes = ruta.split(".")
    k0 = partes[0].lower()
    m = RE_SEGMENTO.match(partes[0])
    if m and m.group(1).lower() in rutas[GLOBAL]:  # también `g[2]`, un elemento de un ARRAY global
        return GLOBAL, partes
    if k0 in {clave for _, clave, _ in programas} and len(partes) > 1:
        return k0, partes[1:]
    duenos = [(n, c) for n, c, _ in programas if m and m.group(1).lower() in rutas[c]]
    if len(duenos) != 1:
        otros = " o ".join(f"«{n}.{partes[0]}»" for n, _ in duenos)
        raise KeyError(f"no existe la variable «{ruta}»" if not duenos
                       else f"«{ruta}» es ambigua: usa {otros}")
    return duenos[0][1], partes


# ── escribir (D10) ──────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Destino:
    """Dónde cae una escritura en la memoria del PLC."""

    ambito: str                 # «<global>» o la clave del PROGRAM
    attr: str                   # `v_x`
    indice: int | None          # posición en la lista de un ARRAY (desde 0)
    tipo: str                   # el elemental que se escribe


def escritura(compilado, ruta: str, valor) -> tuple[Destino, object]:
    """(destino, valor) de `PLC.escribir(ruta, valor)`. `KeyError` si la ruta no existe;
    `ValueError` si no es escribible o el valor no es de su tipo (cada texto dice por qué)."""
    if not isinstance(ruta, str) or not ruta:
        raise KeyError("falta la variable: su ruta en el programa («Main.consigna», «x», «a[2]»)")
    if ruta.startswith("%"):
        raise ValueError(f"«{ruta}» es una dirección de E/S: una entrada la escribe su borne y una "
                         "salida, el programa; escribe una variable de memoria")
    rutas, simbolos = compilado.rutas, compilado.simbolos
    try:
        ambito, partes = ambito_de(rutas, compilado.programas, ruta)
    except KeyError as exc:
        if "ambigua" in str(exc):
            raise
        raise KeyError(f"no existe la variable «{ruta}».{_pista(ruta, simbolos)}") from None
    segs = [RE_SEGMENTO.match(s) for s in partes]
    prefijo = "" if ambito == GLOBAL else next(n for n, c, _ in compilado.programas if c == ambito) + "."
    clave = prefijo + ".".join(m.group(1).lower() if m else s for m, s in zip(segs, partes))
    if not all(segs) or clave not in simbolos:
        raise KeyError(f"no existe la variable «{ruta}».{_pista(clave, simbolos)}")
    tipo, escribible = simbolos[clave]
    attr, fb, _, lo = rutas[ambito][segs[0].group(1).lower()]
    if not escribible:
        bloque = simbolos[prefijo + segs[0].group(1).lower()][0] if fb is not None else None
        raise ValueError(_por_que_no(compilado, ruta, attr, bloque, len(segs)))
    m = segs[-1]
    arreglo = _RE_ARREGLO.match(tipo)
    if arreglo is None:
        if m.group(2) is not None:
            raise KeyError(f"«{ruta}»: «{m.group(1)}» no es un ARRAY")
        return Destino(ambito, attr, None, tipo), valor_para(tipo, valor, ruta)
    if m.group(2) is None:
        raise ValueError(f"«{ruta}» es un {tipo}: escribe un elemento, p. ej. «{ruta}[{lo}]»")
    i = int(m.group(2)) - lo
    if not 0 <= i <= int(arreglo.group(2)) - lo:
        raise KeyError(f"índice fuera de rango en «{ruta}» ({arreglo.group(1)} … {arreglo.group(2)})")
    elem = arreglo.group(3)
    return Destino(ambito, attr, i, elem), valor_para(elem, valor, ruta)


def _pista(clave: str, simbolos: dict) -> str:
    parecida = difflib.get_close_matches(clave, list(simbolos), n=1)
    return f" ¿Quisiste decir «{parecida[0]}»?" if parecida else ""


def _por_que_no(compilado, ruta: str, attr: str, bloque: str | None, n_segs: int) -> str:
    if bloque is not None:
        return (f"«{ruta}» es {'un miembro de ' if n_segs > 1 else ''}una instancia de "
                f"{bloque}: lo calcula el bloque; escribe una variable global o del PROGRAM y "
                "pásasela como entrada")
    if attr.startswith("d_"):
        tag = next((t for t in compilado.tags if _ident(t["direccion"]) == attr), None)
        donde = f" ({tag['direccion']})" if tag else ""
        if tag is not None and tag["sentido"] == "entrada":
            return f"«{ruta}» está en una entrada{donde}: su valor lo da el borne en cada scan"
        return (f"«{ruta}» está en una salida{donde}: la maneja el programa hacia el borne; escribe una "
                "variable de memoria que el programa copie a la salida")
    return f"«{ruta}» es CONSTANT: el programa la declaró de sólo lectura"


def _ident(texto: str) -> str | None:
    d = parsear_direccion(texto)
    return None if isinstance(d, str) else d.ident


def valor_para(tipo: str, valor, ruta: str):
    """El valor de una escritura en su tipo: BOOL true/false o 0/1; INT/DINT entero en su rango;
    REAL finito; TIME ms enteros. Un entero escrito como 50.0 vale; 50.5 en un INT, no."""
    if tipo not in ELEMENTALES:
        raise ValueError(f"«{ruta}» es {tipo}: no se escribe")
    if tipo == BOOL:
        if isinstance(valor, bool):
            return valor
        if isinstance(valor, int) and valor in (0, 1):
            return bool(valor)
        raise ValueError(f"«{ruta}» es BOOL: se escribe true/false o 0/1, llegó {valor!r}")
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ValueError(f"«{ruta}» es {tipo}: se escribe un número, llegó {valor!r}")
    if not math.isfinite(valor):
        raise ValueError(f"«{ruta}» es {tipo}: el valor tiene que ser finito, llegó {valor!r}")
    if tipo == REAL:
        return float(valor)
    if isinstance(valor, float):
        if not valor.is_integer():
            unidad = " de ms" if tipo == TIME else ""
            raise ValueError(f"«{ruta}» es {tipo}: se escribe un número entero{unidad}, llegó {valor!r}")
        valor = int(valor)
    lo, hi = RANGO[tipo]
    if not lo <= valor <= hi:
        raise ValueError(f"«{ruta}» es {tipo}: {valor} no cabe ({lo} … {hi})")
    return valor
