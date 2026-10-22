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
from apolo.library.seguridad.sondas import desplazamientos, direcciones, veredicto

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


class BandaEmpujable:
    """Las bandas (`clase_flexible` «banda») se empujan en la abertura de una guarda (rol
    «guarda»): un punto de banda a ≤ `EMPUJE_MM` de una guarda y SIN apoyo a esa distancia (ni
    tambor, ni cama, ni otra pieza que no sea guarda ni banda: un tramo libre) no bloquea. Donde la
    banda abraza un tambor o asienta en la cama no se mueve."""

    def __init__(self, dc: dict):
        import numpy as np
        from scipy.spatial import cKDTree

        from apolo.library.seguridad.modelo import clase_flexible

        piezas = dc["piezas"]
        self.bandas = {i for i, p in piezas.items() if clase_flexible(p) == "banda"}
        guardas = {i for i, p in piezas.items() if p.rol == "guarda"}
        self._kd_guarda = self._kd_apoyo = None
        if self.bandas and guardas:
            pg = _nube([s for i in guardas for s in dc["solidos"].get(i, [])])
            pa = _nube([s for i, ss in dc["solidos"].items()
                        if i not in guardas and i not in self.bandas for s in ss])
            self._kd_guarda = cKDTree(pg) if len(pg) else None
            self._kd_apoyo = cKDTree(pa) if len(pa) else None
        self._np = np

    def empujable(self, pts):
        """Máscara de los puntos de banda que se empujan (en una abertura y sin apoyo)."""
        np = self._np
        pts = np.asarray(pts, dtype=float).reshape(-1, 3)
        if self._kd_guarda is None:
            return np.zeros(len(pts), dtype=bool)
        d, _ = self._kd_guarda.query(pts, k=1, distance_upper_bound=EMPUJE_MM)
        out = d <= EMPUJE_MM
        if self._kd_apoyo is not None and out.any():
            da, _ = self._kd_apoyo.query(pts[out], k=1, distance_upper_bound=EMPUJE_MM)
            out[np.flatnonzero(out)] = da > EMPUJE_MM
        return out

    def salta(self, fid, q) -> bool:
        return fid in self.bandas and bool(self.empujable([q])[0])


def campo_alcance(solidos: dict, caja, z_piso: float, empuje: BandaEmpujable | None = None):
    """El `CampoAlcance` de la máquina: muestras del teselado de render de cada sólido; las de una
    banda dentro de la abertura de una guarda no cuentan (`empuje`)."""
    import numpy as np

    from apolo.library.seguridad.alcance import CampoAlcance

    nubes = []
    for fid, lista in solidos.items():
        pts = _nube(lista)
        if empuje is not None and fid in empuje.bandas and len(pts):
            pts = pts[~empuje.empujable(pts)]
        nubes.append(pts)
    pts = np.concatenate(nubes) if nubes else np.zeros((0, 3))
    return CampoAlcance(pts, caja, z_piso)


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
                    out.append(h[0] if h is not None and h[1] not in forman else None)
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
