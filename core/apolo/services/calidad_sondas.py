"""Trazado de rayos contra los sólidos del documento (OCCT) para la puerta de publicación (F3).

- `Trazador`: UN compuesto con todos los sólidos y un `IntCurvesFace_ShapeIntersector` cargado
  una vez; cada cara sabe de qué pieza es. `primero` = el cruce más cercano; `todos` = todos los
  cruces (los barridos de reparabilidad).
- `cunas`: los puntos de las cuñas banda ↔ tambor (ISO 13854: la cuña es peligrosa donde la
  separación entre la banda y el tambor es < 25 mm; el punto va donde es 20 mm, a media altura).
- `evaluar_peligro`: las sondas de ISO 13857 sobre cada objetivo del peligro
  (`library/seguridad/sondas.py` decide; aquí sólo se cruzan rayos).

Lee shapes: el llamador sostiene `STATE_LOCK`. Sin `Document`: recibe sólidos y datos puros.
"""

from __future__ import annotations

import math
import time

from apolo.library.seguridad.sondas import (bloqueo_con_piso, desplazamientos, direcciones,
                                            origen, veredicto)

GAP_CUNA_MM = 20.0   # separación banda–tambor en el punto de la cuña (< 25 mm de ISO 13854)
PASO_ARCO_GRADOS = 5.0
MAX_SONDAS_PELIGRO = 4096
#: Una rendija de este ancho o menos no deja entrar el dedo (ISO 13857 tabla 4, fila e ≤ 4 mm):
#: un objetivo de enganche dentro de ella es una holgura funcional, no un peligro (F3c).
HOLGURA_FUNCIONAL_MM = 4.0


class Trazador:
    """Rayos contra todos los sólidos de `solidos` ({fid: [Solid build123d]}).

    Acelerado a mano (medido: el `IntCurvesFace_ShapeIntersector` del compuesto entero tardaba
    10 ms por rayo con las 17 800 caras del transportador de rodillos): caja de cada cara en
    numpy → candidatas en orden de entrada → intersección cara a cara (`IntCurvesFace_Intersector`
    construido una vez por cara, perezoso) hasta que la próxima caja empieza más lejos que el
    mejor cruce."""

    def __init__(self, solidos: dict):
        import numpy as np
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopoDS import TopoDS
        from OCP.TopTools import TopTools_IndexedMapOfShape

        caras, duenios, lo, hi = [], [], [], []
        for fid, lista in solidos.items():
            m = TopTools_IndexedMapOfShape()
            for s in lista:
                TopExp.MapShapes_s(s.wrapped, TopAbs_FACE, m)
            for i in range(1, m.Extent() + 1):
                f = TopoDS.Face_s(m.FindKey(i))
                bb = Bnd_Box()
                BRepBndLib.Add_s(f, bb)
                if bb.IsVoid():
                    continue
                x0, y0, z0, x1, y1, z1 = bb.Get()
                caras.append(f)
                duenios.append(fid)
                lo.append((x0, y0, z0))
                hi.append((x1, y1, z1))
        self._caras, self._duenio = caras, duenios
        self._lo = np.array(lo, dtype=float).reshape(-1, 3) - 1e-3
        self._hi = np.array(hi, dtype=float).reshape(-1, 3) + 1e-3
        self._inter: dict[int, object] = {}
        self.n_rayos = 0

    def _candidatas(self, o, d, t_min: float, t_max: float):
        import numpy as np

        o = np.asarray(o, dtype=float)
        d = np.asarray(d, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            inv = np.where(np.abs(d) > 1e-12, 1.0 / np.where(np.abs(d) > 1e-12, d, 1.0), np.inf)
            t1 = (self._lo - o) * inv
            t2 = (self._hi - o) * inv
            paralelo = np.abs(d) <= 1e-12
            dentro = (self._lo <= o) & (o <= self._hi)
            tn = np.where(paralelo, np.where(dentro, -np.inf, np.inf), np.minimum(t1, t2))
            tx = np.where(paralelo, np.where(dentro, np.inf, -np.inf), np.maximum(t1, t2))
        t_ent = tn.max(axis=1)
        t_sal = tx.min(axis=1)
        ok = (t_sal >= np.maximum(t_ent, t_min)) & (t_ent <= t_max)
        idx = np.nonzero(ok)[0]
        return idx[np.argsort(t_ent[idx], kind="stable")], t_ent

    def _cruces(self, k: int, lin, t_min: float, t_max: float) -> list[float]:
        from OCP.IntCurvesFace import IntCurvesFace_Intersector

        it = self._inter.get(k)
        if it is None:
            it = self._inter[k] = IntCurvesFace_Intersector(self._caras[k], 1e-3)
        it.Perform(lin, t_min, t_max)
        if not it.IsDone():
            return []
        return [float(it.WParameter(i)) for i in range(1, it.NbPnt() + 1)]

    @staticmethod
    def _linea(o, d):
        from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

        return gp_Lin(gp_Pnt(*o), gp_Dir(*d))

    def primero(self, o, d, t_max: float, t_min: float = 0.0):
        """(t, fid) del cruce más cercano en [t_min, t_max], o None."""
        self.n_rayos += 1
        idx, t_ent = self._candidatas(o, d, t_min, t_max)
        lin, mejor = self._linea(o, d), None
        for k in idx:
            if mejor is not None and t_ent[k] > mejor[0]:
                break
            for t in self._cruces(int(k), lin, t_min, t_max):
                if mejor is None or t < mejor[0]:
                    mejor = (t, self._duenio[k])
        return mejor

    def todos(self, o, d, t_max: float, t_min: float = 0.0) -> list[tuple[float, str]]:
        self.n_rayos += 1
        idx, _ = self._candidatas(o, d, t_min, t_max)
        lin = self._linea(o, d)
        out = [(t, self._duenio[k]) for k in idx for t in self._cruces(int(k), lin, t_min, t_max)]
        return sorted(out)


def primero_salvo(tr, o, d, t_max: float, salta=None, t_min: float = 0.0):
    """`tr.primero` saltando los cruces que `salta(fid, punto)` deja pasar (la banda dentro de la
    abertura de una guarda: se empuja, `calidad_codo.BandaEmpujable`)."""
    while True:
        h = tr.primero(o, d, t_max, t_min)
        if h is None or salta is None:
            return h
        q = tuple(o[i] + h[0] * d[i] for i in range(3))
        if not salta(h[1], q):
            return h
        t_min = h[0] + 1e-3


def _dentro(solidos, p) -> bool:
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN

    for s in solidos:
        c = BRepClass3d_SolidClassifier(s.wrapped, gp_Pnt(*p), 1e-4)
        if c.State() == TopAbs_IN:
            return True
    return False


def _u(redondo, theta: float):
    i, j = (k for k in range(3) if k != redondo.eje)
    v = [0.0, 0.0, 0.0]
    v[i], v[j] = math.cos(theta), math.sin(theta)
    return v


def theta(redondo, p) -> float:
    """El ángulo de `p` alrededor del eje del tambor, en la convención de `_u`."""
    i, j = (k for k in range(3) if k != redondo.eje)
    return math.atan2(p[j] - redondo.centro[j], p[i] - redondo.centro[i])


def cunas(banda_solidos, banda_caja, tambor_caja, redondo, hacia=None) -> dict:
    """Los puntos de las cuñas de un tambor que la banda abraza: el arco de contacto se
    busca con puntos a r + 1 mm DENTRO de la banda (cada 5°); en cada borde del arco la banda
    se separa por la tangente y la cuña queda del lado de afuera del arco, a φ = acos(r/(r+g))
    del borde, a radio r + g/2. Tres estaciones a lo ancho (centro y ±15 mm de los bordes).
    `hacia`: el punto 3D donde la banda LLEGA al tambor en el sentido de marcha
    (`calidad_cunas`); con él sólo cuenta el borde más cercano —la cuña de ENTRADA
    (puerta-sin-sobrediseno D4)—; sin él, o si no se puede elegir, las dos.
    → {puntos, arco_grados, bordes, cuna: "entrada" | "las dos"} o {puntos: [], motivo}."""
    from apolo.library.seguridad.cuna_entrada import borde_de_entrada

    a = redondo.eje
    lo = max(banda_caja[0][a], tambor_caja[0][a])
    hi = min(banda_caja[1][a], tambor_caja[1][a])
    if hi - lo < 1.0:
        return {"puntos": [], "motivo": "la banda no cubre el tambor"}
    estaciones = [(lo + hi) / 2.0]
    if hi - lo > 40.0:
        estaciones += [lo + 15.0, hi - 15.0]
    r, n = redondo.radio, int(round(360.0 / PASO_ARCO_GRADOS))
    dentro = []
    for delta in (1.0, 2.5, 0.5):
        dentro = []
        for k in range(n):
            th = math.radians(k * PASO_ARCO_GRADOS)
            q = list(redondo.centro)
            q[a] = estaciones[0]
            u = _u(redondo, th)
            dentro.append(_dentro(banda_solidos, [q[i] + (r + delta) * u[i] for i in range(3)]))
        if any(dentro) and not all(dentro):
            break
    if not any(dentro) or all(dentro):
        return {"puntos": [], "motivo": "no se encontró el arco de contacto de la banda"}
    phi = math.acos(r / (r + GAP_CUNA_MM))
    bordes = []
    for k in range(n):
        sig = (k + 1) % n
        if dentro[k] and not dentro[sig]:
            bordes.append((math.radians((k + 0.5) * PASO_ARCO_GRADOS), +1.0))
        elif not dentro[k] and dentro[sig]:
            bordes.append((math.radians((k + 0.5) * PASO_ARCO_GRADOS), -1.0))
    n_bordes, cuna = len(bordes), "las dos"
    if hacia is not None:
        k = borde_de_entrada([b[0] for b in bordes], theta(redondo, hacia))
        if k is not None:
            bordes, cuna = [bordes[k]], "entrada"
    puntos = []
    for th_t, s in bordes:
        u = _u(redondo, th_t + s * phi)
        for e in estaciones:
            q = list(redondo.centro)
            q[a] = e
            puntos.append(tuple(q[i] + (r + GAP_CUNA_MM / 2.0) * u[i] for i in range(3)))
    return {"puntos": puntos, "arco_grados": sum(dentro) * PASO_ARCO_GRADOS,
            "bordes": n_bordes, "cuna": cuna}


def holgura(tr: Trazador, p, max_mm: float = HOLGURA_FUNCIONAL_MM,
            n: int = 32) -> tuple[float, tuple[str, str]] | None:
    """(ancho, (pieza, pieza)) de la rendija en la que está el punto `p` —en el aire, entre DOS
    piezas distintas que lo encierran a ≤ `max_mm` sumando los dos lados, en alguna dirección— o
    None. Un punto dentro de un sólido da la misma pieza a los dos lados: no es una rendija."""
    mejor = None
    for d in direcciones(n):
        a = tr.primero(p, d, max_mm)
        if a is None:
            continue
        b = tr.primero(p, tuple(-c for c in d), max_mm - a[0])
        if b is None or b[1] == a[1]:
            continue
        if mejor is None or a[0] + b[0] < mejor[0]:
            mejor = (a[0] + b[0], (a[1], b[1]))
    return mejor


def fuera_de_holguras(tr: Trazador, peligro: dict) -> dict:
    """Saca de los objetivos de un peligro de ENGANCHE (lo que gira: eje, cubo, pieza, acople)
    los que caen dentro de una holgura funcional ≤ 4 mm (F3c de puerta-sin-sobrediseno: el punto
    de la salida del motorreductor quedaba en la rendija de 2 mm entre la caja y una chumacera, y
    toda holgura fallaba sin importar su ancho). Criterio: por una rendija ≤ 4 mm no entra el dedo
    (ISO 13857 tabla 4, la fila más angosta: sólo la PUNTA a 2 mm, que toca el borde de la rendija,
    no lo que gira adentro) y nada se arrastra por ella (ISO 13854: el dedo pide 25 mm). Una cuña
    o una cadena (atrapamiento) no: su rendija se abre hacia afuera y ése es su peligro. Muta y
    devuelve el peligro; los quitados van en `en_holgura` ({punto, ancho_mm, entre: las dos
    piezas}: la prueba de sobrantes los vuelve a sondear si quita una de ellas)."""
    if peligro.get("tipo") != "enganche" or not peligro.get("objetivos"):
        return peligro
    quedan, quitados = [], []
    for p in peligro["objetivos"]:
        h = holgura(tr, p)
        if h is None:
            quedan.append(p)
        else:
            quitados.append({"punto": [round(c, 2) for c in p], "ancho_mm": round(h[0], 1),
                             "entre": sorted(h[1])})
    if quitados:
        peligro["objetivos"], peligro["en_holgura"] = quedan, quitados
    return peligro


def evaluar_peligro(tr: Trazador, peligro: dict, caja, z_piso: float,
                    n_direcciones: int = 64, salta=None, *,
                    piso_solido: bool = False) -> tuple[list[dict], float]:
    """Las sondas de un peligro: por objetivo y dirección, el veredicto de `sondas.veredicto`.
    Devuelve ([sonda], ms). Cada sonda que alcanza lleva dirección, entrada al contorno, punto
    tocado, profundidad y abertura; las bloqueadas, la pieza que las paró (`bloquea`). `salta`:
    los cruces que no bloquean (la banda empujable en la abertura de una guarda). `piso_solido`
    (máquina anclada, `calidad_seguridad.piso_solido`): ninguna sonda nace bajo el piso y el piso
    estrecha los haces como una pared (F3f)."""
    t0 = time.perf_counter()
    objetivos = peligro.get("objetivos") or []
    n = n_direcciones
    if objetivos and len(objetivos) * n > MAX_SONDAS_PELIGRO:
        n = max(16, MAX_SONDAS_PELIGRO // len(objetivos))
    dirs = direcciones(n)
    propias = set(peligro["piezas"])
    # lo que FORMA el peligro (la banda de una cuña) no es una abertura de guarda: no estrecha el
    # haz; pero tampoco se atraviesa (el rayo central se bloquea en ella)
    forman = propias | set(peligro.get("forman", ()))
    sondas = []
    z_suelo = z_piso if piso_solido else None
    for p in objetivos:
        for d in dirs:
            ori = origen(p, d, caja, z_piso, piso_solido)
            if ori.get("bajo_piso"):
                sondas.append({"alcanza": False, "bloquea": [], "motivo": "el piso"})
                continue
            o, t_obj = ori["origen"], ori["t_objetivo"]
            hit = primero_salvo(tr, o, d, t_obj + 0.5, salta)
            if hit is not None and hit[1] not in propias:
                sondas.append({"alcanza": False, "bloquea": [hit[1]]})
                continue
            t_llega = hit[0] if hit is not None else t_obj

            def haces(ancho, o=o, d=d, t_llega=t_llega):
                out = []
                for off in desplazamientos(ancho, d):
                    oo = tuple(o[i] + off[i] for i in range(3))
                    h = primero_salvo(tr, oo, d, t_llega, salta)
                    out.append(bloqueo_con_piso(h[0] if h is not None and h[1] not in forman
                                                else None, oo, d, t_llega, z_suelo))
                return out

            v = veredicto(t_llega, ori["t_contorno"], ori["extra"], haces)
            if not v["alcanza"]:
                sondas.append({"alcanza": False, "bloquea": [], "motivo": v["motivo"]})
                continue
            t_ent = ori["t_contorno"]
            sondas.append({
                "alcanza": True, "objetivo": [round(c, 1) for c in p],
                "direccion": [round(c, 3) for c in d],
                "entrada": [round(o[i] + t_ent * d[i], 1) for i in range(3)],
                "toca": [round(o[i] + t_llega * d[i], 1) for i in range(3)],
                "pieza_tocada": hit[1] if hit is not None else None,
                "distancia_mm": v.get("profundidad_mm"), "abertura_mm": v.get("abertura_mm"),
                "sr_mm": v.get("sr_mm"), "sr_requerida_mm": v.get("sr_requerida_mm"),
            })
    return sondas, (time.perf_counter() - t0) * 1000.0
