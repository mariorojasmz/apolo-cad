"""Plantilla de brazo robótico articulado de 4 ejes.

Cadena: base (fija al mundo) → J1 giro de base (Z) → columna → J2 hombro (Y)
→ brazo → J3 codo (Y) → antebrazo → J4 muñeca (X) → muñeca con brida.

Las piezas se construyen en coordenadas mundo (origen = centro de la base) y
las juntas referencian los ids de feature {cmd_id}_{suffix}.
"""

from __future__ import annotations

from build123d import Box, Cylinder, Pos, Rotation

BASE_H = 80.0
COLUMN_H = 140.0
SECTION = 0.14  # grosor de los eslabones respecto al alcance
WRIST_LEN = 70.0


def robot_arm_parts(
    alcance: float, position: tuple[float, float, float], cmd_id: str
) -> tuple[list[dict], list[dict]]:
    if alcance <= 200:
        raise ValueError("El alcance mínimo es 200 mm")
    px, py, pz = position
    upper = alcance * 0.55  # brazo
    fore = alcance * 0.45  # antebrazo
    sec = max(40.0, alcance * SECTION)
    shoulder_z = pz + BASE_H + COLUMN_H  # eje del hombro

    def world(shape, x=0.0, y=0.0, z=0.0):
        return Pos(px + x, py + y, pz + z) * shape

    parts = [
        {
            "suffix": "base", "name": "Base",
            "shape": world(Pos(0, 0, BASE_H / 2) * Cylinder(alcance * 0.18, BASE_H)),
        },
        {
            "suffix": "columna", "name": "Columna (J1)",
            "shape": world(Pos(0, 0, BASE_H + COLUMN_H / 2) * Cylinder(alcance * 0.12, COLUMN_H)),
        },
        {
            "suffix": "brazo", "name": "Brazo (J2)",
            "shape": world(Pos(upper / 2, 0, BASE_H + COLUMN_H) * Box(upper + sec, sec, sec)),
        },
        {
            "suffix": "antebrazo", "name": "Antebrazo (J3)",
            "shape": world(
                Pos(upper + fore / 2, 0, BASE_H + COLUMN_H) * Box(fore + sec * 0.7, sec * 0.8, sec * 0.8)
            ),
        },
        {
            "suffix": "muneca", "name": "Muñeca (J4)",
            "shape": world(
                Pos(upper + fore + WRIST_LEN / 2, 0, BASE_H + COLUMN_H)
                * Rotation(0, 90, 0)
                * Cylinder(sec * 0.35, WRIST_LEN)
            ),
        },
    ]

    fid = lambda suffix: f"{cmd_id}_{suffix}"
    joints = [
        {
            "name": f"j1_base_{cmd_id}", "type": "giratoria",
            "parent": fid("base"), "child": fid("columna"),
            "origin": [px, py, pz + BASE_H], "axis": [0, 0, 1], "lower": -170, "upper": 170,
        },
        {
            "name": f"j2_hombro_{cmd_id}", "type": "giratoria",
            "parent": fid("columna"), "child": fid("brazo"),
            "origin": [px, py, shoulder_z], "axis": [0, 1, 0], "lower": -100, "upper": 100,
        },
        {
            "name": f"j3_codo_{cmd_id}", "type": "giratoria",
            "parent": fid("brazo"), "child": fid("antebrazo"),
            "origin": [px + upper, py, shoulder_z], "axis": [0, 1, 0], "lower": -135, "upper": 135,
        },
        {
            "name": f"j4_muneca_{cmd_id}", "type": "continua",
            "parent": fid("antebrazo"), "child": fid("muneca"),
            "origin": [px + upper + fore, py, shoulder_z], "axis": [1, 0, 0], "lower": -180, "upper": 180,
        },
    ]
    return parts, joints
