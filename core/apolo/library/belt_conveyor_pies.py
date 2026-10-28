"""Pie nivelador de las patas de `create_belt_conveyor` con el criterio 7 (plan
faja-larga-en-tramos, F1b D8). Puro: cotas de la pila, sin OCCT.

Hasta el criterio 6 la placa de la pata (8 mm) llevaba un agujero liso Ø12 y la unión decía
«vástago M12 roscado en la placa»: un Ø12 no lleva rosca M12, y aunque se roscara, 8 mm de chapa
no dan el enganche. La cuenta: para que la rosca interior desarrolle la resistencia del vástago
se pide un enganche ≥ 0,8·d en acero (es la altura de la tuerca normal: DIN 934 M12, m = 10 mm,
y la que ISO 898-2 da por buena para la carga de prueba; criterio de diseño), y 8 mm < 0,8 × 12
= 9,6 mm. Además el vástago sube dentro del tubo de la pata: por arriba no hay lugar para la
contratuerca.

Por eso, con el criterio 7 (como el F6 de `create_roller_conveyor`, `rodillos_cadena_pies.py`):
la placa lleva un barreno de PASO (ISO 273 media, M12 → Ø13,5) y la tuerca DIN 934 de la rosca
del pie SOLDADA por debajo; la CONTRATUERCA de catálogo va en el vástago bajo la tuerca soldada,
entre ella y el disco, y se aprieta contra ella con una llave de boca desde el costado (traba la
altura nivelada). Pila desde el piso con el pie a la mitad de su recorrido: disco → vástago libre
→ contratuerca → tuerca soldada → placa → pata. Recorrido = vástago − 2 tuercas (en la punta
alta el vástago engrana las dos tuercas enteras; en la baja, el disco toca la contratuerca); se
publica como ± la mitad. La pata se acorta lo que crece la pila: el larguero queda donde estaba.
"""

from __future__ import annotations

from dataclasses import dataclass

from .catalog import CATALOG
from .engineering.bolts import clearance_hole_mm

ENGANCHE_MIN = 0.8       # × d: enganche de una rosca interior en acero (altura de la tuerca normal)


@dataclass(frozen=True)
class Pila:
    rosca: float
    tuerca: str            # ref de la soldada y de la contratuerca (DIN 934 de la rosca del pie)
    tuerca_t: float        # altura m
    tuerca_ac: float       # entrecaras
    barreno: float         # paso del vástago por la placa de la pata
    recorrido: float       # total: nivela ± recorrido/2
    z_contra: float        # centro de la contratuerca
    z_tuerca: float        # centro de la tuerca soldada
    z_placa: float         # cara inferior de la placa de la pata
    z_pata0: float         # cara superior de la placa = arranque del tubo de la pata


def rosca_en_la_placa(placa_t: float, rosca: float) -> bool:
    """¿Da la placa el enganche de la rosca del pie? (≥ `ENGANCHE_MIN`·d)."""
    return placa_t >= ENGANCHE_MIN * rosca


def pila(pie_ref: str, placa_t: float) -> Pila:
    """La pila de una pata con el pie `pie_ref` a la mitad de su recorrido."""
    s = CATALOG[pie_ref].params
    rosca, vastago, disco_t = float(s["rosca"]), float(s["altura"]), float(s["disco_t"])
    tuerca = f"TUERCA-M{rosca:g}"
    st = CATALOG[tuerca].params
    m = float(st["thickness"])
    recorrido = vastago - 2.0 * m
    z_contra0 = disco_t + recorrido / 2.0
    z_placa = z_contra0 + 2.0 * m
    return Pila(rosca=rosca, tuerca=tuerca, tuerca_t=m, tuerca_ac=float(st["across_flats"]),
                barreno=clearance_hole_mm(f"M{rosca:g}"), recorrido=recorrido,
                z_contra=z_contra0 + m / 2.0, z_tuerca=z_contra0 + 1.5 * m, z_placa=z_placa,
                z_pata0=z_placa + placa_t)
