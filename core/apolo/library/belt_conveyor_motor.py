"""Base del motorreductor de `create_belt_conveyor` con el criterio 7 (plan faja-larga-en-tramos,
F1b D9): los brazos a tope contra la pata, la cuenta del voladizo y, si no da, las tornapuntas.

Hasta el criterio 6 la base (placa sobre dos brazos de tubo) colgaba de una ménsula de tubo
soldada SÓLO a la cara exterior de la pata, y los brazos arrancaban 1 mm afuera de esa cara, a
1,3 mm de los costados de la pata: no apoyaban en ella. Con el criterio 7 los brazos van a
±`LEG_W` del eje de la pata, A TOPE contra sus dos costados desde su cara interior, soldados a
ella además de a la ménsula; la base se ensancha si el motor es más angosto que los brazos.

**La cuenta** (`cuenta`, criterio de diseño salvo donde se cita; la publica `cuenta_de_la_faja`):

- Cargas: el peso del motor (ficha), de la base y de los brazos, cada uno en su centro; el par de
  reacción del motorreductor (coaxial con acople flexible: su carcasa devuelve el par a la base)
  con `ARRANQUE` × el par nominal de la ficha (arranque directo de un motor de inducción: del
  orden de 2 × el nominal; criterio de diseño).
- Brazos (tubo de catálogo, A500 Gr. B, f_y = `FY_TUBO`): flexión por el peso (mitad por brazo)
  + el par repartido por rigidez entre la torsión de los dos tubos (G·J/a, J = (b−t)³·t de una
  celda cerrada) y la flexión diferencial (s²·3EI/(2a³)); von Mises ≤ 0,6·f_y.
- Soldadura ménsula ↔ pata, SOLA (la de los brazos a la pata no se cuenta: queda del lado
  seguro): anillo cuadrado de b = `LEG_W` como líneas (S_w = 4b²/3, J_w = (2b)³/6), garganta de
  la unión declarada; τ ≤ 0,30·F_EXX (AISC 360 J2.4, ASD: F_nw = 0,60·F_EXX, Ω = 2,00; E70XX).
- Alineación del acople (lo que decide la escuadra): con el par de arranque, el motor se corre
  de costado lo que gira la base sobre su eje (torsión del voladizo × la altura del eje motriz
  sobre los brazos) más lo que gira la pata en la ménsula (voladizo empotrado en el larguero, sin
  contar el pie: el roce con el piso no es un apoyo; × la altura del eje sobre la ménsula). Debe
  quedar ≤ `ALINEACION_MM`: la desalineación paralela que admite un acople de garras del tamaño
  de estos ejes (del orden de 0,38 mm en los catálogos; criterio de diseño). Si no da, dos
  TORNAPUNTAS de tubo a 45° (una bajo cada brazo, soldadas al brazo y al costado de la pata): el
  par pasa por su esfuerzo axil, ± a la distancia entre brazos.

Medido (`tests/test_belt_conveyor_f1b.py`, faja de 4 m): sin tornapuntas dan MOTOR-150-EH
(65 N·m: 0,22 mm, τ soldadura 21 MPa, σ brazo 16 MPa), MOTOR-037 (0,17 mm) y MOTOR-075 (0,35
mm); MOTOR-150 (205 N·m) no (0,7 mm) y lleva las tornapuntas: 0,34 mm, τ 35 MPa.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .belt_conveyor_cotas import LEG_REF, LEG_W, Cotas
from .belt_conveyor_plan import Plan, caja
from .catalog import CATALOG, build_component

E_ACERO = 200e3          # MPa
G_ACERO = 77e3           # MPa
FY_TUBO = 317.0          # MPa, ASTM A500 Gr. B (tubo rectangular)
F_EXX = 482.0            # MPa, electrodo E70XX
RHO = 7.85e-6            # kg/mm³
G = 9.81
ARRANQUE = 2.0           # × par nominal de la ficha (ver el docstring)
ALINEACION_MM = 0.38     # desalineación paralela admisible del acople (ver el docstring)
GARGANTA_MENSULA = 4.0   # la de la unión «mensula_pata»
ANGULO_TORNAPUNTA = 45.0


@dataclass(frozen=True)
class Tubo:
    b: float
    t: float

    @property
    def i(self) -> float:
        return (self.b ** 4 - (self.b - 2.0 * self.t) ** 4) / 12.0

    @property
    def s(self) -> float:
        return self.i / (self.b / 2.0)

    @property
    def area(self) -> float:
        return self.b ** 2 - (self.b - 2.0 * self.t) ** 2

    @property
    def j(self) -> float:
        return (self.b - self.t) ** 3 * self.t   # 4·Am²·t / perímetro medio, celda cuadrada

    @property
    def am(self) -> float:
        return (self.b - self.t) ** 2


def tubo(ref: str) -> Tubo:
    p = CATALOG[ref].params or {}
    return Tubo(float(p["width"]), float(p["wall"]))


def cuenta(cargas: list[tuple[float, float]], par_nm: float, a: float, s: float,
           h_giro: float, h_pata: float, h_eje_mensula: float, brazo: Tubo, pata: Tubo,
           tornapunta: tuple[float, float] | None = None) -> dict:
    """La cuenta del voladizo (unidades: kg, N·m, mm). `cargas` = (kg, brazo desde la cara de
    la pata); `a` = brazo del par (el centro del motor); `s` = entre ejes de los brazos;
    `h_giro` = del eje motriz al eje de los brazos; `h_pata` = de la ménsula al larguero;
    `h_eje_mensula` = del eje motriz a la ménsula; `tornapunta` = (largo, ángulo en grados)."""
    peso = sum(kg for kg, _ in cargas) * G
    m_peso = sum(kg * G * x for kg, x in cargas)                         # N·mm
    t = ARRANQUE * par_nm * 1e3                                          # N·mm
    k_t = 2.0 * G_ACERO * brazo.j / a
    k_db = s ** 2 * 3.0 * E_ACERO * brazo.i / (2.0 * a ** 3)
    k_tp = 0.0
    if tornapunta:
        largo, ang = tornapunta
        k_tp = E_ACERO * brazo.area / largo * math.sin(math.radians(ang)) ** 2 * s ** 2 / 2.0
    k = k_t + k_db + k_tp
    giro = t / k
    giro_pata = t * h_pata / (E_ACERO * pata.i)
    corrimiento = giro * h_giro + giro_pata * h_eje_mensula
    sigma = (m_peso / 2.0 + t * k_db / k / s * a) / brazo.s
    tau = t * k_t / k / 2.0 / (2.0 * brazo.am * brazo.t)
    von_mises = math.hypot(sigma, math.sqrt(3.0) * tau)
    b = LEG_W
    f = m_peso / (4.0 * b * b / 3.0) + t * (b / math.sqrt(2.0)) / ((2.0 * b) ** 3 / 6.0) \
        + peso / (4.0 * b)
    tau_w = f / GARGANTA_MENSULA
    out = {
        "peso_n": round(peso, 1), "momento_peso_nm": round(m_peso / 1e3, 1),
        "par_arranque_nm": round(t / 1e3, 1), "tornapuntas": tornapunta is not None,
        "sigma_brazo_mpa": round(von_mises, 1), "sigma_adm_mpa": round(0.6 * FY_TUBO, 1),
        "tau_soldadura_mpa": round(tau_w, 1), "tau_adm_mpa": round(0.30 * F_EXX, 1),
        "corrimiento_mm": round(corrimiento, 3), "corrimiento_adm_mm": ALINEACION_MM,
    }
    out["ok"] = (von_mises <= 0.6 * FY_TUBO and tau_w <= 0.30 * F_EXX
                 and corrimiento <= ALINEACION_MM)
    return out


@dataclass(frozen=True)
class Base:
    """Cotas de la base del motor (criterio 7), del plan y de la cuenta."""
    x: float
    w: float                 # media anchura de la placa
    y_pata: float            # cara exterior de la pata (raíz del voladizo)
    y0: float
    y1: float
    z_patas: float           # cara superior de la placa (bajo las patas del motor)
    zb0: float               # cara inferior de la placa = tope de los brazos
    za0: float               # cara inferior de los brazos = tope de la ménsula
    zm0: float               # cara inferior de la ménsula
    y_motor: tuple[float, float]


def cotas_base(c: Cotas, bb, y_mo: float, y0: float, y1: float) -> Base:
    from .belt_conveyor_tambores import BASE_MOTOR_T

    z_patas = c.zm + bb.min.Z
    w = max(bb.max.Y, 1.5 * LEG_W + 10.0)            # los brazos (a ±LEG_W) bajo la placa
    zb0 = z_patas - BASE_MOTOR_T
    return Base(x=c.half, w=w, y_pata=c.y_in + LEG_W, y0=y0, y1=y1, z_patas=z_patas, zb0=zb0,
                za0=zb0 - LEG_W,
                zm0=zb0 - 2.0 * LEG_W, y_motor=(y_mo - bb.max.X, y_mo - bb.min.X))


def _tornapunta(b: Base, c: Cotas) -> tuple[float, float, float]:
    """(y del tope de la tornapunta bajo el brazo, z de su arranque en la pata, largo)."""
    from .belt_conveyor_bastidor import z_pata0

    y_cg = sum(b.y_motor) / 2.0
    leg_y = c.y_in + LEG_W / 2.0
    y_top = min(y_cg, b.y1 - LEG_W, leg_y + (b.za0 - z_pata0(c) - 2.0 * LEG_W))
    z_bajo = b.za0 - (y_top - leg_y)
    return y_top, z_bajo, (y_top - leg_y) * math.sqrt(2.0)


def cuenta_de_la_faja(c: Cotas, b: Base, motor_kg: float, tornapuntas: bool) -> dict:
    """La cuenta con las cotas de la faja (brazos desde la cara exterior de la pata)."""
    from .belt_conveyor_tambores import TUBO_BASE

    brazo = tubo(TUBO_BASE)
    largo_brazo = b.y1 - c.y_in
    base_kg = RHO * 2.0 * b.w * (b.y1 - b.y0) * (b.z_patas - b.zb0)
    brazos_kg = 2.0 * RHO * brazo.area * largo_brazo
    a = sum(b.y_motor) / 2.0 - b.y_pata
    cargas = [(motor_kg, a), (base_kg, (b.y0 + b.y1) / 2.0 - b.y_pata),
              (brazos_kg, (c.y_in + b.y1) / 2.0 - b.y_pata)]
    tp = None
    if tornapuntas:
        tp = (_tornapunta(b, c)[2], ANGULO_TORNAPUNTA)
    par = float(CATALOG[c.motor].specs.get("torque_Nm") or 0.0)
    z_brazo, z_mens = b.za0 + LEG_W / 2.0, b.zm0 + LEG_W / 2.0
    return cuenta(cargas, par, a, 2.0 * LEG_W, c.zm - z_brazo, c.rail_bot - z_mens,
                  c.zm - z_mens, brazo, tubo(LEG_REF), tp)


def base_motor(plan: Plan, c: Cotas, bb, y_mo: float, y0: float, y1: float, taladros=(),
               nota: str | None = None, alivios=()) -> dict:
    """La base del criterio 7 (placa, ménsula, brazos a tope contra la pata y, si la cuenta lo
    pide, tornapuntas) con sus uniones. Con el criterio 8 (F1c), la placa con sus agujeros
    roscados (`taladros`: (x, y, Ø), verticales), los `alivios` de la punta de esos pernos en la
    pared superior del brazo que cae debajo y `nota` con el largo de los pernos del motor.
    Devuelve la cuenta con que quedó."""
    from .belt_conveyor_taller import taladro_z
    from .belt_conveyor_tambores import TUBO_BASE

    b = cotas_base(c, bb, y_mo, y0, y1)
    motor_kg = float(CATALOG[c.motor].weight or 0.0)
    calc = cuenta_de_la_faja(c, b, motor_kg, False)
    if not calc["ok"]:
        plan.calculos["base_motor_sin_tornapuntas"] = calc
        calc = cuenta_de_la_faja(c, b, motor_kg, True)
    mat = str(CATALOG[TUBO_BASE].specs.get("material") or "acero")
    x, w = b.x, b.w
    placa = caja(x - w, x + w, y0, y1, b.zb0, b.z_patas)
    for px, py, d in taladros:
        placa = placa - taladro_z(px, py, b.zb0 - 1.0, b.z_patas + 1.0, d)
    plan.pieza("base_motor", "Base del motor", placa, material="acero")
    mens, mcut = build_component(TUBO_BASE, 2.0 * w)
    plan.pieza("mensula_motor", "Ménsula del motor", mens, comp=TUBO_BASE, cut=mcut,
               pos=(x, b.y_pata + LEG_W / 2.0, b.zm0 + LEG_W / 2.0), rot=(0, 90, 0),
               key=f"comp|{TUBO_BASE}|{mcut}", material=mat)
    plan.union("mensula_pata", "mensula_motor", "leg4", "soldadura",
               "ménsula soldada a la cara exterior de la pata", throat_mm=GARGANTA_MENSULA,
               length_mm=round(4 * LEG_W, 1))
    largo = y1 - c.y_in
    brazo, bcut = build_component(TUBO_BASE, largo)
    for k, sx in ((1, -1.0), (2, 1.0)):
        xb = x + sx * LEG_W
        pos, rot = (xb, c.y_in + largo / 2.0, b.za0 + LEG_W / 2.0), (90, 0, 0)
        suyos = [(px, py, d) for px, py, d in alivios if abs(px - xb) < LEG_W / 2.0]
        if suyos:  # criterio 8: el alivio de la punta de los pernos del motor (sin tuerca)
            from apolo.kernel.shapes import place

            forma = place(brazo, pos, rot)
            for px, py, d in suyos:
                forma = forma - taladro_z(px, py, b.zb0 - 6.0, b.zb0 + 1.0, d)  # pared de arriba
            plan.pieza(f"brazo_motor{k}", f"Brazo de la base del motor ({k})", forma,
                       comp=TUBO_BASE, cut=bcut, material=mat)
        else:
            plan.pieza(f"brazo_motor{k}", f"Brazo de la base del motor ({k})", brazo,
                       comp=TUBO_BASE, cut=bcut, pos=pos, rot=rot,
                       key=f"comp|{TUBO_BASE}|{bcut}", material=mat)
        plan.union(f"brazo{k}_pata", f"brazo_motor{k}", "leg4", "soldadura",
                   "brazo a tope contra el costado de la pata (filetes arriba y abajo)",
                   throat_mm=3, length_mm=round(2 * LEG_W, 1))
        plan.union(f"brazo{k}_mensula", f"brazo_motor{k}", "mensula_motor", "soldadura",
                   "brazo soldado sobre la ménsula", throat_mm=3, length_mm=round(2 * LEG_W, 1))
        plan.union(f"base_brazo{k}", "base_motor", f"brazo_motor{k}", "soldadura",
                   "base soldada sobre el brazo", throat_mm=3, length_mm=200.0)
        if calc["tornapuntas"]:
            _pieza_tornapunta(plan, c, b, k, xb, mat)
    plan.union("motor_base", "motor", "base_motor", "perno",
               nota or "patas del motorreductor a la base (4 pernos)", size="M10", qty=4)
    plan.calculos["base_motor"] = calc
    return calc


def _pieza_tornapunta(plan: Plan, c: Cotas, b: Base, k: int, xb: float, mat: str) -> None:
    """Tubo a 45° bajo el brazo `k`: su punta de abajo, cortada a plomo en la cara interior de la
    pata y soldada a su costado; la de arriba, cortada a nivel bajo el brazo y soldada a él."""
    from build123d import Box, Plane

    y_top, z_bajo, largo = _tornapunta(b, c)
    leg_y = c.y_in + LEG_W / 2.0
    d = (0.0, math.sqrt(0.5), math.sqrt(0.5))
    centro = (xb, (leg_y + y_top) / 2.0, (z_bajo + b.za0) / 2.0)
    tubo_ = Plane(origin=centro, x_dir=(1, 0, 0), z_dir=d) * Box(LEG_W, LEG_W, largo + 3 * LEG_W)
    tubo_ = tubo_ - Plane(origin=centro, x_dir=(1, 0, 0), z_dir=d) * Box(
        LEG_W - 6.4, LEG_W - 6.4, largo + 3 * LEG_W + 2.0)
    recorte = caja(xb - LEG_W / 2.0, xb + LEG_W / 2.0, c.y_in, b.y1, z_bajo - 2 * LEG_W, b.za0)
    plan.pieza(f"tornapunta_motor{k}", f"Tornapunta de la base del motor ({k})",
               tubo_ & recorte, material=mat)
    plan.union(f"tornapunta{k}_pata", f"tornapunta_motor{k}", "leg4", "soldadura",
               "tornapunta soldada al costado de la pata", throat_mm=3,
               length_mm=round(2 * LEG_W * math.sqrt(2.0), 1))
    plan.union(f"tornapunta{k}_brazo", f"tornapunta_motor{k}", f"brazo_motor{k}", "soldadura",
               "tornapunta soldada bajo el brazo", throat_mm=3,
               length_mm=round(2 * LEG_W * math.sqrt(2.0), 1))
