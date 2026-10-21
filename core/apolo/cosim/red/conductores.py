"""Resistencia y reactancia de un conductor de cobre por sección, largo y temperatura (plan V8.3 F3).

  - R a 20 °C: la resistencia MÁXIMA por km de IEC 60228, tabla 3 (conductores FLEXIBLES clase 5
    de cobre recocido sin estañar, los H05V-K / H07V-K y los cordones del catálogo). Es la que
    garantiza el fabricante: la caída que da es la del peor conductor que cumple la norma.
  - A otra temperatura: R(T) = R20·(1 + α20·(T − 20)), α20 = 0,00393 /K (IEC 60228, anexo B;
    el cobre recocido patrón de IEC 60028).
  - Temperatura por defecto: 70 °C, la máxima de servicio del aislamiento de PVC (IEC 60364-5-52,
    tabla 52.1, y el `temperatura_C` de las fichas de conductor del catálogo). Es la cota alta de
    la caída: un conductor frío cae menos. El calentamiento real del cable es de V8.6.
  - X: λ = 0,08 mΩ/m por conductor (IEC 60364-5-52, anexo G, el valor que la norma usa para la
    caída de tensión cuando no se conoce el tendido). Sólo en alterna; no se escala con la
    frecuencia (a la salida del variador X ≪ R en las secciones de BT: criterio de diseño).
  - Una sección que la tabla no trae se calcula con la resistividad del cobre patrón
    ρ20 = 1/58 Ω·mm²/m (IEC 60028) y se declara como hipótesis.
"""

from __future__ import annotations

#: IEC 60228, tabla 3 (clase 5, cobre sin estañar): resistencia máxima a 20 °C en Ω/km.
R20_CLASE5_OHM_KM = {
    0.5: 39.0, 0.75: 26.0, 1.0: 19.5, 1.5: 13.3, 2.5: 7.98, 4.0: 4.95, 6.0: 3.30, 10.0: 1.91,
    16.0: 1.21, 25.0: 0.780, 35.0: 0.554, 50.0: 0.386, 70.0: 0.272, 95.0: 0.206, 120.0: 0.161,
    150.0: 0.129, 185.0: 0.106, 240.0: 0.0801,
}
#: Coeficiente de temperatura del cobre a 20 °C (IEC 60228 anexo B, IEC 60028).
ALFA20_COBRE = 0.00393
#: Resistividad del cobre recocido patrón a 20 °C, Ω·mm²/m (IEC 60028).
RHO20_COBRE = 1.0 / 58.0
#: Temperatura de servicio por defecto: la máxima del PVC (IEC 60364-5-52, tabla 52.1).
TEMPERATURA_DEFECTO_C = 70.0
#: Reactancia por conductor, Ω/m (IEC 60364-5-52, anexo G: 0,08 mΩ/m).
LAMBDA_OHM_M = 0.08e-3


def r20_ohm_km(seccion_mm2: float, hipotesis: list[str] | None = None) -> float:
    """R máxima a 20 °C (Ω/km) de un conductor clase 5 de `seccion_mm2`."""
    if not seccion_mm2 or seccion_mm2 <= 0:
        raise ValueError(f"sección inválida: {seccion_mm2!r} mm²")
    for s, r in R20_CLASE5_OHM_KM.items():
        if abs(s - seccion_mm2) < 1e-9:
            return r
    if hipotesis is not None:
        hipotesis.append(f"{seccion_mm2:g} mm² no está en la tabla 3 de IEC 60228: R con ρ20 = 1/58 "
                         "Ω·mm²/m (IEC 60028), sin el margen de la norma")
    return RHO20_COBRE / seccion_mm2 * 1000.0


def resistencia(seccion_mm2: float, largo_m: float, temperatura_C: float = TEMPERATURA_DEFECTO_C,
                hipotesis: list[str] | None = None) -> float:
    """R (Ω) de UN conductor de cobre de `largo_m` a `temperatura_C`."""
    if largo_m < 0:
        raise ValueError(f"largo negativo: {largo_m!r} m")
    r20 = r20_ohm_km(seccion_mm2, hipotesis) * largo_m / 1000.0
    return r20 * (1.0 + ALFA20_COBRE * (temperatura_C - 20.0))


def reactancia(largo_m: float) -> float:
    """X (Ω) de UN conductor de `largo_m` en alterna (IEC 60364-5-52 anexo G)."""
    return LAMBDA_OHM_M * largo_m
