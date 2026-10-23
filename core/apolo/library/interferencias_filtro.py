"""El prefiltro de `checks.interference_report` (F6 de puerta-de-publicacion): qué parejas de
sólidos PUEDEN interferir y merecen la booleana de OCCT. Todo descarte es EXACTO (nunca deja
fuera una interferencia de más de `MIN_VOLUME_MM3`): así el chequeo global escala a máquinas de
~1000 piezas sin truncarse por las parejas que sólo comparten caja.

1. **Barrido por cajas** (`pares_por_caja`): las parejas cuyas cajas se solapan, ordenadas por su
   x mínima y barridas (O(n log n + k) en vez de comparar las n² parejas). Salen en el orden
   estable de la escena (i < j), el de siempre: la paginación `desde` no cambia.
2. **Volumen de la caja común**: A∩B cabe en la intersección de las dos cajas; si ésa no llega a
   `MIN_VOLUME_MM3` (un apoyo cara a cara, alineado), la interferencia tampoco.
3. **Caras en la zona común** (`Filtro.puede_interferir`): si A∩B tiene volumen y B no está
   entera dentro de A, la frontera de A pasa por A∩B, que está dentro de la caja común R; o sea,
   alguna cara de A tiene su caja dentro de R. Lo mismo con B. Una pareja en la que A no tiene
   caras en R y ningún sólido de B está dentro de A (un vértice clasificado contra A) no
   interfiere: la bandeja en U cuya caja abarca todos los rodillos, el bastidor que encierra un
   motor. Ante cualquier error de OCCT, la pareja sigue (a la booleana).
"""

from __future__ import annotations

MARGEN = 0.01


def caja(bb) -> tuple:
    return (bb.min.X, bb.min.Y, bb.min.Z), (bb.max.X, bb.max.Y, bb.max.Z)


def _solapan(a, b, margen: float = MARGEN) -> bool:
    return all(a[0][i] <= b[1][i] + margen and b[0][i] <= a[1][i] + margen for i in range(3))


def comun(a, b) -> tuple:
    """La caja común de dos cajas que se solapan (agrandada en `MARGEN`)."""
    return (tuple(max(a[0][i], b[0][i]) - MARGEN for i in range(3)),
            tuple(min(a[1][i], b[1][i]) + MARGEN for i in range(3)))


def volumen_comun(a, b) -> float:
    v = 1.0
    for i in range(3):
        v *= max(min(a[1][i], b[1][i]) - max(a[0][i], b[0][i]), 0.0)
    return v


def pares_por_caja(cajas: list) -> list[tuple[int, int]]:
    """(i, j), i < j, de las cajas que se solapan (con `MARGEN`), en orden (i, j)."""
    orden = sorted(range(len(cajas)), key=lambda i: cajas[i][0][0])
    activos: list[int] = []
    out = []
    for i in orden:
        x0 = cajas[i][0][0]
        activos = [j for j in activos if cajas[j][1][0] + MARGEN >= x0]
        out.extend((min(i, j), max(i, j)) for j in activos if _solapan(cajas[i], cajas[j]))
        activos.append(i)
    out.sort()
    return out


class Filtro:
    """Cachea por forma sus cajas de cara, sus sólidos y un vértice de cada uno. La caché vive lo
    que dura UN reporte y, como toda caché por `id(shape)`, guarda la forma y la compara con `is`
    (core/apolo/CLAUDE.md)."""

    def __init__(self) -> None:
        self._cache: dict[int, tuple] = {}

    def _datos(self, forma) -> tuple:
        """(cajas de cara | None, sólidos, un vértice por sólido | None)."""
        hit = self._cache.get(id(forma))
        if hit is not None and hit[0] is forma:
            return hit[1]
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib

        try:  # caja de cada cara por su GEOMETRÍA (con la malla podría quedar corta)
            caras = []
            for cara in forma.faces():
                bb = Bnd_Box()
                BRepBndLib.Add_s(cara.wrapped, bb, False)
                if not bb.IsVoid():
                    x0, y0, z0, x1, y1, z1 = bb.Get()
                    caras.append(((x0, y0, z0), (x1, y1, z1)))
        except Exception:  # noqa: BLE001 — sin caras legibles: no se descarta nada
            caras = None
        try:
            solidos = list(forma.solids())
            puntos = []
            for sol in solidos:
                v = sol.vertices()
                if not v:
                    raise ValueError("sólido sin vértices")
                puntos.append((v[0].X, v[0].Y, v[0].Z))
            puntos = puntos or None
        except Exception:  # noqa: BLE001
            solidos, puntos = [], None
        datos = (caras, solidos, puntos)
        self._cache[id(forma)] = (forma, datos)
        return datos

    @staticmethod
    def _alguno_dentro(solidos, puntos) -> bool:
        """¿Algún punto está dentro (o sobre) de algún sólido? (un sólido entero de la otra)."""
        from OCP.BRepClass3d import BRepClass3d_SolidClassifier
        from OCP.gp import gp_Pnt
        from OCP.TopAbs import TopAbs_OUT

        for sol in solidos:
            for p in puntos:
                if BRepClass3d_SolidClassifier(sol.wrapped, gp_Pnt(*p), 1e-6).State() != TopAbs_OUT:
                    return True
        return False

    def _lado(self, fa, fb, r) -> bool:
        """La condición necesaria del lado de A: una cara de A en R, o un sólido de B dentro de A."""
        caras, solidos, _ = self._datos(fa)
        if caras is None or not solidos or any(_solapan(c, r, 0.0) for c in caras):
            return True
        puntos = self._datos(fb)[2]
        if puntos is None:
            return True
        try:
            return self._alguno_dentro(solidos, puntos)
        except Exception:  # noqa: BLE001
            return True

    def puede_interferir(self, fa, fb, ca, cb, min_volumen: float) -> bool:
        """False sólo si A∩B NO puede pasar de `min_volumen` (ver el docstring del módulo)."""
        if volumen_comun(ca, cb) <= min_volumen:
            return False
        r = comun(ca, cb)
        return self._lado(fa, fb, r) and self._lado(fb, fa, r)
