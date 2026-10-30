"""La CATENARIA de una banda modular (plan lo-fijo-que-gira, D3a): matemática PURA sobre la línea
media antihoraria del lazo en el plano (u, w) de la faja (la de `ruta_faja_modelo.linea_media`; la
OCCT la pone `services/calidad_catenaria.py`).

Una banda modular de plástico no lleva tensor: se tensa con su PESO, colgando libre en una zona de
comba justo después de la rueda motriz. La fuente es Intralox, *Installation, Maintenance, and
Troubleshooting Guide — Modular Plastic Conveyor Belts* (2024), p. 15 (`FUENTE`):

- fig. 17: la comba va justo después de la rueda motriz y se ajusta entre 1″ y 6″ (25,4–152 mm) a
  la temperatura de operación (`COMBA_MIN_MM`, `COMBA_MAX_MM`);
- «Break-in period»: en el rodaje la banda alarga del 0,5 % al 1 % de su largo (`RODAJE`); si
  alarga de más, se RETIRAN filas de módulos para volver a la comba.

Lo que mide este módulo:

- **La zona tras el motriz** (`zona_tras_motriz`): desde cada punta del arco de contacto con la
  rueda motriz se sigue la línea media mientras cuelga LIBRE: termina en el primer vértice que toca
  otra pieza (`apoyo`, lo mide el servicio) o donde la banda gira hacia AFUERA del lazo (pasa por
  encima de un desvío: el giro neto en una ventana de `VENTANA_MM` < −`GIRO_APOYO_DEG`; el
  escalón de dos tramos de un modelo hecho a mano gira poco y hacia los dos lados). Su comba es lo
  más que cae bajo la cuerda de sus dos puntas (hacia afuera del lazo); de los dos lados queda el
  que más cuelga: el lado TENSO no puede colgar.
- **Lo que absorbe la comba** (`absorbe_mm`): el largo que guarda una comba parabólica f sobre su
  vano l es ≈ 8·f²/(3·l); crecer de la comba modelada al tope de 152 mm absorbe
  8·(152² − f²)/(3·l). El resto del rodaje se recoge retirando filas, como pide la guía.
- **La parábola del tope** (`parabola`): por dónde pasaría la banda colgando 152 mm bajo su cuerda;
  la zona absorbe el rodaje si cuelga LIBRE hasta ahí (lo mide el servicio contra las piezas).
"""

from __future__ import annotations

import math

import numpy as np

from .fidelidad_faja import _dentro as dentro
from .ruta_faja import TOQUE_MM
from .ruta_faja_modelo import distancia_polilinea

#: Intralox, la guía de instalación (2024): de aquí salen la comba y el rodaje.
FUENTE = ("Intralox, Installation, Maintenance, and Troubleshooting Guide - Modular Plastic "
          "Conveyor Belts (2024), p. 15, fig. 17 «Proper catenary sag» y «Break-in period»: "
          "https://assets-us-01.kc-usercontent.com/19eb64b5-1815-003a-d268-e7109927ccad/"
          "1a1322d8-1d18-4c30-a73c-09319948df43/5009841%202%202024%20MPB%20Conveyor%20Belting%20"
          "Install%20Maintenance%20Troubles%20Manual%20EN.US.pdf")
COMBA_MIN_MM, COMBA_MAX_MM = 25.4, 152.0
RODAJE = 0.01
#: Largo (mm) de la ventana en que se mide el giro neto (los tramos de un modelo hecho a mano).
VENTANA_MM = 100.0
#: Un giro neto hacia AFUERA del lazo de más de esto (°) en la ventana es un apoyo por fuera.
GIRO_APOYO_DEG = 5.0
#: Lo primero (mm) tras el arco de la rueda motriz: su quiebre de salida no es un desvío (el
#: modelo hecho a mano abraza la rueda un poco de más y quiebra hacia la comba).
SALIDA_MM = 30.0
#: Un vértice a ≤ r·(1 + rel) + mm del centro del motriz está en su arco de contacto.
TOL_ARCO_MM, TOL_ARCO_REL = 1.0, 0.01


def giros(media: np.ndarray) -> np.ndarray:
    """El giro con signo (rad, + hacia adentro de un lazo antihorario) en cada vértice."""
    t1 = media - np.roll(media, 1, axis=0)
    t2 = np.roll(media, -1, axis=0) - media
    return np.arctan2(t1[:, 0] * t2[:, 1] - t1[:, 1] * t2[:, 0], np.einsum("ij,ij->i", t1, t2))


def _arco(media: np.ndarray, c: np.ndarray) -> tuple[int, int] | None:
    """(primer, último) vértice del arco de contacto con el motriz de centro `c`, o None."""
    n = len(media)
    dist = np.hypot(*(media - c).T)
    r = float(dist.min())
    toca = dist <= r * (1.0 + TOL_ARCO_REL) + TOL_ARCO_MM
    if toca.all():
        return None
    i0 = i1 = int(np.argmin(dist))
    while toca[(i0 - 1) % n]:
        i0 = (i0 - 1) % n
    while toca[(i1 + 1) % n]:
        i1 = (i1 + 1) % n
    return i0, i1


def _comba(media: np.ndarray, idx: list[int]) -> tuple[float, float, int]:
    """(comba bajo la cuerda hacia afuera, vano, vértice más bajo) de un tramo en orden antihorario."""
    a, b = media[idx[0]], media[idx[-1]]
    ab = b - a
    vano = math.hypot(*ab)
    if vano < 1e-9:
        return 0.0, 0.0, idx[0]
    afuera = np.array([ab[1], -ab[0]]) / vano   # derecha del recorrido antihorario
    d = (media[idx] - a) @ afuera
    k = int(np.argmax(d))
    return max(0.0, float(d[k])), vano, idx[k]


def zona_tras_motriz(media, centro, apoyo=None) -> dict | None:
    """La zona que cuelga libre junto al arco de contacto del motriz de centro `centro` (ver el
    docstring del módulo): {indices (antihorario), desde, hasta, bajo, comba_mm, vano_mm, fin}, o
    None si ninguno de los dos lados cuelga. `apoyo`: [bool] por vértice, ¿toca otra pieza?"""
    m = np.asarray(media, float)
    n = len(m)
    if n < 4:
        return None
    arco = _arco(m, np.asarray(centro, float))
    if arco is None:
        return None
    toca = np.zeros(n, bool) if apoyo is None else np.asarray(apoyo, bool)
    g = giros(m)
    tope = -math.radians(GIRO_APOYO_DEG)
    mejor = None
    for paso, inicio in ((+1, arco[1]), (-1, arco[0])):
        idx, fin, j, s = [inicio], "vuelta", inicio, 0.0
        ventana: list[tuple[float, float]] = []   # (largo recorrido, giro) de lo que va en la ventana
        for _ in range(n - 1):
            k, j = j, (j + paso) % n
            if j in (arco[0], arco[1]):
                break
            s += math.dist(m[k], m[j])
            if s > SALIDA_MM:   # el quiebre de la salida de la rueda no cuenta
                ventana = [(sv, gv) for sv, gv in ventana if sv > s - VENTANA_MM] + [(s, g[j])]
                if sum(gv for _sv, gv in ventana) < tope:
                    fin = "desvio"
                    break
            idx.append(j)
            if toca[j]:
                fin = "apoyo"
                break
        if len(idx) < 3 or fin == "vuelta":
            continue
        orden = idx if paso > 0 else idx[::-1]
        f, vano, bajo = _comba(m, orden)
        z = {"indices": orden, "desde": tuple(map(float, m[orden[0]])),
             "hasta": tuple(map(float, m[orden[-1]])), "bajo": tuple(map(float, m[bajo])),
             "comba_mm": f, "vano_mm": vano, "fin": fin}
        if mejor is None or f > mejor["comba_mm"]:
            mejor = z
    return mejor


def apoyos(media, espesor: float, caras: list, holgura: float = TOQUE_MM) -> np.ndarray:
    """[bool] por vértice: ¿la banda (línea media ± `espesor`/2) toca alguna de las `caras`
    ({ext, huecos} de las secciones de las otras piezas) con `holgura`?"""
    m = np.asarray(media, float)
    toca = np.zeros(len(m), bool)
    alcance = espesor / 2.0 + holgura
    for cara in caras:
        ext = np.asarray(cara["ext"], float)
        if len(ext) < 3:
            continue
        lo, hi = ext.min(axis=0) - alcance, ext.max(axis=0) + alcance
        cerca = np.all((m >= lo) & (m <= hi), axis=1) & ~toca
        if not cerca.any():
            continue
        p = m[cerca]
        lazos = [ext, *(np.asarray(h, float) for h in cara.get("huecos") or [] if len(h) >= 3)]
        d = np.min([distancia_polilinea(p, lz)[0] for lz in lazos], axis=0)
        adentro = dentro(p, ext)
        for h in lazos[1:]:
            adentro &= ~dentro(p, h)
        toca[np.flatnonzero(cerca)[(d <= alcance) | adentro]] = True
    return toca


def absorbe_mm(comba_mm: float, vano_mm: float, tope_mm: float = COMBA_MAX_MM) -> float:
    """Lo que la zona guarda de lazo al crecer su comba hasta `tope_mm`: 8·(tope² − f²)/(3·l)."""
    if vano_mm <= 0:
        return 0.0
    return max(0.0, 8.0 * (tope_mm ** 2 - comba_mm ** 2) / (3.0 * vano_mm))


def parabola(desde, hasta, comba_mm: float, paso_mm: float = 10.0) -> np.ndarray:
    """Los puntos de la línea media colgando `comba_mm` bajo la cuerda desde → hasta (hacia afuera
    de un lazo antihorario: la derecha del recorrido)."""
    a, b = np.asarray(desde, float), np.asarray(hasta, float)
    ab = b - a
    vano = math.hypot(*ab)
    if vano < 1e-9:
        return a[None, :]
    afuera = np.array([ab[1], -ab[0]]) / vano
    s = np.linspace(0.0, 1.0, max(2, int(math.ceil(vano / paso_mm)) + 1))
    return a + s[:, None] * ab + (4.0 * comba_mm * s * (1.0 - s))[:, None] * afuera


def _con_caras(p: np.ndarray, espesor: float) -> np.ndarray:
    """Los puntos de una polilínea abierta y los de sus dos caras (± espesor/2 por su normal)."""
    t = np.gradient(p, axis=0)
    t /= np.maximum(np.hypot(*t.T), 1e-12)[:, None]
    n = np.stack([t[:, 1], -t[:, 0]], axis=1) * (espesor / 2.0)
    return np.vstack([p, p + n, p - n])


def choques_al_tope(zona: dict, media, espesor: float, piezas: dict,
                    tope_mm: float = COMBA_MAX_MM) -> list[dict]:
    """Las piezas en que entra la banda si la zona cuelga `tope_mm` bajo su cuerda, más de lo que
    ya entra la banda modelada en esa zona (+ `TOQUE_MM`), la peor primero: [{pieza, mm}].
    `piezas`: {pieza: [caras]} de sus secciones en el plano."""
    from .fidelidad_faja import _profundidad

    m = np.asarray(media, float)
    tope = _con_caras(parabola(zona["desde"], zona["hasta"], tope_mm), espesor)
    modelo = _con_caras(m[zona["indices"]], espesor)
    out = []
    for pieza, caras in piezas.items():
        hondo = _profundidad(tope, caras)[0]
        if hondo <= TOQUE_MM:
            continue
        exceso = hondo - _profundidad(modelo, caras)[0]
        if exceso > TOQUE_MM:
            out.append({"pieza": pieza, "mm": round(exceso, 1)})
    return sorted(out, key=lambda x: -x["mm"])
