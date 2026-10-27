"""Remaches ciegos (DIN 7337 forma A / ISO 15983, cuerpo inoxidable A2): el TAMAÑO que declara un
`fasten` («Ø4.8») y su capacidad a cortante (F3f de puerta-sin-sobrediseno).

Un remache no tiene métrica: su designación es el Ø del cuerpo (DIN 7337: «Ø4,8 × 10»). Con él
la unión remachada se dimensiona donde se dimensiona la de pernos (`report_uniones`).

Capacidad a cortante por remache y plano de corte (criterio de diseño, declarado):

    F_v = 0,6 · Rm · A_cuerpo / γM2

- la FORMA es la de EN 1993-1-8 tabla 3.4 (remaches: αv = 0,6 sobre la resistencia última,
  γM2 = 1,25); EN 1993-1-3 §8.3 pide para el remache CIEGO el valor de ensayo del fabricante:
  éste es su sustituto conservador hasta tener la ficha;
- Rm = 500 MPa: el mínimo del inoxidable 1.4301 (A2) recocido de EN 10088-3;
- A_cuerpo = el anillo del cuerpo TUBULAR, π/4·(d² − (0,6·d)²): el vástago del mandril que
  queda en el agujero no se cuenta (≈ 0,6·d en las fichas de remaches ciegos A2/A2).

El aplastamiento de las chapas (EN 1993-1-3 tabla 8.1) no se calcula aquí: la unión no conoce
su espesor; se declara en la hipótesis.
"""

from __future__ import annotations

import math
import re

#: Ø nominales de catálogo (`112_fijacion_ciega.yaml`, espejo de `fijacion.REMACHES`).
DIAMETROS_MM = (3.2, 4.0, 4.8, 6.4)
RM_CUERPO_MPA = 500.0      # EN 10088-3, 1.4301 recocido: Rm 500–700 MPa (el mínimo)
GAMMA_M2 = 1.25            # EN 1993-1-8 tabla 2.1
ALFA_V = 0.6               # EN 1993-1-8 tabla 3.4 (remaches)
MANDRIL_RELATIVO = 0.6     # Ø del vástago del mandril ≈ 0,6·d (no resiste: criterio)
NORMA = ("EN 1993-1-8 tabla 3.4 (forma) · EN 10088-3 (1.4301, Rm ≥ 500 MPa) · criterio de "
         "diseño: cuerpo tubular sin el mandril (EN 1993-1-3 §8.3 pide el ensayo del fabricante)")

_RE = re.compile(r"^[ØøΦ⌀](\d+(?:[.,]\d+)?)$")


def diametro(size) -> float | None:
    """El Ø del remache de un `size` declarado («Ø4.8» → 4.8), o None si no es un remache."""
    m = _RE.match(str(size or "").strip())
    return float(m[1].replace(",", ".")) if m else None


def designacion(d: float) -> str:
    """El `size` de un remache de Ø `d` («Ø4.8»): lo que `join_bolted` declara en su `fasten`."""
    return f"Ø{d:g}"


def area_cuerpo_mm2(d: float) -> float:
    return math.pi / 4.0 * d * d * (1.0 - MANDRIL_RELATIVO ** 2)


def capacidad_corte_n(size) -> float | None:
    """F_v (N) de UN remache de catálogo a cortante (ver el módulo); None fuera de tabla."""
    d = diametro(size)
    if d is None or not any(abs(d - x) < 1e-6 for x in DIAMETROS_MM):
        return None
    return ALFA_V * RM_CUERPO_MPA * area_cuerpo_mm2(d) / GAMMA_M2
