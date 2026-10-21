"""Disposición PURA del transportador de rodillos motorizado por cadena (super-comando
`create_roller_conveyor`, plan `docs/plans/plantilla-rodillos-cadena.md`, D1 y F4).

Sin `Document` ni OCCT: de los params del comando y del catálogo deriva TODAS las cotas de la
máquina (las que la piloto, proyecto 74, dejó a mano: § Bitácora F0, «Receta para la F2») y
valida lo que no se puede fabricar con un error que dice qué cambiar. La receta de comandos
que arma la máquina con estos números vive en `commands/receta_rodillos_cadena.py`; la motriz
(motor, piñón por velocidad, portamotor con orejas) en `rodillos_cadena_motriz.py` y las
guardas de la transmisión y la bandeja en `rodillos_cadena_guardas.py`.

MARCO (local, antes de `position`): X a lo largo del transporte (x = 0 en la alimentación,
x = largo en la motriz), Y = 0 en el centro del tubo de rodillo con la transmisión hacia +Y,
Z = 0 el piso.

Lecciones de la piloto y del revisor de taller que quedan dentro (defectos.md):
- larguero de ÁNGULO con el ala horizontal ABAJO y hacia AFUERA: la tuerca del eje queda en la
  cara exterior del ala vertical, lejos del ala horizontal, y entra la llave;
- patas en H: UN travesaño ENTRE las patas de cada estación, a la MISMA altura en todas (la del
  portamotor; a media pata si no hay motor), soldado a sus caras interiores (D8);
- una sola familia de piñones dobles-simples: la cadena `fase: "auto"` gira los alternos;
- la cadena motriz se TENSA sobre su línea de centros (D7) y sus centros son los exactos de un
  número par de eslabones (`eslabones_pares`), nunca una cota a mano;
- la transmisión va cerrada por todos los lados accesibles (D4, D5; ISO 14120).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .acuerdos import zona_plana_ala_angulo
from .catalog import CATALOG
from .engineering.secciones import angulo_libre
from .rodillos_cadena_guardas import GUARDA_T, bandeja, guarda_transmision
from .rodillos_cadena_motriz import (
    ANGULO_MOTRIZ, BASE_MOTOR_T, CADENA, MOTORES, PATA, PINON_MOTRIZ, PINON_RODILLO,
    PLACA_PATA_T, Motriz, elegir_pinon, holgura_motriz, motor_local, motriz as _motriz,
    velocidad_producto,
)
from .transmision import diametro_primitivo

__all__ = [
    "ANGULO_MOTRIZ", "BASE_MOTOR_T", "CADENA", "GUARDA_T", "MOTORES", "PATA", "PINON_MOTRIZ",
    "PINON_RODILLO", "PLACA_PATA_T", "Disposicion", "Estacion", "Motriz", "disposicion",
    "holgura_motriz", "motor_local", "pasos_rodillo", "potencia_requerida", "vano_maximo",
]

LARGUERO = "ANG-75X6"
TUERCA = "TUERCA-M12"
RODILLOS = ("TUBOR-2", "TUBOR-2.5", "TUBOR-3")
#: Eslabones de un lazo rodillo a rodillo (1:1): el paso de rodillos sale de ahí, no es libre.
ESLABONES_RR = (30, 32, 34)

EJE_D = 12.0               # varilla roscada M12 = Ø interior del 6201
RODAMIENTO = "6201"
TAPA_ESPESOR = 15.0
HOLGURA_BASTIDOR = 10.0    # extremo del tubo ↔ cara interior del ala vertical (lado sin cadena)
SOBRE_TUERCA = 4.0         # rosca que asoma de la tuerca (> 2 hilos de M12)
TOPE_SOBRE_EJE = 20.0      # canto superior del larguero sobre el eje (borde del barreno ≥ 1.5·d)
BARRENO_EJE = 13.0         # paso del eje M12 por el ala vertical
BRIDA_BUJE = 3.0           # brida del buje, soldada al extremo del tubo
CUELLO_BUJE_R = 20.0       # cuello del buje: ahí se suelda el cubo del piñón
HOLGURA_HILERA2 = 1.5      # perno de la cadena de la hilera 2 ↔ brida del buje
HOLGURA_CADENA_LARGUERO = 10.0
PLACA_PATA = 150.0
ANCLAJE_D = 14.0           # perno de expansión M12 al piso
MARGEN_EXTREMO = 50.0      # eje del primer/último rodillo ↔ extremo del larguero (mínimo)
LARGO_MIN = 1000.0
GUARDA_PESTANA = 14.0
SEPARADOR_X = 40.0
SEPARADOR_FONDO = 50.0
VANO_TOPE = 1800.0         # luz máxima entre estaciones de patas (práctica de transportador liviano)
G = 9.81
E_ACERO = 210000.0
MU_RODADURA = 0.05         # cartón y bultos de fondo plano sobre rodillos de acero
ETA_LAZO = 0.98            # rendimiento de cada lazo de cadena
ETA_REDUCTOR = 0.85
FACTOR_ARRANQUE = 1.5


def pasos_rodillo() -> list[float]:
    """Pasos de rodillos que cierran un lazo 1:1 sin sobrante: t = (L − z)·p/2 con L par
    (`ESLABONES_RR`). Z15 de 1/2″ → 95.25, 107.95, 120.65."""
    s = CATALOG[PINON_RODILLO].specs
    return [round((n - int(s["z"])) * float(s["paso"]) / 2.0, 2) for n in ESLABONES_RR]


@dataclass(frozen=True)
class Estacion:
    """Estación de patas en H: dos patas bajo los largueros y UN travesaño entre ellas."""

    x: float
    rol: str               # "alimentacion" | "intermedia" | "motriz"
    z_travesano: float     # centro del travesaño


@dataclass(frozen=True)
class Disposicion:
    largo: float
    ancho_util: float
    paso: float
    rodillo: str
    d_rodillo: float
    r_int_tubo: float
    altura: float
    h_eje: float
    carga_kg: float
    xs: tuple              # ejes de los rodillos
    eslabones_rr: int
    y_in_m: float          # caras interiores de las alas verticales
    y_in_p: float
    y_pinon: float         # plano de la hilera 1 de los piñones (su origen)
    y_buje: float          # el buje va de ancho_util/2 a y_buje
    eje_y0: float
    eje_y1: float
    y_tuerca_m: float
    y_tuerca_p: float
    z_larguero: float      # centro del larguero (su bbox)
    pata_largo: float
    estaciones: tuple
    travesano_largo: float
    separadores: tuple     # x de cada separador de guarda (entre rodillos)
    sep_z0: float
    guarda_z: float        # cara SUPERIOR de la guarda de cadenas
    vano_max: float
    velocidad_m_s: float | None   # la del PRODUCTO (superficie del tubo)
    potencia_req_kw: float | None
    motriz: Motriz | None
    r_cadena: float        # envolvente de las cadenas 1:1 alrededor del eje de un rodillo
    guardas: dict | None   # cárter móvil + guarda fija (D4)
    bandeja: dict | None   # bandeja inferior de cadenas (D5)


def _masa_rodillo(ref: str, ancho_util: float, largo_eje: float, con_pinon: bool) -> float:
    s = CATALOG[ref].specs
    od, w = float(s["od"]), float(s["wall"])
    tubo = math.pi / 4.0 * (od**2 - (od - 2 * w) ** 2) * ancho_util * 7.85e-6
    eje = math.pi / 4.0 * EJE_D**2 * largo_eje * 7.85e-6
    return tubo + eje + (CATALOG[PINON_RODILLO].weight if con_pinon else 0.0)


def vano_maximo(carga_kg: float, masa_rodillos_kg: float, largo: float) -> float:
    """Luz entre estaciones de patas para el larguero de ÁNGULO libre (ejes principales,
    `secciones.angulo_libre`) con la carga repartida entre los dos largueros: flecha ≤ L/240
    y σ ≤ 0.6·fy (criterio de `viga_bastidor`), con tope `VANO_TOPE`."""
    s = CATALOG[LARGUERO].specs
    sec = angulo_libre(float(s["leg"]), float(s["t"]))
    q = (carga_kg + masa_rodillos_kg) * G / 2.0 / largo + CATALOG[LARGUERO].weight * G / 1000.0
    fy = 275.0  # S275JR
    flecha = (384.0 * E_ACERO * sec.i_eq_mm4 / (5.0 * 240.0 * q)) ** (1.0 / 3.0)
    tension = math.sqrt(8.0 * 0.6 * fy * sec.w_eq_mm3 / q)
    return min(VANO_TOPE, flecha, tension)


def potencia_requerida(carga_kg: float, masa_rodillos_kg: float, velocidad_m_s: float,
                       n_rodillos: int) -> float:
    """kW: rodadura `MU_RODADURA` con arranque ×`FACTOR_ARRANQUE`; la carga repartida llega
    al rodillo k a través de k lazos (la motriz es el 1.º) y el reductor rinde `ETA_REDUCTOR`."""
    n = n_rodillos
    eta = n / sum(ETA_LAZO ** -k for k in range(1, n + 1)) * ETA_REDUCTOR
    return FACTOR_ARRANQUE * MU_RODADURA * (carga_kg + masa_rodillos_kg) * G * velocidad_m_s / eta / 1000.0


def _rodillos(largo: float, paso: float) -> tuple:
    n = int((largo - 2.0 * MARGEN_EXTREMO) // paso) + 1
    n -= n % 2  # par: la última cadena 1:1 cae en la hilera 1 y la 2 queda para la motriz
    if n < 4:
        raise ValueError(f"largo {largo:g} mm no alcanza para 4 rodillos a paso {paso:g}")
    x0 = (largo - (n - 1) * paso) / 2.0
    return tuple(round(x0 + i * paso, 6) for i in range(n))


def _estaciones(largo: float, xs: tuple, mot: Motriz | None, vano: float, z_trav: float) -> tuple:
    """Voladizo igual en los dos extremos; la motriz bajo el motor. Travesaño a `z_trav` en
    TODAS (D8)."""
    voladizo = (largo - mot.x) if mot is not None else xs[0] + 50.0
    x_f, x_d = voladizo, largo - voladizo
    n_vanos = max(1, math.ceil((x_d - x_f) / vano - 1e-9))
    out = []
    for k in range(n_vanos + 1):
        x = x_f + (x_d - x_f) * k / n_vanos
        rol = "alimentacion" if k == 0 else ("motriz" if k == n_vanos else "intermedia")
        out.append(Estacion(round(x, 6), rol, z_trav))
    return tuple(out)


def disposicion(largo: float, ancho_util: float, paso: float, rodillo: str, altura: float,
                carga_kg: float, motriz: bool, motor: str | None,
                velocidad_m_s: float | None = None) -> Disposicion:
    """Todas las cotas del transportador; `ValueError` accionable si no se puede fabricar.
    `velocidad_m_s` (D6) elige el piñón del motor; sin ella, el de siempre (`PINON_MOTRIZ`)."""
    if rodillo not in RODILLOS:
        raise ValueError(f"rodillo '{rodillo}': usa uno de {', '.join(RODILLOS)}")
    if motriz and motor not in MOTORES:
        raise ValueError(f"motor '{motor}': usa uno de {', '.join(MOTORES)}")
    pasos = pasos_rodillo()
    casa = [t for t in pasos if abs(t - paso) < 0.01]
    if not casa:
        raise ValueError(f"paso {paso:g}: con la cadena 1:1 sólo cierran {pasos} mm")
    paso = casa[0]
    if largo < LARGO_MIN:
        raise ValueError(f"largo mínimo {LARGO_MIN:g} mm")
    st = CATALOG[rodillo].specs
    d_rod, pared = float(st["od"]), float(st["wall"])
    if paso - d_rod < 20.0:
        raise ValueError(f"paso {paso:g} deja {paso - d_rod:.1f} mm entre tubos Ø{d_rod:g}: usa un "
                         "paso mayor o un tubo menor (mínimo 20 mm)")
    if not 150.0 <= ancho_util <= 1500.0:
        raise ValueError("ancho_util entre 150 y 1500 mm")
    sr, sc = CATALOG[PINON_RODILLO].specs, CATALOG[CADENA].specs
    perno = float(sc["ancho_sobre_perno"])
    a2 = ancho_util / 2.0
    h = altura - d_rod / 2.0
    xs = _rodillos(largo, paso)
    t = float(CATALOG[LARGUERO].specs["t"])
    ala = float(CATALOG[LARGUERO].specs["leg"])
    tuerca_t = float(CATALOG[TUERCA].specs["thickness"])
    y_in_m = -a2 - HOLGURA_BASTIDOR
    if motriz:
        dh = float(sr["distancia_hileras"])
        y_pin = a2 + BRIDA_BUJE + HOLGURA_HILERA2 + dh + perno / 2.0
        # la cara del piñón hacia el tubo: el fondo del cubo o la placa de la hilera 2
        fondo = max(float(sr["largo"]) - float(sr["ancho_diente"]) / 2.0,
                    dh + float(sr["ancho_diente"]) / 2.0)
        y_buje = y_pin - fondo - 0.1
        y_in_p = y_pin + perno / 2.0 + HOLGURA_CADENA_LARGUERO
        y_h2 = y_pin - dh
    else:
        y_pin = y_buje = y_h2 = a2
        y_in_p = a2 + HOLGURA_BASTIDOR
    eje_y0 = y_in_m - t - tuerca_t - SOBRE_TUERCA
    eje_y1 = y_in_p + t + tuerca_t + SOBRE_TUERCA
    z_bajo_larguero = h + TOPE_SOBRE_EJE - ala
    pata = z_bajo_larguero - PLACA_PATA_T
    if pata < 250.0:
        raise ValueError("altura de trabajo demasiado baja para patas con travesaño (mínimo "
                         f"{math.ceil(altura - pata + 250.0):g} mm)")
    m_rod = len(xs) * _masa_rodillo(rodillo, ancho_util, eje_y1 - eje_y0, motriz)
    d = {"h_eje": h, "xs": xs, "y_h2": y_h2, "d_rodillo": d_rod, "paso": paso,
         "y_in_m": y_in_m, "y_in_p": y_in_p, "ancho_util": ancho_util}
    # guarda de cadenas: sobre los separadores, por encima de las cadenas y de los tubos
    r_cad = diametro_primitivo(float(sc["paso"]), int(sr["z"])) / 2.0 + float(sc["alto_placa"]) / 2.0
    guarda_base = max(h + r_cad + 3.0, h + d_rod / 2.0 + 3.0 + GUARDA_PESTANA + GUARDA_T)
    g = {"h_eje": h, "d_rodillo": d_rod, "r_cadena": r_cad, "x_ultimo": xs[-1], "largo": largo,
         "a2": a2, "y_in_p": y_in_p, "z_bandeja": h - r_cad - 5.0 - GUARDA_T,
         # pestaña interior de la guarda de cadenas: su cara exterior y su borde libre
         "y_pestana": a2 - 3.0 + GUARDA_T, "z_pestana": guarda_base - GUARDA_PESTANA,
         "z_guarda": guarda_base,  # cara inferior de la chapa de la guarda de cadenas
         # el ala vertical del larguero es plana desde aquí (talón + t + r1)
         "z_alma_plana": z_bajo_larguero + zona_plana_ala_angulo(CATALOG[LARGUERO].specs)[0]}

    def armar(motor_ref: str, pinon: str) -> tuple:
        m = _motriz(motor_ref, pinon, d)
        return m, guarda_transmision(m, g)

    mot = guardas = band = None
    if motriz:
        mot, guardas = armar(motor, elegir_pinon(motor, velocidad_m_s, d_rod, armar))
        band = bandeja(g, guardas["fija"]["x_izq"] - 1.0, guardas["fija"]["pared_int"]["y0"])
    vano = vano_maximo(carga_kg, m_rod, largo)
    z_trav = mot.portamotor["z"] if mot is not None else PLACA_PATA_T + pata / 2.0
    estaciones = _estaciones(largo, xs, mot, vano, z_trav)
    velocidad = potencia = None
    if mot is not None:
        velocidad = velocidad_producto(d_rod, mot.rpm, mot.z_pinon)
        potencia = potencia_requerida(carga_kg, m_rod, velocidad, len(xs))
        if potencia > mot.potencia_kw:
            raise ValueError(f"{mot.motor} da {mot.potencia_kw:g} kW y la carga pide "
                             f"{potencia:.2f} kW: elige un motorreductor mayor")
    sep_z0 = h + TOPE_SOBRE_EJE
    n = len(xs)
    cuantos = math.ceil((n - 4) / 8.0) + 1  # cada ≤ 8 pasos, siempre ENTRE dos rodillos
    seps = tuple(round(xs[0] + paso * (1.5 + round((n - 4) * k / max(1, cuantos - 1))), 6)
                 for k in range(cuantos)) if motriz else ()
    return Disposicion(
        largo=largo, ancho_util=ancho_util, paso=paso, rodillo=rodillo, d_rodillo=d_rod,
        r_int_tubo=d_rod / 2.0 - pared, altura=altura, h_eje=h, carga_kg=carga_kg, xs=xs,
        eslabones_rr=round(int(sr["z"]) + 2.0 * paso / float(sc["paso"])),
        y_in_m=y_in_m, y_in_p=y_in_p, y_pinon=y_pin, y_buje=y_buje, eje_y0=eje_y0, eje_y1=eje_y1,
        y_tuerca_m=y_in_m - t - tuerca_t / 2.0, y_tuerca_p=y_in_p + t + tuerca_t / 2.0,
        z_larguero=h + TOPE_SOBRE_EJE - ala / 2.0, pata_largo=pata, estaciones=estaciones,
        travesano_largo=y_in_p - y_in_m, separadores=seps, sep_z0=sep_z0,
        guarda_z=guarda_base + GUARDA_T, vano_max=vano, velocidad_m_s=velocidad,
        potencia_req_kw=potencia, motriz=mot, r_cadena=r_cad, guardas=guardas, bandeja=band,
    )
