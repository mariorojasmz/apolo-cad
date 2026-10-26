"""CARPINTERÍA y herraje de mueble/puerta: bisagras (pala, media, resorte, piano, europea),
tirador, pomo, cerradura de embutir, cierre magnético, riel y corredera de puerta colgante y
corredera de cajón.

La fachada `builders.py` re-exporta cada nombre por IDENTIDAD y conserva `BUILDERS`
(plan `docs/plans/partir-nucleo-congelado-ii.md`, F1). Contrato de cada builder: una
*factory* `(**params) -> ((length|None) -> shape)`, forma centrada, Z arriba.
"""

from __future__ import annotations

from build123d import Box, Cylinder, Pos, Rotation

from apolo.kernel.shapes import make_revolution


def butt_hinge(leaf_w: float, leaf_h: float, leaf_t: float, knuckle_d: float,
               knuckles: int = 5, holes: int = 3, hole_d: float = 4.0):
    """Bisagra de pala (butt/libro) ABIERTA y plana: dos palas coplanares + nudillo
    (barril) con segmentos interpolados + pasador pasante, y agujeros por pala.
    Plana en XY (espesor en Z = leaf_t), eje del nudillo en Y, palas en ±X.
    leaf_w = ancho total (ambas palas), leaf_h = alto, knuckle_d = Ø del barril."""

    def build(_length=None):
        each = (leaf_w - knuckle_d) / 2.0
        off = knuckle_d / 2.0 + each / 2.0
        solid = (
            Rotation(90, 0, 0) * Cylinder(knuckle_d / 2.0, leaf_h)  # barril, eje Y
            + Pos(-off, 0, 0) * Box(each, leaf_h, leaf_t)
            + Pos(off, 0, 0) * Box(each, leaf_h, leaf_t)
        )
        n = max(2, int(knuckles))
        seg = leaf_h / n
        for i in range(n):
            yc = -leaf_h / 2.0 + seg * (i + 0.5)
            solid += Pos(0, yc, 0) * Rotation(90, 0, 0) * Cylinder(knuckle_d / 2.0 + 0.4, seg * 0.7)
        solid += Rotation(90, 0, 0) * Cylinder(knuckle_d * 0.22, leaf_h + 4.0)  # pasador
        m = max(0, int(holes))
        for sgn in (-1.0, 1.0):
            for j in range(m):
                yc = -leaf_h / 2.0 + leaf_h * (j + 0.5) / m
                solid -= Pos(sgn * off, yc, 0) * Cylinder(hole_d / 2.0, leaf_t + 2.0)
        return solid

    return build


def piano_hinge(leaf_w: float, leaf_t: float, knuckle_d: float, hole_d: float = 4.0):
    """Bisagra continua (piano), cortable a lo largo de Z: barril corrido (eje Z) + dos
    palas coplanares + taladros repartidos. leaf_w = ancho total, leaf_t = espesor de pala."""

    def build(length):
        each = (leaf_w - knuckle_d) / 2.0
        off = knuckle_d / 2.0 + each / 2.0
        solid = (
            Cylinder(knuckle_d / 2.0, length)
            + Pos(-off, 0, 0) * Box(each, leaf_t, length)
            + Pos(off, 0, 0) * Box(each, leaf_t, length)
        )
        n = max(2, int(length / 120.0))
        for sgn in (-1.0, 1.0):
            for i in range(n):
                zc = -length / 2.0 + length * (i + 0.5) / n
                solid -= Pos(sgn * off, 0, zc) * Rotation(90, 0, 0) * Cylinder(hole_d / 2.0, leaf_t + 2.0)
        return solid

    return build


def euro_hinge(cup_d: float = 35.0, cup_depth: float = 11.0, arm_len: float = 52.0,
               plate_w: float = 20.0, plate_h: float = 45.0, plate_t: float = 3.0):
    """Bisagra europea de CAZOLETA (concealed, cabinet): taza Ø35 embutida en la puerta
    + brazo + placa de montaje en el lateral del mueble. Centrada; taza en el extremo -X
    (hacia -Y, dentro de la puerta), placa en +X (plano del lateral)."""

    def build(_length=None):
        cup = Pos(-arm_len / 2.0, -cup_depth / 2.0, 0) * Rotation(90, 0, 0) * Cylinder(cup_d / 2.0, cup_depth)
        arm = Box(arm_len, 11.0, 6.0)
        plate = Pos(arm_len / 2.0, 0, 0) * Box(plate_t, plate_w, plate_h)
        return cup + arm + plate

    return build


def pull_handle(cc: float = 128.0, bar_d: float = 12.0, proj: float = 35.0):
    """Tirador de barra (manija): barra vertical (eje Z) sobre dos postes (eje Y, hacia
    -Y = la puerta). cc = distancia entre centros de los postes."""

    def build(_length=None):
        bar = Cylinder(bar_d / 2.0, cc + bar_d * 2.0)
        post = lambda zc: Pos(0, -proj / 2.0, zc) * Rotation(90, 0, 0) * Cylinder(bar_d * 0.42, proj)
        return bar + post(cc / 2.0) + post(-cc / 2.0)

    return build


def knob(base_d: float = 28.0, height: float = 30.0, stem_d: float = 12.0):
    """Pomo por revolución (eje Z): vástago de montaje (-Z) + base + cuello + cabeza."""

    def build(_length=None):
        rb, rs, rh = base_d / 2.0, stem_d / 2.0, base_d / 2.0 * 0.95
        pts = [
            (0, -6.0), (rs * 0.7, -6.0), (rs * 0.7, 0), (rb, 0), (rb, 3.0),
            (rs, 8.0), (rs, height - 9.0), (rh, height - 4.0), (rh, height), (0, height),
        ]
        return make_revolution(pts)

    return build


def butt_hinge_half(leaf_w_each: float, leaf_h: float, leaf_t: float, knuckle_d: float,
                    side: float = 1.0, holes: int = 3, hole_d: float = 4.0):
    """MEDIA bisagra (una pala + barril), para articulación FIEL: se insertan dos
    (side=+1 y side=-1) coaxiales, cada una fija a su panel → cada pala gira con su
    hoja (a diferencia de la bisagra entera de un solo sólido). Misma orientación que
    `butt_hinge` (barril en Y, pala en ±X según `side`, fina en Z)."""

    def build(_length=None):
        s = 1.0 if side >= 0 else -1.0
        off = (knuckle_d / 2.0 + leaf_w_each / 2.0 - 1.0) * s  # solapa el barril 1 mm → sólido único
        solid = Rotation(90, 0, 0) * Cylinder(knuckle_d / 2.0, leaf_h) + Pos(off, 0, 0) * Box(
            leaf_w_each, leaf_h, leaf_t
        )
        m = max(0, int(holes))
        for j in range(m):
            yc = -leaf_h / 2.0 + leaf_h * (j + 0.5) / m
            solid -= Pos(off, yc, 0) * Cylinder(hole_d / 2.0, leaf_t + 2.0)
        return solid

    return build


def spring_hinge(leaf_w: float, leaf_h: float, leaf_t: float, knuckle_d: float,
                 spring_d: float, holes: int = 3, hole_d: float = 4.0):
    """Bisagra de resorte / cierre automático (soft-close): como `butt_hinge` pero con
    una CAJA DE RESORTE (segmento central de Ø mayor) en el nudillo + pasador."""

    def build(_length=None):
        each = (leaf_w - knuckle_d) / 2.0
        off = knuckle_d / 2.0 + each / 2.0
        solid = (
            Rotation(90, 0, 0) * Cylinder(knuckle_d / 2.0, leaf_h)
            + Pos(-off, 0, 0) * Box(each, leaf_h, leaf_t)
            + Pos(off, 0, 0) * Box(each, leaf_h, leaf_t)
            + Rotation(90, 0, 0) * Cylinder(spring_d / 2.0, leaf_h * 0.42)   # caja de resorte
            + Rotation(90, 0, 0) * Cylinder(knuckle_d * 0.22, leaf_h + 4.0)  # pasador
        )
        m = max(0, int(holes))
        for sgn in (-1.0, 1.0):
            for j in range(m):
                yc = -leaf_h / 2.0 + leaf_h * (j + 0.5) / m
                solid -= Pos(sgn * off, yc, 0) * Cylinder(hole_d / 2.0, leaf_t + 2.0)
        return solid

    return build


def mortise_lock(case_w: float, case_h: float, case_t: float, face_w: float,
                 face_h: float, bolt_d: float):
    """Cerradura de embutir: cuerpo (caja) + placa frontal (faceplate) en el canto +X
    + pestillo/latch saliente + agujero del bombín. Embutida en el canto de la puerta."""

    def build(_length=None):
        case = Box(case_t, case_w, case_h)
        face = Pos(case_t / 2.0 + 1.5, 0, 0) * Box(3.0, face_w, face_h)
        latch = (
            Pos(case_t / 2.0 + 3.0 + bolt_d * 0.7, 0, case_h * 0.22)
            * Rotation(0, 90, 0) * Cylinder(bolt_d / 2.0, bolt_d * 1.4)
        )
        keyhole = Pos(0, 0, -case_h * 0.2) * Rotation(0, 90, 0) * Cylinder(bolt_d * 0.7, case_t + 2.0)
        return (case + face + latch) - keyhole

    return build


def magnetic_catch(body_l: float, body_w: float, body_h: float):
    """Tope/cierre magnético (carcasa): caja con dos imanes a la vista en la cara +X
    (la placa de contacto va en la puerta; aquí se modela el cuerpo, que es la pieza)."""

    def build(_length=None):
        body = Box(body_l, body_w, body_h)
        mag = lambda yo: Pos(body_l / 2.0 - 1.0, yo, 0) * Rotation(0, 90, 0) * Cylinder(body_h * 0.3, 3.0)
        return body + mag(body_w * 0.25) + mag(-body_w * 0.25)

    return build


def door_rail(width: float = 35.0, height: float = 35.0, wall: float = 1.5):
    """Riel U para puerta corrediza/colgante (tipo Ducasse U-100): perfil en U
    (canal abierto por abajo) de sección width×height, cortable a lo largo de X.
    Acero galvanizado; se atornilla cada ~500 mm. `length` = largo de corte."""

    def build(length):
        outer = Box(length, width, height)
        inner = Pos(0, 0, -wall) * Box(length + 2.0, width - 2.0 * wall, height)  # canal abierto abajo
        return outer - inner

    return build


def door_carriage(body_l: float = 80.0, body_w: float = 28.0, body_h: float = 45.0,
                  wheel_d: float = 14.0):
    """Corredera colgante de 4 ruedas (tipo Ducasse D-100): cuerpo body_l×body_w×body_h
    + 4 ruedas de acero (eje Y, ruedan a lo largo del riel en X) + perno colgante hacia
    abajo (al canto de la puerta). `body_l` = a lo largo del riel."""

    def build(_length=None):
        solid = Box(body_l, body_w, body_h)
        r, zc = wheel_d / 2.0, body_h / 2.0 - wheel_d / 2.0  # ruedas ARRIBA (ruedan en el canal del riel)
        for x in (body_l * 0.3, -body_l * 0.3):
            for y in (body_w * 0.25, -body_w * 0.25):
                solid += Pos(x, y, zc) * Rotation(90, 0, 0) * Cylinder(r, wheel_d * 0.55)
        solid += Pos(0, 0, -body_h / 2.0 - 8.0) * Cylinder(4.0, 16.0)  # perno colgante (al canto de la puerta)
        return solid

    return build


def drawer_slide(width: float = 12.0, height: float = 45.0, wall: float = 1.5):
    """Corredera de cajón telescópica (simplificada), cortable a lo largo de X: perfil
    de canal exterior + riel interior deslizante. length = longitud de la corredera."""

    def build(length):
        member = Box(length, width, height) - Box(length + 2.0, width - 2.0 * wall, height - 2.0 * wall)
        inner = Box(length * 0.92, width - 2.0 * wall - 2.0, height - 2.0 * wall - 2.0)
        return member + inner

    return build
