"""Exportador URDF: robot.urdf + meshes/*.stl en un ZIP.

Convenciones: URDF trabaja en metros; el modelo en mm. Los marcos de eslabón
son traslaciones puras (ejes alineados con el mundo): el marco de cada hijo
está en el origen de su junta, así que las transformaciones son restas de
vectores. Si hay varias raíces se añade un eslabón sintético 'world_base'
con juntas fijas (URDF exige un único árbol).
"""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from .model import JOINT_TYPE_URDF, box_inertia, build_kinematic_model

MM = 0.001


def _vec(values) -> str:
    return f"{values[0]:.6f} {values[1]:.6f} {values[2]:.6f}"


def _sub(a, b) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _mm2m(v) -> tuple[float, float, float]:
    return (v[0] * MM, v[1] * MM, v[2] * MM)


def build_urdf(doc, robot_name: str = "apolo_robot") -> tuple[str, dict[str, object]]:
    """Devuelve (xml, {nombre_stl: shape}) para empaquetar."""
    model = build_kinematic_model(doc)
    if not model["joints"]:
        raise ValueError("No hay juntas definidas: añade juntas o un brazo robótico antes de exportar")
    if model["errors"]:
        raise ValueError("; ".join(model["errors"]))

    robot = ET.Element("robot", name=robot_name)
    meshes: dict[str, object] = {}

    multi_root = len(model["roots"]) > 1
    if multi_root:
        ET.SubElement(robot, "link", name="world_base")

    for link in model["links"].values():
        el = ET.SubElement(robot, "link", name=link.name)
        mesh_file = f"{link.name}.stl"
        meshes[mesh_file] = link.shape
        # la malla está en coordenadas mundo (mm); el marco del eslabón está en
        # link.frame → la malla se desplaza -frame (y se escala mm→m)
        offset = _mm2m(_sub((0, 0, 0), link.frame))
        for tag in ("visual", "collision"):
            sub = ET.SubElement(el, tag)
            ET.SubElement(sub, "origin", xyz=_vec(offset), rpy="0 0 0")
            geo = ET.SubElement(sub, "geometry")
            ET.SubElement(geo, "mesh", filename=f"meshes/{mesh_file}", scale=f"{MM} {MM} {MM}")
        inertial = ET.SubElement(el, "inertial")
        ET.SubElement(inertial, "origin", xyz=_vec(_mm2m(_sub(link.com, link.frame))), rpy="0 0 0")
        ET.SubElement(inertial, "mass", value=f"{link.mass_kg:.4f}")
        inertia = box_inertia(link.mass_kg, _mm2m(link.size))
        ET.SubElement(
            inertia_el := inertial, "inertia",
            ixx=f"{inertia['ixx']:.6f}", iyy=f"{inertia['iyy']:.6f}", izz=f"{inertia['izz']:.6f}",
            ixy="0", ixz="0", iyz="0",
        )

    if multi_root:
        for root_id in model["roots"]:
            joint = ET.SubElement(robot, "joint", name=f"fix_{root_id}", type="fixed")
            ET.SubElement(joint, "parent", link="world_base")
            ET.SubElement(joint, "child", link=model["links"][root_id].name)
            ET.SubElement(joint, "origin", xyz=_vec(_mm2m(model["links"][root_id].frame)), rpy="0 0 0")

    import math

    for j in model["joints"]:
        parent = model["links"][j["parent"]]
        child = model["links"][j["child"]]
        el = ET.SubElement(robot, "joint", name=j["name"], type=JOINT_TYPE_URDF[j["type"]])
        ET.SubElement(el, "parent", link=parent.name)
        ET.SubElement(el, "child", link=child.name)
        ET.SubElement(el, "origin", xyz=_vec(_mm2m(_sub(j["origin"], parent.frame))), rpy="0 0 0")
        if j["type"] != "fija":
            ET.SubElement(el, "axis", xyz=_vec(j["axis"]))
        if j["type"] in ("giratoria", "prismatica"):
            if j["type"] == "giratoria":
                lower, upper = math.radians(j["lower"]), math.radians(j["upper"])
            else:
                lower, upper = j["lower"] * MM, j["upper"] * MM
            ET.SubElement(
                el, "limit", lower=f"{lower:.5f}", upper=f"{upper:.5f}", effort="100", velocity="1.0"
            )

    ET.indent(robot)
    xml = '<?xml version="1.0"?>\n' + ET.tostring(robot, encoding="unicode")
    return xml, meshes


def _zip_with_meshes(xml: str, xml_name: str, meshes: dict[str, object]) -> bytes:
    from build123d import export_stl

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(xml_name, xml)
        with tempfile.TemporaryDirectory(prefix="apolo_mesh_") as tmp:
            for mesh_name, shape in meshes.items():
                path = Path(tmp) / mesh_name
                export_stl(shape, str(path))
                zf.write(path, f"meshes/{mesh_name}")
    return buf.getvalue()


def export_urdf_zip(doc, robot_name: str = "apolo_robot") -> bytes:
    xml, meshes = build_urdf(doc, robot_name)
    return _zip_with_meshes(xml, "robot.urdf", meshes)
