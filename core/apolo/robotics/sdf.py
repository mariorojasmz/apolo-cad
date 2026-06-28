"""Exportador SDF 1.6 (Gazebo): model.sdf + meshes/*.stl en un ZIP.

En SDF las poses de los eslabones van en el marco del modelo: como nuestras
mallas ya están en coordenadas mundo, los eslabones llevan pose nula y la
junta lleva su origen en el marco del hijo (= marco del modelo).
"""

from __future__ import annotations

import math
from xml.etree import ElementTree as ET

from .model import box_inertia, build_kinematic_model
from .urdf import MM, _vec, _zip_with_meshes

SDF_JOINT_TYPE = {"fija": "fixed", "giratoria": "revolute", "continua": "revolute", "prismatica": "prismatic"}


def build_sdf(doc, robot_name: str = "apolo_robot") -> tuple[str, dict[str, object]]:
    kin = build_kinematic_model(doc)
    if not kin["joints"]:
        raise ValueError("No hay juntas definidas: añade juntas o un brazo robótico antes de exportar")
    if kin["errors"]:
        raise ValueError("; ".join(kin["errors"]))

    sdf = ET.Element("sdf", version="1.6")
    model = ET.SubElement(sdf, "model", name=robot_name)
    ET.SubElement(model, "static").text = "false"
    meshes: dict[str, object] = {}

    for link in kin["links"].values():
        el = ET.SubElement(model, "link", name=link.name)
        ET.SubElement(el, "pose").text = "0 0 0 0 0 0"
        mesh_file = f"{link.name}.stl"
        meshes[mesh_file] = link.shape

        inertial = ET.SubElement(el, "inertial")
        com_m = (link.com[0] * MM, link.com[1] * MM, link.com[2] * MM)
        ET.SubElement(inertial, "pose").text = f"{_vec(com_m)} 0 0 0"
        ET.SubElement(inertial, "mass").text = f"{link.mass_kg:.4f}"
        size_m = (link.size[0] * MM, link.size[1] * MM, link.size[2] * MM)
        tensor = box_inertia(link.mass_kg, size_m)
        inertia = ET.SubElement(inertial, "inertia")
        for key in ("ixx", "iyy", "izz"):
            ET.SubElement(inertia, key).text = f"{tensor[key]:.6f}"
        for key in ("ixy", "ixz", "iyz"):
            ET.SubElement(inertia, key).text = "0"

        for tag in ("visual", "collision"):
            sub = ET.SubElement(el, tag, name=f"{tag}_{link.name}")
            geo = ET.SubElement(sub, "geometry")
            mesh = ET.SubElement(geo, "mesh")
            ET.SubElement(mesh, "uri").text = f"meshes/{mesh_file}"
            ET.SubElement(mesh, "scale").text = f"{MM} {MM} {MM}"

    for j in kin["joints"]:
        el = ET.SubElement(model, "joint", name=j["name"], type=SDF_JOINT_TYPE[j["type"]])
        ET.SubElement(el, "parent").text = kin["links"][j["parent"]].name
        ET.SubElement(el, "child").text = kin["links"][j["child"]].name
        origin_m = (j["origin"][0] * MM, j["origin"][1] * MM, j["origin"][2] * MM)
        ET.SubElement(el, "pose").text = f"{_vec(origin_m)} 0 0 0"
        if j["type"] != "fija":
            axis = ET.SubElement(el, "axis")
            ET.SubElement(axis, "xyz").text = _vec(j["axis"])
            limit = ET.SubElement(axis, "limit")
            if j["type"] == "giratoria":
                ET.SubElement(limit, "lower").text = f"{math.radians(j['lower']):.5f}"
                ET.SubElement(limit, "upper").text = f"{math.radians(j['upper']):.5f}"
            elif j["type"] == "prismatica":
                ET.SubElement(limit, "lower").text = f"{j['lower'] * MM:.5f}"
                ET.SubElement(limit, "upper").text = f"{j['upper'] * MM:.5f}"
            else:  # continua
                ET.SubElement(limit, "lower").text = "-1e16"
                ET.SubElement(limit, "upper").text = "1e16"

    ET.indent(sdf)
    xml = '<?xml version="1.0"?>\n' + ET.tostring(sdf, encoding="unicode")
    return xml, meshes


def export_sdf_zip(doc, robot_name: str = "apolo_robot") -> bytes:
    xml, meshes = build_sdf(doc, robot_name)
    return _zip_with_meshes(xml, "model.sdf", meshes)
