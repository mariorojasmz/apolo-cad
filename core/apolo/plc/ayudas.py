"""Funciones del runtime que el código generado llama por nombre (`_div`, `_real_int`…).

Son lo ÚNICO de Python que ve un programa ST: el espacio de nombres del `exec` no tiene
`__builtins__` (D6) y trae sólo esto, los bloques estándar y el estado. Cada una respeta la
norma donde la norma dice algo y lo marca como criterio de diseño donde no.
"""

from __future__ import annotations

import math

from .errores import FallaPLC

#: Iteraciones de bucle por ms de watchdog (criterio de diseño: ~0,1 µs por vuelta). El
#: watchdog es DETERMINISTA (D9): cuenta vueltas, no tiempo de pared.
ITER_POR_MS = 10_000


class Watchdog:
    """Presupuesto de vueltas de bucle que le queda al scan en curso."""

    __slots__ = ("resto", "limite_ms")

    def __init__(self) -> None:
        self.resto = 0
        self.limite_ms = 0


def falla_watchdog() -> None:
    raise FallaPLC("watchdog", "el scan superó el tiempo de vigilancia (watchdog): un bucle "
                   "no termina o da demasiadas vueltas")


def _envolver(x: int, bits: int) -> int:
    medio = 1 << (bits - 1)
    return ((x + medio) & ((1 << bits) - 1)) - medio


def div_entera(a: int, b: int) -> int:
    """División entera de ST: trunca hacia cero (Python redondea hacia abajo)."""
    if b == 0:
        raise FallaPLC("division", "división entera por cero")
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def modulo(a: int, b: int) -> int:
    """MOD de IEC 61131-3: el signo es el del dividendo y `x MOD 0 = 0` (tabla 29)."""
    if b == 0:
        return 0
    return a - div_entera(a, b) * b


def div_real(a: float, b: float) -> float:
    """División de REAL con la semántica IEEE 754 de la FPU de un PLC (±inf, nan)."""
    if b == 0:
        if a == 0 or a != a:
            return math.nan
        return math.copysign(math.inf, a) * math.copysign(1.0, b)
    return a / b


def potencia(a: float, b: float) -> float:
    try:
        r = float(a) ** float(b)
    except OverflowError:
        return math.inf
    except ZeroDivisionError:
        return math.inf
    return math.nan if isinstance(r, complex) else r


def _redondear(x: float, que: str) -> int:
    if not math.isfinite(x):
        raise FallaPLC("conversion", f"{que} de un valor no finito ({x})")
    r = math.floor(abs(x) + 0.5)       # al más cercano; el medio, lejos del cero
    return int(r if x >= 0 else -r)


def real_a_int(x: float) -> int:
    return _envolver(_redondear(x, "REAL_TO_INT"), 16)


def real_a_dint(x: float) -> int:
    return _envolver(_redondear(x, "REAL_TO_DINT"), 32)


def truncar(x: float) -> int:
    if not math.isfinite(x):
        raise FallaPLC("conversion", f"TRUNC de un valor no finito ({x})")
    return _envolver(int(x), 32)


def tiempo_por_real(t: int, k: float) -> int:
    return _envolver(_redondear(t * k, "TIME × REAL"), 32)


def indice(i: int, lo: int, hi: int) -> int:
    if lo <= i <= hi:
        return i - lo
    raise FallaPLC("indice", f"índice {i} fuera de ARRAY[{lo}..{hi}]")


def limitar(mn, x, mx):
    return mn if x < mn else (mx if x > mx else x)


def raiz(x: float) -> float:
    return math.sqrt(x) if x >= 0 else math.nan


def absoluto(x):
    return -x if x < 0 else x


def minimo(*xs):
    m = xs[0]
    for x in xs[1:]:
        if x < m:
            m = x
    return m


def maximo(*xs):
    m = xs[0]
    for x in xs[1:]:
        if x > m:
            m = x
    return m


#: Nombre en el código generado → función. El verificador sólo deja pasar estos nombres.
AYUDAS = {
    "_falla_wd": falla_watchdog, "_div": div_entera, "_mod": modulo, "_rdiv": div_real,
    "_expt": potencia, "_real_int": real_a_int, "_real_dint": real_a_dint, "_trunc": truncar,
    "_tmul": tiempo_por_real, "_ix": indice, "_limit": limitar, "_sqrt": raiz,
    "_abs": absoluto, "_min": minimo, "_max": maximo,
}
