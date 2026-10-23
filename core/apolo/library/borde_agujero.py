"""Distancia al BORDE de un agujero de perno, medida en la geometría (EN 1993-1-8, tabla 3.3;
plan puerta-de-publicacion, F6). La usan la puerta de publicación (`services/calidad_bordes.py`)
y `join_bolted` (criterio 5) con la MISMA medida.

Qué se mide, en el plano MEDIO del tramo del eje del perno que cruza la pieza (la chapa, el ala
o la pared del tubo):

- desde el eje salen `N_RAYOS` rectas en el plano (`kernel/rayo.Rayos.cortes`, por paridad: el
  eje está en el hueco del taladro). El primer corte es la pared del agujero; el segundo, donde
  se acaba el material en esa dirección;
- **el agujero**: su ancho `d0` = el menor de a(θ) + a(θ + π) (un perno descentrado en su
  taladro da el Ø igual); largo/ancho > 1,15 → **ranura** (e3, e4 ≥ 1,5·d0); si no, redondo
  (e1, e2 ≥ 1,2·d0). Un taladro roscado (más angosto que el perno) mide con d0 = d nominal;
- **canto libre**: donde se acaba el material sólo es CANTO si la pieza ahí tiene el espesor de
  la chapa (el material a lo largo del eje, justo antes del corte, entre 0,5·t y 1,5·t + 0,6
  mm). La esquina de un tubo, el talón de un ángulo o un pliegue siguen en otra pared (más
  grueso): no son canto (la regla es del borde que se puede desgarrar, no del cambio de plano);
  la superficie de un eje que un perno cruza de lado a lado se afina hacia la tangente (más
  delgado): un eje no es una chapa. El borde del agujero de OTRO perno de la misma pieza
  tampoco: eso es el PASO (`paso_entre`);
- **e** = el ligamento más corto (corte del canto − pared del agujero) + d0/2: la distancia del
  centro del agujero al canto;
- un ANILLO coaxial (arandela, separador, buje: canto libre en todas las direcciones a la misma
  distancia ±15 %) no es una chapa unida: no se juzga;
- una **BARRA maciza** tampoco (`barra`): el tramo del perno en la pieza mide t ≥ 1,5·d0 y la
  sección por el eje del agujero es tan ancha como gruesa (su ancho más angosto en el plano,
  pared a pared pasando por el agujero, W ≤ 1,25·t). Es el eje redondo o la barra cuadrada que
  un perno atraviesa de lado a lado: el «Eje fijo Ø25 (roscado p/ perno)» del tensor, cuyo
  perno M12 tira según su propio eje. La tabla 3.3 es de CHAPAS y alas (t pequeño frente al
  ancho: el ligamento de la pared se aplasta y desgarra en su plano, EN 1993-1-8 § 3.5 y tabla
  3.4); el extremo de una barra a tracción falla de otro modo (la rosca se barre o el extremo
  se arranca). Umbrales: criterio de diseño, no de la norma (una chapa gruesa o una oreja de
  t < 1,5·d0, o con W > 1,25·t, sigue juzgándose). De una barra ROSCADA el control juzga en
  cambio la rosca enganchada (≥ 1·d en acero, VDI 2230: `calidad/bordes.py`); el
  arrancamiento del extremo de una barra con perno PASANTE queda fuera del alcance: se cuenta,
  no se juzga.

Sin dato no se inventa: el eje DENTRO del material (perno modelado sin su agujero) devuelve
`sin_agujero`; una abertura mucho mayor que el perno (> 2·d + 2 mm), `abertura`. El llamador
decide qué hace con eso (la puerta lo cuenta; `join_bolted` sólo mira lo medido).
"""

from __future__ import annotations

import math

E_MIN = 1.2       # e1, e2 ≥ 1,2·d0 (EN 1993-1-8, tabla 3.3)
E_RANURA = 1.5    # e3, e4 ≥ 1,5·d0 (agujero ranurado)
P_MIN = 2.2       # p1 ≥ 2,2·d0; p2 ≥ 2,4·d0 pide la dirección de la carga: se juzga la menor
N_RAYOS = 36
_RANURA = 1.15
_ANILLO = 1.15
BARRA_T = 1.5     # barra: tramo del perno t ≥ 1,5·d0 …
BARRA_W = 1.25    # … y sección tan ancha como gruesa, W ≤ 1,25·t (criterio de diseño)
_TOL = 0.05


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b, k=1.0):
    return (a[0] + k * b[0], a[1] + k * b[1], a[2] + k * b[2])


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def base_perp(eje):
    otro = (1.0, 0.0, 0.0) if abs(eje[0]) < 0.9 else (0.0, 1.0, 0.0)
    u = _unit(_cross(eje, otro))
    return u, _cross(eje, u)


def distancia_a_eje(q, punto, eje) -> float:
    w = _sub(q, punto)
    perp = _sub(w, (eje[0] * _dot(w, eje), eje[1] * _dot(w, eje), eje[2] * _dot(w, eje)))
    return math.sqrt(_dot(perp, perp))


def e_requerido(d0: float, forma: str) -> float:
    return (E_RANURA if forma == "ranura" else E_MIN) * d0


def medir_borde(rayos, punto, eje, t0: float, t1: float, d_nominal: float,
                otros=(), roscado: bool = False) -> dict:
    """La distancia al canto del agujero que el eje `punto + t·eje` (unitario) abre en el
    sólido de `rayos` (un `kernel.rayo.Rayos`), en el plano medio de [t0, t1]. `otros` =
    [(punto, eje, radio)] de los OTROS pernos de la misma pieza. Devuelve {estado:
    "medido" | "sin_agujero" | "abertura" | "anillo" | "barra" | "sin_medida", motivo, …};
    barra → {d0, espesor, ancho, roscado}; medido →
    {d0, forma, e (None = sin canto libre a menos de `alcance`), e_min, cumple, espesor,
    centro, hacia (dirección del canto más cercano)}."""
    tm, t = (t0 + t1) / 2.0, max(t1 - t0, 0.1)
    centro = _add(punto, eje, tm)
    macizo = rayos.dentro(centro)
    if macizo and not roscado:
        return {"estado": "sin_agujero", "motivo": "el eje del perno pasa por material: la "
                "pieza no tiene su agujero modelado"}
    alcance = 3.0 * d_nominal + 10.0
    u, v = base_perp(eje)
    dirs, pared, canto = [], [], []
    for k in range(N_RAYOS):
        ang = 2.0 * math.pi * k / N_RAYOS
        w = _add(_add((0.0, 0.0, 0.0), u, math.cos(ang)), v, math.sin(ang))
        cs = rayos.cortes(centro, w, 0.0, alcance)
        if macizo:  # taladro roscado macizo: la pared es el Ø nominal, el primer corte el canto
            cs = [d_nominal / 2.0, *cs] if cs and cs[0] > d_nominal / 2.0 else cs[:0]
        dirs.append(w)
        pared.append(cs[0] if cs else None)
        canto.append(cs[1] if len(cs) > 1 else None)
    mitad = N_RAYOS // 2
    anchos = [pared[k] + pared[k + mitad] for k in range(mitad)
              if pared[k] is not None and pared[k + mitad] is not None]
    if not anchos:
        return {"estado": "sin_medida", "motivo": "no se reconoce la pared del agujero"}
    ancho = min(anchos)
    if ancho > 2.0 * d_nominal + 2.0:
        return {"estado": "abertura", "motivo": f"el perno pasa por una abertura de "
                f"{ancho:.1f} mm, no por su agujero"}
    abierto = any(p is None for p in pared)
    forma = "ranura" if abierto or max(anchos) > _RANURA * ancho else "redondo"
    d0 = max(ancho, d_nominal)
    libres = []  # (ligamento, k)
    n_material = 0
    for k, (w, a, b) in enumerate(zip(dirs, pared, canto, strict=True)):
        if a is None:
            continue
        n_material += 1
        if b is None:
            continue
        q = _add(centro, w, b)
        if any(distancia_a_eje(q, p, e) <= r + 0.5 for p, e, r in otros):
            continue  # el canto es el agujero de otro perno: eso es el paso
        dentro = _add(centro, w, b - min(0.5, (b - a) / 2.0))
        lejos = 3.0 * t + 20.0
        arriba = rayos.cortes(dentro, eje, 0.0, lejos)
        abajo = rayos.cortes(dentro, (-eje[0], -eje[1], -eje[2]), 0.0, lejos)
        grueso = (arriba[0] if arriba else lejos) + (abajo[0] if abajo else lejos)
        if 0.5 * t <= grueso <= 1.5 * t + 0.6:
            libres.append((b - a, k))
    if libres and len(libres) == n_material == N_RAYOS:
        ligs = [x for x, _k in libres]
        if max(ligs) <= _ANILLO * min(ligs):
            return {"estado": "anillo", "motivo": "anillo coaxial al perno (arandela, "
                    "separador o buje): no es una chapa unida"}
    barra = _barra(canto, t, d0, roscado)
    if barra is not None:
        return barra
    e_min = e_requerido(d0, forma)
    base = {"estado": "medido", "motivo": "", "d0": round(d0, 2), "forma": forma,
            "e_min": round(e_min, 2), "espesor": round(t, 2),
            "centro": [round(x, 2) for x in centro]}
    if not libres:
        return {**base, "e": None, "cumple": True}
    lig, k = min(libres)
    e = lig + ancho / 2.0
    return {**base, "e": round(e, 2), "cumple": e >= e_min - _TOL,
            "hacia": [round(x, 4) for x in dirs[k]]}


def _barra(canto: list, t: float, d0: float, roscado: bool) -> dict | None:
    """`barra` si la pieza, en el agujero, es una barra maciza (t ≥ BARRA_T·d0 y su ancho más
    angosto pared a pared W ≤ BARRA_W·t); si no, None (chapa, ala, pared de tubo: se juzga)."""
    mitad = len(canto) // 2
    anchos = [canto[k] + canto[k + mitad] for k in range(mitad)
              if canto[k] is not None and canto[k + mitad] is not None]
    if not anchos or t < BARRA_T * d0 - _TOL:
        return None
    w = min(anchos)
    if w > BARRA_W * t + _TOL:
        return None
    sigue = ("se juzga su rosca enganchada (≥ k·d)" if roscado else
             "el arrancamiento del extremo con un perno pasante queda fuera del alcance")
    return {"estado": "barra", "motivo": f"barra maciza (t = {t:.1f} mm según el perno, ancho "
            f"{w:.1f} mm): la tabla 3.3 es de chapas y alas; {sigue}",
            "d0": round(d0, 2), "espesor": round(t, 2), "ancho": round(w, 2),
            "roscado": bool(roscado)}


def paso_entre(c1, eje, c2) -> float:
    """Distancia entre dos ejes paralelos (el paso), medida en el plano ⊥ al eje."""
    return distancia_a_eje(c2, c1, eje)
