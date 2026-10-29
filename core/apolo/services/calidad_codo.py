"""Sondas con el brazo DOBLADO (ISO 13857, alcance a través de aberturas) para la puerta de
publicación — el complemento de las sondas rectas de `calidad_sondas.py` (F6 de
puerta-de-publicacion).

Una sonda recta sólo ve el peligro si una LÍNEA desde fuera de la máquina llega a él. El brazo
entra por una abertura > 20 mm hasta el hombro y se dobla: la cuña retorno ↔ desvío de la faja de
motor central quedaba a 60 mm de la ranura de 36 mm entre el borde de la banda y el larguero,
encima de la guarda del drive, y ninguna recta llegaba (se sube entre las patas y se baja junto
a la banda). Aquí:

1. `campo_alcance`: el campo de la muñeca (`library/seguridad/alcance.py`) sobre el teselado de
   todos los sólidos;
2. `sondas_con_codo`: desde cada objetivo del peligro, la MANO va recta (≤ 230 mm, tabla 6) a
   los voxeles a los que llega la muñeca —los más cercanos en cada una de 256 direcciones: así
   también se encuentran las ventanas estrechas, que una esfera fija de direcciones salta—; si el
   tramo está libre, `sondas.veredicto` lo juzga con sus haces (profundidad = la de la muñeca +
   el tramo).
3. **La banda se empuja** (`BandaEmpujable`): una banda que atraviesa la abertura de una guarda
   no la tapa; en un tramo LIBRE a ≤ `EMPUJE_MM` de una guarda la banda no bloquea la sonda, no
   estrecha el haz y no es pared del brazo: la abertura es la que queda al empujarla (re-revisión
   de la faja central: la banda de retorno cruza la guarda del drive por una ranura de ~10–12 mm,
   23,6 mm empujándola, a 59 mm de la cuña del desvío). Donde abraza un tambor o asienta en la cama
   no se mueve, y fuera de las aberturas sigue sin atravesarse.

Lee shapes (teselado): el llamador sostiene `STATE_LOCK`. Sin `Document`.
"""

from __future__ import annotations

import time

from apolo.library.seguridad.iso13857 import ALCANCE_DESDE_MUNECA_MM
from apolo.library.seguridad.sondas import (bloqueo_con_piso, desplazamientos, direcciones,
                                            veredicto)

from .calidad_sondas import primero_salvo

MAX_SONDAS_CODO = 4096   # por peligro (como las rectas)
N_SECTORES = 256         # direcciones en que se agrupan las muñecas candidatas de cada objetivo
POR_SECTOR = 2           # las más cercanas de cada sector
#: En una cuña, la mano tiene que llegar a la CUÑA: tocar el tambor a más de esto del punto (su
#: canto o su cara más allá del borde de la banda) no es la cuña. Las rectas, como siempre, cuentan
#: todo contacto con el peligro; el extremo de eje y lo que gira tienen sus propios objetivos.
TOQUE_CUNA_MM = 20.0
#: Una banda a ≤ esto de una guarda está en su abertura y se empuja (criterio de diseño: la mano
#: desplaza una banda flexible lo que le deja la ranura).
EMPUJE_MM = 15.0


def nubes_de(solidos: dict, fids, nubes: dict | None = None):
    """La nube de las piezas `fids` ({fid: [Solid]}); `nubes` = memo por pieza (la prueba de
    sobrantes rearma el campo sin una pieza: el teselado de las demás no cambia)."""
    import numpy as np

    partes = []
    for fid in fids:
        if nubes is None:
            partes.append(_nube(solidos.get(fid, [])))
        else:
            if fid not in nubes:
                nubes[fid] = _nube(solidos.get(fid, []))
            partes.append(nubes[fid])
    partes = [x for x in partes if len(x)]
    return np.concatenate(partes) if partes else np.zeros((0, 3))


def _nube(solidos) -> list:
    import numpy as np

    from apolo.kernel.malla_render import triangular
    from apolo.library.seguridad.alcance import muestrear_triangulos

    out = []
    for s in solidos:
        try:
            xyz, tri, _ = triangular(s)
        except Exception:  # noqa: BLE001 — un sólido que no tesela no aporta paredes
            continue
        out.append(muestrear_triangulos(xyz, tri))
    return np.concatenate(out) if out else np.zeros((0, 3))


def _nube_y_bloques(solidos: dict, fids, nubes: dict | None):
    """(la nube de `nubes_de(solidos, fids, nubes)`, {fid: (desde, hasta)} de sus filas)."""
    import numpy as np

    partes, bloques, n = [], {}, 0
    for fid in fids:
        x = nubes_de(solidos, [fid], nubes)
        bloques[fid] = (n, n + len(x))
        n += len(x)
        if len(x):
            partes.append(x)
    return (np.concatenate(partes) if partes else np.zeros((0, 3))), bloques


def _distancia(kd, pts, quitado):
    """La distancia de cada punto al vecino de `kd` más cercano NO `quitado` (máscara por fila
    del árbol; None = ninguno), ∞ si no hay a ≤ `EMPUJE_MM`: la misma que daría el árbol armado
    sin lo quitado (`query(k)` creciente con la misma cota; cada distancia es la del mismo par)."""
    import numpy as np

    d, i = kd.query(pts, k=1, distance_upper_bound=EMPUJE_MM)
    if quitado is None:
        return d
    n = kd.n
    pend = np.flatnonzero((i < n) & quitado[np.minimum(i, n - 1)])
    k = 4
    while len(pend):
        dk, ik = kd.query(pts[pend], k=k, distance_upper_bound=EMPUJE_MM)
        valido = ik < n
        libre = valido & ~quitado[np.minimum(ik, n - 1)]
        hay = libre.any(axis=1)
        primero = np.argmax(libre, axis=1)
        d[pend] = np.where(hay, dk[np.arange(len(pend)), primero], np.inf)
        pend = pend[~hay & valido[:, -1]]  # todos quitados y quizá más dentro de la cota
        k *= 4
    return d


class BandaEmpujable:
    """Las bandas (`clase_flexible` «banda») se empujan en la abertura de una guarda (rol
    «guarda»): un punto de banda a ≤ `EMPUJE_MM` de una guarda y SIN apoyo a esa distancia (ni
    tambor, ni cama, ni otra pieza que no sea guarda ni banda: un tramo libre) no bloquea. Donde la
    banda abraza un tambor o asienta en la cama no se mueve.

    `sin(q)` es la de la máquina sin las piezas `q` SIN rehacer los árboles (plan puerta-rapida,
    D1): las filas de `q` se enmascaran al consultar (`_distancia`). Las bandas no cambian (si `q`
    tiene una, None: hay que rehacerla) y una guarda o un apoyo quitado sólo pierde sus puntos."""

    def __init__(self, dc: dict, nubes: dict | None = None):
        import numpy as np
        from scipy.spatial import cKDTree

        from apolo.library.seguridad.modelo import clase_flexible

        piezas = dc["piezas"]
        self.dc = dc  # el de la corrida, para reusarla sin una pieza (`sin`)
        self.bandas = {i for i, p in piezas.items() if clase_flexible(p) == "banda"}
        guardas = {i for i, p in piezas.items() if p.rol == "guarda"}
        self._kd_guarda = self._kd_apoyo = None
        self._bloques_g = self._bloques_a = {}
        self._sin_g = self._sin_a = None  # filas enmascaradas de cada árbol (`sin`)
        if self.bandas and guardas:
            pg, self._bloques_g = _nube_y_bloques(dc["solidos"], sorted(guardas), nubes)
            pa, self._bloques_a = _nube_y_bloques(
                dc["solidos"], [i for i in dc["solidos"]
                                if i not in guardas and i not in self.bandas], nubes)
            self._kd_guarda = cKDTree(pg) if len(pg) else None
            self._kd_apoyo = cKDTree(pa) if len(pa) else None
        self._np = np

    def sin(self, q) -> BandaEmpujable | None:
        """La de esta máquina sin las piezas `q` (una vista: los árboles son éstos), `self` si
        ninguna de `q` aporta puntos, None si `q` quita una banda."""
        import copy

        np = self._np
        if set(q) & self.bandas:
            return None
        mascaras = []
        for kd, bloques in ((self._kd_guarda, self._bloques_g), (self._kd_apoyo, self._bloques_a)):
            filas = [bloques[i] for i in q if i in bloques and bloques[i][1] > bloques[i][0]]
            if kd is None or not filas:
                mascaras.append(None)
                continue
            m = np.zeros(kd.n, dtype=bool)
            for a, b in filas:
                m[a:b] = True
            mascaras.append(m)
        if all(m is None for m in mascaras):
            return self
        v = copy.copy(self)
        v._sin_g, v._sin_a = mascaras
        return v

    def empujable(self, pts):
        """Máscara de los puntos de banda que se empujan (en una abertura y sin apoyo)."""
        np = self._np
        pts = np.asarray(pts, dtype=float).reshape(-1, 3)
        if self._kd_guarda is None:
            return np.zeros(len(pts), dtype=bool)
        d = _distancia(self._kd_guarda, pts, self._sin_g)
        out = d <= EMPUJE_MM
        if self._kd_apoyo is not None and out.any():
            da = _distancia(self._kd_apoyo, pts[out], self._sin_a)
            out[np.flatnonzero(out)] = da > EMPUJE_MM
        return out

    def salta(self, fid, q) -> bool:
        return fid in self.bandas and bool(self.empujable([q])[0])


def campo_alcance(solidos: dict, caja, z_piso: float, empuje: BandaEmpujable | None = None,
                  memo: dict | None = None, piso_solido: bool = False):
    """El `CampoAlcance` de la máquina: muestras del teselado de render de cada sólido; las de una
    banda dentro de la abertura de una guarda no cuentan (`empuje`). `memo`: las nubes por pieza
    ya teseladas (`nubes_de`). `piso_solido`: el de lo anclado es pared (F3f)."""
    import numpy as np

    from apolo.library.seguridad.alcance import CampoAlcance

    nubes = []
    for fid in solidos:
        pts = nubes_de(solidos, [fid], memo)
        if empuje is not None and fid in empuje.bandas and len(pts):
            pts = pts[~empuje.empujable(pts)]
        nubes.append(pts)
    pts = np.concatenate(nubes) if nubes else np.zeros((0, 3))
    return CampoAlcance(pts, caja, z_piso, piso_solido=piso_solido)


def _libre_hasta(tr, p, u, s: float, propias: set, salta) -> bool:
    """¿Va la mano de `p` a `p + s·u` sin cruzar un sólido ajeno al peligro? (lo del peligro se
    atraviesa: tocarlo ya es llegar; la banda en una abertura, se empuja)."""
    t_min = 0.0
    while True:
        h = primero_salvo(tr, p, u, s, salta, t_min)
        if h is None:
            return True
        if h[1] not in propias:
            return False
        t_min = h[0] + 1e-3


def _munecas(campo, p, sectores):
    """Las muñecas candidatas de `p`: por sector de dirección, las `POR_SECTOR` más cercanas."""
    import numpy as np

    c, prof, dist = campo.cerca(p, ALCANCE_DESDE_MUNECA_MM)
    if not len(c):
        return []
    u = (c - np.asarray(p)) / np.maximum(dist, 1e-9)[:, None]
    sector = np.argmax(u @ sectores.T, axis=1)
    orden = np.lexsort((dist, sector))
    out, cuenta = [], {}
    for k in orden:
        sk = int(sector[k])
        if cuenta.get(sk, 0) < POR_SECTOR:
            cuenta[sk] = cuenta.get(sk, 0) + 1
            out.append((tuple(float(v) for v in c[k]), float(prof[k]), float(dist[k])))
    return out


def sondas_con_codo(tr, campo, peligro: dict, n_direcciones: int = 64,
                    empuje: BandaEmpujable | None = None) -> tuple[list[dict], float]:
    """Las sondas con el brazo doblado de un peligro → ([sonda], ms), con el formato de
    `calidad_sondas.evaluar_peligro` (las que alcanzan llevan además `codo` —la muñeca— y su
    profundidad). `n_direcciones` no se usa (las muñecas salen del campo); queda por firma."""
    import numpy as np

    t0 = time.perf_counter()
    objetivos = peligro.get("objetivos") or []
    tope = max(1, MAX_SONDAS_CODO // max(1, len(objetivos)))
    propias = set(peligro["piezas"])
    forman = propias | set(peligro.get("forman", ()))
    cuna = bool(peligro.get("cuna"))
    salta = empuje.salta if empuje is not None else None
    sectores = np.array(direcciones(N_SECTORES))
    z_suelo = campo.z_piso if getattr(campo, "piso_solido", False) else None
    sondas = []
    for p in objetivos:
        for w, prof, s in _munecas(campo, p, sectores)[:tope]:
            u = tuple((w[i] - p[i]) / max(s, 1e-9) for i in range(3))
            if not _libre_hasta(tr, p, u, s, propias, salta):
                sondas.append({"alcanza": False, "bloquea": [], "motivo": "la mano no pasa"})
                continue
            d = tuple(-c for c in u)  # de la muñeca hacia el objetivo
            hit = primero_salvo(tr, w, d, s + 0.5, salta)
            t_llega = hit[0] if hit is not None else s
            if cuna and s - t_llega > TOQUE_CUNA_MM:
                sondas.append({"alcanza": False, "bloquea": [],
                               "motivo": "toca el tambor lejos de la cuña"})
                continue

            def haces(ancho, o=w, d=d, t_llega=t_llega):
                out = []
                for off in desplazamientos(ancho, d):
                    oo = tuple(o[i] + off[i] for i in range(3))
                    h = primero_salvo(tr, oo, d, t_llega, salta)
                    out.append(bloqueo_con_piso(h[0] if h is not None and h[1] not in forman
                                                else None, oo, d, t_llega, z_suelo))
                return out

            v = veredicto(t_llega, 0.0, prof, haces)
            if not v["alcanza"]:
                sondas.append({"alcanza": False, "bloquea": [], "motivo": v["motivo"]})
                continue
            sondas.append({
                "alcanza": True, "via": "brazo doblado", "objetivo": [round(c, 1) for c in p],
                "direccion": [round(c, 3) for c in d],
                "codo": [round(c, 1) for c in w], "profundidad_codo_mm": round(prof, 1),
                "toca": [round(w[i] + t_llega * d[i], 1) for i in range(3)],
                "pieza_tocada": hit[1] if hit is not None else None,
                "distancia_mm": v.get("profundidad_mm"), "abertura_mm": v.get("abertura_mm"),
                "sr_mm": v.get("sr_mm"), "sr_requerida_mm": v.get("sr_requerida_mm"),
            })
    return sondas, (time.perf_counter() - t0) * 1000.0
