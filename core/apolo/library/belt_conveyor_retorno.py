"""Rodillos de retorno y pernos pasantes de `create_belt_conveyor` (v6, criterio 6; plan
faja-larga-en-tramos D3 y D4).

**Rodillos de retorno (D3).** Sin apoyo, el ramal de retorno cuelga entre los dos tambores en
catenaria y roza lo que tiene debajo. Cuando el tramo libre (de tambor a tambor: `largo`) pasa
`PASO_RETORNO`, la faja lleva rodillos de catálogo bajo el ramal de retorno, espaciados
≤ `PASO_RETORNO`. Fuente del 3 m: Martin Engineering, *Foundations* (§ «Belt conveyor idler
spacing»), que remite a las tablas de espaciamiento sugerido de CEMA (*Belt Conveyors for Bulk
Materials*): los rodillos de retorno no llevan carga y se espacian típicamente a 3 m (10 ft).
Es FUENTE SECUNDARIA: la tabla de CEMA no se verificó contra el libro.

- El rodillo es el más chico del catálogo `rodillos` cuya capacidad de ficha es ≥ 2 × el peso de
  la banda en un vano (`elegir_rodillo`); su tubo cubre la banda y sus muñones entran en dos
  soportes de chapa ATORNILLADOS a la cara interior de los largueros (un rodillo se cambia
  aflojando un soporte).
- Su cara superior queda a `HOLGURA_RETORNO` del ramal de retorno: la ruta de la banda
  (`ruta_faja*.py`) lo cuenta como APOYO POR AFUERA (≤ 1 mm de la cara exterior) y el lazo, el
  abrazamiento de los tambores y la comba entre apoyos siguen coherentes (la banda no se desvía).
- Van entre las guardas de los tambores, lejos de las patas, de las placas de empalme y de los
  soportes de la cama (en el medio entre dos soportes), y la guarda inferior se corta en cada uno.
- La cuña rodillo ↔ banda es peligro (la puerta la sondea como la de un tambor: medido en la de
  4 m, 17 sondas llegaban desde abajo): con guardas, cajón de chapa bajo el rodillo con alas a
  `HOLGURA_GUARDA` del ramal que llegan `ALCANCE` más allá (`_guarda`), y el muñón entra en un
  alojamiento CIEGO del soporte (por el barreno pasante una sonda tocaba la punta del eje).

**Pernos pasantes con buje (D4).** Un larguero es un tubo CERRADO: un perno a su cara interior
deja la tuerca adentro, sin acceso de llave. El catálogo no tiene remache-tuerca (sólo remaches
ciegos ≤ Ø6,4, `112_fijacion_ciega.yaml`) y un remache no se desarma: la placa del soporte de la
cama y el soporte del rodillo tienen que soltarse para cambiar la banda. Solución: perno M8
PASANTE que cruza el tubo de lado a lado, tuerca por la cara exterior, con un BUJE soldado dentro
del larguero (tubo Ø`BUJE_D` por los dos barrenos, soldado en las dos caras al fabricar el
larguero). La cuenta pide el buje: la precarga de apriete del M8 8.8 es 0,7·A_s·R_y =
0,7 × 36,6 × 640 ≈ 16,4 kN (`bolts.tightening_torque_nm`) y el alma de 4,8 mm del TUBO-4X2
(A500 Gr.B, f_y = 317 MPa) aguanta una carga concentrada de ≈ 2π·m_p = 2π·f_y·t²/4 ≈ 11,5 kN
(líneas de rotura, cota inferior; criterio de diseño): sin buje el apriete aplasta el tubo.
"""

from __future__ import annotations

import math

from .belt_conveyor_cotas import LEG_W, PLACA_SOPORTE_T, Cotas
from .belt_conveyor_plan import Plan, caja, cilindro_y
from .catalog import CATALOG, build_component, refs_in_category

PASO_RETORNO = 3000.0    # espaciamiento máximo de los rodillos de retorno (ver el docstring)
HOLGURA_RETORNO = 0.5    # de la cara superior del rodillo a la cara inferior del ramal de retorno
SOPORTE_RET_T = 8.0      # chapa del soporte del rodillo de retorno
ALOJAMIENTO = 5.0        # alojamiento CIEGO del muñón (fresado desde la cara interior): la punta
#                          del eje que gira no asoma por fuera (la sonda la tocaba por el barreno)
SOPORTE_RET_W = 50.0     # su ancho a lo largo de X
PERNO_PASANTE = "M8"
BUJE_D = 14.0            # Ø exterior del buje soldado dentro del larguero
FS_RODILLO = 2.0         # capacidad de ficha ≥ 2 × el peso de banda que carga
CHAPA_GUARDA = 3.0       # guarda del rodillo de retorno
JUEGO_GUARDA = 5.0       # del rodillo a las paredes de su guarda
HOLGURA_GUARDA = 15.0    # de las alas de la guarda al ramal de retorno (ranura ≤ 20: ISO 13857)
BAJO_TALLER = 35.0       # criterio 8: el soporte baja hasta 35 mm bajo el eje (los M6 de la guarda)
SEPARACION_SOPORTES = 2 * 30.0 + SOPORTE_RET_W + 2 * 10.0  # el rodillo entre dos soportes de cama


def media_huella(c: Cotas) -> float:
    """Medio largo en X del hueco de la guarda inferior en un rodillo: su soporte, con 1 mm de
    juego (las paredes de la guarda del rodillo no salen del ancho de la banda: pasan bajo el
    ala de la guarda inferior, que sigue tapando la ranura hasta el soporte)."""
    return SOPORTE_RET_W / 2.0 + 1.0


def alcance_guarda(c: Cotas) -> float:
    """Medio largo en X de la guarda de un rodillo, alas incluidas."""
    from .belt_conveyor_guardas import ALCANCE

    r = float(CATALOG[elegir_rodillo(c)].specs["diametro_mm"]) / 2.0
    return r + JUEGO_GUARDA + CHAPA_GUARDA + ALCANCE


def con_criterio(c: Cotas) -> bool:
    return c.criterio >= 6


def agujero_perno() -> float:
    from .engineering.bolts import clearance_hole_mm

    return float(clearance_hole_mm(PERNO_PASANTE))


def nota_pasante(c: Cotas, que: str, espesor: float = PLACA_SOPORTE_T) -> str:
    from .fijacion import largo_perno

    largo = largo_perno(PERNO_PASANTE, espesor + c.rail_t, estricto=True)
    return (f"{que}: perno pasante {PERNO_PASANTE}x{largo:g} DIN 933 + tuerca, cruza el larguero "
            f"por un buje soldado (Ø{BUJE_D:g}: el tubo no se aplasta al apretar) y se aprieta por "
            "la cara exterior")


def limites_buje(c: Cotas) -> tuple[float, float]:
    """(z mín, z máx) del eje de un perno pasante: el buje entero dentro del hueco del tubo."""
    return (c.rail_bot + c.wall + BUJE_D / 2.0 + 1.0, c.rail_top - c.wall - BUJE_D / 2.0 - 1.0)


def bujes(forma, c: Cotas, lado: float, pernos):
    """El tubo del larguero con un buje soldado y su barreno en cada perno pasante (x, z)."""
    if not pernos:
        return forma
    d0 = agujero_perno()
    # (x, z) = el M8 de siempre; (x, z, Ø del agujero, Ø del buje): los del criterio 8 (F1c)
    pts = [p if len(p) == 4 else (p[0], p[1], d0, BUJE_D) for p in pernos]
    y0, y1 = lado * c.y_in, lado * c.y_out
    if c.criterio >= 8:  # F1c: muchos más pernos; en dos booleanas (misma forma, más rápido)
        from .belt_conveyor_taller import cortar, unir

        forma = unir(forma, [cilindro_y(x, z, y0, y1, b / 2.0) for x, z, _d, b in pts])
        return cortar(forma, [cilindro_y(x, z, y0 - lado, y1 + lado, d / 2.0)
                              for x, z, d, _b in pts])
    for x, z, _d, buje in pts:
        forma = forma + cilindro_y(x, z, y0, y1, buje / 2.0)
    for x, z, d, _b in pts:
        forma = forma - cilindro_y(x, z, y0 - lado, y1 + lado, d / 2.0)
    return forma


def taladrar(forma, c: Cotas, lado: float, pernos, espesor: float):
    """La placa (a ras de la cara interior del larguero) con el barreno de cada perno pasante."""
    d0 = agujero_perno()
    for x, z in pernos:
        forma = forma - cilindro_y(x, z, lado * (c.y_in - espesor - 1.0), lado * (c.y_in + 1.0),
                                   d0 / 2.0)
    return forma


def elegir_rodillo(c: Cotas) -> str:
    """El rodillo más chico cuya capacidad de ficha es ≥ `FS_RODILLO` × el peso de la banda (PVC,
    su rol) en un vano de `PASO_RETORNO`."""
    from .materials import density

    carga = density("pvc") * c.t * c.ancho * PASO_RETORNO
    refs = sorted(refs_in_category("rodillos"), key=lambda r: float(CATALOG[r].specs["diametro_mm"]))
    for ref in refs:
        if float(CATALOG[ref].specs.get("capacidad_kg") or 0.0) >= FS_RODILLO * carga:
            return ref
    raise ValueError(f"ningún rodillo del catálogo carga {FS_RODILLO:g} × {carga:.1f} kg de banda "
                     "por vano de retorno")


def z_eje_rodillo(c: Cotas, x: float, r: float) -> float:
    """Z del eje de un rodillo de radio `r` en `x` que queda a `HOLGURA_RETORNO` de la cara
    exterior del ramal de retorno: la tangente exterior de abajo de los dos tambores (radio
    exterior + banda), que va inclinada si el motriz está engomado y el de cola no."""
    x1, z1, r1 = -c.half, c.zc, c.r_c + c.t
    x2, z2, r2 = c.half, c.zm, c.r_m + c.t
    dist = math.hypot(x2 - x1, z2 - z1)
    beta = math.atan2(z2 - z1, x2 - x1) - math.acos((r1 - r2) / dist)  # normal hacia abajo
    a, b = math.cos(beta), math.sin(beta)
    d = a * x1 + b * z1 + r1
    return (d + r + HOLGURA_RETORNO - a * x) / b


def _geometria(c: Cotas, x: float):
    """(ref, forma, corte, z del eje, z de los pernos del soporte) del rodillo en `x`."""
    ref = elegir_rodillo(c)
    stub_probe = build_component(ref, 100.0)[0].bounding_box()
    stub = (stub_probe.size.Z - 100.0) / 2.0
    # el muñón entra en el alojamiento ciego del soporte y queda a 0,5 mm de su fondo
    largo = 2.0 * (c.y_in - SOPORTE_RET_T + ALOJAMIENTO - 0.5 - stub)
    forma, cut = build_component(ref, largo)
    z_eje = z_eje_rodillo(c, x, float(CATALOG[ref].specs["diametro_mm"]) / 2.0)
    lo, hi = limites_buje(c)
    z_perno = max(lo + 1.0, z_eje + 25.0)
    if z_perno > hi:
        raise ValueError(f"el tubo {c.tubo} no deja atornillar el soporte del rodillo de retorno "
                         "con perno pasante y buje")
    return ref, forma, cut, z_eje, z_perno


def x_rodillos(c: Cotas) -> list[float]:
    """X de los rodillos de retorno (vacío con el criterio de la v5 o si el ramal libre no pasa
    `PASO_RETORNO`). Candidatos: el medio entre dos soportes de la cama, entre las guardas de los
    tambores y lejos de patas y empalmes; de ellos, los más cercanos a un reparto parejo, o el
    voraz si el parejo deja un vano > `PASO_RETORNO`."""
    from .belt_conveyor_bastidor import estaciones, x_soportes
    from .belt_conveyor_guardas import x_de_tambor
    from .belt_conveyor_tramos import EMPALME_T

    if not con_criterio(c) or c.largo <= PASO_RETORNO + 1e-9:
        return []
    margen = alcance_guarda(c) + 20.0  # las alas de su guarda no llegan a las de los tambores
    xa = x_de_tambor(c, c.x_tc, c.r_c, -1.0, c.viaje)[0] + margen
    xb = x_de_tambor(c, c.half, c.r_m, 1.0, 0.0)[0] - margen
    sop = x_soportes(c)
    patas = estaciones(c)
    # entre dos soportes que dejan sitio (el par de una junta de la cama no: F1c, D13)
    cands = [(a + b) / 2.0 for a, b in zip(sop, sop[1:]) if b - a >= SEPARACION_SOPORTES]
    cands = [x for x in cands if xa < x < xb
             and all(abs(x - p) >= LEG_W / 2.0 + SOPORTE_RET_W / 2.0 + 10.0 for p in patas)
             and all(abs(x - s) >= EMPALME_T + SOPORTE_RET_W / 2.0 + 10.0 for s in c.empalmes)]
    n = math.ceil(c.largo / PASO_RETORNO - 1e-9) - 1

    def vanos_ok(xs):
        pts = [-c.half] + sorted(xs) + [c.half]
        return all(b - a <= PASO_RETORNO + 1e-6 for a, b in zip(pts, pts[1:]))

    for m in range(n, n + 3):  # el reparto parejo con el mínimo de rodillos que cumpla
        elegidos: list[float] = []
        for j in range(1, m + 1):
            meta = -c.half + j * c.largo / (m + 1)
            libres = [x for x in cands if x not in elegidos]
            if libres:
                elegidos.append(min(libres, key=lambda x: abs(x - meta)))
        if len(elegidos) == m and vanos_ok(elegidos):
            return sorted(elegidos)
    elegidos, pos = [], -c.half
    while c.half - pos > PASO_RETORNO + 1e-6:
        alcance = [x for x in cands if pos < x <= pos + PASO_RETORNO + 1e-6]
        if not alcance:
            raise ValueError(f"no hay dónde poner un rodillo de retorno a ≤ {PASO_RETORNO:g} mm "
                             f"del apoyo anterior (x = {pos:.0f})")
        pos = max(alcance)
        elegidos.append(pos)
    return elegidos


def pernos_soporte_ret(x: float, z_perno: float) -> list[tuple[float, float]]:
    return [(x - SOPORTE_RET_W / 4.0, z_perno), (x + SOPORTE_RET_W / 4.0, z_perno)]


def pasantes(c: Cotas, i: int) -> list[tuple[float, float]]:
    """(x, z) de cada perno pasante del larguero `i`: placas de los soportes de la cama y
    soportes de los rodillos de retorno (criterio 6; vacío antes)."""
    from .belt_conveyor_bastidor import pernos_soporte, x_soportes

    if not con_criterio(c):
        return []
    out = [p for x in x_soportes(c) for p in pernos_soporte(c, x)]
    out += [p for x in x_rodillos(c) for p in pernos_soporte_ret(x, _geometria(c, x)[4])]
    return out


def rodillos(plan: Plan, c: Cotas) -> None:
    """Los rodillos de retorno, cada uno con sus dos soportes atornillados a los largueros."""
    from .belt_conveyor_tramos import rail

    for k, x in enumerate(x_rodillos(c), start=1):
        ref, forma, cut, z_eje, z_perno = _geometria(c, x)
        d_eje = float(CATALOG[ref].specs["eje_mm"])
        suf = f"ret{k}"
        plan.pieza(suf, f"Rodillo de retorno ({k})", forma, comp=ref, cut=cut, pos=(x, 0.0, z_eje),
                   rot=(90, 0, 0), key=f"comp|{ref}|{cut}")
        taller = c.criterio >= 8 and c.guardas
        for i, lado, signo in ((1, -1.0, "−"), (2, 1.0, "+")):
            sop = f"{suf}_{'m' if lado < 0 else 'p'}"
            h = SOPORTE_RET_W / 2.0
            # F1c (D12): con el criterio 8 baja 10 mm más, para los M6 roscados de su guarda
            z_bajo = z_eje - (BAJO_TALLER if taller else 25.0)
            placa = caja(x - h, x + h, lado * (c.y_in - SOPORTE_RET_T), lado * c.y_in, z_bajo,
                         z_perno + 14.0)
            y_cara = c.y_in - SOPORTE_RET_T
            placa = placa - cilindro_y(x, z_eje, lado * (y_cara - 1.0),
                                       lado * (y_cara + ALOJAMIENTO), d_eje / 2.0 + 0.5)
            placa = taladrar(placa, c, lado, pernos_soporte_ret(x, z_perno), SOPORTE_RET_T)
            if taller:
                from .belt_conveyor_taller import broca, taladro_y

                for xg, zg in pernos_guarda_ret(x, z_eje):
                    placa = placa - taladro_y(xg, zg, lado * (y_cara - 1.0), lado * (c.y_in + 1.0),
                                              broca("M6"))
            plan.pieza(sop, f"Soporte del rodillo de retorno ({k}, {signo}Y)", placa,
                       material="acero")
            plan.union(f"{sop}_larg", sop, rail(c, i, x), "perno",
                       nota_pasante(c, "soporte del rodillo atornillado al larguero",
                                    SOPORTE_RET_T), size=PERNO_PASANTE, qty=2)
            plan.union(f"{sop}_eje", suf, sop, "contacto",
                       "muñón del rodillo en el barreno del soporte (se cambia aflojando un soporte)")
        if c.guardas:
            _guarda(plan, c, k, x, z_eje, float(CATALOG[ref].specs["diametro_mm"]) / 2.0, d_eje)


def _guarda(plan: Plan, c: Cotas, k: int, x: float, z_eje: float, r: float, d_eje: float) -> None:
    """Guarda de la cuña rodillo ↔ banda (ISO 13857; la puerta la sondea como la de un tambor):
    cajón de chapa bajo el rodillo, entre sus dos soportes, con alas a `HOLGURA_GUARDA` bajo el
    ramal de retorno que llegan `ALCANCE` más allá de las paredes (como la bandeja de las guardas
    de los tambores): por la ranura ≤ 20 mm no se llega a la cuña. Atornillada a los soportes del
    rodillo por dos mejillas bajo los muñones."""
    from .belt_conveyor_guardas import ALCANCE

    e = CHAPA_GUARDA
    xw = r + JUEGO_GUARDA
    z_ala = z_eje + r + HOLGURA_RETORNO - HOLGURA_GUARDA       # cara superior de las alas
    z_fondo = z_eje - r - 10.0 - e
    yc = c.y_in - SOPORTE_RET_T                                 # a ras de los soportes
    yb = c.ancho / 2.0
    forma = caja(x - xw - e, x + xw + e, -yc, yc, z_fondo, z_fondo + e)        # fondo
    for sx in (-1.0, 1.0):  # paredes en el ancho de la banda: fuera de él tapa la guarda inferior
        forma = forma + caja(x + sx * xw, x + sx * (xw + e), -yb - 0.5, yb + 0.5, z_fondo, z_ala)
        if c.criterio >= 9 and c.cierres:
            # faja-compacta (D6): fuera del ancho de la banda, la pared sigue hasta la mejilla y
            # sube hasta el ala de la guarda inferior. Sin ella, entre el fondo y esa ala quedaba
            # un paso (< 10 mm) al extremo del rodillo, donde la guarda inferior se corta: una
            # sonda llegaba a la cuña (ya en el criterio 8: una faja sin motor)
            from .belt_conveyor_guardas import CHAPA, HOLGURA_ALA, z_retorno

            z_tope = min(z_ala, z_retorno(c) - HOLGURA_ALA - CHAPA - 0.5)
            for s in (-1.0, 1.0):
                forma = forma + caja(x + sx * xw, x + sx * (xw + e), s * (yb + 0.4),
                                     s * (yc - e + 0.1), z_fondo, z_tope)
        forma = forma + caja(x + sx * xw, x + sx * (xw + e + ALCANCE), -yb, yb, z_ala - e,
                             z_ala)                                             # ala
    for s in (-1.0, 1.0):                                                       # mejillas
        forma = forma + caja(x - xw - e, x + xw + e, s * (yc - e), s * yc, z_fondo,
                             z_eje - d_eje / 2.0 - 2.0)
    nota = "guarda atornillada al soporte del rodillo (se quita para cambiar el rodillo)"
    if c.criterio >= 8:  # F1c (D12): sus agujeros y M6 a rosca en el soporte (8 mm)
        from .belt_conveyor_taller import cuenta_rosca, nota_rosca, paso, taladro_y

        for s in (-1.0, 1.0):
            for xg, zg in pernos_guarda_ret(x, z_eje):
                forma = forma - taladro_y(xg, zg, s * (yc - e - 1.0), s * (yc + 1.0), paso("M6"))
        cuenta = cuenta_rosca(f"guarda_ret{k}", "M6", e, SOPORTE_RET_T, "el soporte del rodillo")
        plan.calculos.setdefault("roscas", []).append(cuenta)
        nota = nota_rosca(nota, cuenta)
    suf = f"guarda_ret{k}"
    plan.pieza(suf, f"Guarda del rodillo de retorno ({k})", forma, material="acero")
    for lado in ("m", "p"):
        plan.union(f"{suf}_{lado}", suf, f"ret{k}_{lado}", "perno", nota, size="M6", qty=2)


def pernos_guarda_ret(x: float, z_eje: float) -> list[tuple[float, float]]:
    """(x, z) de los dos M6 de la guarda del rodillo en cada soporte (criterio 8): bajo el
    alojamiento del muñón, en lo que la mejilla y el soporte solapan."""
    return [(x - SOPORTE_RET_W / 4.0, z_eje - 23.0), (x + SOPORTE_RET_W / 4.0, z_eje - 23.0)]
