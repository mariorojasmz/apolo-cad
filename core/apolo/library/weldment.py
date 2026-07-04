"""Plantilla paramétrica de bastidor soldado (weldment).

Genera la lista de piezas para el comando create_weldment. Como el transportador,
es un "super-comando": un bastidor completo es una sola entrada del historial,
editable paramétricamente, y los miembros son instancias de catálogo con
longitud de corte → el BOM produce la lista de corte automáticamente.

Disposición (Z arriba), envolvente ancho(X) × fondo(Y) × alto(Z):
- 4 postes verticales (perfil en Z) en las esquinas.
- Anillos horizontales (superior, inferior y N intermedios): 2 largueros X +
  2 travesaños Y cada uno, RECORTADOS a tope entre postes (sin solape).
- Cordones de soldadura opcionales: esferas marcadoras en los nodos.
"""

from __future__ import annotations

from dataclasses import dataclass

from apolo.kernel.shapes import PROFILE_SIZES, place

from .catalog import CATALOG, build_component


@dataclass
class WeldmentPart:
    suffix: str
    name: str
    shape: object
    component: str | None
    cut_length: float | None
    base_key: str | None = None
    base_shape: object | None = None
    position: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0)
    miter: tuple | None = None  # (α1, α2) grados desde el corte recto; None = a tope


def _picture_frame(perfil_ref: str, sec: float, px: float, py: float, z: float,
                   ring_idx: int) -> list[WeldmentPart]:
    """Marco cerrado a INGLETE 45° en el nivel z (V5.8): 4 miembros en orden cíclico
    entre los nodos de centrolínea (±px, ±py) — la punta exterior cae sola en la
    esquina ancho/2×fondo/2, longitud de corte = longitud EXTERIOR (lo que el
    taller corta). Los 4 comparten el plano bisector con su vecino: contacto
    cara-cara exacto, sin solape ni hueco."""
    import math

    from apolo.kernel.matrix import direction_to_euler
    from apolo.kernel.shapes import place as _place

    from .miter import member_ends, mitered_profile

    corners3 = [(-px, -py, z), (px, -py, z), (px, py, z), (-px, py, z)]
    labels = ["Larguero X", "Travesaño Y", "Larguero X", "Travesaño Y"]
    out: list[WeldmentPart] = []
    n = len(corners3)
    for k in range(n):
        a, b = corners3[k], corners3[(k + 1) % n]
        prev_node = corners3[(k - 1) % n]  # vecino en a = miembro anterior del ciclo
        next_node = corners3[(k + 2) % n]  # vecino en b = miembro siguiente
        w_a = tuple(prev_node[i] - a[i] for i in range(3))
        w_b = tuple(next_node[i] - b[i] for i in range(3))
        end1, end2 = member_ends(a, b, w_a, w_b)
        d = tuple(b[i] - a[i] for i in range(3))
        span = math.sqrt(sum(c * c for c in d))
        shape, key, cut_ext, miter = mitered_profile(perfil_ref, span, sec, end1, end2)
        mid = tuple((a[i] + b[i]) / 2.0 for i in range(3))
        rot = direction_to_euler(d)
        out.append(WeldmentPart(
            f"mk{ring_idx}_{k + 1}", f"{labels[k]} (marco {ring_idx})",
            _place(shape, mid, rot), perfil_ref, cut_ext,
            base_key=key, base_shape=shape, position=mid, rotation=rot, miter=miter,
        ))
    return out


def _section(perfil_ref: str) -> float:
    comp = CATALOG.get(perfil_ref)
    if comp is None or comp.category != "perfiles":
        raise ValueError(f"'{perfil_ref}' no es un perfil del catálogo")
    section = comp.specs.get("seccion", "40x40")
    return max(PROFILE_SIZES.get(section, (40.0, 40.0)))


def weldment_parts(
    ancho: float,
    fondo: float,
    alto: float,
    perfil_ref: str,
    anillos_intermedios: int = 0,
    cordones: bool = True,
    esquinas: str = "tope",
) -> list[WeldmentPart]:
    sec = _section(perfil_ref)
    if ancho <= 2 * sec or fondo <= 2 * sec:
        raise ValueError(f"Ancho y fondo deben superar {2 * sec:g} mm (2× sección del perfil)")
    if alto <= 2 * sec:
        raise ValueError(f"El alto debe superar {2 * sec:g} mm")
    if anillos_intermedios < 0 or anillos_intermedios > 20:
        raise ValueError("anillos_intermedios debe estar entre 0 y 20")
    if esquinas not in ("tope", "inglete"):
        raise ValueError("esquinas debe ser 'tope' o 'inglete'")

    # centrolíneas de los postes (caras exteriores a ras de ancho×fondo)
    px = ancho / 2.0 - sec / 2.0
    py = fondo / 2.0 - sec / 2.0
    rail_x_len = ancho - 2 * sec  # larguero recortado a tope entre postes
    rail_y_len = fondo - 2 * sec

    parts: list[WeldmentPart] = []

    def add(suffix, name, base, base_key, component, cut, position, rotation, miter=None):
        parts.append(
            WeldmentPart(
                suffix, name, place(base, position, rotation), component, cut,
                base_key=base_key, base_shape=base, position=position, rotation=rotation,
                miter=miter,
            )
        )

    inglete = esquinas == "inglete"
    corners = [(-px, -py), (px, -py), (px, py), (-px, py)]

    # ---- 4 postes: completos (tope) o A TOPE ENTRE los marcos (inglete)
    post_len = alto - 2 * sec if inglete else alto
    post_shape, post_cut = build_component(perfil_ref, post_len)
    post_key = f"comp|{perfil_ref}|{post_cut}"
    for i, (cx, cy) in enumerate(corners, start=1):
        add(f"post{i}", f"Poste ({i})", post_shape, post_key, perfil_ref, post_cut,
            (cx, cy, alto / 2.0), (0, 0, 0))

    # ---- anillos horizontales: z de cada anillo (inferior, intermedios, superior)
    n_rings = anillos_intermedios + 2
    zs = [sec / 2.0 + (alto - sec) * k / (n_rings - 1) for k in range(n_rings)]
    railx_shape, railx_cut = build_component(perfil_ref, rail_x_len)
    railx_key = f"comp|{perfil_ref}|{railx_cut}"
    raily_shape, raily_cut = build_component(perfil_ref, rail_y_len)
    raily_key = f"comp|{perfil_ref}|{raily_cut}"
    for r, z in enumerate(zs, start=1):
        if inglete and r in (1, n_rings):
            parts += _picture_frame(perfil_ref, sec, px, py, z, r)
            continue
        for s, sign in enumerate((-1.0, 1.0), start=1):
            add(f"rx{r}_{s}", f"Larguero X (anillo {r})", railx_shape, railx_key, perfil_ref, railx_cut,
                (0, sign * py, z), (0, 90, 0))
            add(f"ry{r}_{s}", f"Travesaño Y (anillo {r})", raily_shape, raily_key, perfil_ref, raily_cut,
                (sign * px, 0, z), (90, 0, 0))

    # ---- cordones de soldadura (marcadores esféricos en los nodos)
    if cordones:
        from build123d import Sphere

        bead = Sphere(sec * 0.6)
        bead_key = f"weldbead|{round(sec * 0.6, 2)}"
        n = 0
        for z in zs:
            for cx, cy in corners:
                n += 1
                add(f"bead{n}", "Cordón", bead, bead_key, None, None, (cx, cy, z), (0, 0, 0))

    return parts
