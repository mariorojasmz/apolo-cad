"""¿La cinta que anima el visor ES la banda del modelo? (fabrica-de-publicaciones, ajuste D13b).

En marcha el visor no dibuja el sólido de la banda: dibuja una cinta (`ruta_faja` /
`ruta_faja_modelo`). Lo que validaron las interferencias y la puerta de entrega es el sólido, así
que la cinta se prueba contra él, siempre (la corren la marcha del visor y la fábrica). PURO:
recibe la ruta y las secciones planas que `services/marcha_visual.py` sacó con OCCT.

1. **Desvío**: la línea media de la cinta no se aparta de la del modelo más que `TOL_DESVIO_MM`,
   salvo la comba: en un tramo recto del ramal de retorno (`RutaFaja.combables`) puede salir
   HACIA AFUERA del lazo hasta el tope CEMA (2 % del tramo). Se mide en los dos sentidos (cinta →
   modelo y modelo → cinta), con las dos polilíneas muestreadas cada `PASO_MM`: un atajo en recta
   entre dos puntos que sí están sobre el modelo también se ve.
2. **Cruces**: ningún punto de la cinta (sus dos caras y la línea media, cada `PASO_MM`, en cada
   plano de corte a lo ancho) entra en otra pieza más de lo que entra el MODELO en esa misma pieza
   y plano, más `TOL_CONTACTO_MM`. Así los tambores que abraza y lo que la apoya (que el modelo ya
   toca) pasan, y lo que el modelo no toca —una guarda, la placa del drive— no se puede atravesar.

Sin línea media del modelo (respaldo del casco convexo) el desvío no se puede medir y se dice;
los cruces sí, y bastan para no publicar una cinta que atraviesa algo.
"""

from __future__ import annotations

import math

import numpy as np

from .ruta_faja import COMBA_CEMA, RutaFaja
from .ruta_faja_modelo import TOL_CONTACTO_MM, distancia_polilinea, normales_afuera

#: Lo que la cinta puede apartarse del modelo fuera de la comba (mm): la discretización.
TOL_DESVIO_MM = 1.0
#: Separación de las muestras a lo largo de la cinta y del modelo (mm).
PASO_MM = 5.0


def densificar(p: np.ndarray, paso: float = PASO_MM) -> tuple[np.ndarray, np.ndarray]:
    """(puntos de un lazo cerrado cada ≤ `paso`, índice del tramo del que sale cada uno)."""
    sig = np.roll(p, -1, axis=0)
    out, seg = [], []
    for k, (a, b) in enumerate(zip(p, sig)):
        n = max(1, int(math.ceil(math.dist(a, b) / paso)))
        s = np.arange(n)[:, None] / n
        out.append(a + s * (b - a))
        seg.append(np.full(n, k))
    return np.vstack(out), np.concatenate(seg)


def _dentro(pts: np.ndarray, poli: np.ndarray) -> np.ndarray:
    a, b = poli, np.roll(poli, -1, axis=0)
    x, y = pts[:, :1], pts[:, 1:2]
    cruza = (a[None, :, 1] > y) != (b[None, :, 1] > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xc = a[None, :, 0] + (y - a[None, :, 1]) * (b[None, :, 0] - a[None, :, 0]) / (b[None, :, 1] - a[None, :, 1])
    return (np.count_nonzero(cruza & (x < xc), axis=1) % 2) == 1


def _profundidad(pts: np.ndarray, caras: list) -> tuple[float, tuple | None]:
    """(lo más hondo que entra un punto en la región de `caras`, dónde). Cara = {ext, huecos}."""
    hondo, donde = 0.0, None
    for cara in caras:
        ext = np.asarray(cara["ext"], float)
        if len(ext) < 3:
            continue
        lo, hi = ext.min(axis=0), ext.max(axis=0)
        cand = pts[np.all((pts >= lo) & (pts <= hi), axis=1)]
        if not len(cand):
            continue
        huecos = [np.asarray(h, float) for h in cara.get("huecos") or [] if len(h) >= 3]
        adentro = _dentro(cand, ext)
        for h in huecos:
            adentro &= ~_dentro(cand, h)
        cand = cand[adentro]
        if not len(cand):
            continue
        d = np.min([distancia_polilinea(cand, lazo)[0] for lazo in [ext, *huecos]], axis=0)
        i = int(np.argmax(d))
        if d[i] > hondo:
            hondo, donde = float(d[i]), (float(cand[i][0]), float(cand[i][1]))
    return hondo, donde


def _bordes(caras: list) -> np.ndarray:
    lazos = [np.asarray(lz, float) for c in caras for lz in [c["ext"], *(c.get("huecos") or [])]
             if len(lz) >= 3]
    return np.vstack([densificar(lz)[0] for lz in lazos]) if lazos else np.empty((0, 2))


def desvio(ruta: RutaFaja) -> dict | None:
    """El peor exceso de la cinta sobre lo permitido respecto de la línea media del modelo."""
    if not ruta.modelo or len(ruta.puntos) < 3:
        return None
    m, r = np.asarray(ruta.modelo, float), np.asarray(ruta.puntos, float)
    n = len(m)
    comba = np.zeros(n)
    for i, j in ruta.combables:
        comba[i:j] = COMBA_CEMA * math.dist(m[i % n], m[j % n])
    rd, _sr = densificar(r)
    d, k, q = distancia_polilinea(rd, m)
    tramo = np.roll(m, -1, axis=0)[k] - m[k]
    afuera = np.einsum("ij,ij->i", rd - q, np.stack([tramo[:, 1], -tramo[:, 0]], axis=1)) > 0
    exceso = d - (TOL_DESVIO_MM + np.where(afuera, comba[k], 0.0))
    md, sm = densificar(m)
    d2, _k2, _q2 = distancia_polilinea(md, r)
    exceso2 = d2 - (TOL_DESVIO_MM + comba[sm])
    i, i2 = int(np.argmax(exceso)), int(np.argmax(exceso2))
    if exceso[i] >= exceso2[i2]:
        peor, donde, permitido = exceso[i], rd[i], d[i] - exceso[i]
    else:
        peor, donde, permitido = exceso2[i2], md[i2], d2[i2] - exceso2[i2]
    return {"desvio_mm": round(float(max(d.max(), d2.max())), 2),
            "exceso_mm": round(float(max(peor, 0.0)), 2),
            "permitido_mm": round(float(permitido), 2),
            "donde": [round(float(donde[0]), 1), round(float(donde[1]), 1)]}


def cruces(ruta: RutaFaja, cortes: list, nombres: dict | None = None) -> list[dict]:
    """Las piezas en las que la cinta entra más que el modelo (+ `TOL_CONTACTO_MM`), la peor
    primero. `cortes`: [{v, banda: [caras], piezas: {pieza: [caras]}}]."""
    p, _s = densificar(np.asarray(ruta.puntos, float))
    nrm = normales_afuera(p) * (ruta.espesor / 2.0)
    cinta = np.vstack([p, p + nrm, p - nrm])
    peores: dict = {}
    for c in cortes:
        borde = _bordes(c.get("banda") or [])
        for pieza, caras in (c.get("piezas") or {}).items():
            hondo, donde = _profundidad(cinta, caras)
            if hondo <= TOL_CONTACTO_MM:
                continue
            modelo = _profundidad(borde, caras)[0] if len(borde) else 0.0
            exceso = hondo - modelo
            if exceso > TOL_CONTACTO_MM and exceso > peores.get(pieza, {}).get("exceso_mm", 0.0):
                peores[pieza] = {"pieza": pieza, "nombre": (nombres or {}).get(pieza, pieza),
                                 "exceso_mm": round(exceso, 1), "cinta_mm": round(hondo, 1),
                                 "modelo_mm": round(modelo, 1), "v": round(float(c["v"]), 1),
                                 "donde": [round(donde[0], 1), round(donde[1], 1)]}
    return sorted(peores.values(), key=lambda x: -x["exceso_mm"])


def verificar_faja(ruta: RutaFaja, *, cortes: list | None = None,
                   nombres: dict | None = None) -> dict:
    """El veredicto (ver el docstring del módulo): {ok, origen, desvio, cruces, planos, motivo}."""
    dv = desvio(ruta)
    cx = cruces(ruta, cortes, nombres) if cortes else []
    motivos = []
    if cx:
        x = cx[0]
        motivos.append(
            f"la cinta animada atraviesa «{x['nombre']}» ({x['pieza']}) {x['exceso_mm']:g} mm más que "
            f"el modelo (entra {x['cinta_mm']:g} mm; el sólido de la banda, {x['modelo_mm']:g} mm), en "
            f"u = {x['donde'][0]:g}, w = {x['donde'][1]:g} mm del marco de la faja"
            + (f"; y {len(cx) - 1} pieza(s) más" if len(cx) > 1 else ""))
    if dv and dv["exceso_mm"] > 0:
        motivos.append(f"la cinta se aparta {dv['desvio_mm']:g} mm del contorno del modelo (lo "
                       f"permitido ahí es {dv['permitido_mm']:g} mm) cerca de u = {dv['donde'][0]:g}, "
                       f"w = {dv['donde'][1]:g} mm")
    return {"ok": not motivos, "origen": ruta.origen, "desvio": dv, "cruces": cx,
            "planos": len(cortes or []), "motivo": "; ".join(motivos) or None}
