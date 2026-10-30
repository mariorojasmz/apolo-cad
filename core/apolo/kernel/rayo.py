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


#: «¿Está dentro?» por paridad (plan maquinas-grandes, D2): dos rectas OBLICUAS (ninguna paralela
#: a un eje, a 45° ni a la otra: las caras de un modelo casi nunca las contienen) y la distancia
#: por debajo de la cual un corte es RASANTE (el punto está sobre la frontera o la recta roza una
#: arista): ahí decide el clasificador de OCCT.
_RECTAS = tuple(tuple(c / sum(x * x for x in d) ** 0.5 for c in d)
                for d in ((0.5373, 0.6930, 0.4806), (-0.6209, 0.3459, 0.7033)))
_RASANTE = 1e-4


class Rayos:
    """Tramos de material de un sólido a lo largo de rectas ARBITRARIAS (plan
    puerta-de-publicacion D3: el eje de un perno no tiene por qué ser un eje del mundo).

    Intersección recta-caras de OCCT (`IntCurvesFace_ShapeIntersector`, cargado UNA vez por
    sólido) y clasificación del punto medio de cada tramo entre cortes: dentro → material. Mucho
    más barato que la varilla booleana de `tramos_en_eje` cuando un mismo sólido se cruza con
    muchas rectas. Puro: no muta nada.

    La clasificación de un punto (`estado`, plan maquinas-grandes D2) cuenta los cortes de dos
    rectas oblicuas con el MISMO intersector: si las dos son limpias y coinciden, ésa es la
    respuesta; ante la menor duda, el `BRepClass3d_SolidClassifier` de siempre, cargado una vez
    por sólido (armarlo por consulta costaba ~0,1 s en una pieza de 250 caras)."""

    def __init__(self, solid) -> None:
        self.solid = solid
        self._inter = None
        self._clasif = None
        self._alcance = None
        self._orientado = None

    def _cargar(self):
        if self._inter is None:
            from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

            self._inter = IntCurvesFace_ShapeIntersector()
            self._inter.Load(self.solid.wrapped, 1e-6)
        return self._inter

    def _occt(self, punto):
        """El estado (`TopAbs_State`) que da el clasificador de OCCT con tolerancia 1e-6: el de
        siempre, cargado una vez. Lanza lo que lance OCCT."""
        from OCP.gp import gp_Pnt

        if self._clasif is None:
            from OCP.BRepClass3d import BRepClass3d_SolidClassifier

            c = BRepClass3d_SolidClassifier()
            c.Load(self.solid.wrapped)
            self._clasif = c
        self._clasif.Perform(gp_Pnt(*punto), 1e-6)
        return self._clasif.State()

    def _caja(self):
        """(centro, semidiagonal) de una caja que contiene al sólido (la holgada: sólo acota el
        largo de las rectas), o None."""
        if self._alcance is None:
            from OCP.Bnd import Bnd_Box
            from OCP.BRepBndLib import BRepBndLib

            bb = Bnd_Box()
            BRepBndLib.Add_s(self.solid.wrapped, bb, False)
            if bb.IsVoid():
                self._alcance = (None,)
            else:
                x0, y0, z0, x1, y1, z1 = bb.Get()
                c = ((x0 + x1) / 2.0, (y0 + y1) / 2.0, (z0 + z1) / 2.0)
                r = 0.5 * ((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2) ** 0.5
                self._alcance = (c, r)
        return None if self._alcance[0] is None else self._alcance

    def _voto(self, punto, d, largo: float):
        """La paridad de la recta `punto + t·d`, t ∈ [−largo, largo]: (cortes, dentro) si es
        limpia, None si duda. Limpia = ningún corte sobre la frontera de su cara (arista,
        vértice), tangente ni a < `_RASANTE` del punto o de otro corte, y las transiciones de
        OCCT (con la orientación de cada cara) alternan entrar/salir empezando por entrar."""
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt
        from OCP.IntCurveSurface import IntCurveSurface_In, IntCurveSurface_Out
        from OCP.TopAbs import TopAbs_IN

        inter = self._cargar()
        inter.Perform(gp_Lin(gp_Pnt(*punto), gp_Dir(*d)), -largo, largo)
        if not inter.IsDone():
            return None
        cortes = []
        for i in range(1, inter.NbPnt() + 1):
            tr = inter.Transition(i)
            if inter.State(i) != TopAbs_IN or tr not in (IntCurveSurface_In, IntCurveSurface_Out):
                return None
            cortes.append((inter.WParameter(i), tr == IntCurveSurface_In))
        cortes.sort()
        dentro = False  # la recta nace fuera (antes de toda cara)
        for k, (t, entra) in enumerate(cortes):
            if abs(t) < _RASANTE or (k and t - cortes[k - 1][0] < _RASANTE):
                return None
            if entra != (k % 2 == 0):
                return None  # no alterna: un corte perdido o doble, o el sólido al revés
            if t < 0:
                dentro = entra
        if len(cortes) % 2:
            return None
        return len(cortes), dentro

    def _paridad(self, punto) -> bool | None:
        """True/False si las dos rectas son limpias y coinciden; None = duda (al clasificador)."""
        caja = self._caja()
        if caja is None:
            return None
        c, r = caja
        largo = sum((punto[k] - c[k]) ** 2 for k in range(3)) ** 0.5 + r + 1.0
        votos = []
        for d in _RECTAS:
            v = self._voto(punto, d, largo)
            if v is None:
                return None
            votos.append(v)
        if votos[0][1] != votos[1][1]:
            return None
        if votos[0][0] == 0 and votos[1][0] == 0 and not self._bien_orientado():
            return None  # sin cortes, sólo un sólido bien orientado deja el punto fuera
        return votos[0][1]

    def _bien_orientado(self) -> bool:
        """¿El sólido encierra lo de adentro (no está al revés)? La primera cara que cruza una
        recta por el centro de su caja es de ENTRADA; sin una recta limpia, no se sabe (False)."""
        if self._orientado is None:
            self._orientado = False
            caja = self._caja()
            if caja is not None:
                c, r = caja
                for d in _RECTAS:
                    v = self._voto(c, d, r + 1.0)
                    if v is not None and v[0]:
                        self._orientado = True
                        break
        return self._orientado

    def estado(self, punto):
        """El `TopAbs_State` de `punto` contra el sólido, el MISMO que el clasificador de OCCT
        (tolerancia 1e-6): por paridad si no hay duda, si no por el clasificador. Lanza lo que
        lance el clasificador (cada llamador decide su respaldo)."""
        from OCP.TopAbs import TopAbs_IN, TopAbs_OUT

        try:
            par = self._paridad(tuple(float(x) for x in punto))
        except Exception:  # noqa: BLE001 — el intersector falló: decide el clasificador
            par = None
        if par is None:
            return self._occt(punto)
        return TopAbs_IN if par else TopAbs_OUT

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
        """¿`punto` está DENTRO del sólido (lo que diría el clasificador de OCCT, `estado`)?
        False si falla."""
        from OCP.TopAbs import TopAbs_IN

        try:
            return self.estado(punto) == TopAbs_IN
        except Exception:  # noqa: BLE001
            return False

    def tramos(self, origen, direccion, t0: float, t1: float) -> list[tuple[float, float]]:
        """Tramos [a, b] (parámetro t sobre la recta `origen + t·direccion`, `direccion`
        unitaria) dentro del sólido entre `t0` y `t1`, ordenados; [] si falla OCCT."""
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
            p = tuple(origen[k] + m * direccion[k] for k in range(3))
            try:
                dentro = self.estado(p) == TopAbs_IN
            except Exception:  # noqa: BLE001
                continue
            if not dentro:
                continue
            if out and a <= out[-1][1] + _UNIR_MM:
                out[-1][1] = b
            else:
                out.append([a, b])
        return [(a, b) for a, b in out]
