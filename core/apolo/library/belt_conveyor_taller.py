"""Criterio 8 de `create_belt_conveyor` (F1c del plan faja-larga-en-tramos, D10–D14): lo que un
revisor de taller a ciegas encontró en la plantilla del criterio 7 —uniones declaradas sin
agujeros, tuercas que quedaban DENTRO de un tubo cerrado, chapas más largas que la plancha
comercial y tornillería sin largo en la BOM—. Funciones puras (formas build123d y números) que
usan los módulos de la plantilla sólo con `criterio >= 8`; lo sellado antes regenera igual.

- **Rosca en placa (D10, D11)**: un perno que entra en una placa de acero gruesa no lleva tuerca;
  la placa va roscada (broca de machuelo ISO 2306 en la geometría) y el perno se elige del
  catálogo con su punta DENTRO de la placa (`HOLGURA_PUNTA` antes de lo que tenga detrás) y un
  enganche ≥ `K_ACERO`·d: el de `calidad/agarre.py` (VDI 2230, criterio de taller), que además
  cubre el 0,8·d de la altura de la tuerca normal (DIN 934, ISO 898-2). En hierro fundido
  (la brida de una chumacera, el carro del tensor) ≥ `K_FUNDICION`·d. La cuenta de cada una va
  a `Plan.calculos["roscas"]`.
- **Perno pasante (D12)**: lo que se atornilla a un tubo cerrado lo cruza de lado a lado por un
  buje soldado (D4 de la F1) y la tuerca queda por fuera; lo que va sobre la cara superior del
  larguero (las guardas laterales) va a espárragos soldados (ISO 13918) con tuerca por arriba.
- **Paños (D13)**: chapa comercial de 2440/3000 mm y plegadora usual de 3 m: ninguna cama ni
  guarda lateral pasa `PANO_MAX`; un tramo largo se parte en paños IGUALES con su junta.
- **Largo en la nota (D14)**: cada unión `perno` nombra su designación («M10x25 DIN 933»), que
  `tornilleria_declarada.py` lee para la BOM.
"""

from __future__ import annotations

import math

PANO_MAX = 3000.0        # chapa comercial (2440 / 3000) y plegadora de taller (D13)
K_ACERO = 1.0            # enganche de rosca ≥ k·d en acero (el de `calidad/agarre.py`)
K_FUNDICION = 1.5        # … en hierro fundido
HOLGURA_PUNTA = 0.5      # de la punta del perno a lo que tiene detrás la placa roscada
ARANDELA = 1.6           # arandela ISO 7089 bajo la tuerca de un espárrago (M6)


def con_taller(c) -> bool:
    return c.criterio >= 8


def d_nominal(size: str) -> float:
    return float(size.upper().lstrip("M"))


def broca(size: str) -> float:
    """Broca de machuelo (ISO 2306) de la rosca `size`: el agujero roscado en la geometría."""
    from .engineering.threads import thread_spec

    return float(thread_spec(size)["broca_mm"])


def paso(size: str) -> float:
    """Agujero de paso (ISO 273 serie media) de un perno `size`."""
    from .engineering.bolts import clearance_hole_mm

    return float(clearance_hole_mm(size))


def largo_a_rosca(size: str, agarre: float, placa: float, k: float = K_ACERO,
                  fondo: float = 0.0) -> float:
    """El perno DIN 933 de catálogo más corto que engancha ≥ k·d en una placa roscada de
    `placa` mm (aprieta `agarre` mm bajo la cabeza). Su punta no pasa la placa, salvo `fondo`
    mm de alivio detrás de ella."""
    from .largos_perno import largos_catalogo

    d = d_nominal(size)
    largos = [L for L in largos_catalogo(f"PERNO-HEX-{size}")
              if min(L - agarre, placa) >= k * d - 1e-6
              and L <= agarre + placa + fondo - HOLGURA_PUNTA + 1e-6]
    if not largos:
        raise ValueError(f"ningún {size} de catálogo engancha {k:g}·d en {placa:g} mm de rosca "
                         f"con {agarre:g} mm de agarre: usa una placa más gruesa")
    return min(largos)


def cuenta_rosca(union: str, size: str, agarre: float, placa: float, donde: str,
                 k: float = K_ACERO, fondo: float = 0.0) -> dict:
    """La cuenta de una unión a rosca en placa (para `Plan.calculos["roscas"]`); `pasa_mm` > 0
    = la punta sale de la placa y entra en el alivio de `fondo` mm."""
    largo = largo_a_rosca(size, agarre, placa, k, fondo)
    d = d_nominal(size)
    enganche = min(largo - agarre, placa)
    return {"union": union, "perno": f"{size}x{largo:g} DIN 933", "rosca_en": donde,
            "agarre_mm": round(agarre, 2), "placa_mm": placa,
            "enganche_mm": round(enganche, 2), "pide_mm": round(k * d, 2),
            "pasa_mm": round(largo - agarre - placa, 2),
            "norma": ("VDI 2230 / criterio de taller (enganche ≥ 1·d en acero, ≥ 1,5·d en "
                      "fundición); cubre 0,8·d de la tuerca DIN 934 (ISO 898-2)"),
            "ok": enganche >= k * d - 1e-6}


def nota_rosca(que: str, cuenta: dict) -> str:
    return (f"{que}: {cuenta['perno']} a la rosca de {cuenta['rosca_en']} (enganche "
            f"{cuenta['enganche_mm']:g} mm ≥ {cuenta['pide_mm']:g})")


def largo_pasante(size: str, agarre: float) -> float:
    from .fijacion import largo_perno

    return largo_perno(size, agarre, estricto=True)


def nota_pasante(que: str, size: str, agarre: float, buje: float, cabeza: str = "DIN 933") -> str:
    largo = largo_pasante(size, agarre)
    return (f"{que}: perno pasante {size}x{largo:g} {cabeza} + tuerca, cruza el tubo por un buje "
            f"soldado (Ø{buje:g}: el tubo no se aplasta al apretar) y se aprieta por fuera")


def largo_esparrago(size: str, agarre: float) -> float:
    """Espárrago soldado (ISO 13918): agarre + arandela + tuerca DIN 934 + 2 hilos, de la serie."""
    from .engineering.bolts import hex_nut_mm
    from .fijacion import paso_grueso
    from .largos_perno import SERIE_ISO

    minimo = agarre + ARANDELA + hex_nut_mm(size)[1] + 2.0 * paso_grueso(size)
    return float(next(L for L in SERIE_ISO if L >= minimo - 1e-6))


def nota_esparrago(que: str, size: str, agarre: float) -> str:
    largo = largo_esparrago(size, agarre)
    return (f"{que}: espárrago {size}x{largo:g} ISO 13918 soldado a la cara superior del "
            "larguero + arandela y tuerca por arriba (nada dentro del tubo)")


def panos(tramos: list[tuple[float, float]], junta: float) -> list[tuple[float, float]]:
    """Cada (x0, x1) partido en paños IGUALES de ≤ `PANO_MAX` con un hueco de 2·`junta`."""
    out = []
    for x0, x1 in tramos:
        n = max(1, math.ceil((x1 - x0) / PANO_MAX - 1e-9))
        largo = (x1 - x0 - 2.0 * junta * (n - 1)) / n
        out += [(x0 + k * (largo + 2.0 * junta), x0 + k * (largo + 2.0 * junta) + largo)
                for k in range(n)]
    return out


def repartir(x0: float, x1: float, n: int, prohibidos=(), margen: float = 40.0,
             rejilla: float = 5.0, separacion: float = 30.0) -> list[float]:
    """`n` posiciones de perno entre `x0 + margen` y `x1 − margen`, lo más parejas posible, a
    ≥ `separacion` entre sí y fuera de los intervalos `prohibidos` [(lo, hi)]. ValueError si no
    caben."""
    a, b = x0 + margen, x1 - margen
    if b < a:
        a = b = (x0 + x1) / 2.0
    libres = [a + k * rejilla for k in range(int(round((b - a) / rejilla)) + 1)]
    libres = [x for x in libres if not any(lo <= x <= hi for lo, hi in prohibidos)]
    metas = [(a + b) / 2.0] if n == 1 else [a + (b - a) * k / (n - 1) for k in range(n)]
    out: list[float] = []
    for m in metas:
        cand = [x for x in libres if all(abs(x - y) >= separacion for y in out)]
        if not cand:
            raise ValueError(f"no caben {n} pernos entre x = {x0:.0f} y {x1:.0f} lejos de lo "
                             "que ya ocupa el larguero")
        out.append(min(cand, key=lambda x: abs(x - m)))
    return sorted(out)


def unir(forma, piezas):
    """`forma` + todas las `piezas` en UNA booleana (de a una, un tubo con 40 bujes tardaba 3 s)."""
    piezas = list(piezas)
    return forma.fuse(*piezas) if piezas else forma


def cortar(forma, herramientas):
    """`forma` − todas las `herramientas` en UNA booleana."""
    herramientas = list(herramientas)
    return forma.cut(*herramientas) if herramientas else forma


def taladro_y(x: float, z: float, y0: float, y1: float, d: float):
    from .belt_conveyor_plan import cilindro_y

    return cilindro_y(x, z, y0, y1, d / 2.0)


def taladro_z(x: float, y: float, z0: float, z1: float, d: float):
    from build123d import Cylinder, Pos

    z0, z1 = sorted((z0, z1))
    return Pos(x, y, (z0 + z1) / 2.0) * Cylinder(d / 2.0, z1 - z0)


def avellanado(x: float, y: float, z_top: float, size: str, espesor: float):
    """Agujero de paso + avellanado a 90° (DIN 74) de un tornillo DIN 7991 que queda a ras de
    `z_top` (la cara de la cama por donde desliza la banda)."""
    from build123d import Cone, Pos

    dk = AVELLANADO_DK[size]
    d0 = paso(size)
    h = (dk - d0) / 2.0                                    # cono de 90°
    cono = Pos(x, y, z_top - h / 2.0 + 0.05) * Cone(d0 / 2.0, dk / 2.0 + 0.05, h + 0.1)
    return cono + taladro_z(x, y, z_top - espesor - 1.0, z_top + 1.0, d0)


#: Ø de la cabeza de un DIN 7991 (ISO 10642) y su altura: el avellanado y el espesor mínimo
AVELLANADO_DK = {"M5": 10.0, "M6": 12.0, "M8": 16.0}
AVELLANADO_K = {"M5": 2.8, "M6": 3.3, "M8": 4.4}
