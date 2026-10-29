"""El motor ELEGIDO POR CUENTA del transportador de rodillos por cadena (`create_roller_conveyor`
con `motor: "auto"`, plan `docs/plans/plantilla-rodillos-cadena.md`, F9: E12, E13 y E14). Puro.

**Qué motor** (E12): el motorreductor de tornillo sinfín NMRV (`motorreductores_sinfin`) más
chico que da la potencia de la cuenta (`rodillos_cadena.potencia_requerida` con η = `ETA_SINFIN`,
la carga del comando: la que el modelador sacó de los requisitos) a la TENSIÓN de la red
(`red_v`): sirve si una de sus tensiones de placa está a ±5 % (IEC 60034-1 §7.3, zona A: Lima
220 V acepta un 220/380 V o un 230/400 V; nunca un 400 V solo). La velocidad sale de la relación
`i` de su serie (`specs.relaciones_i`) y del piñón ASA 40 simple del motor (± 10 %).

**Dónde va** (E13): el sinfín es de ejes ORTOGONALES: su salida va a lo ancho (Y, a la hilera 2
del último rodillo) y el motor, A LO LARGO (−X, bajo los rodillos), así que el ancho que ocupa es
el de la caja y el motor (Ø), no su largo: arma con todo ancho útil de la familia (≥ 400). Se
monta girado 180° sobre X (`ROTACION`): la brida y el eje hueco hacia +Y (ahí entra el eje de
salida enchufable, accesorio de catálogo de la serie NMRV) y la tapa hacia −Y; el motor queda
SOBRE el eje de salida y la caja de bornes mira al piso. La caja apoya en un calzo soldado a la
base (el cuerpo del motor baja más que la caja: sin calzo la base lo cortaría) con sus 4 tornillos
a las roscas de la cara de la caja, desde abajo; el travesaño portamotor va ENTRE la caja de
bornes y esos tornillos (la llave entra).

**La cadena** (E14): la cadena motriz y los lazos llevan el par NOMINAL del motor elegido (un
bulto trabado le pide todo su par) con FS ≥ `FS_CADENA` (la regla `transmision.capacidad` de la
puerta, tabla ACA de ASME B29.1), y el piñón del motor tiene ≥ `Z_MOTRIZ_MIN` dientes (con menos,
sólo servicio lento y liviano: Tsubaki «Chain Drive Selection», la misma cifra de
`engineering/cadena.py`). La única cadena con piñón de rodillo de catálogo es la ASA 40-1
(doble-simple Z15): si su FS no alcanza con el motor más chico que da la potencia, el error lo
dice (una ASA 40-2 o 50 pide un piñón doble-dúplex o ASA 50 doble-simple que el catálogo no tiene).

Las cotas de la caja salen de las fórmulas del builder `worm_gearmotor` (`builders_accionamiento`),
como `rodillos_cadena_motriz.motor_local` con el helicoidal; un test las compara con el sólido.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .catalog import CATALOG

ROTACION = {"x": 180, "y": 0, "z": 0}
CALZO_T = 12.0             # el motor de 0,25–0,55 kW baja 2–8 mm bajo la caja: el calzo lo libra
ETA_SINFIN = 0.75          # rendimiento del sinfín (el de `rules.detect_conveyor` para el NMRV)
TOL_TENSION = 0.05         # IEC 60034-1 §7.3, zona A: ±5 % de la tensión de placa
Z_MOTRIZ_MIN = 17
FS_CADENA = 1.2            # el umbral del ítem `transmision.capacidad` de la puerta
BORDE_ROSCA = 10.0         # rosca de la cara de la caja a esto de su canto (≈ 1,5 · d0 de un M6)
HOLGURA_MOTOR = 5.0        # cuerpo del motor ↔ guarda fija y nada que gire ↔ base


def sinfines() -> list[str]:
    """Los motorreductores sinfín del catálogo, de menor a mayor potencia."""
    refs = [r for r, c in CATALOG.items() if c.category == "motorreductores_sinfin"]
    return sorted(refs, key=lambda r: (float(CATALOG[r].specs["potencia_kW"]), r))


def tensiones(ref: str) -> tuple[float, ...]:
    """Las tensiones de placa (V entre fases) de un motorreductor: las de su ficha eléctrica o,
    sin ella, las de `specs.tension` («230/400V»)."""
    c = CATALOG[ref]
    el = getattr(c, "electrico", None)
    for carga in getattr(el, "cargas", ()) or ():
        if carga.tension is not None and carga.tension.valores:
            return tuple(float(v) for v in carga.tension.valores)
    return tuple(float(v) for v in re.findall(r"\d+(?:\.\d+)?", str(c.specs.get("tension", ""))))


def sirve_red(ref: str, red_v: float) -> bool:
    return any(abs(u - red_v) <= TOL_TENSION * red_v + 1e-9 for u in tensiones(ref))


def rpm_motor(ref: str) -> float:
    """rpm del motor (placa de su ficha eléctrica, 4 polos a 60 Hz)."""
    el = getattr(CATALOG[ref], "electrico", None)
    n = (getattr(el, "modelo", None) or {}).get("n_rpm")
    if not n:
        raise ValueError(f"{ref}: la ficha no publica las rpm del motor (n_rpm)")
    return float(n)


@dataclass(frozen=True)
class SinfinLocal:
    """Cotas del NMRV YA GIRADO (`ROTACION`) alrededor del eje de salida (origen del builder):
    x a lo largo del transporte, y a lo largo del eje de salida, z hacia arriba."""

    hw: float              # caja de la corona: x, z ∈ ±hw/2
    hy: float              # y ∈ ±hy/2
    bore_d: float
    cara_salida: float     # y del cubo de la brida (la salida del eje), hacia +Y
    tapa: float            # y de la cara de la tapa del eje hueco, hacia −Y
    brida_r: float
    pernos_brida_z: float  # z del perno más bajo de la brida
    motor_x0: float        # el motor (con el ventilador) va de motor_x1 a motor_x0 (< 0)
    motor_x1: float
    motor_z: float         # centro del motor
    motor_r: float
    bornes_x1: float       # extremo de la caja de bornes hacia la caja reductora
    bornes_z0: float
    z_tope: float          # lo más alto (cuerpo del motor)


def sinfin_local(ref: str) -> SinfinLocal:
    p = CATALOG[ref].params or {}
    cd, bore = float(p["center_distance"]), float(p["bore_d"])
    md, ml = float(p["motor_d"]), float(p["motor_len"])
    hw, hy, fd = cd * 1.7, cd * 1.3, cd * 1.7
    mz = 0.42 * hw                       # zoff = −0.42·hw, girado 180° sobre X
    mx = -0.6 * hw - ml / 2.0
    rbc = fd / 2.0 - cd * 0.13
    return SinfinLocal(
        hw=hw, hy=hy, bore_d=bore, cara_salida=hy / 2.0 + 24.0, tapa=hy / 2.0 + 14.5,
        brida_r=fd / 2.0, pernos_brida_z=-(rbc + 4.5), motor_x0=mx - ml / 2.0 - 30.0,
        motor_x1=-0.6 * hw, motor_z=mz, motor_r=md / 2.0, bornes_x1=mx + 0.21 * ml,
        bornes_z0=mz - 0.5 * md - 12.0 - 0.15 * md, z_tope=mz + md / 2.0,
    )


def perno_caja(ref: str) -> str:
    """La métrica de las roscas de la cara de la caja (Motovario NMRV: M6 hasta el 040, M8 del
    050 al 075, M10 de ahí arriba; del orden del catálogo rev0 2017, a verificar)."""
    cd = float((CATALOG[ref].params or {})["center_distance"])
    return "M6" if cd <= 40 else ("M8" if cd <= 75 else "M10")


def velocidad(d_rodillo: float, ref: str, i: float, z_motor: int) -> float:
    from .rodillos_cadena_motriz import velocidad_producto

    return velocidad_producto(d_rodillo, rpm_motor(ref) / i, z_motor)


def fs_cadena(potencia_kw: float, rpm_rodillo: float) -> float | None:
    """FS de la ASA 40-1 con el piñón Z15 del rodillo a `rpm_rodillo` contra la potencia nominal
    del motor con servicio moderado: la cuenta de `engineering/cadena.regla_cadena`."""
    from .rodillos_cadena_motriz import CADENA, PINON_RODILLO
    from .transmision import HP_A_KW, factor_hileras, factor_servicio, potencia_nominal_asa40_1_hp

    zr = int(CATALOG[PINON_RODILLO].specs["z"])
    hp = potencia_nominal_asa40_1_hp(zr, rpm_rodillo)
    if hp is None:
        return None
    hileras = int(CATALOG[CADENA].specs.get("hileras", 1))
    return hp * HP_A_KW * factor_hileras(hileras) / (potencia_kw * factor_servicio("moderado"))


def elegir(d_rodillo: float, v_obj: float, red_v: float, potencia_de, armar):
    """(motor, piñón, i) del motorreductor sinfín más chico que sirve: tensión de la red,
    potencia de la cuenta (`potencia_de(v)` en kW a la velocidad real), cadena con FS ≥
    `FS_CADENA` contra su par nominal, piñón del motor ≥ Z17 que entra en el eje y da `v_obj`
    ± 10 % con una relación de su serie, y `armar(motor, piñón, i)` (motriz + guardas) sin
    error. Si ninguno, `ValueError` con lo que falta de cada uno."""
    from .rodillos_cadena_motriz import PINON_RODILLO, TOL_VELOCIDAD, pinones_motor

    zr = int(CATALOG[PINON_RODILLO].specs["z"])
    por_que: list[str] = []
    for ref in sinfines():
        pk = float(CATALOG[ref].specs["potencia_kW"])
        if not sirve_red(ref, red_v):
            por_que.append(f"{ref}: es de {'/'.join(f'{u:g}' for u in tensiones(ref))} V y la red "
                           f"es de {red_v:g} V")
            continue
        loc = sinfin_local(ref)
        combos = []
        for pin in pinones_motor():
            s = CATALOG[pin].specs
            if int(s["z"]) < Z_MOTRIZ_MIN or float(s.get("agujero_max_mm") or 0.0) < loc.bore_d \
                    or float(s.get("piloto_mm") or 0.0) > loc.bore_d:  # el piloto se agranda
                continue
            for i in CATALOG[ref].specs.get("relaciones_i") or ():
                v = velocidad(d_rodillo, ref, float(i), int(s["z"]))
                if abs(v - v_obj) <= TOL_VELOCIDAD * v_obj:
                    combos.append((abs(v - v_obj), int(s["z"]), float(i), pin, v))
        if not combos:
            por_que.append(f"{ref}: ningún piñón ≥ Z{Z_MOTRIZ_MIN} que entre en su eje "
                           f"Ø{loc.bore_d:g} da {v_obj:g} m/s ± {TOL_VELOCIDAD:.0%} con su serie de "
                           "relaciones")
            continue
        motivo = None
        for _dv, _z, i, pin, v in sorted(combos):
            req = potencia_de(v)
            if pk < req:
                motivo = f"{ref}: da {pk:g} kW y la carga pide {req:.2f} kW"
                continue
            fs = fs_cadena(pk, v * 60000.0 / (math.pi * d_rodillo))
            if fs is None or fs < FS_CADENA:
                motivo = (f"{ref}: la cadena ASA 40-1 con el piñón Z{zr} del rodillo lleva su par "
                          f"nominal con FS {fs:.2f} < {FS_CADENA:g}" if fs is not None else
                          f"{ref}: rpm del rodillo fuera de la tabla ACA")
                continue
            try:
                armar(ref, pin, i)
            except ValueError as exc:
                motivo = f"{ref} + Z{CATALOG[pin].specs['z']} (i = {i:g}): {exc}"
                continue
            return ref, pin, i
        por_que.append(motivo or f"{ref}: no se arma")
    raise ValueError(
        "motor auto: ningún motorreductor del catálogo sirve (" + "; ".join(por_que) + "). Una "
        "cadena mayor (ASA 40-2 o ASA 50) pide un piñón de rodillo doble-dúplex o ASA 50 "
        "doble-simple que el catálogo no tiene: baja la carga, parte el transportador en tramos "
        "con su motor o sube la velocidad")


def motriz_sinfin(motor: str, pinon: str, i: float, d: dict):
    """La motriz con el sinfín: la misma `Motriz` de `rodillos_cadena_motriz.motriz` (cadena
    motriz inclinada, portamotor con orejas sobre la línea de centros) con la caja girada
    (`ROTACION`) y sus piezas propias en `sinfin`. `ValueError` accionable si no se arma."""
    from .rodillos_cadena_guardas import GUARDA_T, RENDIJA
    from .rodillos_cadena_motriz import (
        ANGULO_MOTRIZ, BASE_MOTOR_T, CADENA, HOLGURA_GIRA, MONTAJE_MM, OREJA_T, PATA,
        PINON_RODILLO, PLACA_PATA_T, Motriz, _oreja, holgura_motriz, tensado_requerido,
    )
    from .transmision import diametro_primitivo, eslabones_pares

    sc, sm = CATALOG[CADENA].specs, CATALOG[pinon].specs
    p, alto = float(sc["paso"]), float(sc["alto_placa"])
    zm, zr = int(sm["z"]), int(CATALOG[PINON_RODILLO].specs["z"])
    loc = sinfin_local(motor)
    if float(sm.get("agujero_max_mm") or 0.0) < loc.bore_d:
        raise ValueError(f"el piñón Z{zm} no entra en el eje Ø{loc.bore_d:g} del {motor}")
    h, x_l, y_h2 = d["h_eje"], d["xs"][-1], d["y_h2"]
    a = math.radians(ANGULO_MOTRIZ)
    bajo = loc.z_tope + d["d_rodillo"] / 2.0 + 10.0  # el motor pasa bajo los tubos
    n, c = eslabones_pares(p, zm, zr, bajo / math.cos(a))
    tensado = tensado_requerido(n, p)
    if holgura_motriz(d["paso"], c, ANGULO_MOTRIZ, pinon) < 5.0 or min(
            holgura_motriz(d["paso"], c + t, ANGULO_MOTRIZ, pinon)
            for t in (-MONTAJE_MM, tensado)) < HOLGURA_GIRA:
        raise ValueError(f"la cadena motriz (Z{zm}) choca con la del penúltimo rodillo")
    x_m, z_m = x_l - c * math.sin(a), h - c * math.cos(a)
    medio = float(sm["ancho_diente"]) / 2.0
    y_cubo = y_h2 + medio - float(sm["largo"])
    yi0 = y_cubo - HOLGURA_GIRA - GUARDA_T     # cara interior de la pared interior del cárter
    fi0 = yi0 - RENDIJA - GUARDA_T              # y la de la pared interior de la guarda fija
    # el cuerpo del motor no entra a la guarda fija; la brida queda antes del cárter
    y_m = min(fi0 - HOLGURA_MOTOR - loc.motor_r, yi0 - 14.0 - loc.cara_salida)
    atras = min(y_m - loc.tapa, y_m - loc.motor_r)
    if atras < d["y_in_m"] + 15.0:
        raise ValueError(f"el {motor} no cabe entre las patas: ancho_util mínimo "
                         f"{math.ceil(d['ancho_util'] + d['y_in_m'] + 15.0 - atras):g} mm")
    r_env = max(diametro_primitivo(p, zm) / 2.0 + alto / 2.0, float(sm["de"]) / 2.0)
    # cara superior de la base, bajo el calzo (más alto si el piñón baja más que la caja)
    calzo = max(CALZO_T, r_env + HOLGURA_GIRA + 1.0 - loc.hw / 2.0)
    z_b = z_m - loc.hw / 2.0 - calzo
    if z_m - r_env - HOLGURA_GIRA < z_b or loc.motor_z - loc.motor_r < z_b - z_m + 3.0 \
            or loc.pernos_brida_z < z_b - z_m:
        raise ValueError(f"el piñón Z{zm} o el {motor} tocan la base: usa otro piñón")
    w = float(CATALOG[PATA].specs["width"])
    roscas = perno_caja(motor)
    s_llave = {"M6": 10.0, "M8": 13.0, "M10": 16.0}[roscas]
    lo = x_m + loc.bornes_x1 + 3.0 + w / 2.0             # el travesaño, tras la caja de bornes
    hi = x_m - (loc.hw / 2.0 - BORDE_ROSCA) - s_llave - w / 2.0 - 2.0  # y antes de la llave
    if lo > hi:
        raise ValueError(f"el travesaño portamotor no cabe entre la caja de bornes y los tornillos "
                         f"del {motor}")
    x_pm = (lo + hi) / 2.0
    z_t = z_b - BASE_MOTOR_T - w / 2.0
    oreja = _oreja(tensado, a)
    ot = d.get("oreja_t", OREJA_T)
    oreja["t"] = ot
    if z_t - oreja["medio_alto"] - tensado < d.get("z_pata0", PLACA_PATA_T) + 20.0:
        raise ValueError("altura insuficiente para el motorreductor bajo los rodillos: sube la "
                         "altura de trabajo")
    cx, cy = loc.hw / 2.0 - BORDE_ROSCA, loc.hy / 2.0 - BORDE_ROSCA
    sinfin = {
        "calzo": {"x0": x_m - loc.hw / 2.0, "x1": x_m + loc.hw / 2.0, "y0": y_m - loc.hy / 2.0,
                  "y1": y_m + loc.hy / 2.0, "z0": z_b, "z1": z_b + calzo},
        "roscas": roscas, "pernos": [(x_m + sx * cx, y_m + sy * cy) for sx in (-1, 1)
                                     for sy in (-1, 1)],
        # eje de salida: Ø del hueco (con su holgura) dentro de la caja, Ø nominal afuera
        "eje": {"y0": y_m - loc.hy / 2.0 + 5.0, "y_hombro": y_m + loc.cara_salida,
                "y1": y_h2 + medio + 5.0, "r_caja": loc.bore_d / 2.0 + 1.5,
                "r": loc.bore_d / 2.0},
        # collar del cárter: tapa el eje entre el cubo de la brida y el cárter
        "collar": {"y0": y_m + loc.cara_salida + 2.0, "y1": yi0,
                   "ri": loc.bore_d / 2.0 + HOLGURA_GIRA, "re": loc.bore_d / 2.0 + 5.0},
        "base_x": (x_pm - w / 2.0, x_m + loc.hw / 2.0 + 2.0),
    }
    y_base0 = y_m - loc.hy / 2.0 - 2.0
    sp = CATALOG[motor].specs
    return Motriz(
        motor=motor, pinon=pinon, z_pinon=zm, potencia_kw=float(sp["potencia_kW"]),
        rpm=rpm_motor(motor) / i, x=x_m, y=y_m, z=z_m, angulo_deg=ANGULO_MOTRIZ, eslabones=n,
        centros=c, tensado_mm=tensado, montaje_mm=MONTAJE_MM, eje_d=loc.bore_d, y_pinon=y_h2,
        y_cubo=y_cubo, r_envolvente=r_env, z_base=z_b, y_base0=y_base0,
        pies=((x_m, x_m), (x_m, x_m)), pies_z=z_b, pies_y1=y_base0,
        portamotor={"x": x_pm, "y": (d["y_in_m"] + d["y_in_p"]) / 2.0, "z": z_t,
                    "largo": d["y_in_p"] - d["y_in_m"] - 2.0 * ot},
        oreja=oreja, tipo="sinfin", relacion=float(i), sinfin=sinfin,
    )
