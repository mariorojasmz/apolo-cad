"""Eje HEXAGONAL que se calza (F7 de `create_roller_conveyor`, plan
`docs/plans/plantilla-rodillos-cadena.md`, § Bitácora F7, E6–E7). Puro: cotas y cuentas, sin
`Document` ni OCCT; la receta que lo arma vive en `commands/receta_rodillos_eje.py`.

El eje es una barra hexagonal calibrada (`EJE_HEX` entrecaras, EN 10278) con las caras planas
VERTICALES, cortada a medida y con los dos extremos fresados a doble plano (`PLANOS`): el
extremo se calza en una RANURA abierta hacia arriba en el ala vertical de cada larguero (taladro
Ø`RANURA` en el fondo + dos cortes de sierra hasta el canto: taller sin láser ni punzonadora).
- No gira: las caras del doble plano quedan entre las paredes de la ranura (0,25 mm por lado).
- No corre: los hombros del hexágono quedan a `HOLGURA_HOMBRO` de la cara interior de cada ala.
- El rodillo gira sobre dos rodamientos de agujero hexagonal (`RODAMIENTO_HEX`); dos separadores
  de tubo (`SEPARADOR_D`) del ala al aro interior dejan el juego axial en `JUEGO_AXIAL` por lado.
- Se saca LEVANTÁNDOLO: el rodillo sale con su eje, sin tocar una tuerca.

MARCO: el de `rodillos_cadena.py` (Y a lo largo del eje, Z arriba); la sección del eje y de la
ranura, en el plano X-Z del rodillo con origen en su eje.
"""

from __future__ import annotations

import math

EJE_HEX = 11.0             # entrecaras de la barra hexagonal (EN 10278, tolerancia h11)
PLANOS = 8.0               # doble plano de cada extremo (lo que entra en la ranura)
RANURA = 8.5               # ancho de la ranura y Ø del taladro de su fondo: 0.25 mm por lado
SOBRE = 6.0                # el extremo asoma por fuera del ala (se ve calzado desde afuera)
HOLGURA_HOMBRO = 0.25      # hombro del hexágono ↔ cara interior del ala, por lado
RODAMIENTO_HEX = "6202-HEX11"
SEPARADOR_D = 17.2         # tubo EN 10255 DN10 × 2: agujero 13.2 > esquinas del hexágono 12.7
SEPARADOR_PARED = 2.0
HUECO_GIRA_R = 11.0        # buje y piñón: libran el aro interior del 6202 (Ø ≈ 21) y el separador


def r_esquinas(s: float = EJE_HEX) -> float:
    """Radio a las aristas de un hexágono de entrecaras `s`."""
    return s / math.sqrt(3.0)


def seccion_hex(s: float = EJE_HEX) -> list[tuple[float, float]]:
    """Vértices (x, z) del hexágono con las caras planas VERTICALES (normales ±X): las paredes
    de la ranura las aprietan, nunca una arista."""
    r = r_esquinas(s)
    return [(s / 2.0, -r / 2.0), (s / 2.0, r / 2.0), (0.0, r), (-s / 2.0, r / 2.0),
            (-s / 2.0, -r / 2.0), (0.0, -r)]


def _z_plano(s: float, p: float) -> float:
    """Alto (± z) de la cara del doble plano: donde la cara inclinada del hexágono corta x = p/2."""
    return r_esquinas(s) - (p / 2.0) / math.sqrt(3.0)


def seccion_extremo(s: float = EJE_HEX, p: float = PLANOS) -> list[tuple[float, float]]:
    """Vértices (x, z) del extremo con doble plano: el hexágono recortado a |x| ≤ p/2."""
    z1, r = _z_plano(s, p), r_esquinas(s)
    return [(p / 2.0, -z1), (p / 2.0, z1), (0.0, r), (-p / 2.0, z1), (-p / 2.0, -z1), (0.0, -r)]


def asiento(s: float = EJE_HEX, p: float = PLANOS, ancho: float = RANURA) -> float:
    """mm del eje del rodillo SOBRE el centro del fondo redondo de la ranura: el extremo apoya en
    sus dos aristas bajas (±p/2, −z1) sobre el arco de radio ancho/2 (se centra solo)."""
    z1, a = _z_plano(s, p), ancho / 2.0
    if a <= p / 2.0:
        raise ValueError(f"ranura de {ancho:g} mm: no entra el doble plano de {p:g}")
    return z1 - math.sqrt(a * a - (p / 2.0) ** 2)


def w_hex(s: float = EJE_HEX) -> float:
    """mm³: módulo resistente del hexágono a flexión con la carga VERTICAL (caras planas
    verticales: la fibra extrema es la arista de arriba o de abajo, a s/√3)."""
    a = r_esquinas(s)
    return 5.0 * math.sqrt(3.0) / 16.0 * a**4 / a


def _flexion_libre(rects, puntos) -> tuple[float, float]:
    """(I_eq, W_eq) de una sección de rectángulos (x, z, ancho, alto) a flexión VERTICAL libre de
    girar (flexión esviada de un ángulo sin arriostrar): I_eq = (Ix·Iz − Ixz²)/Iz y la fibra peor
    entre `puntos`. Sin acuerdos: sólo vale como COCIENTE entre dos secciones."""
    area = sum(w * h for _, _, w, h in rects)
    cx = sum((x + w / 2.0) * w * h for x, _, w, h in rects) / area
    cz = sum((z + h / 2.0) * w * h for _, z, w, h in rects) / area
    ix = sum(w * h**3 / 12.0 + w * h * (z + h / 2.0 - cz) ** 2 for _, z, w, h in rects)
    iz = sum(h * w**3 / 12.0 + w * h * (x + w / 2.0 - cx) ** 2 for x, _, w, h in rects)
    ixz = sum(w * h * (x + w / 2.0 - cx) * (z + h / 2.0 - cz) for x, z, w, h in rects)
    det = ix * iz - ixz**2
    peor = max(abs(iz * (pz - cz) - ixz * (px - cx)) / det for px, pz in puntos)
    return det / iz, 1.0 / peor


def factores_ranura(lado: float, t: float, alto_ranura: float, paso: float) -> tuple[float, float]:
    """(k_w, k_i): lo que la ranura le quita al ángulo de lados `lado` × `t` (ala vertical cortada
    `alto_ranura` desde su canto, una ranura de `RANURA` por paso).
    - k_w = W de la sección POR la ranura / W entero (σ: el momento máximo cae junto a una);
    - k_i = rigidez equivalente del tramo: flexibilidades en serie, (1 − f) entera + f por la
      ranura, con f = RANURA / paso (la flecha). Criterio de diseño, sin concentración de
      tensiones en el fondo (el arco de r = RANURA/2 la suaviza)."""
    def angulo(alto_v: float):
        rects = [(0.0, 0.0, lado, t), (0.0, t, t, alto_v - t)]
        puntos = [(0.0, 0.0), (lado, 0.0), (lado, t), (0.0, alto_v), (t, alto_v)]
        return _flexion_libre(rects, puntos)

    i_0, w_0 = angulo(lado)
    i_r, w_r = angulo(lado - alto_ranura)
    f = min(1.0, RANURA / paso)
    k_i = 1.0 / ((1.0 - f) + f * i_0 / i_r)
    return w_r / w_0, k_i


def tiro_vertical_cadena(d) -> dict:
    """La cuenta de la decisión E6 con cadena: ¿la tracción de una cadena puede SACAR un eje de
    su ranura abierta hacia arriba? Una cadena tira de cada piñón hacia el otro piñón de su lazo,
    sobre la línea de centros; sólo un tiro con componente HACIA ARRIBA mayor que el peso del
    rodillo lo levantaría. Devuelve el coseno director vertical de cada tiro (+ = hacia arriba):
    `lazos` (rodillo a rodillo, mismo h: 0) y `motriz` (último rodillo → piñón del motor)."""
    m = d.motriz
    if m is None:
        return {"lazos": None, "motriz": None}
    dx, dz = m.x - d.xs[-1], m.z - d.h_eje
    return {"lazos": 0.0, "motriz": dz / math.hypot(dx, dz)}
