"""Cotas puras de `create_belt_conveyor` (v4–v5): de los params a las medidas de cada pieza, sin OCCT.

Las piezas las arman `belt_conveyor_bastidor.py`, `belt_conveyor_tambores.py` y
`belt_conveyor_guardas.py` con estas cotas; el orden y la banda, `belt_conveyor.py`.

Referencias de la disposición (Z arriba, transporte hacia +X, tambor motriz en +X):
- los ejes de los tambores bajan lo que crece su tambor (engomado): el ramal de carga queda
  plano a la altura de trabajo (`altura` = cara superior de la banda);
- el larguero lleva su cara superior 3 mm sobre el tope de los tambores y los dos ejes pasan
  por su ALMA con holgura (barreno Ø eje + 6; en la cola, una ranura con la carrera del tensor);
- chumaceras y tensores van POR FUERA de los largueros (se atornillan y se cambian sin
  desarmar la faja); el motorreductor va en voladizo del lado +Y, coaxial al eje motriz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .catalog import CATALOG, refs_in_category

LEG_REF = "TUBO-2X2"
BRACE_REF = "TUBO-2X2"
FOOT_REF = "PIE-M12-50"
FACE_MARGIN = 50.0       # ancho de cara del tambor = ancho de banda + margen (25/lado)
BANDA_A_LARGUERO = 35.0  # del borde de la banda a la cara interior del larguero
LARGUERO_SOBRE_TAMBOR = 3.0  # cara superior del larguero sobre el tope de los tambores
HOLGURA_EJE = 3.0        # radial, en el paso del eje por el larguero y la placa
PLACA_CHUMACERA_T = 12.0  # placa porta-chumacera soldada al larguero (roscas de la brida)
NIVELACION_MM = 20.0     # vástago visible del pie nivelador (regulación de la altura)
PLACA_PATA = 80.0
PLACA_PATA_T = 8.0
CAMA_T = 6.0             # chapa de la cama de deslizamiento
CAMA_HOLGURA = 2.0       # de la cama a la cara inferior del ramal de carga
CAMA_A_TAMBOR = 10.0     # de la punta de la cama a la superficie del tambor (en su carrera)
SOPORTE_PASO = 800.0     # paso máximo de los soportes de la cama
PLACA_SOPORTE_T = 6.0
LEG_W = 50.8             # TUBO-2X2
VANO_MAX = 4000.0        # vano máximo entre estaciones de patas (flecha del larguero)


@dataclass(frozen=True)
class Cotas:
    largo: float
    ancho: float
    altura: float
    t: float                 # espesor de banda
    half: float
    cara: float              # ancho de cara de los tambores
    tambor_m: str
    tambor_c: str
    r_m: float               # radio exterior (engomado incluido)
    r_c: float
    d_m: float               # Ø de los ejes
    d_c: float
    zm: float                # eje del tambor motriz
    zc: float                # eje del tambor de cola
    tubo: str
    rail_t: float            # espesor del larguero en Y
    rail_h: float            # canto del larguero en Z
    wall: float
    y_in: float              # cara interior del larguero (|y|)
    rail_y: float            # eje del larguero (|y|)
    y_out: float             # cara exterior del larguero (|y|)
    rail_top: float
    rail_bot: float
    x0: float                # punta de cola de los largueros
    x1: float                # punta motriz
    chum_m: str              # chumacera de brida del eje motriz
    chum_c: str | None       # la de cola (sin tensor)
    uct: str | None          # unidad tensora de carro (con tensor)
    carrera: float           # carrera del tensor (0 sin tensor)
    x_leg_t: float
    x_leg_h: float
    motor: str | None
    guardas: bool
    cierres: bool = False    # v5: guardas inferiores y placas de cierre de los largueros
    # v6 (faja-larga-en-tramos): el bastidor en tramos iguales (`belt_conveyor_tramos.py`) y el
    # criterio de taller (6: rodillos de retorno y pernos pasantes con buje; 5: la v5 tal cual)
    tramo_max: float | None = None
    criterio: int = 5
    tramos: tuple = ()       # (x0, x1) del tubo de cada tramo de larguero, de la cola a la cabeza
    empalmes: tuple = ()     # X del centro de cada empalme (entre las dos placas)

    @property
    def n_tramos(self) -> int:
        return max(1, len(self.tramos))

    @property
    def viaje(self) -> float:
        """Lo que el tambor de cola corre hacia cada lado desde su posición de diseño."""
        return self.carrera / 2.0

    @property
    def leg_y(self) -> float:
        """Eje de las patas (|y|): a ras de la cara interior del larguero."""
        return self.y_in + LEG_W / 2.0

    @property
    def cama_top(self) -> float:
        return self.altura - self.t - CAMA_HOLGURA

    @property
    def cama_x0(self) -> float:
        return -self.half + self.r_c + self.viaje + CAMA_A_TAMBOR

    @property
    def cama_x1(self) -> float:
        return self.half - self.r_m - CAMA_A_TAMBOR


def radio_exterior(ref: str) -> float:
    """Radio que ABRAZA la banda: el del tambor más su engomado (`lagging_mm`), si lo tiene."""
    specs = CATALOG[ref].specs
    return float(specs["diametro_mm"]) / 2.0 + float(specs.get("lagging_mm", 0.0))


def chumacera_de_brida(d: float) -> str:
    """La chumacera de brida cuadrada (UCF) del catálogo para un eje de Ø `d`."""
    for ref in refs_in_category("chumaceras"):
        c = CATALOG[ref]
        if c.familia == "flange_bearing" and (c.params or {}).get("flange") == "cuadrada" \
                and math.isclose(float(c.params["d"]), d):
            return ref
    raise ValueError(f"no hay chumacera de brida UCF para un eje de Ø{d:g} mm en el catálogo")


def perno_de_brida(ref: str) -> str:
    """Métrica del perno que entra en los agujeros de la brida (agujero N − 2 mm, serie normal)."""
    n = float(CATALOG[ref].params["N"])
    for m in (10, 12, 14, 16, 20):
        if n - 2.0 <= m + 0.5:
            return f"M{m}"
    return "M20"


def unidades_tensoras() -> list[str]:
    """Las unidades tensoras de catálogo con su carrera de ficha (familia UCT)."""
    return [r for r in refs_in_category("chumaceras") if CATALOG[r].familia == "take_up_unit"]


def tensor_v4(ref: str | None, d_cola: float) -> str | None:
    """El tensor que monta la v4. Un tensor tipo trotadora de un log v3 (`TENSOR-TROT-xx`) se
    monta como la unidad tensora de carro UCT del mismo eje: la trotadora no tiene carrera de
    tensado medible (su perno es vertical) y la UCT sí, de ficha."""
    if ref is None:
        return None
    comp = CATALOG[ref]
    if comp.category == "tensores_trotadora":
        d = float(comp.specs.get("shaft_d") or (comp.params or {}).get("shaft_d") or d_cola)
        cands = [r for r in unidades_tensoras() if math.isclose(float(CATALOG[r].params["d"]), d)]
        if not cands:
            raise ValueError(f"no hay unidad tensora UCT para el eje Ø{d:g} del tensor {ref}")
        return cands[0]
    if comp.familia != "take_up_unit":
        raise ValueError(f"{ref} no es una unidad tensora de carro")
    return ref


def cotas(largo: float, ancho: float, altura: float, tambor_m: str, tambor_c: str, tubo: str,
          tensor: str | None, motor: str | None, espesor: float, guardas: bool,
          cierres: bool = False, tramo_max: float | None = None, criterio: int = 5) -> Cotas:
    from dataclasses import replace

    from .belt_conveyor_tramos import partir

    c = _cotas(largo, ancho, altura, tambor_m, tambor_c, tubo, tensor, motor, espesor, guardas,
               cierres)
    c = replace(c, tramo_max=tramo_max, criterio=criterio)
    tramos, empalmes = partir(c)
    return replace(c, tramos=tramos, empalmes=empalmes)


def _cotas(largo: float, ancho: float, altura: float, tambor_m: str, tambor_c: str, tubo: str,
           tensor: str | None, motor: str | None, espesor: float, guardas: bool,
           cierres: bool) -> Cotas:
    r_m, r_c = radio_exterior(tambor_m), radio_exterior(tambor_c)
    d_m = float(CATALOG[tambor_m].specs["eje_mm"])
    d_c = float(CATALOG[tambor_c].specs["eje_mm"])
    tube = CATALOG[tubo]
    rail_t, rail_h = float(tube.specs["height"]), float(tube.specs["width"])
    wall = float((tube.params or {}).get("wall", 3.0))
    if ancho < 100.0:
        raise ValueError("Ancho de banda mínimo 100 mm")
    uct = tensor_v4(tensor, d_c)
    carrera = 0.0
    if uct is not None:
        carrera = float(CATALOG[uct].params["carrera"])
        if not math.isclose(float(CATALOG[uct].params["d"]), d_c):
            raise ValueError(f"el tensor {uct} es para eje Ø{CATALOG[uct].params['d']:g} y el "
                             f"tambor de cola {tambor_c} lleva eje Ø{d_c:g}")
    minimo = max(2.0 * (r_m + r_c) + 200.0, r_m + r_c + carrera / 2.0 + 400.0)
    if largo < minimo:
        raise ValueError(f"Largo mínimo {minimo:g} mm (dos tambores, su tensor y la cama)")
    half = largo / 2.0
    zm, zc = altura - r_m - espesor, altura - r_c - espesor
    rail_top = altura - espesor + LARGUERO_SOBRE_TAMBOR
    rail_bot = rail_top - rail_h
    for z, d, quien in ((zm, d_m, "motriz"), (zc, d_c, "de cola")):
        r = d / 2.0 + HOLGURA_EJE
        if z + r > rail_top - wall or z - r < rail_bot + wall:
            raise ValueError(f"el tubo {tubo} ({rail_h:g} mm de canto) no deja pasar el eje "
                             f"{quien} Ø{d:g} por su alma: usa un tubo de más canto")
    y_in = ancho / 2.0 + BANDA_A_LARGUERO
    chum_m = chumacera_de_brida(d_m)
    chum_c = None if uct else chumacera_de_brida(d_c)

    def placa_w(ref):
        return float(CATALOG[ref].params["size_w"]) + 30.0

    x1 = half + max(r_m + espesor + 40.0, placa_w(chum_m) / 2.0 + 15.0)
    if uct:
        voladizo_c = float(CATALOG[uct].params["L"]) / 2.0 + 15.0
        x_leg_t = -half + float(CATALOG[uct].params["L"]) / 2.0 + LEG_W / 2.0 + 10.0
    else:
        voladizo_c = max(r_c + espesor + 40.0, placa_w(chum_c) / 2.0 + 15.0)
        x_leg_t = -half
    if rail_bot < PLACA_PATA_T + NIVELACION_MM + 200.0:
        raise ValueError(f"Altura de trabajo insuficiente para las patas (el larguero queda a "
                         f"{rail_bot:g} mm del piso)")
    return Cotas(
        largo=largo, ancho=ancho, altura=altura, t=espesor, half=half, cara=ancho + FACE_MARGIN,
        tambor_m=tambor_m, tambor_c=tambor_c, r_m=r_m, r_c=r_c, d_m=d_m, d_c=d_c, zm=zm, zc=zc,
        tubo=tubo, rail_t=rail_t, rail_h=rail_h, wall=wall, y_in=y_in, rail_y=y_in + rail_t / 2.0,
        y_out=y_in + rail_t, rail_top=rail_top, rail_bot=rail_bot, x0=-half - voladizo_c, x1=x1,
        chum_m=chum_m, chum_c=chum_c, uct=uct, carrera=carrera, x_leg_t=x_leg_t, x_leg_h=half,
        motor=motor, guardas=guardas, cierres=cierres)
