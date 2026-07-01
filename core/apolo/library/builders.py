"""Builders geométricos genéricos del catálogo (data-driven).

Cada builder es una *factory* `(**params) -> ((length|None) -> shape)`: recibe
los parámetros fijos declarados en el YAML del componente y devuelve la función
que el catálogo invoca con la longitud de corte (o None). La forma se construye
centrada en el origen, eje Z hacia arriba (convención del kernel).

Para añadir un tipo de pieza nuevo: define una factory y regístrala en BUILDERS.
Los componentes del catálogo la referencian por nombre (campo `builder`).
"""

from __future__ import annotations

import math

from build123d import Box, Cylinder, Pos, Rotation

from apolo.kernel.shapes import make_rect_tube, make_revolution, make_structural_profile


def profile(size: str):
    """Perfil de aluminio ranurado (T-slot), cortable a lo largo de Z."""
    return lambda length: make_structural_profile(size, length)


def rect_tube(width: float, height: float, wall: float = 3.0):
    """Tubo estructural rectangular de ACERO (hueco), cortable a lo largo de Z.
    Pareja de acero de ``profile`` (aluminio): largueros, patas y travesaños del bastidor."""
    return lambda length: make_rect_tube(width, height, wall, length)


def cylinder(diameter: float):
    """Cilindro macizo eje Z, cortable (ejes, piezas a medida)."""
    return lambda length: Cylinder(diameter / 2.0, length)


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


def box(width: float, depth: float, height: float):
    """Caja fija centrada en el origen."""
    return lambda _length=None: Box(width, depth, height)


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


def leg(profile_size: str = "40x40", plate: float = 120.0, plate_t: float = 10.0):
    """Pata regulable = columna de perfil + placa base; length = altura total."""

    def build(length):
        column = Pos(0, 0, plate_t / 2) * make_structural_profile(profile_size, length - plate_t)
        base = Pos(0, 0, -(length - plate_t) / 2) * Box(plate, plate, plate_t)
        return column + base

    return build


def guard(thickness: float = 6.0, height: float = 150.0):
    """Guarda/faldón lateral: chapa cortable a lo largo de X."""
    return lambda length: Box(length, thickness, height)


def sensor(body_r: float = 9.0, body_l: float = 70.0,
           bracket: tuple = (40.0, 20.0, 4.0), bracket_pos: tuple = (0.0, -25.0, -20.0)):
    """Sensor cilíndrico con soporte (fijo)."""

    def build(_length=None):
        body = Rotation(90, 0, 0) * Cylinder(body_r, body_l)
        sup = Pos(*bracket_pos) * Box(*bracket)
        return body + sup

    return build


def bearing(d: float, D: float, B: float):
    """Rodamiento rígido de bolas (anillo macizo) por revolución; eje Z, ancho B.

    d = diámetro interior, D = exterior, B = ancho. Perfil [r, z] del anillo.
    """

    def build(_length=None):
        ri, ro, hz = d / 2.0, D / 2.0, B / 2.0
        profile_pts = [(ri, -hz), (ro, -hz), (ro, hz), (ri, hz)]
        return make_revolution(profile_pts)

    return build


def screw(d: float, length: float, head_d: float, head_h: float):
    """Tornillo Allen (DIN 912): cabeza cilíndrica + vástago, por revolución.

    Origen centrado; la cabeza queda en +Z. length = longitud del vástago.
    """

    def build(_length=None):
        total = length + head_h
        z0 = -total / 2.0  # base del vástago
        zc = z0 + length   # unión vástago/cabeza
        profile_pts = [
            (0.0, z0), (d / 2.0, z0), (d / 2.0, zc),
            (head_d / 2.0, zc), (head_d / 2.0, zc + head_h), (0.0, zc + head_h),
        ]
        return make_revolution(profile_pts)

    return build


def linear_rail(width: float, height: float):
    """Riel de guía lineal: barra cortable a lo largo de X (sección width×height)."""
    return lambda length: Box(length, width, height)


def linear_block(width: float, length: float, height: float, bore: float = 0.0):
    """Carro de guía lineal: bloque fijo con rebaje inferior para el riel."""

    def build(_length=None):
        body = Box(length, width, height)
        if bore > 0:
            channel = Pos(0, 0, -height / 2 + bore / 2) * Box(length + 2, bore, bore)
            body = body - channel
        return body

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


def pillow_block(d: float, H: float, H1: float, L: float, J: float,
                 A: float, N: float, Bi: float, s: float):
    """Chumacera de PIE tipo UCP (soporte con rodamiento de inserto): cuerpo fundido
    acampanado sobre base de 2 patas con agujeros ranurados + inserto con collar y 2
    prisioneros + grasera. Cotas comerciales UCP2xx (mm): d=Ø eje, H=altura al centro
    del eje, H1=altura total, L=largo, J=distancia entre pernos, A=ancho de base,
    N=Ø agujero de perno, Bi=ancho del inserto, s=espesor de base. Marco canónico:
    EJE del rodamiento a lo largo de Y, base abajo (-Z), ORIGEN en el centro del
    barreno (para insertarlo directamente sobre el eje)."""

    def build(_length=None):
        Rh = H1 - H                        # radio de la campana (tope del cuerpo)
        zb0, zb1 = -H, -H + s              # base: cara inferior / superior
        hw = Bi                            # ancho axial del cuerpo (= inserto)

        # --- base de 2 patas (obround: caja central + 2 semicírculos) ---
        base = Pos(0, 0, zb0 + s / 2.0) * Box(L - A, A, s)
        base = base + Pos(-(L - A) / 2.0, 0, zb0 + s / 2.0) * Cylinder(A / 2.0, s)
        base = base + Pos((L - A) / 2.0, 0, zb0 + s / 2.0) * Cylinder(A / 2.0, s)

        # --- pedestal fundido: revolución (eje Z) recortada al ancho del cuerpo ---
        flare = make_revolution([
            (0.0, zb1 - 0.5 * s),
            (A * 0.62, zb1 - 0.5 * s),
            (Rh * 0.62, 0.0),
            (0.0, 0.0),
        ])
        flare = flare & (Pos(0, 0, 0) * Box(4.0 * L, hw, 4.0 * H1))

        # --- campana del rodamiento (cilindro, eje Y) ---
        boss = Pos(0, 0, 0) * Rotation(90, 0, 0) * Cylinder(Rh, hw)

        body = base + flare + boss

        # --- inserto: collar saliente (+Y) + 2 prisioneros ---
        cor, cw = 0.66 * d, 0.36 * d
        cy = hw / 2.0 + cw / 2.0 - 2.0
        body = body + Pos(0, cy, 0) * Rotation(90, 0, 0) * Cylinder(cor, cw)
        for ang in (40.0, -40.0):
            a = math.radians(ang)
            body = body + Pos(cor * math.sin(a), cy, cor * math.cos(a)) * \
                Rotation(0, ang, 0) * Cylinder(0.09 * d, 0.5 * d)

        # --- grasera (niple de engrase) en el tope ---
        body = body + Pos(0, 0, Rh - 2.0) * Cylinder(0.085 * d, 0.55 * d)

        # --- barrenos: pernos ranurados en la base + barreno del eje ---
        for xf in (-J / 2.0, J / 2.0):
            slot = Pos(xf, 0, zb0 + s / 2.0) * Box(0.5 * N, N, s + 6.0)
            slot = slot + Pos(xf - 0.25 * N, 0, zb0 + s / 2.0) * Cylinder(N / 2.0, s + 6.0)
            slot = slot + Pos(xf + 0.25 * N, 0, zb0 + s / 2.0) * Cylinder(N / 2.0, s + 6.0)
            body = body - slot
        body = body - Pos(0, 0, 0) * Rotation(90, 0, 0) * Cylinder(d / 2.0, L)

        return body

    return build


def flange_bearing(d: float, flange: str, size_w: float, size_h: float,
                   bolt_span: float, N: float, Bi: float, s: float):
    """Chumacera de BRIDA (rodamiento de inserto en soporte embridado) para atornillar a
    una cara VERTICAL — eje PERPENDICULAR al plano de montaje. flange='cuadrada' → UCF
    (brida cuadrada, 4 pernos); flange='oval' → UCFL (brida oval, 2 pernos). Cotas
    comerciales (mm): d=Ø eje, size_w×size_h=brida (lado cuadrado / largo×ancho del óvalo),
    bolt_span=distancia entre centros de pernos, N=Ø agujero de perno, Bi=ancho del inserto,
    s=espesor de la brida. Reusa el inserto con collar+prisioneros+grasera de la UCP. Marco
    canónico: EJE del rodamiento a lo largo de Y, ORIGEN en el centro del barreno, brida en
    +Y (cara de montaje contra la pared), campana+inserto hacia -Y."""

    def build(_length=None):
        hw = Bi / 2.0
        boss_r = 1.08 * d                      # cubo del rodamiento (OD ~2.15·d)
        yc = hw + s / 2.0                       # centro de la placa (cara montaje en +Y)

        # --- brida (placa) en el plano X-Z, espesor s en Y ---
        if flange == "oval":
            plate = Pos(0, yc, 0) * Box(size_w - size_h, s, size_h)
            plate = plate + Pos(-(size_w - size_h) / 2.0, yc, 0) * Rotation(90, 0, 0) * Cylinder(size_h / 2.0, s)
            plate = plate + Pos((size_w - size_h) / 2.0, yc, 0) * Rotation(90, 0, 0) * Cylinder(size_h / 2.0, s)
            bolt_xz = [(-bolt_span / 2.0, 0.0), (bolt_span / 2.0, 0.0)]
        else:                                   # cuadrada (4 pernos)
            plate = Pos(0, yc, 0) * Box(size_w, s, size_h)
            h = bolt_span / 2.0
            bolt_xz = [(-h, -h), (h, -h), (-h, h), (h, h)]

        # --- cubo/campana del rodamiento (cilindro eje Y): del frente a dentro de la brida ---
        boss = Pos(0, s / 2.0, 0) * Rotation(90, 0, 0) * Cylinder(boss_r, Bi + s)
        body = plate + boss

        # --- inserto: collar saliente (-Y, frente) + 2 prisioneros ---
        cor, cw = 0.66 * d, 0.36 * d
        cy = -hw - cw / 2.0 + 2.0
        body = body + Pos(0, cy, 0) * Rotation(90, 0, 0) * Cylinder(cor, cw)
        for ang in (40.0, -40.0):
            a = math.radians(ang)
            body = body + Pos(cor * math.sin(a), cy, cor * math.cos(a)) * \
                Rotation(0, ang, 0) * Cylinder(0.09 * d, 0.5 * d)

        # --- grasera en el tope del cubo ---
        body = body + Pos(0, s / 2.0, boss_r - 2.0) * Cylinder(0.085 * d, 0.55 * d)

        # --- barrenos de perno (eje Y) + barreno del eje ---
        for bx, bz in bolt_xz:
            body = body - Pos(bx, yc, bz) * Rotation(90, 0, 0) * Cylinder(N / 2.0, s + 6.0)
        body = body - Pos(0, 0, 0) * Rotation(90, 0, 0) * Cylinder(d / 2.0, Bi + s + 20.0)

        return body

    return build


def endstop(d: float, altura: float, base_ancho: float, base_t: float):
    """Tope regulable: vástago cilíndrico (eje Z) sobre una base cuadrada."""

    def build(_length=None):
        stem = Cylinder(d / 2.0, altura)
        base = Pos(0, 0, -altura / 2.0 - base_t / 2.0) * Box(base_ancho, base_ancho, base_t)
        return stem + base

    return build


def leveling_foot(rosca: float, altura: float, disco_d: float, disco_t: float):
    """Pie nivelador: vástago roscado (eje Z) sobre un disco de apoyo."""

    def build(_length=None):
        stem = Cylinder(rosca / 2.0, altura)
        disk = Pos(0, 0, -altura / 2.0 - disco_t / 2.0) * Cylinder(disco_d / 2.0, disco_t)
        return stem + disk

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


def _hex_prism(across_flats: float, height: float):
    """Prisma hexagonal centrado en el origen, eje Z, dado el entrecaras (AF)."""
    from build123d import RegularPolygon, extrude

    r = across_flats / 2.0 / 0.8660254  # circunradio desde el entrecaras (AF/2 = apotema)
    return Pos(0, 0, -height / 2.0) * extrude(RegularPolygon(r, 6), height)


def hex_bolt(d: float, across_flats: float, head_h: float, shank: float = 50.0):
    """Perno de cabeza HEXAGONAL (DIN 933, rosca total modelada lisa): cabeza hex + vástago
    Ø=d. Eje Z; vástago centrado en el origen, cabeza en +Z. `length` (al cortar) = largo del
    vástago (así el tensor lo dimensiona). AF = entrecaras de la cabeza, head_h = altura cabeza."""

    def build(length=None):
        L = float(length) if length else shank
        shaft = Pos(0, 0, -L / 2.0) * Cylinder(d / 2.0, L)  # vástago hacia -Z (tope en el origen)
        head = Pos(0, 0, head_h / 2.0) * _hex_prism(across_flats, head_h)  # cabeza en +Z desde el origen
        return shaft + head  # origen = cara inferior de la cabeza = inicio del vástago

    return build


def hex_nut(d: float, across_flats: float, thickness: float):
    """Tuerca HEXAGONAL (DIN 934): prisma hexagonal con agujero Ø=d (rosca modelada lisa).
    Eje Z, centrada en el origen; AF = entrecaras, thickness = altura (m)."""

    def build(_length=None):
        return _hex_prism(across_flats, thickness) - Cylinder(d / 2.0, thickness + 2.0)

    return build


def socket_cap(d: float, shank: float = 50.0):
    """Tornillo de cabeza cilíndrica con HEXÁGONO INTERIOR (Allen / DIN 912): cabeza Ø≈1.5·d con
    hueco hexagonal arriba para llave Allen, + vástago Ø=d (rosca modelada lisa). Eje Z; vástago
    hacia -Z; origen en la cara inferior de la cabeza. `length` (al cortar) = largo del vástago.
    Cabeza y llave se derivan de d (head Ø=1.5d, alto≈d, llave AF≈0.85d)."""
    head_d = 1.5 * d
    head_h = d                          # cabeza cilíndrica ≈ d de alto (DIN 912)
    key_af = round(0.85 * d)            # entrecaras de la llave Allen (M10→8/9, M12→10, M16→14, M20→17)

    def build(length=None):
        L = float(length) if length else shank
        shaft = Pos(0, 0, -L / 2.0) * Cylinder(d / 2.0, L)             # vástago hacia -Z
        head = Pos(0, 0, head_h / 2.0) * Cylinder(head_d / 2.0, head_h)  # cabeza cilíndrica en +Z
        depth = 0.55 * head_h
        head = head - Pos(0, 0, head_h - depth / 2.0) * _hex_prism(key_af, depth)  # hueco Allen arriba
        return shaft + head  # origen = cara inferior de la cabeza = inicio del vástago

    return build


def round_tube(od: float, wall: float):
    """Tubo redondo de acero HUECO, eje Z, cortable a lo largo de Z.
    od = Ø exterior, wall = espesor de pared. Pareja redonda de `rect_tube`."""

    def build(length):
        outer = Cylinder(od / 2.0, length)
        if 0.0 < wall < od / 2.0:
            outer = outer - Cylinder(od / 2.0 - wall, length)
        return outer

    return build


def angle(leg: float, t: float):
    """Ángulo de acero de lados iguales (perfil L), cortable a lo largo de Z.
    Sección en XY centrada en su caja; leg = lado, t = espesor."""

    def build(length):
        horiz = Pos(0, -leg / 2.0 + t / 2.0, 0) * Box(leg, t, length)
        vert = Pos(-leg / 2.0 + t / 2.0, 0, 0) * Box(t, leg, length)
        return horiz + vert

    return build


def channel(h: float, b: float, tw: float, tf: float):
    """Perfil U / canal (tipo UPN, prismático simplificado sin conicidad), cortable en Z.
    h = altura (alma, Y), b = ancho de ala (X), tw = espesor de alma, tf = espesor de ala."""

    def build(length):
        web = Pos(-b / 2.0 + tw / 2.0, 0, 0) * Box(tw, h, length)
        top = Pos(0, h / 2.0 - tf / 2.0, 0) * Box(b, tf, length)
        bot = Pos(0, -h / 2.0 + tf / 2.0, 0) * Box(b, tf, length)
        return web + top + bot

    return build


def i_beam(h: float, b: float, tw: float, tf: float):
    """Viga doble T (tipo IPE/IPN, prismático simplificado), cortable a lo largo de Z.
    h = altura (Y), b = ancho de ala (X), tw = espesor de alma, tf = espesor de ala."""

    def build(length):
        web = Box(tw, h, length)
        top = Pos(0, h / 2.0 - tf / 2.0, 0) * Box(b, tf, length)
        bot = Pos(0, -h / 2.0 + tf / 2.0, 0) * Box(b, tf, length)
        return web + top + bot

    return build


# ----------------------------------------------------------- carpintería / herraje
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


def wood_screw(d: float = 4.0, length: float = 40.0, head_d: float = 8.0):
    """Tirafondo / tornillo de madera (cabeza avellanada plana), por revolución (eje Z):
    punta cónica + vástago + cabeza avellanada. length = largo bajo cabeza."""

    def build(_length=None):
        head_h = (head_d - d) / 2.0
        total = length + head_h
        z_top, z_tip = total / 2.0, -total / 2.0
        pts = [
            (0, z_tip), (d / 2.0, z_tip + d), (d / 2.0, z_top - head_h),
            (head_d / 2.0, z_top), (0, z_top),
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


BUILDERS = {
    "profile": profile,
    "rect_tube": rect_tube,  # tubo estructural rectangular de acero (hueco)
    "cylinder": cylinder,
    "roller": roller,  # rodillo con eje pasante
    "drum": drum,  # tambor/polea motriz con eje
    "box": box,
    "motor": motor,
    "worm_gearmotor": worm_gearmotor,  # motorreductor sinfín-corona NMRV, eje hueco + motor perpendicular (frame IEC real)
    "leg": leg,
    "guard": guard,
    "sensor": sensor,
    "bearing": bearing,
    "screw": screw,
    "linear_rail": linear_rail,
    "linear_block": linear_block,
    "pulley": pulley,
    "v_pulley": v_pulley,  # polea en V (sheave) para faja de potencia, sección A/B (ISO 4183)
    "pillow_block": pillow_block,      # chumacera de pie UCP
    "flange_bearing": flange_bearing,  # chumacera de brida UCF/UCFL
    "endstop": endstop,
    "leveling_foot": leveling_foot,
    "tensioner": tensioner,
    "take_up": take_up,  # tensor tipo trotadora (faja de banda, sin chumacera)
    "hex_bolt": hex_bolt,  # perno cabeza hexagonal DIN 933 (comercial)
    "hex_nut": hex_nut,  # tuerca hexagonal DIN 934
    "socket_cap": socket_cap,  # tornillo Allen (cabeza cilíndrica + hexágono interior) DIN 912
    "round_tube": round_tube,  # tubo redondo de acero (hueco)
    "angle": angle,  # ángulo L de lados iguales
    "channel": channel,  # perfil U / canal (UPN)
    "i_beam": i_beam,  # viga doble T (IPE/IPN)
    # carpintería / herraje
    "butt_hinge": butt_hinge,  # bisagra de pala (libro)
    "butt_hinge_half": butt_hinge_half,  # media bisagra (articulación fiel: 2 mitades)
    "spring_hinge": spring_hinge,  # bisagra de resorte / soft-close
    "mortise_lock": mortise_lock,  # cerradura de embutir
    "magnetic_catch": magnetic_catch,  # tope/cierre magnético
    "piano_hinge": piano_hinge,  # bisagra continua (piano), cortable
    "euro_hinge": euro_hinge,  # bisagra europea de cazoleta (mueble)
    "pull_handle": pull_handle,  # tirador de barra
    "knob": knob,  # pomo
    "wood_screw": wood_screw,  # tirafondo
    "drawer_slide": drawer_slide,  # corredera de cajón, cortable
    "door_rail": door_rail,  # riel U para puerta corrediza/colgante (U-100), cortable
    "door_carriage": door_carriage,  # corredera colgante de 4 ruedas (D-100)
}
