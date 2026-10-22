"""Distancias de seguridad de ISO 13857:2019 (miembros superiores, personas ≥ 14 años).

- **Alcance general del brazo**: 850 mm (tabla 4, abertura > 20 mm en ranura: el brazo entra
  hasta el hombro). Un peligro a más de 850 mm del contorno de la máquina, por el camino libre
  de la sonda, está fuera de alcance.
- **Alcance a través de aberturas regulares** (tabla 4, columna RANURA, la más exigente: el
  modelo no distingue ranura de cuadrado o círculo): una abertura de ancho e deja llegar el dedo,
  la mano o el brazo hasta `sr` mm detrás de ella.

Criterio de diseño (declarado, no de la norma): las aberturas se miden con haces de sondas
paralelas (`sondas.py`), así que la clase de abertura es la del haz más ancho que pasa.
"""

from __future__ import annotations

ALCANCE_BRAZO_MM = 850.0
#: Tabla 6 (alcance alrededor de una estructura), brazo apoyado hasta la MUÑECA: la mano alcanza
#: R = 230 mm. El último tramo de las sondas con el brazo doblado (`services/calidad_codo.py`).
ALCANCE_DESDE_MUNECA_MM = 230.0
NORMA = ("ISO 13857:2019 tabla 4 (ranura) + alcance del brazo 850 mm + tabla 6 (brazo doblado: "
         "codo y muñeca)")

# (e_max de la fila, sr mínima) — tabla 4, ranura: e ≤ 4 → 2; 4 < e ≤ 6 → 10; … ; e > 20 → 850
TABLA4_RANURA: tuple[tuple[float, float], ...] = (
    (4.0, 2.0), (6.0, 10.0), (8.0, 20.0), (10.0, 80.0), (12.0, 100.0), (20.0, 120.0),
)
# anchos de los haces que miden la abertura (los límites de fila de la tabla)
CLASES_ABERTURA_MM: tuple[float, ...] = tuple(e for e, _ in TABLA4_RANURA)


def sr_requerida(abertura_max_mm: float | None) -> float:
    """La distancia de seguridad sr que exige una abertura de ancho < `abertura_max_mm` (el haz
    de ese ancho NO pasó); None = pasa el haz más ancho → abertura > 20 mm → alcance del brazo."""
    if abertura_max_mm is None:
        return ALCANCE_BRAZO_MM
    for e, sr in TABLA4_RANURA:
        if abertura_max_mm <= e:
            return sr
    return ALCANCE_BRAZO_MM
