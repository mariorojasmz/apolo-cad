"""Builders de TRANSMISIÓN POR CADENA del catálogo: piñones (ISO 606 / ANSI B29.1) y cadena de
rodillos recta, más la geometría de eslabón que usa el comando de cadena (plan
`docs/plans/cadenas-pinones.md`, D5).

Módulo propio porque `builders.py` está congelado por el trinquete de tamaño; `loader.py` une
este registro (y el de anclas, `ANCLAS`) con los demás y rechaza un nombre repetido. Mismo
contrato que allá: cada builder es una *factory* `(**params) -> ((length|None) -> shape)`. La
matemática (d0, forma del diente, capas de la cadena) vive en `transmision.py`, que es pura.

MARCO CANÓNICO del piñón (`sprocket`), el que fija `position` en `insert_component`:

- Eje del piñón = +Z; ORIGEN sobre el eje, en el plano medio de la hilera 1.
- El cubo sale hacia −Z: el piñón ocupa z ∈ [ancho_diente/2 − largo, ancho_diente/2] (o hasta
  el fondo de la hilera 2, si queda más abajo).
- Un ASIENTO de diente centrado en +X: el centro del asiento (punto de paso) está en
  (d0/2, 0, 0). Los asientos siguen cada 360°/z.
- Dos hileras (dúplex, a `distancia_hileras` = pt; doble-simple, a la distancia entre sus dos
  placas): la hilera 2 tiene su plano medio en z = −distancia_hileras.
- Anclas (`ANCLAS["sprocket"]`): `eje` y `hilera_1` en el origen, `hilera_2` en
  (0, 0, −distancia_hileras), `fase` en el centro del asiento de +X; todas con eje +Z.

Qué es REAL y qué REPRESENTATIVO: d0, de, fondo (df = d0 − d1 nominal), ancho de diente, cubo,
largo, piloto y distancia entre hileras son los de la ficha. Los flancos son la forma MÁXIMA de
ISO 606 (ri mín, re máx, α máx: `transmision.forma_diente`): representativos. Entre hileras va
el cubo; su Ø deja pasar las placas de la cadena en todo el catálogo salvo en la 40B12 y la 08B
z9, cuyo cubo PUBLICADO es mayor (lo declaran en `no_publicado`). Sin
chaflán de diente, chavetero ni prisionero (el piloto se maquina en taller). Un solo sólido; el
3D reproduce los pesos publicados con ±5 %.

MARCO DE LA CADENA (`roller_chain`, `cadena_por_rodillos`, `cadena_bandas`): rodillos centrados en puntos (x, y)
del plano XY, pernos paralelos a Z, hilera 1 en z = 0 y hilera 2 en z = −pt (las capas, de
`transmision.capas_cadena`): una cadena cuyos centros son los de `transmision.rodillos_del_lazo`
cae sobre las hileras de dos piñones colocados en ese marco.
"""

from __future__ import annotations

import math

from build123d import (
    Compound, Cylinder, Edge, Face, Kind, Pos, Rotation, SlotCenterToCenter, Vector, Wire,
    extrude,
)

from apolo.kernel.shapes import make_revolution

from .transmision import capas_cadena, diametro_primitivo, forma_diente

#: Tipos de piñón que entiende `sprocket`.
TIPOS_PINON = ("simple", "duplex", "doble_simple")

_SOLAPE = 0.5   # solape (mm) entre el cubo y la placa dentada: ni tangentes ni disjuntos


# ------------------------------------------------------------------ perfil del diente
def _rot(p, a):
    c, s = math.cos(a), math.sin(a)
    return (c * p[0] - s * p[1], s * p[0] + c * p[1])


def _interseccion_circulos(c1, r1, c2, r2):
    """Los dos puntos donde se cortan dos circunferencias (o ValueError si no se cortan)."""
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    d = math.hypot(dx, dy)
    if d > r1 + r2 or d < abs(r1 - r2) or d == 0:
        raise ValueError("Circunferencias sin intersección")
    a = (r1 * r1 - r2 * r2 + d * d) / (2.0 * d)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    mx, my = c1[0] + a * dx / d, c1[1] + a * dy / d
    return (mx + h * dy / d, my - h * dx / d), (mx - h * dy / d, my + h * dx / d)


def geometria_diente(paso: float, z: int, rodillo: float, de: float) -> dict:
    """Puntos de UN hueco de diente centrado en +X (marco canónico), lado +Y; el lado −Y es su
    espejo. Devuelve `R` (radio primitivo), `ri`, `re`, el extremo del asiento `q`, el centro del
    flanco `ce`, la punta del flanco sobre el círculo exterior `t` y `media_punta` (rad, semiancho
    angular de la cresta). ValueError si el diente queda en punta antes de llegar a `de`."""
    R = diametro_primitivo(paso, z) / 2.0
    f = forma_diente(z, rodillo)
    ri, re, alfa = f["ri"], f["re"], f["alfa"]
    ra = de / 2.0
    if not R < ra < R + paso:
        raise ValueError(f"Piñón z{z}: Ø exterior {de} fuera de rango para d0 = {2 * R:.2f}")
    u = (-math.cos(alfa / 2.0), math.sin(alfa / 2.0))   # del punto de paso al extremo del asiento
    q = (R + ri * u[0], ri * u[1])
    ce = (R + (ri + re) * u[0], (ri + re) * u[1])        # flanco convexo, tangente exterior al asiento
    cands = _interseccion_circulos((0.0, 0.0), ra, ce, re)
    # la punta del flanco: la intersección más cercana al asiento, del lado +Y
    t = min((c for c in cands if c[1] > 0), key=lambda c: math.dist(c, q), default=None)
    if t is None:
        raise ValueError(f"Piñón z{z}: el flanco no llega al Ø exterior {de}")
    media_punta = math.pi / z - math.atan2(t[1], t[0])
    if media_punta <= 0.0:
        raise ValueError(
            f"Piñón z{z}: con Ø exterior {de} el diente queda en punta (reduce de)"
        )
    return {"R": R, "ri": ri, "re": re, "q": q, "ce": ce, "t": t, "media_punta": media_punta}


def _arco(p0, p1, centro, r) -> Edge:
    """Arco CORTO (< 180°) de p0 a p1 sobre la circunferencia (centro, r)."""
    a0 = math.atan2(p0[1] - centro[1], p0[0] - centro[0])
    a1 = math.atan2(p1[1] - centro[1], p1[0] - centro[0])
    da = (a1 - a0 + math.pi) % (2.0 * math.pi) - math.pi
    am = a0 + da / 2.0
    pm = (centro[0] + r * math.cos(am), centro[1] + r * math.sin(am))
    return Edge.make_three_point_arc(Vector(*p0, 0), Vector(*pm, 0), Vector(*p1, 0))


def perfil_dentado(paso: float, z: int, rodillo: float, de: float) -> Face:
    """Cara plana (z = 0) del contorno dentado completo, con un asiento centrado en +X: por
    hueco, arco de asiento (ri) + dos flancos (re) y, entre huecos, la cresta sobre Ø `de`.
    Un solo contorno de 4·z aristas: extruirlo cuesta una operación, no z booleanas."""
    g = geometria_diente(paso, z, rodillo, de)
    R, ri, re = g["R"], g["ri"], g["re"]
    q, ce, t = g["q"], g["ce"], g["t"]
    qm, cem, tm = (q[0], -q[1]), (ce[0], -ce[1]), (t[0], -t[1])
    ang = 2.0 * math.pi / z
    aristas = []
    for k in range(z):
        a = k * ang
        # sentido antihorario: flanco −Y (de la punta al asiento), asiento, flanco +Y, cresta
        aristas.append(_arco(_rot(tm, a), _rot(qm, a), _rot(cem, a), re))
        aristas.append(_arco(_rot(qm, a), _rot(q, a), _rot((R, 0.0), a), ri))
        aristas.append(_arco(_rot(q, a), _rot(t, a), _rot(ce, a), re))
        aristas.append(_arco(_rot(t, a), _rot(tm, a + ang), (0.0, 0.0), de / 2.0))
    return Face(Wire(aristas))


# ------------------------------------------------------------------ piñón
def _validar_pinon(tipo, paso, z, rodillo, de, ancho_diente, cubo, largo, piloto_mm,
                   distancia_hileras) -> dict:
    """Rechaza combinaciones imposibles con un mensaje que dice qué corregir (un YAML malo
    falla al CARGAR el catálogo). Devuelve la geometría del diente."""
    if tipo not in TIPOS_PINON:
        raise ValueError(f"Piñón: tipo desconocido '{tipo}'; usa uno de {', '.join(TIPOS_PINON)}")
    for nombre, valor in {"paso": paso, "rodillo": rodillo, "de": de, "ancho_diente": ancho_diente,
                          "largo": largo, "piloto_mm": piloto_mm}.items():
        if not valor > 0:
            raise ValueError(f"Piñón: {nombre} debe ser > 0 (vale {valor})")
    if rodillo >= paso:
        raise ValueError(f"Piñón: rodillo {rodillo} ≥ paso {paso}")
    g = geometria_diente(paso, z, rodillo, de)
    df = 2.0 * (g["R"] - g["ri"])
    if cubo >= df:
        raise ValueError(f"Piñón z{z}: cubo Ø{cubo} ≥ fondo del diente Ø{df:.2f} (taparía los dientes)")
    if piloto_mm >= (cubo if cubo > 0 else df) - 2.0:
        raise ValueError(f"Piñón z{z}: piloto Ø{piloto_mm} no deja pared al cubo Ø{cubo}")
    if largo < ancho_diente:
        raise ValueError(f"Piñón z{z}: largo {largo} < ancho de diente {ancho_diente}")
    if tipo == "simple":
        if distancia_hileras:
            raise ValueError("Piñón simple con distancia_hileras: sólo dúplex y doble-simple la llevan")
    else:
        if distancia_hileras <= ancho_diente:
            raise ValueError(
                f"Piñón {tipo}: distancia entre hileras {distancia_hileras} ≤ ancho de diente {ancho_diente}"
            )
        if cubo <= 0 or largo < distancia_hileras:
            raise ValueError(f"Piñón {tipo}: el cubo (Ø{cubo}, largo {largo}) no une las dos hileras")
    return g


def sprocket(tipo: str, paso: float, z: int, rodillo: float, de: float, ancho_diente: float,
             cubo: float, largo: float, piloto_mm: float, distancia_hileras: float = 0.0):
    """Piñón para cadena de rodillos, UN sólido (mm).

    `tipo` ∈ {"simple" (una hilera con cubo, tipo B), "duplex" (dos hileras a `distancia_hileras`
    = pt, para cadena doble), "doble_simple" (dos placas simples a `distancia_hileras`, un cubo:
    dos cadenas simples, el rodillo a rodillo)}. `paso` y `rodillo` (d1) son los de la cadena; `z`
    dientes; `de` Ø exterior de la ficha; `ancho_diente` por hilera; `cubo` Ø del cubo; `largo` =
    largo total sobre el agujero; `piloto_mm` = agujero piloto (a maquinar con chaveta y
    prisionero).

    MARCO CANÓNICO (ver el docstring del módulo): eje +Z, origen en el plano medio de la hilera
    1, cubo hacia −Z, asiento centrado en +X; hilera 2 en z = −distancia_hileras.
    """
    _validar_pinon(tipo, paso, z, rodillo, de, ancho_diente, cubo, largo, piloto_mm,
                   distancia_hileras)
    filas = [0.0] if tipo == "simple" else [0.0, -float(distancia_hileras)]
    medio = ancho_diente / 2.0

    def build(_length=None):
        placa = extrude(perfil_dentado(paso, z, rodillo, de), amount=ancho_diente)
        partes = [Pos(0, 0, zf - medio) * placa for zf in filas]
        z_top, z_bot = medio - _SOLAPE, medio - largo
        if cubo > 0 and z_top - z_bot > 0:
            partes.append(Pos(0, 0, (z_top + z_bot) / 2.0) * Cylinder(cubo / 2.0, z_top - z_bot))
        z_min = min(z_bot, filas[-1] - medio)
        taladro = Pos(0, 0, (medio + z_min) / 2.0) * Cylinder(piloto_mm / 2.0, medio - z_min + 2.0)
        # un fuse y un cut con todas las herramientas (z booleanas sueltas cuestan z veces más)
        cuerpo = partes[0].fuse(*partes[1:]) if len(partes) > 1 else partes[0]
        cuerpo = cuerpo.cut(taladro)
        if not hasattr(cuerpo, "volume") or len(cuerpo.solids()) != 1:
            raise RuntimeError(f"Piñón z{z}: las partes no quedaron unidas en un solo sólido")
        return cuerpo

    return build


def anclas_pinon(tipo: str, paso: float, z: int, distancia_hileras: float = 0.0, **_otros) -> dict:
    """Anclas LOCALES del piñón (marco canónico), calculadas desde sus params (plan D6):
    `eje` y `hilera_1` en el origen; `hilera_2` (dúplex y doble-simple) en z = −distancia_hileras;
    `fase` en el centro del asiento de +X, a radio d0/2 (su ángulo da el de los dientes). Todas
    con eje +Z (el del piñón)."""
    eje = [0.0, 0.0, 1.0]
    out = {
        "eje": {"origin": [0.0, 0.0, 0.0], "axis": list(eje)},
        "hilera_1": {"origin": [0.0, 0.0, 0.0], "axis": list(eje)},
        "fase": {"origin": [diametro_primitivo(paso, z) / 2.0, 0.0, 0.0], "axis": list(eje)},
    }
    if tipo != "simple":
        out["hilera_2"] = {"origin": [0.0, 0.0, -float(distancia_hileras)], "axis": list(eje)}
    return out


# ------------------------------------------------------------------ cadena
def placa_eslabon(c0, c1, alto: float, z0: float, z1: float):
    """Placa de eslabón en ESTADIO entre dos centros de rodillo (x, y) cualesquiera (no
    necesariamente a un paso: el tramo de un lazo puede quedar estirado), de z0 a z1."""
    dx, dy = c1[0] - c0[0], c1[1] - c0[1]
    largo = math.hypot(dx, dy)
    perfil = SlotCenterToCenter(largo, alto, rotation=math.degrees(math.atan2(dy, dx)))
    return Pos((c0[0] + c1[0]) / 2.0, (c0[1] + c1[1]) / 2.0, z0) * extrude(perfil, amount=z1 - z0)


def rodillo_y_perno(c, rodillo: float, perno: float, capas: dict):
    """Perno (de lado a lado, ancho sobre perno) con su rodillo en cada hilera, como UN sólido
    de revolución centrado en (x, y) = c, eje Z."""
    zp0, zp1 = capas["perno"]
    rp, rr = perno / 2.0, rodillo / 2.0
    perfil = [(0.0, zp0), (rp, zp0)]
    for z0, z1 in sorted(capas["rodillos"]):
        perfil += [(rp, z0), (rr, z0), (rr, z1), (rp, z1)]
    perfil += [(rp, zp1), (0.0, zp1)]
    return Pos(c[0], c[1], 0) * make_revolution(perfil)


def cadena_por_rodillos(centros, cerrada: bool, rodillo: float, perno: float, alto_placa: float,
                        capas: dict, unir: bool = True):
    """Cadena que pasa por los centros de rodillo dados (x, y), en orden; placas interiores en los
    pares (0,1), (2,3)… y exteriores en (1,2), (3,4)… (y (n−1, 0) si `cerrada`: n debe ser PAR).
    `capas` = `transmision.capas_cadena(...)`. `unir=True` funde todo en UN sólido (el perno
    atraviesa rodillo y placas: solapan); `False` devuelve un Compound de piezas sueltas."""
    n = len(centros)
    if cerrada and n % 2:
        raise ValueError(f"Lazo cerrado con {n} eslabones: debe ser PAR (impar exige eslabón acodado)")
    # plantillas: UN rodillo y UNA placa por (tipo, largo); cada pieza es una copia colocada
    # (comparte la geometría: crear 400 primitivas costaba más que fundirlas)
    rod = rodillo_y_perno((0.0, 0.0), rodillo, perno, capas)
    piezas = [Pos(c[0], c[1], 0) * rod for c in centros]
    plantillas: dict = {}
    for i in range(n if cerrada else n - 1):
        c0, c1 = centros[i], centros[(i + 1) % n]
        largo = math.dist(c0, c1)
        tipo = "interiores" if i % 2 == 0 else "exteriores"
        clave = (tipo, round(largo, 6))
        if clave not in plantillas:
            plantillas[clave] = [placa_eslabon((0.0, 0.0), (largo, 0.0), alto_placa, z0, z1)
                                 for z0, z1 in capas[tipo]]
        giro = math.degrees(math.atan2(c1[1] - c0[1], c1[0] - c0[0]))
        piezas += [Pos(c0[0], c0[1], 0) * Rotation(0, 0, giro) * pl for pl in plantillas[clave]]
    if not unir:
        return Compound(piezas)
    cuerpo = piezas[0].fuse(*piezas[1:])
    if not hasattr(cuerpo, "volume") or len(cuerpo.solids()) != 1:
        raise RuntimeError("Cadena: las piezas no quedaron unidas en un solo sólido")
    return cuerpo


def cadena_bandas(centros, alto_placa: float, capas: dict):
    """Lazo CERRADO en detalle «simple»: las bandas que envuelven las placas de los eslabones,
    una por cada lado de cada hilera de dientes (en dúplex, la del medio es una sola), sin
    rodillos ni pernos. Cada banda = el polígono de los centros de rodillo desplazado ±alto/2
    (esquinas en arco: el extremo en estadio de las placas) y extruido en el ancho que ocupan
    las placas de ese lado. El hueco de los dientes (entre placas interiores) queda libre, así
    que no cruza el piñón: por construcción, lo mismo que las placas del detalle «eslabones».
    Devuelve un Compound de bandas (disjuntas)."""
    planos = sorted(capas["interiores"] + capas["exteriores"])
    lo, hi = planos[0][0], max(z1 for _z0, z1 in planos)
    inter = sorted(capas["interiores"])
    huecos = [(inter[i][1], inter[i + 1][0]) for i in range(0, len(inter), 2)]  # entre placas
    tramos, z0 = [], lo
    for h0, h1 in sorted(huecos):
        tramos.append((z0, h0))
        z0 = h1
    tramos.append((z0, hi))
    poligono = Wire.make_polygon([Vector(x, y, 0) for x, y in centros], close=True)
    cara = Face(poligono.offset_2d(alto_placa / 2.0, kind=Kind.ARC),
                [poligono.offset_2d(-alto_placa / 2.0, kind=Kind.ARC)])
    return Compound([Pos(0, 0, a) * extrude(cara, amount=b - a) for a, b in tramos if b - a > 0])


def roller_chain(paso: float, rodillo: float, ancho_interior: float, perno: float,
                 alto_placa: float, espesor_placa: float, ancho_sobre_perno: float,
                 hileras: int = 1, pt: float = 0.0):
    """Tramo RECTO de cadena de rodillos, cortable (`length` = largo de corte, mm). Lleva
    round(length/paso) rodillos a lo largo de X, centrados en x = 0; pernos paralelos a Z; plano
    medio de la hilera 1 en z = 0 y la hilera 2 (cadena doble) en z = −pt: el marco de las
    hileras del piñón. Es la geometría de `insert_component`; el lazo entre dos piñones lo arma
    el comando de cadena con `cadena_por_rodillos`."""
    capas = capas_cadena(ancho_interior, espesor_placa, ancho_sobre_perno, hileras, pt)

    def build(length):
        n = max(2, round(float(length) / paso))
        xs = [(i - (n - 1) / 2.0) * paso for i in range(n)]
        return cadena_por_rodillos([(x, 0.0) for x in xs], False, rodillo, perno, alto_placa, capas)

    return build


BUILDERS = {
    "sprocket": sprocket,          # piñón ISO 606 / ANSI B29.1: simple, dúplex, doble-simple
    "roller_chain": roller_chain,  # tramo recto de cadena de rodillos (cortable)
}

#: Anclas por FAMILIA calculadas desde los params del builder (plan cadenas-pinones D6). El
#: loader las une con las de los demás módulos (nombre repetido = error) y las guarda en el
#: `Component`; `catalog.component_anchors` las suma a las de categoría.
ANCLAS = {
    "sprocket": anclas_pinon,
}
