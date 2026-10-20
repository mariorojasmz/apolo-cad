"""Bloques estándar de IEC 61131-3 (3.ª ed.): TON, TOF, TP, CTU, CTD, CTUD, R_TRIG, F_TRIG,
SR y RS.

Cada bloque es una clase con `__slots__` (el estado de la instancia, con los nombres que usa
el código generado: `v_in`, `v_q`…) y una función `(instancia, t_ms)` que lo evalúa con el
reloj VIRTUAL del scan (D9: nada de reloj de pared). Los campos con `_` son internos: ST no
los puede nombrar (el compilador sólo deja leer las entradas y salidas de la interfaz).

Decisiones donde la norma deja margen (criterio de diseño, como CODESYS):
- un temporizador lee `PT` en cada llamada; un `PT` negativo cuenta como 0;
- `F_TRIG` arranca con su memoria en TRUE: no da un pulso en el primer scan si CLK arranca en
  FALSE (`R_TRIG` sí lo da si CLK arranca en TRUE, como la norma);
- los contadores detectan el flanco como R_TRIG (memoria inicial FALSE) y se saturan en los
  límites de INT (PVmax = 32767, PVmin = -32768).
"""

from __future__ import annotations

_INT_MAX, _INT_MIN = 32767, -32768


class _Bloque:
    __slots__ = ()
    INICIAL: dict = {}

    def __init__(self) -> None:
        reiniciar(self)


def reiniciar(b) -> None:
    for k, v in type(b).INICIAL.items():
        setattr(b, k, v)


class TON(_Bloque):
    __slots__ = ("v_in", "v_pt", "v_q", "v_et", "_ini", "_corre")
    INICIAL = {"v_in": False, "v_pt": 0, "v_q": False, "v_et": 0, "_ini": 0, "_corre": False}


class TOF(_Bloque):
    __slots__ = ("v_in", "v_pt", "v_q", "v_et", "_ini", "_corre", "_prev")
    INICIAL = {"v_in": False, "v_pt": 0, "v_q": False, "v_et": 0, "_ini": 0, "_corre": False,
               "_prev": False}


class TP(_Bloque):
    __slots__ = ("v_in", "v_pt", "v_q", "v_et", "_ini", "_corre", "_prev")
    INICIAL = TOF.INICIAL


class CTU(_Bloque):
    __slots__ = ("v_cu", "v_r", "v_pv", "v_q", "v_cv", "_prev")
    INICIAL = {"v_cu": False, "v_r": False, "v_pv": 0, "v_q": False, "v_cv": 0, "_prev": False}


class CTD(_Bloque):
    __slots__ = ("v_cd", "v_ld", "v_pv", "v_q", "v_cv", "_prev")
    INICIAL = {"v_cd": False, "v_ld": False, "v_pv": 0, "v_q": False, "v_cv": 0, "_prev": False}


class CTUD(_Bloque):
    __slots__ = ("v_cu", "v_cd", "v_r", "v_ld", "v_pv", "v_qu", "v_qd", "v_cv", "_pu", "_pd")
    INICIAL = {"v_cu": False, "v_cd": False, "v_r": False, "v_ld": False, "v_pv": 0,
               "v_qu": False, "v_qd": False, "v_cv": 0, "_pu": False, "_pd": False}


class R_TRIG(_Bloque):
    __slots__ = ("v_clk", "v_q", "_m")
    INICIAL = {"v_clk": False, "v_q": False, "_m": False}


class F_TRIG(_Bloque):
    __slots__ = ("v_clk", "v_q", "_m")
    INICIAL = {"v_clk": False, "v_q": False, "_m": True}


class SR(_Bloque):
    __slots__ = ("v_s1", "v_r", "v_q1")
    INICIAL = {"v_s1": False, "v_r": False, "v_q1": False}


class RS(_Bloque):
    __slots__ = ("v_s", "v_r1", "v_q1")
    INICIAL = {"v_s": False, "v_r1": False, "v_q1": False}


def ton(s: TON, t: int) -> None:
    """Retardo a la conexión: Q sube cuando IN lleva PT en TRUE; IN en FALSE lo repone."""
    if s.v_in:
        if not s._corre:
            s._corre = True
            s._ini = t
        pt = s.v_pt if s.v_pt > 0 else 0
        et = t - s._ini
        if et >= pt:
            s.v_et = pt
            s.v_q = True
        else:
            s.v_et = et
            s.v_q = False
    else:
        s._corre = False
        s.v_et = 0
        s.v_q = False


def tof(s: TOF, t: int) -> None:
    """Retardo a la desconexión: Q sigue en TRUE durante PT después de que IN baja."""
    if s.v_in:
        s.v_q = True
        s.v_et = 0
        s._corre = False
    else:
        if s._prev:
            s._corre = True
            s._ini = t
        if s._corre:
            pt = s.v_pt if s.v_pt > 0 else 0
            et = t - s._ini
            if et >= pt:
                s.v_et = pt
                s.v_q = False
                s._corre = False
            else:
                s.v_et = et
    s._prev = s.v_in


def tp(s: TP, t: int) -> None:
    """Pulso: un flanco de subida de IN da Q en TRUE durante PT; no se re-dispara en el pulso."""
    if s._corre:
        pt = s.v_pt if s.v_pt > 0 else 0
        et = t - s._ini
        if et >= pt:
            s.v_et = pt
            s.v_q = False
            s._corre = False
        else:
            s.v_et = et
    if not s._corre and s.v_in and not s._prev:
        s._ini = t
        s.v_et = 0
        if s.v_pt > 0:
            s._corre = True
            s.v_q = True
    if not s._corre and not s.v_in:
        s.v_et = 0
    s._prev = s.v_in


def ctu(s: CTU, t: int) -> None:
    flanco = s.v_cu and not s._prev
    s._prev = s.v_cu
    if s.v_r:
        s.v_cv = 0
    elif flanco and s.v_cv < _INT_MAX:
        s.v_cv += 1
    s.v_q = s.v_cv >= s.v_pv


def ctd(s: CTD, t: int) -> None:
    flanco = s.v_cd and not s._prev
    s._prev = s.v_cd
    if s.v_ld:
        s.v_cv = s.v_pv
    elif flanco and s.v_cv > _INT_MIN:
        s.v_cv -= 1
    s.v_q = s.v_cv <= 0


def ctud(s: CTUD, t: int) -> None:
    sube = s.v_cu and not s._pu
    baja = s.v_cd and not s._pd
    s._pu = s.v_cu
    s._pd = s.v_cd
    if s.v_r:
        s.v_cv = 0
    elif s.v_ld:
        s.v_cv = s.v_pv
    elif not (sube and baja):
        if sube and s.v_cv < _INT_MAX:
            s.v_cv += 1
        elif baja and s.v_cv > _INT_MIN:
            s.v_cv -= 1
    s.v_qu = s.v_cv >= s.v_pv
    s.v_qd = s.v_cv <= 0


def r_trig(s: R_TRIG, t: int) -> None:
    s.v_q = s.v_clk and not s._m
    s._m = s.v_clk


def f_trig(s: F_TRIG, t: int) -> None:
    s.v_q = (not s.v_clk) and (not s._m)
    s._m = not s.v_clk


def sr(s: SR, t: int) -> None:
    """Biestable con prioridad al SET."""
    s.v_q1 = s.v_s1 or (not s.v_r and s.v_q1)


def rs(s: RS, t: int) -> None:
    """Biestable con prioridad al RESET."""
    s.v_q1 = (not s.v_r1) and (s.v_s or s.v_q1)


#: clave del bloque → (clase de la instancia, nombre en el código, función).
BLOQUES = {
    "ton": (TON, "_b_ton", ton), "tof": (TOF, "_b_tof", tof), "tp": (TP, "_b_tp", tp),
    "ctu": (CTU, "_b_ctu", ctu), "ctd": (CTD, "_b_ctd", ctd), "ctud": (CTUD, "_b_ctud", ctud),
    "r_trig": (R_TRIG, "_b_r_trig", r_trig), "f_trig": (F_TRIG, "_b_f_trig", f_trig),
    "sr": (SR, "_b_sr", sr), "rs": (RS, "_b_rs", rs),
}
