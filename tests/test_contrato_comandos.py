"""Contrato de los comandos con los logs guardados (plan `estado-regen-y-params-estrictos`).

Dos trinquetes (el patrón de `tests/test_tamano_archivos.py`), extras vetables del plan:

**Ningún campo desaparece sin upcaster (D12).** Un `.apolo` guarda los params de cada comando
tal cual se mandaron, y el replay IGNORA en silencio una clave que el modelo ya no declara
(D6: así regeneran los logs viejos). Quitar o renombrar un campo no rompe nada visible: el log
viejo pierde ese dato y regenera con el default, distinto de lo que se diseñó. `CAMPOS`
declara las rutas de cada comando (`apolo.commands.strict.field_paths`: `position.x`,
`flaps[].child.altura`). Falla si:
  - una ruta DESAPARECE: conserva el campo (con un default que reproduzca lo anterior) o
    escribe un upcaster que traduzca los logs viejos; recién entonces sácala de `CAMPOS`;
  - aparece una ruta o un comando sin declarar: agrégalo (un campo nuevo entra con un default
    que reproduce lo anterior: raíz § Log de comandos);
  - un comando declarado ya no existe: sus logs guardados quedarían sin executor.

**Ningún executor cambia sin decidir su versión (D11).** La caché de geometría reanuda por
firmas de params: si el código de un executor cambia la geometría con los MISMOS params y su
`version` no sube, un open caliente sirve la geometría vieja. `VERSIONES` guarda
`{tipo: (version, huella del código del executor)}`. Si la huella cambió y la versión no,
falla y obliga a elegir: subir la versión (cambió la geometría) o actualizar sólo la huella
(fue un refactor). La huella es la de la función del executor, no la de los helpers que
llama: un helper compartido lo cubre la regla D10 (`core/apolo/commands/CLAUDE.md`).

La lógica (`problemas_de_campos`, `problemas_de_version`, `huella`) vive en
`apolo/contrato_comandos.py`, que viaja en la wheel: la suite de una extensión aplica los MISMOS
trinquetes a sus comandos con su propio `CAMPOS`/`VERSIONES` (nucleo-abierto F1c).

`python tests/test_contrato_comandos.py` imprime los dos literales actuales para pegar.
"""

from __future__ import annotations

from apolo.commands.registry import REGISTRY
from apolo.commands.strict import field_paths
from apolo.contrato_comandos import (
    huella,
    literal_campos,
    literal_versiones,
    problemas_de_campos,
    problemas_de_version,
)

# ── Rutas de campos por comando (se generan; ver el docstring) ───────────────────────────
CAMPOS: dict[str, str] = {
    "add_cable": "designacion ref desde hasta largo_m piezas",
    "add_constraint": (
        "name tipo joint anchor anchor.x anchor.y anchor.z point point.x point.y point.z axis "
        "axis.x axis.y axis.z value"
    ),
    "add_device": "ref designacion ubicacion pieza ajustes cantidad",
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
        "ref_a.max ref_a.point ref_a.count ref_a.medir ref_a.entidad ref_a.name ref_b ref_b.mode "
        "ref_b.direction ref_b.face ref_b.min ref_b.max ref_b.point ref_b.count ref_b.medir "
        "ref_b.entidad ref_b.name value flip"
    ),
    "add_rail_constraint": (
        "name joint anchor anchor.x anchor.y anchor.z point point.x point.y point.z axis axis.x "
        "axis.y axis.z"
    ),
    "add_program": "plc nombre lenguaje fuente ciclo_ms ciclos",
    "add_wire": "puntos seccion_mm2 color tipo cable hilo potencial largo_m",
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
        "edges.count edges.medir edges.entidad edges.name distance"
    ),
    "create_belt_conveyor": (
        "name largo ancho_banda altura espesor_banda tambor_motriz tambor_cola tubo tensor motor "
        "guardas cierres position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z"
    ),
    "create_box": (
        "name width depth height position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z"
    ),
    "create_chain": (
        "name cadena pinon_a pinon_b hilera_a hilera_b detalle eslabones fase potencia_kw rpm_a "
        "servicio"
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
    "create_roller_conveyor": (
        "name largo ancho_util paso rodillo altura carga_kg motriz motor velocidad_m_s anclaje "
        "position position.x position.y position.z"
    ),
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
        "engomado coronado_mm holgura_eje eje_fit position position.x position.y position.z "
        "rotation rotation.x rotation.y rotation.z"
    ),
    "create_weldment": (
        "name ancho fondo alto perfil anillos_intermedios cordones esquinas position position.x "
        "position.y position.z rotation rotation.x rotation.y rotation.z"
    ),
    "delete_faces": (
        "feature faces faces.mode faces.direction faces.face faces.min faces.max faces.point "
        "faces.count faces.medir faces.entidad faces.name tangentes"
    ),
    "delete_feature": "feature",
    "distribute": "features axis start end",
    "drill_hole": (
        "feature position position.x position.y position.z axis cara cara.mode cara.direction "
        "cara.face cara.min cara.max cara.point cara.count cara.medir cara.entidad cara.name "
        "en_cara en_cara.u en_cara.v diameter depth counterbore_d counterbore_depth fit thread"
    ),
    "duplicate_feature": "feature offset offset.x offset.y offset.z",
    "fasten": "name a b kind size qty throat_mm length_mm nota",
    "fill_surface": (
        "name feature edges edges.mode edges.direction edges.face edges.min edges.max edges.point "
        "edges.count edges.medir edges.entidad edges.name tangent"
    ),
    "fillet": (
        "feature edges edges.mode edges.direction edges.face edges.min edges.max edges.point "
        "edges.count edges.medir edges.entidad edges.name radius"
    ),
    "ground": "name feature nota",
    "import_step": (
        "attachment name split position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z"
    ),
    "insert_component": (
        "component name length position position.x position.y position.z rotation rotation.x "
        "rotation.y rotation.z orientacion orientacion.largo orientacion.abre_hacia "
        "orientacion.canto orientacion.alas criterio"
    ),
    "insert_project": (
        "project_id attachment name overrides position position.x position.y position.z rotation "
        "rotation.x rotation.y rotation.z keep_grounds"
    ),
    "join_bolted": "name a b size count patron spacing norma criterio madera",
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
        "face.medir face.entidad face.name distance"
    ),
    "run_script": (
        "name code position position.x position.y position.z rotation rotation.x rotation.y "
        "rotation.z"
    ),
    "set_variable": "name expression",
    "shell": (
        "feature openings openings.mode openings.direction openings.face openings.min "
        "openings.max openings.point openings.count openings.medir openings.entidad openings.name "
        "thickness"
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
        "cara.max cara.point cara.count cara.medir cara.entidad cara.name cara_target "
        "cara_target.mode cara_target.direction cara_target.face cara_target.min cara_target.max "
        "cara_target.point cara_target.count cara_target.medir cara_target.entidad "
        "cara_target.name deslizar deslizar.u deslizar.v"
    ),
    "thicken": "feature thickness both flip",
    "transform": (
        "feature translate translate.x translate.y translate.z rotate rotate.x rotate.y rotate.z"
    ),
    "transform_group": (
        "group translate translate.x translate.y translate.z rotate rotate.x rotate.y rotate.z"
    ),
}

# ── Versión y huella del código de cada executor (se generan; ver el docstring) ───────────
VERSIONES: dict[str, tuple[int, str]] = {
    "add_cable": (1, "d824d9f16db621b8"),
    "add_constraint": (1, "18a7bd522aeca52f"),
    "add_device": (1, "d824d9f16db621b8"),
    "add_joinery": (1, "6ccbf5bbf26c1cb1"),
    "add_joint": (1, "7569d5069e5caaeb"),
    "add_mate": (1, "a3596f3795b93db8"),
    "add_rail_constraint": (1, "591f0dc2cac566fe"),
    "add_program": (1, "d824d9f16db621b8"),
    "add_wire": (1, "d824d9f16db621b8"),
    "attach": (1, "cb91ea338ddcb3c9"),
    "boolean_op": (1, "81e15484e1e85781"),
    "boundary_surface": (1, "31495c5cb0a9bf8d"),
    "center_in": (1, "228e71c9315f37c8"),
    "chamfer": (1, "2fcdc6b118e984ba"),
    # compuesto: corre fasten/ground; cotas y plan en library/belt_conveyor*.py (D10). v5: cierres
    # (campo oculto que pone el sello de entrada; un log v4 trae False → misma geometría)
    "create_belt_conveyor": (5, "a593b7f744a57110"),
    "create_box": (1, "fcc825dfc9669eac"),
    "create_chain": (2, "c0911a5d981a48bd"),
    "create_conveyor": (1, "57fa344a272c945c"),
    "create_cylinder": (1, "df2b2a1a5fb50cf9"),
    "create_drive_roller": (2, "5d9571216a3a26e0"),  # v2: «Anillo Seeger DIN 472-Ø» (F6)
    "create_extrude_poly": (1, "1b52acc21ee53008"),
    "create_frame": (1, "d8387fb3400cbec1"),
    "create_group": (1, "450675e65cecac8a"),
    "create_revolve": (1, "1688dc48118c2a15"),
    "create_robot_arm": (1, "c4ceee70195b1ad0"),
    # compuesto: la huella es la del executor; cotas y receta viven en otros módulos (regla D10)
    "create_roller_conveyor": (3, "450707432cde2d9d"),
    "create_sheet_metal": (1, "2aeed3174e15adda"),
    "create_structural_profile": (1, "ada70bc0722ffb7f"),
    # +coronado_mm: con 0 (default) la geometría no cambia; v2: «Anillo Seeger DIN 472-Ø» (F6)
    "create_take_up": (2, "a02e2fb07d4773ae"),
    "create_weldment": (1, "344bdbf91fff4cd9"),
    "delete_faces": (1, "1f3b55e6bf50bed4"),
    "delete_feature": (1, "131eec22d5b444b7"),
    "distribute": (1, "dbd8f19a2efade42"),
    "drill_hole": (1, "f9fe72f8f410fa3f"),
    "duplicate_feature": (1, "1e53ee34eb4d6e87"),
    "fasten": (1, "dc344ffbe685a9f5"),
    "fill_surface": (1, "16418efc4d5e7384"),
    "fillet": (1, "f63f072057031b48"),
    "ground": (1, "afb091e73600725e"),
    "import_step": (1, "d75412508c6ccfdd"),
    # v2: anclas de perfil abierto; criterio 2 (F6): un log viejo trae 1 → misma geometría y firma
    "insert_component": (2, "26b05f2f1a36a2ed"),
    "insert_project": (1, "01664975967281c6"),
    "join_bolted": (1, "24fbb11752560dc0"),  # criterio 2 (union-en-perfil-hueco): un log viejo trae 1 → misma geometría y firma
    "mirror_feature": (1, "6973b59545d49469"),
    "pattern_circular": (1, "608d05fdba3297c0"),
    "pattern_group": (1, "cb174b5f27cebde8"),
    "pattern_linear": (1, "ecfdc2b719ffbc08"),
    "push_face": (1, "55dda35c7aab1ee7"),
    "run_script": (2, "0428994fa44d3402"),  # v2: la forma vuelve del worker en BRep (sandbox-caliente D6)
    "set_variable": (1, "20e2308e5779cf31"),
    "shell": (1, "89dc700db43488bd"),
    "sketch_extrude": (1, "a015278d8aa9a46c"),
    "sketch_loft": (1, "e41e6a032e0d5888"),
    "sketch_revolve": (1, "c3d7c1be67aa287f"),
    "sketch_sweep": (1, "49793adb31fb3547"),
    "snap_to": (1, "266d691576cbc90e"),
    "thicken": (1, "eac24a8527d7c1d1"),
    "transform": (1, "677c04429f2aced8"),
    "transform_group": (1, "343448f3917778d0"),
}


# ── Gate (la lógica viaja en la wheel: `apolo.contrato_comandos`, la usa también una extensión) ─


def test_ningun_campo_desaparece_sin_upcaster():
    perdidos, _ = problemas_de_campos(REGISTRY, CAMPOS)
    assert not perdidos, (
        "Desaparecieron campos que un log guardado puede usar (el replay los ignoraría en "
        "silencio y regeneraría con el default):\n" + "\n".join(perdidos) + "\n"
        "Conserva el campo con un default que reproduzca lo anterior, o escribe un upcaster "
        "que traduzca los logs viejos; recién entonces sácalo de CAMPOS."
    )


def test_cada_campo_nuevo_queda_declarado():
    _, nuevos = problemas_de_campos(REGISTRY, CAMPOS)
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


def test_ningun_executor_cambia_sin_decidir_su_version():
    problemas = problemas_de_version(REGISTRY, VERSIONES)
    assert not problemas, (
        "Contrato de versiones de los executors (D11):\n" + "\n".join(problemas) + "\n"
        "Si cambia la geometría que produce con los MISMOS params, sube `version` en su "
        "CommandSpec (invalida la caché SÓLO de los proyectos que lo usan); si fue un refactor "
        "sin efecto en la geometría, actualiza sólo la huella. Después pega el literal que "
        "imprime `python tests/test_contrato_comandos.py` (regla D10: "
        "core/apolo/commands/CLAUDE.md)."
    )


def test_el_trinquete_de_versiones_ve_cada_salida():
    """Código cambiado sin versión → falla; versión subida → pide declararla; versión que
    baja → falla; refactor declarado (huella nueva, misma versión) → pasa."""
    from types import SimpleNamespace

    def ejecutor_a(ctx, cmd_id, p):
        return None

    def ejecutor_b(ctx, cmd_id, p):
        return p

    def registro(version, fn):
        return {"x": SimpleNamespace(version=version, executor=fn)}

    declarado = {"x": (2, huella(ejecutor_a))}
    assert problemas_de_version(registro(2, ejecutor_a), declarado) == []
    assert "cambió y su versión no" in problemas_de_version(registro(2, ejecutor_b), declarado)[0]
    assert "subiste a v3" in problemas_de_version(registro(3, ejecutor_b), declarado)[0]
    assert "BAJÓ" in problemas_de_version(registro(1, ejecutor_a), declarado)[0]
    assert problemas_de_version(registro(2, ejecutor_b), {"x": (2, huella(ejecutor_b))}) == []
    assert "ya no existe" in problemas_de_version({}, declarado)[0]


def test_el_trinquete_de_campos_ve_cada_salida():
    """Sobre un registro cualquiera (lo que hace la suite de una extensión): campo perdido,
    comando que ya no existe, campo nuevo y comando nuevo."""
    from types import SimpleNamespace

    from pydantic import BaseModel

    class P(BaseModel):
        a: int = 1
        b: int = 2

    reg = {"x.uno": SimpleNamespace(model=P)}
    assert problemas_de_campos(reg, {"x.uno": "a b"}) == ([], [])
    perdidos, nuevos = problemas_de_campos(reg, {"x.uno": "a b c", "x.dos": "a"})
    assert perdidos == ["  x.uno: c", "  x.dos: el comando ya no existe (sus logs no tienen executor)"]
    assert problemas_de_campos(reg, {"x.uno": "a"})[1] == ["  x.uno: b"]
    assert problemas_de_campos(reg, {})[1] == ["  x.uno: comando nuevo"]
    assert '"x.uno": "a b"' in literal_campos(reg)


if __name__ == "__main__":
    print(literal_campos(REGISTRY))
    print()
    print(literal_versiones(REGISTRY))