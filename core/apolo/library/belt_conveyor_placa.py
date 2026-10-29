"""Tensor de PLACA RANURADA de `create_belt_conveyor` (plan faja-compacta, D3; criterio 9).

Para fajas livianas, en lugar de la unidad tensora de carro UCT (marco de 317 × 199 mm): la
chumacera de BRIDA de catálogo del Ø del eje de cola, a rosca en una placa que corre sobre la cara
exterior del larguero, y un perno empujador con contratuerca en una oreja soldada al larguero.

- **La placa ranurada** (`PLACA_T`, la chapa de la plantilla) lleva la chumacera a ROSCA en sus
  cuatro agujeros (la cuenta de `belt_conveyor_taller.cuenta_rosca`: la punta no la pasa, no roza
  el larguero) y dos RANURAS a lo largo de X, del lado de la cabeza, por donde pasan dos espárragos
  M10 soldados a la cara exterior del larguero (ISO 13918) con arandela y tuerca por fuera.
  Vetable (D3 decía «apernada por ranuras a una placa soldada al larguero»): el larguero es un tubo
  CERRADO y una placa soldada a él no deja dónde poner la tuerca de un perno que pasa por su
  ranura (quedaría dentro del tubo o apretada contra él: lo que la F1c sacó de toda la plantilla);
  la placa que CORRE sobre espárragos soldados sí, con la tuerca por fuera.
- **La carrera** es la de `belt_conveyor_carrera.cuenta` (lo que pide el lazo); la placa tapa la
  ranura del eje en el larguero en TODA la carrera (sale `carrera` + el radio del paso del eje
  hacia la cola desde el eje y llega del otro lado hasta las ranuras de los espárragos).
- **El perno empujador** (M12 DIN 933, a rosca en la oreja, con contratuerca) empuja el canto de
  la placa hacia la cola al tensar; el modelo la muestra al INICIO de la carrera (banda recién
  montada), a `HUELGO` de la oreja. Su largo es el de catálogo que cubre la carrera + la oreja + la
  contratuerca + 2 hilos: eso limita la carrera (`CARRERA_MAX`). Va DECLARADO en su unión, como el
  resto de la tornillería de la plantilla (la BOM lo compra de la nota, con su tuerca): modelado,
  la puerta lo leía como un perno que tiene que enroscar en la placa que empuja y le probaba la
  llave contra la cara del larguero, a 3 mm de su eje.
- **Criterio 10 (F1b del plan, D8)**: la carrera ya no la limita el perno de catálogo. Si el DIN
  933 M12 más largo no la cubre, el empujador es una VARILLA ROSCADA M12 DIN 976-1 cortada a
  medida (de rosca corrida, comercial en barras: el «espárrago» que la BOM compra con su largo) con
  dos tuercas contra-apretadas en su punta exterior (la cabeza de la llave) y la contratuerca en la
  oreja. El tope es GEOMÉTRICO (`belt_conveyor_carrera.tope_placa`): lo que el tensor ocupa por la
  cara exterior del larguero (hasta la punta del empujador y su llave) tiene que caber antes del
  primer empalme del bastidor y dejar sitio al primer soporte de la cama.
"""

from __future__ import annotations

import math

from .belt_conveyor_cotas import HOLGURA_EJE, Cotas, perno_de_brida
from .belt_conveyor_plan import Plan, caja, cilindro_y, ranura_x
from .catalog import CATALOG, build_component

PLACA_T = 20.0            # la placa: rosca M10 de la brida y el canto donde empuja el perno M12
ESPARRAGO = "M10"         # los dos espárragos soldados que guían y aprietan la placa
Z_ESPARRAGO = 25.0        # ± desde el eje, dentro de la cara del larguero
PERNO = "PERNO-HEX-M12"   # el perno empujador
TUERCA = "TUERCA-M12"     # su contratuerca
OREJA_T = 16.0            # rosca M12 de ≥ 1·d con su margen
OREJA_ALTO = 50.0         # en Z
HUELGO = 5.0              # de la oreja al canto de la placa al inicio de la carrera
Y_PERNO = 15.0            # eje del perno desde la cara del larguero: la rosca de la oreja a
#                           ≥ 1,2·d0 de su canto soldado (EN 1993-1-8 tabla 3.3) y la punta (Ø12)
#                           sobre el canto de la placa de 20 (de 9 a 21 mm)
LLAVE_ESPARRAGO = 14.0    # de la brida al paso del espárrago (vaso de la tuerca M10)


def _fijos_perno() -> float:
    """Lo que el perno empujador gasta sin carrera: huelgo + oreja + contratuerca + 2 hilos."""
    from .fijacion import paso_grueso

    return HUELGO + OREJA_T + float(CATALOG[TUERCA].params["thickness"]) + 2.0 * paso_grueso("M12")


def _carrera_max() -> float:
    from .largos_perno import largos_catalogo

    return 5.0 * math.floor((max(largos_catalogo(PERNO)) - _fijos_perno()) / 5.0)


CARRERA_MAX = _carrera_max()
VARILLA = "DIN 976-1"     # criterio 10: la varilla roscada cuando el DIN 933 no cubre la carrera
PASO_VARILLA = 10.0       # se corta a medida: el largo, redondeado a 10 mm hacia arriba


def empujador(c: Cotas) -> tuple[float, bool]:
    """(largo, es varilla): el DIN 933 de catálogo que cubre la carrera o, con el criterio 10 y
    una carrera que ninguno cubre, la varilla roscada (con sus dos tuercas de cabeza)."""
    from .largos_perno import largo_comercial

    largo = largo_comercial(PERNO, _fijos_perno() + c.carrera)
    if largo is not None or c.criterio < 10:
        return largo, False
    from .fijacion import paso_grueso

    cabeza = 2.0 * float(CATALOG[TUERCA].params["thickness"]) + 2.0 * paso_grueso("M12")
    total = _fijos_perno() + c.carrera + cabeza
    return PASO_VARILLA * math.ceil(total / PASO_VARILLA - 1e-9), True


def medidas(c: Cotas) -> dict:
    """Las cotas de la placa al inicio de la carrera, relativas al eje (x = −half)."""
    from .belt_conveyor_taller import paso

    p = CATALOG[c.chum_c].params
    w, h = float(p["size_w"]), float(p["size_h"])
    d0 = paso(ESPARRAGO)
    p0 = w / 2.0 + LLAVE_ESPARRAGO + d0 / 2.0           # el espárrago, al inicio de la carrera
    b = p0 + c.carrera + d0 / 2.0 + math.ceil(1.2 * d0)  # canto +X (donde empuja el perno)
    a = max(w / 2.0 + 10.0, c.carrera + c.d_c / 2.0 + HOLGURA_EJE + 10.0)  # tapa la ranura
    largo, varilla = empujador(c)
    if largo is None:
        raise ValueError(f"la carrera de {c.carrera:g} mm no cabe en un perno empujador de "
                         f"catálogo ({PERNO})")
    return {"w": w, "h": h, "d0": d0, "p0": p0, "a": a, "b": b, "hz": h / 2.0 + 5.0,
            "x_e": -c.half + b, "largo_perno": largo, "varilla": varilla,
            # la varilla lleva su «cabeza» (las dos tuercas) dentro de su largo
            "cabeza": 0.0 if varilla else float(CATALOG[PERNO].params["head_h"])}


def voladizo(c: Cotas) -> float:
    """Lo que el larguero sale más allá del final de la carrera: la guarda de cola y la ranura."""
    return max(c.r_c + c.t + 40.0, c.d_c / 2.0 + HOLGURA_EJE + 25.0)


def x_extremo_placa(c: Cotas) -> float:
    """El canto +X de la placa al inicio de la carrera (la estación de patas de cola va después)."""
    return medidas(c)["x_e"]


def x_extremo_tensor(c: Cotas) -> float:
    """Hasta dónde llega el tensor por la cara exterior del larguero (la cabeza del perno)."""
    m = medidas(c)
    return m["x_e"] + m["largo_perno"] + m["cabeza"]


def x_fin_oreja(c: Cotas) -> float:
    """El canto +X de la oreja (donde termina lo soldado del tensor)."""
    return medidas(c)["x_e"] + HUELGO + OREJA_T


def zona_empujador(c: Cotas) -> tuple[float, float, float]:
    """Criterio 10 (D8): (desde, hasta, z mínima) de la franja de la cara exterior del larguero que
    recorre el empujador con su llave: un perno pasante con tuerca por fuera (soporte de la cama)
    puede ir ahí sólo POR ENCIMA, con su llave de vaso sin tocar las tuercas de la punta del
    empujador (que recorren toda la carrera)."""
    from .belt_conveyor_bastidor import LLAVE_M8

    r_tuerca = float(CATALOG[TUERCA].params["across_flats"]) / math.sqrt(3.0)  # circunradio
    return (medidas(c)["x_e"], x_extremo_tensor(c) + LLAVE_M8, c.zc + r_tuerca + LLAVE_M8)


def tensor_placa(plan: Plan, c: Cotas, i: int, s: float, rail: str) -> float:
    """El tensor de placa ranurada del lado `s` (chumacera, placa y oreja; el perno, declarado) con
    sus uniones. Devuelve |y| del extremo del eje de cola (2 mm después del collar del inserto)."""
    from .belt_conveyor_taller import broca, cuenta_rosca, nota_rosca, taladro_y
    from .belt_conveyor_tambores_taller import _registrar

    m = medidas(c)
    ref = c.chum_c
    p = CATALOG[ref].params
    bi, sb, span = float(p["Bi"]), float(p["s"]), float(p["bolt_span"])
    x, z, yo = -c.half, c.zc, c.y_out
    y_placa = yo + PLACA_T
    y0 = y_placa + bi / 2.0 + sb                       # origen de la UCF (centro del barreno)
    signo = "−" if s < 0 else "+"
    suf = f"chum_c{i}"
    plan.pieza(suf, f"Chumacera de cola ({signo}Y)", build_component(ref)[0], comp=ref,
               pos=(x, s * y0, z), rot=(0, 0, 180) if s > 0 else (0, 0, 0), key=f"comp|{ref}|std")

    # la placa: tapa la ranura del eje, la chumacera a rosca y las ranuras de los espárragos
    placa = caja(x - m["a"], x + m["b"], s * yo, s * y_placa, z - m["hz"], z + m["hz"])
    placa = placa - cilindro_y(x, z, s * (yo - 1.0), s * (y_placa + 1.0),
                               c.d_c / 2.0 + HOLGURA_EJE)
    size = perno_de_brida(ref)
    for dx in (-span / 2.0, span / 2.0):
        for dz in (-span / 2.0, span / 2.0):
            placa = placa - taladro_y(x + dx, z + dz, s * (yo - 1.0), s * (y_placa + 1.0),
                                      broca(size))
    xr = x + m["p0"] + c.carrera / 2.0
    for dz in (-Z_ESPARRAGO, Z_ESPARRAGO):
        placa = placa - ranura_x(xr, z + dz, s * (yo - 1.0), s * (y_placa + 1.0),
                                 c.carrera + m["d0"], m["d0"])
    psuf = f"placa_c{i}"
    plan.pieza(psuf, f"Placa ranurada del tensor ({i})", placa, material="acero")
    cuenta = _registrar(plan, cuenta_rosca(f"{suf}_placa", size, sb, PLACA_T,
                                           "la placa ranurada del tensor"))
    plan.union(f"{suf}_placa", suf, psuf, "perno",
               nota_rosca("brida de la chumacera a la placa ranurada", cuenta), size=size, qty=4)
    plan.union(f"{suf}_eje", "tambor_cola", suf, "contacto",
               "eje en el inserto, fijado con sus prisioneros")
    plan.union(f"{psuf}_larg", psuf, rail, "perno", _nota_esparragos(c), size=ESPARRAGO, qty=2)

    # la oreja con la rosca del perno empujador (declarado, con su contratuerca)
    x_o = m["x_e"] + HUELGO
    yp = yo + Y_PERNO
    alto = Y_PERNO + 18.0
    oreja = (caja(x_o, x_o + OREJA_T, s * yo, s * (yo + alto), z - OREJA_ALTO / 2.0,
                  z + OREJA_ALTO / 2.0)
             - _taladro_x(x_o - 1.0, x_o + OREJA_T + 1.0, s * yp, z, broca("M12")))
    osuf = f"oreja_c{i}"
    plan.pieza(osuf, f"Oreja del tensor ({i})", oreja, material="acero")
    plan.union(f"{osuf}_sold", osuf, rail, "soldadura",
               "oreja soldada a la cara exterior del larguero (filetes a los dos lados)",
               throat_mm=4, length_mm=round(2.0 * OREJA_ALTO, 1))
    if m["varilla"]:  # criterio 10 (D8): el DIN 933 de catálogo no cubre la carrera
        quien = (f"empujador de varilla roscada M12x{m['largo_perno']:g} {VARILLA} (espárrago de "
                 "rosca corrida, cortado a medida) con dos tuercas DIN 934 contra-apretadas en su "
                 "punta exterior (la cabeza de la llave),")
    else:
        quien = f"perno empujador M12x{m['largo_perno']:g} DIN 933"
    plan.union(f"empuje_c{i}", osuf, psuf, "perno",
               f"{quien} a la rosca de la oreja "
               f"(enganche {OREJA_T:g} mm ≥ 1·d) + contratuerca contra la oreja: su punta empuja "
               f"el canto de la placa hacia la cola al tensar (carrera {c.carrera:g} mm; banda "
               "recién montada: al inicio)", size="M12", qty=1)
    collar = y0 + bi / 2.0 + 0.36 * c.d_c - 2.0          # como `tambores.chumacera`
    return collar + 2.0


def _nota_esparragos(c: Cotas) -> str:
    from .belt_conveyor_taller import largo_esparrago

    largo = largo_esparrago(ESPARRAGO, PLACA_T)
    return (f"placa ranurada a 2 espárragos {ESPARRAGO}x{largo:g} ISO 13918 soldados a la cara "
            f"exterior del larguero + arandela y tuerca por fuera: corre por sus ranuras "
            f"({c.carrera:g} mm de carrera, nada dentro del tubo)")


def _taladro_x(x0: float, x1: float, y: float, z: float, d: float):
    from build123d import Cylinder, Pos, Rotation

    return Pos((x0 + x1) / 2.0, y, z) * Rotation(0, 90, 0) * Cylinder(d / 2.0, x1 - x0)
