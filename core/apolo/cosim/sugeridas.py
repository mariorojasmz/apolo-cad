"""Aserciones SUGERIDAS a partir de lo que pasó en una corrida (plan V8.4 D10, F4).

Al guardar una sesión en vivo como escenario, la API la corre por lote y propone —no impone—
aserciones con lo que se observó, en la gramática de `aserciones.py`. Por cada ancla del
escenario (la PRIMERA vez que ocurre cada acción o evento, que es la que mira «desde …») se
mira el tramo hasta el ancla siguiente:
  - una velocidad que ARRANCA (`.rpm`, `.f_Hz` que sube): «-M1.rpm >= X dentro_de Δ desde
    pulsar -S1», con X al 90 % de lo alcanzado y Δ con margen (×1,25 + 0,1 s);
  - una que PARA (baja más de la mitad): «-M1.rpm <= Y dentro_de Δ desde presionar -S0», con Y
    al 10 % de lo que le quedaba por bajar;
  - un par que cae a cero (`.par_Nm`, el STO o el contactor que abre): «-M1.par_Nm == 0
    dentro_de Δ desde …»;
  - una protección que dispara (`.disparado` a true): «-Q1.disparado dentro_de Δ desde …».
Y al final, un contador del PLC (variable entera que sólo sube de a 1): «-K1.Main.cuenta == N
al_final». Las cifras se redondean HACIA el lado que pasa (umbral a 3 cifras, Δ a 0,1 s).

`sugerir` evalúa cada una contra la MISMA corrida (`veredicto.evaluar`) y devuelve sólo las que
pasan: una sugerencia que no se cumple sobre lo que la persona vio sería mentira. Sólo velocidades
positivas (un motor que gira al revés no se sugiere). Puro: stdlib, sobre el JSON del worker.
"""

from __future__ import annotations

import math

from .aserciones import AsercionInvalida, leer_asercion
from .veredicto import Lector, evaluar_una

MAX_SUGERIDAS = 12
#: Lo mínimo que tiene que cambiar una velocidad para que cuente como arranque o parada.
CAMBIO_MIN = {".rpm": 50.0, ".f_Hz": 2.0}
CERO = 1e-6


def _cifras(x: float, arriba: bool, n: int = 3) -> float:
    """`x` a `n` cifras significativas, redondeado hacia arriba o hacia abajo."""
    if x == 0 or not math.isfinite(x):
        return 0.0
    paso = 10.0 ** (math.floor(math.log10(abs(x))) - n + 1)
    q = (math.ceil if arriba else math.floor)(x / paso - (1e-9 if arriba else -1e-9))
    return round(q * paso, 9)


def _delta(dt: float) -> float:
    """El Δ de la ventana con margen: ×1,25 + 0,1 s, a 0,1 s hacia arriba."""
    return math.ceil((dt * 1.25 + 0.1) * 10.0 - 1e-9) / 10.0


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _anclas(esc, lec: Lector) -> list[tuple[str, float]]:
    """(texto del ancla, hora REAL) de la primera vez que ocurre cada acción y evento."""
    vistas, out = set(), []
    candidatas = [({"accion": a.accion, "dispositivo": a.dispositivo}, f"{a.accion} {a.dispositivo}")
                  for a in esc.acciones] + [({"evento": e.tipo}, e.tipo) for e in esc.eventos]
    for ancla, txt in candidatas:
        if txt in vistas:
            continue
        vistas.add(txt)
        t = lec.ancla(ancla)
        if t is not None:
            out.append((txt, t))
    return sorted(out, key=lambda x: x[1])


def _velocidad(n: str, minimo: float, lec: Lector, txt: str, t0: float, t1: float) -> str | None:
    pts = [(t, x) for t, x in lec.puntos(n, t0, t1) if _num(x)]
    v0 = lec.valor_en(n, t0)
    if not pts or not _num(v0):
        return None
    vmax, vmin = max(x for _, x in pts), min(x for _, x in pts)
    if vmax > 0 and vmax - v0 > max(minimo, 0.2 * vmax):
        x = _cifras(v0 + 0.9 * (vmax - v0), arriba=False)
        hit = next(t for t, v in pts if v >= x)
        return f"{n} >= {x:g} dentro_de {_delta(hit - t0):g} s desde {txt}"
    if v0 > 0 and v0 - vmin > max(minimo, 0.5 * v0):
        y = _cifras(vmin + 0.1 * (v0 - vmin), arriba=True)
        hit = next(t for t, v in pts if v <= y)
        return f"{n} <= {y:g} dentro_de {_delta(hit - t0):g} s desde {txt}"
    return None


def _par_a_cero(n: str, lec: Lector, txt: str, t0: float, t1: float) -> str | None:
    v0 = lec.valor_en(n, t0)
    if not _num(v0) or abs(v0) <= 1e-3:
        return None
    hit = next((t for t, x in lec.puntos(n, t0, t1) if _num(x) and abs(x) <= CERO), None)
    return None if hit is None else f"{n} == 0 dentro_de {_delta(hit - t0):g} s desde {txt}"


def _disparo(n: str, lec: Lector, txt: str, t0: float, t1: float) -> str | None:
    if lec.valor_en(n, t0) is True:
        return None
    hit = next((t for t, x in lec.disc.get(n, []) if x is True and t0 - 1e-9 <= t <= t1 + 1e-9), None)
    return None if hit is None else f"{n} dentro_de {_delta(hit - t0):g} s desde {txt}"


def _contadores(lec: Lector) -> list[str]:
    """Las variables del PLC («-K1.Main.cuenta») enteras que sólo suben de a 1 y terminan > 0."""
    out = []
    for n, cambios in sorted(lec.disc.items()):
        vals = [x for _, x in cambios]
        if n.count(".") < 2 or not vals or not all(_num(x) and float(x).is_integer() for x in vals):
            continue
        if vals[0] == 0 and vals[-1] > 0 and all(b - a == 1 for a, b in zip(vals, vals[1:])):
            out.append(f"{n} == {vals[-1]:g} al_final")
    return out


def candidatas(esc, lec: Lector) -> list[str]:
    """Las aserciones que se proponen, SIN verificar (`sugerir` las verifica)."""
    anclas = _anclas(esc, lec)
    nombres = lec.nombres()
    out: list[str] = []
    for i, (txt, t0) in enumerate(anclas):
        t1 = anclas[i + 1][1] if i + 1 < len(anclas) else lec.dur
        if t1 - t0 < 1e-9:
            continue  # otra ancla en el mismo instante: el tramo es de ella
        for n in nombres:
            sufijo = next((s for s in CAMBIO_MIN if n.endswith(s)), None)
            if sufijo and n in lec.an:
                s = _velocidad(n, CAMBIO_MIN[sufijo], lec, txt, t0, t1)
            elif n.endswith(".par_Nm") and n in lec.an:
                s = _par_a_cero(n, lec, txt, t0, t1)
            elif n.endswith(".disparado") and n in lec.disc:
                s = _disparo(n, lec, txt, t0, t1)
            else:
                s = None
            if s:
                out.append(s)
    return list(dict.fromkeys(out + _contadores(lec)))


def sugerir(esc, res: dict) -> list[dict]:
    """[{asercion, observado}] de las candidatas que PASAN sobre `res` (la corrida de `esc`, un
    `Escenario` leído), hasta `MAX_SUGERIDAS`. `observado` es el detalle del veredicto."""
    lec = Lector(res)
    out = []
    for k, txt in enumerate(candidatas(esc, lec)):
        try:
            a = leer_asercion(txt, k, esc.duracion_s, esc.acciones, esc.eventos)
        except AsercionInvalida:
            continue
        fila = evaluar_una(a, lec)
        if fila["pasa"]:
            out.append({"asercion": a["texto"], "observado": fila["detalle"]})
        if len(out) >= MAX_SUGERIDAS:
            break
    return out
