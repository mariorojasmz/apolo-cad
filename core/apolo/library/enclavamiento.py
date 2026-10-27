"""¿Entra la lengüeta en su interruptor de resguardo? (plan mandos-de-seguridad, F2b). PURO.

Un interruptor de resguardo con actuador separado (ISO 14119 tipo 2, `RESG-2NC`) sólo cierra sus
NC con la lengüeta (`RESG-LENGUETA`) adentro de su ranura. La co-simulación toma el contacto
como cerrado sin mirar la geometría: si en el 3D la lengüeta queda fuera, la máquina real no
arranca, o el operario puentea el enclavamiento (medido en dos máquinas el 2026-10-27).

Geometría: SÓLO de las anclas del builder `interruptor_resguardo` (en mundo, ya posadas por el
llamador) y de las cotas del mismo builder (`RESG_RANURA`, `RESG_LENGUETA`), nunca del bbox:
- cuerpo: `ranura` = el centro de la BOCA, eje = el sentido en que entra la lengüeta; el
  `fijacion_1 → fijacion_2` es el +Y local (hacia la cabeza). Con ellos sale el marco de la
  ranura: ancho (`RESG_RANURA[0]`) por el X local, canto (`[1]`) por el Y local, fondo (`[2]`).
- lengüeta: `punta` = el centro de la punta, eje = hacia donde apunta; `fijacion_1 → fijacion_2`
  es su +X local (el ancho, `RESG_LENGUETA[0]`); el canto (`[1]`) va por Y = Z × X.

Criterio (`insercion`):
- profundidad = (punta − boca) · eje de la ranura;
- la sección de la lengüeta (sus 4 esquinas en la punta y donde cruza la boca) cabe en la de la
  ranura: la tolerancia de alineación es la holgura del propio par (±1 mm de ancho, ±0,5 mm de
  canto), más allá la lengüeta choca con el cabezal; con la lengüeta inclinada lo dicen las
  esquinas de la boca;
- `insercion_min_mm` de la ficha del interruptor ≤ profundidad ≤ fondo de la ranura (más
  adentro, la punta choca con el fondo).
«Fuera» (resguardo abierto): la punta no pasó la boca o ninguna esquina de la punta cae en la
sección de la ranura.
"""

from __future__ import annotations

import math

from .builders_mandos import RESG_LENGUETA, RESG_RANURA

#: Tolerancia numérica de las comparaciones (mm): el redondeo de las anclas posadas.
EPS_MM = 0.05

INSERTADA, CORTA, FUERA, DESALINEADA, AL_FONDO = (
    "insertada", "corta", "fuera", "desalineada", "choca con el fondo")


def _sub(a, b):
    return tuple(a[i] - b[i] for i in range(3))


def _add(a, b, k=1.0):
    return tuple(a[i] + k * b[i] for i in range(3))


def _dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v):
    n = math.sqrt(_dot(v, v))
    if n < 1e-9:
        raise ValueError("vector nulo")
    return tuple(x / n for x in v)


def _ancla(anclas: dict, nombre: str):
    a = anclas[nombre]
    return tuple(float(x) for x in a["origin"]), _unit(tuple(float(x) for x in a["axis"]))


def marco_ranura(anclas: dict) -> tuple | None:
    """(boca, eje de entrada, X del ancho, Y del canto) de la ranura, o None si faltan anclas."""
    try:
        boca, ez = _ancla(anclas, "ranura")
        (f1, _), (f2, _) = _ancla(anclas, "fijacion_1"), _ancla(anclas, "fijacion_2")
        ey = _unit(_sub(f2, f1))
        return boca, ez, _unit(_cross(ey, tuple(-x for x in ez))), ey
    except (KeyError, TypeError, ValueError):
        return None


def marco_lengueta(anclas: dict) -> tuple | None:
    """(punta, hacia donde apunta, X del ancho, Y del canto) de la lengüeta, o None."""
    try:
        punta, t = _ancla(anclas, "punta")
        (f1, _), (f2, _) = _ancla(anclas, "fijacion_1"), _ancla(anclas, "fijacion_2")
        wx = _unit(_sub(f2, f1))
        return punta, t, wx, _unit(_cross(t, wx))
    except (KeyError, TypeError, ValueError):
        return None


def _esquinas(centro, wx, wy):
    a, b = RESG_LENGUETA[0] / 2, RESG_LENGUETA[1] / 2
    return [_add(_add(centro, wx, sx * a), wy, sy * b) for sx in (-1, 1) for sy in (-1, 1)]


def _en_seccion(p, boca, ex, ey, eps=EPS_MM) -> tuple[float, float]:
    """Holgura (mm) del punto a los lados de la ranura por ancho y por canto (< 0: fuera)."""
    r = _sub(p, boca)
    return RESG_RANURA[0] / 2 - abs(_dot(r, ex)) + eps, RESG_RANURA[1] / 2 - abs(_dot(r, ey)) + eps


def insercion(ranura: tuple, lengueta: tuple, insercion_min_mm: float) -> dict:
    """Cómo queda la lengüeta en la ranura: `{estado, profundidad_mm, holgura_ancho_mm,
    holgura_canto_mm, minimo_mm, fondo_mm}` (holguras: la menor de las esquinas, negativa si
    alguna se sale de la sección)."""
    boca, ez, ex, ey = ranura
    punta, t, wx, wy = lengueta
    fondo = RESG_RANURA[2]
    prof = _dot(_sub(punta, boca), ez)
    esquinas = _esquinas(punta, wx, wy)
    coseno = _dot(t, ez)
    if prof > 0 and coseno > 1e-6:  # donde la lengüeta cruza la boca
        esquinas += _esquinas(_add(punta, t, -prof / coseno), wx, wy)
    holguras = [_en_seccion(p, boca, ex, ey) for p in esquinas]
    hx = min(h[0] for h in holguras) - EPS_MM
    hy = min(h[1] for h in holguras) - EPS_MM
    cabe = coseno > 0.5 and all(h[0] >= 0 and h[1] >= 0 for h in holguras)
    if prof <= EPS_MM:
        estado = FUERA
    elif not cabe:
        estado = DESALINEADA
    elif max(_dot(_sub(p, boca), ez) for p in esquinas[:4]) > fondo + EPS_MM:
        estado = AL_FONDO
    elif prof < insercion_min_mm - EPS_MM:
        estado = CORTA
    else:
        estado = INSERTADA
    return {"estado": estado, "profundidad_mm": round(prof, 2), "holgura_ancho_mm": round(hx, 2),
            "holgura_canto_mm": round(hy, 2), "minimo_mm": float(insercion_min_mm),
            "fondo_mm": fondo}


def fuera(ranura: tuple, lengueta: tuple) -> bool:
    """¿La lengüeta está fuera de la ranura? (la punta no pasó la boca o ninguna esquina de la
    punta cae en la sección de la ranura)."""
    boca, ez, ex, ey = ranura
    punta, _t, wx, wy = lengueta
    if _dot(_sub(punta, boca), ez) <= EPS_MM:
        return True
    return not any(min(_en_seccion(p, boca, ex, ey, eps=0.0)) > 0 for p in _esquinas(punta, wx, wy))


def texto(r: dict) -> str:
    """El estado de una inserción en palabras, con sus cifras."""
    p, m, f = r["profundidad_mm"], r["minimo_mm"], r["fondo_mm"]
    if r["estado"] == FUERA:
        return (f"la punta queda {abs(p):.1f} mm fuera de la boca de la ranura" if p < -EPS_MM
                else "la punta queda en la boca de la ranura, sin entrar")
    if r["estado"] == DESALINEADA:
        return (f"entra {p:.1f} mm pero no cabe en la ranura de {RESG_RANURA[0]:g}×{RESG_RANURA[1]:g} "
                f"(holgura de ancho {r['holgura_ancho_mm']:.1f} mm, de canto {r['holgura_canto_mm']:.1f} mm; "
                "negativa = se sale): choca con el cabezal")
    if r["estado"] == AL_FONDO:
        return f"entra {p:.1f} mm, más que el fondo de la ranura ({f:g} mm): choca con el fondo"
    if r["estado"] == CORTA:
        return f"entra {p:.1f} mm de los {m:g} mm que pide el interruptor"
    return f"entra {p:.1f} mm (pide {m:g}–{f:g} mm)"
