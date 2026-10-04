"""Contrato de los comandos con los logs guardados: ningún campo desaparece sin upcaster (D12).

Plan `estado-regen-y-params-estrictos`. Un `.apolo` guarda los params de cada comando tal cual
se mandaron, y el replay IGNORA en silencio una clave que el modelo ya no declara (D6: así
regeneran los logs viejos). Por eso quitar o renombrar un campo no rompe nada visible: el log
viejo pierde ese dato y regenera con el default, distinto de lo que se diseñó.

**Trinquete** (el patrón de `tests/test_tamano_archivos.py`). `CAMPOS` declara las rutas de
campos de cada comando (`apolo.commands.strict.field_paths`: `position.x`,
`flaps[].child.altura`). El gate falla si:
  - una ruta DESAPARECE: conserva el campo (con un default que reproduzca lo anterior) o
    escribe un upcaster que traduzca los logs viejos; recién entonces sácala de `CAMPOS`;
  - aparece una ruta o un comando sin declarar: agrégalo (un campo nuevo entra con un default
    que reproduce lo anterior: raíz § Log de comandos);
  - un comando declarado ya no existe: sus logs guardados quedarían sin executor.

`python tests/test_contrato_comandos.py` imprime el literal actual para pegar.
"""

from __future__ import annotations

from apolo.commands.registry import REGISTRY
from apolo.commands.strict import field_paths

# ── Rutas de campos por comando (se generan; ver el docstring) ───────────────────────────
CAMPOS: dict[str, str] = {
    "add_constraint": (
        "name tipo joint anchor anchor.x anchor.y anchor.z point point.x point.y point.z axis "
        "axis.x axis.y axis.z value"
    ),
    "add_joinery": (
        "name type feature_a feature_b position position.x position.y position.z axis axis.x "
        "axis.y axis.z width height depth count spacing clearance"
    ),
    "add_joint": (
        "name type parent child origin origin.x origin.y origin.z axis axis.x axis.y axis.z lower "
        "upper arrastrar"
    ),
    "add_mate": (
        "name type feature_a feature_b ref_a ref_a.mode ref_a.direction ref_a.face ref_a.min "
        "ref_a.max ref_a.point ref_a.count ref_a.entidad ref_a.name ref_b ref_b.mode "
        "ref_b.direction ref_b.face ref_b.min ref_b.max ref_b.point ref_b.count ref_b.entidad "
        "ref_b.name value flip"
    ),
    "add_rail_constraint": (
        "name joint anchor anchor.x anchor.y anchor.z point point.x point.y point.z axis axis.x "
        "axis.y axis.z"
    ),
    "attach": (
        "feature anchor target target_anchor offset offset.x offset.y offset.z align_my align_to"
    ),
    "boolean_op": "name operation target tools",
    "boundary_surface": (
        "name curves curves[].points curves[].smooth points holes holes[].points holes[].smooth "
        "position position.x position.y position.z rotation rotation.x rotation.y rotation.z"
    ),
    "center_in": "feature into axes",
    "chamfer": (
        "feature edges edges.mode edges.direction edges.face edges.min edges.max edges.point "
        "edges.count edges.entidad edges.name distance"
    ),
    "create_belt_conveyor": (
        "name largo ancho_banda altura espesor_banda tambor_motriz tambor_cola tubo tensor motor "
        "guardas position position.x position.y position.z rotation rotation.x rotation.y "
        "rotation.z"
    ),
    "create_box": (
        "name width depth height position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z"
    ),
    "create_conveyor": (
        "name largo ancho altura paso rodillo motor position position.x position.y position.z "
        "rotation rotation.x rotation.y rotation.z"
    ),
    "create_cylinder": (
        "name radius height axis position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z"
    ),
    "create_drive_roller": (
        "name diam_rodillo ancho_banda rodamiento perno espesor_soporte voladizo largo_eje_motor "
        "dir_tensor engomado holgura_eje position position.x position.y position.z rotation "
        "rotation.x rotation.y rotation.z"
    ),
    "create_extrude_poly": (
        "name points height axis position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z"
    ),
    "create_frame": (
        "name nodes edges perfil cordones esquinas position position.x position.y position.z "
        "rotation rotation.x rotation.y rotation.z"
    ),
    "create_group": "name members parent role",
    "create_revolve": (
        "name profile angle axis position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z"
    ),
    "create_robot_arm": "name alcance position position.x position.y position.z",
    "create_sheet_metal": (
        "name ancho fondo espesor lados altura_pestana angulo radio k_factor holes holes[].x "
        "holes[].y holes[].d flaps flaps[].lado flaps[].altura flaps[].angulo flaps[].radio "
        "flaps[].holes flaps[].holes[].u flaps[].holes[].v flaps[].holes[].d flaps[].cutouts "
        "flaps[].cutouts[].u flaps[].cutouts[].v flaps[].cutouts[].ancho flaps[].cutouts[].alto "
        "flaps[].child flaps[].child.altura flaps[].child.angulo flaps[].child.radio "
        "flaps[].child.direccion flaps[].child.holes flaps[].child.holes[].u "
        "flaps[].child.holes[].v flaps[].child.holes[].d flaps[].child.cutouts "
        "flaps[].child.cutouts[].u flaps[].child.cutouts[].v flaps[].child.cutouts[].ancho "
        "flaps[].child.cutouts[].alto position position.x position.y position.z rotation "
        "rotation.x rotation.y rotation.z"
    ),
    "create_structural_profile": (
        "name profile length position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z"
    ),
    "create_take_up": (
        "name diam_rodillo ancho_banda rodamiento perno espesor_soporte voladizo dir_tensor "
        "engomado holgura_eje eje_fit position position.x position.y position.z rotation "
        "rotation.x rotation.y rotation.z"
    ),
    "create_weldment": (
        "name ancho fondo alto perfil anillos_intermedios cordones esquinas position position.x "
        "position.y position.z rotation rotation.x rotation.y rotation.z"
    ),
    "delete_faces": (
        "feature faces faces.mode faces.direction faces.face faces.min faces.max faces.point "
        "faces.count faces.entidad faces.name tangentes"
    ),
    "delete_feature": "feature",
    "distribute": "features axis start end",
    "drill_hole": (
        "feature position position.x position.y position.z axis cara cara.mode cara.direction "
        "cara.face cara.min cara.max cara.point cara.count cara.entidad cara.name en_cara "
        "en_cara.u en_cara.v diameter depth counterbore_d counterbore_depth fit thread"
    ),
    "duplicate_feature": "feature offset offset.x offset.y offset.z",
    "fasten": "name a b kind size qty throat_mm length_mm nota",
    "fill_surface": (
        "name feature edges edges.mode edges.direction edges.face edges.min edges.max edges.point "
        "edges.count edges.entidad edges.name tangent"
    ),
    "fillet": (
        "feature edges edges.mode edges.direction edges.face edges.min edges.max edges.point "
        "edges.count edges.entidad edges.name radius"
    ),
    "ground": "name feature nota",
    "import_step": (
        "attachment name split position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z"
    ),
    "insert_component": (
        "component name length position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z"
    ),
    "insert_project": (
        "project_id attachment name overrides position position.x position.y position.z rotation "
        "rotation.x rotation.y rotation.z keep_grounds"
    ),
    "join_bolted": "name a b size count patron spacing norma",
    "mirror_feature": "feature plane offset",
    "pattern_circular": (
        "feature count axis_point axis_point.x axis_point.y axis_point.z axis_dir total_angle"
    ),
    "pattern_group": (
        "source count spacing spacing.x spacing.y spacing.z count2 spacing2 spacing2.x spacing2.y "
        "spacing2.z"
    ),
    "pattern_linear": "feature count spacing spacing.x spacing.y spacing.z",
    "push_face": (
        "feature face face.mode face.direction face.face face.min face.max face.point face.count "
        "face.entidad face.name distance"
    ),
    "run_script": (
        "name code position position.x position.y position.z rotation rotation.x rotation.y "
        "rotation.z"
    ),
    "set_variable": "name expression",
    "shell": (
        "feature openings openings.mode openings.direction openings.face openings.min "
        "openings.max openings.point openings.count openings.entidad openings.name thickness"
    ),
    "sketch_extrude": (
        "name sketch plane height position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z"
    ),
    "sketch_loft": (
        "name sections sections[].sketch sections[].z ruled position position.x position.y "
        "position.z rotation rotation.x rotation.y rotation.z"
    ),
    "sketch_revolve": (
        "name sketch angle position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z"
    ),
    "sketch_sweep": (
        "name sketch path smooth closed helix helix.radius helix.pitch helix.turns helix.lefthand "
        "position position.x position.y position.z rotation rotation.x rotation.y rotation.z"
    ),
    "snap_to": (
        "feature target lado gap alinear cara cara.mode cara.direction cara.face cara.min "
        "cara.max cara.point cara.count cara.entidad cara.name cara_target cara_target.mode "
        "cara_target.direction cara_target.face cara_target.min cara_target.max cara_target.point "
        "cara_target.count cara_target.entidad cara_target.name deslizar deslizar.u deslizar.v"
    ),
    "thicken": "feature thickness both flip",
    "transform": (
        "feature translate translate.x translate.y translate.z rotate rotate.x rotate.y rotate.z"
    ),
    "transform_group": (
        "group translate translate.x translate.y translate.z rotate rotate.x rotate.y rotate.z"
    ),
}


# ── Medición ──────────────────────────────────────────────────────────────────────────────


def rutas_actuales() -> dict[str, list[str]]:
    return {t: field_paths(spec.model) for t, spec in sorted(REGISTRY.items())}


def _envuelve(rutas: list[str], ancho: int = 88) -> list[str]:
    lineas, actual = [], ""
    for r in rutas:
        if actual and len(actual) + 1 + len(r) > ancho:
            lineas.append(actual + " ")
            actual = r
        else:
            actual = f"{actual} {r}" if actual else r
    return lineas + [actual]


def literal_campos() -> str:
    out = ["CAMPOS: dict[str, str] = {"]
    for tipo, rutas in rutas_actuales().items():
        partes = _envuelve(rutas)
        if len(partes) == 1 and len(tipo) + len(partes[0]) < 86:
            out.append(f'    "{tipo}": "{partes[0]}",')
        else:
            out.append(f'    "{tipo}": (')
            out += [f'        "{p}"' for p in partes]
            out.append("    ),")
    return "\n".join(out + ["}"])


# ── Gate ──────────────────────────────────────────────────────────────────────────────────


def test_ningun_campo_desaparece_sin_upcaster():
    perdidos = []
    for tipo, declaradas in CAMPOS.items():
        actuales = set(field_paths(REGISTRY[tipo].model)) if tipo in REGISTRY else set()
        faltan = [r for r in declaradas.split() if r not in actuales]
        if tipo not in REGISTRY:
            perdidos.append(f"  {tipo}: el comando ya no existe (sus logs no tienen executor)")
        elif faltan:
            perdidos.append(f"  {tipo}: {', '.join(faltan)}")
    assert not perdidos, (
        "Desaparecieron campos que un log guardado puede usar (el replay los ignoraría en "
        "silencio y regeneraría con el default):\n" + "\n".join(perdidos) + "\n"
        "Conserva el campo con un default que reproduzca lo anterior, o escribe un upcaster "
        "que traduzca los logs viejos; recién entonces sácalo de CAMPOS."
    )


def test_cada_campo_nuevo_queda_declarado():
    nuevos = []
    for tipo, rutas in rutas_actuales().items():
        declaradas = set(CAMPOS.get(tipo, "").split())
        sobran = [r for r in rutas if r not in declaradas]
        if tipo not in CAMPOS:
            nuevos.append(f"  {tipo}: comando nuevo")
        elif sobran:
            nuevos.append(f"  {tipo}: {', '.join(sobran)}")
    assert not nuevos, (
        "Campos o comandos sin declarar en CAMPOS (un campo nuevo entra con un default que "
        "reproduce lo anterior; después, declarado aquí, ya no puede desaparecer sin "
        "upcaster):\n" + "\n".join(nuevos) + "\n"
        "Pega el literal que imprime `python tests/test_contrato_comandos.py`."
    )


def test_field_paths_recorre_anidados_listas_y_opcionales():
    rutas = field_paths(REGISTRY["create_sheet_metal"].model)
    assert {"position.x", "flaps[].lado", "flaps[].child.holes[].d"} <= set(rutas)
    assert "cara.point" in field_paths(REGISTRY["drill_hole"].model)  # `EdgeSelector | None`


if __name__ == "__main__":
    print(literal_campos())
