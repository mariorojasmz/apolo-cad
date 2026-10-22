"""La ruta de la faja tomada del MODELO (fabrica-de-publicaciones, ajuste D13a): matemática PURA.

`ruta_faja.py` arma la ruta con el casco convexo de los tambores; un drive central en Ω no es
convexo (la banda baja a abrazar el motriz por debajo de dos desvíos) y el casco lo corta en
recta, a través de las guardas. Aquí la forma sale de la SECCIÓN del sólido de la banda —el que
validaron las interferencias y la puerta de entrega—, en el plano ⟂ al eje de los tambores por el
centro del ancho, que `services/marcha_visual.py` extrae con OCCT y manda como puntos (u, w):

- **Línea media** (`linea_media`): cada punto del contorno EXTERIOR se promedia con el punto más
  cercano del contorno interior (todos los huecos de la sección). No hace falta emparejar las dos
  polilíneas (cada una sale muestreada a su manera): en un arco el más cercano está sobre el
  radio, así la media queda en r + t/2; en un tramo recto, a t/2 de cada cara. El espesor es la
  mediana de esas distancias; donde el más cercano no es plausible (|d − t| > t/2: un hueco que
  no es la cara interior, como el de un tubo completo del super-comando) el punto se corre t/2
  por la normal hacia adentro. Con t ≪ el radio de cualquier tambor, el error es O(t²/r).
- **Tambores** (`ruta_modelo`): una pieza redonda cuyo centro queda a ≤ r + t/2 + `TOL_CONTACTO_MM`
  de la línea media la toca: adentro del lazo es un tambor que abraza (`envueltos`), afuera un
  desvío o rodillo de retorno (`apoyos_fuera`); el abrazamiento es el ángulo que barre la línea
  media en contacto con ella.
- **Comba** sólo en los tramos RECTOS del modelo (`rectos`) del ramal de retorno y libres por
  debajo: la misma de `ruta_faja._vano` (CEMA 2 %, la tensión, la holgura con lo de abajo), con
  las secciones reales de las piezas como obstáculos.

Sin un lazo cerrado en la sección (una banda hecha como caja, o tramos que no se funden), devuelve
None y el llamador cae al casco convexo de siempre.
"""

from __future__ import annotations

import math

import numpy as np

from .ruta_faja import VANO_MIN_MM, PiezaPlano, RutaFaja, _perfil, _vano

#: Un punto a menos de esto (mm) de la cuerda sigue en el mismo tramo recto.
TOL_RECTO_MM = 0.2
#: Holgura (mm) de contacto: una pieza a esta distancia de la cara de la banda la toca.
TOL_CONTACTO_MM = 1.0
#: Espesor de banda creíble (mm).
ESPESOR_MIN, ESPESOR_MAX = 0.1, 50.0


def area(pts) -> float:
    p = np.asarray(pts, float)
    if len(p) < 3:
        return 0.0
    q = np.roll(p, -1, axis=0)
    return 0.5 * float(np.sum(p[:, 0] * q[:, 1] - q[:, 0] * p[:, 1]))


def antihoraria(pts) -> np.ndarray:
    """Los puntos sin repetidos consecutivos (ni el cierre), en sentido antihorario."""
    p = np.asarray(pts, float).reshape(-1, 2)
    if len(p) and np.allclose(p[0], p[-1]):
        p = p[:-1]
    if len(p) > 1:
        paso = np.hypot(*(np.roll(p, -1, axis=0) - p).T)
        p = p[paso > 1e-6]
    return p[::-1].copy() if area(p) < 0 else p


def distancia_polilinea(p: np.ndarray, poli: np.ndarray, cerrada: bool = True):
    """(distancia, índice del segmento, punto más cercano) de cada punto de `p` (N, 2) a la
    polilínea `poli` (M, 2). Por bloques: N·M sin agotar la memoria."""
    a, b = (poli, np.roll(poli, -1, axis=0)) if cerrada else (poli[:-1], poli[1:])
    ab = b - a
    l2 = np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-18)
    d = np.empty(len(p))
    k = np.empty(len(p), dtype=int)
    q = np.empty((len(p), 2))
    paso = max(1, 2_000_000 // max(1, len(a)))
    for i0 in range(0, len(p), paso):
        pp = p[i0:i0 + paso]
        ap = pp[:, None, :] - a[None, :, :]
        t = np.clip(np.einsum("nmj,mj->nm", ap, ab) / l2, 0.0, 1.0)
        proy = a[None, :, :] + t[..., None] * ab[None, :, :]
        dd = np.hypot(*(pp[:, None, :] - proy).transpose(2, 0, 1))
        j = np.argmin(dd, axis=1)
        filas = np.arange(len(pp))
        d[i0:i0 + paso], k[i0:i0 + paso] = dd[filas, j], j
        q[i0:i0 + paso] = proy[filas, j]
    return d, k, q


def normales_afuera(p: np.ndarray) -> np.ndarray:
    """Normal hacia AFUERA (derecha del recorrido antihorario) en cada vértice de un lazo:
    promedio de la de sus dos tramos."""
    t1 = p - np.roll(p, 1, axis=0)
    t2 = np.roll(p, -1, axis=0) - p
    t1 /= np.maximum(np.hypot(*t1.T), 1e-12)[:, None]
    t2 /= np.maximum(np.hypot(*t2.T), 1e-12)[:, None]
    t = t1 + t2
    n = np.stack([t[:, 1], -t[:, 0]], axis=1)
    return n / np.maximum(np.hypot(*n.T), 1e-12)[:, None]


def linea_media(exterior, huecos) -> tuple[np.ndarray, float]:
    """(línea media antihoraria, espesor) de la sección de una banda: ver el docstring."""
    ext = antihoraria(exterior)
    inner = [antihoraria(h) for h in huecos if len(h) >= 3]
    if len(ext) < 3 or not inner:
        return np.empty((0, 2)), 0.0
    d = np.full(len(ext), np.inf)
    q = np.zeros_like(ext)
    for h in inner:
        dh, _k, qh = distancia_polilinea(ext, h)
        mejor = dh < d
        d[mejor], q[mejor] = dh[mejor], qh[mejor]
    t = float(np.median(d))
    if not ESPESOR_MIN <= t <= ESPESOR_MAX:
        return np.empty((0, 2)), 0.0
    media = 0.5 * (ext + q)
    raros = np.abs(d - t) > 0.5 * t
    if np.any(raros):
        media[raros] = ext[raros] - normales_afuera(ext)[raros] * (t / 2.0)
    return antihoraria(media), t


def _colineal(q: np.ndarray, i: int, k: int) -> bool:
    a, b = q[i], q[k]
    ab = b - a
    largo = math.hypot(*ab)
    if largo < 1e-9:
        return False
    tramo = q[i:k + 1] - a
    lejos = np.abs(tramo[:, 0] * ab[1] - tramo[:, 1] * ab[0]) / largo
    avance = (tramo @ ab) / largo
    return bool(np.all(lejos <= TOL_RECTO_MM) and np.all(np.diff(avance) > -TOL_RECTO_MM))


def rectos(media: np.ndarray) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """(lazo cerrado Q, tramos rectos [(i, j)] en índices de Q) de una línea media antihoraria.
    Q empieza en el vértice que más gira (así ningún tramo recto queda partido en el cierre) y
    repite el primero al final (len(Q) = n + 1). Un tramo es recto si todos sus puntos quedan a
    ≤ `TOL_RECTO_MM` de su cuerda, avanzando; los de menos de `VANO_MIN_MM` no cuentan."""
    n = len(media)
    t1 = media - np.roll(media, 1, axis=0)
    t2 = np.roll(media, -1, axis=0) - media
    giro = np.abs(np.arctan2(t1[:, 0] * t2[:, 1] - t1[:, 1] * t2[:, 0], np.einsum("ij,ij->i", t1, t2)))
    k0 = int(np.argmax(giro))
    q = np.vstack([np.roll(media, -k0, axis=0), np.roll(media, -k0, axis=0)[:1]])
    out, i = [], 0
    while i < n:
        j = i + 1
        while j < n and _colineal(q, i, j + 1):
            j += 1
        if math.dist(q[i], q[j]) >= VANO_MIN_MM:
            out.append((i, j))
        i = j
    return q, out


def dentro_lazo(p, poli: np.ndarray) -> bool:
    """Par-impar: ¿el punto cae dentro del polígono?"""
    x, y = p
    a, b = poli, np.roll(poli, -1, axis=0)
    cruza = (a[:, 1] > y) != (b[:, 1] > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xc = a[:, 0] + (y - a[:, 1]) * (b[:, 0] - a[:, 0]) / (b[:, 1] - a[:, 1])
    return bool(np.count_nonzero(cruza & (x < xc)) % 2)


def _barrido_deg(lazo: np.ndarray, c: np.ndarray, r_toque: float) -> tuple[float, int]:
    """(ángulo que barre el lazo en contacto con el círculo, primer vértice en contacto)."""
    rel = lazo - c
    toca = np.hypot(*rel.T) <= r_toque
    if not np.any(toca):
        return 0.0, int(np.argmin(np.hypot(*rel.T)))
    sig = np.roll(rel, -1, axis=0)
    ambos = toca & np.roll(toca, -1)
    ang = np.abs(np.arctan2(rel[:, 0] * sig[:, 1] - rel[:, 1] * sig[:, 0], np.einsum("ij,ij->i", rel, sig)))
    return math.degrees(float(np.sum(ang[ambos]))), int(np.argmax(toca))


def ruta_modelo(banda: PiezaPlano, piezas: list[PiezaPlano], seccion: dict | None, *,
                obstaculos: dict | None = None, peso_n_mm: float | None = None,
                tension_n: float | None = None) -> RutaFaja | None:
    """La ruta de la línea media que sale de la sección del modelo (ver el docstring del módulo),
    o None si la sección no da un lazo cerrado. `obstaculos`: {pieza: [(u, w)]} con los puntos de
    sus secciones reales (las que da `services/marcha_visual`); sin ellos, su encuadre."""
    if not seccion or not seccion.get("huecos"):
        return None
    media, t = linea_media(seccion["ext"], seccion["huecos"])
    if len(media) < 3:
        return None
    q, tramos_rectos = rectos(media)
    lazo = q[:-1]
    envueltos, fuera = [], []
    for p in piezas:
        if not p.redonda or p.pieza == banda.pieza:
            continue
        c = np.asarray(p.centro, float)
        r_toque = p.radio + t / 2.0 + TOL_CONTACTO_MM
        d, _k, _q = distancia_polilinea(c[None, :], lazo)
        if d[0] > r_toque:
            continue
        barrido, k0 = _barrido_deg(lazo, c, r_toque)
        e = {"pieza": p.pieza, "u": float(c[0]), "w": float(c[1]), "r": p.radio,
             "abrazamiento_deg": round(barrido, 1)}
        (envueltos if dentro_lazo(c, lazo) else fuera).append((k0, e))
    adentro = {e["pieza"] for _k, e in envueltos}
    obst_puntos = dict(obstaculos or {})
    for p in piezas:
        if p.pieza != banda.pieza and p.pieza not in obst_puntos:
            obst_puntos[p.pieza] = _perfil(p)
    nombres = [k for k in obst_puntos if k not in adentro and k != banda.pieza]
    obst = [obst_puntos[k] for k in nombres]
    inicio = {i: j for i, j in tramos_rectos}
    puntos, tramos, k = [], [], 0
    n = len(lazo)
    while k < n:
        puntos.append((float(q[k][0]), float(q[k][1])))
        j = inicio.get(k)
        if j is None:
            k += 1
            continue
        p0, p1 = tuple(q[k]), tuple(q[j])
        normal_w = -(p1[0] - p0[0]) / math.dist(p0, p1)
        if normal_w < -0.5:   # ramal de retorno: cuelga
            interior, vanos, _usados = _vano(p0, p1, t, nombres, peso_n_mm, tension_n, obst)
            puntos += [(float(a), float(b)) for a, b in interior]
            tramos += vanos
        k = j
    largo = sum(math.dist(puntos[i], puntos[(i + 1) % len(puntos)]) for i in range(len(puntos)))
    combables = [(i, j) for i, j in tramos_rectos if -(q[j][0] - q[i][0]) / math.dist(q[i], q[j]) < -0.5]
    return RutaFaja(puntos=puntos, espesor=t, largo_mm=largo,
                    envueltos=[e for _k, e in sorted(envueltos, key=lambda x: x[0])],
                    apoyos_fuera=[e for _k, e in sorted(fuera, key=lambda x: x[0])],
                    tramos=tramos, modelo=[(float(a), float(b)) for a, b in lazo],
                    combables=combables, origen="seccion")
