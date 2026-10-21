"""Banco de los tests de guardas de la plantilla de rodillos (plan plantilla-rodillos-cadena F4).

- Sonda de dedo recta de Ø8 (ISO 13857: por una abertura de 8 mm el dedo entra hasta el
  nudillo): rayos de OCCT contra las piezas de una escena. `alcanza(rayos, p, d)` dice si la
  sonda que avanza desde `p` en la dirección `d` (un eje del mundo) toca una pieza PELIGROSA
  antes que cualquier otra: el rayo central llega primero a lo que gira y ninguno de 8 rayos
  sobre su contorno (r = 4 mm) choca antes con otra pieza.
- `interferencias_sin_tope`: las de `interference_report` sin su tope de `MAX_PAIRS` parejas
  candidatas (con todo lo declarado incluido, una máquina de 3 m pasa de 400).
"""

from __future__ import annotations

import math
from collections import defaultdict

from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

RADIO = 4.0
_CELDA = 40.0


class Rayos:
    def __init__(self, formas: dict, peligro) -> None:
        self.items = []
        for fid, forma in formas.items():
            inter = IntCurvesFace_ShapeIntersector()
            inter.Load(forma.wrapped, 1e-6)
            b = forma.bounding_box()
            self.items.append((bool(peligro(fid)), inter,
                               (b.min.X - 0.5, b.min.Y - 0.5, b.min.Z - 0.5),
                               (b.max.X + 0.5, b.max.Y + 0.5, b.max.Z + 0.5)))
        self._indices: dict[int, dict] = {}

    def _indice(self, eje: int) -> dict:
        """Piezas por celda del plano perpendicular al `eje` de los rayos."""
        if eje not in self._indices:
            i, j = (k for k in range(3) if k != eje)
            idx = defaultdict(list)
            for n, (_, _, lo, hi) in enumerate(self.items):
                for a in range(math.floor(lo[i] / _CELDA), math.floor(hi[i] / _CELDA) + 1):
                    for b in range(math.floor(lo[j] / _CELDA), math.floor(hi[j] / _CELDA) + 1):
                        idx[(a, b)].append(n)
            self._indices[eje] = idx
        return self._indices[eje]

    def primeros(self, p, d, hasta: float = math.inf) -> tuple:
        """(distancia a la primera pieza que no gira, a la primera que gira), None si no hay."""
        eje = max(range(3), key=lambda k: abs(d[k]))
        i, j = (k for k in range(3) if k != eje)
        cands = []
        for n in self._indice(eje).get((math.floor(p[i] / _CELDA), math.floor(p[j] / _CELDA)), ()):
            _, _, lo, hi = self.items[n]
            if not (lo[i] <= p[i] <= hi[i] and lo[j] <= p[j] <= hi[j]):
                continue
            t0 = ((lo[eje] if d[eje] > 0 else hi[eje]) - p[eje]) / d[eje]
            cands.append((t0, n))
        cands.sort()
        mejor = {False: None, True: None}
        linea = gp_Lin(gp_Pnt(*p), gp_Dir(*d))
        for t0, n in cands:
            tope = min([t for t in mejor.values() if t is not None] + [hasta])
            if t0 > tope:
                break
            peligro, inter, _, _ = self.items[n]
            inter.Perform(linea, 0.0, tope + 1.0 if tope < math.inf else 1e9)
            if inter.IsDone() and inter.NbPnt():
                t = min(inter.WParameter(k) for k in range(1, inter.NbPnt() + 1))
                if mejor[peligro] is None or t < mejor[peligro]:
                    mejor[peligro] = t
        return mejor[False], mejor[True]


def interferencias_sin_tope(formas: dict, excluir: set, focus: set | None = None) -> list:
    """[(a, b, volumen)] de las parejas cuyo sólido común pasa `MIN_VOLUME_MM3`, sin tope de
    parejas. `formas`: {fid: shape}; con `focus`, sólo las parejas que tocan esos ids."""
    from apolo.library.checks import MIN_VOLUME_MM3, _bboxes_overlap

    ids = [f for f in formas if f not in excluir]
    cajas = {f: formas[f].bounding_box() for f in ids}
    out = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            if focus is not None and a not in focus and b not in focus:
                continue
            if not _bboxes_overlap(cajas[a], cajas[b]):
                continue
            comun = formas[a] & formas[b]
            vol = float(comun.volume) if comun is not None else 0.0
            if vol > MIN_VOLUME_MM3:
                out.append((a, b, round(vol, 1)))
    return out


def alcanza(rayos: Rayos, p, d) -> bool:
    """La sonda (eje + dos anillos de 8 rayos, a 2 y a 4 mm) avanza hasta tocar algo: ¿lo
    primero que toca gira? Un rayo solo pasaría entre los rodillos de una cadena (4.8 mm)."""
    eje = max(range(3), key=lambda k: abs(d[k]))
    u, v = (k for k in range(3) if k != eje)
    puntos = [tuple(p)]
    for r in (RADIO / 2.0, RADIO):
        for k in range(8):
            q = list(p)
            q[u] += r * math.cos(k * math.pi / 4.0)
            q[v] += r * math.sin(k * math.pi / 4.0)
            puntos.append(tuple(q))
    t_b = t_h = math.inf
    for q in puntos:
        b, h = rayos.primeros(q, d, hasta=t_b)
        t_b = min(t_b, b if b is not None else math.inf)
        t_h = min(t_h, h if h is not None else math.inf)
    return t_h < t_b
