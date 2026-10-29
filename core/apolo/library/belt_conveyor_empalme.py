"""EMPALME DE CAMPO de la banda de `create_belt_conveyor` (plan faja-compacta F1b, D12; criterio 10).

La re-revisión a ciegas de la mesa de sorteo (MEDIA) halló que los soportes de la cama, la cama y
el retorno ATRAVIESAN el lazo de la banda de larguero a larguero: con una banda sin fin, cambiarla
obliga a desmontar unas 80 uniones M8 y las chapas de la cama. La salida de mercado es la banda con
EMPALME MECÁNICO articulado (grapas con pasador, de catálogo: `23_empalmes_banda.yaml`): se saca el
pasador y la banda sale a lo largo de la faja, sin desarmar nada de lo que la atraviesa.

En la plantilla la cama y sus soportes atraviesan SIEMPRE el lazo (van entre los dos ramales y de
larguero a larguero), así que toda faja con el criterio 10 lleva su empalme; un log de antes no lo
trae y regenera igual. La puerta lo reconoce (`services/calidad_reparabilidad.banda_montable`): un
lazo sin fin atravesado sin empalme de campo es FALLA.

- **Dónde**: la tira de grapas sobre la cara EXTERIOR del ramal de retorno (lo que asoma de las
  grapas), cortada al ancho de la banda, en el medio del vano libre entre el tambor de cola y el
  primer rodillo de retorno (o el motriz, sin rodillos): la banda es un sólido fijo del modelo y el
  empalme se dibuja en una posición de la marcha. Se toca con la banda en toda su cara (la
  tangente exterior de los dos tambores, la misma que asienta los rodillos de retorno).
- **Unión**: `contacto` con la banda (las grapas se clavan en ella); nada más la sostiene.
"""

from __future__ import annotations

import math

from .belt_conveyor_cotas import Cotas
from .belt_conveyor_plan import Plan
from .catalog import CATALOG, build_component

REF = "EMPALME-GRAPA-ART"


def lleva_empalme(c: Cotas) -> bool:
    return c.criterio >= 10


def _cara_retorno(c: Cotas) -> tuple[float, float, float, float]:
    """(a, b, d) de la recta a·x + b·z = d de la cara exterior del ramal de retorno (normal
    (a, b) hacia AFUERA del lazo, hacia abajo) y su pendiente."""
    x1, z1, r1 = -c.half, c.zc, c.r_c + c.t
    x2, z2, r2 = c.half, c.zm, c.r_m + c.t
    dist = math.hypot(x2 - x1, z2 - z1)
    beta = math.atan2(z2 - z1, x2 - x1) - math.acos((r1 - r2) / dist)
    a, b = math.cos(beta), math.sin(beta)
    return a, b, a * x1 + b * z1 + r1, beta


def x_empalme(c: Cotas) -> float:
    """El medio del vano libre del retorno entre el tambor de cola y el primer apoyo."""
    from .belt_conveyor_retorno import x_rodillos

    rodillos = x_rodillos(c)
    return (-c.half + (rodillos[0] if rodillos else c.half)) / 2.0


def empalme(plan: Plan, c: Cotas) -> None:
    """La tira de grapas del empalme de campo sobre la cara exterior del ramal de retorno."""
    from build123d import Plane

    if not lleva_empalme(c):
        return
    a, b, d, _ = _cara_retorno(c)
    x = x_empalme(c)
    z = (d - a * x) / b                                    # la cara de la banda en x
    e = float(CATALOG[REF].params["height"])
    base, cut = build_component(REF, c.ancho)
    centro = (x + a * e / 2.0, 0.0, z + b * e / 2.0)
    forma = Plane(origin=centro, x_dir=(0.0, 1.0, 0.0), z_dir=(a, 0.0, b)) * base
    plan.pieza("empalme_banda", "Empalme de campo de la banda (grapas articuladas)", forma,
               comp=REF, cut=cut)
    plan.union("banda_empalme", "empalme_banda", "banda", "contacto",
               "empalme de campo: grapas articuladas clavadas en las dos puntas de la banda y unidas "
               "por su pasador; para cambiar la banda se saca el pasador y se tira de ella a lo largo "
               "de la faja, sin desarmar la cama ni sus soportes, que atraviesan el lazo")
