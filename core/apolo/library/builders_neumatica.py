"""Geometría de los cilindros neumáticos del catálogo (plan V8.9 D5, F2). Módulo propio:
`builders.py` está congelado por el trinquete de tamaño.

MARCO LOCAL de todo lo de aquí: +X = el AVANCE del vástago; el origen es el centro de la cara
DELANTERA del cuerpo (por donde sale el vástago: la tapa delantera en ISO 15552, la cara de la
tapa de la que nace la nariz en ISO 6432); +Z = el lado de los puertos. El cuerpo crece hacia −X
con la carrera. Las piezas salen en la pose RETRAÍDA (carrera 0 de la junta).

- `cuerpo_*`: tapas y camisa en UN sólido, con el paso del vástago (holgura radial
  `HOLGURA_VASTAGO`: el sello real roza, el modelo no se cruza con el vástago en ningún punto
  del recorrido), los 4 roscados del cuadro TG en cada tapa (ISO 15552) y los dos puertos.
- `vastago`: el vástago Ø d hasta su hombro (WH desde la cara delantera) y la rosca KK de largo
  AM; su extremo interior queda a 1 mm de la tapa trasera retraído.
- `brida` / `pie` (ISO 15552, cotas de `neumatica/montajes.py`), `empujador` (placa con buje
  roscado que asienta en el hombro del vástago).
- `cilindro_iso15552` / `cilindro_iso6432`: los builders del CATÁLOGO (`insert_component`, la
  ficha): cuerpo + vástago retraídos fundidos en un sólido.

Lo que es forma y no cota de interfaz (largo de las tapas, chaflán de la camisa, el ojo trasero
del ISO 6432, la profundidad de los roscados) es criterio de modelo: no cambia ningún entregable
de compra; las cotas de interfaz salen de los params de cada ref (YAML) con su fuente.
"""

from __future__ import annotations

from dataclasses import dataclass

from build123d import Axis, Box, Cylinder, Pos, Rotation, chamfer

#: holgura radial del vástago en su paso por el cuerpo y del buje del empujador (criterio de modelo)
HOLGURA_VASTAGO = 0.5
_SOLAPE = 0.5
#: broca de machuelo ISO 2306 (métrica) / ISO 228 (G) de los roscados que se dibujan
BROCA_MACHUELO = {"M5": 4.2, "M6": 5.0, "M8": 6.8, "M10": 8.5, "G1/8": 8.8, "G1/4": 11.8, "G3/8": 15.25}
#: agujero de paso ISO 273 serie media de los tornillos de la tapa
PASO_ISO273 = {"M5": 5.5, "M6": 6.6, "M8": 9.0, "M10": 11.0}


@dataclass(frozen=True)
class Cotas:
    """Cotas de un cilindro (params del YAML). ISO 15552: `E` lado del cuerpo cuadrado, `C`
    largo del cuerpo en carrera 0, `TG` cuadro de los roscados de las tapas, `tapa` su rosca.
    ISO 6432: `E` = Ø de la camisa, `XC` del pasador trasero al hombro del vástago, `nariz`/
    `nariz_l` Ø y largo de la rosca de la nariz, `CD`/`EW` Ø del pasador y ancho del ojo."""

    norma: str
    D: float
    d: float
    E: float
    WH: float
    AM: float
    KK: float
    puerto: str
    C: float = 0.0
    TG: float = 0.0
    tapa: str = ""
    XC: float = 0.0
    nariz: float = 0.0
    nariz_l: float = 0.0
    CD: float = 0.0
    EW: float = 0.0

    @property
    def iso15552(self) -> bool:
        return self.norma == "ISO 15552"

    @property
    def largo_tapa(self) -> float:
        """Largo de cada tapa de ISO 15552 (criterio de modelo: 22 % del cuerpo)."""
        return round(0.22 * self.C, 1)

    def largo(self, carrera: float) -> float:
        """De la cara delantera al extremo trasero de la camisa (sin el ojo del ISO 6432)."""
        if self.iso15552:
            return self.C + carrera
        return self.XC - self.WH - 1.5 * self.CD + carrera

    def x_interior(self, carrera: float) -> float:
        """Extremo interior del vástago retraído (a 1 mm del fondo)."""
        fondo = self.largo_tapa if self.iso15552 else 3.0
        return -self.largo(carrera) + fondo + 1.0

    @property
    def x_extremo(self) -> float:
        return self.WH + self.AM


def cotas_de(params: dict) -> Cotas:
    """Las `Cotas` de los params del YAML de una ref (`Component.params`)."""
    claves = set(Cotas.__dataclass_fields__)
    return Cotas(**{k: v for k, v in params.items() if k in claves})


def _cil_x(r: float, x0: float, x1: float, y: float = 0.0, z: float = 0.0):
    """Cilindro de radio r a lo largo de X entre x0 y x1."""
    return Pos((x0 + x1) / 2.0, y, z) * (Rotation(0, 90, 0) * Cylinder(r, x1 - x0))


def _caja(x0, x1, y0, y1, z0, z1):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2) * Box(x1 - x0, y1 - y0, z1 - z0)


def _agujero_z(r: float, x: float, y: float, z_tope: float, prof: float):
    """Agujero vertical (eje Z) de radio r que entra desde z_tope hacia −Z `prof` mm."""
    return Pos(x, y, z_tope - prof / 2.0 + _SOLAPE / 2.0) * Cylinder(r, prof + _SOLAPE)


def _cuadro(s: float):
    return [(sy * s / 2.0, sz * s / 2.0) for sy in (-1, 1) for sz in (-1, 1)]


def _x_puertos(c: Cotas, carrera: float) -> tuple[float, float]:
    """x de los puertos A (fondo) y B (vástago) sobre +Z."""
    largo = c.largo(carrera)
    if c.iso15552:
        return -largo + c.largo_tapa / 2.0, -c.largo_tapa / 2.0
    return -largo + 6.0, -6.0


def _tope_puertos(c: Cotas) -> float:
    return c.E / 2.0


def cuerpo_iso15552(c: Cotas, carrera: float, con_paso: bool = True):
    largo, lt = c.largo(carrera), c.largo_tapa
    trasera = _caja(-largo, -largo + lt, -c.E / 2, c.E / 2, -c.E / 2, c.E / 2)
    delantera = _caja(-lt, 0.0, -c.E / 2, c.E / 2, -c.E / 2, c.E / 2)
    lado = c.E - 3.0
    camisa = _caja(-largo + lt - _SOLAPE, -lt + _SOLAPE, -lado / 2, lado / 2, -lado / 2, lado / 2)
    camisa = chamfer(camisa.edges().filter_by(Axis.X), 2.0)
    forma = trasera + camisa + delantera
    if con_paso:
        forma = forma - _cil_x(c.d / 2.0 + HOLGURA_VASTAGO, -largo + lt, _SOLAPE)
    r_rosca = BROCA_MACHUELO[c.tapa] / 2.0
    prof = min(12.0, lt - 3.0)
    for y, z in _cuadro(c.TG):
        forma = forma - _cil_x(r_rosca, -prof, _SOLAPE, y, z)
        forma = forma - _cil_x(r_rosca, -largo - _SOLAPE, -largo + prof, y, z)
    r_p = BROCA_MACHUELO[c.puerto] / 2.0
    prof_p = c.E / 2.0 - c.d / 2.0 - HOLGURA_VASTAGO - 2.0
    for x in _x_puertos(c, carrera):
        forma = forma - _agujero_z(r_p, x, 0.0, c.E / 2.0, prof_p)
    return forma


def cuerpo_iso6432(c: Cotas, carrera: float, con_paso: bool = True):
    largo = c.largo(carrera)
    camisa = _cil_x(c.E / 2.0, -largo, 0.0)
    nariz = _cil_x(c.nariz / 2.0, -_SOLAPE, c.nariz_l)
    x_pasador = -(c.XC - c.WH) - carrera
    ojo = _caja(x_pasador - c.CD, -largo + _SOLAPE, -c.EW / 2, c.EW / 2, -c.CD, c.CD)
    pasador = Pos(x_pasador, 0, 0) * (Rotation(90, 0, 0) * Cylinder(c.CD / 2.0, c.EW + 2 * _SOLAPE))
    forma = camisa + nariz + ojo - pasador
    if con_paso:
        forma = forma - _cil_x(c.d / 2.0 + HOLGURA_VASTAGO, -largo + 3.0, c.nariz_l + _SOLAPE)
    r_p = BROCA_MACHUELO[c.puerto] / 2.0
    prof_p = c.E / 2.0 - c.d / 2.0 - HOLGURA_VASTAGO - 1.0
    for x in _x_puertos(c, carrera):
        forma = forma - _agujero_z(r_p, x, 0.0, c.E / 2.0, prof_p)
    return forma


def cuerpo(c: Cotas, carrera: float, con_paso: bool = True):
    return (cuerpo_iso15552 if c.iso15552 else cuerpo_iso6432)(c, carrera, con_paso)


def vastago(c: Cotas, carrera: float, desde: float | None = None):
    """El vástago retraído: Ø d hasta el hombro (x = WH) y la rosca hasta WH + AM."""
    x0 = c.x_interior(carrera) if desde is None else desde
    barra = _cil_x(c.d / 2.0, x0, c.WH)
    rosca = _cil_x(min(c.KK, c.d) / 2.0 - 0.1, c.WH - _SOLAPE, c.x_extremo)
    return barra + rosca


def anclas_cuerpo(c: Cotas, carrera: float) -> dict:
    """Anclas LOCALES del cuerpo: el eje (cara delantera, +X), la tapa trasera y los puertos."""
    xa, xb = _x_puertos(c, carrera)
    z = _tope_puertos(c)
    out = {"eje": {"origin": [0.0, 0.0, 0.0], "axis": [1.0, 0.0, 0.0]},
           "tapa_trasera": {"origin": [-c.largo(carrera), 0.0, 0.0], "axis": [-1.0, 0.0, 0.0]},
           "A": {"origin": [xa, 0.0, z], "axis": [0.0, 0.0, 1.0]},
           "B": {"origin": [xb, 0.0, z], "axis": [0.0, 0.0, 1.0]}}
    if not c.iso15552:
        out["nariz"] = {"origin": [0.0, 0.0, 0.0], "axis": [1.0, 0.0, 0.0]}
        out["pasador"] = {"origin": [-(c.XC - c.WH) - carrera, 0.0, 0.0], "axis": [0.0, 1.0, 0.0]}
    return out


# ── accesorios de montaje (ISO 15552) ──────────────────────────────────────────────────────


def brida(c: Cotas, b, x_apoyo: float, sentido: int):
    """La brida FA apoyada en la cara x = `x_apoyo` del cuerpo y que crece hacia `sentido`
    (+1 delantera, −1 trasera)."""
    x0, x1 = sorted((x_apoyo, x_apoyo + sentido * b.BB))
    forma = _caja(x0, x1, -b.BE / 2, b.BE / 2, -b.BC / 2, b.BC / 2)
    forma = forma - _cil_x(b.BA / 2.0, x0 - _SOLAPE, x1 + _SOLAPE)
    for y, z in _cuadro(c.TG):
        forma = forma - _cil_x(PASO_ISO273[c.tapa] / 2.0, x0 - _SOLAPE, x1 + _SOLAPE, y, z)
    for sy in (-1, 1):
        for sz in (-1, 1):
            forma = forma - _cil_x(b.BP / 2.0, x0 - _SOLAPE, x1 + _SOLAPE, sy * b.BF / 2, sz * b.BD / 2)
    return forma


def anclas_brida(b, x_apoyo: float, sentido: int) -> dict:
    x = x_apoyo + sentido * b.BB
    out = {"brida": {"origin": [x, 0.0, 0.0], "axis": [float(sentido), 0.0, 0.0]}}
    k = 0
    for sy in (-1, 1):
        for sz in (-1, 1):
            k += 1
            out[f"brida_agujero_{k}"] = {"origin": [x, sy * b.BF / 2, sz * b.BD / 2],
                                         "axis": [float(sentido), 0.0, 0.0]}
    return out


def pie(c: Cotas, p, d_central: float, x_apoyo: float, sentido: int):
    """Un pie LB atornillado a la cara x = `x_apoyo` de una tapa, hacia `sentido` (±1): ala
    vertical contra la tapa (con el paso central y los del cuadro TG) y ala de base a −AH."""
    xv0, xv1 = sorted((x_apoyo, x_apoyo + sentido * p.AT))
    xb0, xb1 = sorted((x_apoyo, x_apoyo + sentido * (p.AG + p.AD)))
    vertical = _caja(xv0, xv1, -p.AE / 2, p.AE / 2, -p.AH, c.E / 2)
    base = _caja(xb0, xb1, -p.AE / 2, p.AE / 2, -p.AH, -p.AH + p.AT)
    forma = vertical + base
    forma = forma - _cil_x(d_central / 2.0, xv0 - _SOLAPE, xv1 + _SOLAPE)
    for y, z in _cuadro(c.TG):
        forma = forma - _cil_x(PASO_ISO273[c.tapa] / 2.0, xv0 - _SOLAPE, xv1 + _SOLAPE, y, z)
    xh = x_apoyo + sentido * p.AG
    for sy in (-1, 1):
        forma = forma - _agujero_z(p.AP / 2.0, xh, sy * p.AF / 2, -p.AH + p.AT, p.AT)
    return forma


def anclas_pie(p, x_apoyo: float, sentido: int, nombre: str) -> dict:
    xc = x_apoyo + sentido * (p.AG + p.AD) / 2.0
    xh = x_apoyo + sentido * p.AG
    return {nombre: {"origin": [xc, 0.0, -p.AH], "axis": [0.0, 0.0, -1.0]},
            f"{nombre}_agujero_1": {"origin": [xh, -p.AF / 2, -p.AH], "axis": [0.0, 0.0, -1.0]},
            f"{nombre}_agujero_2": {"origin": [xh, p.AF / 2, -p.AH], "axis": [0.0, 0.0, -1.0]}}


# ── empujador ──────────────────────────────────────────────────────────────────────────────


def diametro_buje(c: Cotas) -> float:
    """Ø del buje roscado del empujador (criterio de diseño: 2·KK + 4 mm de pared)."""
    return 2.0 * c.KK + 4.0


def empujador(c: Cotas, ancho: float, alto: float, espesor: float):
    """Placa `ancho` (Y) × `alto` (Z) × `espesor` (X) con su buje roscado detrás: el buje asienta
    en el hombro del vástago (x = WH) y aloja toda la rosca AM; la placa empieza 1 mm más allá."""
    x_buje = c.x_extremo + 1.0
    buje = _cil_x(diametro_buje(c) / 2.0, c.WH, x_buje + _SOLAPE)
    buje = buje - _cil_x(c.KK / 2.0 + HOLGURA_VASTAGO, c.WH - _SOLAPE, x_buje - 0.5)
    placa = _caja(x_buje, x_buje + espesor, -ancho / 2, ancho / 2, -alto / 2, alto / 2)
    return buje + placa


def x_cara_empujador(c: Cotas, espesor: float) -> float:
    return c.x_extremo + 1.0 + espesor


# ── builders del catálogo ──────────────────────────────────────────────────────────────────


def _catalogo(**params):
    c = cotas_de(params)

    def build(length):
        return cuerpo(c, 0.0, con_paso=False) + vastago(c, 0.0, desde=-c.largo_tapa if c.iso15552 else -1.0)

    return build


def cilindro_iso15552(**params):
    return _catalogo(norma="ISO 15552", **params)


def cilindro_iso6432(**params):
    return _catalogo(norma="ISO 6432", **params)


def _anclas_catalogo(norma: str):
    def anclas(**params):
        c = cotas_de({"norma": norma, **params})
        return {**anclas_cuerpo(c, 0.0),
                "extremo_vastago": {"origin": [c.x_extremo, 0.0, 0.0], "axis": [1.0, 0.0, 0.0]}}
    return anclas


BUILDERS = {"cilindro_iso15552": cilindro_iso15552, "cilindro_iso6432": cilindro_iso6432}
#: anclas por familia (`loader.ANCLAS`): las de la ref insertada sola, retraída
ANCLAS = {"cilindro_iso15552": _anclas_catalogo("ISO 15552"),
          "cilindro_iso6432": _anclas_catalogo("ISO 6432")}
