"""Plantilla paramétrica de transportador de rodillos.

Genera la lista de piezas (forma + referencia de catálogo) para el comando
create_conveyor. Es un "super-comando": un transportador completo es una sola
entrada del historial, editable paramétricamente.

Disposición (Z arriba, transporte a lo largo de X):
- 2 largueros PERFIL-4080 (sección 80 ancho × 40 alto, tumbada: 40 en Y, 80 en Z)
- rodillos entre largueros, eje en Y, parte superior a la altura de trabajo
- 4 patas PATA-REG con placa base en el suelo (z=0)
- 2 travesaños PERFIL-4040 de arriostrado bajo los largueros
- motorreductor opcional colgado del larguero en el extremo de descarga
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from apolo.kernel.shapes import place

from .catalog import CATALOG, build_component

RAIL_W = 40.0   # ancho del larguero en Y (perfil 40x80 tumbado)
RAIL_H = 80.0   # alto del larguero en Z

# Componentes por ROL (centralizados; no dispersos por el cuerpo). Cambiar el
# transportador a otros perfiles/patas es editar aquí, no rastrear literales.
RAIL_REF = "PERFIL-4080"   # largueros
LEG_REF = "PATA-REG"       # patas
BRACE_REF = "PERFIL-4040"  # arriostrado


@dataclass
class ConveyorPart:
    suffix: str
    name: str
    shape: object
    component: str | None
    cut_length: float | None
    # instancias: geometría canónica compartida + colocación local
    base_key: str | None = None
    base_shape: object | None = None
    position: tuple = (0.0, 0.0, 0.0)
    rotation: tuple = (0.0, 0.0, 0.0)


def conveyor_parts(
    largo: float,
    ancho: float,
    altura: float,
    paso: float,
    rodillo_ref: str,
    motor_ref: str | None,
) -> list[ConveyorPart]:
    rodillo = CATALOG[rodillo_ref]
    d = float(rodillo.specs["diametro_mm"])

    if ancho <= 2 * RAIL_W + 100:
        raise ValueError(f"Ancho mínimo {2 * RAIL_W + 100:g} mm (largueros + 100 de rodillo)")
    if altura <= RAIL_H + 60:
        raise ValueError(f"Altura de trabajo mínima {RAIL_H + 60:g} mm")
    if paso < d + 5:
        raise ValueError(
            f"Paso {paso:g} mm incompatible con rodillo Ø{d:g}: los rodillos se tocan (mínimo {d + 5:g})"
        )
    if largo < 2 * paso + 100:
        raise ValueError(f"Largo mínimo {2 * paso + 100:g} mm para al menos 2 rodillos")

    roller_axis_z = altura - d / 2.0
    rail_center_z = roller_axis_z - RAIL_H / 2.0  # cara superior del larguero a la altura del eje
    rail_y = (ancho - RAIL_W) / 2.0
    roller_len = ancho - 2 * RAIL_W - 4.0

    parts: list[ConveyorPart] = []

    def add(suffix, name, base, base_key, component, cut, position, rotation):
        parts.append(
            ConveyorPart(
                suffix, name, place(base, position, rotation), component, cut,
                base_key=base_key, base_shape=base, position=position, rotation=rotation,
            )
        )

    # largueros (extruidos en Z → tumbados a lo largo de X con rot Y=90)
    rail_shape, rail_cut = build_component(RAIL_REF, largo)
    rail_key = f"comp|PERFIL-4080|{rail_cut}"
    for i, sign in enumerate((-1.0, 1.0), start=1):
        add(f"rail{i}", f"Larguero ({i})", rail_shape, rail_key, RAIL_REF, rail_cut,
            (0, sign * rail_y, rail_center_z), (0, 90, 0))

    # rodillos
    usable = largo - 2 * RAIL_W
    n_rollers = int(math.floor(usable / paso))
    start_x = -((n_rollers - 1) * paso) / 2.0
    roller_shape, roller_cut = build_component(rodillo_ref, roller_len)
    roller_key = f"comp|{rodillo_ref}|{roller_cut}"
    for i in range(n_rollers):
        add(f"rod{i + 1}", f"Rodillo ({i + 1})", roller_shape, roller_key, rodillo_ref, roller_cut,
            (start_x + i * paso, 0, roller_axis_z), (90, 0, 0))

    # patas
    leg_len = rail_center_z - RAIL_H / 2.0
    leg_x = largo / 2.0 - 120.0
    leg_shape, leg_cut = build_component(LEG_REF, leg_len)
    leg_key = f"comp|PATA-REG|{leg_cut}"
    positions = [(-leg_x, -rail_y), (-leg_x, rail_y), (leg_x, -rail_y), (leg_x, rail_y)]
    for i, (px, py) in enumerate(positions, start=1):
        add(f"leg{i}", f"Pata ({i})", leg_shape, leg_key, LEG_REF, leg_cut,
            (px, py, leg_len / 2.0), (0, 0, 0))

    # travesaños de arriostrado entre patas (eje Y, a media altura)
    brace_len = ancho - 2 * RAIL_W
    brace_shape, brace_cut = build_component(BRACE_REF, brace_len)
    brace_key = f"comp|PERFIL-4040|{brace_cut}"
    for i, px in enumerate((-leg_x, leg_x), start=1):
        add(f"brace{i}", f"Travesaño ({i})", brace_shape, brace_key, BRACE_REF, brace_cut,
            (px, 0, leg_len / 2.0), (90, 0, 0))

    # motorreductor en el extremo de descarga, colgado bajo el larguero
    if motor_ref:
        motor_shape, _ = build_component(motor_ref)
        add("motor", "Motorreductor", motor_shape, f"comp|{motor_ref}|std", motor_ref, None,
            (largo / 2.0 - 200.0, 0, rail_center_z - RAIL_H), (0, 0, 90))

    return parts
