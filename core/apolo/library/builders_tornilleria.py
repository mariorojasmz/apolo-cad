"""TORNILLERÍA del catálogo: prisma hexagonal (`_hex_prism`, lo usan también
`builders_fijacion.py` y los de aquí), perno y tuerca hexagonales, tornillo Allen DIN 912
(liso y con hexágono interior) y tirafondo.

La fachada `builders.py` re-exporta cada nombre por IDENTIDAD y conserva `BUILDERS`
(plan `docs/plans/partir-nucleo-congelado-ii.md`, F1). Contrato de cada builder: una
*factory* `(**params) -> ((length|None) -> shape)`, forma centrada, Z arriba.
"""

from __future__ import annotations

from build123d import Cylinder, Pos

from apolo.kernel.shapes import make_revolution


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
