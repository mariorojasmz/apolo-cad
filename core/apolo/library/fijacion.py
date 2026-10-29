"""Qué fijación lleva una unión y de qué largo: el criterio de TALLER de `join_bolted`
(plan union-en-perfil-hueco, D1–D4). Puro: recibe espesores medidos (mm) y lo que la unión
sabe de la base; no ve geometría ni `Document`.

- **D1. La fijación sigue al acceso.** Sin acceso al lado de atrás (perfil cerrado u
  obstáculo) → fijación CIEGA: remache ciego DIN 7337 / ISO 15983 hasta M8. Más grande no hay
  ciega de catálogo: error que dice qué hacer.
- **D2. El largo sale del espesor real.** Perno = el comercial más corto que deja 2–3 hilos
  fuera de la tuerca: L ≥ grip + m + 2·paso (M6, grip 4,5 → M6×12).
- **D3** (el lado de la tuerca) lo resuelve el executor con la geometría.
- **D4. Madera → tornillo para madera** DIN 571 (cabeza hexagonal, se aprieta con llave) sin
  tuerca: la parte dentro de la madera es ≥ 2/3 del tornillo y no asoma por la otra cara.

Las medidas de las tablas son REFERENCIALES (envolventes de catálogo comercial), en espejo de
las fichas `REMACHE-*` (`112_fijacion_ciega.yaml`) y `TIRAFONDO-HEX-*`
(`113_tirafondos_hex.yaml`), como `bolts.py` lo es de `PERNO-HEX-*`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .engineering.bolts import (
    STD_LENGTHS,
    clearance_hole_mm,
    hex_head_mm,
    hex_nut_mm,
    nominal_diameter_mm,
)
from .engineering.threads import COARSE

# Remache ciego de cabeza plana (DIN 7337 forma A / ISO 15983): d → (Ø cabeza dk, alto k).
# dk ≈ 2·d, k ≈ 0,3·d; taladro = d + 0,1 (ISO 15983).
REMACHES: dict[float, tuple[float, float]] = {
    3.2: (6.5, 1.0), 4.0: (8.0, 1.2), 4.8: (9.5, 1.5), 6.4: (13.0, 1.9),
}
REMACHE_LARGOS = [6, 8, 10, 12, 14, 16, 18, 20, 25, 30]
# Agarre máximo de un remache de largo L: L − 0,7·d (tablas de fabricante: 4,8×10 → 6,5).
_AGARRE_LIBRE = 0.7
# métrica pedida → Ø del remache: el más grueso que reemplaza a ese perno (hasta M8)
_REMACHE_POR_METRICA = {"M6": 4.8, "M8": 6.4}

# Tornillo para madera de cabeza hexagonal DIN 571: d → (entrecaras s, alto de cabeza k).
TIRAFONDOS_HEX: dict[float, tuple[float, float]] = {
    6.0: (10.0, 4.0), 8.0: (13.0, 5.5), 10.0: (17.0, 7.0), 12.0: (19.0, 8.0),
}
TIRAFONDO_LARGOS = [16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 120, 140, 160]
_PENETRACION_BUENA = 6.0   # criterio de diseño: ≥ 6·d dentro de la madera (práctica EN 1995-1-1)
_RESPALDO_MADERA_MM = 2.0  # la punta queda ≥ 2 mm antes de la cara de atrás

# Arandela plana DIN 125-A / ISO 7089: métrica → (d1, d2, h). Espejo de `115_arandelas.yaml`
# (plan bom-de-compra-fiel D5: join_bolted la pone bajo la tuerca y el largo del perno la cuenta).
ARANDELAS_DIN125: dict[str, tuple[float, float, float]] = {
    "M6": (6.4, 12.0, 1.6), "M8": (8.4, 16.0, 1.6), "M10": (10.5, 20.0, 2.0),
    "M12": (13.0, 24.0, 2.5), "M14": (15.0, 28.0, 2.5), "M16": (17.0, 30.0, 3.0),
    "M18": (19.0, 34.0, 3.0), "M20": (21.0, 37.0, 3.0), "M24": (25.0, 44.0, 4.0),
}
# Tuerca autoblocante DIN 985 / ISO 10511: métrica → altura total h (el anillo de nylon incluido;
# la entrecaras es la de la DIN 934). Espejo de la familia `TUERCA-AB-*` de `109_tuercas.yaml`.
TUERCAS_DIN985: dict[str, float] = {
    "M6": 6.0, "M8": 8.0, "M10": 10.0, "M12": 12.0, "M14": 14.0, "M16": 16.0, "M18": 18.5,
    "M20": 20.0, "M24": 24.0,
}


@dataclass(frozen=True)
class Fijacion:
    """La fijación elegida para UN punto de la unión (todas las del patrón son iguales)."""

    tipo: str            # "perno" | "remache" | "tornillo_madera"
    ref: str             # ficha de catálogo
    nombre: str          # nombre de la pieza en la escena
    d: float             # Ø nominal
    largo: float         # largo bajo cabeza
    broca_anadida: float  # Ø del agujero en la pieza que se agrega
    broca_base: float    # Ø del agujero en la base (paso, remache o piloto en madera)
    cabeza_s: float      # entrecaras (perno, tornillo) o Ø de cabeza (remache)
    cabeza_k: float      # alto de la cabeza
    tuerca: str | None = None   # ficha de la tuerca (sólo el perno pasante)
    tuerca_s: float = 0.0
    tuerca_m: float = 0.0
    norma: str = ""
    nombre_tuerca: str = ""     # nombre de la pieza tuerca en la escena
    arandela: str | None = None  # ficha de la arandela bajo la tuerca (D5 de bom-de-compra-fiel)
    arandela_d1: float = 0.0
    arandela_d2: float = 0.0
    arandela_h: float = 0.0


def paso_grueso(size: str) -> float:
    d = nominal_diameter_mm(size)
    return COARSE.get(size, (0.125 * d, 0.0))[0]


def largo_perno(size: str, grip: float, estricto: bool = False,
                altura_tuerca: float | None = None) -> float:
    """D2: el largo comercial más corto que deja ≥ 2 hilos fuera de la tuerca (DIN 934, o la de
    `altura_tuerca`: la DIN 985 es más alta). `grip` incluye las arandelas que el perno cruza.

    `estricto` (criterio 3 de join_bolted, plan puerta-de-publicacion D3): el largo sale de los
    que el CATÁLOGO vende para `PERNO-HEX-{size}` y, si ninguno alcanza, ValueError accionable.
    Sin él (criterio 2, logs guardados) se conserva el respaldo silencioso al más largo de la
    serie (200 mm): un log viejo regenera igual y la puerta lo marca FALLA."""
    from .largos_perno import largo_comercial, largos_catalogo

    m = altura_tuerca if altura_tuerca is not None else hex_nut_mm(size)[1]
    minimo = grip + m + 2.0 * paso_grueso(size)
    if not estricto:
        return float(next((L for L in STD_LENGTHS if L >= minimo - 1e-6), STD_LENGTHS[-1]))
    ref = f"PERNO-HEX-{size}"
    largo = largo_comercial(ref, minimo)
    if largo is None:
        largos = largos_catalogo(ref)
        mayor = f"{size}×{largos[-1]:g}" if largos else f"ninguno (la ficha {ref} no declara largos)"
        raise ValueError(
            f"El agarre de {grip:.1f} mm pide un perno {size} de ≥ {minimo:.1f} mm (agarre + "
            f"tuerca + 2 hilos) y el más largo de catálogo es {mayor}: une piezas más delgadas "
            "en el eje del perno, sube la métrica o usa una varilla roscada con dos tuercas."
        )
    return float(largo)


def perno_pasante(size: str, grip: float, norma: str = "DIN 933",
                  estricto: bool = False, arandela: bool = False,
                  tuerca: str = "din934") -> Fijacion:
    """Perno hexagonal DIN 933 + tuerca DIN 934 (o autoblocante DIN 985 con `tuerca="din985"`),
    largo por D2 (`estricto`: ver `largo_perno`). Con `arandela`, una DIN 125-A bajo la tuerca y
    el largo la cuenta (plan bom-de-compra-fiel D5). Sin los dos, la fijación de siempre."""
    d = nominal_diameter_mm(size)
    s, k = hex_head_mm(size)
    ts, tm = hex_nut_mm(size)
    ref_tuerca, nombre_tuerca = f"TUERCA-{size}", f"Tuerca {size} DIN 934"
    if tuerca == "din985":
        if size not in TUERCAS_DIN985:
            raise ValueError(f"Sin tuerca autoblocante DIN 985 de catálogo para {size}.")
        tm = TUERCAS_DIN985[size]
        ref_tuerca, nombre_tuerca = f"TUERCA-AB-{size}", f"Tuerca autoblocante {size} DIN 985"
    a_d1 = a_d2 = a_h = 0.0
    if arandela:
        if size not in ARANDELAS_DIN125:
            raise ValueError(f"Sin arandela DIN 125-A de catálogo para {size}.")
        a_d1, a_d2, a_h = ARANDELAS_DIN125[size]
    largo = largo_perno(size, grip + a_h, estricto, altura_tuerca=tm)
    clear = clearance_hole_mm(size)
    return Fijacion("perno", f"PERNO-HEX-{size}", f"Perno {size}×{largo:g} {norma}", d, largo,
                    clear, clear, s, k, tuerca=ref_tuerca, tuerca_s=ts, tuerca_m=tm,
                    norma=norma, nombre_tuerca=nombre_tuerca,
                    arandela=f"ARANDELA-{size}" if arandela else None,
                    arandela_d1=a_d1, arandela_d2=a_d2, arandela_h=a_h)


def remache_ciego(size: str, grip: float, cavidad: float) -> Fijacion:
    """D1: remache ciego para una base sin acceso al lado de atrás. `cavidad` = espacio libre
    detrás de la pared (donde se forma la cabeza ciega). ValueError accionable si no hay uno."""
    d = _REMACHE_POR_METRICA.get(size)
    if d is None:
        raise ValueError(
            f"La base no tiene acceso por detrás (perfil cerrado u obstáculo) y no hay fijación "
            f"ciega de catálogo para {size}: el remache ciego llega hasta M8 (Ø6.4). Usa size "
            "M6 u M8, o une a una cara con acceso por detrás (una ménsula o placa soldada)."
        )
    dk, k = REMACHES[d]
    largo = next((L for L in REMACHE_LARGOS if L - _AGARRE_LIBRE * d >= grip - 1e-6), None)
    if largo is None:
        raise ValueError(
            f"El espesor a remachar ({grip:.1f} mm) supera el agarre del remache ciego Ø{d:g} más "
            f"largo ({REMACHE_LARGOS[-1]} mm): adelgaza la pieza que agregas o une en otra cara."
        )
    if largo - grip > cavidad - 0.5:
        raise ValueError(
            f"Detrás de la pared hay {cavidad:.1f} mm libres y la cabeza ciega del remache "
            f"Ø{d:g}×{largo} necesita {largo - grip:.1f} mm: une en una cara con más fondo."
        )
    return Fijacion("remache", f"REMACHE-{d:g}", f"Remache ciego Ø{d:g}×{largo} DIN 7337",
                    d, float(largo), round(d + 0.1, 2), round(d + 0.1, 2), dk, k,
                    norma="DIN 7337 / ISO 15983")


def tornillo_madera(size: str, t_anadida: float, t_madera: float) -> Fijacion:
    """D4: tornillo para madera DIN 571 a través de la pieza que se agrega y dentro de la
    madera. Largo comercial con penetración ≥ 2/3 del tornillo y sin asomar por detrás;
    entre los que cumplen, el más corto que penetra ≥ 6·d o, si la madera no da, el más largo."""
    d_nom = nominal_diameter_mm(size)  # M14+ → el más grueso de la tabla (Ø12)
    d = max((x for x in TIRAFONDOS_HEX if x <= d_nom), default=min(TIRAFONDOS_HEX))
    s, k = TIRAFONDOS_HEX[d]
    tope = t_madera - _RESPALDO_MADERA_MM
    validos = [L for L in TIRAFONDO_LARGOS
               if L - t_anadida >= 2.0 / 3.0 * L - 1e-6 and L - t_anadida <= tope + 1e-6]
    if not validos:
        raise ValueError(
            f"La madera ({t_madera:.0f} mm en el eje) no admite un tornillo DIN 571 Ø{d:g} con "
            f"2/3 de su largo dentro sin asomar por detrás (la pieza que agregas mide "
            f"{t_anadida:.1f} mm): usa un tornillo más delgado o une a una madera más gruesa."
        )
    buenos = [L for L in validos if L - t_anadida >= _PENETRACION_BUENA * d]
    largo = float(buenos[0] if buenos else validos[-1])
    piloto = round(0.7 * d * 2) / 2.0  # pretaladro ≈ 0,7·d (criterio de diseño)
    return Fijacion("tornillo_madera", f"TIRAFONDO-HEX-{d:g}",
                    f"Tornillo para madera Ø{d:g}×{largo:g} DIN 571", d, largo,
                    clearance_hole_mm(f"M{d:g}"), piloto, s, k, norma="DIN 571")
