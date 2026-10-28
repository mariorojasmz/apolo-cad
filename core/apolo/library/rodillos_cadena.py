"""Disposición PURA del transportador de rodillos motorizado por cadena (super-comando
`create_roller_conveyor`, plan `docs/plans/plantilla-rodillos-cadena.md`, D1 y F4).

Sin `Document` ni OCCT: de los params del comando y del catálogo deriva TODAS las cotas de la
máquina (las que la piloto, proyecto 74, dejó a mano: § Bitácora F0, «Receta para la F2») y
valida lo que no se puede fabricar con un error que dice qué cambiar. La receta de comandos
que arma la máquina con estos números vive en `commands/receta_rodillos_cadena.py`; la motriz
(motor, piñón por velocidad, portamotor con orejas) en `rodillos_cadena_motriz.py`, las
guardas de la transmisión y la bandeja en `rodillos_cadena_guardas.py` y los pies niveladores
en `rodillos_cadena_pies.py`.

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
- la transmisión va cerrada por todos los lados accesibles (D4, D5; ISO 14120);
- cada pata apoya en un pie nivelador de catálogo (D10): un bastidor soldado de 4 o más apoyos
  no se nivela sobre placas lisas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .acuerdos import zona_plana_ala_angulo
from .catalog import CATALOG
from .engineering.secciones import angulo_libre
from .rodillos_cadena_guardas import GUARDA_T, bandeja, guarda_transmision
from .rodillos_cadena_motriz import (
    ANGULO_MOTRIZ, BASE_MOTOR_T, CADENA, MOTORES, PATA, PINON_MOTRIZ, PINON_RODILLO,
    PLACA_PATA_T, Motriz, elegir_pinon, holgura_motriz, motor_local, motriz as _motriz,
    velocidad_producto,
)
from .rodillos_cadena_pies import Pies, pila
from .rodillos_cadena_pies import elegir as elegir_pies
from .rodillos_cadena_pies import familias as pies_familias
from .transmision import diametro_primitivo

__all__ = [
    "ANGULO_MOTRIZ", "BASE_MOTOR_T", "CADENA", "GUARDA_T", "MOTORES", "PATA", "PINON_MOTRIZ",
    "PINON_RODILLO", "PLACA_PATA_T", "Disposicion", "Estacion", "Motriz", "Pies", "disposicion",
    "holgura_motriz", "motor_local", "pasos_rodillo", "potencia_requerida", "rango_paso_libre",
    "rodamiento_de", "validar_paso", "vano_maximo",
]

LARGUERO = "ANG-75X6"
TUERCA = "TUERCA-M12"
RODILLOS = ("TUBOR-2", "TUBOR-2.5", "TUBOR-3")
#: Eslabones de un lazo rodillo a rodillo (1:1): con cadena el paso de rodillos sale de ahí.
ESLABONES_RR = (30, 32, 34)
#: Luz mínima entre tubos vecinos (paso − Ø): la que la disposición ya exigía con cadena. Con
#: rodillos libres no hay atrapamiento (nada los acciona: «peligro = lo accionado»); es holgura
#: de taller: la ovalidad y la flecha del tubo bajo carga no los hacen rozar.
HOLGURA_TUBOS = 20.0
#: Paso máximo con rodillos libres: en el largo mínimo (`LARGO_MIN`) caben los 4 rodillos que
#: pide `_rodillos` ((1000 − 2·50)/3); más allá un bulto necesita ≥ 900 mm para apoyar en 3.
PASO_LIBRE_MAX = 300.0

EJE_D = 12.0               # varilla roscada M12 = Ø interior del 6201
RODAMIENTO = "6201"
TAPA_ESPESOR = 15.0
HOLGURA_BASTIDOR = 10.0    # extremo del tubo ↔ cara interior del ala vertical (lado sin cadena)
# F6 (`taller`): el eje se TRABA contra el ala entre una tuerca interior y la exterior, y un
# separador (tubo Ø16 × 2 sobre el eje) entre la tuerca interior y el aro INTERIOR del 6201 acota
# el juego axial del rodillo. Lo que gira (tapa, buje, piñón) no toca nada que no gire.
HOLGURA_BASTIDOR_TALLER = 16.0  # tuerca interior (10) + separador (5.5) + juego (0.5)
JUEGO_AXIAL = 0.5          # separador ↔ aro interior del 6201, por lado (≤ 2 mm: criterio de taller)
SEPARADOR_EJE_D = 16.0     # Ø exterior del separador: < hombro del aro interior del 6201 (Ø≈17)
HUECO_GIRA_R = 10.0        # agujero de buje y piñón: libra el separador (2 mm) y el aro interior
# F7 (`eje: "hexagonal"`, también sellado): barra hexagonal calzada en ranuras abiertas hacia
# arriba del ala vertical, sobre 6202 de agujero hexagonal; cotas en `rodillos_cadena_eje.py`.
EJES = ("roscado", "hexagonal")
# F8 (`pie: "base"`, también sellado): con `anclaje`, pie nivelador con base de anclaje anclado
# directo al concreto, sin placa de piso ni soldadura (`rodillos_cadena_pies.py`).
PIES = ("disco", "base")
ALOJ_HOMBRO_R = 13.0       # hombro de la tapa: sólo el aro EXTERIOR (Da máx del 6201 ≈ 28.4)
SOBRE_TUERCA = 4.0         # rosca que asoma de la tuerca (> 2 hilos de M12)
TOPE_SOBRE_EJE = 20.0      # canto superior del larguero sobre el eje (borde del barreno ≥ 1.5·d)
BARRENO_EJE = 13.0         # paso del eje M12 por el ala vertical
BRIDA_BUJE = 3.0           # brida del buje, soldada al extremo del tubo
CUELLO_BUJE_R = 20.0       # cuello del buje: ahí se suelda el cubo del piñón
HOLGURA_HILERA2 = 1.5      # perno de la cadena de la hilera 2 ↔ brida del buje
HOLGURA_CADENA_LARGUERO = 10.0
PLACA_PATA = 150.0
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


def rango_paso_libre(rodillo: str) -> tuple[float, float]:
    """(mínimo, máximo) del paso con `motriz: libre`: Ø del tubo + `HOLGURA_TUBOS` …
    `PASO_LIBRE_MAX`."""
    return float(CATALOG[rodillo].specs["od"]) + HOLGURA_TUBOS, PASO_LIBRE_MAX


def validar_paso(paso: float, rodillo: str, motriz: bool) -> float:
    """El paso que vale (con cadena, el de la lista exacta) o `ValueError` con lo que vale.
    Con cadena, sólo `pasos_rodillo()`; libre, el rango de `rango_paso_libre`."""
    if motriz:
        pasos = pasos_rodillo()
        for t in pasos:
            if abs(t - paso) < 0.01:
                return t
        raise ValueError(f"paso {paso:g}: con la cadena 1:1 sólo cierran {pasos} mm")
    lo, hi = rango_paso_libre(rodillo)
    if not lo - 1e-9 <= paso <= hi + 1e-9:
        raise ValueError(f"paso {paso:g}: con rodillos libres y tubo {rodillo} va de {lo:g} a "
                         f"{hi:g} mm (Ø{lo - HOLGURA_TUBOS:g} + {HOLGURA_TUBOS:g} mm entre tubos; "
                         f"≤ {hi:g} para 4 rodillos en el largo mínimo)")
    return paso


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
    pies: Pies | None = None  # pie nivelador de cada pata y su pila (D10, `rodillos_cadena_pies`)
    taller: bool = False   # F6: eje trabado, 6201 de compra, contratuerca y anclajes accesibles
    eje_hex: bool = False  # F7: eje hexagonal calzado en ranuras (`rodillos_cadena_eje`)


def rodamiento_de(d) -> str:
    """El rodamiento de cada tapa: el 6201 (eje M12) o, con el eje hexagonal (F7), el 6202 de
    agujero hexagonal."""
    from .rodillos_cadena_eje import RODAMIENTO_HEX

    return RODAMIENTO_HEX if getattr(d, "eje_hex", False) else RODAMIENTO


def _masa_rodillo(ref: str, ancho_util: float, largo_eje: float, con_pinon: bool) -> float:
    s = CATALOG[ref].specs
    od, w = float(s["od"]), float(s["wall"])
    tubo = math.pi / 4.0 * (od**2 - (od - 2 * w) ** 2) * ancho_util * 7.85e-6
    eje = math.pi / 4.0 * EJE_D**2 * largo_eje * 7.85e-6
    return tubo + eje + (CATALOG[PINON_RODILLO].weight if con_pinon else 0.0)


def vano_maximo(carga_kg: float, masa_rodillos_kg: float, largo: float, k_w: float = 1.0,
                k_i: float = 1.0) -> float:
    """Luz entre estaciones de patas para el larguero de ÁNGULO libre (ejes principales,
    `secciones.angulo_libre`) con la carga repartida entre los dos largueros: flecha ≤ L/240
    y σ ≤ 0.6·fy (criterio de `viga_bastidor`), con tope `VANO_TOPE`. `k_w`/`k_i` (F7): lo que
    las ranuras del eje le quitan a W y a la rigidez (`rodillos_cadena_eje.factores_ranura`)."""
    s = CATALOG[LARGUERO].specs
    sec = angulo_libre(float(s["leg"]), float(s["t"]))
    q = (carga_kg + masa_rodillos_kg) * G / 2.0 / largo + CATALOG[LARGUERO].weight * G / 1000.0
    fy = 275.0  # S275JR
    flecha = (384.0 * E_ACERO * sec.i_eq_mm4 * k_i / (5.0 * 240.0 * q)) ** (1.0 / 3.0)
    tension = math.sqrt(8.0 * 0.6 * fy * sec.w_eq_mm3 * k_w / q)
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
                velocidad_m_s: float | None = None, anclaje: bool = True,
                taller: bool = False, eje: str = "roscado", pie: str = "disco") -> Disposicion:
    """Todas las cotas del transportador; `ValueError` accionable si no se puede fabricar.
    `velocidad_m_s` (D6) elige el piñón del motor; sin ella, el de siempre (`PINON_MOTRIZ`).
    El pie nivelador de las patas (D10) sale de la carga por pata; `anclaje` pone una placa de
    piso con 2 anclajes bajo cada disco. Las cotas se arman con la pila del pie MAYOR (la más
    alta: valida del lado seguro) y, ya elegido el pie, se alargan las patas. `taller` (F6, el
    sello de todo comando nuevo) abre el lado sin cadena a `HOLGURA_BASTIDOR_TALLER` para la
    tuerca interior y el separador del eje, y arma la pila del pie con su contratuerca. `eje`
    «hexagonal» (F7, sellado también; pide `taller`): el eje se calza en ranuras del ala, asoma
    `rodillos_cadena_eje.SOBRE` por fuera y las ranuras recortan el vano del larguero. `pie`
    «base» (F8, sellado también; pide `taller`): con `anclaje`, el pie de base de anclaje va
    anclado directo al piso, sin placa de piso ni soldadura."""
    from . import rodillos_cadena_eje as hx

    if eje not in EJES:
        raise ValueError(f"eje '{eje}': usa uno de {', '.join(EJES)}")
    if pie not in PIES:
        raise ValueError(f"pie '{pie}': usa uno de {', '.join(PIES)}")
    eje_hex = eje == "hexagonal"
    if eje_hex and not taller:
        raise ValueError("el eje hexagonal va con la plantilla de taller (taller: true)")
    base = pie == "base"
    if base and not taller:
        raise ValueError("el pie con base de anclaje va con la plantilla de taller (taller: true)")
    if rodillo not in RODILLOS:
        raise ValueError(f"rodillo '{rodillo}': usa uno de {', '.join(RODILLOS)}")
    if motriz and motor not in MOTORES:
        raise ValueError(f"motor '{motor}': usa uno de {', '.join(MOTORES)}")
    paso = validar_paso(paso, rodillo, motriz)
    if largo < LARGO_MIN:
        raise ValueError(f"largo mínimo {LARGO_MIN:g} mm")
    st = CATALOG[rodillo].specs
    d_rod, pared = float(st["od"]), float(st["wall"])
    if paso - d_rod < HOLGURA_TUBOS:  # con cadena: un paso de la lista con un tubo grande
        raise ValueError(f"paso {paso:g} deja {paso - d_rod:.1f} mm entre tubos Ø{d_rod:g}: usa un "
                         f"paso mayor o un tubo menor (mínimo {HOLGURA_TUBOS:g} mm)")
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
    holgura = HOLGURA_BASTIDOR_TALLER if taller else HOLGURA_BASTIDOR
    y_in_m = -a2 - holgura
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
        y_in_p = a2 + holgura
    sobre = hx.SOBRE if eje_hex else tuerca_t + SOBRE_TUERCA
    eje_y0, eje_y1 = y_in_m - t - sobre, y_in_p + t + sobre
    z_bajo_larguero = h + TOPE_SOBRE_EJE - ala
    z_pata0 = pila(pies_familias(base and anclaje)[-1], anclaje, taller, base).z_pata0
    pata = z_bajo_larguero - z_pata0
    if pata < 250.0:
        raise ValueError("altura de trabajo demasiado baja para patas con travesaño y pie "
                         f"nivelador (mínimo {math.ceil(altura - pata + 250.0):g} mm)")
    m_rod = len(xs) * _masa_rodillo(rodillo, ancho_util, eje_y1 - eje_y0, motriz)
    d = {"h_eje": h, "xs": xs, "y_h2": y_h2, "d_rodillo": d_rod, "paso": paso,
         "y_in_m": y_in_m, "y_in_p": y_in_p, "ancho_util": ancho_util, "z_pata0": z_pata0}
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
    k_w = k_i = 1.0
    if eje_hex:  # la ranura baja del canto del larguero hasta el fondo de su arco
        k_w, k_i = hx.factores_ranura(ala, t, TOPE_SOBRE_EJE + hx.asiento() + hx.RANURA / 2.0, paso)
    vano = vano_maximo(carga_kg, m_rod, largo, k_w, k_i)
    z_trav = mot.portamotor["z"] if mot is not None else z_pata0 + pata / 2.0
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
    prov = Disposicion(
        largo=largo, ancho_util=ancho_util, paso=paso, rodillo=rodillo, d_rodillo=d_rod,
        r_int_tubo=d_rod / 2.0 - pared, altura=altura, h_eje=h, carga_kg=carga_kg, xs=xs,
        # libre: sin lazos (con un paso libre la cuenta de eslabones no sería entera)
        eslabones_rr=round(int(sr["z"]) + 2.0 * paso / float(sc["paso"])) if motriz else 0,
        y_in_m=y_in_m, y_in_p=y_in_p, y_pinon=y_pin, y_buje=y_buje, eje_y0=eje_y0, eje_y1=eje_y1,
        y_tuerca_m=y_in_m - t - tuerca_t / 2.0, y_tuerca_p=y_in_p + t + tuerca_t / 2.0,
        z_larguero=h + TOPE_SOBRE_EJE - ala / 2.0, pata_largo=pata, estaciones=estaciones,
        travesano_largo=y_in_p - y_in_m, separadores=seps, sep_z0=sep_z0,
        guarda_z=guarda_base + GUARDA_T, vano_max=vano, velocidad_m_s=velocidad,
        potencia_req_kw=potencia, motriz=mot, r_cadena=r_cad, guardas=guardas, bandeja=band,
        taller=taller, eje_hex=eje_hex,
    )
    # D10: el pie sale de la carga por pata; la pata crece lo que la pila baja
    pies = elegir_pies(prov, anclaje, taller, base)
    pata = z_bajo_larguero - pies.z_pata0
    if mot is None:
        estaciones = _estaciones(largo, xs, None, vano, pies.z_pata0 + pata / 2.0)
    return replace(prov, pata_largo=pata, estaciones=estaciones, pies=pies)
