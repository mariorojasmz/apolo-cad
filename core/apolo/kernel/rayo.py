"""Tramos de MATERIAL a lo largo de una recta paralela a un eje del mundo.

Lo usa `join_bolted` (plan union-en-perfil-hueco, D1/D2): el largo del perno sale de lo que
el perno ATRAVIESA de verdad por el centro del taladro (el alma de 3 mm de una C, no los 50 mm
de su caja) y un perfil cerrado se reconoce porque la recta, tras salir de la primera pared,
vuelve a entrar en la MISMA pieza (la pared de enfrente del tubo).

Se mide con una varilla de sección 0,1 × 0,1 mm intersecada con el sólido (booleana de OCCT):
cada sólido del resultado es un tramo. Es robusto frente a caras curvas o inclinadas y no
depende del signo de las normales de un STEP. Puro: no muta nada.
"""

from __future__ import annotations

_LADO_VARILLA = 0.1  # mm: sección de la varilla de medición
_UNIR_MM = 1e-3      # dos tramos a menos de esto son uno (cara compartida de un compound)


def tramos_en_eje(shape, eje: int, punto, t0: float, t1: float) -> list[tuple[float, float]]:
    """Tramos [a, b] (coordenada `eje` del mundo: 0 = X, 1 = Y, 2 = Z), ordenados, donde la
    recta paralela a `eje` que pasa por `punto` está DENTRO de `shape`, entre `t0` y `t1`.
    [] si no la cruza (o si la booleana falla: el llamador lo trata como «sin material»)."""
    from build123d import Box, Pos

    lo, hi = min(t0, t1), max(t0, t1)
    if hi - lo <= 0:
        return []
    centro = [float(punto[0]), float(punto[1]), float(punto[2])]
    centro[eje] = (lo + hi) / 2.0
    medidas = [_LADO_VARILLA] * 3
    medidas[eje] = hi - lo
    varilla = Pos(*centro) * Box(*medidas)
    try:
        corte = shape & varilla
        solidos = list(corte.solids()) if corte is not None else []
    except Exception:  # noqa: BLE001 — booleana fallida = sin dato, nunca rompe al llamador
        return []
    crudos = []
    for s in solidos:
        try:
            if float(s.volume) <= 0:
                continue
            bb = s.bounding_box()
        except Exception:  # noqa: BLE001
            continue
        crudos.append(((bb.min.X, bb.min.Y, bb.min.Z)[eje], (bb.max.X, bb.max.Y, bb.max.Z)[eje]))
    crudos.sort()
    out: list[list[float]] = []
    for a, b in crudos:
        if out and a <= out[-1][1] + _UNIR_MM:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return [(a, b) for a, b in out]


class Rayos:
    """Tramos de material de un sólido a lo largo de rectas ARBITRARIAS (plan
    puerta-de-publicacion D3: el eje de un perno no tiene por qué ser un eje del mundo).

    Intersección recta-caras de OCCT (`IntCurvesFace_ShapeIntersector`, cargado UNA vez por
    sólido) y clasificación del punto medio de cada tramo entre cortes: dentro → material. Mucho
    más barato que la varilla booleana de `tramos_en_eje` cuando un mismo sólido se cruza con
    muchas rectas. Puro: no muta nada."""

    def __init__(self, solid) -> None:
        self.solid = solid
        self._inter = None

    def _cargar(self):
        if self._inter is None:
            from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

            self._inter = IntCurvesFace_ShapeIntersector()
            self._inter.Load(self.solid.wrapped, 1e-6)
        return self._inter

    def cortes(self, origen, direccion, t0: float, t1: float) -> list[float]:
        """Parámetros t (ordenados, sin repetir a 1e-4) donde la recta corta una cara del
        sólido entre `t0` y `t1`, SIN clasificar: quien sabe de qué lado arranca (un punto en el
        hueco de un taladro, uno dentro del material) lee la paridad y se ahorra el
        clasificador por tramo de `tramos`. [] si falla OCCT."""
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

        try:
            inter = self._cargar()
            inter.Perform(gp_Lin(gp_Pnt(*origen), gp_Dir(*direccion)), t0, t1)
            if not inter.IsDone():
                return []
            ts = sorted(inter.WParameter(i) for i in range(1, inter.NbPnt() + 1))
        except Exception:  # noqa: BLE001 — OCCT caprichoso: sin dato
            return []
        out: list[float] = []
        for t in ts:
            if not out or t - out[-1] > 1e-4:
                out.append(t)
        return out

    def dentro(self, punto) -> bool:
        """¿`punto` está DENTRO del sólido (clasificador de OCCT)? False si falla."""
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_IN

        try:
            return BRepClass3d_SolidClassifier(self.solid.wrapped, gp_Pnt(*punto),
                                               1e-6).State() == TopAbs_IN
        except Exception:  # noqa: BLE001
            return False

    def tramos(self, origen, direccion, t0: float, t1: float) -> list[tuple[float, float]]:
        """Tramos [a, b] (parámetro t sobre la recta `origen + t·direccion`, `direccion`
        unitaria) dentro del sólido entre `t0` y `t1`, ordenados; [] si falla OCCT."""
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
        from OCP.TopAbs import TopAbs_IN

        try:
            inter = self._cargar()
            inter.Perform(gp_Lin(gp_Pnt(*origen), gp_Dir(*direccion)), t0, t1)
            if not inter.IsDone():
                return []
            cortes = sorted({round(inter.WParameter(i), 6) for i in range(1, inter.NbPnt() + 1)})
        except Exception:  # noqa: BLE001 — OCCT caprichoso: sin dato, nunca rompe al llamador
            return []
        bordes = [t0, *[c for c in cortes if t0 < c < t1], t1]
        out: list[list[float]] = []
        for a, b in zip(bordes, bordes[1:]):
            if b - a <= _UNIR_MM:
                continue
            m = (a + b) / 2.0
            p = gp_Pnt(*(origen[k] + m * direccion[k] for k in range(3)))
            try:
                dentro = BRepClass3d_SolidClassifier(self.solid.wrapped, p, 1e-6).State() == TopAbs_IN
            except Exception:  # noqa: BLE001
                continue
            if not dentro:
                continue
            if out and a <= out[-1][1] + _UNIR_MM:
                out[-1][1] = b
            else:
                out.append([a, b])
        return [(a, b) for a, b in out]
