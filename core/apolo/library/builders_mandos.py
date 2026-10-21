"""Builders de MANDOS del catálogo: la seta de parada de emergencia (plan seta-de-emergencia,
D4–D5).

Módulo propio porque `builders.py` está congelado por el trinquete de tamaño; `loader.py` une
este registro con los demás. Mismo contrato de factory `(**params) -> ((length|None) -> …)`,
pero un builder de `ZONADOS` devuelve sus partes etiquetadas `{zona: forma}`: el loader las une
en UN sólido y guarda de qué zona sale cada cara (`library/zonas.py`, `kernel/zonas.py`).

MARCO CANÓNICO (`seta_emergencia`), el que fija `position` en `insert_component`:

- ORIGEN en el centro de la CARA DE APOYO: el frente de la puerta donde asienta el anillo de
  leyenda (`montaje="puerta"`) o la base de la caja que se atornilla a la máquina
  (`montaje="caja"`). +Z sale hacia el operador; con la pieza en una cara vertical, +Y es
  ARRIBA (la prensaestopa de la caja sale por −Y, hacia el piso).
- Puerta: anillo de leyenda Ø`d_leyenda` × 1,5 en z ∈ [0, 1,5], collar Ø30, seta Ø`d_seta`
  con el frente en z = 12 + 0,525·d_seta (33 mm la de Ø40). Detrás, el cuello Ø22 que pasa por
  el agujero Ø22,5 de una puerta de `panel_mm` y el portacontactos 30 × 40 × 42 que aprieta
  contra su cara trasera (z = −panel_mm).
- Caja: caja de superficie `lado_caja` × `lado_caja` × `alto_caja` en z ∈ [0, alto_caja], con
  2 agujeros pasantes Ø5,5 (M5) en diagonal, prensaestopa M20 (hexágono de 24 entre caras) en
  la cara −Y y la misma cabeza (leyenda, collar y seta) sobre la tapa.
- Anclas: `montaje` = la cara de apoyo, eje = su normal SALIENTE (hacia el soporte, −Z, como la
  placa de una garrucha); `agujero` = el eje del Ø22,5 con el sentido del taladro (−Z): en la
  puerta, en su cara de apoyo; en la caja, en la tapa. La caja agrega `fijacion_1/2`, los ejes
  de sus agujeros de fijación en la cara de apoyo.

Cotas típicas de la línea Harmony XB5AS8445 + ZBY9140 / Siemens SIRIUS ACT 3SU1, sin verificar
(`cotas_verificadas: false` en el YAML). Las partes solapan 0.5–1 mm (regla de
`library/CLAUDE.md`).
"""

from __future__ import annotations

import math

from build123d import Axis, Box, Cylinder, Pos, RegularPolygon, Rotation, Solid, Sphere, extrude

#: Montajes que entiende `seta_emergencia`.
MONTAJES_SETA = ("puerta", "caja")
#: Zonas de cada montaje, en el orden del YAML.
ZONAS_SETA = {"puerta": ("seta", "collar", "leyenda", "cuerpo"),
              "caja": ("seta", "collar", "leyenda", "caja", "prensaestopa")}

AGUJERO_D = 22.5       # agujero de montaje de la serie Ø22 (IEC 60947-5-1, orden de catálogo)
CUELLO_D = 22.0
COLLAR_D = 30.0
COLLAR_ALTO = 13.0
LEYENDA_T = 1.5
CUERPO = (30.0, 40.0, 42.0)   # portacontactos + 1 bloque NC, detrás de la puerta (X, Y, Z)
FIJACION_D = 5.5      # paso de M5
PRENSA_AF = 24.0      # M20 × 1,5: hexágono de 24 entre caras
_SOLAPE = 0.5


def _validar(d_seta, montaje, d_leyenda, panel_mm, alto_caja, lado_caja) -> None:
    if montaje not in MONTAJES_SETA:
        raise ValueError(f"Seta de emergencia: montaje '{montaje}' desconocido; usa "
                         f"{' o '.join(MONTAJES_SETA)}")
    if not 30 <= d_seta <= 60:
        raise ValueError(f"Seta de emergencia: d_seta {d_seta} fuera de la serie (30–60 mm)")
    if d_leyenda < COLLAR_D + 4:
        raise ValueError(f"Seta de emergencia: d_leyenda {d_leyenda} no asoma del collar "
                         f"Ø{COLLAR_D:g}")
    if montaje == "puerta" and not 0.5 <= panel_mm <= 6:
        raise ValueError(f"Seta de emergencia: panel_mm {panel_mm} fuera de 0,5–6 mm")
    if montaje == "caja":
        if not 40 <= alto_caja <= 120:
            raise ValueError(f"Seta de emergencia: alto_caja {alto_caja} fuera de 40–120 mm")
        if d_leyenda > lado_caja - 4:
            raise ValueError(f"Seta de emergencia: la leyenda Ø{d_leyenda:g} no entra en la tapa "
                             f"de {lado_caja:g}")
        if lado_caja < 60:
            raise ValueError(f"Seta de emergencia: lado_caja {lado_caja} < 60 mm")


def _cabeza(z0: float, d_seta: float, d_leyenda: float) -> dict:
    """Leyenda, collar y seta con la cara trasera de la leyenda en z0."""
    leyenda = Pos(0, 0, z0 + LEYENDA_T / 2) * Cylinder(d_leyenda / 2, LEYENDA_T)
    z_collar = z0 + LEYENDA_T - _SOLAPE
    collar = Pos(0, 0, z_collar + COLLAR_ALTO / 2) * Cylinder(COLLAR_D / 2, COLLAR_ALTO)
    # seta: cilindro Ø d recortado por una esfera → falda recta y casquete de 0,275·d
    z_seta = z_collar + COLLAR_ALTO - 2.0
    alto, casquete, a = 0.525 * d_seta, 0.275 * d_seta, d_seta / 2
    radio = (a * a + casquete * casquete) / (2 * casquete)
    tope = z_seta + alto
    seta = (Pos(0, 0, z_seta + alto / 2) * Cylinder(a, alto)) & (Pos(0, 0, tope - radio)
                                                                 * Sphere(radio))
    return {"seta": seta, "collar": collar, "leyenda": leyenda}


def _centros_fijacion(lado: float) -> tuple[tuple[float, float], ...]:
    """Los 2 agujeros de fijación de la caja, en diagonal a 9 mm de los bordes."""
    c = lado / 2 - 9.0
    return ((-c, c), (c, -c))


def _caja(lado: float, alto: float) -> tuple[object, object]:
    """Caja (aristas verticales redondeadas R4) con sus 2 agujeros de fijación pasantes, y la
    prensaestopa M20 que sale por −Y desde 1 mm dentro de la pared: hexágono de 9 mm, tuerca
    ciega Ø22 de 12 mm y la salida del cable Ø10 de 3 mm."""
    caja = Solid(Box(lado, lado, alto).wrapped)
    caja = Pos(0, 0, alto / 2) * caja.fillet(4.0, caja.edges().filter_by(Axis.Z))
    for x, y in _centros_fijacion(lado):
        caja = caja - Pos(x, y, alto / 2) * Cylinder(FIJACION_D / 2, alto + 2)
    hexagono = Pos(0, 0, 0) * extrude(RegularPolygon(PRENSA_AF / math.sqrt(3), 6), 9.0)
    tuerca = Pos(0, 0, 8.5 + 6.0) * Cylinder(11.0, 12.0)
    salida = Pos(0, 0, 20.0 + 1.5) * Cylinder(5.0, 3.0)
    prensa = Pos(0, -lado / 2 + 1.0, alto / 2) * Rotation(90, 0, 0) * (hexagono + tuerca + salida)
    return caja, prensa


def seta_emergencia(d_seta: float = 40, montaje: str = "puerta", d_leyenda: float = 60,
                    panel_mm: float = 2.0, alto_caja: float = 55, lado_caja: float = 72):
    """Seta de parada de emergencia Ø`d_seta` (ISO 13850) en zonas: `seta`, `collar`,
    `leyenda` y `cuerpo` (puerta) o `caja` + `prensaestopa` (caja de superficie)."""
    _validar(d_seta, montaje, d_leyenda, panel_mm, alto_caja, lado_caja)

    def build(_length):
        if montaje == "puerta":
            partes = _cabeza(0.0, d_seta, d_leyenda)
            # cuello: de 1 mm dentro del portacontactos a 1 mm dentro de la leyenda
            cuello = Pos(0, 0, -panel_mm / 2) * Cylinder(CUELLO_D / 2, panel_mm + 2.0)
            cx, cy, cz = CUERPO
            portacontactos = Pos(0, 0, -panel_mm - cz / 2) * Box(cx, cy, cz)
            partes["cuerpo"] = cuello + portacontactos
            return partes
        caja, prensa = _caja(lado_caja, alto_caja)
        partes = _cabeza(alto_caja - _SOLAPE, d_seta, d_leyenda)
        partes["caja"] = caja
        partes["prensaestopa"] = prensa
        return partes

    return build


def anclas_seta(d_seta: float = 40, montaje: str = "puerta", d_leyenda: float = 60,
                panel_mm: float = 2.0, alto_caja: float = 55, lado_caja: float = 72) -> dict:
    """Anclas LOCALES de la seta (marco del docstring del módulo)."""
    abajo = [0.0, 0.0, -1.0]
    out = {"montaje": {"origin": [0.0, 0.0, 0.0], "axis": abajo}}
    if montaje == "puerta":
        out["agujero"] = {"origin": [0.0, 0.0, 0.0], "axis": abajo}
        return out
    out["agujero"] = {"origin": [0.0, 0.0, float(alto_caja)], "axis": abajo}
    for k, (x, y) in enumerate(_centros_fijacion(lado_caja), start=1):
        out[f"fijacion_{k}"] = {"origin": [float(x), float(y), 0.0], "axis": abajo}
    return out


BUILDERS = {"seta_emergencia": seta_emergencia}
ANCLAS = {"seta_emergencia": anclas_seta}
#: Builders que devuelven `{zona: forma}` (el YAML que los nombra declara `zonas:`).
ZONADOS = frozenset({"seta_emergencia"})
