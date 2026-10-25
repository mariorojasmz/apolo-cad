"""Schemas pydantic de los parámetros de cada comando.

Estos modelos son la única fuente de verdad: de su JSON Schema se generan
los formularios de la UI y las tools del agente IA.

FACHADA (plan partir-nucleo-congelado, F2): los modelos viven por familia en
`models_base` (Vec3, Rot3, listas de catálogo), `models_basicos`, `models_maquinas`,
`models_chapa`, `models_modificar`, `models_croquis` y `models_ensamblaje`; aquí se
re-exportan por IDENTIDAD, para siempre (`tests/test_rutas_viejas.py`). `models_base` se
importa PRIMERO: `models_cilindro`, `models_faja`… importan `Vec3`/`Rot3` de `.models`.
"""

from __future__ import annotations

from .models_base import (  # noqa: F401
    _floor_to_int,
    Vec3,
    Rot3,
    _roller_refs,
    _profile_refs,
    _motor_refs,
)

# la selección de caras/aristas vive en su módulo; se re-exporta con el mismo nombre
from .models_selectores import EdgeSelector, SlideUV  # noqa: F401
from .models_union import JoinBoltedParams  # noqa: F401 — se re-exporta (salió por tamaño)

from .models_basicos import (  # noqa: F401
    CreateBoxParams,
    CreateCylinderParams,
    CreateStructuralProfileParams,
    BooleanOpParams,
    TransformParams,
    PatternLinearParams,
    PatternGroupParams,
    DeleteParams,
    DuplicateParams,
    CenterInParams,
    DistributeParams,
    ANCHOR_NAMES,
    AttachParams,
    SnapToParams,
    SetVariableParams,
)
from .models_maquinas import (  # noqa: F401
    CreateConveyorParams,
    CreateWeldmentParams,
    CreateFrameParams,
    RunScriptParams,
    CreateRobotArmParams,
)
from .models_chapa import (  # noqa: F401
    SheetSide,
    Hole,
    FlapHole,
    FlapCutout,
    ChildFlap,
    FlapSpec,
    SheetMetalParams,
)
from .models_modificar import (  # noqa: F401
    FilletParams,
    DeleteFacesParams,
    PushFaceParams,
    ChamferParams,
    ShellParams,
    DRILL_AXES,
    DrillHoleParams,
    PatternCircularParams,
    MirrorParams,
    JOINERY_TYPES,
    AddJoineryParams,
)
from .models_croquis import (  # noqa: F401
    CreateRevolveParams,
    CreateExtrudePolyParams,
    ImportStepParams,
    SKETCH_DOC,
    SketchExtrudeParams,
    SketchRevolveParams,
    HelixSpec,
    SketchSweepParams,
    LoftSection,
    SketchLoftParams,
    CurveSpec,
    BoundarySurfaceParams,
    FillSurfaceParams,
    ThickenParams,
)
from .models_ensamblaje import (  # noqa: F401
    JOINT_TYPES,
    AddJointParams,
    MATE_TYPES,
    AddMateParams,
    AddRailConstraintParams,
    CONSTRAINT_TYPES,
    AddConstraintParams,
    CreateGroupParams,
    TransformGroupParams,
    InsertProjectParams,
    GroundParams,
)


def __getattr__(nombre: str):
    """`InsertComponentParams` salió a `models_componente.py` (trinquete de tamaño) y se
    re-exporta PEREZOSO: aquel módulo importa `Vec3`/`Rot3` de éste."""
    if nombre in ("InsertComponentParams", "OrientacionPerfil"):
        from . import models_componente

        return getattr(models_componente, nombre)
    raise AttributeError(f"module {__name__!r} has no attribute {nombre!r}")
