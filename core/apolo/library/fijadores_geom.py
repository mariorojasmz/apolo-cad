"""Reconoce la GEOMETRÍA de un fijador (plan acceso-de-herramienta, D1): dónde está su
hexágono, hacia dónde mira y qué llave pide.

Se lee del SÓLIDO, no del catálogo ni del comando: una tuerca de catálogo rotada, un perno de
`join_bolted` o una tuerca importada de STEP se reconocen igual. El hexágono son 3 pares de
caras planas paralelas cuyas normales están a 60° entre sí y son ⟂ a un eje común; la distancia
de cada par es el entrecaras `s`. Exterior (tuerca, cabeza hexagonal) o interior (hueco Allen)
se decide con un clasificador de sólido, nunca con el signo de `normal_at` (las caras de un
STEP vienen REVERSED: [kernel](../kernel/CLAUDE.md)).

Lo que no tiene hexágono reconocible devuelve None y el llamador lo declara «no evaluado»
(riesgo «falsos rojos con herraje modelado como caja» del plan).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_TOL_ANG = 0.02   # |cos| de tolerancia para paralelismo / 60°
_TOL_MM = 0.5     # tolerancia axial para «llega al extremo del sólido»
_MAX_LINEAS = 40  # un sólido con más direcciones de cara plana no es un fijador simple

Vec = tuple[float, float, float]


@dataclass(frozen=True)
class FijadorGeom:
    """Fijador reconocido. Coordenadas MUNDO (mm).

    - `tipo`: "tuerca" | "cabeza_hex" | "allen".
    - `base`: punto del eje en la cara de ASIENTO (t = 0). En la tuerca, una de sus dos caras
      (el asiento real lo decide el chequeo con los vecinos: `lado_conocido=False`). En el Allen,
      la cara SUPERIOR de la cabeza (por donde entra la llave).
    - `eje`: unitario hacia AFUERA (t creciente).
    - `altura`: alto del hexágono a lo largo del eje (m de la tuerca, alto de la cabeza).
    - `s`: entrecaras del hexágono (llave).
    - `planas`: las 3 normales de las caras del hexágono (⟂ `eje`), para orientar la boca.
    """

    tipo: str
    base: Vec
    eje: Vec
    altura: float
    s: float
    planas: tuple[Vec, Vec, Vec]
    lado_conocido: bool = True

    @property
    def r_esquinas(self) -> float:
        return self.s / math.sqrt(3.0)  # radio a las aristas del hexágono (s/2 / cos 30°)


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(a) -> Vec:
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def _add(a, b, k: float = 1.0) -> Vec:
    return (a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2])


def _canon(n) -> Vec:
    """Normal con signo canónico: dos caras paralelas comparten «línea» sin importar su signo."""
    for c in n:
        if abs(c) > 1e-6:
            return n if c > 0 else (-n[0], -n[1], -n[2])
    return n


def _caras_planas(solid) -> list[tuple[Vec, Vec, list[Vec]]]:
    """[(normal canónica, centro, vértices)] de las caras planas del sólido."""
    from apolo.kernel.topology import _kind

    out = []
    for f in solid.faces():
        if "PLANE" not in _kind(f):
            continue
        try:
            n = f.normal_at()
            c = f.center()
            vs = [(v.X, v.Y, v.Z) for v in f.vertices()]
        except Exception:  # noqa: BLE001
            continue
        out.append((_canon(_unit((n.X, n.Y, n.Z))), (c.X, c.Y, c.Z), vs))
    return out


def _lineas(caras) -> list[tuple[Vec, list]]:
    """Agrupa caras por línea normal (paralelas, sin signo)."""
    lineas: list[tuple[Vec, list]] = []
    for n, c, vs in caras:
        for ln, grupo in lineas:
            if abs(_dot(ln, n)) > 1 - _TOL_ANG * 0.05:
                grupo.append((c, vs))
                break
        else:
            lineas.append((n, [(c, vs)]))
    return lineas


def _par(ln, grupo) -> tuple[float, float] | None:
    """(offset menor, offset mayor) de las DOS caras paralelas de la línea; None si no hay
    exactamente dos planos distintos."""
    offs = sorted({round(_dot(ln, c), 3) for c, _ in grupo})
    if len(offs) != 2 or offs[1] - offs[0] < 1.0:
        return None
    return offs[0], offs[1]


def _hexagono(lineas):
    """Busca tres líneas a 60° ⟂ a un eje común con el mismo entrecaras.
    → (eje, (n1, n2, n3), s, [(línea, (lo, hi), grupo)×3]) o None."""
    cands = [(ln, g, _par(ln, g)) for ln, g in lineas]
    cands = [x for x in cands if x[2] is not None]
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            a, b = cands[i], cands[j]
            if abs(abs(_dot(a[0], b[0])) - 0.5) > _TOL_ANG:
                continue
            eje = _unit(_cross(a[0], b[0]))
            s = a[2][1] - a[2][0]
            if abs((b[2][1] - b[2][0]) - s) > 0.2:
                continue
            for k in range(len(cands)):
                if k in (i, j):
                    continue
                c = cands[k]
                if (abs(_dot(c[0], eje)) < _TOL_ANG
                        and abs(abs(_dot(c[0], a[0])) - 0.5) < _TOL_ANG
                        and abs(abs(_dot(c[0], b[0])) - 0.5) < _TOL_ANG
                        and abs((c[2][1] - c[2][0]) - s) < 0.2):
                    return eje, (a[0], b[0], c[0]), s, [a, b, c]
    return None


def _resolver_eje(n1, mid1, n2, mid2, eje) -> Vec:
    """Punto P con P·n1 = mid1, P·n2 = mid2, P·eje = 0 (Cramer 3×3)."""
    rows = (n1, n2, eje)
    rhs = (mid1, mid2, 0.0)

    def det(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))

    d = det(rows)
    out = []
    for col in range(3):
        m = [list(r) for r in rows]
        for r in range(3):
            m[r][col] = rhs[r]
        out.append(det(m) / d)
    return (out[0], out[1], out[2])


def _dentro(solid, p) -> bool:
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN

    cls = BRepClass3d_SolidClassifier(solid.wrapped, gp_Pnt(*p), 1e-6)
    return cls.State() == TopAbs_IN


def reconocer_fijador(solid) -> FijadorGeom | None:
    """El fijador del `solid` (un sólido build123d) o None si no tiene hexágono reconocible."""
    try:
        caras = _caras_planas(solid)
        lineas = _lineas(caras)
        if len(lineas) > _MAX_LINEAS:
            return None
        hexa = _hexagono(lineas)
        if hexa is None:
            return None
        eje, planas, s, trio = hexa
        n1, _, (lo1, hi1) = trio[0]
        n2, _, (lo2, hi2) = trio[1]
        centro0 = _resolver_eje(n1, (lo1 + hi1) / 2.0, n2, (lo2 + hi2) / 2.0, eje)
        # alcance axial del hexágono (vértices de sus caras laterales) y del sólido entero
        t_hex = [_dot(_add(v, centro0, -1.0), eje)
                 for _, grupo, _ in trio for _, vs in grupo for v in vs]
        t_sol = [_dot(_add((v.X, v.Y, v.Z), centro0, -1.0), eje) for v in solid.vertices()]
        t0, t1, s0, s1 = min(t_hex), max(t_hex), min(t_sol), max(t_sol)
        # ¿exterior o interior? un punto 0.5 mm MÁS ALLÁ de una cara lateral, radialmente
        cara_c = trio[0][1][0][0]
        radial = _add(cara_c, _add(centro0, eje, _dot(_add(cara_c, centro0, -1.0), eje)), -1.0)
        sonda = _add(cara_c, _unit(radial), 0.5)
        interior = _dentro(solid, sonda)
    except Exception:  # noqa: BLE001  — geometría rara: no evaluable, nunca rompe la puerta
        return None

    def punto(t: float) -> Vec:
        return _add(centro0, eje, t)

    menos = (-eje[0], -eje[1], -eje[2])
    if interior:  # hueco Allen: la llave entra por el extremo del sólido al que llega el hueco
        if s1 - t1 < _TOL_MM:
            return FijadorGeom("allen", punto(s1), eje, 0.0, s, planas)
        if t0 - s0 < _TOL_MM:
            return FijadorGeom("allen", punto(s0), menos, 0.0, s, planas)
        return None
    sale_menos, sale_mas = s0 < t0 - _TOL_MM, s1 > t1 + _TOL_MM
    if sale_menos and not sale_mas:  # vástago hacia −eje: la cabeza mira a +eje
        return FijadorGeom("cabeza_hex", punto(t0), eje, t1 - t0, s, planas)
    if sale_mas and not sale_menos:
        return FijadorGeom("cabeza_hex", punto(t1), menos, t1 - t0, s, planas)
    return FijadorGeom("tuerca", punto(t0), eje, t1 - t0, s, planas, lado_conocido=False)
