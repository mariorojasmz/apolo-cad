"""Tipos del subconjunto de ST (D5) y sus reglas de compatibilidad.

Elementales: BOOL, INT (16 bits), DINT (32 bits), REAL y TIME (32 bits de ms). Conversiones
implícitas de IEC 61131-3 3.ª ed. (tabla 11) dentro del subconjunto: INT → DINT e INT → REAL;
todo lo demás pide su conversión explícita (`DINT_TO_REAL(…)`). Un literal entero se adapta
al tipo de destino si cabe (`LIT_INT`).

REAL se calcula en doble precisión (Python): la diferencia con el REAL de 32 bits de un PLC
no cambia ninguna prueba de máquina (criterio de diseño).
"""

from __future__ import annotations

from dataclasses import dataclass, field

BOOL, INT, DINT, REAL, TIME = "BOOL", "INT", "DINT", "REAL", "TIME"
LIT_INT = "LIT_INT"   # literal entero todavía sin tipo
ERROR = "ERROR"       # ya se reportó un error: compatible con todo, para no encadenar errores
ELEMENTALES = (BOOL, INT, DINT, REAL, TIME)
ENTEROS = (INT, DINT, LIT_INT)
NUMERICOS = (INT, DINT, REAL, LIT_INT)

RANGO = {INT: (-32768, 32767), DINT: (-2**31, 2**31 - 1), TIME: (-2**31, 2**31 - 1)}

_IMPLICITAS = {INT: (DINT, REAL), LIT_INT: (INT, DINT, REAL)}

#: Valor inicial por defecto de cada elemental.
DEFECTO = {BOOL: False, INT: 0, DINT: 0, REAL: 0.0, TIME: 0}


@dataclass(frozen=True)
class Arreglo:
    elem: str
    lo: int
    hi: int

    @property
    def n(self) -> int:
        return self.hi - self.lo + 1


@dataclass
class InterfazFB:
    """Entradas y salidas de un FUNCTION_BLOCK (estándar o del usuario)."""

    nombre: str                                   # escritura original
    py: str                                       # función del runtime o generada
    entradas: dict[str, tuple[str, str]] = field(default_factory=dict)  # clave → (orig, tipo)
    salidas: dict[str, tuple[str, str]] = field(default_factory=dict)
    estandar: bool = False

    def miembros(self) -> str:
        e = ", ".join(o for o, _ in self.entradas.values()) or "ninguna"
        s = ", ".join(o for o, _ in self.salidas.values()) or "ninguna"
        return f"entradas {e}; salidas {s}"


def nombre(t) -> str:
    if isinstance(t, Arreglo):
        return f"ARRAY[{t.lo}..{t.hi}] OF {t.elem}"
    if isinstance(t, InterfazFB):
        return t.nombre
    return "un entero" if t == LIT_INT else str(t)


def asignable(destino, origen) -> bool:
    if ERROR in (destino, origen) or destino == origen:
        return True
    return destino in _IMPLICITAS.get(origen, ())


def comun(a, b):
    """El tipo al que se llevan los dos operandos, o None si no se mezclan sin conversión."""
    if ERROR in (a, b):
        return ERROR
    if a == b:
        return a
    if b in _IMPLICITAS.get(a, ()):
        return b
    if a in _IMPLICITAS.get(b, ()):
        return a
    return None


def concreto(t):
    """El tipo con el que se guarda un resultado: un literal suelto es DINT."""
    return DINT if t == LIT_INT else t


def pista_conversion(destino, origen) -> str:
    """Qué conversión escribir para pasar de `origen` a `destino`, si existe."""
    if destino == TIME and origen == LIT_INT:
        return " Escribe un literal de tiempo, p. ej. T#500ms o T#2s."
    o = DINT if origen == LIT_INT else origen
    if (o, destino) in CONVERSIONES:
        return f" Convierte con {o}_TO_{destino}(…)."
    return ""


def pista_mezcla(a, b) -> str:
    """Qué conversión une dos operandos que no se mezclan solos."""
    for x, y in ((a, b), (b, a)):
        if x == REAL and y == DINT:
            return " Convierte con DINT_TO_REAL(…)."
        if x == TIME and y == LIT_INT:
            return " Escribe un literal de tiempo, p. ej. T#500ms o T#2s."
        if x == BOOL and y in (INT, DINT, LIT_INT, REAL):
            return " Convierte el BOOL con BOOL_TO_INT(…)."
    return ""


#: Conversiones explícitas `A_TO_B` del subconjunto → plantilla del código (`{0}` = argumento).
CONVERSIONES: dict[tuple[str, str], str] = {
    (BOOL, INT): "(1 if {0} else 0)", (BOOL, DINT): "(1 if {0} else 0)",
    (BOOL, REAL): "(1.0 if {0} else 0.0)",
    (INT, BOOL): "({0} != 0)", (DINT, BOOL): "({0} != 0)",
    (INT, DINT): "{0}", (DINT, INT): "W16", (INT, REAL): "({0} + 0.0)",
    (DINT, REAL): "({0} + 0.0)", (REAL, INT): "_real_int({0})", (REAL, DINT): "_real_dint({0})",
    (TIME, DINT): "{0}", (DINT, TIME): "{0}", (TIME, INT): "W16", (INT, TIME): "{0}",
    (TIME, REAL): "({0} + 0.0)", (REAL, TIME): "_real_dint({0})",
}

#: Funciones estándar del subconjunto (además de las conversiones).
FUNCIONES_ESTANDAR = ("ABS", "SQRT", "MIN", "MAX", "LIMIT", "SEL", "TRUNC", "EXPT")


def _fb(nombre_: str, py: str, entradas: dict, salidas: dict) -> InterfazFB:
    return InterfazFB(nombre_, py, {k.lower(): (k, t) for k, t in entradas.items()},
                      {k.lower(): (k, t) for k, t in salidas.items()}, estandar=True)


#: Los bloques estándar de V8.3 (IEC 61131-3, tabla 43–46). Código: `bloques.py`.
FB_ESTANDAR: dict[str, InterfazFB] = {
    "ton": _fb("TON", "_b_ton", {"IN": BOOL, "PT": TIME}, {"Q": BOOL, "ET": TIME}),
    "tof": _fb("TOF", "_b_tof", {"IN": BOOL, "PT": TIME}, {"Q": BOOL, "ET": TIME}),
    "tp": _fb("TP", "_b_tp", {"IN": BOOL, "PT": TIME}, {"Q": BOOL, "ET": TIME}),
    "ctu": _fb("CTU", "_b_ctu", {"CU": BOOL, "R": BOOL, "PV": INT}, {"Q": BOOL, "CV": INT}),
    "ctd": _fb("CTD", "_b_ctd", {"CD": BOOL, "LD": BOOL, "PV": INT}, {"Q": BOOL, "CV": INT}),
    "ctud": _fb("CTUD", "_b_ctud", {"CU": BOOL, "CD": BOOL, "R": BOOL, "LD": BOOL, "PV": INT},
                {"QU": BOOL, "QD": BOOL, "CV": INT}),
    "r_trig": _fb("R_TRIG", "_b_r_trig", {"CLK": BOOL}, {"Q": BOOL}),
    "f_trig": _fb("F_TRIG", "_b_f_trig", {"CLK": BOOL}, {"Q": BOOL}),
    "sr": _fb("SR", "_b_sr", {"S1": BOOL, "R": BOOL}, {"Q1": BOOL}),
    "rs": _fb("RS", "_b_rs", {"S": BOOL, "R1": BOOL}, {"Q1": BOOL}),
}
