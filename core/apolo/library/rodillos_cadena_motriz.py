"""Motriz PURA del transportador de rodillos por cadena (`create_roller_conveyor`, plan
`docs/plans/plantilla-rodillos-cadena.md`, D1, D6 y D7). Sin `Document` ni OCCT.

El motorreductor va bajo el último rodillo con la cadena motriz inclinada `ANGULO_MOTRIZ`
hacia la alimentación. Se TENSA corriendo SOBRE la línea de centros (D7): el travesaño
portamotor se atornilla a las caras interiores de las patas con orejas soldadas a sus
extremos, de ranuras paralelas a esa línea, y base, motor y cárter corren juntos. Recorrido:
`+tensado_mm` (aleja el motor) ≥ la mitad del estirado de reemplazo (3 % del largo de la
cadena → 1.5 % en centros; criterio de diseño de los fabricantes de cadena de rodillos,
Tsubaki/Renold) y `−montaje_mm` (acerca) para montar el eslabón de unión. Una ranura de cada
oreja abre arriba y la otra abajo: cada sentido lo frena el fondo de una.

Con `velocidad_m_s` (D6) el piñón del motor sale de los ASA 40 SIMPLES del catálogo: el de
la velocidad más cercana dentro de ±10 % que entre en el eje del motor y arme la motriz.

MARCO: el de `rodillos_cadena.py` (X transporte, Y = 0 al centro del tubo, transmisión hacia
+Y, Z = 0 el piso). En el plano XZ de la motriz, ŵ = (sen a, cos a) va del eje del motor al
del último rodillo y û = (cos a, −sen a) es su normal hacia +X.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .catalog import CATALOG
from .transmision import diametro_primitivo, eslabones_pares

CADENA = "CADENA-ASA40-1"
PINON_RODILLO = "PINON-ASA40-DS-Z15"
#: El piñón del motor cuando no se pide velocidad (logs v1): la velocidad de siempre.
PINON_MOTRIZ = "PINON-ASA40-1-Z30"
PATA = "TUBO-2X2"
MOTORES = ("MOTOR-037", "MOTOR-075", "MOTOR-150")
PLACA_PATA_T = 10.0
#: Inclinación de la cadena motriz desde la vertical, hacia la alimentación. Con paso 95.25 deja
#: 7.7 mm a la cadena del penúltimo rodillo (`holgura_motriz`); a 25° quedarían 3.
ANGULO_MOTRIZ = 20.0
BASE_MOTOR_T = 8.0
SERVICIO = "moderado"
TOL_VELOCIDAD = 0.10       # ±10 %: el criterio «0.9 × objetivo» de la velocidad de banda
#: Estirado de reemplazo de una cadena de rodillos: 3 % de su largo (Tsubaki, Renold).
ESTIRADO_REEMPLAZO = 0.03
MONTAJE_MM = 3.0           # acercar el motor para montar el eslabón de unión
OREJA_T = 6.0              # chapa de la oreja del portamotor
OREJA_U = 35.0             # media anchura de la oreja (según û)
OREJA_W = 75.0             # medio largo de la oreja (según ŵ)
PERNO_OREJA = "M10"
RANURA_OREJA = 11.0        # paso de un M10
W_PERNO = 50.0             # pernos de la oreja a ±50 mm del centro del tubo, según ŵ
HOLGURA_GIRA = 3.0         # nada que no gire a menos de esto de lo que gira


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
    pie_alto: float
    pie_x0: float          # los rieles van de pie_x0 a pie_x1
    pie_x1: float
    caja_x1: float         # cara de la caja reductora hacia el eje de salida


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
        pie_alto=md * 0.13, pie_x0=foot_cx - foot_len / 2.0, pie_x1=foot_cx + foot_len / 2.0,
        caja_x1=gl / 2.0,
    )


def pinones_motor() -> list[str]:
    """Los piñones ASA 40 SIMPLES del catálogo (los que puede llevar el motor), de menor a
    mayor número de dientes."""
    refs = [r for r, c in CATALOG.items()
            if (c.specs or {}).get("serie") == "ASA 40" and c.specs.get("tipo") == "simple"]
    return sorted(refs, key=lambda r: int(CATALOG[r].specs["z"]))


def velocidad_producto(d_rodillo: float, rpm_motor: float, z_motor: int) -> float:
    """m/s del producto: superficie del tubo (π·Ø·n), con el rodillo a rpm·z_motor/z_rodillo.
    No es la de la cadena (π·Ø primitivo·n), que el revisor de F3 leyó por la del producto."""
    zr = int(CATALOG[PINON_RODILLO].specs["z"])
    return math.pi * d_rodillo * rpm_motor * z_motor / zr / 60000.0


def tensado_requerido(eslabones: int, paso: float) -> float:
    """mm que los centros deben crecer para absorber el estirado de reemplazo: la mitad del
    3 % del largo de la cadena (el estirado se reparte en los dos ramales)."""
    return ESTIRADO_REEMPLAZO / 2.0 * eslabones * paso


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


def holgura_motriz(paso: float, centros: float, angulo_deg: float,
                   pinon: str = PINON_MOTRIZ) -> float:
    """mm libres entre la cadena motriz (y su piñón) y la cadena de la hilera 2 que abraza el
    piñón del PENÚLTIMO rodillo, en el plano de la hilera 2 (XZ). Negativo = chocan."""
    sc = CATALOG[CADENA].specs
    p, alto = float(sc["paso"]), float(sc["alto_placa"])
    r_s = diametro_primitivo(p, int(CATALOG[PINON_RODILLO].specs["z"])) / 2.0
    r_m = diametro_primitivo(p, int(CATALOG[pinon].specs["z"])) / 2.0
    a = math.radians(angulo_deg)
    ultimo, motor, penultimo = (0.0, 0.0), (-centros * math.sin(a), -centros * math.cos(a)), (-paso, 0.0)
    envolvente = r_s + alto / 2.0  # la cadena 1:1 abraza el penúltimo piñón hasta aquí
    tramos = min(_dist_segmento(penultimo, *t) for t in _tangentes(ultimo, r_s, motor, r_m))
    return min(tramos - envolvente - alto / 2.0,
               math.dist(penultimo, motor) - envolvente - (r_m + alto / 2.0))


@dataclass(frozen=True)
class Motriz:
    motor: str
    pinon: str             # piñón del motor (D6)
    z_pinon: int
    potencia_kw: float
    rpm: float
    x: float               # origen del motorreductor (eje de salida a lo largo de +Y)
    y: float
    z: float
    angulo_deg: float
    eslabones: int
    centros: float
    tensado_mm: float      # +recorrido sobre la línea de centros (aleja el motor: tensa)
    montaje_mm: float      # −recorrido (acerca: monta el eslabón de unión)
    eje_d: float
    y_pinon: float         # plano de la hilera del piñón motriz (= hilera 2 del último rodillo)
    y_cubo: float          # cara del cubo del piñón motriz hacia el motor
    r_envolvente: float    # radio que barre la cadena (o el piñón) alrededor del eje del motor
    z_base: float          # cara SUPERIOR de la base = apoyo de las patas del motor
    y_base0: float         # la base empieza bajo el extremo de las patas del motor
    pies: tuple            # (x0, x1) de los dos rieles de patas
    pies_z: float          # cara superior de los rieles
    pies_y1: float         # extremo de los rieles hacia la transmisión
    portamotor: dict       # x, y, z (centro del tubo) y largo (entre orejas)
    oreja: dict            # puntos XZ relativos al centro del tubo, pernos y ranuras


def _a_xz(u: float, w: float, a: float) -> tuple[float, float]:
    return (u * math.cos(a) + w * math.sin(a), -u * math.sin(a) + w * math.cos(a))


def _oreja(tensado: float, a: float) -> dict:
    """Oreja del portamotor en (û, ŵ) alrededor del centro del tubo, pasada a XZ. El perno A
    (arriba) entra por una ranura que ABRE arriba y la cierra abajo el fondo que frena el
    acercamiento de montaje; el B (abajo), por una que abre abajo y cuyo fondo frena el tensado.
    Los dos caen sobre la vertical del centro de la pata (û = −ŵ·tan a)."""
    r = RANURA_OREJA / 2.0
    ua, ub = -W_PERNO * math.tan(a), W_PERNO * math.tan(a)
    wa_fondo = W_PERNO - MONTAJE_MM - r - 0.5  # 0.5 mm de más: el fondo no es el tope exacto
    wb_fondo = -W_PERNO + tensado + r + 0.5
    if wb_fondo >= wa_fondo - 10.0:
        raise ValueError("el recorrido de tensado no cabe en las orejas del portamotor")
    uw = [(-OREJA_U, -OREJA_W), (ub - r, -OREJA_W), (ub - r, wb_fondo), (ub + r, wb_fondo),
          (ub + r, -OREJA_W), (OREJA_U, -OREJA_W), (OREJA_U, OREJA_W), (ua + r, OREJA_W),
          (ua + r, wa_fondo), (ua - r, wa_fondo), (ua - r, OREJA_W), (-OREJA_U, OREJA_W)]
    return {
        "puntos": [[round(v, 4) for v in _a_xz(u, w, a)] for u, w in uw],
        "pernos": [_a_xz(ua, W_PERNO, a), _a_xz(ub, -W_PERNO, a)],
        "ranuras": [{"perno": _a_xz(ua, W_PERNO, a), "abre": "arriba"},
                    {"perno": _a_xz(ub, -W_PERNO, a), "abre": "abajo"}],
        "medio_alto": OREJA_W * math.cos(a) + OREJA_U * math.sin(a),
    }


def _libra_pies(ml: MotorLocal, y_pies1: float, y_h2: float, y_cubo: float, sm: dict,
                r_env: float, perno: float) -> float:
    """Radio de lo que gira sobre los rieles de patas que se meten bajo el piñón (0 si no)."""
    radio = 0.0
    if y_pies1 + HOLGURA_GIRA > y_cubo:
        radio = float(sm["cubo"]) / 2.0
    if y_pies1 + HOLGURA_GIRA > y_h2 - float(sm["ancho_diente"]) / 2.0:
        radio = float(sm["de"]) / 2.0
    if y_pies1 + HOLGURA_GIRA > y_h2 - perno / 2.0:
        radio = max(radio, r_env)
    return radio


def motriz(motor: str, pinon: str, d: dict) -> Motriz:
    """Motorreductor bajo el último rodillo, cadena motriz inclinada, base y portamotor con
    orejas. `ValueError` accionable si no se arma."""
    sc, sm = CATALOG[CADENA].specs, CATALOG[pinon].specs
    sr = CATALOG[PINON_RODILLO].specs
    p, alto, perno = float(sc["paso"]), float(sc["alto_placa"]), float(sc["ancho_sobre_perno"])
    zm, zr = int(sm["z"]), int(sr["z"])
    ml = motor_local(motor)
    if float(sm.get("agujero_max_mm") or 0.0) < ml.eje_d:
        raise ValueError(f"el piñón Z{zm} (agujero máx Ø{float(sm.get('agujero_max_mm') or 0):g}) no "
                         f"entra en el eje Ø{ml.eje_d:g} del {motor}")
    h, x_l, y_h2 = d["h_eje"], d["xs"][-1], d["y_h2"]
    # el motor (caja de bornes) pasa bajo los tubos con 10 mm de aire
    bajo = ml.z_max + d["d_rodillo"] / 2.0 + 10.0
    ang = ANGULO_MOTRIZ
    a = math.radians(ang)
    n, c = eslabones_pares(p, zm, zr, bajo / math.cos(a))  # el menor par que alcanza
    tensado = tensado_requerido(n, p)
    if holgura_motriz(d["paso"], c, ang, pinon) < 5.0 or min(
            holgura_motriz(d["paso"], c + t, ang, pinon) for t in (-MONTAJE_MM, tensado)) < HOLGURA_GIRA:
        raise ValueError(f"la cadena motriz (Z{zm}) choca con la del penúltimo rodillo a paso "
                         f"{d['paso']:g}: usa un paso de rodillos mayor")
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
    y_cubo = y_h2 + medio_pinon - float(sm["largo"])
    if y_cubo - (y_m + ml.caja_x1) < 14.0:  # dos paredes de 2 + rendija + holguras
        raise ValueError(f"el eje del {motor} no deja lugar a las paredes del cárter")
    r_env = max(diametro_primitivo(p, zm) / 2.0 + alto / 2.0, float(sm["de"]) / 2.0)
    z_b = z_m + ml.z_pies
    if z_m - r_env - HOLGURA_GIRA < z_b:
        raise ValueError(f"el piñón Z{zm} toca la base del {motor}: usa un piñón menor")
    pies = tuple((x_m + s * ml.pie_y - ml.pie_ancho / 2.0, x_m + s * ml.pie_y + ml.pie_ancho / 2.0)
                 for s in (-1.0, 1.0))
    pies_z, pies_y1 = z_b + ml.pie_alto, y_m + ml.pie_x1
    radio = _libra_pies(ml, pies_y1, y_h2, y_cubo, sm, r_env, perno)
    if radio and math.hypot(ml.pie_y - ml.pie_ancho / 2.0, z_m - pies_z) < radio + HOLGURA_GIRA:
        raise ValueError(f"el piñón Z{zm} toca las patas del {motor}: usa un piñón menor")
    w = float(CATALOG[PATA].specs["width"])
    z_t = z_b - BASE_MOTOR_T - w / 2.0
    oreja = _oreja(tensado, a)
    if z_t - oreja["medio_alto"] - tensado < d.get("z_pata0", PLACA_PATA_T) + 20.0:
        raise ValueError("altura insuficiente para el motorreductor bajo los rodillos: sube la "
                         "altura de trabajo")
    sp = CATALOG[motor].specs
    return Motriz(
        motor=motor, pinon=pinon, z_pinon=zm, potencia_kw=float(sp["potencia_kW"]),
        rpm=float(sp["rpm_salida"]), x=x_m, y=y_m, z=z_m, angulo_deg=ang, eslabones=n, centros=c,
        tensado_mm=tensado, montaje_mm=MONTAJE_MM, eje_d=ml.eje_d, y_pinon=y_h2, y_cubo=y_cubo,
        r_envolvente=r_env, z_base=z_b, y_base0=y_m + ml.pie_x0 - 5.0, pies=pies, pies_z=pies_z,
        pies_y1=pies_y1,
        portamotor={"x": x_m, "y": (d["y_in_m"] + d["y_in_p"]) / 2.0, "z": z_t,
                    "largo": d["y_in_p"] - d["y_in_m"] - 2.0 * OREJA_T},
        oreja=oreja,
    )


def _falla(armar, motor: str, pinon: str) -> str | None:
    """Por qué no se arma la motriz con ese motor y ese piñón (None si se arma)."""
    try:
        armar(motor, pinon)
    except ValueError as exc:
        return str(exc)
    return None


def elegir_pinon(motor: str, velocidad_m_s: float | None, d_rodillo: float, armar) -> str:
    """Piñón del motor: sin velocidad pedida, `PINON_MOTRIZ` (logs v1); con ella, el ASA 40
    simple que dé la velocidad más cercana dentro de ±10 % y con el que `armar(motor, piñón)`
    (motriz + guardas; `ValueError` si no) no falle. Si ninguno, `ValueError` con las
    velocidades que salen con ese motor y qué motor + piñón da la pedida."""
    if velocidad_m_s is None:
        return PINON_MOTRIZ

    def v(m, ref):
        return velocidad_producto(d_rodillo, float(CATALOG[m].specs["rpm_salida"]),
                                  int(CATALOG[ref].specs["z"]))

    def dentro(m):
        return sorted((abs(v(m, r) - velocidad_m_s), r) for r in pinones_motor()
                      if abs(v(m, r) - velocidad_m_s) <= TOL_VELOCIDAD * velocidad_m_s)

    for _, ref in dentro(motor):
        if _falla(armar, motor, ref) is None:
            return ref
    salen = ", ".join(f"Z{CATALOG[r].specs['z']} {v(motor, r):.3f}" for r in pinones_motor()
                      if _falla(armar, motor, r) is None)
    otros = sorted((dv, m, r) for m in MOTORES if m != motor for dv, r in dentro(m))
    sugerencia = "ningún motorreductor del catálogo la da: cambia el Ø del rodillo"
    if otros:  # el primero que se arma; si ninguno, el más cercano y por qué no se arma
        m, r = next(((m, r) for _, m, r in otros if _falla(armar, m, r) is None), otros[0][1:])
        falla = _falla(armar, m, r)
        sugerencia = (f"{m} + piñón Z{CATALOG[r].specs['z']} da {v(m, r):.3f} m/s"
                      + (f", pero {falla}" if falla else ""))
    raise ValueError(f"velocidad {velocidad_m_s:g} m/s: con {motor} ningún piñón la da dentro de "
                     f"±{TOL_VELOCIDAD:.0%} (salen, en m/s: {salen or 'ninguna'}); {sugerencia}")
