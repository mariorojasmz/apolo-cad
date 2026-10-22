"""Alcance del brazo DOBLADO (ISO 13857:2019, tablas 4 y 6) — el campo de dónde puede estar la
MUÑECA de un brazo que entra desde fuera de la máquina con un codo, no sólo en línea recta.

Las sondas rectas (`sondas.py`) prueban líneas de vista desde el contorno. Un brazo que pasa una
abertura > 20 mm llega hasta el hombro (sr 850 mm) y se DOBLA: un peligro que sólo se alcanza
doblando el brazo (sube entre las patas, pasa por encima del borde de una guarda y baja junto al
borde de la banda) quedaba fuera de toda recta y salía OK (F6 de puerta-de-publicacion: la cuña
retorno ↔ desvío de la faja de motor central). Modelo (declarado, criterio de diseño sobre la
tabla 6 de «alcance alrededor»: hombro, codo, muñeca):

- **Sonda del brazo** = 20 mm de diámetro (la abertura > 20 mm de la tabla 4 por la que entra el
  brazo): un voxel es transitable si su centro está a ≥ `R_BRAZO_MM` de toda superficie. Un paso
  entre centros vecinos (≤ la diagonal del voxel < 2·R) no salta ninguna pared.
- **Brazo** (hombro → codo): RECTO desde fuera de la caja de la máquina, o desde el piso por
  debajo de ella con la distancia horizontal al borde de la caja (la vara de `sondas.origen`).
- **Antebrazo** (codo → muñeca): otro tramo RECTO desde cualquier punto que el brazo alcanza.
- La profundidad del voxel = el largo de ese camino; > 850 mm (el brazo entero) no llega.
- **Mano** (muñeca → peligro, ≤ 230 mm, tabla 6): la tira `services/calidad_codo.py` y la juzga
  `sondas.veredicto` con sus haces, como una sonda recta (la abertura que pasa la mano decide sr).

Las rectas van por las 26 direcciones de la red (barrido por capas). Puro: numpy/scipy, sin OCCT.
"""

from __future__ import annotations

import math

from .iso13857 import ALCANCE_BRAZO_MM

R_BRAZO_MM = 10.0          # radio de la sonda del brazo (abertura > 20 mm: entra el brazo)
PASO_GRILLA_MM = 10.0      # lado del voxel
PASO_MUESTRAS_MM = 5.0     # separación de las muestras sobre las superficies
MARGEN_MM = 60.0           # la grilla sobresale de la caja de la máquina (≥ el origen de las sondas)
MAX_VOXELES = 12_000_000   # con más, el voxel crece (y se declara en la evidencia)


def _grilla(n_i, n_j):
    """Índices (t, i, j) de una grilla (n_i + 1) × (n_j + 1) por triángulo t, vectorizado."""
    import numpy as np

    tam = (n_i + 1) * (n_j + 1)
    t = np.repeat(np.arange(len(tam)), tam)
    k = np.arange(int(tam.sum())) - np.repeat(np.cumsum(tam) - tam, tam)
    return t, k // (n_j[t] + 1), k % (n_j[t] + 1)


def muestrear_triangulos(xyz, tri, paso: float = PASO_MUESTRAS_MM):
    """Puntos sobre los triángulos con separación ≤ `paso` (determinista): las superficies como
    nube de puntos para medir la holgura del brazo. Cada triángulo se barre en una grilla
    alineada a su lado MAYOR y a su altura (un triángulo largo y fino da pocos puntos: ~ área/paso²
    + perímetro/paso), más sus tres lados. Con la holgura del brazo (10 mm) el error de medir
    contra muestras es de segundo orden: ≤ paso²/(4·r) (0,6 mm con paso 5)."""
    import numpy as np

    xyz = np.asarray(xyz, dtype=float)
    tri = np.asarray(tri, dtype=np.int64).reshape(-1, 3)
    if len(tri) == 0:
        return np.zeros((0, 3))
    v = xyz[tri]                                             # (m, 3 vértices, 3)
    lados = np.stack([v[:, 1] - v[:, 0], v[:, 2] - v[:, 1], v[:, 0] - v[:, 2]], axis=1)
    largos = np.linalg.norm(lados, axis=2)
    out = []
    for e in range(3):                                       # los lados
        n = np.maximum(1, np.ceil(largos[:, e] / paso)).astype(np.int64)
        t, i, _ = _grilla(n, np.zeros_like(n))
        out.append(v[t, e] + lados[t, e] * (i / n[t])[:, None])
    k = np.argmax(largos, axis=1)                             # el lado mayor es la base
    m = np.arange(len(tri))
    a, base = v[m, k], lados[m, k]
    c = v[m, (k + 2) % 3]                                    # el vértice opuesto
    lb = np.maximum(largos[m, k], 1e-9)
    e1 = base / lb[:, None]
    ac = c - a
    s = (ac * e1).sum(axis=1)
    alto_v = ac - s[:, None] * e1
    alto = np.linalg.norm(alto_v, axis=1)
    e2 = alto_v / np.maximum(alto, 1e-9)[:, None]
    n_i = np.ceil(lb / paso).astype(np.int64)
    n_j = np.ceil(alto / paso).astype(np.int64)
    sel = n_j >= 2                                           # con n_j ≤ 1 bastan los lados
    if sel.any():
        t, i, j = _grilla(n_i[sel], n_j[sel])
        idx = np.flatnonzero(sel)[t]
        x = i * (lb[idx] / n_i[idx])
        y = j * (alto[idx] / n_j[idx])
        # dentro: 0 ≤ y ≤ alto y, a esa altura, entre los dos lados que suben al vértice opuesto
        f = y / np.maximum(alto[idx], 1e-9)
        dentro = (x >= f * s[idx] - 1e-6) & (x <= lb[idx] + f * (s[idx] - lb[idx]) + 1e-6)
        idx, x, y = idx[dentro], x[dentro], y[dentro]
        out.append(a[idx] + e1[idx] * x[:, None] + e2[idx] * y[:, None])
    return np.concatenate(out)


class CampoAlcance:
    """Profundidad (mm) a la que llega la MUÑECA por voxel: brazo recto desde fuera + antebrazo
    recto desde donde llega el brazo (un codo), por voxeles transitables (modelo en el docstring
    del módulo).

    Semillas (la vara de las sondas rectas, `sondas.origen`): fuera de la caja de la máquina = 0;
    la capa del piso dentro de la caja = la distancia horizontal al borde de la caja (el brazo
    llega por el piso, por debajo de la máquina). `puntos`: muestras de TODAS las superficies
    (`muestrear_triangulos`); `caja` = ((lo), (hi)); `z_piso`: la grilla empieza ahí."""

    def __init__(self, puntos, caja, z_piso: float, paso: float = PASO_GRILLA_MM,
                 r_brazo: float = R_BRAZO_MM, alcance: float = ALCANCE_BRAZO_MM):
        import numpy as np

        lo, hi = (np.asarray(c, dtype=float) for c in caja)
        self.lo = np.array([lo[0] - MARGEN_MM, lo[1] - MARGEN_MM, z_piso])
        top = np.array([hi[0] + MARGEN_MM, hi[1] + MARGEN_MM, hi[2] + MARGEN_MM])
        n_est = float(np.prod(np.maximum(1.0, (top - self.lo) / paso)))
        if n_est > MAX_VOXELES:
            paso *= (n_est / MAX_VOXELES) ** (1.0 / 3.0)
        # con un voxel mayor, la sonda engorda lo justo para que ningún paso salte una pared
        self.paso, self.alcance = paso, alcance
        self.r_brazo = max(r_brazo, paso * math.sqrt(3.0) / 2.0 + 0.01)
        forma = tuple(int(v) for v in np.maximum(1, np.ceil((top - self.lo) / paso)))
        self.forma = forma
        libre = self._transitables(np.asarray(puntos, dtype=float), forma)
        c = [self.lo[k] + (np.arange(forma[k]) + 0.5) * paso for k in range(3)]
        fuera_xy = ((c[0] < lo[0]) | (c[0] > hi[0]))[:, None] | ((c[1] < lo[1]) | (c[1] > hi[1]))[None, :]
        semillas = np.full(forma, np.inf, dtype=np.float32)
        semillas[fuera_xy] = 0.0
        semillas[:, :, c[2] > hi[2]] = 0.0
        borde = np.minimum(np.minimum(c[0] - lo[0], hi[0] - c[0])[:, None],
                           np.minimum(c[1] - lo[1], hi[1] - c[1])[None, :])
        semillas[:, :, 0] = np.minimum(semillas[:, :, 0], np.maximum(borde, 0.0))
        semillas[~libre] = np.inf
        brazo = self._recta(libre, semillas)          # hombro → codo: recto desde fuera
        brazo[brazo > alcance] = np.inf
        antebrazo = self._recta(libre, brazo)         # codo → muñeca: otro tramo recto
        antebrazo[antebrazo > alcance] = np.inf
        self._prof = antebrazo

    def _transitables(self, pts, forma):
        """Voxeles cuyo centro está a ≥ r_brazo de toda muestra (descontado el error de muestreo)."""
        import numpy as np
        from scipy.ndimage import distance_transform_edt
        from scipy.spatial import cKDTree

        h = self.paso
        ocupado = np.zeros(forma, dtype=bool)
        if len(pts):
            ijk = np.floor((pts - self.lo) / h).astype(np.int64)
            ok = np.all((ijk >= 0) & (ijk < np.array(forma)), axis=1)
            ocupado[tuple(ijk[ok].T)] = True
        if not ocupado.any():
            return np.ones(forma, dtype=bool)
        d = distance_transform_edt(~ocupado, sampling=h)
        seguro = d > self.r_brazo + h * math.sqrt(3.0) / 2.0 + 0.5  # ninguna muestra en r_brazo
        dudoso = (~ocupado) & (~seguro)
        libre = seguro.copy()
        cand = np.argwhere(dudoso)
        if len(cand):
            centros = self.lo + (cand + 0.5) * h
            dist, _ = cKDTree(pts).query(centros, k=1, distance_upper_bound=self.r_brazo)
            libre[tuple(cand[dist >= self.r_brazo].T)] = True
        return libre

    def _recta(self, libre, base):
        """F(v) = mín, sobre las 26 direcciones d de la red y k ≥ 0, de base(v − k·d) + k·|d|·paso
        con los k + 1 voxeles de esa recta transitables: un tramo RECTO del brazo que sale de
        donde `base` es finita. El paso (≤ la diagonal del voxel < 2·r_brazo) no salta paredes.
        Barrido por capas a lo largo del eje MÁS CORTO en que d avanza."""
        import numpy as np

        mejor = base.copy()
        n = self.forma
        for d in [(dx, dy, dz) for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)
                  if (dx, dy, dz) != (0, 0, 0)]:
            a = min((k for k in range(3) if d[k]), key=lambda k: n[k])
            paso = np.float32(self.paso * math.sqrt(sum(v * v for v in d)))
            otros = [k for k in range(3) if k != a]
            cur = np.moveaxis(base, a, 0).copy()
            ok = np.moveaxis(libre, a, 0)
            db, dc = d[otros[0]], d[otros[1]]
            nb, nc = cur.shape[1], cur.shape[2]
            dst = (slice(max(db, 0), nb + min(db, 0)), slice(max(dc, 0), nc + min(dc, 0)))
            src = (slice(max(-db, 0), nb - max(db, 0)), slice(max(-dc, 0), nc - max(dc, 0)))
            desp = np.empty((nb, nc), dtype=cur.dtype)
            rango = range(1, n[a]) if d[a] > 0 else range(n[a] - 2, -1, -1)
            for i in rango:
                desp.fill(np.inf)
                desp[dst] = cur[i - d[a]][src]
                desp += paso
                np.minimum(cur[i], desp, out=desp)
                cur[i] = np.where(ok[i], desp, np.inf)
            np.minimum(mejor, np.moveaxis(cur, 0, a), out=mejor)
        return mejor

    def profundidad(self, p) -> float | None:
        """La profundidad (mm) del voxel de `p` por el brazo recto, o None si no llega (o no cabe)."""
        ijk = [int(math.floor((p[k] - self.lo[k]) / self.paso)) for k in range(3)]
        if not all(0 <= ijk[k] < self.forma[k] for k in range(3)):
            return 0.0 if p[2] >= self.lo[2] else None  # fuera de la grilla = fuera de la máquina
        v = float(self._prof[tuple(ijk)])
        return None if math.isinf(v) else v
