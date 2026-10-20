"""PLC virtual de Apolo (plan V8.3, F1): compilador propio de ST (IEC 61131-3) a Python
seguro y su runtime de scan con reloj virtual.

Puro: no conoce el documento, la API, el estado, la física ni la geometría (lo exige
`tests/test_capas_plc.py`). Uso:

    from apolo.plc import compilar, PLC
    prog = compilar(fuente_st, bornes={"I0.0", "Q0.0", ...})   # ErrorCompilacion si no
    plc = PLC(prog, ciclo_ms=10)
    plc.escribir_entrada("I0.0", True)
    salidas = plc.paso(t_ms)          # {"Q0.0": True, ...}
"""

from .compilador import Compilado, compilar
from .errores import ErrorCompilacion, ErrorST, FallaPLC
from .runtime import PLC, RUN, SIN_TENSION, STOP

__all__ = ["PLC", "RUN", "STOP", "SIN_TENSION", "Compilado", "ErrorCompilacion", "ErrorST",
           "FallaPLC", "compilar"]
