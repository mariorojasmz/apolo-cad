"""Plantilla paramétrica de FAJA DE BANDA (belt conveyor).

Super-comando create_belt_conveyor: una faja de banda plana con cama de
deslizamiento y 2 tambores de extremo es una sola entrada del historial,
editable paramétricamente. A diferencia de ``conveyor.py`` (transportador de
RODILLOS), aquí los extremos son TAMBORES (motriz engomado + cola), hay BANDA
envolvente (lazo), cama de deslizamiento, bastidor de tubo estructural de acero,
tensor tipo trotadora (sin chumacera) y motorreductor de eje hueco.

Disposición (Z arriba, transporte a lo largo de X; tambores en ±largo/2):
- 2 largueros de tubo estructural a lo largo de X
- tambor motriz (cabeza, +X) y tambor de cola/tensor (-X), eje en Y
- banda = lazo (racetrack) hueco envolviendo ambos tambores
- cama de deslizamiento (plancha) bajo el ramal de carga
- 4 patas de tubo + pies niveladores + 2 travesaños de arriostrado
- 2 tensores tipo trotadora en la cola (opcional)
- motorreductor de eje hueco en el tambor motriz (opcional)
- 2 guardas laterales (opcional)
"""

from __future__ import annotations

import math

from build123d import Box, Cylinder, Plane, Polygon, extrude

from apolo.kernel.shapes import place

from .catalog import CATALOG, build_component
from .conveyor import ConveyorPart

LEG_REF = "TUBO-2X2"
BRACE_REF = "TUBO-2X2"
FOOT_REF = "PIE-M12-50"
GUARD_REF = "GUARDA-150"
FACE_MARGIN = 50.0  # ancho de cara del tambor = ancho de banda + margen (25/lado)


def _radio_exterior(ref: str) -> float:
    """Radio que ABRAZA la banda: el del tambor más su engomado (`lagging_mm`), si lo tiene."""
    specs = CATALOG[ref].specs
    return float(specs["diametro_mm"]) / 2.0 + float(specs.get("lagging_mm", 0.0))


def _belt_loop(x_m: float, z_m: float, r_m: float, x_c: float, z_c: float, r_c: float,
               thickness: float, width: float):
    """Banda como lazo HUECO que abraza dos tambores de radio propio (el motriz engomado es más
    grande que el de cola): envolvente convexa de los dos círculos de radio r+t menos la de los
    de radio r, extruida sobre el ancho de banda (eje Y). Coordenadas en el plano XZ."""

    def tangentes(r1: float, r2: float):
        # rectas tangentes EXTERIORES de los círculos (x_c, z_c, r1) y (x_m, z_m, r2): el
        # cuadrilátero de sus cuatro puntos de tangencia + los dos círculos = la envolvente
        dx, dz = x_m - x_c, z_m - z_c
        dist = math.hypot(dx, dz)
        fi, beta = math.atan2(dz, dx), math.acos((r1 - r2) / dist)
        pts = []
        for ang in (fi + beta, fi - beta):
            nx, nz = math.cos(ang), math.sin(ang)
            pts.append(((x_c + r1 * nx, z_c + r1 * nz), (x_m + r2 * nx, z_m + r2 * nz)))
        (a1, a2), (b1, b2) = pts
        return [a1, a2, b2, b1]

    def region(extra: float):
        r1, r2 = r_c + extra, r_m + extra
        cuad = extrude(Plane.XZ * Polygon(*tangentes(r1, r2)), amount=width / 2.0, both=True)
        caps = (
            place(Cylinder(r1, width), (x_c, 0, z_c), (90, 0, 0))
            + place(Cylinder(r2, width), (x_m, 0, z_m), (90, 0, 0))
        )
        return cuad + caps

    return region(thickness) - region(0.0)


def belt_conveyor_parts(
    largo: float,
    ancho_banda: float,
    altura: float,
    tambor_motriz_ref: str,
    tambor_cola_ref: str,
    tubo_ref: str,
    tensor_ref: str | None,
    motor_ref: str | None,
    espesor_banda: float,
    guardas: bool,
) -> list[ConveyorPart]:
    # cada tambor con su radio EXTERIOR (engomado incluido): la banda abraza ése, y cada eje baja
    # lo que crece su tambor para que el ramal de carga quede plano a la altura de trabajo
    r_m = _radio_exterior(tambor_motriz_ref)
    r_c = _radio_exterior(tambor_cola_ref)
    tube = CATALOG[tubo_ref]
    rail_t = float(tube.specs["height"])  # espesor del larguero en Y (tras tumbarlo)
    rail_h = float(tube.specs["width"])   # peralte del larguero en Z (vertical)

    cara = ancho_banda + FACE_MARGIN
    if largo < 2.0 * (r_m + r_c) + 200.0:
        raise ValueError(f"Largo mínimo {2.0 * (r_m + r_c) + 200.0:g} mm (dos tambores + holgura)")
    if ancho_banda < 100.0:
        raise ValueError("Ancho de banda mínimo 100 mm")
    if altura <= rail_h + max(r_m, r_c) + 60.0:
        raise ValueError(f"Altura de trabajo mínima {rail_h + max(r_m, r_c) + 60.0:g} mm")

    zc = altura - r_c - espesor_banda               # eje del tambor de cola (y de los largueros)
    zm = altura - r_m - espesor_banda               # eje del tambor motriz
    rail_center_z = zc - rail_h / 2.0               # cara superior del larguero al eje
    rail_y = ancho_banda / 2.0 + 35.0 + rail_t / 2.0
    half = largo / 2.0
    overhang = max(r_m, r_c) + espesor_banda + 40.0
    rail_len = largo + 2.0 * overhang

    parts: list[ConveyorPart] = []

    def add(suffix, name, base, base_key, component, cut, position, rotation):
        parts.append(
            ConveyorPart(
                suffix, name, place(base, position, rotation), component, cut,
                base_key=base_key, base_shape=base, position=position, rotation=rotation,
            )
        )

    # largueros (tubo estructural): extruidos en Z → tumbados a lo largo de X (rot Y=90)
    rail_shape, rail_cut = build_component(tubo_ref, rail_len)
    rail_key = f"comp|{tubo_ref}|{rail_cut}"
    for i, sign in enumerate((-1.0, 1.0), start=1):
        add(f"rail{i}", f"Larguero ({i})", rail_shape, rail_key, tubo_ref, rail_cut,
            (0, sign * rail_y, rail_center_z), (0, 90, 0))

    # tambores (eje en Y → rot X=90)
    drive_shape, drive_cut = build_component(tambor_motriz_ref, cara)
    add("tambor_motriz", "Tambor motriz", drive_shape, f"comp|{tambor_motriz_ref}|{drive_cut}",
        tambor_motriz_ref, drive_cut, (half, 0, zm), (90, 0, 0))
    tail_shape, tail_cut = build_component(tambor_cola_ref, cara)
    add("tambor_cola", "Tambor de cola", tail_shape, f"comp|{tambor_cola_ref}|{tail_cut}",
        tambor_cola_ref, tail_cut, (-half, 0, zc), (90, 0, 0))

    # banda = lazo envolvente (geometría a medida)
    belt = _belt_loop(half, zm, r_m, -half, zc, r_c, espesor_banda, ancho_banda)
    add("banda", "Banda", belt, None, None, None, (0, 0, 0), (0, 0, 0))

    # cama de deslizamiento (plancha a medida) bajo el ramal de carga
    deck_t = 20.0
    deck = Box(largo - 2.0 * max(r_m, r_c), ancho_banda + 20.0, deck_t)
    deck_z = altura - espesor_banda - 2.0 - deck_t / 2.0
    add("cama", "Cama de deslizamiento", deck, None, None, None, (0, 0, deck_z), (0, 0, 0))

    # patas + pies niveladores
    leg_len = rail_center_z - rail_h / 2.0
    leg_x = half - 150.0
    leg_shape, leg_cut = build_component(LEG_REF, leg_len)
    leg_key = f"comp|{LEG_REF}|{leg_cut}"
    foot_shape, _ = build_component(FOOT_REF)
    foot_key = f"comp|{FOOT_REF}|std"
    n = 1
    for px in (-leg_x, leg_x):
        for py in (-rail_y, rail_y):
            add(f"leg{n}", f"Pata ({n})", leg_shape, leg_key, LEG_REF, leg_cut,
                (px, py, leg_len / 2.0), (0, 0, 0))
            add(f"foot{n}", f"Pie nivelador ({n})", foot_shape, foot_key, FOOT_REF, None,
                (px, py, 25.0), (0, 0, 0))
            n += 1

    # travesaños de arriostrado (eje Y) bajo los largueros, en las estaciones de patas
    brace_len = 2.0 * rail_y - rail_t
    brace_shape, brace_cut = build_component(BRACE_REF, brace_len)
    brace_key = f"comp|{BRACE_REF}|{brace_cut}"
    for i, px in enumerate((-leg_x, leg_x), start=1):
        add(f"brace{i}", f"Travesaño ({i})", brace_shape, brace_key, BRACE_REF, brace_cut,
            (px, 0, leg_len - 30.0), (90, 0, 0))

    # tensor tipo TROTADORA en el tambor de cola: soporte en «C» + tornillo M16 VERTICAL que
    # pasa por el agujero transversal del eje (uno por lado). El eje de TAMBOR-102-COLA ya trae
    # los agujeros; el M16 cae a `hole_inset` mm del extremo del eje (mismo valor que el builder).
    if tensor_ref:
        cola_specs = CATALOG[tambor_cola_ref].specs
        cola_stub = float(cola_specs.get("stub_mm", 40.0))
        hole_inset = float(cola_specs.get("hole_inset_mm", 22.0))
        takeup_y = cara / 2.0 + cola_stub - hole_inset
        tensor_shape, _ = build_component(tensor_ref)
        tensor_key = f"comp|{tensor_ref}|std"
        for i, sy in enumerate((-1.0, 1.0), start=1):
            rot = (0, 0, 180) if sy > 0 else (0, 0, 0)  # el alma de la «C» mira hacia afuera
            add(f"tensor{i}", f"Tensor trotadora ({i})", tensor_shape, tensor_key, tensor_ref, None,
                (-half, sy * takeup_y, zc), rot)

    # motorreductor de eje hueco en el tambor motriz
    if motor_ref:
        motor_shape, _ = build_component(motor_ref)
        add("motor", "Motorreductor", motor_shape, f"comp|{motor_ref}|std", motor_ref, None,
            (half, cara / 2.0 + 100.0, zm), (0, 0, 0))

    # guardas laterales (contención de paquetes)
    if guardas:
        guard_shape, guard_cut = build_component(GUARD_REF, largo)
        guard_key = f"comp|{GUARD_REF}|{guard_cut}"
        for i, sy in enumerate((-1.0, 1.0), start=1):
            add(f"guarda{i}", f"Guarda lateral ({i})", guard_shape, guard_key, GUARD_REF, guard_cut,
                (0, sy * (ancho_banda / 2.0 + 12.0), altura + 60.0), (0, 0, 0))

    return parts
