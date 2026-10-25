"""Las líneas de un esquema neumático (plan V8.9 F5, D11): cada LÍNEA del circuito (puertos
unidos por tubos) se dibuja como un bus ortogonal.

Regla: cada puerto baja (o sube) en vertical hasta un CARRIL horizontal de su línea, y el carril
une los extremos. El carril va en la franja libre entre las filas de símbolos: por encima de todos
los puertos que miran hacia arriba y por debajo de todos los que miran hacia abajo de esa línea
(el aire sube: fuente abajo, válvulas al medio, cilindros arriba, ISO 1219-2). Dos carriles que se
pisarían en la misma franja se separan. Un cruce sin unión queda sin punto; una derivación (tres
o más brazos en un punto) lleva el punto de unión (ISO 1219-1).

Si la franja no existe (una topología fuera de la composición por reglas), el carril va por
encima de todo y la ruta se declara en `avisos`: nunca se omite una conexión.
"""

from __future__ import annotations

from ..esquema import conductor, punto_union
from ..sheet import SheetModel
from .trazo import ARRIBA, Puerto

PASO_CARRIL = 1.8  # separación entre carriles de una misma franja (mm, criterio)
HOLGURA_X = 1.0
MARGEN_FRANJA = 1.0


def _libre(ocupados, y: float, xa: float, xb: float) -> bool:
    return not any(abs(y - yo) < PASO_CARRIL * 0.66 and xa < x1 + HOLGURA_X and x0 < xb + HOLGURA_X
                   for yo, x0, x1 in ocupados)


def _carril(ocupados, lo: float, hi: float, xa: float, xb: float) -> float | None:
    medio = (lo + hi) / 2
    k = 0
    while True:
        for y in ((medio,) if k == 0 else (medio + k * PASO_CARRIL, medio - k * PASO_CARRIL)):
            if lo + MARGEN_FRANJA <= y <= hi - MARGEN_FRANJA and _libre(ocupados, y, xa, xb):
                return y
        k += 1
        if medio - k * PASO_CARRIL < lo and medio + k * PASO_CARRIL > hi:
            return None


def _unicos(puertos: list[Puerto]) -> list[Puerto]:
    vistos, out = set(), []
    for p in puertos:
        k = (round(p.x, 3), round(p.y, 3))
        if k not in vistos:
            vistos.add(k)
            out.append(p)
    return out


def rutear(m: SheetModel, lineas: list[tuple[str, list[Puerto]]], *, techo: float,
           trazos: dict | None = None) -> list[str]:
    """Dibuja cada línea (nombre, puertos). `techo`: la y por encima de todos los símbolos (para
    una ruta forzada). Devuelve los avisos. `trazos`, si se pasa, recibe {nombre: índices en
    `m.lines` de sus tramos}: el panel del visor tiñe cada línea por su presión (V8.9 F6)."""
    avisos: list[str] = []
    ocupados: list[tuple[float, float, float]] = []
    pendientes = []
    for nombre, pts in lineas:
        pts = _unicos(pts)
        if len(pts) < 2:
            continue
        arriba = [p.y for p in pts if p.dir == ARRIBA]
        abajo = [p.y for p in pts if p.dir != ARRIBA]
        xa, xb = min(p.x for p in pts), max(p.x for p in pts)
        if arriba and abajo:
            lo, hi = max(arriba), min(abajo)
        elif arriba:
            lo, hi = max(arriba), max(arriba) + 10.0
        else:
            lo, hi = min(abajo) - 10.0, min(abajo)
        pendientes.append((hi - lo, nombre, pts, lo, hi, xa, xb))
    # las franjas angostas primero: tienen menos lugar
    for _, nombre, pts, lo, hi, xa, xb in sorted(pendientes, key=lambda t: (t[0], t[5], t[1])):
        y = _carril(ocupados, lo, hi, xa, xb) if hi - lo > 2 * MARGEN_FRANJA else None
        if y is None:
            y = techo
            while not _libre(ocupados, y, xa, xb):
                y += PASO_CARRIL
            avisos.append(f"la línea {nombre} no cabe en la franja entre sus aparatos: va por encima")
        ocupados.append((y, xa, xb))
        n0 = len(m.lines)
        _dibujar(m, pts, y, xa, xb)
        if trazos is not None:
            trazos[nombre] = list(range(n0, len(m.lines)))
    return avisos


def _dibujar(m: SheetModel, pts: list[Puerto], y: float, xa: float, xb: float) -> None:
    for p in pts:
        if abs(p.y - y) > 1e-6:
            conductor(m, p.x, p.y, p.x, y)
    if xb - xa > 1e-6:
        conductor(m, xa, y, xb, y)
    brazos: dict[float, set] = {}
    for p in pts:
        x = round(p.x, 3)
        b = brazos.setdefault(x, set())
        if p.y > y + 1e-6:
            b.add("arriba")
        elif p.y < y - 1e-6:
            b.add("abajo")
        if x > xa + 1e-6:
            b.add("izq")
        if x < xb - 1e-6:
            b.add("der")
    for x, b in brazos.items():
        if len(b) >= 3:
            punto_union(m, x, y)
