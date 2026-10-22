"""Plantilla paramétrica de FAJA DE BANDA (belt conveyor): super-comando `create_belt_conveyor`.

Una faja de banda plana con cama de deslizamiento y dos tambores de extremo es UNA entrada del
historial, editable paramétricamente. A diferencia de `conveyor.py` (rodillos), los extremos son
TAMBORES (motriz engomado + cola), hay BANDA envolvente (lazo) y cama de deslizamiento.

v4 (plan puerta-de-publicacion, Bitácora «create_belt_conveyor v4»): se monta como en la
industria y declara lo que toca. Disposición (Z arriba, transporte hacia +X, motriz en +X):
- bastidor (`belt_conveyor_bastidor.py`): 2 largueros de tubo con el paso de los ejes por el
  alma, 4 patas soldadas con pie nivelador, 2 travesaños; cama atornillada sobre soportes;
- tambores y accionamiento (`belt_conveyor_tambores.py`): motriz de eje vivo en chumaceras UCF
  por fuera de los largueros; cola en unidades tensoras de carro UCT (o en UCF sin tensor);
  motorreductor coaxial con acople flexible sobre una base en voladizo;
- resguardos atornillados (`belt_conveyor_guardas.py`): guardas laterales en L, cajas de los
  tambores, tapas de los extremos de eje y cubierta del acople;
- las cotas, puras, en `belt_conveyor_cotas.py`; el plan (piezas + uniones + anclajes), en
  `belt_conveyor_plan.py`.

v5 (F6 de puerta-de-publicacion, sondas con el brazo doblado): con `cierres` (lo trae todo
comando NUEVO por el sello de entrada; un log v4 no lo trae y regenera igual) los largueros
llevan placa de cierre soldada en sus puntas y, con guardas, una guarda inferior atornillada
bajo la ranura banda ↔ larguero entre las guardas de los tambores.
"""

from __future__ import annotations

import math

from build123d import Cylinder, Plane, Polygon, extrude

from apolo.kernel.shapes import place

from . import belt_conveyor_bastidor as bastidor
from . import belt_conveyor_guardas as guardas
from . import belt_conveyor_tambores as tambores
from .belt_conveyor_cotas import FACE_MARGIN, cotas, radio_exterior  # noqa: F401 — re-export
from .belt_conveyor_plan import Plan

_radio_exterior = radio_exterior  # nombre histórico


def _belt_loop(x_m: float, z_m: float, r_m: float, x_c: float, z_c: float, r_c: float,
               thickness: float, width: float):
    """Banda como lazo HUECO que abraza dos tambores de radio propio (el motriz engomado es más
    grande que el de cola): envolvente convexa de los dos círculos de radio r+t menos la de los
    de radio r, extruida sobre el ancho de banda (eje Y). Coordenadas en el plano XZ."""

    def tangentes(r1: float, r2: float):
        # rectas tangentes EXTERIORES de los círculos (x_c, z_c, r1) y (x_m, z_m, r2): el
        # cuadrilátero de sus cuatro puntos de tangencia + los dos círculos = la envolvente
        dx, dz = x_m - x_c, z_m - z_c
        dist = math.hypot(dx, dz)
        fi, beta = math.atan2(dz, dx), math.acos((r1 - r2) / dist)
        pts = []
        for ang in (fi + beta, fi - beta):
            nx, nz = math.cos(ang), math.sin(ang)
            pts.append(((x_c + r1 * nx, z_c + r1 * nz), (x_m + r2 * nx, z_m + r2 * nz)))
        (a1, a2), (b1, b2) = pts
        return [a1, a2, b2, b1]

    def region(extra: float):
        r1, r2 = r_c + extra, r_m + extra
        # align=None: Polygon CENTRA sus puntos por defecto y los tramos quedaban a la altura del
        # piso, separados de los tubos (fabrica-de-publicaciones, ajuste D13: lo vio la sección)
        cuad = extrude(Plane.XZ * Polygon(*tangentes(r1, r2), align=None), amount=width / 2.0,
                       both=True)
        caps = (
            place(Cylinder(r1, width), (x_c, 0, z_c), (90, 0, 0))
            + place(Cylinder(r2, width), (x_m, 0, z_m), (90, 0, 0))
        )
        return cuad + caps

    return region(thickness) - region(0.0)


def belt_conveyor_parts(
    largo: float,
    ancho_banda: float,
    altura: float,
    tambor_motriz_ref: str,
    tambor_cola_ref: str,
    tubo_ref: str,
    tensor_ref: str | None,
    motor_ref: str | None,
    espesor_banda: float,
    guardas_on: bool,
    cierres: bool = False,
) -> Plan:
    """El plan de la faja: piezas (sufijo, nombre, forma…), uniones declaradas y anclajes.
    `cierres` (v5; False = la v4 tal cual, la de los logs viejos): placas de cierre soldadas en
    las puntas de los largueros y, con guardas, las guardas inferiores bajo la ranura banda ↔
    larguero."""
    c = cotas(largo, ancho_banda, altura, tambor_motriz_ref, tambor_cola_ref, tubo_ref,
              tensor_ref, motor_ref, espesor_banda, guardas_on, cierres)
    plan = Plan()
    bastidor.largueros(plan, c)

    # tambor motriz: chumaceras UCF a los dos lados; del lado +Y el acople del motorreductor
    lados = {-1.0: "rail1", 1.0: "rail2"}
    collar = {s: tambores.chumacera(plan, c, c.chum_m, c.half, c.zm, s, f"chum_m{i}",
                                    "motriz", lados[s], "tambor_motriz")
              for i, s in ((1, -1.0), (2, 1.0))}
    y_eje = {s: collar[s] + 2.0 for s in (-1.0, 1.0)}
    if c.motor:
        y_eje[1.0] = tambores.motorreductor(plan, c, collar[1.0])
    tambores.tambor(plan, c, "tambor_motriz", "Tambor motriz", c.tambor_m, c.half, c.zm,
                    -y_eje[-1.0], y_eje[1.0])
    if c.guardas:
        for i, s in ((1, -1.0), (2, 1.0)):
            if s < 0 or not c.motor:
                tambores.tapa_brida(plan, c, c.chum_m, c.half, c.zm, s, f"tapa_m{i}", "motriz",
                                    f"chum_m{i}", y_eje[s])

    # tambor de cola: unidades tensoras de carro (tensor de tornillo de catálogo) o UCF
    if c.uct:
        y_cola = max(tambores.tensor_carro(plan, c, i, s, lados[s])
                     for i, s in ((1, -1.0), (2, 1.0)))
    else:
        y_cola = max(tambores.chumacera(plan, c, c.chum_c, -c.half, c.zc, s, f"chum_c{i}",
                                        "de cola", lados[s], "tambor_cola")
                     for i, s in ((1, -1.0), (2, 1.0))) + 2.0
        if c.guardas:
            for i, s in ((1, -1.0), (2, 1.0)):
                tambores.tapa_brida(plan, c, c.chum_c, -c.half, c.zc, s, f"tapa_c{i}", "de cola",
                                    f"chum_c{i}", y_cola)
    tambores.tambor(plan, c, "tambor_cola", "Tambor de cola", c.tambor_c, -c.half, c.zc,
                    -y_cola, y_cola)

    # banda = lazo envolvente (geometría a medida), apoyada en los tambores y en la cama
    plan.pieza("banda", "Banda", _belt_loop(c.half, c.zm, c.r_m, -c.half, c.zc, c.r_c, c.t,
                                            c.ancho))
    bastidor.cama(plan, c)
    plan.union("banda_motriz", "banda", "tambor_motriz", "contacto",
               "la banda abraza el tambor motriz (engomado)")
    plan.union("banda_cola", "banda", "tambor_cola", "contacto", "la banda abraza el tambor de cola")
    plan.union("banda_cama", "banda", "cama", "contacto",
               "el ramal de carga desliza sobre la cama")
    bastidor.patas(plan, c)
    if c.guardas:
        guardas.laterales(plan, c)
        guardas.de_tambores(plan, c)
    if c.cierres:
        bastidor.placas_de_cierre(plan, c)
        if c.guardas:
            guardas.inferiores(plan, c)
    return plan
