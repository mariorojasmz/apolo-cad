"""Corte a INGLETE de miembros de perfil (V5.8) — geometría pura.

El corte es el plano BISECTOR de los dos miembros pasando por el NODO: ambos
comparten exactamente el mismo plano (casado perfecto) y la fórmula generaliza a
cualquier ángulo θ y azimut φ. El miembro se construye en su MARCO LOCAL (perfil
extruido en Z, nodos en ±span/2) y se recorta ANTES del place global → la base se
cachea por (ref, span, α@φ por extremo) con formato de clave propio ``|mtr|`` que
jamás colisiona con un miembro recto.

Propiedad ancla (tests): para una sección con el centroide EN EL EJE (todas las del
catálogo), el volumen del miembro ingleteado es EXACTAMENTE ``A · span`` — el plano
oblicuo pasa por un punto del eje, así que la altura media en el centroide es el
propio nodo, para cualquier α y φ.
"""

from __future__ import annotations

import math

from .catalog import build_component

MAX_MITER_DEG = 75.0  # α mayor (θ < 30°) daría puntas absurdas → fallback a tope
COLLINEAR_TOL_DEG = 2.0  # miembros casi colineales: corte RECTO en el nodo (α=0)


def miter_angle(u, v) -> float:
    """Ángulo de inglete α (grados DESDE el corte recto) entre dos miembros que
    SALEN del mismo nodo con direcciones u y v: α = 90 − θ/2."""
    du = math.sqrt(sum(c * c for c in u))
    dv = math.sqrt(sum(c * c for c in v))
    if du < 1e-9 or dv < 1e-9:
        raise ValueError("Dirección nula en el nodo")
    dot = sum(a * b for a, b in zip(u, v)) / (du * dv)
    theta = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
    return 90.0 - theta / 2.0


def _end_txt(end) -> str:
    return "tope" if end is None else f"{end[0]:.1f}@{end[1]:.1f}"


def mitered_profile(perfil_ref: str, span: float, sec: float,
                    end1: tuple[float, float] | None,
                    end2: tuple[float, float] | None,
                    ) -> tuple[object, str, float, tuple[float | None, float | None]]:
    """Miembro de perfil con extremos a inglete o a tope, EN EL MARCO LOCAL
    (eje Z, nodo1 en −span/2, nodo2 en +span/2, centrado como los builders).

    `end` = (α_deg, φ_deg) → inglete: α desde el corte recto, φ = azimut XY local
    hacia el VECINO (el material se quita del lado del vecino más allá del plano
    bisector; el miembro corre HASTA el nodo y su punta lo rebasa h = sup·tanα).
    `end` = None → tope: el miembro termina `sec` antes del nodo (como siempre).

    Devuelve (shape local, base_key, longitud_de_corte_EXTERIOR, (α1, α2))."""
    from build123d import Box, Pos, Rotation

    from apolo.kernel.matrix import direction_to_euler

    for end in (end1, end2):
        if end is not None and not (0.0 <= end[0] <= MAX_MITER_DEG):
            raise ValueError(f"Ángulo de inglete {end[0]:g}° fuera de rango (0–{MAX_MITER_DEG:g})")

    def _sup(phi_deg: float) -> float:
        # soporte de la sección (cuadrada sec×sec alineada al frame local) en la
        # dirección transversal φ: cuánto rebasa la PUNTA el plano del nodo
        p = math.radians(phi_deg)
        return (sec / 2.0) * (abs(math.cos(p)) + abs(math.sin(p)))

    # extensión de CONSTRUCCIÓN por extremo (el tool recorta al plano exacto)
    def _ext_build(end) -> float:
        if end is None:
            return -sec  # tope: termina sec antes del nodo, sin corte
        return sec * math.tan(math.radians(end[0])) + 1.0  # sobra 1 mm, se recorta

    ext1, ext2 = _ext_build(end1), _ext_build(end2)
    l_build = span + ext1 + ext2
    if l_build <= 1.0:
        raise ValueError(f"El miembro (span {span:g} mm) es demasiado corto para el perfil")
    shape, _ = build_component(perfil_ref, l_build)
    # el builder centra en el origen → desplazar para que los nodos queden en ±span/2
    shape = Pos(0, 0, (ext2 - ext1) / 2.0) * shape

    b_size = 3.0 * max(l_build, sec)
    for node_z, a_z, end in ((-span / 2.0, 1.0, end1), (span / 2.0, -1.0, end2)):
        if end is None:
            continue
        alpha, phi = end
        theta = 180.0 - 2.0 * alpha  # ángulo entre los miembros
        tr, ar = math.radians(theta), (0.0, 0.0, a_z)
        p = math.radians(phi)
        t_hat = (math.cos(p), math.sin(p), 0.0)
        # vecino saliente del nodo: b = a·cosθ + t̂·sinθ; normal del bisector n = a − b
        b_vec = tuple(ar[i] * math.cos(tr) + t_hat[i] * math.sin(tr) for i in range(3))
        n_vec = tuple(ar[i] - b_vec[i] for i in range(3))
        # tool = semiespacio del lado del VECINO (negativo de n): caja con la cara
        # superior SOBRE el plano bisector, apilada hacia −n
        rot = direction_to_euler(n_vec)
        tool = (Pos(0, 0, node_z) * Rotation(*rot) * Pos(0, 0, -b_size / 2.0)
                * Box(b_size, b_size, b_size))
        shape = shape - tool

    cut_ext = span
    for end in (end1, end2):
        cut_ext += (_sup(end[1]) * math.tan(math.radians(end[0]))) if end else -sec

    key = f"comp|{perfil_ref}|{round(span, 2)}|mtr|{_end_txt(end1)}|{_end_txt(end2)}"
    miter = (round(end1[0], 1) if end1 else None, round(end2[0], 1) if end2 else None)
    return shape, key, round(cut_ext, 2), miter


def member_ends(a, b, out_a, out_b):
    """Extremos (end1, end2) de un miembro a→b para `mitered_profile`, en MUNDO.

    `out_a`/`out_b` = dirección SALIENTE del VECINO en cada nodo (None → tope).
    α = 90−θ/2 con θ entre las direcciones salientes; θ casi colineal → corte
    RECTO en el nodo (α=0); α > MAX_MITER_DEG → fallback a tope (None). El azimut
    φ se proyecta al frame local de `direction_frame(b−a)` — el MISMO que usa el
    place — para que el plano del corte case con la colocación."""
    from apolo.kernel.matrix import direction_frame

    d = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    n = math.sqrt(sum(c * c for c in d))
    if n < 1e-9:
        raise ValueError("Miembro de longitud nula")
    d_hat = tuple(c / n for c in d)
    x_l, y_l, _ = direction_frame(d)

    def _end(a_out, w):
        if w is None:
            return None
        alpha = miter_angle(a_out, w)
        if alpha < COLLINEAR_TOL_DEG:
            return (0.0, 0.0)  # colineal: corte recto EN el nodo
        if alpha > MAX_MITER_DEG:
            return None  # punta absurda → tope (coping fuera de alcance)
        wx = sum(w[i] * x_l[i] for i in range(3))
        wy = sum(w[i] * y_l[i] for i in range(3))
        if abs(wx) < 1e-9 and abs(wy) < 1e-9:
            return (0.0, 0.0)  # vecino colineal puro
        return (alpha, math.degrees(math.atan2(wy, wx)) % 360.0)

    return _end(d_hat, out_a), _end(tuple(-c for c in d_hat), out_b)
