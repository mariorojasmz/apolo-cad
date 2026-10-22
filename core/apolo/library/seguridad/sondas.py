"""Sondas de alcance (ISO 13857) — la geometría pura de los rayos y el veredicto de cada uno.

Una sonda es un rayo RECTO que llega a un punto del peligro desde fuera de la máquina, en una
de las direcciones de una esfera de Fibonacci (determinista). El trazado contra los sólidos lo
hace `services/calidad_sondas.py` (OCCT); aquí sólo:

- `direcciones(n)`: la esfera de direcciones (unitarias, sentido de AVANCE del rayo);
- `origen(p, d, caja, z_piso)`: dónde arranca el rayo — fuera de la caja de la máquina (+50 mm)
  o, si viene de abajo, en el PISO (nadie mete el brazo desde bajo el suelo); devuelve también
  dónde entra al contorno, para medir la profundidad del alcance;
- `desplazamientos(ancho, d)`: los rayos paralelos de un haz de ese ancho (centro + 6 en
  hexágono, radio ancho/2);
- `veredicto(...)`: con los cruces ya medidos, ¿llega la mano?

Reglas del veredicto (declaradas):
1. El rayo central se BLOQUEA si su primer cruce es un sólido que no es el peligro → seguro.
2. Si llega (cruza primero el peligro o alcanza el punto por el aire), la profundidad es la del
   camino libre desde el contorno; > 850 mm → fuera de alcance.
3. Si pasa el haz de 20 mm (abertura > 20 mm: entra el brazo) → FALLA.
4. Si no, la abertura es la del haz más ancho que pasa; su `sr` sale de la tabla 4 y se mide desde
   la abertura (el último sólido que estrechó el haz siguiente) hasta el peligro: sr < requerida →
   FALLA.

Una recta sólo ve líneas de vista: lo que se alcanza DOBLANDO el brazo lo prueban `alcance.py`
(el campo de la muñeca) y `services/calidad_codo.py` (la mano), con este mismo `veredicto`.
"""

from __future__ import annotations

import math

from .iso13857 import ALCANCE_BRAZO_MM, CLASES_ABERTURA_MM, sr_requerida

MARGEN_ORIGEN_MM = 50.0
EPS = 1e-9


def direcciones(n: int) -> list[tuple[float, float, float]]:
    """`n` direcciones unitarias repartidas sobre la esfera (Fibonacci, sin azar)."""
    out = []
    oro = math.pi * (3.0 - math.sqrt(5.0))
    for i in range(n):
        z = 1.0 - 2.0 * (i + 0.5) / n
        r = math.sqrt(max(0.0, 1.0 - z * z))
        th = oro * i
        out.append((r * math.cos(th), r * math.sin(th), z))
    return out


def _salida(p, d, lo, hi) -> float:
    """s ≥ 0 en que p − s·d sale de la caja [lo, hi] (p adentro)."""
    s = math.inf
    for i in range(3):
        if abs(d[i]) < EPS:
            continue
        borde = lo[i] if d[i] > 0 else hi[i]  # yendo hacia −d
        s = min(s, (p[i] - borde) / d[i])
    return max(0.0, s)


def origen(p, d, caja, z_piso: float) -> dict:
    """{origen, t_objetivo, t_contorno, extra}: el rayo arranca en `origen`, llega a `p` en
    `t_objetivo`; la profundidad de un cruce en t es `t − t_contorno + extra` (`extra`: lo que el
    brazo recorre por debajo de la máquina desde su borde hasta el punto del piso)."""
    lo, hi = caja
    lo_m = [lo[i] - MARGEN_ORIGEN_MM for i in range(3)]
    hi_m = [hi[i] + MARGEN_ORIGEN_MM for i in range(3)]
    lo_m[2] = min(lo_m[2], z_piso)
    s_fuera = _salida(p, d, lo_m, hi_m)
    s_piso = (p[2] - z_piso) / d[2] if d[2] > EPS else math.inf
    if s_piso < s_fuera:
        o = tuple(p[i] - s_piso * d[i] for i in range(3))
        dx = max(0.0, min(o[0] - lo[0], hi[0] - o[0]))
        dy = max(0.0, min(o[1] - lo[1], hi[1] - o[1]))
        return {"origen": o, "t_objetivo": s_piso, "t_contorno": 0.0, "extra": min(dx, dy)}
    o = tuple(p[i] - s_fuera * d[i] for i in range(3))
    s_caja = _salida(p, d, lo, hi)
    return {"origen": o, "t_objetivo": s_fuera, "t_contorno": max(0.0, s_fuera - s_caja),
            "extra": 0.0}


def _perpendiculares(d):
    a = (1.0, 0.0, 0.0) if abs(d[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = (d[1] * a[2] - d[2] * a[1], d[2] * a[0] - d[0] * a[2], d[0] * a[1] - d[1] * a[0])
    n = math.sqrt(sum(c * c for c in u))
    u = tuple(c / n for c in u)
    v = (d[1] * u[2] - d[2] * u[1], d[2] * u[0] - d[0] * u[2], d[0] * u[1] - d[1] * u[0])
    return u, v


def desplazamientos(ancho: float, d) -> list[tuple[float, float, float]]:
    """Los 6 rayos laterales de un haz de `ancho` mm (hexágono de radio ancho/2, ⊥ a d)."""
    u, v = _perpendiculares(d)
    r = ancho / 2.0
    out = []
    for k in range(6):
        a = math.pi / 3.0 * k
        c, s = math.cos(a) * r, math.sin(a) * r
        out.append(tuple(c * u[i] + s * v[i] for i in range(3)))
    return out


def veredicto(t_llega: float | None, t_contorno: float, extra: float, haces) -> dict:
    """Veredicto de una sonda. `t_llega`: None si el rayo central se bloqueó; si no, el t en que
    toca el peligro. `haces(ancho)` → lista de t de bloqueo de sus rayos laterales (None = libre
    hasta `t_llega`), perezosa: sólo se pide lo necesario.

    → {alcanza, motivo, profundidad_mm?, abertura_mm?, sr_mm?, sr_requerida_mm?}"""
    if t_llega is None:
        return {"alcanza": False, "motivo": "bloqueado"}
    prof = t_llega - t_contorno + extra
    if prof > ALCANCE_BRAZO_MM:
        return {"alcanza": False, "motivo": "fuera de alcance", "profundidad_mm": round(prof, 1)}
    clases = sorted(CLASES_ABERTURA_MM, reverse=True)  # 20, 12, 10, 8, 6, 4
    falla_previa: list = []
    falla_ancho = None
    for ancho in clases:
        bloqueos = haces(ancho)
        if all(b is None for b in bloqueos):
            if falla_ancho is None:  # pasa el haz más ancho: entra el brazo
                return {"alcanza": True, "motivo": "abertura > 20 mm",
                        "profundidad_mm": round(prof, 1), "abertura_mm": f"> {ancho:g}",
                        "sr_mm": round(prof, 1), "sr_requerida_mm": ALCANCE_BRAZO_MM}
            break
        falla_previa, falla_ancho = bloqueos, ancho
    # abertura < falla_ancho: se mide desde el último sólido que estrechó ese haz
    t_abertura = max(b for b in falla_previa if b is not None)
    sr = t_llega - t_abertura
    req = sr_requerida(falla_ancho)
    return {"alcanza": sr < req, "motivo": f"abertura < {falla_ancho:g} mm",
            "profundidad_mm": round(prof, 1), "abertura_mm": f"< {falla_ancho:g}",
            "sr_mm": round(sr, 1), "sr_requerida_mm": req}
