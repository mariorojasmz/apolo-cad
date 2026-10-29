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

v6 (plan faja-larga-en-tramos): con `tramo_max` el bastidor sale en tramos iguales empernados
con placas de empalme y una estación de patas bajo cada empalme (`belt_conveyor_tramos.py`); con
el criterio 6, rodillos de retorno cada ≤ 3 m y pernos pasantes con buje en lo que se atornilla
a la cara interior de los largueros (`belt_conveyor_retorno.py`). El sello de entrada pone los
dos en toda faja NUEVA; un log de antes no los trae y regenera igual.

F1b (mismo plan, D7–D9): `lado_abierto` deja el costado de los operarios sin la pared de la guarda
lateral (sólo la guarda cubre-ranura a ras de la banda, `belt_conveyor_guardas.py`); el criterio 7
(el del sello desde la F1b) suma el pie nivelador con tuerca soldada y contratuerca
(`belt_conveyor_pies.py`) y los brazos de la base del motor a tope contra la pata, con su cuenta
y, si no da, tornapuntas (`belt_conveyor_motor.py`).

F1c (criterio 8, el del sello desde la F1c): cada unión de la plantilla con sus agujeros en la
geometría, ninguna tuerca dentro de un tubo cerrado (rosca en placa, perno pasante con buje o
espárrago soldado), cama y guardas laterales en paños ≤ 3 m, la cama del espesor de su cuenta y
cada perno con su largo en la nota (`belt_conveyor_taller.py` y sus vecinos `*_taller.py`,
`belt_conveyor_cama.py`).

faja-compacta (criterio 9, el del sello desde su F1): la carrera del tensor de cola calculada y el
carro al INICIO de ella (`belt_conveyor_carrera.py`); valores nuevos de `motor` (motorreductor
sinfín de eje hueco calzado en el tambor, `belt_conveyor_nmrv*.py`) y de `tensor`
(«placa-ranurada», `belt_conveyor_placa.py`).

faja-compacta F1b (criterio 10, el del sello desde la F1b): el sinfín no se rechaza por la carga
supuesta y su relación sale con el radio de la simulación (`belt_conveyor_nmrv_cuenta.py`), la
placa ranurada llega a su tope GEOMÉTRICO (`belt_conveyor_carrera.tope_placa`), una estación de
patas a cada lado de cada empalme con la cuenta del tramo suelto (`belt_conveyor_tramo_suelto.py`)
y el empalme de campo de la banda (`belt_conveyor_empalme.py`).
"""

from __future__ import annotations

import math

from build123d import Cylinder, Plane, Polygon, extrude

from apolo.kernel.shapes import place

from . import belt_conveyor_bastidor as bastidor
from . import belt_conveyor_guardas as guardas
from . import belt_conveyor_retorno as retorno
from . import belt_conveyor_tambores as tambores
from . import belt_conveyor_tramos as tramos
from .belt_conveyor_cotas import FACE_MARGIN, cotas, radio_exterior  # noqa: F401 — re-export
from .belt_conveyor_cotas import PLACA_CHUMACERA_T
from .belt_conveyor_nmrv_cuenta import es_sinfin
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
    tramo_max: float | None = None,
    criterio: int = 5,
    lado_abierto: str = "ninguno",
    velocidad: float | None = None,
) -> Plan:
    """El plan de la faja: piezas (sufijo, nombre, forma…), uniones declaradas y anclajes.
    `cierres` (v5; False = la v4 tal cual, la de los logs viejos): placas de cierre soldadas en
    las puntas de los largueros y, con guardas, las guardas inferiores bajo la ranura banda ↔
    larguero. `tramo_max` (v6; None = una pieza): el bastidor en tramos iguales empernados.
    `criterio` (v6; 5 = la v5 tal cual): 6 suma los rodillos de retorno y el perno pasante con
    buje en las placas de los soportes de la cama; 7 (F1b) suma el pie con tuerca soldada y
    contratuerca y los brazos del motor a tope contra la pata. `lado_abierto` (F1b; «ninguno» =
    como siempre): con guardas, ese costado lleva sólo la guarda cubre-ranura a ras de la banda.
    `velocidad` (faja-compacta, m/s): la de la banda, para la relación de un motorreductor sinfín
    de eje hueco (D2; los demás motores no la leen)."""
    c = cotas(largo, ancho_banda, altura, tambor_motriz_ref, tambor_cola_ref, tubo_ref,
              tensor_ref, motor_ref, espesor_banda, guardas_on, cierres, tramo_max, criterio,
              lado_abierto, velocidad)
    plan = Plan()
    bastidor.largueros(plan, c)

    # tambor motriz: chumaceras UCF a los dos lados; del lado +Y el acople del motorreductor
    lados_m = {-1.0: tramos.rail(c, 1, c.half), 1.0: tramos.rail(c, 2, c.half)}
    lados = {-1.0: tramos.rail(c, 1, -c.half), 1.0: tramos.rail(c, 2, -c.half)}
    collar = {s: tambores.chumacera(plan, c, c.chum_m, c.half, c.zm, s, f"chum_m{i}",
                                    "motriz", lados_m[s], "tambor_motriz")
              for i, s in ((1, -1.0), (2, 1.0))}
    y_eje = {s: collar[s] + 2.0 for s in (-1.0, 1.0)}
    sm, chaveta = c.lado_motor, None
    if c.motor and es_sinfin(c.motor):  # faja-compacta D1: eje hueco calzado en el tambor
        from . import belt_conveyor_nmrv as nmrv

        y_eje[sm] = nmrv.montar(plan, c, collar[sm])
        y0k, y1k, bk, rk = nmrv.chaveta(c, collar[sm])
        chaveta = (*sorted((sm * y0k, sm * y1k)), bk, rk)
    elif c.motor:
        y_eje[1.0] = tambores.motorreductor(plan, c, collar[1.0])
    tambores.tambor(plan, c, "tambor_motriz", "Tambor motriz", c.tambor_m, c.half, c.zm,
                    -y_eje[-1.0], y_eje[1.0], chaveta)
    if c.guardas:
        for i, s in ((1, -1.0), (2, 1.0)):
            if s != sm or not c.motor:
                tambores.tapa_brida(plan, c, c.chum_m, c.half, c.zm, s, f"tapa_m{i}", "motriz",
                                    f"chum_m{i}", y_eje[s])

    # tambor de cola: unidades tensoras de carro (tensor de tornillo de catálogo), placa ranurada
    # (faja-compacta D3) o UCF
    if c.uct:
        y_cola = max(tambores.tensor_carro(plan, c, i, s, lados[s])
                     for i, s in ((1, -1.0), (2, 1.0)))
    else:
        if c.placa_c:
            from .belt_conveyor_placa import PLACA_T, tensor_placa

            y_cola, placa_t = max(tensor_placa(plan, c, i, s, lados[s])
                                  for i, s in ((1, -1.0), (2, 1.0))), PLACA_T
        else:
            y_cola = max(tambores.chumacera(plan, c, c.chum_c, -c.half, c.zc, s, f"chum_c{i}",
                                            "de cola", lados[s], "tambor_cola")
                         for i, s in ((1, -1.0), (2, 1.0))) + 2.0
            placa_t = PLACA_CHUMACERA_T
        if c.guardas:
            for i, s in ((1, -1.0), (2, 1.0)):
                tambores.tapa_brida(plan, c, c.chum_c, -c.half, c.zc, s, f"tapa_c{i}", "de cola",
                                    f"chum_c{i}", y_cola, placa_t)
    if c.cuenta_carrera:
        plan.calculos["carrera_tensor"] = c.cuenta_carrera
    tambores.tambor(plan, c, "tambor_cola", "Tambor de cola", c.tambor_c, -c.half, c.zc,
                    -y_cola, y_cola)

    # banda = lazo envolvente (geometría a medida), apoyada en los tambores y en la cama
    plan.pieza("banda", "Banda", _belt_loop(c.half, c.zm, c.r_m, -c.half, c.zc, c.r_c, c.t,
                                            c.ancho))
    bastidor.cama(plan, c)
    plan.union("banda_motriz", "banda", "tambor_motriz", "contacto",
               "la banda abraza el tambor motriz (engomado)")
    plan.union("banda_cola", "banda", "tambor_cola", "contacto", "la banda abraza el tambor de cola")
    n_camas = len(tramos.tramos_cama(c))  # una por tramo; con el criterio 8, por paño
    for j in range(1, n_camas + 1):
        plan.union("banda_cama" if n_camas == 1 else f"banda_cama{j}", "banda",
                   tramos.cama(c, j), "contacto", "el ramal de carga desliza sobre la cama")
    bastidor.patas(plan, c)
    if c.guardas:
        guardas.laterales(plan, c)
        guardas.de_tambores(plan, c)
    if c.cierres:
        bastidor.placas_de_cierre(plan, c)
        if c.guardas:
            guardas.inferiores(plan, c)
    if c.n_tramos > 1:
        tramos.placas_de_empalme(plan, c)
    retorno.rodillos(plan, c)
    if c.criterio >= 10:  # faja-compacta F1b: el empalme de campo (D12) y el tramo suelto (D11)
        from .belt_conveyor_empalme import empalme
        from .belt_conveyor_tramo_suelto import verificar

        empalme(plan, c)
        verificar(plan, c)
    return plan
