"""Apoyos de los ejes y accionamiento de `create_belt_conveyor` con el criterio 8 (F1c del plan
faja-larga-en-tramos, D10, D11, D12, D14). Lo usa `belt_conveyor_tambores.py` sólo con
`criterio >= 8`.

- **D10 Chumacera motriz**: la placa porta-chumacera (12 mm, soldada plana a la cara exterior
  del larguero) lleva los 4 agujeros de la brida ROSCADOS (broca de machuelo M10 = Ø8,5): los
  pernos de la UCF entran por la brida y enroscan en la placa con la punta dentro de ella; nada
  queda dentro del tubo. La cuenta (`belt_conveyor_taller.cuenta_rosca`): brida de 14 mm, M10x25,
  enganche 11 mm ≥ 1·d (VDI 2230; cubre 0,8·d de DIN 934 / ISO 898-2).
- **D11 Tensor**: el marco del UCT apoyaba en la cara exterior del larguero con 4 M12 cuyas
  tuercas caían dentro del tubo. Ahora apoya en una PLACA PORTA-TENSOR de `PLACA_TENSOR_T` soldada
  al larguero (sale `PLACA_TENSOR_MARGEN` del marco, con la ranura de la carrera del eje) con los
  4 M12 roscados. Se descartó el perno pasante con buje: su tuerca caería en la cara interior,
  a 10 mm del tambor de cola.
- **Tapas de los extremos de eje**: la de la chumacera, con dos orejas sobre la brida y M6 a
  rosca en la brida (hierro fundido: enganche ≥ 1,5·d); la del tensor, un disco más ancho con dos
  M6 a rosca en el soporte del carro.
- **Accionamiento**: el agujero roscado del prisionero en cada cubo del acople (DIN 916, el largo
  que cabe en la pared del cubo), la base del motor roscada bajo las patas del motorreductor
  (M10) y la guarda del acople con cuatro pestañas atornilladas a rosca en la base (M6).
"""

from __future__ import annotations

from .belt_conveyor_plan import Plan, caja, ranura_x
from .belt_conveyor_taller import (
    K_FUNDICION,
    broca,
    cuenta_rosca,
    nota_rosca,
    paso,
    taladro_y,
    taladro_z,
)

PLACA_TENSOR_T = 16.0       # placa porta-tensor: rosca M12 de ≥ 1·d con su margen
PLACA_TENSOR_MARGEN = 15.0  # lo que la placa sale del marco del UCT
ESQUINA_MARCO = 6.0         # los agujeros del marco, en sus esquinas (cabezal × riel)
PERNO_MARCO = "M12"
PERNO_TAPA = "M6"
PERNO_PRISIONERO = "M8"
SERIE_DIN916 = (8, 10, 12, 16, 20, 25, 30, 35, 40)   # prisionero de punta plana, M8
ARANDELA_M10 = 2.0          # ISO 7089 bajo la cabeza de los pernos de las patas del motor


def _registrar(plan: Plan, cuenta: dict) -> dict:
    plan.calculos.setdefault("roscas", []).append(cuenta)
    return cuenta


def placa_chumacera(plan: Plan, placa, c, ref: str, x: float, z: float, lado: float, suf: str,
                    y_placa: float):
    """(placa con los 4 agujeros roscados de la brida, nota de la unión brida ↔ placa)."""
    from .belt_conveyor_cotas import PLACA_CHUMACERA_T, perno_de_brida
    from .catalog import CATALOG

    prm = CATALOG[ref].params
    h, size = float(prm["bolt_span"]) / 2.0, perno_de_brida(ref)
    for dx in (-h, h):
        for dz in (-h, h):
            placa = placa - taladro_y(x + dx, z + dz, lado * (c.y_out - 1.0),
                                      lado * (y_placa + 1.0), broca(size))
    cuenta = _registrar(plan, cuenta_rosca(f"{suf}_placa", size, float(prm["s"]),
                                           PLACA_CHUMACERA_T, "la placa porta-chumacera"))
    return placa, nota_rosca("brida de la chumacera a la placa porta-chumacera", cuenta)


def orejas_tapa(plan: Plan, copa, ref: str, x: float, z: float, lado: float, ya: float,
                r_in: float, tapa_t: float, suf: str):
    """(la copa con dos orejas sobre la brida y su agujero, nota de la unión tapa ↔ brida)."""
    from .catalog import CATALOG

    d0 = paso(PERNO_TAPA)
    borde = 1.2 * d0 + d0 / 2.0
    r_h = r_in + tapa_t + 6.0
    for sx in (-1.0, 1.0):
        oreja = caja(x + sx * (r_in + 1.0), x + sx * (r_h + borde), lado * ya,
                     lado * (ya + tapa_t), z - borde, z + borde)
        copa = copa + oreja - taladro_y(x + sx * r_h, z, lado * (ya - 1.0),
                                        lado * (ya + tapa_t + 1.0), d0)
    s = float(CATALOG[ref].params["s"])
    cuenta = _registrar(plan, cuenta_rosca(f"{suf}_brida", PERNO_TAPA, tapa_t, s,
                                           "la brida de la chumacera (hierro fundido, taladrada)",
                                           k=K_FUNDICION))
    return copa, nota_rosca("tapa atornillada a la brida de la chumacera", cuenta)


def placa_tensor(plan: Plan, c, i: int, lado: float, rail: str) -> str:
    """La placa porta-tensor soldada al larguero (D11), con la ranura de la carrera del eje y los
    4 M12 del marco roscados. Devuelve su sufijo."""
    from .belt_conveyor_cotas import HOLGURA_EJE
    from .catalog import CATALOG

    p = CATALOG[c.uct].params
    L, H, m = float(p["L"]), float(p["H"]), PLACA_TENSOR_MARGEN
    y0, y1 = lado * c.y_out, lado * (c.y_out + PLACA_TENSOR_T)
    xm = c.x_tc  # el centro del marco = el de la carrera (faja-compacta D4; −half hasta el 8)
    placa = caja(xm - L / 2.0 - m, xm + L / 2.0 + m, y0, y1, c.zc - H / 2.0 - m,
                 c.zc + H / 2.0 + m)
    alto = c.d_c + 2.0 * HOLGURA_EJE
    xr, carrera = c.ranura_cola
    placa = placa - ranura_x(xr, c.zc, y0 - lado, y1 + lado, carrera + alto, alto)
    for dx in (-1.0, 1.0):
        for dz in (-1.0, 1.0):
            placa = placa - taladro_y(xm + dx * (L / 2.0 - ESQUINA_MARCO),
                                      c.zc + dz * (H / 2.0 - ESQUINA_MARCO), y0 - lado, y1 + lado,
                                      broca(PERNO_MARCO))
    psuf = f"tensor{i}_placa"
    plan.pieza(psuf, f"Placa porta-tensor ({i})", placa, material="acero")
    plan.union(f"{psuf}_sold", psuf, rail, "soldadura",
               "placa porta-tensor soldada al larguero (filetes arriba y abajo)", throat_mm=4,
               length_mm=round(2.0 * (L + 2.0 * m), 1))
    cuenta = _registrar(plan, cuenta_rosca(f"tensor{i}_placa", PERNO_MARCO, float(p["A"]),
                                           PLACA_TENSOR_T, "la placa porta-tensor"))
    plan.union(f"tensor{i}_placa", f"tensor{i}", psuf, "perno",
               nota_rosca("marco del tensor a la placa porta-tensor", cuenta), size=PERNO_MARCO,
               qty=4)
    return psuf


def tapa_carro(plan: Plan, c, i: int, lado: float, ya: float, tapa_t: float):
    """(el disco de la tapa del tensor con sus dos agujeros, nota de su unión al carro)."""
    from .belt_conveyor_plan import cilindro_y
    from .catalog import CATALOG

    d = float(CATALOG[c.uct].params["d"])
    r_h = d / 2.0 + 11.0
    tapa = cilindro_y(-c.half, c.zc, lado * ya, lado * (ya + tapa_t), r_h + 1.2 * paso(PERNO_TAPA)
                      + paso(PERNO_TAPA) / 2.0)
    for sx in (-1.0, 1.0):
        tapa = tapa - taladro_y(-c.half + sx * r_h, c.zc, lado * (ya - 1.0),
                                lado * (ya + tapa_t + 1.0), paso(PERNO_TAPA))
    cuenta = _registrar(plan, cuenta_rosca(f"tapa_c{i}_carro", PERNO_TAPA, tapa_t,
                                           float(CATALOG[c.uct].params["A"]),
                                           "el soporte del carro (hierro fundido, taladrado)",
                                           k=K_FUNDICION))
    return tapa, nota_rosca("tapa atornillada al carro sobre el extremo del eje", cuenta)


# ------------------------------------------------------------------ accionamiento
def prisionero(pared: float) -> float:
    """El prisionero DIN 916 más largo que cabe en la pared del cubo (1 mm adentro)."""
    return float(max(L for L in SERIE_DIN916 if L <= pared - 1.0))


def acople_prisioneros(acople, x: float, z: float, ys, od: float, ds):
    """El acople con el agujero roscado (M8, broca Ø6,8) del prisionero sobre cada cubo."""
    for y, d in zip(ys, ds):
        acople = acople - taladro_z(x, y, z + d / 2.0 - 1.0, z + od / 2.0 + 1.0,
                                    broca(PERNO_PRISIONERO))
    return acople


def nota_prisionero(que: str, od: float, d: float) -> str:
    largo = prisionero(od / 2.0 - d / 2.0)
    return f"{que}: chaveta + prisionero {PERNO_PRISIONERO}x{largo:g} DIN 916"


def medidas_motor(forma, bb, d_mot: float):
    """(patas, z de su cara superior, cara del reductor): medidas en la forma del motor (marco
    local: eje X; las de `_guarda_acople`)."""
    patas = (forma & caja(bb.min.X - 1, bb.max.X + 1, bb.min.Y - 1, bb.max.Y + 1, bb.min.Z,
                          bb.min.Z + 1.0)).bounding_box()
    z_pata = (forma & caja(patas.min.X, patas.max.X, patas.max.Y - 2.0, patas.max.Y, bb.min.Z,
                           bb.min.Z + 40.0)).bounding_box().max.Z
    cara = (forma & caja(0.0, bb.max.X + 1, -1.0, 1.0, d_mot / 2.0 + 2.0,
                         d_mot / 2.0 + 4.0)).bounding_box().max.X
    return patas, z_pata, cara


def pie_motor(forma, bb) -> tuple[float, float, float, float]:
    """(x0, x1, y del eje, espesor) de la pata +Y del motor, MEDIDOS en su forma (marco local):
    la tira de su eje, de abajo hacia arriba, hasta el primer hueco (encima va el cuerpo)."""
    base = (forma & caja(bb.min.X - 1, bb.max.X + 1, 0.0, bb.max.Y + 1, bb.min.Z,
                         bb.min.Z + 1.0)).bounding_box()
    yc = (base.min.Y + base.max.Y) / 2.0
    tira = forma & caja(base.min.X + 5.0, base.max.X - 5.0, yc - 1.0, yc + 1.0, bb.min.Z,
                        bb.max.Z)
    pie = min(tira.solids(), key=lambda s: s.bounding_box().min.Z).bounding_box()
    return base.min.X, base.max.X, yc, pie.max.Z - bb.min.Z


def taladros_motor(plan: Plan, x: float, y_mo: float, forma, bb):
    """(agujeros roscados M10 de la base bajo el eje de las patas del motor, a 15 mm de sus
    puntas; alivios de la punta en el brazo de abajo, si la punta pasa la base; nota de la
    unión). El perno aprieta la pata y su arandela (ISO 7089). La placa de 12 mm deja una
    ventana de 1,5 mm entre «engancha 1·d» y «la punta no la pasa», más angosta que el paso de la
    serie de largos: cuando ningún largo cae en ella, la punta entra por un alivio (agujero de
    paso) en la pared superior del brazo, que es un tubo: no lleva tuerca, sólo deja pasar."""
    from .belt_conveyor_cotas import LEG_W
    from .belt_conveyor_tambores import BASE_MOTOR_T, TUBO_BASE
    from .catalog import CATALOG

    x0, x1, yc, t = pie_motor(forma, bb)
    pts = [(x + sy * yc, y_mo - xl) for xl in (x0 + 15.0, x1 - 15.0) for sy in (-1.0, 1.0)]
    pared = float((CATALOG[TUBO_BASE].params or {}).get("wall", 3.2))
    cuenta = _registrar(plan, cuenta_rosca("motor_base", "M10", t + ARANDELA_M10, BASE_MOTOR_T,
                                           "la base del motor", fondo=LEG_W - pared - 1.0))
    alivios = [(px, py, paso("M10")) for px, py in pts] if cuenta["pasa_mm"] > -0.5 else []
    nota = nota_rosca("patas del motorreductor a la base (con arandela)", cuenta)
    if alivios:
        nota += "; la punta entra en el brazo por su alivio"
    return [(px, py, broca("M10")) for px, py in pts], alivios, nota


def pestanas_acople(x: float, ya: float, yb: float, hx: float):
    """(x, y) de los 4 pernos de la guarda del acople: dos pestañas por costado, a ras de la base."""
    y2 = min(ya + 42.0, yb - 14.0)
    return [(x + sx * (hx + 12.0), y) for sx in (-1.0, 1.0) for y in (ya + 12.0, y2)]


def pestanas(forma, pts, x: float, za: float, e: float, hx: float):
    """La guarda del acople con sus pestañas (24 × 24, a ras de la base) y su agujero."""
    for px, py in pts:
        sx = 1.0 if px > x else -1.0
        forma = forma + caja(x + sx * (hx - e), x + sx * (hx + 24.0), py - 12.0, py + 12.0, za,
                             za + e)
    for px, py in pts:
        forma = forma - taladro_z(px, py, za - 1.0, za + e + 1.0, paso(PERNO_TAPA))
    return forma


def nota_pestanas(plan: Plan, e: float) -> str:
    from .belt_conveyor_tambores import BASE_MOTOR_T

    cuenta = _registrar(plan, cuenta_rosca("guarda_acople_base", PERNO_TAPA, e, BASE_MOTOR_T,
                                           "la base del motor"))
    return nota_rosca("guarda atornillada a la base del motor", cuenta)
