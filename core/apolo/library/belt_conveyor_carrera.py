"""La carrera del tensor de cola de `create_belt_conveyor` con el criterio 9 (plan faja-compacta,
D4). Puro: de las cotas a la carrera, sin OCCT.

Hasta el criterio 8 la unidad tensora UCT salía con el carro a MITAD de su carrera de ficha: la
re-revisión a ciegas de la mesa de sorteo midió 75 mm por lado contra lo que pide el lazo. Con el
criterio 9:

- **Lo que pide el lazo** es el control `tensor.carrera` de la puerta de publicación
  (`calidad/tensor.carrera_requerida`, la MISMA cuenta): el tensor recupera ≥ 1 % del largo del
  lazo (estiramiento de servicio de una banda de PVC de 2 capas, 0,5–1 %: CEMA y fabricantes de
  banda, la cifra que ya cita la puerta) + 20 mm de montaje. El tambor de cola, al correr `x`,
  alarga el lazo `factor·x` (las dos ramas libres que salen de él: factor = cos θ₁ + cos θ₂, ≈ 2),
  así que la carrera del TENSOR es esa cifra dividida por el factor.
- **UCT**: la de ficha tiene que alcanzar (si no, error con la salida); el carro sale al INICIO de
  su carrera (banda recién montada: el tornillo lo empuja hacia la cola al tensar), no centrado.
  La ranura del eje en el larguero y en la placa porta-tensor se corta con la carrera que pide el
  lazo (no la de ficha entera): con el carro al inicio, la ventana del marco dejaba ver 150 mm de
  ranura de 31 (un brazo, ISO 13857 tabla 4) y la puerta llegaba por ahí a la cuña de cola; la
  corta, el soporte del carro la tapa (en la de 4 m, entera).
- **Placa ranurada** (D3, `belt_conveyor_placa.py`): la ranura se dimensiona con esa carrera,
  redondeada a `PASO_CARRERA` hacia arriba.

En los dos, el tambor de cola queda en −largo/2 (la banda nueva) y su carrera va de ahí hacia la
cola: `Cotas.x_tc` es el CENTRO de esa carrera (−largo/2 − carrera/2); lo que antes rodeaba al
tambor con ±carrera/2 (ranura del larguero, guarda de cola, punta de la cama) rodea ahora ese centro.
"""

from __future__ import annotations

import math

from .belt_conveyor_cotas import LEG_W, Cotas
from .catalog import CATALOG

PASO_CARRERA = 5.0       # la carrera de la placa ranurada, redondeada a 5 mm hacia arriba
UCT_MARGEN = 15.0        # del marco de la UCT a la punta del larguero (el de la v4)


def radios_medios(c: Cotas) -> tuple[float, float]:
    """(cola, motriz): el radio de la LÍNEA MEDIA de la banda sobre cada tambor."""
    return c.r_c + c.t / 2.0, c.r_m + c.t / 2.0


def largo_lazo(c: Cotas) -> float:
    """Largo de la línea media del lazo abierto entre los dos tambores (el que mide la puerta con
    `calidad_tensores.largo_de_banda`): 2·√(D² − ΔR²) + π·(R₁ + R₂) + 2·ΔR·asin(ΔR/D)."""
    r1, r2 = radios_medios(c)
    d = math.hypot(2.0 * c.half, c.zm - c.zc)
    dr = r2 - r1
    return (2.0 * math.sqrt(d * d - dr * dr) + math.pi * (r1 + r2)
            + 2.0 * dr * math.asin(dr / d))


def factor_cola(c: Cotas) -> float:
    """Lo que alarga el lazo cada mm que el tambor de cola corre hacia la cola (eje X): la suma de
    los cosenos de las dos ramas libres con X (cada una a ±β de la línea de centros, de pendiente
    φ)."""
    r1, r2 = radios_medios(c)
    d = math.hypot(2.0 * c.half, c.zm - c.zc)
    phi = math.atan2(c.zm - c.zc, 2.0 * c.half)
    beta = math.asin((r2 - r1) / d)
    return math.cos(phi + beta) + math.cos(phi - beta)


def cuenta(c: Cotas) -> dict:
    """La carrera que pide el lazo al tensor de cola (para `Plan.calculos["carrera_tensor"]`)."""
    from .calidad.tensor import ESTIRAMIENTO_BANDA, MONTAJE_BANDA_MM, carrera_requerida

    lazo = largo_lazo(c)
    factor = factor_cola(c)
    pide_lazo = carrera_requerida("banda", lazo)
    pide = pide_lazo / factor
    return {
        "titulo": "Carrera del tensor de cola",
        "entradas": {"largo del lazo": f"{lazo:.0f} mm", "estiramiento": "1 %",
                     "montaje": f"{MONTAJE_BANDA_MM:g} mm", "factor del tambor": f"{factor:.3f}"},
        "formula": "carrera ≥ (1 %·L_lazo + 20 mm) / (cos θ₁ + cos θ₂)",
        "sustitucion": f"({ESTIRAMIENTO_BANDA:g}·{lazo:.0f} + {MONTAJE_BANDA_MM:g}) / {factor:.3f}",
        "resultado": f"carrera ≥ {pide:.1f} mm",
        "criterio": "la carrera del tensor recupera el estiramiento de servicio del lazo",
        "norma": "CEMA y fabricantes de banda (1 % + 20 mm), el control tensor.carrera",
        "lazo_mm": round(lazo, 1), "factor": round(factor, 4), "pide_lazo_mm": round(pide_lazo, 1),
        "pide_mm": round(pide, 1),
    }


def aplicar(c: Cotas) -> Cotas:
    """Las cotas del criterio 9 con tensor: la carrera elegida, el centro de la carrera, la punta
    del larguero de cola y la estación de patas de cola. ValueError si la carrera no alcanza."""
    from dataclasses import replace

    calc = cuenta(c)
    pide = calc["pide_mm"]
    if c.uct:
        carrera = c.carrera
        if carrera < pide - 1e-6:
            from .belt_conveyor_placa import CARRERA_MAX

            otra = (f"usa tensor «placa-ranurada» (su ranura se dimensiona hasta {CARRERA_MAX:g} mm)"
                    if pide <= CARRERA_MAX else "acorta la faja: ningún tensor de la plantilla da "
                    "esa carrera")
            raise ValueError(f"el lazo de {calc['lazo_mm']:.0f} mm pide {pide:.0f} mm de carrera "
                             f"al tensor de cola y la {c.uct} tiene {carrera:g}: {otra}")
        x_tc = -c.half - carrera / 2.0
        largo_uct = float(CATALOG[c.uct].params["L"])
        x0 = x_tc - largo_uct / 2.0 - UCT_MARGEN
        x_leg_t = x_tc + largo_uct / 2.0 + LEG_W / 2.0 + 10.0
        # la ranura del larguero, con la carrera que pide el lazo: con el carro al inicio la
        # ventana del marco dejaba ver la de ficha entera (31 mm, un brazo según ISO 13857)
        ranura = min(carrera, PASO_CARRERA * math.ceil(pide / PASO_CARRERA - 1e-9))
    else:
        from . import belt_conveyor_placa as pr

        carrera = PASO_CARRERA * math.ceil(pide / PASO_CARRERA - 1e-9)
        if carrera > pr.CARRERA_MAX:
            raise ValueError(f"el lazo de {calc['lazo_mm']:.0f} mm pide {pide:.0f} mm de carrera "
                             f"al tensor de cola y la placa ranurada llega a {pr.CARRERA_MAX:g} "
                             "(el perno empujador de catálogo): acorta la faja")
        x_tc = -c.half - carrera / 2.0
        c2 = replace(c, carrera=carrera)
        x0 = -c.half - carrera - pr.voladizo(c2)
        x_leg_t = pr.x_extremo_placa(c2) + LEG_W / 2.0 + 10.0
        ranura = carrera
    calc.update(carrera_mm=carrera, ranura_mm=ranura, tensor=c.uct or "placa-ranurada",
                ok=carrera >= pide - 1e-6, posicion="al inicio de la carrera (banda recién montada)")
    return replace(c, carrera=carrera, x_tc_=x_tc, x0=x0, x_leg_t=x_leg_t, cuenta_carrera=calc,
                   ranura_c=ranura)
