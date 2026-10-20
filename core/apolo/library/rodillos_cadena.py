"""Disposición PURA del transportador de rodillos motorizado por cadena (super-comando
`create_roller_conveyor`, plan `docs/plans/plantilla-rodillos-cadena.md`, D1).

Sin `Document` ni OCCT: de los params del comando y del catálogo deriva TODAS las cotas de la
máquina (las que la piloto, proyecto 74, dejó a mano: § Bitácora F0, «Receta para la F2») y
valida lo que no se puede fabricar con un error que dice qué cambiar. La receta de comandos
que arma la máquina con estos números vive en `commands/receta_rodillos_cadena.py`.

MARCO (local, antes de `position`): X a lo largo del transporte (x = 0 en la alimentación,
x = largo en la motriz), Y = 0 en el centro del tubo de rodillo con la transmisión hacia +Y,
Z = 0 el piso.

Lecciones de la piloto que quedan dentro (revision-de-taller, defectos.md):
- larguero de ÁNGULO con el ala horizontal ABAJO y hacia AFUERA: la tuerca del eje queda en la
  cara exterior del ala vertical, lejos del ala horizontal, y entra la llave;
- patas en H: travesaño ENTRE las patas, soldado a sus caras interiores; ningún travesaño fuera
  de una estación de patas (los ejes atornillados ya amarran los largueros);
- una sola familia de piñones dobles-simples: la cadena `fase: "auto"` gira los alternos;
- la cadena motriz se TENSA: va inclinada (`ANGULO_MOTRIZ`) hacia la alimentación y el motor
  desliza en X sobre ranuras abiertas de su base (cada mm de ranura acerca o aleja los centros
  sin(θ) mm), y sus centros son los exactos de un número par de eslabones (`eslabones_pares`),
  nunca una cota a mano.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .catalog import CATALOG
from .engineering.secciones import angulo_libre
from .transmision import diametro_primitivo, eslabones_pares

CADENA = "CADENA-ASA40-1"
PINON_RODILLO = "PINON-ASA40-DS-Z15"
PINON_MOTRIZ = "PINON-ASA40-1-Z30"
LARGUERO = "ANG-75X6"
PATA = "TUBO-2X2"
TUERCA = "TUERCA-M12"
RODILLOS = ("TUBOR-2", "TUBOR-2.5", "TUBOR-3")
MOTORES = ("MOTOR-037", "MOTOR-075", "MOTOR-150")
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
PLACA_PATA_T = 10.0
ANCLAJE_D = 14.0           # perno de expansión M12 al piso
Z_TRAVESANO = 150.0        # centro del travesaño bajo de las patas en H
MARGEN_EXTREMO = 50.0      # eje del primer/último rodillo ↔ extremo del larguero (mínimo)
LARGO_MIN = 1000.0
#: Inclinación de la cadena motriz desde la vertical, hacia la alimentación. Con paso 95.25 deja
#: 7.7 mm a la cadena del penúltimo rodillo (`holgura_motriz`); a 25° quedarían 3.
ANGULO_MOTRIZ = 20.0
TENSADO_MIN_MM = 20.0      # recorrido mínimo del motor sobre sus ranuras, a cada lado
BASE_MOTOR_T = 8.0
RANURA_ANCHO = 10.0        # M8 de las patas del motor
GUARDA_T = 2.0
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


@dataclass(frozen=True)
class MotorLocal:
    """Medidas del motorreductor helicoidal en su marco LOCAL (builder `motor`: eje común = X,
    origen en el centro de la caja reductora, eje de salida hacia +X)."""

    x_min: float           # extremo de la tapa del ventilador
    eje_ini: float         # el eje de salida va de eje_ini a eje_fin
    eje_fin: float
    eje_d: float
    z_max: float           # tope de la caja de bornes
    z_pies: float          # cara inferior de las patas
    pie_y: float           # los dos rieles de patas en y = ±pie_y
    pie_ancho: float
    pie_x0: float          # los rieles van de pie_x0 a pie_x1
    pie_x1: float


def motor_local(ref: str) -> MotorLocal:
    """Las fórmulas del builder `motor` (`builders.py`) sobre los params del catálogo; un test
    las compara con el sólido construido."""
    p = CATALOG[ref].params or {}
    box, md, ml = float(p["box_size"]), float(p["motor_d"]), float(p["motor_len"])
    gl = box * 0.95
    sd = float(p.get("shaft_d") or box * 0.22)
    sl = float(p.get("shaft_len") or box * 0.6)
    mx = -gl / 2.0 - md * 0.28 - ml / 2.0
    foot_cx = (mx + gl / 2.0) / 2.0
    foot_len = (gl / 2.0 - (mx - ml / 2.0)) * 0.92
    return MotorLocal(
        x_min=mx - ml / 2.0 - md * 0.15, eje_ini=gl / 2.0 - 6.0, eje_fin=gl / 2.0 + sl - 6.0,
        eje_d=sd, z_max=md * 0.70, z_pies=-md * 0.565, pie_y=md * 0.30, pie_ancho=md * 0.16,
        pie_x0=foot_cx - foot_len / 2.0, pie_x1=foot_cx + foot_len / 2.0,
    )


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
class Motriz:
    motor: str
    potencia_kw: float
    rpm: float
    x: float               # origen del motorreductor (eje de salida a lo largo de +Y)
    y: float
    z: float
    angulo_deg: float
    eslabones: int
    centros: float
    tensado_mm: float      # recorrido del motor a cada lado sobre las ranuras
    eje_d: float
    y_pinon: float         # plano de la hilera del piñón motriz (= hilera 2 del último rodillo)
    base: dict             # x, y, z (centro), ancho (X), largo (Y), puntos (polígono local)
    guarda: dict           # x, y (cara exterior), z (centro), ancho, alto, pestana


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
    velocidad_m_s: float | None
    potencia_req_kw: float | None
    motriz: Motriz | None


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


def _tangentes(c1, r1, c2, r2):
    """Los dos tramos rectos (tangentes exteriores) de una cadena abierta entre dos círculos de
    paso, como pares de puntos."""
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    d = math.hypot(dx, dy)
    ux, uy = dx / d, dy / d
    k = (r1 - r2) / d
    h = math.sqrt(max(0.0, 1.0 - k * k))
    out = []
    for s in (1.0, -1.0):
        nx, ny = k * ux - s * h * uy, k * uy + s * h * ux
        out.append(((c1[0] + r1 * nx, c1[1] + r1 * ny), (c2[0] + r2 * nx, c2[1] + r2 * ny)))
    return out


def _dist_segmento(q, a, b) -> float:
    ax, ay = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((q[0] - a[0]) * ax + (q[1] - a[1]) * ay) / (ax * ax + ay * ay)))
    return math.hypot(q[0] - a[0] - t * ax, q[1] - a[1] - t * ay)


def holgura_motriz(paso: float, centros: float, angulo_deg: float) -> float:
    """mm libres entre la cadena motriz (y su piñón) y la cadena de la hilera 2 que abraza el
    piñón del PENÚLTIMO rodillo, en el plano de la hilera 2 (XZ). Negativo = chocan."""
    sc = CATALOG[CADENA].specs
    p, alto = float(sc["paso"]), float(sc["alto_placa"])
    r_s = diametro_primitivo(p, int(CATALOG[PINON_RODILLO].specs["z"])) / 2.0
    r_m = diametro_primitivo(p, int(CATALOG[PINON_MOTRIZ].specs["z"])) / 2.0
    a = math.radians(angulo_deg)
    ultimo, motor, penultimo = (0.0, 0.0), (-centros * math.sin(a), -centros * math.cos(a)), (-paso, 0.0)
    envolvente = r_s + alto / 2.0  # la cadena 1:1 abraza el penúltimo piñón hasta aquí
    tramos = min(_dist_segmento(penultimo, *t) for t in _tangentes(ultimo, r_s, motor, r_m))
    return min(tramos - envolvente - alto / 2.0,
               math.dist(penultimo, motor) - envolvente - (r_m + alto / 2.0))


def _rodillos(largo: float, paso: float) -> tuple:
    n = int((largo - 2.0 * MARGEN_EXTREMO) // paso) + 1
    n -= n % 2  # par: la última cadena 1:1 cae en la hilera 1 y la 2 queda para la motriz
    if n < 4:
        raise ValueError(f"largo {largo:g} mm no alcanza para 4 rodillos a paso {paso:g}")
    x0 = (largo - (n - 1) * paso) / 2.0
    return tuple(round(x0 + i * paso, 6) for i in range(n))


def _motriz(motor: str, d: dict) -> Motriz:
    """Motorreductor bajo el último rodillo, cadena motriz inclinada y base ranurada."""
    sc, sm = CATALOG[CADENA].specs, CATALOG[PINON_MOTRIZ].specs
    sr = CATALOG[PINON_RODILLO].specs
    p, alto, perno = float(sc["paso"]), float(sc["alto_placa"]), float(sc["ancho_sobre_perno"])
    zm, zr = int(sm["z"]), int(sr["z"])
    ml = motor_local(motor)
    h, x_l, y_h2 = d["h_eje"], d["xs"][-1], d["y_h2"]
    # el motor (caja de bornes) pasa bajo los tubos con 10 mm de aire
    bajo = ml.z_max + d["d_rodillo"] / 2.0 + 10.0
    ang = ANGULO_MOTRIZ
    a = math.radians(ang)
    n, c = eslabones_pares(p, zm, zr, bajo / math.cos(a))  # el menor par que alcanza
    if holgura_motriz(d["paso"], c, ang) < 5.0:
        raise ValueError(f"la cadena motriz choca con la del penúltimo rodillo a paso {d['paso']:g}: "
                         "usa un paso de rodillos mayor")
    tensado = max(TENSADO_MIN_MM, p / 2.0 / math.sin(a))
    x_m, z_m = x_l - c * math.sin(a), h - c * math.cos(a)
    medio_pinon = float(sm["ancho_diente"]) / 2.0
    y_m = y_h2 + medio_pinon + 5.0 - ml.eje_fin  # el eje asoma 5 mm del piñón
    atras = y_m + ml.x_min
    if atras < d["y_in_m"] + 15.0:
        falta = d["y_in_m"] + 15.0 - atras
        raise ValueError(
            f"el motorreductor {motor} no cabe entre las patas: ancho_util mínimo "
            f"{math.ceil(d['ancho_util'] + falta):g} mm (va bajo los rodillos, con el eje hacia "
            "la transmisión)")
    # base: placa con ranuras ABIERTAS en X bajo los 2 rieles de patas (M8, 2 por riel)
    medio_x = ml.pie_y + ml.pie_ancho / 2.0 + tensado + 15.0
    y_lo = y_m + ml.pie_x0 - 5.0
    y_hi = y_h2 - perno / 2.0 - 9.1  # deja pasar la pestaña de la guarda de transmisión
    yc = (y_lo + y_hi) / 2.0
    fondo = ml.pie_y - tensado - RANURA_ANCHO / 2.0  # fondo de la ranura (|x| local)
    ranuras = [y_lo + 25.0 - yc, y_hi - 25.0 - yc]
    puntos = [[-medio_x, y_lo - yc], [medio_x, y_lo - yc]]
    for yr in ranuras:  # borde +X, de abajo hacia arriba
        w = RANURA_ANCHO / 2.0
        puntos += [[medio_x, yr - w], [fondo, yr - w], [fondo, yr + w], [medio_x, yr + w]]
    puntos += [[medio_x, y_hi - yc], [-medio_x, y_hi - yc]]
    for yr in reversed(ranuras):  # borde −X, de arriba hacia abajo
        w = RANURA_ANCHO / 2.0
        puntos += [[-medio_x, yr + w], [-fondo, yr + w], [-fondo, yr - w], [-medio_x, yr - w]]
    z_base = z_m + ml.z_pies - BASE_MOTOR_T / 2.0
    base = {"x": x_m, "y": yc, "z": z_base, "ancho": 2 * medio_x, "largo": y_hi - y_lo,
            "puntos": [[round(u, 3), round(v, 3)] for u, v in puntos]}
    if z_base - BASE_MOTOR_T / 2.0 - float(CATALOG[PATA].specs["width"]) < PLACA_PATA_T + 60.0:
        raise ValueError("altura insuficiente para el motorreductor bajo los rodillos: sube la "
                         "altura de trabajo")
    # guarda de transmisión: caja de chapa por fuera de la cadena motriz, sobre el portamotor
    r_m = diametro_primitivo(p, zm) / 2.0 + alto / 2.0 + 8.0
    r_s = diametro_primitivo(p, zr) / 2.0 + alto / 2.0 + 5.0
    x_lo, x_hi = min(x_m - r_m, x_l - r_s), max(x_m + r_m, x_l + r_s)
    z_lo, z_hi = z_base - BASE_MOTOR_T / 2.0, h - 42.0
    y_ext = y_h2 + perno / 2.0 + 10.5
    guarda = {"x": (x_lo + x_hi) / 2.0, "y": y_ext, "z": (z_lo + z_hi) / 2.0,
              "ancho": x_hi - x_lo, "alto": z_hi - z_lo,
              "pestana": y_ext - (y_h2 - perno / 2.0 - 5.1) - GUARDA_T}
    sp = CATALOG[motor].specs
    return Motriz(
        motor=motor, potencia_kw=float(sp["potencia_kW"]), rpm=float(sp["rpm_salida"]),
        x=x_m, y=y_m, z=z_m, angulo_deg=ang, eslabones=n, centros=c, tensado_mm=tensado,
        eje_d=ml.eje_d, y_pinon=y_h2, base=base, guarda=guarda,
    )


def disposicion(largo: float, ancho_util: float, paso: float, rodillo: str, altura: float,
                carga_kg: float, motriz: bool, motor: str | None) -> Disposicion:
    """Todas las cotas del transportador; `ValueError` accionable si no se puede fabricar."""
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
         "y_in_m": y_in_m, "ancho_util": ancho_util}
    mot = _motriz(motor or MOTORES[0], d) if motriz else None
    # estaciones: voladizo igual en los dos extremos; la motriz bajo el motor
    voladizo = (largo - mot.x) if mot is not None else xs[0] + 50.0
    x_f, x_d = voladizo, largo - voladizo
    vano = vano_maximo(carga_kg, m_rod, largo)
    n_vanos = max(1, math.ceil((x_d - x_f) / vano - 1e-9))
    estaciones = []
    for k in range(n_vanos + 1):
        x = x_f + (x_d - x_f) * k / n_vanos
        rol = "alimentacion" if k == 0 else ("motriz" if k == n_vanos else "intermedia")
        zt = Z_TRAVESANO
        if rol == "motriz" and mot is not None:
            zt = mot.base["z"] - BASE_MOTOR_T / 2.0 - float(CATALOG[PATA].specs["width"]) / 2.0
        estaciones.append(Estacion(round(x, 6), rol, zt))
    velocidad = potencia = None
    if mot is not None:
        zm, zr = int(CATALOG[PINON_MOTRIZ].specs["z"]), int(sr["z"])
        velocidad = math.pi * d_rod * mot.rpm * zm / zr / 60000.0
        # carga repartida: el rodillo k recibe su parte a través de k lazos (la motriz es el 1.º)
        n = len(xs)
        eta = n / sum(ETA_LAZO ** -k for k in range(1, n + 1)) * ETA_REDUCTOR
        potencia = FACTOR_ARRANQUE * MU_RODADURA * (carga_kg + m_rod) * G * velocidad / eta / 1000.0
        if potencia > mot.potencia_kw:
            raise ValueError(f"{mot.motor} da {mot.potencia_kw:g} kW y la carga pide "
                             f"{potencia:.2f} kW: elige un motorreductor mayor")
    # guarda de cadenas: sobre los separadores, por encima de las cadenas y de los tubos
    sep_z0 = h + TOPE_SOBRE_EJE
    r_cad = diametro_primitivo(float(sc["paso"]), int(sr["z"])) / 2.0 + float(sc["alto_placa"]) / 2.0
    guarda_base = max(h + r_cad + 3.0, h + d_rod / 2.0 + 3.0 + GUARDA_PESTANA + GUARDA_T)
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
        z_larguero=h + TOPE_SOBRE_EJE - ala / 2.0, pata_largo=pata, estaciones=tuple(estaciones),
        travesano_largo=y_in_p - y_in_m, separadores=seps, sep_z0=sep_z0,
        guarda_z=guarda_base + GUARDA_T, vano_max=vano, velocidad_m_s=velocidad,
        potencia_req_kw=potencia, motriz=mot,
    )
