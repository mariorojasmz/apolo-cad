"""Chapa metálica: pieza tipo bandeja (base + pestañas plegadas) y su DESPLEGADO
(flat pattern) para corte láser.

3D: pliegue vivo (cajas unidas) — robusto y determinista; el radio se usa solo en
el desarrollo. Desplegado: bend allowance estándar → contorno en cruz + líneas de
plegado, sobre el SheetModel que ya exportan svg.py/dxf.py.

Lados → ejes (Z arriba, base centrada en XY, cara inferior en z=0):
  frente=+Y · atras=−Y · izquierda=−X · derecha=+X
"""

from __future__ import annotations

import math

from apolo.drawing.sheet import Circle, Label, Line, Polygon, SheetModel, _dim_h, _dim_v

MARGIN = 15.0


def bend(angulo: float, r: float, t: float, k: float) -> tuple[float, float, float]:
    """Devuelve (BA, OSSB, BD) para una pestaña que forma `angulo`° con la base.
    El ángulo de DOBLADO es θ = 180 − angulo (90° de pestaña ⇒ doblar 90°)."""
    theta = 180.0 - angulo
    th = math.radians(theta)
    ba = th * (r + k * t)               # bend allowance (arco de la fibra neutra)
    ossb = (r + t) * math.tan(th / 2.0)  # outside setback
    bd = 2.0 * ossb - ba                 # bend deduction
    return ba, ossb, bd


# ------------------------------------------------------------------ 3D plegado
def _fillet_bends(result, ancho, fondo, espesor, altura, lados, radio):
    """Redondea (best-effort) las aristas cóncavas del pliegue. Si la selección o
    el fillet fallan, devuelve el sólido vivo sin tocar (la pieza nunca se rompe;
    el desplegado ya incorpora el radio en el bend allowance)."""
    from build123d import Axis, fillet

    eps = 0.5
    r = min(radio, max(0.3, altura - 1.0))
    edges = []
    for lado in lados:
        if lado in ("frente", "atras"):
            sign = 1.0 if lado == "frente" else -1.0
            y_in = sign * (fondo / 2.0 - espesor)
            cand = (
                result.edges().filter_by(Axis.X)
                .filter_by_position(Axis.Z, espesor - eps, espesor + eps)
                .filter_by_position(Axis.Y, y_in - eps, y_in + eps)
            )
        else:
            sign = 1.0 if lado == "derecha" else -1.0
            x_in = sign * (ancho / 2.0 - espesor)
            cand = (
                result.edges().filter_by(Axis.Y)
                .filter_by_position(Axis.Z, espesor - eps, espesor + eps)
                .filter_by_position(Axis.X, x_in - eps, x_in + eps)
            )
        edges += list(cand)
    if not edges:
        return result
    try:
        out = fillet(edges, radius=r)
        if out is not None and out.volume > 0:
            return out
    except Exception:  # noqa: BLE001 — pliegue vivo es un fallback válido
        pass
    return result


def sheet_metal_solid(
    ancho: float, fondo: float, espesor: float, lados: list[str],
    altura: float, angulo: float, radio: float, holes=None,
):
    from build123d import Box, Cylinder, Pos, Rotation

    if radio >= ancho / 2 or radio >= fondo / 2:
        raise ValueError("El radio de plegado es demasiado grande para la base")

    result = Pos(0, 0, espesor / 2.0) * Box(ancho, fondo, espesor)  # base, cara inferior en z=0
    delta = angulo - 90.0  # inclinación respecto a la vertical

    def wall_up(length: float):
        return Pos(0, 0, altura / 2.0) * Box(length, espesor, altura)  # muro vertical, base en z=0

    for lado in lados:
        if lado in ("frente", "atras"):
            sign = 1.0 if lado == "frente" else -1.0
            pivot_y = sign * (fondo / 2.0 - espesor / 2.0)
            wall = Pos(0, pivot_y, espesor) * Rotation(-sign * delta, 0, 0) * wall_up(ancho)
        else:  # izquierda / derecha (muro a lo largo de Y)
            sign = 1.0 if lado == "derecha" else -1.0
            pivot_x = sign * (ancho / 2.0 - espesor / 2.0)
            wall_y = Pos(0, 0, altura / 2.0) * Box(espesor, fondo, altura)
            wall = Pos(pivot_x, 0, espesor) * Rotation(0, sign * delta, 0) * wall_y
        result = result + wall

    if radio > 0 and lados:
        result = _fillet_bends(result, ancho, fondo, espesor, altura, lados, radio)

    for hx, hy, hd in holes or []:
        if abs(hx) + hd / 2.0 > ancho / 2.0 + 1e-6 or abs(hy) + hd / 2.0 > fondo / 2.0 + 1e-6:
            raise ValueError(f"El taladro ({hx:g}, {hy:g}) Ø{hd:g} se sale de la base")
        result = result - Pos(hx, hy, espesor / 2.0) * Cylinder(hd / 2.0, espesor + 2.0)
    return result


# -------------------------------------------------------------- desplegado 2D
def _axis_blank(dim_base: float, lo: bool, hi: bool, altura: float, ba: float, ossb: float):
    """Recorre un eje: devuelve (total, base_lo, base_hi, flap_lo_w, flap_hi_w).
    base_lo/base_hi = posiciones de las líneas de plegado (bordes de la base)."""
    flap = (altura - ossb) + ba  # ancho de la solapa desarrollada más allá del pliegue
    base_lo = flap if lo else 0.0
    base_flat = dim_base - (ossb if lo else 0.0) - (ossb if hi else 0.0)
    base_hi = base_lo + base_flat
    total = base_hi + (flap if hi else 0.0)
    return total, base_lo, base_hi, (flap if lo else 0.0), (flap if hi else 0.0)


def flat_pattern(
    name: str, ancho: float, fondo: float, espesor: float, lados: list[str],
    altura: float, angulo: float, radio: float, k_factor: float, holes=None,
) -> SheetModel:
    ba, ossb, _bd = bend(angulo, radio, espesor, k_factor)
    left, right = "izquierda" in lados, "derecha" in lados
    back, front = "atras" in lados, "frente" in lados

    tx, bx0, bx1, _, _ = _axis_blank(ancho, left, right, altura, ba, ossb)
    ty, by0, by1, _, _ = _axis_blank(fondo, back, front, altura, ba, ossb)

    ox = oy = MARGIN
    bx0 += ox; bx1 += ox; by0 += oy; by1 += oy
    x_lo, x_hi = ox, ox + tx
    y_lo, y_hi = oy, oy + ty

    # contorno en cruz (un único anillo, recorrido perimetral continuo)
    ring: list[tuple[float, float]] = [(bx0, by0)]
    ring += [(bx0, y_lo), (bx1, y_lo), (bx1, by0)] if back else [(bx1, by0)]
    ring += [(x_hi, by0), (x_hi, by1), (bx1, by1)] if right else [(bx1, by1)]
    ring += [(bx1, y_hi), (bx0, y_hi), (bx0, by1)] if front else [(bx0, by1)]
    ring += [(x_lo, by1), (x_lo, by0), (bx0, by0)] if left else [(bx0, by0)]

    model = SheetModel(tx + 2 * MARGIN, ty + 2 * MARGIN)
    model.polygons.append(Polygon([ring], "corte"))

    # líneas de plegado (discontinuas) en los bordes de la base
    if left:
        model.lines.append(Line(bx0, by0, bx0, by1, "hidden"))
    if right:
        model.lines.append(Line(bx1, by0, bx1, by1, "hidden"))
    if back:
        model.lines.append(Line(bx0, by0, bx1, by0, "hidden"))
    if front:
        model.lines.append(Line(bx0, by1, bx1, by1, "hidden"))

    # taladros: la base 3D está centrada en XY → su centro en el blank es (cx, cy)
    cx, cy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0
    for hx, hy, hd in holes or []:
        model.circles.append(Circle(cx + hx, cy + hy, hd / 2.0, "corte"))

    _dim_h(model, x_lo, y_lo, tx, round(tx, 1))
    _dim_v(model, x_lo, y_lo, ty, round(ty, 1))
    model.labels.append(
        Label((x_lo + x_hi) / 2, y_hi + 6, f"{name} · desplegado · e={espesor:g} mm", 3.4)
    )
    model.meta = {"blank": [round(tx, 2), round(ty, 2)], "espesor": espesor}
    return model
