"""Chapa metálica: base + pestañas plegadas (con MULTI-PLIEGUE, V5.5) y su
DESPLEGADO (flat pattern) para corte láser.

3D: pliegue vivo (cajas unidas) — robusto y determinista; el radio se usa solo en
el desarrollo. Desplegado: bend allowance estándar → contorno en cruz + líneas de
plegado, sobre el SheetModel que ya exportan svg.py/dxf.py.

Lados → ejes (Z arriba, base centrada en XY, cara inferior en z=0):
  frente=+Y · atras=−Y · izquierda=−X · derecha=+X

V5.5 — pestañas ricas (`flaps`): cada pestaña puede llevar taladros y RECORTES
rectangulares propios, y UNA pestaña hija (2º pliegue en su borde libre: perfiles
C/Z, solapas, hem de rigidez). Convención de coordenadas LOCALES de pestaña:
  u = mm a lo largo de la línea de pliegue, 0 en el centro, alineada con el eje
      MUNDIAL (+X en frente/atras, +Y en izquierda/derecha) — igual que los holes
      de la base, sin espejos.
  v = mm desde el BORDE LIBRE de la pestaña hacia el pliegue, medida sobre la
      cara. Es la métrica en la que el 3D de pliegue vivo y el desarrollo
      COINCIDEN exactamente sin conocer el radio.
Un hole/cutout que invade la zona de pliegue se RECHAZA (desplegar el arco queda
fuera de alcance). El K-FACTOR puede resolverse POR MATERIAL (tabla de doblado al
aire, r/t≈1 — valores medios de taller; el K real depende de proceso/herramienta).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from apolo.drawing.sheet import Circle, Label, Line, Polygon, SheetModel, _dim_h, _dim_v

MARGIN = 15.0

# K-factor por material (doblado al aire, r/t≈1; tablas de taller estándar).
# El acero conserva el 0.40 histórico → retro-compatible con proyectos guardados.
K_FACTOR_BY_MATERIAL = {
    "acero": 0.40,
    "acero inoxidable": 0.45,
    "aluminio": 0.35,
    "laton": 0.35,
}
K_FACTOR_DEFAULT = 0.40


def k_for_material(material: str | None) -> float:
    """K-factor según el material resuelto de la pieza (default 0.40)."""
    from .materials import _norm

    return K_FACTOR_BY_MATERIAL.get(_norm(material or ""), K_FACTOR_DEFAULT)


def bend(angulo: float, r: float, t: float, k: float) -> tuple[float, float, float]:
    """Devuelve (BA, OSSB, BD) para una pestaña que forma `angulo`° con la base.
    El ángulo de DOBLADO es θ = 180 − angulo (90° de pestaña ⇒ doblar 90°)."""
    theta = 180.0 - angulo
    th = math.radians(theta)
    ba = th * (r + k * t)               # bend allowance (arco de la fibra neutra)
    ossb = (r + t) * math.tan(th / 2.0)  # outside setback
    bd = 2.0 * ossb - ba                 # bend deduction
    return ba, ossb, bd


# --------------------------------------------------------- pestañas ricas (V5.5)
@dataclass
class Child:
    """Pestaña hija (2º pliegue en el borde libre de la padre)."""

    altura: float
    angulo: float = 90.0
    radio: float | None = None           # None → radio de la padre
    direccion: str = "interior"          # interior=C (hacia la base) · exterior=Z
    holes: list[tuple] = field(default_factory=list)    # (u, v, d)
    cutouts: list[tuple] = field(default_factory=list)  # (u, v, ancho, alto)


@dataclass
class Flap:
    """Pestaña de primer nivel con features propias."""

    lado: str
    altura: float
    angulo: float = 90.0
    radio: float | None = None           # None → radio global
    holes: list[tuple] = field(default_factory=list)
    cutouts: list[tuple] = field(default_factory=list)
    child: Child | None = None


def flaps_from_specs(specs) -> list[Flap] | None:
    """Convierte los FlapSpec pydantic del comando (duck-typed: solo atributos) a
    los dataclasses de la librería. Lista vacía/None → None (vía simple)."""
    if not specs:
        return None
    out: list[Flap] = []
    for f in specs:
        child = None
        if getattr(f, "child", None) is not None:
            c = f.child
            child = Child(
                altura=c.altura, angulo=c.angulo, radio=c.radio, direccion=c.direccion,
                holes=[(h.u, h.v, h.d) for h in c.holes],
                cutouts=[(q.u, q.v, q.ancho, q.alto) for q in c.cutouts],
            )
        out.append(Flap(
            lado=f.lado, altura=f.altura, angulo=f.angulo, radio=f.radio,
            holes=[(h.u, h.v, h.d) for h in f.holes],
            cutouts=[(q.u, q.v, q.ancho, q.alto) for q in f.cutouts],
            child=child,
        ))
    return out


def _normalize_flaps(
    lados: list[str], altura: float, angulo: float, flaps: list[Flap] | None
) -> list[Flap]:
    """Vía simple (lados/altura/angulo) → lista de Flap. Si `flaps` viene, manda."""
    if flaps:
        seen = set()
        for f in flaps:
            if f.lado in seen:
                raise ValueError(f"Pestaña duplicada en el lado '{f.lado}'")
            seen.add(f.lado)
        return list(flaps)
    return [Flap(lado=lado, altura=altura, angulo=angulo) for lado in lados]


def _flap_length(flap: Flap, ancho: float, fondo: float) -> float:
    return ancho if flap.lado in ("frente", "atras") else fondo


def _validate_features(flap: Flap, espesor: float, k: float, radio_global: float,
                       length: float) -> None:
    """Dominios de holes/cutouts (v desde el borde libre; nunca en zona de pliegue)."""
    r_p = flap.radio if flap.radio is not None else radio_global
    _, ossb_p, _ = bend(flap.angulo, r_p, espesor, k)
    ossb_c = 0.0
    if flap.child is not None:
        r_c = flap.child.radio if flap.child.radio is not None else r_p
        _, ossb_c, _ = bend(flap.child.angulo, r_c, espesor, k)
        if flap.altura <= ossb_p + ossb_c + 0.5:
            raise ValueError(
                f"La pestaña '{flap.lado}' (altura {flap.altura:g}) no da para su "
                f"pliegue hijo: necesita > {ossb_p + ossb_c + 0.5:g} mm"
            )
    elif flap.altura <= ossb_p:
        raise ValueError(
            f"La pestaña '{flap.lado}' (altura {flap.altura:g}) es menor que su "
            f"retroceso de pliegue ({ossb_p:g} mm)"
        )

    def _dom(items, alto_of, cara_lo, cara_hi, donde):
        for it in items:
            u, v, half_u, half_v = it
            if v - half_v < cara_lo - 1e-6 or v + half_v > cara_hi + 1e-6:
                raise ValueError(
                    f"El recorte/taladro en {donde} de '{flap.lado}' (v={v:g}) invade "
                    f"la zona de pliegue: v válido ∈ [{cara_lo + half_v:g}, "
                    f"{cara_hi - half_v:g}] (v se mide desde el borde libre)"
                )
            if abs(u) + half_u > length / 2.0 + 1e-6:
                raise ValueError(
                    f"El recorte/taladro en {donde} de '{flap.lado}' (u={u:g}) se sale "
                    f"del ancho de la pestaña (|u| ≤ {length / 2.0 - half_u:g})"
                )

    # cara útil de la PADRE: v ∈ [ossb_c, altura − ossb_p] (v desde el borde libre)
    items_p = [(u, v, d / 2.0, d / 2.0) for (u, v, d) in flap.holes]
    items_p += [(u, v, w / 2.0, h / 2.0) for (u, v, w, h) in flap.cutouts]
    _dom(items_p, None, ossb_c, flap.altura - ossb_p, "la pestaña")
    if flap.child is not None:
        r_c = flap.child.radio if flap.child.radio is not None else r_p
        _, ossb_c2, _ = bend(flap.child.angulo, r_c, espesor, k)
        items_c = [(u, v, d / 2.0, d / 2.0) for (u, v, d) in flap.child.holes]
        items_c += [(u, v, w / 2.0, h / 2.0) for (u, v, w, h) in flap.child.cutouts]
        _dom(items_c, None, 0.0, flap.child.altura - ossb_c2, "el pliegue hijo")


# ------------------------------------------------------------------ 3D plegado
def _fillet_bends(result, ancho, fondo, espesor, altura, lados, radio):
    """Redondea (best-effort) las aristas cóncavas del pliegue base↔pestaña. Si la
    selección o el fillet fallan, devuelve el sólido vivo sin tocar (la pieza nunca
    se rompe; el desplegado ya incorpora el radio en el bend allowance). Los
    pliegues HIJO quedan vivos (fallback documentado)."""
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


# flip del sentido "interior" del hijo por lado (canónico: interior = −y local)
_FLIP = {"frente": 1.0, "atras": -1.0, "izquierda": 1.0, "derecha": -1.0}


def _canonical_wall(flap: Flap, length: float, espesor: float):
    """Ensamblaje LOCAL de una pestaña (muro a lo largo de X, base en z=0, borde
    libre en z=altura; espesor en ±y/2): muro + hijo + cortes de holes/cutouts.
    La colocación por lado aplica después UNA transformación rígida."""
    from build123d import Box, Cylinder, Pos, Rotation

    wall = Pos(0, 0, flap.altura / 2.0) * Box(length, espesor, flap.altura)

    def _cutters(items_holes, items_cuts, top_z):
        cuts = []
        for u, v, d in items_holes:
            cuts.append(Pos(u, 0, top_z - v) * Rotation(90, 0, 0) * Cylinder(d / 2.0, espesor + 2.0))
        for u, v, w, h in items_cuts:
            cuts.append(Pos(u, 0, top_z - v) * Box(w, espesor + 2.0, h))
        return cuts

    for c in _cutters(flap.holes, flap.cutouts, flap.altura):
        wall = wall - c

    if flap.child is not None:
        ch = flap.child
        theta_c = 180.0 - ch.angulo
        dir_sign = 1.0 if ch.direccion == "interior" else -1.0
        flip = _FLIP[flap.lado]
        child_raw = Pos(0, 0, ch.altura / 2.0) * Box(length, espesor, ch.altura)
        for c in _cutters(ch.holes, ch.cutouts, ch.altura):
            child_raw = child_raw - c
        # continuar hacia arriba desde el borde libre y doblar θc sobre su línea media
        child = (
            Pos(0, 0, flap.altura)
            * Rotation(dir_sign * flip * theta_c, 0, 0)
            * child_raw
        )
        wall = wall + child
    return wall


def sheet_metal_solid(
    ancho: float, fondo: float, espesor: float, lados: list[str],
    altura: float, angulo: float, radio: float, holes=None,
    flaps: list[Flap] | None = None, k_factor: float = K_FACTOR_DEFAULT,
):
    from build123d import Box, Cylinder, Pos, Rotation

    if radio >= ancho / 2 or radio >= fondo / 2:
        raise ValueError("El radio de plegado es demasiado grande para la base")

    the_flaps = _normalize_flaps(lados, altura, angulo, flaps)
    for f in the_flaps:
        _validate_features(f, espesor, k_factor, radio, _flap_length(f, ancho, fondo))

    result = Pos(0, 0, espesor / 2.0) * Box(ancho, fondo, espesor)  # base, cara inferior en z=0

    for f in the_flaps:
        length = _flap_length(f, ancho, fondo)
        wall = _canonical_wall(f, length, espesor)
        delta = f.angulo - 90.0  # inclinación respecto a la vertical
        if f.lado in ("frente", "atras"):
            sign = 1.0 if f.lado == "frente" else -1.0
            pivot_y = sign * (fondo / 2.0 - espesor / 2.0)
            wall = Pos(0, pivot_y, espesor) * Rotation(-sign * delta, 0, 0) * wall
        else:  # izquierda / derecha: canónico girado 90° sobre Z (u → +Y mundo)
            sign = 1.0 if f.lado == "derecha" else -1.0
            pivot_x = sign * (ancho / 2.0 - espesor / 2.0)
            wall = (
                Pos(pivot_x, 0, espesor)
                * Rotation(0, sign * delta, 0)
                * Rotation(0, 0, 90)
                * wall
            )
        result = result + wall

    lados_presentes = [f.lado for f in the_flaps]
    radios = [f.radio if f.radio is not None else radio for f in the_flaps]
    if any(r > 0 for r in radios) and the_flaps:
        alt_min = min(f.altura for f in the_flaps)
        result = _fillet_bends(result, ancho, fondo, espesor, alt_min,
                               lados_presentes, max(radios))

    for hx, hy, hd in holes or []:
        if abs(hx) + hd / 2.0 > ancho / 2.0 + 1e-6 or abs(hy) + hd / 2.0 > fondo / 2.0 + 1e-6:
            raise ValueError(f"El taladro ({hx:g}, {hy:g}) Ø{hd:g} se sale de la base")
        result = result - Pos(hx, hy, espesor / 2.0) * Cylinder(hd / 2.0, espesor + 2.0)
    return result


# -------------------------------------------------------------- desplegado 2D
@dataclass
class _SideDev:
    """Desarrollo de un lado: strip más allá del pliegue + features proyectadas."""

    strip: float = 0.0        # ancho desarrollado más allá de la línea de pliegue
    ossb: float = 0.0         # retroceso que RECORTA la base
    present: bool = False
    child_fold: float | None = None      # distancia pliegue-hijo desde la línea de pliegue
    holes: list = field(default_factory=list)     # (u, offset_desde_pliegue, d)
    cutouts: list = field(default_factory=list)   # (u, offset, ancho, alto)


def _side_dev(flap: Flap | None, espesor: float, k: float, radio_global: float) -> _SideDev:
    if flap is None:
        return _SideDev()
    r_p = flap.radio if flap.radio is not None else radio_global
    ba_p, ossb_p, _ = bend(flap.angulo, r_p, espesor, k)
    dev = _SideDev(present=True, ossb=ossb_p)
    if flap.child is None:
        dev.strip = (flap.altura - ossb_p) + ba_p  # misma aritmética que la vía clásica
        parent_face_end = dev.strip
    else:
        ch = flap.child
        r_c = ch.radio if ch.radio is not None else r_p
        ba_c, ossb_c, _ = bend(ch.angulo, r_c, espesor, k)
        lp = flap.altura - ossb_p - ossb_c
        dev.child_fold = ba_p + lp
        dev.strip = ba_p + lp + ba_c + (ch.altura - ossb_c)
        parent_face_end = ba_p + lp
        # features del HIJO: v desde SU borde libre → offset = strip_total − v
        for u, v, d in ch.holes:
            dev.holes.append((u, dev.strip - v, d))
        for u, v, w, h in ch.cutouts:
            dev.cutouts.append((u, dev.strip - v, w, h))
    # features de la PADRE: offset = BA_p + (altura_p − OSSB_p) − v
    for u, v, d in flap.holes:
        dev.holes.append((u, ba_p + (flap.altura - ossb_p) - v, d))
    for u, v, w, h in flap.cutouts:
        dev.cutouts.append((u, ba_p + (flap.altura - ossb_p) - v, w, h))
    return dev


def _axis_blank_dev(dim_base: float, lo: _SideDev, hi: _SideDev):
    """Recorre un eje: (total, base_lo, base_hi) con strips por lado."""
    base_lo = lo.strip if lo.present else 0.0
    base_flat = dim_base - (lo.ossb if lo.present else 0.0) - (hi.ossb if hi.present else 0.0)
    base_hi = base_lo + base_flat
    total = base_hi + (hi.strip if hi.present else 0.0)
    return total, base_lo, base_hi


def flat_pattern(
    name: str, ancho: float, fondo: float, espesor: float, lados: list[str],
    altura: float, angulo: float, radio: float, k_factor: float, holes=None,
    flaps: list[Flap] | None = None,
) -> SheetModel:
    the_flaps = _normalize_flaps(lados, altura, angulo, flaps)
    for f in the_flaps:
        _validate_features(f, espesor, k_factor, radio, _flap_length(f, ancho, fondo))
    by_side = {f.lado: f for f in the_flaps}

    dev = {
        side: _side_dev(by_side.get(side), espesor, k_factor, radio)
        for side in ("frente", "atras", "izquierda", "derecha")
    }
    left, right = dev["izquierda"], dev["derecha"]
    back, front = dev["atras"], dev["frente"]

    tx, bx0, bx1 = _axis_blank_dev(ancho, left, right)
    ty, by0, by1 = _axis_blank_dev(fondo, back, front)

    ox = oy = MARGIN
    bx0 += ox; bx1 += ox; by0 += oy; by1 += oy
    x_lo, x_hi = ox, ox + tx
    y_lo, y_hi = oy, oy + ty

    # contorno en cruz (un único anillo; el pliegue hijo solo ALARGA el brazo)
    ring: list[tuple[float, float]] = [(bx0, by0)]
    ring += [(bx0, y_lo), (bx1, y_lo), (bx1, by0)] if back.present else [(bx1, by0)]
    ring += [(x_hi, by0), (x_hi, by1), (bx1, by1)] if right.present else [(bx1, by1)]
    ring += [(bx1, y_hi), (bx0, y_hi), (bx0, by1)] if front.present else [(bx0, by1)]
    ring += [(x_lo, by1), (x_lo, by0), (bx0, by0)] if left.present else [(bx0, by0)]

    model = SheetModel(tx + 2 * MARGIN, ty + 2 * MARGIN)
    model.polygons.append(Polygon([ring], "corte"))

    # líneas de plegado (discontinuas) en los bordes de la base
    if left.present:
        model.lines.append(Line(bx0, by0, bx0, by1, "hidden"))
    if right.present:
        model.lines.append(Line(bx1, by0, bx1, by1, "hidden"))
    if back.present:
        model.lines.append(Line(bx0, by0, bx1, by0, "hidden"))
    if front.present:
        model.lines.append(Line(bx0, by1, bx1, by1, "hidden"))

    cx, cy = (bx0 + bx1) / 2.0, (by0 + by1) / 2.0

    # por lado: línea de pliegue del hijo + holes/cutouts proyectados.
    # (eje_u, base de partida, signo del offset hacia fuera del blank)
    frames = {
        "frente": ("x", by1, +1.0),
        "atras": ("x", by0, -1.0),
        "derecha": ("y", bx1, +1.0),
        "izquierda": ("y", bx0, -1.0),
    }
    for side, d in dev.items():
        if not d.present:
            continue
        axis_u, origin, s = frames[side]
        if d.child_fold is not None:
            pos = origin + s * d.child_fold
            if axis_u == "x":
                model.lines.append(Line(bx0, pos, bx1, pos, "hidden"))
            else:
                model.lines.append(Line(pos, by0, pos, by1, "hidden"))
        for u, off, hd in d.holes:
            if axis_u == "x":
                model.circles.append(Circle(cx + u, origin + s * off, hd / 2.0, "corte"))
            else:
                model.circles.append(Circle(origin + s * off, cy + u, hd / 2.0, "corte"))
        for u, off, w, h in d.cutouts:
            if axis_u == "x":
                x0, x1 = cx + u - w / 2.0, cx + u + w / 2.0
                y0, y1 = origin + s * off - h / 2.0, origin + s * off + h / 2.0
            else:
                x0, x1 = origin + s * off - h / 2.0, origin + s * off + h / 2.0
                y0, y1 = cy + u - w / 2.0, cy + u + w / 2.0
            model.polygons.append(
                Polygon([[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]], "corte")
            )

    # taladros de la base: la base 3D está centrada en XY → su centro es (cx, cy)
    for hx, hy, hd in holes or []:
        model.circles.append(Circle(cx + hx, cy + hy, hd / 2.0, "corte"))

    _dim_h(model, x_lo, y_lo, tx, round(tx, 1))
    _dim_v(model, x_lo, y_lo, ty, round(ty, 1))
    model.labels.append(
        Label((x_lo + x_hi) / 2, y_hi + 6,
              f"{name} · desplegado · e={espesor:g} mm · K={k_factor:g}", 3.4)
    )
    model.meta = {"blank": [round(tx, 2), round(ty, 2)], "espesor": espesor, "k": k_factor}
    return model
