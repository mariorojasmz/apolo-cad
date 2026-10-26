"""Piezas del ACCIONAMIENTO de un transportador: rodillo, tambor, motorreductores helicoidal y
sinfín-corona, poleas (dentada y en V), tensor de banda y take-up tipo trotadora. (La
transmisión por cadena —piñones y cadena— vive en `builders_transmision.py`.)

La fachada `builders.py` re-exporta cada nombre por IDENTIDAD y conserva `BUILDERS`
(plan `docs/plans/partir-nucleo-congelado-ii.md`, F1). Contrato de cada builder: una
*factory* `(**params) -> ((length|None) -> shape)`, forma centrada, Z arriba.
"""

from __future__ import annotations

from build123d import Box, Cylinder, Pos, Rotation

from apolo.kernel.shapes import make_revolution


def roller(diameter: float, shaft_d: float = 12.0, stub: float = 25.0):
    """Rodillo de transporte: tubo Ø=diameter (cortable, length = cara) + EJE pasante
    Ø=shaft_d con muñones que sobresalen `stub` por cada extremo (para asentar en
    soportes/rodamientos). El eje resuelve el "rodillo flotante"."""

    def build(length):
        body = Cylinder(diameter / 2.0, length)
        shaft = Cylinder(shaft_d / 2.0, length + 2.0 * stub)
        return body + shaft

    return build


def drum(diameter: float, shaft_d: float = 25.0, stub: float = 40.0, lagging: float = 0.0,
         shaft_hole_d: float = 0.0, hole_inset: float = 0.0):
    """Tambor/polea motriz: cuerpo Ø=diameter (cortable, length = ancho de cara) + EJE
    pasante Ø=shaft_d con muñones (`stub` por extremo) + camisa de lagging opcional
    (Ø+2·lagging sobre el 92 % central). Eje en Z local → al girar 90° sobre X queda en Y.
    Si `shaft_hole_d`>0, perfora un agujero TRANSVERSAL en cada extremo del eje (a `hole_inset`
    mm del extremo), para el tornillo M16 del tensor tipo trotadora; queda perpendicular al eje."""

    def build(length):
        body = Cylinder(diameter / 2.0, length)
        if lagging > 0:
            body = body + Cylinder(diameter / 2.0 + lagging, length * 0.92)
        shaft = Cylinder(shaft_d / 2.0, length + 2.0 * stub)
        solid = body + shaft
        if shaft_hole_d > 0 and hole_inset > 0:
            at = length / 2.0 + stub - hole_inset  # posición a lo largo del eje (Z local)
            for sgn in (1.0, -1.0):
                hole = Pos(0, 0, sgn * at) * Rotation(90, 0, 0) * Cylinder(shaft_hole_d / 2.0, shaft_d + 8.0)
                solid = solid - hole
        return solid

    return build


def motor(box_size: float, motor_d: float, motor_len: float,
          shaft_d: float | None = None, shaft_len: float | None = None):
    """Motorreductor HELICOIDAL EN LÍNEA (coaxial, tipo SEW R / NORD): motor IEC (cilindro) +
    campana adaptadora + caja reductora coaxial + eje de salida coaxial en el extremo OPUESTO al
    motor, con patas (foot-mounted) y caja de bornes. Eje común = X local; origen en el centro de
    la caja reductora. `box_size` ≈ Ø de la caja reductora; `motor_d`/`motor_len` = cuerpo IEC;
    `shaft_d`/`shaft_len` = eje de salida. Una sola Feature."""

    def build(_length=None):
        gd = box_size
        gl = box_size * 0.95
        sd = shaft_d if shaft_d is not None else box_size * 0.22
        sl = shaft_len if shaft_len is not None else box_size * 0.6
        md = motor_d
        # caja reductora coaxial, centrada en el origen (eje X)
        gearbox = Pos(0, 0, 0) * Rotation(0, 90, 0) * Cylinder(gd / 2.0, gl)
        # campana adaptadora motor -> reductor (lado -X de la caja)
        bell = Pos(-gl / 2.0 - md * 0.14, 0, 0) * Rotation(0, 90, 0) * Cylinder(gd * 0.42, md * 0.34)
        # motor IEC (cilindro) en -X
        mx = -gl / 2.0 - md * 0.28 - motor_len / 2.0
        rotor = Pos(mx, 0, 0) * Rotation(0, 90, 0) * Cylinder(md / 2.0, motor_len)
        # cubierta del ventilador (extremo -X del motor)
        fan = Pos(mx - motor_len / 2.0 - md * 0.05, 0, 0) * Rotation(0, 90, 0) * Cylinder(md * 0.40, md * 0.20)
        # caja de bornes arriba del motor
        term = Pos(mx, 0, md * 0.57) * Box(motor_len * 0.42, md * 0.42, md * 0.26)
        # eje de salida COAXIAL (+X, extremo opuesto al motor)
        out_shaft = Pos(gl / 2.0 + sl / 2.0 - 6.0, 0, 0) * Rotation(0, 90, 0) * Cylinder(sd / 2.0, sl)
        # patas de fijación (2 rieles) bajo el conjunto motor+caja
        foot_cx = (mx + gl / 2.0) / 2.0
        foot_len = (gl / 2.0 - (mx - motor_len / 2.0)) * 0.92
        foot = Box(foot_len, md * 0.16, md * 0.13)
        feet = (Pos(foot_cx, md * 0.30, -md / 2.0) * foot
                + Pos(foot_cx, -md * 0.30, -md / 2.0) * foot)
        return gearbox + bell + rotor + fan + term + out_shaft + feet

    return build


def worm_gearmotor(center_distance: float, bore_d: float, motor_d: float, motor_len: float):
    """Motorreductor SINFÍN-CORONA tipo NMRV: caja de corona con eje HUECO pasante (para montar
    DIRECTO sobre el eje del tambor motriz) + brida de salida con círculo de pernos + tapa NMRV,
    y el MOTOR PERPENDICULAR (a 90°, tornillo sin fin) con ventilador y bornes. `center_distance`
    = tamaño NMRV (mm, distancia entre centros); `bore_d` = Ø del eje hueco de salida. El barreno
    de salida va a lo largo de Y local (eje del tambor): al insertarlo sobre un eje/tambor en Y se
    coloca sin rotación. Envolvente de caja/brida/motor escalado del tamaño (representativo;
    verificar cotas exactas con el proveedor). Requiere brazo de torque aparte (anti-giro)."""
    import math

    cd = float(center_distance)
    Hw = cd * 1.7        # tamaño en el plano de la corona (X, Z) ~ Ø rueda + carcasa
    Hy = cd * 1.3        # ancho AXIAL (Y, a lo largo del eje hueco): la caja es MÁS PLANA en el eje
    FD = cd * 1.7        # Ø de la brida de salida (~ tamaño de la cara)
    CV = cd * 0.95       # Ø de la tapa NMRV
    br = bore_d / 2.0

    def build(_length=None):
        # caja de la corona (más ancha en X/Z que en el eje Y) con barreno pasante (eje hueco) en Y
        solid = Box(Hw, Hy, Hw) - Rotation(90, 0, 0) * Cylinder(br + 1.5, Hy + 60)
        # brida de salida (lado máquina, -Y) + cubo con bore chavetado
        fl_y = -Hy / 2.0 - 11.0
        solid = solid + (Pos(0, fl_y, 0) * Rotation(90, 0, 0) * Cylinder(FD / 2.0, 22)
                         - Pos(0, fl_y, 0) * Rotation(90, 0, 0) * Cylinder(br + 1.5, 40))
        solid = solid + (Pos(0, fl_y + 7, 0) * Rotation(90, 0, 0) * Cylinder(br + 16, 40)
                         - Pos(0, fl_y + 7, 0) * Rotation(90, 0, 0) * Cylinder(br + 1.5, 60))
        # tapa NMRV (lado exterior, +Y)
        solid = solid + Pos(0, Hy / 2.0 + 7, 0) * Rotation(90, 0, 0) * Cylinder(CV / 2.0, 15)
        # círculo de pernos de la brida (6)
        rbc = FD / 2.0 - cd * 0.13
        for i in range(6):
            a = math.radians(60.0 * i + 30.0)
            solid = solid + Pos(rbc * math.cos(a), fl_y, rbc * math.sin(a)) * Rotation(90, 0, 0) * Cylinder(4.5, 26)
        # sinfín + motor PERPENDICULAR (eje X), offset abajo (-Z, hacia el tornillo sin fin)
        zoff = -Hw * 0.42
        wx = -Hw * 0.55
        mx = -Hw * 0.6 - motor_len / 2.0
        solid = solid + Pos(wx, 0, zoff) * Box(Hw * 0.5, Hy * 0.85, Hw * 0.7)             # carcasa del sinfín
        solid = solid + Pos(mx, 0, zoff) * Rotation(0, 90, 0) * Cylinder(motor_d / 2.0, motor_len)   # motor
        solid = solid + Pos(mx - motor_len / 2.0 - 15, 0, zoff) * Rotation(0, 90, 0) * Cylinder(motor_d * 0.38, 30)  # ventilador
        solid = solid + Pos(mx, 0, zoff + motor_d * 0.5 + 12) * Box(motor_len * 0.42, motor_d * 0.5, motor_d * 0.3)  # bornes
        return solid

    return build


def pulley(pitch_d: float, width: float, bore_d: float = 0.0, flange_d: float = 0.0):
    """Polea/piñón por revolución: cuerpo con pestañas y taladro central opcional.

    pitch_d = diámetro primitivo, width = ancho, bore_d = taladro, flange_d =
    diámetro de pestaña (por defecto pitch_d + 8).
    """

    def build(_length=None):
        rb = bore_d / 2.0
        rp = pitch_d / 2.0
        rf = (flange_d if flange_d else pitch_d + 8.0) / 2.0
        hw = width / 2.0
        fl = min(2.0, hw * 0.4)  # espesor de pestaña
        profile_pts = [
            (rb, -hw), (rf, -hw), (rf, -hw + fl), (rp, -hw + fl),
            (rp, hw - fl), (rf, hw - fl), (rf, hw), (rb, hw),
        ]
        return make_revolution(profile_pts)

    return build


def v_pulley(outer_d: float, width: float, bore_d: float = 0.0, grooves: int = 1,
            groove_top: float = 13.0, groove_depth: float = 11.0, groove_pitch: float = 15.0):
    """Polea en V (sheave) para FAJA DE POTENCIA: disco macizo con N canales en V
    (trapezoidales) en la llanta + taladro central, por revolución (eje Z local → al
    girar 90° sobre X queda en Y, como el tambor). Medidas tipo sección A (groove_top≈13,
    pitch≈15) o B (≈17 / ≈19); `outer_d` = Ø exterior comercial, `width` = ancho de la llanta."""

    def build(_length=None):
        ro = outer_d / 2.0
        rb = max(bore_d / 2.0, 0.0)
        hw = width / 2.0
        n = max(1, int(grooves))
        gd = max(min(groove_depth, ro - rb - 4.0), 1.0)   # no llegar al taladro
        gt = min(groove_top, width / n * 0.8)             # cabe N canales en el ancho
        e = groove_pitch
        centers = sorted((i - (n - 1) / 2.0) * e for i in range(n))
        pts = [(rb, -hw), (ro, -hw)]
        for zc in centers:                                # llanta con N muescas en V
            pts.append((ro, max(zc - gt / 2.0, -hw)))
            pts.append((ro - gd, zc))
            pts.append((ro, min(zc + gt / 2.0, hw)))
        pts.append((ro, hw))
        pts.append((rb, hw))
        return make_revolution(pts)

    return build


def tensioner(pitch_d: float, width: float, bracket_w: float, bracket_h: float, bracket_t: float):
    """Tensor de banda: polea pequeña (eje Z) + soporte/bracket debajo."""

    def build(_length=None):
        rp = pitch_d / 2.0
        rf = rp + 4.0
        hw = width / 2.0
        fl = min(2.0, hw * 0.4)
        wheel = make_revolution([
            (6.0, -hw), (rf, -hw), (rf, -hw + fl), (rp, -hw + fl),
            (rp, hw - fl), (rf, hw - fl), (rf, hw), (6.0, hw),
        ])
        bracket = Pos(0, 0, -rf - bracket_t / 2.0) * Box(bracket_w, bracket_h, bracket_t)
        return wheel + bracket

    return build


def take_up(shaft_d: float = 25.0, bolt_d: float = 16.0, arm: float = 50.0,
            plate_t: float = 10.0, width: float = 44.0):
    """Conjunto tensor tipo TROTADORA (estilo trotadora): soporte en «C» (dos alas
    horizontales + alma) montado en el bastidor, y un tornillo M(bolt_d) VERTICAL que pasa
    por el ala superior, por el AGUJERO TRANSVERSAL del eje del rodillo y por el ala inferior
    (lo sujeta y, al girarlo, tensa). Sin chumacera; un conjunto por lado. Centrado en el eje
    del tornillo: Y = eje del rodillo (la «C» abre en +Y), Z = vertical (tornillo), X = avance."""

    def build(_length=None):
        sep = shaft_d + 6.0                 # luz entre alas (el eje pasa por el medio)
        zf = sep / 2.0 + plate_t / 2.0      # centro de cada ala
        top = Pos(0, 0, zf) * Box(width, arm, plate_t)
        bot = Pos(0, 0, -zf) * Box(width, arm, plate_t)
        web = Pos(0, -arm / 2.0 - plate_t / 2.0, 0) * Box(width, plate_t, sep + 2.0 * plate_t)
        bolt_h = sep + 2.0 * plate_t + 2.0 * bolt_d
        bolt = Cylinder(bolt_d / 2.0, bolt_h)  # vertical (eje Z)
        head = Pos(0, 0, bolt_h / 2.0 + bolt_d * 0.35) * Cylinder(bolt_d * 0.9, bolt_d * 0.7)
        nut = Pos(0, 0, -bolt_h / 2.0 - bolt_d * 0.35) * Box(bolt_d * 1.7, bolt_d * 1.7, bolt_d * 0.7)
        return top + bot + web + bolt + head + nut

    return build
