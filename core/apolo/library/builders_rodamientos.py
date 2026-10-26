"""Rodamientos, soportes y guiado del catálogo: rodamiento rígido, chumaceras de pie (UCP) y
de brida (UCF/UCFL), riel y carro lineal, tope regulable y sensor con soporte.

La fachada `builders.py` re-exporta cada nombre por IDENTIDAD y conserva `BUILDERS`
(plan `docs/plans/partir-nucleo-congelado-ii.md`, F1). Contrato de cada builder: una
*factory* `(**params) -> ((length|None) -> shape)`, forma centrada, Z arriba.
"""

from __future__ import annotations

import math

from build123d import Box, Cylinder, Pos, Rotation

from apolo.kernel.shapes import make_revolution


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
