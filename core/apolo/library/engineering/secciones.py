"""Propiedades de sección (A, I y W por eje) de las familias cortables del catálogo.

Las consume la viga continua (`viga_continua.py`) para la flecha y la tensión de flexión de
las vigas de un bastidor ([flecha-de-bastidor](../../../../docs/plans/flecha-de-bastidor.md)).
PURO: recibe el `builder` y los `params` de una ficha del catálogo, nunca un `Document`.

Ejes LOCALES del builder (los perfiles se extruyen en Z; la sección vive en XY):
  - `i_x` = inercia respecto al eje local X → flexión con la carga en Y (el canto de la
    sección es su medida en Y: `height` del tubo, `h` del canal y de la viga I);
  - `i_y` = respecto al eje local Y → carga en X;
  - `w_*` = módulo resistente ELÁSTICO mínimo (I / distancia a la fibra más alejada);
  - `i_min` = eje principal débil: igual a min(i_x, i_y) salvo en el ángulo, cuyo eje
    principal está a 45° (un ángulo libre de girar flecta alrededor de él).

Fuentes, de mejor a peor:
  1. TABLA de la norma del perfil laminado (EN 10056-1 ángulo, DIN 1026-1 UPN, EN 10365 IPE),
     con acuerdos de raíz y de borde: sólo si los params coinciden con la designación.
  2. HSS ASTM A500 (tubos): geometría con el espesor de DISEÑO t = 0.93·t_nominal (AISC 360-16
     §B4.2) y radio exterior de esquina 2·t (convención del AISC Steel Construction Manual,
     parte 1): reproduce las tablas del AISC a ±1 % (lo prueba el test).
  3. GEOMETRÍA prismática sin acuerdos (params editados, fuera de tabla), declarada en `fuente`.
     Medido contra la tabla en toda la serie: IPE 3–5 % bajo (conservador); UPN eje fuerte y
     ángulo 1–4 % sobre; UPN eje DÉBIL 12–15 % sobre (el ala cónica es más delgada en la punta):
     no conservador, pero una viga de bastidor flecta por el eje fuerte.
Sin sección determinable (perfil ranurado de aluminio: la inercia depende del fabricante y el
modelo es macizo) → `None` con su motivo en `SIN_SECCION`; jamás se inventa un número.

Unidades: mm, mm², mm³, mm⁴.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Espesor de diseño de un HSS ERW (ASTM A500) = 0.93 × nominal (AISC 360-16 §B4.2).
HSS_FACTOR_ESPESOR = 0.93
NORMA_HSS = "ASTM A500 · AISC 360-16 §B4.2 (t = 0.93·t_nom, r_ext = 2·t)"

#: Familias cortables SIN sección determinable y por qué (la regla lo declara en `no_aplica`).
SIN_SECCION = {
    "profile": "perfil ranurado de aluminio: la inercia depende del fabricante y el modelo "
               "es macizo (sobrestimaría I); declara la sección del fabricante",
    "leg": "pata regulable: columna con placa, no viga (la cubre el pandeo de patas)",
}


@dataclass(frozen=True)
class Seccion:
    """Propiedades de una sección recta en los ejes locales del builder (ver el módulo)."""

    area_mm2: float
    i_x_mm4: float
    i_y_mm4: float
    w_x_mm3: float
    w_y_mm3: float
    i_min_mm4: float
    fuente: str  # "tabla" | "hss" | "geometría"
    norma: str


# ── Tablas de norma (cm, cm², cm³, cm⁴, como las publica la norma) ─────────────────────────

#: Ángulo de lados iguales EN 10056-1, por (lado, espesor) en mm:
#: A, I (= Iy = Iz, ejes paralelos a las alas), Wel, e (centroide desde el talón), Iv (mínima).
_ANGULOS = {
    (25, 3): {"A": 1.42, "I": 0.80, "W": 0.45, "e": 0.72, "Iv": 0.33},
    (30, 3): {"A": 1.74, "I": 1.40, "W": 0.65, "e": 0.84, "Iv": 0.58},
    (40, 4): {"A": 3.08, "I": 4.47, "W": 1.55, "e": 1.12, "Iv": 1.86},
    (50, 5): {"A": 4.80, "I": 11.0, "W": 3.05, "e": 1.40, "Iv": 4.59},
    (60, 6): {"A": 6.91, "I": 22.8, "W": 5.29, "e": 1.69, "Iv": 9.43},
    (75, 6): {"A": 8.73, "I": 45.8, "W": 8.41, "e": 2.05, "Iv": 18.9},
    (80, 8): {"A": 12.3, "I": 72.2, "W": 12.6, "e": 2.26, "Iv": 29.9},
    (100, 10): {"A": 19.2, "I": 177.0, "W": 24.6, "e": 2.82, "Iv": 73.0},
}

#: Canal UPN DIN 1026-1, por altura h (mm): (b, tw, tf) nominales y A, Iy/Wy (eje fuerte, el
#: del alma), Iz/Wz (eje débil), e (centroide desde el dorso del alma).
_UPN = {
    80: {"dims": (45, 6, 8), "A": 11.0, "Iy": 106.0, "Wy": 26.5, "Iz": 19.4, "Wz": 6.36, "e": 1.45},
    100: {"dims": (50, 6, 8.5), "A": 13.5, "Iy": 206.0, "Wy": 41.2, "Iz": 29.3, "Wz": 8.49, "e": 1.55},
    120: {"dims": (55, 7, 9), "A": 17.0, "Iy": 364.0, "Wy": 60.7, "Iz": 43.2, "Wz": 11.1, "e": 1.60},
    140: {"dims": (60, 7, 10), "A": 20.4, "Iy": 605.0, "Wy": 86.4, "Iz": 62.7, "Wz": 14.8, "e": 1.75},
    160: {"dims": (65, 7.5, 10.5), "A": 24.0, "Iy": 925.0, "Wy": 116.0, "Iz": 85.3, "Wz": 18.3,
          "e": 1.84},
    180: {"dims": (70, 8, 11), "A": 28.0, "Iy": 1350.0, "Wy": 150.0, "Iz": 114.0, "Wz": 22.4,
          "e": 1.92},
    200: {"dims": (75, 8.5, 11.5), "A": 32.2, "Iy": 1910.0, "Wy": 191.0, "Iz": 148.0, "Wz": 27.0,
          "e": 2.01},
}

#: Viga IPE EN 10365, por altura h (mm): (b, tw, tf) nominales y A, Iy/Wy (fuerte), Iz/Wz.
_IPE = {
    80: {"dims": (46, 3.8, 5.2), "A": 7.64, "Iy": 80.1, "Wy": 20.0, "Iz": 8.49, "Wz": 3.69},
    100: {"dims": (55, 4.1, 5.7), "A": 10.32, "Iy": 171.0, "Wy": 34.2, "Iz": 15.92, "Wz": 5.79},
    120: {"dims": (64, 4.4, 6.3), "A": 13.21, "Iy": 317.8, "Wy": 52.96, "Iz": 27.67, "Wz": 8.65},
    140: {"dims": (73, 4.7, 6.9), "A": 16.43, "Iy": 541.2, "Wy": 77.32, "Iz": 44.92, "Wz": 12.31},
    160: {"dims": (82, 5.0, 7.4), "A": 20.09, "Iy": 869.3, "Wy": 108.7, "Iz": 68.31, "Wz": 16.66},
    180: {"dims": (91, 5.3, 8.0), "A": 23.95, "Iy": 1317.0, "Wy": 146.3, "Iz": 100.9, "Wz": 22.16},
    200: {"dims": (100, 5.6, 8.5), "A": 28.48, "Iy": 1943.0, "Wy": 194.3, "Iz": 142.4, "Wz": 28.47},
}

NORMA_ANGULO = "EN 10056-1 (ángulo de lados iguales)"
NORMA_UPN = "DIN 1026-1 (canal UPN)"
NORMA_IPE = "EN 10365 (viga IPE)"


# ── Geometría ─────────────────────────────────────────────────────────────────────────────


def seccion_rectangulos(rects, fuente: str = "geometría", norma: str = "geometría prismática") -> Seccion:
    """Sección compuesta por rectángulos que NO se solapan, cada uno `(cx, cy, ancho, alto)`.

    I respecto a los ejes centroidales paralelos a X e Y; W con la fibra más alejada del
    centroide; `i_min` con el producto de inercia (ejes principales)."""
    a = sum(w * h for _, _, w, h in rects)
    if a <= 0:
        raise ValueError("sección sin área")
    cx = sum(x * w * h for x, _, w, h in rects) / a
    cy = sum(y * w * h for _, y, w, h in rects) / a
    ix = sum(w * h**3 / 12.0 + w * h * (y - cy) ** 2 for _, y, w, h in rects)
    iy = sum(h * w**3 / 12.0 + w * h * (x - cx) ** 2 for x, _, w, h in rects)
    ixy = sum(w * h * (x - cx) * (y - cy) for x, y, w, h in rects)
    c_y = max(max(abs(y + h / 2 - cy), abs(y - h / 2 - cy)) for _, y, _, h in rects)
    c_x = max(max(abs(x + w / 2 - cx), abs(x - w / 2 - cx)) for x, _, w, _ in rects)
    i_min = (ix + iy) / 2.0 - math.sqrt(((ix - iy) / 2.0) ** 2 + ixy**2)
    return Seccion(a, ix, iy, ix / c_y, iy / c_x, i_min, fuente, norma)


def _rect_redondeado(ancho: float, alto: float, r: float) -> tuple[float, float]:
    """(A, I_x) de un rectángulo macizo de esquinas redondeadas con radio r (centrado):
    cruz central + 4 cuartos de círculo, cada uno con su Steiner."""
    r = max(0.0, min(r, ancho / 2.0, alto / 2.0))
    area = ancho * alto - (4.0 - math.pi) * r * r
    ix = ancho * (alto - 2 * r) ** 3 / 12.0
    ix += 2.0 * ((ancho - 2 * r) * r**3 / 12.0 + (ancho - 2 * r) * r * (alto / 2.0 - r / 2.0) ** 2)
    a_q = math.pi * r * r / 4.0
    i_q = (math.pi / 16.0 - 4.0 / (9.0 * math.pi)) * r**4  # cuarto de círculo, eje propio
    d = alto / 2.0 - r + 4.0 * r / (3.0 * math.pi)
    ix += 4.0 * (i_q + a_q * d * d)
    return area, ix


def seccion_rect_hueca(ancho: float, alto: float, pared: float, r_ext: float = 0.0,
                       fuente: str = "geometría", norma: str = "geometría") -> Seccion:
    """Tubo rectangular hueco (`ancho` en X, `alto` en Y) con radio exterior `r_ext` y radio
    interior r_ext − pared (aristas vivas con 0). Pared ≥ media sección → macizo."""
    ancho, alto, pared = float(ancho), float(alto), float(pared)
    if ancho <= 0 or alto <= 0:
        raise ValueError("tubo sin sección")
    a_o, ix_o = _rect_redondeado(ancho, alto, r_ext)
    _, iy_o = _rect_redondeado(alto, ancho, r_ext)
    wi, hi = ancho - 2 * pared, alto - 2 * pared
    if pared > 0 and wi > 0 and hi > 0:
        r_i = max(r_ext - pared, 0.0)
        a_i, ix_i = _rect_redondeado(wi, hi, r_i)
        _, iy_i = _rect_redondeado(hi, wi, r_i)
    else:
        a_i = ix_i = iy_i = 0.0
    ix, iy = ix_o - ix_i, iy_o - iy_i
    return Seccion(a_o - a_i, ix, iy, ix / (alto / 2.0), iy / (ancho / 2.0), min(ix, iy), fuente, norma)


def seccion_tubo_redondo(od: float, pared: float, fuente: str = "geometría",
                         norma: str = "geometría") -> Seccion:
    """Tubo redondo (macizo con pared ≥ od/2 o pared ≤ 0): I = π/64·(D⁴ − d⁴)."""
    od = float(od)
    if od <= 0:
        raise ValueError("tubo sin sección")
    di = od - 2.0 * pared if 0 < pared < od / 2.0 else 0.0
    area = math.pi / 4.0 * (od**2 - di**2)
    i = math.pi / 64.0 * (od**4 - di**4)
    w = i / (od / 2.0)
    return Seccion(area, i, i, w, w, i, fuente, norma)


def seccion_hss_rect(ancho: float, alto: float, pared_nominal: float) -> Seccion:
    """HSS rectangular ASTM A500 con espesor de diseño y radio de esquina del AISC."""
    t = HSS_FACTOR_ESPESOR * float(pared_nominal)
    return seccion_rect_hueca(ancho, alto, t, r_ext=2.0 * t, fuente="hss", norma=NORMA_HSS)


def seccion_hss_redondo(od: float, pared_nominal: float) -> Seccion:
    """HSS redondo ASTM A500 con espesor de diseño 0.93·t (AISC 360-16 §B4.2)."""
    return seccion_tubo_redondo(od, HSS_FACTOR_ESPESOR * float(pared_nominal), fuente="hss",
                                norma="ASTM A500 · AISC 360-16 §B4.2 (t = 0.93·t_nom)")


def rects_angulo(lado: float, t: float):
    """Ángulo L del builder `angle`: ala horizontal abajo y vertical a la izquierda."""
    return [(0.0, -lado / 2 + t / 2, lado, t), (-lado / 2 + t / 2, t / 2, t, lado - t)]


def rects_canal(h: float, b: float, tw: float, tf: float):
    """Canal U del builder `channel`: alma en Y a la izquierda (x = −b/2), alas en X."""
    return [(-b / 2 + tw / 2, 0.0, tw, h - 2 * tf),
            (0.0, h / 2 - tf / 2, b, tf), (0.0, -h / 2 + tf / 2, b, tf)]


def rects_viga_i(h: float, b: float, tw: float, tf: float):
    """Viga doble T del builder `i_beam`: alma en Y centrada, alas en X."""
    return [(0.0, 0.0, tw, h - 2 * tf),
            (0.0, h / 2 - tf / 2, b, tf), (0.0, -h / 2 + tf / 2, b, tf)]


# ── Tabla → Seccion ───────────────────────────────────────────────────────────────────────


def _casa(a, b) -> bool:
    return all(abs(float(x) - float(y)) <= 1e-6 for x, y in zip(a, b, strict=True))


def _de_tabla_angulo(fila: dict) -> Seccion:
    i = fila["I"] * 1e4
    w = fila["W"] * 1e3
    return Seccion(fila["A"] * 100, i, i, w, w, fila["Iv"] * 1e4, "tabla", NORMA_ANGULO)


def _de_tabla_doble(fila: dict, norma: str) -> Seccion:
    """Canal/IPE: el eje fuerte de la norma (y, el del alma) es el X local del builder."""
    ix, iy = fila["Iy"] * 1e4, fila["Iz"] * 1e4
    return Seccion(fila["A"] * 100, ix, iy, fila["Wy"] * 1e3, fila["Wz"] * 1e3, min(ix, iy),
                   "tabla", norma)


def seccion_catalogo(builder: str, params: dict) -> Seccion | None:
    """Sección de una pieza cortable a partir de su familia (`builder`) y sus `params` de
    catálogo. None si la familia no tiene sección determinable (`SIN_SECCION`) o no es de
    perfil (rodillos, guardas, cadenas…)."""
    p = params or {}
    if builder == "rect_tube":
        return seccion_hss_rect(p["width"], p["height"], p.get("wall", 3.0))
    if builder == "round_tube":
        return seccion_hss_redondo(p["od"], p["wall"])
    if builder == "cylinder":
        return seccion_tubo_redondo(p["diameter"], 0.0, norma="sección maciza")
    if builder == "angle":
        lado, t = float(p["leg"]), float(p["t"])
        for (l_tab, t_tab), fila in _ANGULOS.items():
            if _casa((lado, t), (l_tab, t_tab)):
                return _de_tabla_angulo(fila)
        return seccion_rectangulos(rects_angulo(lado, t), norma=f"{NORMA_ANGULO}, sin acuerdos")
    if builder in ("channel", "i_beam"):
        h, b, tw, tf = (float(p[k]) for k in ("h", "b", "tw", "tf"))
        tabla, norma = (_UPN, NORMA_UPN) if builder == "channel" else (_IPE, NORMA_IPE)
        for h_tab, fila in tabla.items():
            if _casa((h, b, tw, tf), (h_tab, *fila["dims"])):
                return _de_tabla_doble(fila, norma)
        rects = rects_canal(h, b, tw, tf) if builder == "channel" else rects_viga_i(h, b, tw, tf)
        return seccion_rectangulos(rects, norma=f"{norma}, sin acuerdos")
    return None
