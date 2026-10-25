"""Gate permanente: las rutas viejas del núcleo siguen sirviendo, por IDENTIDAD, para siempre.

Plan [partir-nucleo-congelado](../docs/plans/partir-nucleo-congelado.md), D2 y D11: al partir
un archivo congelado, su ruta vieja queda como fachada (shim) que re-exporta cada nombre de
nivel superior que definía. Las listas son CERRADAS: un nombre que falta o que deja de ser el
MISMO objeto que en su casa nueva pone el gate rojo (un re-export por valor o una copia harían
que parchear una ruta no alcance a la otra). Cada fase del plan suma su sección.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

# ── models (F2) ───────────────────────────────────────────────────────────────

#: Casa nueva de cada nombre que `apolo.commands.models` definía en `1f01d0a`/`553b208`
#: (69 definiciones de nivel superior), en el orden del archivo original por familia.
MODELS: dict[str, tuple[str, ...]] = {
    "apolo.commands.models_base": (
        "_floor_to_int", "Vec3", "Rot3", "_roller_refs", "_profile_refs", "_motor_refs",
    ),
    "apolo.commands.models_basicos": (
        "CreateBoxParams", "CreateCylinderParams", "CreateStructuralProfileParams",
        "BooleanOpParams", "TransformParams", "PatternLinearParams", "PatternGroupParams",
        "DeleteParams", "DuplicateParams", "CenterInParams", "DistributeParams", "ANCHOR_NAMES",
        "AttachParams", "SnapToParams", "SetVariableParams",
    ),
    "apolo.commands.models_maquinas": (
        "CreateConveyorParams", "CreateWeldmentParams", "CreateFrameParams", "RunScriptParams",
        "CreateRobotArmParams",
    ),
    "apolo.commands.models_chapa": (
        "SheetSide", "Hole", "FlapHole", "FlapCutout", "ChildFlap", "FlapSpec",
        "SheetMetalParams",
    ),
    "apolo.commands.models_modificar": (
        "FilletParams", "DeleteFacesParams", "PushFaceParams", "ChamferParams", "ShellParams",
        "DRILL_AXES", "DrillHoleParams", "PatternCircularParams", "MirrorParams",
        "JOINERY_TYPES", "AddJoineryParams",
    ),
    "apolo.commands.models_croquis": (
        "CreateRevolveParams", "CreateExtrudePolyParams", "ImportStepParams", "SKETCH_DOC",
        "SketchExtrudeParams", "SketchRevolveParams", "HelixSpec", "SketchSweepParams",
        "LoftSection", "SketchLoftParams", "CurveSpec", "BoundarySurfaceParams",
        "FillSurfaceParams", "ThickenParams",
    ),
    "apolo.commands.models_ensamblaje": (
        "JOINT_TYPES", "AddJointParams", "MATE_TYPES", "AddMateParams",
        "AddRailConstraintParams", "CONSTRAINT_TYPES", "AddConstraintParams",
        "CreateGroupParams", "TransformGroupParams", "InsertProjectParams", "GroundParams",
    ),
    # re-exports que `models` ya tenía antes de partirse (dos directos, dos perezosos)
    "apolo.commands.models_selectores": ("EdgeSelector", "SlideUV"),
    "apolo.commands.models_union": ("JoinBoltedParams",),
    "apolo.commands.models_componente": ("InsertComponentParams", "OrientacionPerfil"),
}

#: Las definiciones propias de `models` antes de partirse (sin los re-exports viejos).
DEFINICIONES_MODELS = 69


def faltantes(ruta_vieja: str, casas: dict[str, tuple[str, ...]]) -> list[str]:
    """Nombres que `ruta_vieja` ya no sirve o que no son el MISMO objeto que en su casa."""
    vieja = importlib.import_module(ruta_vieja)
    malos: list[str] = []
    for casa, nombres in casas.items():
        nueva = importlib.import_module(casa)
        for nombre in nombres:
            if not hasattr(vieja, nombre):
                malos.append(f"{ruta_vieja}.{nombre}: ya no existe")
            elif getattr(vieja, nombre) is not getattr(nueva, nombre):
                malos.append(f"{ruta_vieja}.{nombre}: no es el objeto de {casa}")
    return malos


def test_models_sirve_cada_nombre_viejo_por_identidad():
    assert faltantes("apolo.commands.models", MODELS) == []


#: Casas de los re-exports que `models` ya tenía (no son definiciones suyas).
_REEXPORTS_VIEJOS = {
    "apolo.commands.models_selectores",
    "apolo.commands.models_union",
    "apolo.commands.models_componente",
}


def test_models_lista_cerrada():
    propios = [n for casa, ns in MODELS.items() if casa not in _REEXPORTS_VIEJOS for n in ns]
    assert len(propios) == len(set(propios)) == DEFINICIONES_MODELS


@pytest.mark.parametrize("casa", sorted(MODELS))
def test_cada_casa_nueva_define_lo_que_se_le_atribuye(casa):
    """La casa declarada es la de verdad (una clase o función nace en su módulo)."""
    mod = importlib.import_module(casa)
    for nombre in MODELS[casa]:
        obj = getattr(mod, nombre)
        if isinstance(obj, type) or inspect.isfunction(obj):
            assert obj.__module__ == casa, f"{nombre} nace en {obj.__module__}, no en {casa}"


def test_el_gate_caza_un_nombre_que_falta(monkeypatch):
    import apolo.commands.models as models

    monkeypatch.delattr(models, "Vec3")
    assert faltantes("apolo.commands.models", MODELS) == [
        "apolo.commands.models.Vec3: ya no existe"
    ]


def test_el_gate_caza_una_copia_en_vez_del_mismo_objeto(monkeypatch):
    import apolo.commands.models as models

    class CreateBoxParams:  # mismo nombre, otro objeto
        pass

    monkeypatch.setattr(models, "CreateBoxParams", CreateBoxParams)
    assert faltantes("apolo.commands.models", MODELS) == [
        "apolo.commands.models.CreateBoxParams: no es el objeto de apolo.commands.models_basicos"
    ]
