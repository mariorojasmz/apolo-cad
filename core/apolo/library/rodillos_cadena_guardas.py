"""Guardas PURAS de la transmisión del transportador de rodillos por cadena (plan
`docs/plans/plantilla-rodillos-cadena.md`, D4 y D5). Sin `Document` ni OCCT: polígonos en el
plano XZ (marco de `rodillos_cadena.py`) que la receta extruye a lo largo de Y.

D4 — la guarda de la transmisión son dos cajas que TELESCOPAN a lo largo de la línea de
centros de la motriz (ISO 14120; aberturas por ISO 13857, tabla 4):
- **cárter móvil**, soldado a la base del motor (su piso): pared interior con barreno del eje
  y muescas para las patas del motor, pared exterior y dos extremos. Corre con el motor al
  tensar: ninguna pared fija necesita ranura para el eje;
- **guarda fija**, cuatro paredes por fuera del cárter con una rendija de `RENDIJA` mm, desde
  encima del eje del motor hasta bajo los tubos, atornillada (M6) al alma del larguero +Y. Su
  extremo +X sube hasta la guarda de cadenas y cierra el final del bastidor.
- Rendija ≤ 6.1 mm → ISO 13857 tabla 4 pide ≥ `SOLAPE_ISO` mm al peligro: el solape de las
  dos cajas sobre la línea de centros es ese número más el recorrido de tensado y de montaje.
  Eje en su barreno y patas en sus muescas: 2 mm de holgura (e ≤ 4).

D5 — la bandeja inferior de cadenas: perfil en C de chapa bajo los lazos y los piñones, de la
alimentación a la guarda fija, en tramos de ≤ `TRAMO_MAX` que se sacan con 2 M6 al alma.
"""

from __future__ import annotations

import math

from .rodillos_cadena_motriz import HOLGURA_GIRA, MONTAJE_MM, OREJA_T, Motriz

GUARDA_T = 2.0             # chapa de guardas y bandeja
RENDIJA = 5.0              # entre las paredes que telescopan (≤ 6.1: ISO 13857 tabla 4)
SOLAPE_ISO = 20.0          # ISO 13857 tabla 4: rendija 6 < e ≤ 8 → 20 mm hasta el peligro
HOLGURA_PIE = 2.0          # muescas del cárter alrededor de las patas del motor y del eje
BAJO_CADENA = 5.0          # fondo de la bandeja bajo el ramal más bajo
BAJO_TUBO = 3.0            # pestañas bajo los tubos
M6_PASO = 6.6              # ISO 273 media
V_PERNO = 7.0              # M6 al alma: a 7 mm del borde libre de la pestaña
TRAMO_MAX = 1000.0
X_INICIO = 2.5             # la bandeja (y su tapa) empiezan a 2.5 mm del extremo del bastidor
SEPARACION_TRAMOS = 1.0


def tope_atornillado(d: dict) -> tuple[float, float]:
    """(borde de las pestañas que se atornillan al alma del larguero, altura de sus M6). Bajo
    los tubos si el ala lo deja (así sus cajas no tocan las de los tubos y la puerta de entrega
    no gasta parejas candidatas), y nunca con el M6 fuera de la zona plana del ala (lint
    «asiento fuera de la zona plana», `acuerdos.zona_plana_ala_angulo`)."""
    z_perno = d["z_alma_plana"] + M6_PASO / 2.0 + 1.0
    tope = min(d["h_eje"] - d["d_rodillo"] / 2.0 - 0.5, d["h_eje"] - 25.0)
    # el barreno de la pestaña de la bandeja, fuera de su pliegue (radio 2 + espesor)
    pestana_min = V_PERNO + M6_PASO / 2.0 + 2.0 * GUARDA_T + 1.0
    tope = max(tope, z_perno + V_PERNO, d["z_bandeja"] + GUARDA_T + pestana_min)
    return tope, tope - V_PERNO


def tira(polilinea: list, espesor: float, lado: float) -> tuple[list, list]:
    """Chapa de `espesor` a un `lado` (+1 hacia +X subiendo) de la `polilinea` de su cara
    interior (de abajo hacia arriba, ningún tramo horizontal): (polígono, cara exterior). Los
    extremos se cortan en horizontal, a la altura del primer y del último punto."""
    segs = []
    for (x0, z0), (x1, z1) in zip(polilinea, polilinea[1:]):
        lg = math.hypot(x1 - x0, z1 - z0)
        dx, dz = (x1 - x0) / lg, (z1 - z0) / lg
        segs.append(((dx, dz), (lado * dz, -lado * dx)))
    ext = []
    for j, (x, z) in enumerate(polilinea):
        if j in (0, len(polilinea) - 1):
            (dx, dz), (nx, nz) = segs[0 if j == 0 else -1]
            k = -espesor * nz / dz  # resbala sobre el tramo hasta la horizontal del extremo
            ext.append((x + espesor * nx + k * dx, z))
        else:
            (_, n0), (_, n1) = segs[j - 1], segs[j]
            f = espesor / (1.0 + n0[0] * n1[0] + n0[1] * n1[1])
            ext.append((x + f * (n0[0] + n1[0]), z + f * (n0[1] + n1[1])))
    return list(polilinea) + ext[::-1], ext


def cortar(polilinea: list, z: float) -> list:
    """La polilínea (de abajo hacia arriba) hasta la altura `z`."""
    out = [polilinea[0]]
    for (x0, z0), (x1, z1) in zip(polilinea, polilinea[1:]):
        if z1 >= z:
            out.append((x0 + (x1 - x0) * (z - z0) / (z1 - z0), z))
            return out
        out.append((x1, z1))
    return out


def _r(pts) -> list:
    return [[round(x, 4), round(z, 4)] for x, z in pts]


class _Linea:
    """Recta paralela a la línea de centros a distancia `u` (+X) del eje del motor."""

    def __init__(self, mot: Motriz):
        self.m, self.a = mot, math.radians(mot.angulo_deg)

    def x(self, u: float, z: float) -> float:
        return self.m.x + u / math.cos(self.a) + (z - self.m.z) * math.tan(self.a)

    def z(self, u: float, x: float) -> float:
        return self.m.z + (x - self.m.x - u / math.cos(self.a)) / math.tan(self.a)


def _extremo_carter(ln: _Linea, u: float, z0: float, z1: float, x_libre: float, s: float) -> list:
    """Cara interior de un extremo del cárter: sobre la línea `u` y, si al pie no libra la pata
    del motor (`x_libre`), vertical hasta donde la línea la libra."""
    x0 = ln.x(u, z0)
    if (x_libre - x0) * s <= 0:
        return [(x0, z0), (ln.x(u, z1), z1)]
    return [(x_libre, z0), (x_libre, ln.z(u, x_libre)), (ln.x(u, z1), z1)]


def _contorno(izq: list, der: list, z_top: float) -> list:
    """Contorno de una pared en Y entre las caras exteriores de sus dos extremos, hasta
    `z_top`: cada lado se corta ahí o sigue en vertical hasta ahí."""
    def hasta(pl):
        pl = cortar(pl, z_top) if pl[-1][1] > z_top else list(pl)
        return pl + [(pl[-1][0], z_top)] if pl[-1][1] < z_top else pl

    return hasta(izq) + hasta(der)[::-1]


def guarda_transmision(mot: Motriz, d: dict) -> dict:
    """Cárter móvil + guarda fija. `d` (lo arma `rodillos_cadena.disposicion`): h_eje,
    d_rodillo, r_cadena (envolvente de las cadenas 1:1), x_ultimo, largo, a2, y_in_p,
    z_bandeja (cara inferior de la bandeja), y_pestana / z_pestana (cara exterior y borde libre
    de la pestaña interior de la guarda de cadenas), z_guarda (cara inferior de su chapa) y
    z_alma_plana (donde empieza la zona plana del ala). `ValueError` si no cabe."""
    ln, a, t, s = _Linea(mot), math.radians(mot.angulo_deg), GUARDA_T, RENDIJA
    h, b = d["h_eje"], mot.tensado_mm
    ui, uf = mot.r_envolvente + HOLGURA_GIRA, mot.r_envolvente + HOLGURA_GIRA + t + s
    z_b = mot.z_base
    z_fb = mot.z + mot.eje_d / 2.0 + HOLGURA_GIRA + MONTAJE_MM * math.cos(a)
    z_ct = z_fb + (SOLAPE_ISO + b + MONTAJE_MM + 2.0) * math.cos(a)
    if z_ct + MONTAJE_MM * math.cos(a) + HOLGURA_GIRA > h - d["r_cadena"]:
        raise ValueError("la guarda de la transmisión no cabe entre el motor y las cadenas: usa "
                         "un rodillo de más Ø o un motorreductor más chico")
    z_k = z_ct + MONTAJE_MM * math.cos(a) + HOLGURA_GIRA
    # ---- cárter móvil
    (p0x0, p0x1), (p1x0, p1x1) = mot.pies
    c_izq, c_izq_ext = tira(_extremo_carter(ln, -ui, z_b, z_ct, p0x0 - HOLGURA_PIE, -1.0), t, -1.0)
    c_der, c_der_ext = tira(_extremo_carter(ln, ui, z_b, z_ct, p1x1 + HOLGURA_PIE, 1.0), t, 1.0)
    yi1 = mot.y_cubo - HOLGURA_GIRA
    yo1 = d["y_in_p"] - t - s
    if yo1 > d["y_in_p"] - OREJA_T - 1.0:
        raise ValueError("el cárter choca con las orejas del portamotor")
    contorno = _contorno(c_izq_ext, c_der_ext, z_ct)
    interior = list(contorno)
    if mot.pies_y1 > yi1 - t - HOLGURA_PIE:  # las patas del motor cruzan la pared: muescas
        zt = mot.pies_z + HOLGURA_PIE        # en el borde de abajo, que se recorre hacia −X
        for x0, x1 in sorted(mot.pies, reverse=True):
            interior += [(x1 + HOLGURA_PIE, z_b), (x1 + HOLGURA_PIE, zt), (x0 - HOLGURA_PIE, zt),
                         (x0 - HOLGURA_PIE, z_b)]
    carter = {
        "base": {"x0": c_izq_ext[0][0], "x1": c_der_ext[0][0], "y0": mot.y_base0, "y1": yo1,
                 "z1": z_b},
        "pared_int": {"puntos": _r(interior), "y0": yi1 - t, "y1": yi1,
                      "eje": (mot.x, mot.z, mot.eje_d + 2.0 * HOLGURA_PIE)},
        "pared_ext": {"puntos": _r(contorno), "y0": yo1 - t, "y1": yo1},
        "extremos": [{"puntos": _r(p), "y0": yi1, "y1": yo1 - t} for p in (c_izq, c_der)],
        "z_tope": z_ct,
    }
    # ---- guarda fija
    x_ult, largo = d["x_ultimo"], d["largo"]
    z_vtop = d["z_bandeja"] - 1.0
    if z_vtop <= z_k:
        raise ValueError("la guarda de la transmisión no cabe bajo la bandeja de cadenas")
    x_iz = ln.x(-uf, z_k)
    f_izq, f_izq_ext = tira([(ln.x(-uf, z_fb), z_fb), (x_iz, z_k), (x_iz, z_vtop)], t, -1.0)
    x1 = ln.x(uf, z_k)
    x_min = x_ult + d["r_cadena"] + HOLGURA_GIRA  # libra la cadena del último piñón
    x_e = min(max(x1, x_min), largo - t - 0.5)  # dentro del bastidor
    if x_e < x_min:
        raise ValueError("el extremo de la guarda de la transmisión no cabe tras el último "
                         "piñón: alarga el bastidor")
    der = [(ln.x(uf, z_fb), z_fb), (x1, z_k)]
    if abs(x_e - x1) > 1e-6:
        der.append((x_e, z_k + abs(x1 - x_e)))  # pliegue a 45° hasta la vertical del extremo
    der.append((x_e, d["z_pestana"] - 0.5))
    f_der, f_der_ext = tira(der, t, 1.0)
    fi1 = yi1 - t - s
    z_int = h - d["d_rodillo"] / 2.0 - BAJO_TUBO
    z_ext, z_perno = tope_atornillado(d)
    ext_o = _contorno(f_izq_ext, cortar(f_der_ext, z_ext), z_ext)
    x_l0, x_l1 = f_izq_ext[-1][0], cortar(f_der_ext, z_ext)[-1][0]
    y_n, z_n = d["y_pestana"] + 0.5, d["z_pestana"] - 0.5
    fija = {
        "pared_int": {"puntos": _r(_contorno(f_izq_ext, cortar(f_der_ext, z_int), z_int)),
                      "y0": fi1 - t, "y1": fi1},
        "pared_ext": {"puntos": _r(ext_o), "y0": d["y_in_p"] - t, "y1": d["y_in_p"],
                      "pernos": [(x_l0 + 20.0, z_perno), (x_l1 - 20.0, z_perno)]},
        "extremos": [{"puntos": _r(p), "y0": fi1, "y1": d["y_in_p"] - t} for p in (f_izq, f_der)],
        # cierra el final del bastidor sobre el extremo +X, hasta la guarda de cadenas (deja
        # pasar la pestaña interior de ésta)
        "tapa": {"x0": x_e, "x1": x_e + t,
                 "puntos": [[y_n, z_n], [d["y_in_p"] - t, z_n], [d["y_in_p"] - t, d["z_guarda"] - 0.5],
                            [y_n, d["z_guarda"] - 0.5]]},
        "x_izq": x_l0, "z_base": z_fb, "z_k": z_k,
    }
    return {"carter": carter, "fija": fija}


def bandeja(d: dict, x_fin: float, y0: float) -> dict:
    """Perfil en C bajo los lazos, de `X_INICIO` a `x_fin` en tramos iguales de ≤ `TRAMO_MAX`,
    y la tapa del extremo de alimentación (soldada al primer tramo) hasta la guarda de cadenas.
    `d`: el de `guarda_transmision`."""
    h, t = d["h_eje"], GUARDA_T
    z0 = h - d["r_cadena"] - BAJO_CADENA - t
    largo = x_fin - X_INICIO
    n = max(1, math.ceil(largo / TRAMO_MAX - 1e-9))
    lt = (largo - (n - 1) * SEPARACION_TRAMOS) / n
    alto_int = h - d["d_rodillo"] / 2.0 - BAJO_TUBO - z0 - t
    if alto_int < 3.0:  # los tubos bajan hasta la bandeja: sin pestaña, el borde bajo su extremo
        alto_int, y0 = None, d["a2"] + 0.5
    tramos = [(X_INICIO + k * (lt + SEPARACION_TRAMOS), X_INICIO + k * (lt + SEPARACION_TRAMOS) + lt)
              for k in range(n)]
    c = 3.0  # chaflán: libra el radio de los pliegues
    y_a, y_b, z_a = y0 + t, d["y_in_p"] - t, z0 + t
    y_n, z_n, z_top = d["y_pestana"] + 0.5, d["z_pestana"] - 0.5, d["z_guarda"] - 0.5
    tope, z_perno = tope_atornillado(d)
    arriba = ([[y_n, z_top], [y_n, z_n], [y_a, z_n]] if y_n > y_a else [[y_a, z_top]])
    return {
        "tramos": tramos, "y0": y0, "y1": d["y_in_p"], "z0": z0,
        "alto_int": alto_int,
        "alto_ext": tope - z0 - t, "v_perno": V_PERNO, "z_perno": z_perno,
        # hasta la guarda de cadenas, con la muesca por donde baja su pestaña interior
        "tapa": {"x0": X_INICIO, "x1": X_INICIO + t,
                 "puntos": [[y_a + c, z_a], [y_b - c, z_a], [y_b, z_a + c], [y_b, z_top], *arriba,
                            [y_a, z_a + c]]},
    }
