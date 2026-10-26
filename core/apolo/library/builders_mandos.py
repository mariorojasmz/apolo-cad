"""Builders de MANDOS del catálogo: la seta de parada de emergencia (plan seta-de-emergencia,
D4–D5; la de dos bloques NC, plan mandos-de-seguridad D1), el interruptor de resguardo con su
lengüeta (mandos-de-seguridad D2) y el pulsador, selector o piloto de puerta Ø22
(pedidos-de-extensiones-ii D2); el marco de los dos últimos, junto a su builder.

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
  contra su cara trasera (z = −panel_mm); con `bloques=2`, `BLOQUE_EXTRA` más hondo.
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

#: el agujero que pide el cuello Ø22 (default de referencia: el dato que corta la puerta es
#: `specs.agujero` de cada ficha, plan pedidos-de-extensiones-ii D1)
AGUJERO_D = 22.5
CUELLO_D = 22.0
COLLAR_D = 30.0
COLLAR_ALTO = 13.0
LEYENDA_T = 1.5
CUERPO = (30.0, 40.0, 42.0)   # portacontactos + 1 bloque NC, detrás de la puerta (X, Y, Z)
#: Lo que alarga el portacontactos cada bloque de contacto más (`bloques`, plan
#: mandos-de-seguridad D1): orden de un módulo apilado de la línea, sin verificar.
BLOQUE_EXTRA = 14.0
BLOQUES_SETA = (1, 2)
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
    prensa = Pos(0, -lado / 2 + 1.0, alto / 2) * Rotation(90, 0, 0) * _prensa_m20()
    return caja, prensa


def _prensa_m20():
    """Prensaestopa M20 a lo largo de +Z desde z = 0: hexágono de 9 mm, tuerca ciega Ø22 de 12 mm
    y la salida del cable Ø10 de 3 mm."""
    hexagono = Pos(0, 0, 0) * extrude(RegularPolygon(PRENSA_AF / math.sqrt(3), 6), 9.0)
    tuerca = Pos(0, 0, 8.5 + 6.0) * Cylinder(11.0, 12.0)
    salida = Pos(0, 0, 20.0 + 1.5) * Cylinder(5.0, 3.0)
    return hexagono + tuerca + salida


def seta_emergencia(d_seta: float = 40, montaje: str = "puerta", d_leyenda: float = 60,
                    panel_mm: float = 2.0, alto_caja: float = 55, lado_caja: float = 72,
                    bloques: int = 1):
    """Seta de parada de emergencia Ø`d_seta` (ISO 13850) en zonas: `seta`, `collar`,
    `leyenda` y `cuerpo` (puerta) o `caja` + `prensaestopa` (caja de superficie). `bloques` = los
    bloques NC (2 = dos canales): en la puerta, cada uno más alarga el portacontactos
    `BLOQUE_EXTRA`; en la caja van adentro (la caja de 2 pide `alto_caja` para los dos)."""
    _validar(d_seta, montaje, d_leyenda, panel_mm, alto_caja, lado_caja)
    if bloques not in BLOQUES_SETA:
        raise ValueError(f"Seta de emergencia: bloques {bloques} fuera de la serie "
                         f"({', '.join(map(str, BLOQUES_SETA))})")
    if montaje == "caja" and alto_caja < 55 + BLOQUE_EXTRA * (bloques - 1):
        raise ValueError(f"Seta de emergencia: con {bloques} bloques la caja pide alto_caja ≥ "
                         f"{55 + BLOQUE_EXTRA * (bloques - 1):g} mm")

    def build(_length):
        if montaje == "puerta":
            partes = _cabeza(0.0, d_seta, d_leyenda)
            # cuello: de 1 mm dentro del portacontactos a 1 mm dentro de la leyenda
            cuello = Pos(0, 0, -panel_mm / 2) * Cylinder(CUELLO_D / 2, panel_mm + 2.0)
            cx, cy, cz = CUERPO
            cz += BLOQUE_EXTRA * (bloques - 1)
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
                panel_mm: float = 2.0, alto_caja: float = 55, lado_caja: float = 72,
                bloques: int = 1) -> dict:
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


# ── interruptor de resguardo con actuador separado (plan mandos-de-seguridad D2) ──────────────
#
# MARCO (`interruptor_resguardo`): ORIGEN en el centro de la CARA DE APOYO (la que se atornilla
# a la estructura o a la hoja del resguardo), +Z sale del soporte, +Y hacia la cabeza.
# - `parte="cuerpo"`: caja RESG_CUERPO en z ∈ [0, 30] con la RANURA de la lengüeta en la cara
#   +Z junto a la cabeza (RESG_RANURA, centrada en y = RESG_Y_RANURA), 2 pasantes Ø5,5 (M5) en
#   y = RESG_Y_FIJACION y la prensaestopa M20 por −Y (hacia el piso en una cara vertical).
# - `parte="lengueta"`: la placa RESG_PLACA con 2 pasantes Ø4,5 (M4) en x = ±RESG_X_FIJACION y
#   la lengüeta RESG_LENGUETA que sale por +Z.
# - Anclas: `montaje` (la cara de apoyo, eje −Z), `fijacion_1/2`; el cuerpo, `ranura` (la boca,
#   eje −Z: el sentido en que entra la lengüeta); la lengüeta, `punta` (eje +Z). Con la lengüeta
#   a fondo (su punta en el fondo de la ranura) la placa queda a 7,5 mm del frente del cuerpo.
# Cotas del orden de Schneider XCSPA + XCSZ01 / Siemens 3SE5 con actuador, sin verificar.
RESG_CUERPO = (30.0, 92.0, 30.0)
RESG_RANURA = (20.0, 4.5, 16.0)
RESG_Y_RANURA = 36.0
RESG_Y_FIJACION = (-38.0, 22.0)
RESG_PLACA = (40.0, 14.0, 3.0)
RESG_LENGUETA = (18.0, 3.5, 24.0)
RESG_X_FIJACION = 14.0
PARTES_RESGUARDO = ("cuerpo", "lengueta")


def interruptor_resguardo(parte: str = "cuerpo"):
    """Interruptor de resguardo (ISO 14119 tipo 2): el cuerpo con la ranura o su lengüeta, que
    va en la hoja del resguardo (marco en el comentario de arriba)."""
    if parte not in PARTES_RESGUARDO:
        raise ValueError(f"Interruptor de resguardo: parte «{parte}» desconocida; usa "
                         f"{' o '.join(PARTES_RESGUARDO)}")

    def build(_length):
        if parte == "cuerpo":
            cx, cy, cz = RESG_CUERPO
            cuerpo = Pos(0, 0, cz / 2) * Box(cx, cy, cz)
            rx, ry, rz = RESG_RANURA
            cuerpo = cuerpo - Pos(0, RESG_Y_RANURA, cz - rz / 2 + 0.5) * Box(rx, ry, rz + 1.0)
            for y in RESG_Y_FIJACION:
                cuerpo = cuerpo - Pos(0, y, cz / 2) * Cylinder(FIJACION_D / 2, cz + 2)
            return cuerpo + Pos(0, -cy / 2 + 1.0, cz / 2) * Rotation(90, 0, 0) * _prensa_m20()
        px, py, pz = RESG_PLACA
        placa = Pos(0, 0, pz / 2) * Box(px, py, pz)
        for x in (-RESG_X_FIJACION, RESG_X_FIJACION):
            placa = placa - Pos(x, 0, pz / 2) * Cylinder(2.25, pz + 2)
        lx, ly, lz = RESG_LENGUETA
        return placa + Pos(0, 0, pz - _SOLAPE + lz / 2) * Box(lx, ly, lz)

    return build


def anclas_resguardo(parte: str = "cuerpo") -> dict:
    """Anclas LOCALES del interruptor de resguardo (marco del comentario de arriba)."""
    abajo = [0.0, 0.0, -1.0]
    out = {"montaje": {"origin": [0.0, 0.0, 0.0], "axis": abajo}}
    if parte == "cuerpo":
        for k, y in enumerate(RESG_Y_FIJACION, start=1):
            out[f"fijacion_{k}"] = {"origin": [0.0, float(y), 0.0], "axis": abajo}
        out["ranura"] = {"origin": [0.0, RESG_Y_RANURA, RESG_CUERPO[2]], "axis": abajo}
        return out
    for k, x in enumerate((-RESG_X_FIJACION, RESG_X_FIJACION), start=1):
        out[f"fijacion_{k}"] = {"origin": [float(x), 0.0, 0.0], "axis": abajo}
    punta = RESG_PLACA[2] - _SOLAPE + RESG_LENGUETA[2]
    out["punta"] = {"origin": [0.0, 0.0, punta], "axis": [0.0, 0.0, 1.0]}
    return out


# ── mando de puerta de la serie Ø22 (plan pedidos-de-extensiones-ii, D2) ─────────────────────
#
# MARCO (`mando_22`), el de la seta de puerta: ORIGEN en el centro de la CARA DE APOYO (el frente
# de la puerta donde asienta el bisel), +Z hacia el operador, +Y arriba. Delante (z ∈ [0,
# `delante`]): el bisel Ø`BISEL_D` × `BISEL_ALTO` y, sobre él, lo que se acciona o se ve según
# `tipo` (el botón y la lente Ø`FRENTE_D`; la maneta del selector, `MANETA`). Detrás: el cuello
# Ø22 que pasa por el agujero de la puerta (`specs.agujero` de la ficha) y el portacontactos
# `width` × `height` que aprieta contra su cara trasera (z = −`panel_mm`) hasta z = −`detras`.
# `delante`/`detras` son los de `tablero.puerta` (el loader exige que coincidan): la caja de la
# pieza es la huella `width` × `height` × (`delante` + `detras`) que mide la colocación.
# Anclas: `montaje` y `agujero` en el origen, eje −Z (las de la seta de puerta).
# Cotas del orden de Schneider Harmony XB5 (ficha XB5AA31: 30 mm de ancho; chapa de 1 a 6 mm),
# sin verificar (`cotas_verificadas: false` en el YAML). Zonas (D-a): `frente` (el botón, la
# lente o la maneta: el acabado de `specs.color`, lo exige el loader), `bisel` y `cuerpo` (cuello
# + portacontactos), en ese orden.
TIPOS_MANDO_22 = ("pulsador", "selector", "piloto")
ZONAS_MANDO_22 = ("frente", "bisel", "cuerpo")
BISEL_D = 30.0
BISEL_ALTO = 8.0
FRENTE_D = 24.0              # botón del pulsador y lente del piloto
MANETA = (8.0, 24.0)         # maneta del selector (X × Y), en la posición «0»
PANEL_MANDO_22 = (1.0, 6.0)  # «clamping thickness: 1 to 6 mm» de la ficha XB5AA31


def _validar_mando_22(tipo, width, height, delante, detras, panel_mm) -> None:
    if tipo not in TIPOS_MANDO_22:
        raise ValueError(f"Mando Ø22: tipo «{tipo}» desconocido; usa {', '.join(TIPOS_MANDO_22)}")
    if width < BISEL_D or height < BISEL_D:
        raise ValueError(f"Mando Ø22: la huella {width:g}×{height:g} no cubre el bisel Ø{BISEL_D:g}")
    if not PANEL_MANDO_22[0] <= panel_mm <= PANEL_MANDO_22[1]:
        raise ValueError(f"Mando Ø22: panel_mm {panel_mm} fuera de {PANEL_MANDO_22[0]:g}–"
                         f"{PANEL_MANDO_22[1]:g} mm (la chapa que aprieta)")
    if delante < BISEL_ALTO + 2:
        raise ValueError(f"Mando Ø22: delante {delante:g} no deja frente sobre el bisel de "
                         f"{BISEL_ALTO:g} mm")
    if detras < panel_mm + 10:
        raise ValueError(f"Mando Ø22: detras {detras:g} no deja portacontactos tras la chapa de "
                         f"{panel_mm:g} mm")


def mando_22(tipo: str = "pulsador", width: float = 30, height: float = 30, delante: float = 12,
             detras: float = 38, panel_mm: float = 2.0):
    """Pulsador, selector o piloto de puerta de la serie Ø22 con su cuello por el agujero de la
    chapa (marco en el comentario de arriba), en las zonas `ZONAS_MANDO_22`."""
    _validar_mando_22(tipo, width, height, delante, detras, panel_mm)

    def build(_length):
        bisel = Pos(0, 0, BISEL_ALTO / 2) * Cylinder(BISEL_D / 2, BISEL_ALTO)
        z0, alto = BISEL_ALTO - _SOLAPE, delante - BISEL_ALTO + _SOLAPE
        if tipo == "selector":
            frente = Pos(0, 0, z0 + alto / 2) * Box(MANETA[0], MANETA[1], alto)
        else:
            frente = Pos(0, 0, z0 + alto / 2) * Cylinder(FRENTE_D / 2, alto)
        # cuello: de 1 mm dentro del portacontactos a 1 mm dentro del bisel (como la seta)
        cuello = Pos(0, 0, -panel_mm / 2) * Cylinder(CUELLO_D / 2, panel_mm + 2.0)
        fondo = detras - panel_mm
        portacontactos = Pos(0, 0, -panel_mm - fondo / 2) * Box(width, height, fondo)
        return {"frente": frente, "bisel": bisel, "cuerpo": portacontactos + cuello}

    return build


def anclas_mando_22(**_params) -> dict:
    """Anclas LOCALES del mando Ø22: las de la seta de puerta."""
    abajo = [0.0, 0.0, -1.0]
    return {"montaje": {"origin": [0.0, 0.0, 0.0], "axis": abajo},
            "agujero": {"origin": [0.0, 0.0, 0.0], "axis": abajo}}


BUILDERS = {"seta_emergencia": seta_emergencia, "interruptor_resguardo": interruptor_resguardo,
            "mando_22": mando_22}
ANCLAS = {"seta_emergencia": anclas_seta, "interruptor_resguardo": anclas_resguardo,
          "mando_22": anclas_mando_22}
#: Builders que devuelven `{zona: forma}` (el YAML que los nombra declara `zonas:`).
ZONADOS = frozenset({"seta_emergencia", "mando_22"})
#: La zona de un builder por zonas que lleva el color de la ficha (`specs.color`): el loader
#: exige que su acabado sea el de ese color y que sea `fijo` (`zonas.verificar_color_de_ficha`).
ZONA_DE_COLOR = {"mando_22": "frente"}
