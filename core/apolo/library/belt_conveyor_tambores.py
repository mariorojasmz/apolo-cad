"""Tambores, apoyos y accionamiento de `create_belt_conveyor` (v4).

- Tambor motriz de EJE VIVO en dos chumaceras de brida UCF, atornilladas por fuera de los
  largueros a una placa porta-chumacera soldada (roscas de la brida en la placa: se cambian sin
  desarmar la faja). El eje pasa por el alma del larguero con holgura.
- Tambor de cola en dos unidades tensoras de carro UCT de catálogo (tensor de tornillo estándar,
  carrera de ficha) atornilladas por fuera de los largueros; sin tensor, en chumaceras UCF.
- Motorreductor coaxial al eje motriz del lado +Y, unido por un acople flexible y apoyado por sus
  patas en una base en voladizo soldada a la pata del lado motriz (accionamiento directo en el
  lado lento: sin cadena ni faja que tensar).
- Con guardas, los extremos libres de los ejes llevan tapa atornillada a su soporte y el acople
  una cubierta atornillada a la base.

Con el criterio 7 (F1b) la base del motor va con los brazos a tope contra la pata y su cuenta
(`belt_conveyor_motor.py`).

El eje de cada tambor se modela a la medida de la máquina (lo que pide su montaje), con el cuerpo
y el engomado del catálogo: la ficha (BOM, masa) sigue siendo la del tambor.
"""

from __future__ import annotations

from build123d import Cylinder, Pos

from .belt_conveyor_cotas import HOLGURA_EJE, LEG_W, PLACA_CHUMACERA_T, Cotas, perno_de_brida
from .belt_conveyor_plan import Plan, caja, cilindro_y
from .builders import drum
from .catalog import CATALOG, build_component

TAPA_T = 3.0
BASE_MOTOR_T = 12.0
TUBO_BASE = "TUBO-2X2"


def tambor(plan: Plan, c: Cotas, suf: str, nombre: str, ref: str, x: float, z: float,
           y_lo: float, y_hi: float) -> None:
    """Cuerpo del tambor de catálogo + su eje de `y_lo` a `y_hi` (mundo). Marco local: eje Z;
    la rotación (90, 0, 0) lo lleva a −Y, así que el tramo mundial [y_lo, y_hi] es el local
    [−y_hi, −y_lo]."""
    comp = CATALOG[ref]
    prm = {**(comp.params or {}), "stub": 0.0, "shaft_hole_d": 0.0, "hole_inset": 0.0}
    d = float(comp.specs["eje_mm"])
    cuerpo = drum(**prm)(c.cara)
    eje = Pos(0, 0, -(y_lo + y_hi) / 2.0) * Cylinder(d / 2.0, y_hi - y_lo)
    plan.pieza(suf, nombre, cuerpo + eje, comp=ref, cut=c.cara, pos=(x, 0.0, z), rot=(90, 0, 0),
               key=f"faja|{ref}|{c.cara:g}|{y_lo:.2f}|{y_hi:.2f}")


def _brida(ref: str) -> dict:
    p = CATALOG[ref].params
    return {k: float(p[k]) for k in ("d", "size_w", "size_h", "Bi", "s")}


def _y_soporte(c: Cotas, b: dict) -> float:
    """|y| del origen (centro del barreno) de una UCF montada sobre la placa porta-chumacera."""
    return c.y_out + PLACA_CHUMACERA_T + b["Bi"] / 2.0 + b["s"]


def chumacera(plan: Plan, c: Cotas, ref: str, x: float, z: float, lado: float, suf: str,
              donde: str, rail: str, tambor_suf: str) -> float:
    """Placa porta-chumacera soldada a la cara exterior del larguero + chumacera UCF atornillada
    a ella. Devuelve |y| del extremo del collar del inserto (hasta ahí llega el soporte)."""
    b = _brida(ref)
    y_placa = c.y_out + PLACA_CHUMACERA_T
    y0 = _y_soporte(c, b)
    signo = "−" if lado < 0 else "+"
    plan.pieza(suf, f"Chumacera {donde} ({signo}Y)", build_component(ref)[0], comp=ref,
               pos=(x, lado * y0, z), rot=(0, 0, 180) if lado > 0 else (0, 0, 0),
               key=f"comp|{ref}|std")
    pw, ph = b["size_w"] + 30.0, b["size_h"] + 10.0
    placa = (caja(x - pw / 2.0, x + pw / 2.0, lado * c.y_out, lado * y_placa, z - ph / 2.0,
                  z + ph / 2.0)
             - cilindro_y(x, z, lado * (c.y_out - 1.0), lado * (y_placa + 1.0),
                          b["d"] / 2.0 + HOLGURA_EJE))
    psuf = f"{suf}_placa"
    plan.pieza(psuf, f"Placa porta-chumacera {donde} ({signo}Y)", placa, material="acero")
    plan.union(f"{psuf}_sold", psuf, rail, "soldadura",
               "placa porta-chumacera soldada al larguero (filetes arriba y abajo)", throat_mm=4,
               length_mm=round(2.0 * pw, 1))
    plan.union(f"{suf}_placa", suf, psuf, "perno",
               "brida de la chumacera a las roscas de la placa", size=perno_de_brida(ref), qty=4)
    plan.union(f"{suf}_eje", tambor_suf, suf, "contacto",
               "eje en el inserto, fijado con sus prisioneros")
    return y0 + b["Bi"] / 2.0 + 0.36 * b["d"] - 2.0


def tapa_brida(plan: Plan, c: Cotas, ref: str, x: float, z: float, lado: float, suf: str,
               donde: str, chumacera_suf: str, y_eje: float) -> None:
    """Tapa (copa) atornillada a la brida de la chumacera sobre el extremo libre del eje."""
    b = _brida(ref)
    r_in = 1.08 * b["d"] + 6.5       # libra el cubo, el collar y la grasera del soporte
    ya, yb = _y_soporte(c, b) - b["Bi"] / 2.0, y_eje + 3.0
    copa = (cilindro_y(x, z, lado * ya, lado * (yb + TAPA_T), r_in + TAPA_T)
            - cilindro_y(x, z, lado * (ya - 1.0), lado * yb, r_in))
    plan.pieza(suf, f"Tapa del eje {donde} ({'−' if lado < 0 else '+'}Y)", copa, material="acero")
    plan.union(f"{suf}_brida", suf, chumacera_suf, "perno",
               "tapa atornillada a la brida de la chumacera", size="M6", qty=2)


def tensor_carro(plan: Plan, c: Cotas, i: int, lado: float, rail: str) -> float:
    """Unidad tensora de carro UCT por fuera del larguero (su tornillo empuja hacia −X: tensa
    la banda) y, con guardas, la tapa de su barreno. Devuelve |y| del extremo del eje."""
    p = CATALOG[c.uct].params
    a, d = float(p["A"]), float(p["d"])
    suf = f"tensor{i}"
    plan.pieza(suf, f"Tensor de carro ({i})", build_component(c.uct)[0], comp=c.uct,
               pos=(-c.half, lado * (c.y_out + a / 2.0), c.zc), key=f"comp|{c.uct}|std")
    plan.union(f"{suf}_larg", suf, rail, "perno",
               "marco del tensor atornillado al larguero sobre su ranura", size="M12", qty=4)
    plan.union(f"{suf}_eje", "tambor_cola", suf, "contacto",
               "eje en el inserto del carro, fijado con sus prisioneros")
    if c.guardas:
        ya = c.y_out + a
        tapa = cilindro_y(-c.half, c.zc, lado * ya, lado * (ya + TAPA_T), d / 2.0 + 12.0)
        plan.pieza(f"tapa_c{i}", f"Tapa del tensor ({i})", tapa, material="acero")
        plan.union(f"tapa_c{i}_carro", f"tapa_c{i}", suf, "perno",
                   "tapa atornillada al carro sobre el extremo del eje", size="M6", qty=2)
    return c.y_out + a - 2.0


def motorreductor(plan: Plan, c: Cotas, y_collar: float) -> float:
    """Motorreductor coaxial al eje motriz (+Y) con acople flexible y su base en voladizo.
    Devuelve |y| del extremo del eje motriz (dentro del cubo del acople)."""
    comp = CATALOG[c.motor]
    forma, _ = build_component(c.motor)
    bb = forma.bounding_box()
    prm = comp.params or {}
    d_mot = float(prm.get("shaft_d") or 0.22 * float(prm.get("box_size", 100.0)))
    cubo = 1.5 * max(c.d_m, d_mot)                   # largo de cada cubo del acople
    od = round(2.6 * max(c.d_m, d_mot))
    y_c0 = y_collar + 8.0
    y_c1 = y_c0 + 2.0 * cubo + 10.0
    y_mo = y_c1 - cubo + bb.max.X                    # el extremo del eje del motor en el cubo
    x, z = c.half, c.zm
    plan.pieza("motor", "Motorreductor", forma, comp=c.motor, pos=(x, y_mo, z), rot=(0, 0, -90),
               key=f"comp|{c.motor}|std")
    acople = (cilindro_y(x, z, y_c0, y_c1, od / 2.0)
              - cilindro_y(x, z, y_c0 - 1.0, y_c0 + cubo, c.d_m / 2.0)
              - cilindro_y(x, z, y_c1 - cubo, y_c1 + 1.0, d_mot / 2.0))
    plan.pieza("acople", "Acople flexible", acople, material="acero")
    plan.union("acople_eje", "acople", "tambor_motriz", "perno",
               "cubo del acople en el eje motriz: chaveta + prisionero", size="M8", qty=1)
    plan.union("acople_motor", "acople", "motor", "perno",
               "cubo del acople en el eje del motorreductor: chaveta + prisionero", size="M8",
               qty=1)
    _base_motor(plan, c, bb, y0=y_c0 - 10.0, y1=y_mo - bb.min.X + 10.0, y_mo=y_mo)
    if c.guardas:
        _guarda_acople(plan, c, forma, bb, y_mo, y_c0 - 7.0, od, d_mot)
    return y_c0 + cubo


def _base_motor(plan: Plan, c: Cotas, bb, y0: float, y1: float, y_mo: float) -> None:
    """Placa bajo las patas del motor sobre dos brazos soldados a una ménsula que se suelda a la
    cara exterior de la pata del lado motriz (+Y). Con el criterio 7 (F1b, D9), los brazos a tope
    contra la pata, con su cuenta y, si no da, tornapuntas (`belt_conveyor_motor.py`)."""
    if c.criterio >= 7:
        from .belt_conveyor_motor import base_motor

        base_motor(plan, c, bb, y_mo, y0, y1)
        return
    x = c.half
    z_patas = c.zm + bb.min.Z
    w = bb.max.Y
    y_pata = c.y_in + LEG_W                          # cara exterior de la pata +Y
    zb0 = z_patas - BASE_MOTOR_T
    za0 = zb0 - LEG_W
    zm0 = za0 - LEG_W
    mat = str(CATALOG[TUBO_BASE].specs.get("material") or "acero")
    plan.pieza("base_motor", "Base del motor", caja(x - w, x + w, y0, y1, zb0, z_patas),
               material="acero")
    mens, mcut = build_component(TUBO_BASE, 2.0 * w)
    plan.pieza("mensula_motor", "Ménsula del motor", mens, comp=TUBO_BASE, cut=mcut,
               pos=(x, y_pata + LEG_W / 2.0, zm0 + LEG_W / 2.0), rot=(0, 90, 0),
               key=f"comp|{TUBO_BASE}|{mcut}", material=mat)
    plan.union("mensula_pata", "mensula_motor", "leg4", "soldadura",
               "ménsula soldada a la cara exterior de la pata", throat_mm=4,
               length_mm=round(4 * LEG_W, 1))
    largo_brazo = y1 - (y_pata + 1.0)
    brazo, bcut = build_component(TUBO_BASE, largo_brazo)
    for k, sx in ((1, -1.0), (2, 1.0)):
        xb = x + sx * (w - LEG_W / 2.0 - 10.0)
        plan.pieza(f"brazo_motor{k}", f"Brazo de la base del motor ({k})", brazo, comp=TUBO_BASE,
                   cut=bcut, pos=(xb, y_pata + 1.0 + largo_brazo / 2.0, za0 + LEG_W / 2.0),
                   rot=(90, 0, 0), key=f"comp|{TUBO_BASE}|{bcut}", material=mat)
        plan.union(f"brazo{k}_mensula", f"brazo_motor{k}", "mensula_motor", "soldadura",
                   "brazo soldado sobre la ménsula", throat_mm=3, length_mm=round(2 * LEG_W, 1))
        plan.union(f"base_brazo{k}", "base_motor", f"brazo_motor{k}", "soldadura",
                   "base soldada sobre el brazo", throat_mm=3, length_mm=200.0)
    plan.union("motor_base", "motor", "base_motor", "perno",
               "patas del motorreductor a la base (4 pernos)", size="M10", qty=4)


def _guarda_acople(plan: Plan, c: Cotas, forma, bb, y_mo: float, ya: float, od: float,
                   d_mot: float) -> None:
    """Cubierta de chapa sin fondo del extremo de la chumacera a la cara del reductor (cubre el
    acople y el eje de salida), con pasos para los ejes y escotada sobre las patas del motor;
    atornillada a la base. Las cotas del motor se MIDEN en su forma (marco local: eje X)."""
    # patas: lo más bajo de la forma; su tope, en una franja de 2 mm del borde exterior de la
    # pata (ahí no llega el cuerpo del motor); la cara del reductor, justo encima del eje
    patas = (forma & caja(bb.min.X - 1, bb.max.X + 1, bb.min.Y - 1, bb.max.Y + 1, bb.min.Z,
                          bb.min.Z + 1.0)).bounding_box()
    z_pata = (forma & caja(patas.min.X, patas.max.X, patas.max.Y - 2.0, patas.max.Y, bb.min.Z,
                           bb.min.Z + 40.0)).bounding_box().max.Z
    cara = (forma & caja(0.0, bb.max.X + 1, -1.0, 1.0, d_mot / 2.0 + 2.0,
                         d_mot / 2.0 + 4.0)).bounding_box().max.X
    x, z, e = c.half, c.zm, 2.0
    yb = y_mo - cara - 1.0
    za, zb = z + bb.min.Z, z + od / 2.0 + 10.0
    hx = od / 2.0 + 10.0
    lleno = caja(x - hx, x + hx, ya, yb, za, zb)
    hueco = caja(x - hx + e, x + hx - e, ya + e, yb - e, za - 1.0, zb - e)
    pasos = (cilindro_y(x, z, ya - 1.0, ya + e + 1.0, c.d_m / 2.0 + 5.0)
             + cilindro_y(x, z, yb - e - 1.0, yb + 1.0, d_mot / 2.0 + 5.0))
    escote = caja(x - patas.max.Y - 1.0, x + patas.max.Y + 1.0, y_mo - patas.max.X - 1.0,
                  yb + 1.0, za - 1.0, z + z_pata + 1.0)
    plan.pieza("guarda_acople", "Guarda del acople", lleno - hueco - pasos - escote,
               material="acero")
    plan.union("guarda_acople_base", "guarda_acople", "base_motor", "perno",
               "guarda atornillada a la base del motor", size="M6", qty=4)
