"""Motorreductor SINFÍN de eje hueco calzado en el tambor motriz de `create_belt_conveyor` (plan
faja-compacta, D1). La cuenta (calce, relación, potencia, brazo), en `belt_conveyor_nmrv_cuenta.py`.

- **Calce**: el reductor (NMRV de catálogo, builder `worm_gearmotor`: origen en su barreno, eje
  hueco a lo largo de Y, brida de salida del lado −Y) se calza en el extremo del eje vivo del
  tambor motriz, por fuera de su chumacera (las dos chumaceras siguen: el eje vivo de siempre), a
  `HUELGO_CUBO` del collar del inserto. El eje entra hasta `FONDO_EJE` antes de la tapa del reductor
  (la tapa de su lado exterior es la del catálogo: el extremo libre del eje hueco queda cerrado) y
  lleva su CHAVETA DIN 6885 (b de la ficha, h y t1 de la norma) en el chavetero de la ficha, cortado
  en el cubo del reductor: el reductor arrastra el eje por la chaveta, sin acople.
- **Motor acostado a lo largo del larguero, hacia la cola**: el sinfín del builder va hacia −X local,
  bajo el eje; en el costado −Y (operarios a +Y) el reductor es el de motor del otro lado del sinfín
  (el espejo: la posición de montaje se pide al comprarlo), con la brida siempre hacia el larguero.
- **Brazo de reacción**: chapa atornillada a la cara de salida del reductor (los 6 pernos de su
  brida, M8 a sus roscas) que baja `R_BRAZO` hasta un perno M12 por un buje elástico, a rosca en un
  SOPORTE de barra redonda soldado a la cara exterior de la pata de cabeza (la que está bajo el eje
  motriz, soldada al larguero): el anclaje queda desfasado del eje y deja flotar el reductor.
  Vetable (D1 dice «al larguero»): bajo el eje el larguero tiene ~40 mm de canto libre; la pata da
  un brazo de palanca de `R_BRAZO` y está soldada al larguero en ese punto.
- Sin acople, base, ménsula, brazos de base ni guarda de acople: la salida es el eje hueco, a
  `HUELGO_CUBO` del collar y dentro del agujero del brazo (sin hueco por donde entre un dedo).
"""

from __future__ import annotations

import math

from build123d import Plane

from apolo.kernel.shapes import place

from .belt_conveyor_cotas import Cotas
from .belt_conveyor_plan import Plan, caja, cilindro_y
from .catalog import CATALOG, build_component

HUELGO_CUBO = 3.0        # del collar del inserto de la chumacera al cubo del reductor
FONDO_EJE = 3.0          # del extremo del eje a la cara interior de la tapa del reductor
T_BRAZO = 8.0            # chapa del brazo de reacción
ANCHO_BRAZO = 50.0
R_BRAZO = 150.0          # del eje motriz al perno del anclaje
BUJE_ELASTICO = 20.0     # Ø exterior del buje elástico del anclaje (agujero del brazo)
HUELGO_SOPORTE = 1.0     # del soporte al brazo (el reborde del buje)
FONDO_ROSCA = 24.0       # la rosca M12 del soporte (2·d)
LARGO_CHAVETA = 50.0     # DIN 6885 (serie 18…90 para b = 8)
#: DIN 6885-1 forma A: b → (h, t1 = profundidad en el eje)
CHAVETA = {5: (5.0, 3.0), 6: (6.0, 3.5), 8: (7.0, 4.0), 10: (8.0, 5.0), 12: (8.0, 5.0),
           14: (9.0, 5.5)}


def _forma(c: Cotas):
    """(forma local del reductor, del lado del motor; sus cotas del builder)."""
    prm = CATALOG[c.motor].params
    cd = float(prm["center_distance"])
    forma, _ = build_component(c.motor)
    if c.lado_motor < 0:
        forma = forma.mirror(Plane.XZ)
    return forma, {"cd": cd, "hy": 1.3 * cd, "fd": 1.7 * cd, "br": float(prm["bore_d"]) / 2.0}


def cotas_y(c: Cotas, collar: float) -> dict:
    """|y| del cubo, del centro del reductor, de la cara de su brida y del extremo del eje."""
    hy = 1.3 * float(CATALOG[c.motor].params["center_distance"])
    cubo = collar + HUELGO_CUBO
    centro = cubo + hy / 2.0 + 24.0                    # el cubo sale 24 mm de la caja (builder)
    return {"cubo": cubo, "centro": centro, "brida": cubo + 2.0, "eje": centro + hy / 2.0 - FONDO_EJE,
            "hy": hy}


def chaveta(c: Cotas, collar: float) -> tuple[float, float, float, float]:
    """(|y| inicio, |y| fin, b, radio de su cara de arriba) de la chaveta del eje motriz."""
    b = int(CATALOG[c.motor].specs["chavetero_b"])
    h, t1 = CHAVETA[b]
    y1 = cotas_y(c, collar)["eje"] - FONDO_EJE
    return y1 - LARGO_CHAVETA, y1, float(b), c.d_m / 2.0 - t1 + h


def montar(plan: Plan, c: Cotas, collar: float) -> float:
    """El reductor, su brazo de reacción y su soporte, con sus uniones. Devuelve |y| del extremo
    del eje motriz (dentro del eje hueco)."""
    from .belt_conveyor_bastidor import z_pata0
    from .belt_conveyor_carrera import largo_lazo
    from .belt_conveyor_nmrv_cuenta import D_SOPORTE, GARGANTA_SOPORTE, cuenta, cuenta_brazo

    calc = cuenta(c, largo_lazo(c))
    plan.calculos["motorreductor"] = calc
    s, x, z = c.lado_motor, c.half, c.zm
    forma, g = _forma(c)
    y = cotas_y(c, collar)
    motor = place(forma, (x, s * y["centro"], z), (0, 0, 0))
    spec = CATALOG[c.motor].specs
    b, top = float(spec["chavetero_b"]), float(spec["chavetero_t"]) - c.d_m / 2.0
    ranura = caja(x - b / 2.0, x + b / 2.0, s * (y["cubo"] - 1.0),
                  s * (y["centro"] + y["hy"] / 2.0 - 0.6), z + g["br"], z + top)
    # F1b (D9, criterio 10): la relación en el nombre, como en la placa del reductor que se compra
    # (NMRV-063 i = 40): de ahí la leen la vida L10 y el par (`relacion_motor.rpm_salida`)
    nombre = f"Motorreductor (i = {calc['relacion']:g})" if c.criterio >= 10 else "Motorreductor"
    plan.pieza("motor", nombre, motor - ranura, comp=c.motor)
    y0k, y1k, bk, _ = chaveta(c, collar)
    plan.union("motor_eje", "tambor_motriz", "motor", "contacto",
               f"eje motriz en el eje hueco del {c.motor} con chaveta {bk:g}x"
               f"{CHAVETA[int(bk)][0]:g}x{LARGO_CHAVETA:g} DIN 6885 (i = {calc['relacion']:g}: "
               f"{calc['n_tambor_rpm']:g} rpm → {calc['v_m_s']:g} m/s)"
               + (f"; AVISO: {calc['aviso']}" if calc.get("aviso") else ""))

    # brazo de reacción: disco sobre la brida + barra hasta el anclaje
    r_brazo = min(R_BRAZO, z - z_pata0(c) - D_SOPORTE)
    ya, yb = s * (y["brida"] - T_BRAZO), s * y["brida"]
    w = ANCHO_BRAZO
    brazo = (cilindro_y(x, z, ya, yb, g["fd"] / 2.0)
             + caja(x - w / 2.0, x + w / 2.0, ya, yb, z - r_brazo, z)
             + cilindro_y(x, z - r_brazo, ya, yb, w / 2.0))
    brazo = brazo - cilindro_y(x, z, ya - s, yb + s, g["br"] + 17.0)
    brazo = brazo - cilindro_y(x, z - r_brazo, ya - s, yb + s, BUJE_ELASTICO / 2.0)
    rbc = g["fd"] / 2.0 - 0.13 * g["cd"]
    for k in range(6):  # los 6 pernos de la brida del reductor (Ø9: paso de M8, ISO 273)
        a = math.radians(60.0 * k + 30.0)
        brazo = brazo - cilindro_y(x + rbc * math.cos(a), z + rbc * math.sin(a), ya - s, yb + s,
                                   4.5)
    plan.pieza("brazo_reaccion", "Brazo de reacción del motorreductor", brazo, material="acero")
    plan.union("brazo_motor", "brazo_reaccion", "motor", "perno",
               "brazo a la cara de salida del reductor: 6 tornillos M8x20 DIN 933 a sus roscas "
               "(enganche 12 mm = 1,5·d en fundición)", size="M8", qty=6)

    # soporte del anclaje: barra Ø40 soldada a la pata de cabeza, M12 a rosca en su punta
    from .belt_conveyor_taller import broca, cuenta_rosca, nota_rosca
    from .belt_conveyor_tambores_taller import _registrar

    y_s1 = y["brida"] - T_BRAZO - HUELGO_SOPORTE
    soporte = (cilindro_y(x, z - r_brazo, s * c.y_out, s * y_s1, D_SOPORTE / 2.0)
               - cilindro_y(x, z - r_brazo, s * (y_s1 - FONDO_ROSCA), s * (y_s1 + 1.0),
                            broca("M12") / 2.0))
    plan.pieza("soporte_brazo", "Soporte del brazo de reacción", soporte, material="acero")
    pata = "leg4" if s > 0 else "leg3"
    plan.union("soporte_pata", "soporte_brazo", pata, "soldadura",
               "soporte soldado a la cara exterior de la pata de cabeza (cordón alrededor)",
               throat_mm=GARGANTA_SOPORTE, length_mm=round(math.pi * D_SOPORTE, 1))
    cr = _registrar(plan, cuenta_rosca("brazo_soporte", "M12", T_BRAZO + HUELGO_SOPORTE + 2.5,
                                       FONDO_ROSCA, "el soporte del brazo"))
    plan.union("brazo_soporte", "brazo_reaccion", "soporte_brazo", "perno",
               nota_rosca("anclaje del brazo por su buje elástico (Ø20) con arandela", cr),
               size="M12", qty=1)
    plan.calculos["brazo_reaccion"] = cuenta_brazo(
        calc["par_salida_nm"], r_brazo, w, T_BRAZO, r_brazo - g["fd"] / 2.0,
        y_s1 + HUELGO_SOPORTE + T_BRAZO / 2.0 - c.y_out)
    return y["eje"]


def sobresale(c: Cotas, collar: float) -> float:
    """Cuánto sale el reductor de la cara exterior del larguero (|y|): lo mide el test contra la
    escena; esta es la cuenta de las cotas (el motor IEC centrado en la caja)."""
    m = float(CATALOG[c.motor].params["motor_d"])
    return cotas_y(c, collar)["centro"] + m / 2.0 - c.y_out
