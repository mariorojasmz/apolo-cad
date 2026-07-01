"""Modelo cinemático derivado del documento.

Construye el árbol de eslabones (features) y juntas, asigna marcos de
referencia (traslaciones puras: el marco de cada eslabón hijo se sitúa en el
origen de su junta) y detecta referencias rotas. Es la base común de los
exportadores URDF y SDF y del panel Cinemática.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

JOINT_TYPE_URDF = {"fija": "fixed", "giratoria": "revolute", "continua": "continuous", "prismatica": "prismatic"}


def _safe_name(text: str) -> str:
    out = re.sub(r"[^A-Za-z0-9_]", "_", text)
    return out if out and not out[0].isdigit() else f"l_{out}"


@dataclass
class KinLink:
    id: str
    name: str
    shape: object
    frame: tuple[float, float, float]  # origen del marco del eslabón (mundo)
    mass_kg: float
    com: tuple[float, float, float]  # centro de masas (mundo)
    size: tuple[float, float, float]  # dimensiones bbox (inercia de caja)


def _link_physics(feat) -> tuple[float, tuple, tuple]:
    """Masa/COM/bbox de un eslabón para URDF/SDF/MuJoCo. Densidad UNIFICADA con
    `materials.py` (resolve_material: override → catálogo → heurística por nombre) —
    la misma fuente que mass-properties/cutlist; antes usaba una tabla por categoría
    (solo perfiles/patas=aluminio) que divergía del resto del sistema."""
    from apolo.library.catalog import CATALOG
    from apolo.library.materials import density as mat_density
    from apolo.library.materials import resolve_material

    density = mat_density(resolve_material(feat, CATALOG))
    volume = max(float(feat.shape.volume), 1.0)
    bb = feat.shape.bounding_box()
    com = ((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
    size = (max(bb.max.X - bb.min.X, 1.0), max(bb.max.Y - bb.min.Y, 1.0), max(bb.max.Z - bb.min.Z, 1.0))
    return volume * density, com, size


def build_kinematic_model(doc) -> dict:
    """Devuelve {links: {id: KinLink}, joints: [dict], roots: [id], errors: [str]}."""
    errors: list[str] = []
    joints: list[dict] = []
    for joint in doc.joints.values():
        if joint["parent"] not in doc.scene or joint["child"] not in doc.scene:
            errors.append(f"La junta '{joint['name']}' referencia sólidos inexistentes")
            continue
        joints.append(dict(joint))

    involved: set[str] = set()
    for j in joints:
        involved.add(j["parent"])
        involved.add(j["child"])

    child_frames = {j["child"]: tuple(j["origin"]) for j in joints}
    links: dict[str, KinLink] = {}
    for fid in involved:
        feat = doc.scene[fid]
        mass, com, size = _link_physics(feat)
        links[fid] = KinLink(
            id=fid,
            name=_safe_name(f"{feat.name}_{fid}"),
            shape=feat.shape,
            frame=child_frames.get(fid, (0.0, 0.0, 0.0)),
            mass_kg=round(mass, 4),
            com=com,
            size=size,
        )

    children = {j["child"] for j in joints}
    roots = sorted(fid for fid in involved if fid not in children)
    return {"links": links, "joints": joints, "roots": roots, "errors": errors}


def joints_payload(doc) -> dict:
    """Estado cinemático para la UI: juntas + raíces + errores."""
    model = build_kinematic_model(doc)
    return {
        "joints": [
            {
                "name": j["name"],
                "type": j["type"],
                "parent": j["parent"],
                "child": j["child"],
                "origin": j["origin"],
                "axis": j["axis"],
                "lower": j["lower"],
                "upper": j["upper"],
                "command_id": j["command_id"],
            }
            for j in model["joints"]
        ],
        "roots": model["roots"],
        "errors": model["errors"],
    }


def box_inertia(mass: float, size_m: tuple[float, float, float]) -> dict:
    sx, sy, sz = size_m
    return {
        "ixx": mass / 12.0 * (sy**2 + sz**2),
        "iyy": mass / 12.0 * (sx**2 + sz**2),
        "izz": mass / 12.0 * (sx**2 + sy**2),
    }
