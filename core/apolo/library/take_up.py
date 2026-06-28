"""Plantillas paramétricas de RODILLOS tipo trotadora (eje + rodamientos + seeger + soporte «C»).

Dos super-comandos que comparten geometría (helpers de este módulo):

- ``create_take_up`` → **rodillo de cola tensable** (idler): eje FIJO que sobresale a AMBOS lados,
  con un TENSOR por lado.
- ``create_drive_roller`` → **rodillo motriz**: tensor en UN lado (no-motor) y en el otro un EJE
  LARGO para acoplar el motorreductor.

Esquema trotadora (SIN chumacera): el tubo gira sobre 2 rodamientos alojados en sus extremos,
retenidos con seeger.

TENSOR (mecanismo, IMPORTANTE para montar bien):
- Un solo **soporte en «C»** por lado: su **alma** se SUELDA al larguero (al interior del bastidor)
  y sus **dos aletas** capturan el eje del rodillo.
- Un **perno horizontal** (a lo largo de la banda, eje X) pasa por las **dos aletas y por el eje**;
  el eje tiene **hilo** ahí (hace de tuerca). La **cabeza queda al exterior**.
- Al girar el perno, el eje (enroscado en él) se desplaza: hacia la cabeza/exterior = **jala el
  rodillo = TENSA**; al revés = afloja. ``dir_tensor`` elige a qué extremo apunta la cabeza
  (-1 = hacia -X/cola, +1 = hacia +X/cabeza).

Frame canónico: eje del rodillo a lo largo de Y, centrado en el origen → al insertar basta
`position`=(extremo, 0, altura del eje).
"""

from __future__ import annotations

from build123d import Box, Cylinder

from apolo.kernel.shapes import place

from .builders import socket_cap
from .catalog import CATALOG, build_component
from .conveyor import ConveyorPart

# largos comerciales de stock (DIN 933, mm) para redondear el perno a una medida real
_STD_BOLT_LEN = [25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 80, 90, 100, 110, 120, 130, 140, 150]

_AL = 45.0        # largo (Y) de las aletas del soporte (van del alma hacia adentro)
_HZ = 70.0        # alto (Z) de las aletas / del soporte
_PERNO_OFF = 28.0  # el perno va a `half+voladizo-_PERNO_OFF` (hacia adentro, NO en el extremo del eje)
_EJE_GAP = 16.0    # el eje se queda `_EJE_GAP` mm CORTO del alma → el alma queda SÓLIDA (sin agujero)


def _cyl_y(r: float, h: float, y: float = 0.0):
    """Cilindro de radio r y largo h con eje a lo largo de Y, centrado en (0, y, 0)."""
    return place(Cylinder(r, h), (0.0, y, 0.0), (90.0, 0.0, 0.0))


def _ybr(half: float, voladizo: float, sgn: float) -> float:
    """Y del perno (donde cruza el eje), por lado: hacia ADENTRO del extremo, no en la punta del eje."""
    return sgn * (half + voladizo - _PERNO_OFF)


# ---------------------------------------------------------------- helpers comunes

def _roller_body(diam_rodillo: float, cara: float, big: float, engomado: bool, name: str):
    """Tubo HUECO (bore = Ø ext. del rodamiento) + engomado opcional a TODO el ancho. UNA pieza."""
    lag = 6.0 if engomado else 0.0
    body = _cyl_y(diam_rodillo / 2.0, cara) - _cyl_y(big / 2.0, cara + 2.0)
    if lag > 0:
        body = body + (_cyl_y(diam_rodillo / 2.0 + lag, cara) - _cyl_y(diam_rodillo / 2.0, cara))
    return ConveyorPart("rodillo", name, body, None, None)


def _bearing_seeger_parts(rodamiento: str, big: float, width_b: float, half: float) -> list[ConveyorPart]:
    """2 rodamientos de catálogo en los extremos del tubo + 2 seeger de retención."""
    parts: list[ConveyorPart] = []
    brg_shape, _ = build_component(rodamiento)
    for i, sgn in enumerate((-1.0, 1.0), start=1):
        yb = sgn * (half - width_b / 2.0)
        parts.append(
            ConveyorPart(
                f"rod{i}", f"Rodamiento {rodamiento} ({i})",
                place(brg_shape, (0.0, yb, 0.0), (90.0, 0.0, 0.0)), rodamiento, None,
                base_key=f"comp|{rodamiento}|std", base_shape=brg_shape,
                position=(0.0, yb, 0.0), rotation=(90.0, 0.0, 0.0),
            )
        )
        seeger = _cyl_y(big / 2.0 + 2.0, 2.0, sgn * (half - 1.0)) - _cyl_y(big / 2.0 - 3.0, 4.0, sgn * (half - 1.0))
        parts.append(ConveyorPart(f"seeger{i}", f"Seeger retención ({i})", seeger, None, None))
    return parts


def _take_up_side(perno: str, bolt_d: float, t: float, half: float, voladizo: float,
                  bore: float, sgn_y: float, dir_tensor: float, idx: int) -> list[ConveyorPart]:
    """Un lado del TENSOR: un soporte en «C» (alma soldada al larguero + 2 aletas) y un perno
    horizontal que pasa por las 2 aletas y por el eje (roscado). Cabeza al exterior (`dir_tensor`);
    al girar, jala el eje y tensa. `sgn_y` = en qué muñón del eje va."""
    dx = 1.0 if dir_tensor >= 0 else -1.0
    a = bore / 2.0 + 12.0                            # medio-claro entre aletas (recorrido del eje)
    y_perno = _ybr(half, voladizo, sgn_y)            # perno: hacia ADENTRO (no en la punta del eje)
    y_alma = sgn_y * (half + voladizo)               # alma al borde exterior (cara interior del larguero)
    y_aletas = sgn_y * (half + voladizo - _AL / 2.0)  # centro de las aletas LARGAS (del alma hacia adentro)

    # 2 aletas (normales a X) LARGAS con agujero de PASO del perno (a la altura del perno, no del eje-tip)
    cbody = None
    for sx in (-1.0, 1.0):
        xa = sx * (a + t / 2.0)
        plate = place(Box(t, _AL, _HZ), (xa, y_aletas, 0.0), (0, 0, 0))
        plate = plate - place(Cylinder((bolt_d + 1.0) / 2.0, t + 2.0), (xa, y_perno, 0.0), (0, 90, 0))
        cbody = plate if cbody is None else cbody + plate
    # alma (normal a Y) SÓLIDA: se SUELDA a la cara interior del larguero; el eje ya NO la alcanza
    cbody = cbody + place(Box(2.0 * (a + t), t, _HZ), (0.0, y_alma, 0.0), (0, 0, 0))

    # perno tensor ALLEN (cabeza cilíndrica + hexágono interior), eje X: cabeza al exterior,
    # atraviesa aleta-eje-aleta; se gira con llave Allen
    head_x = dx * (a + t + 6.0)
    span = 2.0 * (a + t) + 11.0   # cabeza + cruza ambas aletas + el eje (sin sobresalir de más)
    bolt_L = next((Lc for Lc in _STD_BOLT_LEN if Lc >= span), _STD_BOLT_LEN[-1])
    bolt_canon = socket_cap(bolt_d)(bolt_L)
    pos = (head_x, y_perno, 0.0)
    rot = (0.0, 90.0 * dx, 0.0)                  # Ry(±90): eje del perno de Z a ±X (cabeza al exterior)
    return [
        ConveyorPart(f"soporte{idx}", f"Soporte en C {t:g}mm ({idx})", cbody, None, None),
        ConveyorPart(f"perno{idx}", f"Perno tensor Allen {perno}×{bolt_L:g} ({idx})",
                     place(bolt_canon, pos, rot), perno, None,
                     base_key=f"comp|{perno}|{bolt_L:.0f}", base_shape=bolt_canon,
                     position=pos, rotation=rot),
    ]


def _common(rodamiento: str, perno: str, diam_rodillo: float, ancho_banda: float, voladizo: float):
    """Validación + cotas compartidas. Devuelve (bore, big, width_b, bolt_d, cara, half)."""
    brg = CATALOG[rodamiento]
    bore = float(brg.specs["d"])     # Ø interior del rodamiento = Ø del eje
    big = float(brg.specs["D"])      # Ø exterior del rodamiento (aloja en el tubo)
    width_b = float(brg.specs["B"])  # ancho del rodamiento
    if perno not in CATALOG:
        raise ValueError(f"perno desconocido '{perno}'")
    bolt_d = float(CATALOG[perno].specs["d"])
    if diam_rodillo < big + 10.0:
        raise ValueError(f"Ø rodillo mínimo {big + 10:g} mm (debe alojar el rodamiento Ø{big:g})")
    if ancho_banda < 100.0:
        raise ValueError("Ancho de banda mínimo 100 mm")
    if voladizo < _AL:
        raise ValueError(f"Voladizo mínimo {_AL:g} mm (para que las aletas del soporte libren el rodillo)")
    cara = ancho_banda
    half = cara / 2.0
    return bore, big, width_b, bolt_d, cara, half


def _shaft_with_holes(bore: float, length: float, bolt_d: float, y_off: float, holes_y: list[float]):
    """Eje (cilindro a lo largo de Y) con un agujero transversal (a lo largo de X) en cada
    `holes_y` — por ahí pasa el perno tensor (el eje hace de tuerca)."""
    shaft = _cyl_y(bore / 2.0, length, y_off)
    for hy in holes_y:
        shaft = shaft - place(Cylinder((bolt_d + 1.0) / 2.0, bore + 12.0), (0.0, hy, 0.0), (0.0, 90.0, 0.0))
    return shaft


# ---------------------------------------------------------------- super-comandos

def take_up_parts(diam_rodillo, ancho_banda, rodamiento, perno, espesor_soporte,
                  voladizo, engomado, dir_tensor=-1.0) -> list[ConveyorPart]:
    """Rodillo de COLA tensable: eje fijo + TENSOR (soporte «C» + perno longitudinal) en AMBOS extremos."""
    bore, big, width_b, bolt_d, cara, half = _common(rodamiento, perno, diam_rodillo, ancho_banda, voladizo)

    parts = [_roller_body(diam_rodillo, cara, big, engomado, "Rodillo de cola")]
    holes = [_ybr(half, voladizo, 1.0), _ybr(half, voladizo, -1.0)]
    eje_ext = voladizo - _EJE_GAP   # el eje se queda corto del alma (alma sólida)
    parts.append(ConveyorPart("eje", "Eje fijo (roscado p/ perno)",
                              _shaft_with_holes(bore, cara + 2.0 * eje_ext, bolt_d, 0.0, holes), None, None))
    parts += _bearing_seeger_parts(rodamiento, big, width_b, half)
    for i, sgn in enumerate((-1.0, 1.0), start=1):
        parts += _take_up_side(perno, bolt_d, espesor_soporte, half, voladizo, bore, sgn, dir_tensor, i)
    return parts


def drive_roller_parts(diam_rodillo, ancho_banda, rodamiento, perno, espesor_soporte,
                       voladizo, largo_eje_motor, engomado, dir_tensor=1.0) -> list[ConveyorPart]:
    """Rodillo MOTRIZ: TENSOR (soporte «C» + perno longitudinal) en el lado -Y (no-motor) y un EJE
    LARGO en +Y para acoplar el motorreductor. Reusa los helpers del rodillo de cola."""
    bore, big, width_b, bolt_d, cara, half = _common(rodamiento, perno, diam_rodillo, ancho_banda, voladizo)
    if largo_eje_motor < 50.0:
        raise ValueError("Largo del eje al motor mínimo 50 mm (para acoplar el reductor)")

    parts = [_roller_body(diam_rodillo, cara, big, engomado, "Rodillo motriz")]
    # eje ASIMÉTRICO: -Y (take-up) se queda corto del alma; +Y sobresale `largo_eje_motor` (al reductor)
    eje_ext = voladizo - _EJE_GAP
    shaft_len = cara + eje_ext + largo_eje_motor
    y_off = (largo_eje_motor - eje_ext) / 2.0
    parts.append(ConveyorPart("eje", f"Eje motriz Ø{bore:g} (largo al reductor)",
                              _shaft_with_holes(bore, shaft_len, bolt_d, y_off, [_ybr(half, voladizo, -1.0)]),
                              None, None))
    parts += _bearing_seeger_parts(rodamiento, big, width_b, half)
    parts += _take_up_side(perno, bolt_d, espesor_soporte, half, voladizo, bore, -1.0, dir_tensor, 1)  # take-up SOLO -Y
    return parts
