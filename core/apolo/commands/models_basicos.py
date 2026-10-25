"""Params de lo básico: primitivas, booleana, transform, patrones lineal y de grupo,
borrar, duplicar, colocación por intención (centrar, repartir, attach, snap_to) y variables.

Sale de `models.py` (fachada) por tamaño.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .models_base import Rot3, Vec3, _floor_to_int
from .models_selectores import EdgeSelector, SlideUV


class CreateBoxParams(BaseModel):
    """Caja rectangular centrada en el origen."""

    name: str = Field("Caja", title="Nombre")
    width: float = Field(100, gt=0, le=100000, title="Ancho (X)", description="mm")
    depth: float = Field(100, gt=0, le=100000, title="Fondo (Y)", description="mm")
    height: float = Field(100, gt=0, le=100000, title="Alto (Z)", description="mm")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")


class CreateCylinderParams(BaseModel):
    """Cilindro centrado en el origen. Por defecto su eje es Z; usa `axis` para
    crearlo a lo largo de X o Y sin rotarlo manualmente."""

    name: str = Field("Cilindro", title="Nombre")
    radius: float = Field(25, gt=0, le=50000, title="Radio", description="mm")
    height: float = Field(100, gt=0, le=100000, title="Altura", description="mm")
    axis: Literal["x", "y", "z"] = Field("z", title="Eje", description="eje del cilindro (z por defecto)")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")


class CreateStructuralProfileParams(BaseModel):
    """Perfil de aluminio ranurado (tipo T-slot), extruido a lo largo de Z y centrado."""

    name: str = Field("Perfil", title="Nombre")
    profile: Literal["20x20", "30x30", "40x40", "40x80", "45x45"] = Field(
        "40x40", title="Sección"
    )
    length: float = Field(1000, gt=0, le=12000, title="Largo", description="mm")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")


class BooleanOpParams(BaseModel):
    """Combina sólidos: el resultado sustituye al objetivo y consume las herramientas."""

    name: str = Field("Booleana", title="Nombre")
    operation: Literal["union", "cut", "intersect"] = Field("union", title="Operación")
    target: str = Field(..., title="Sólido objetivo", description="id de feature")
    tools: list[str] = Field(..., min_length=1, title="Sólidos herramienta", description="ids de features")


class TransformParams(BaseModel):
    """Mueve y/o rota un sólido existente (rotación alrededor de su centro)."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    translate: Vec3 = Field(default_factory=Vec3, title="Traslación")
    rotate: Rot3 = Field(default_factory=Rot3, title="Rotación")


class PatternLinearParams(BaseModel):
    """Crea copias equiespaciadas de un sólido a lo largo de un vector."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    count: int = Field(
        3, ge=2, le=200, title="Nº total de instancias",
        description="entero 2–200; acepta =expresión (p. ej. =largo/paso)",
    )
    spacing: Vec3 = Field(..., title="Separación entre instancias")

    _count_floor = field_validator("count", mode="before")(_floor_to_int)


class PatternGroupParams(BaseModel):
    """Arraya TODAS las features creadas por un comando fuente (no solo un sólido, como
    pattern_linear), en línea y opcionalmente en rejilla 2D. SOLO geometría: si la fuente
    está referenciada por juntas/mates, el comando se rechaza (arraya solo geometría)."""

    source: str = Field(
        ..., title="Comando fuente",
        description="command_id (no feature) cuyas features se replican",
    )
    count: int = Field(
        3, ge=2, le=200, title="Nº total (eje 1)",
        description="entero 2–200; acepta =expresión",
    )
    spacing: Vec3 = Field(..., title="Separación (eje 1)")
    count2: int = Field(
        1, ge=1, le=200, title="Nº (eje 2, rejilla)",
        description="1 = sin rejilla; entero 1–200; acepta =expresión",
    )
    spacing2: Vec3 = Field(default_factory=Vec3, title="Separación (eje 2)")

    _count_floor = field_validator("count", mode="before")(_floor_to_int)
    _count2_floor = field_validator("count2", mode="before")(_floor_to_int)


class DeleteParams(BaseModel):
    """Elimina un sólido de la escena."""

    feature: str = Field(..., title="Sólido", description="id de feature")


class DuplicateParams(BaseModel):
    """Duplica un sólido existente con un desfase opcional → nuevo sólido."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    offset: Vec3 = Field(default_factory=lambda: Vec3(x=20, y=20), title="Desfase")


class CenterInParams(BaseModel):
    """Centra un sólido DENTRO de otro (por sus cajas envolventes) en los ejes elegidos.
    Colocación por intención: en vez de calcular la coordenada, dices 'céntralo en B'.
    Se reevalúa al regenerar, así que si B cambia, el sólido se recentra solo."""

    feature: str = Field(..., title="Sólido a centrar", description="id de feature")
    into: str = Field(..., title="Sólido contenedor", description="id de feature")
    axes: list[Literal["x", "y", "z"]] = Field(
        default_factory=lambda: ["x", "y"], title="Ejes a centrar"
    )


class DistributeParams(BaseModel):
    """Reparte varios sólidos uniformemente entre dos coordenadas a lo largo de un eje
    (centros equiespaciados de `start` a `end`). Colocación por intención: 'repártelos
    parejo entre aquí y allá' en vez de calcular cada posición."""

    features: list[str] = Field(..., title="Sólidos", description="ids en el orden a repartir")
    axis: Literal["x", "y", "z"] = Field("x", title="Eje")
    start: float = Field(..., title="Centro del primero (mm)", description="acepta =expresión")
    end: float = Field(..., title="Centro del último (mm)", description="acepta =expresión")


ANCHOR_NAMES = Literal["centro", "base", "tope", "min_x", "max_x", "min_y", "max_y"]


class AttachParams(BaseModel):
    """Ensambla: opcionalmente ORIENTA el sólido (gira sobre su centro para que
    su eje align_my quede según align_to) y después lo traslada para que su
    ancla coincida con el ancla del destino, con desfase opcional. Las anclas
    se calculan de la caja envolvente actual de cada sólido."""

    feature: str = Field(..., title="Sólido a mover", description="id de feature")
    anchor: ANCHOR_NAMES = Field("base", title="Ancla del sólido")
    target: str = Field(..., title="Sólido destino", description="id de feature")
    target_anchor: ANCHOR_NAMES = Field("tope", title="Ancla del destino")
    offset: Vec3 = Field(default_factory=Vec3, title="Desfase")
    align_my: Literal["x", "y", "z"] | None = Field(
        None, title="Alinear mi eje", description="eje del sólido a reorientar"
    )
    align_to: Literal["x", "y", "z"] | None = Field(
        None, title="Hacia el eje", description="eje global destino"
    )


class SnapToParams(BaseModel):
    """Coloca un sólido JUNTO a otro sin aritmética, en dos modos. (1) BBOX (default):
    traslada `feature` para que su cara enfrentada quede a `gap` mm del `lado` del bbox
    de `target` (lado='+x' pega contra el max_x; gap=0 = a ras); `alinear` la centra
    además en esos ejes. (2) CARA-A-CARA (V6.8-E, pasa `cara` + `cara_target`): APOYA la
    cara PLANA de la pieza contra la cara PLANA del target — rota la pieza lo MÍNIMO para
    dejar las normales anti-paralelas (la orientación se conserva todo lo posible: un
    listón sobre un larguero inclinado se inclina con él, sin girar alrededor de la
    normal) y alinea los centros de cara a `gap` mm + `deslizar` {u,v} en el plano del
    target (u = eje MAYOR de la cara). `lado`/`alinear` se ignoran en este modo. Ambos
    modos se REEVALÚAN al regenerar (relacional persistente): si el target se mueve o
    cambia, la pieza lo sigue. Para caras cilíndricas usa mates (add_mate concéntrico)."""

    feature: str = Field(..., title="Sólido a colocar", description="id de feature")
    target: str = Field(..., title="Sólido de referencia", description="id de feature")
    lado: Literal["+x", "-x", "+y", "-y", "+z", "-z"] = Field(
        "+x", title="Lado", description="lado del target contra el que se pega la pieza",
    )
    gap: float = Field(
        0.0, ge=0, title="Holgura", description="mm entre las piezas; acepta =expresión",
    )
    alinear: list[Literal["x", "y", "z"]] = Field(
        default_factory=list, title="Centrar en ejes",
        description="ejes en que centrar la pieza dentro del target (además del snap)",
    )
    cara: "EdgeSelector | None" = Field(
        None, title="Cara de la pieza", json_schema_extra={"x-selector": "face"},
        description="modo cara-a-cara: cara PLANA de la pieza que APOYA (con cara_target)",
    )
    cara_target: "EdgeSelector | None" = Field(
        None, title="Cara del target", json_schema_extra={"x-selector": "face"},
        description="cara PLANA del target contra la que se apoya",
    )
    deslizar: "SlideUV" = Field(
        default_factory=lambda: SlideUV(), title="Deslizar en el plano",
        description="desplazamiento {u,v} mm en el plano de la cara target "
        "(u = eje MAYOR de la cara, v = el menor); solo modo cara-a-cara",
    )

    @model_validator(mode="after")
    def _face_mode_pair(self):
        if (self.cara is None) != (self.cara_target is None):
            raise ValueError(
                "El modo cara-a-cara necesita `cara` Y `cara_target` (o ninguno = modo bbox)"
            )
        return self


class SetVariableParams(BaseModel):
    """Define o actualiza una variable de proyecto. Cualquier parámetro numérico
    de otro comando puede usarla escribiendo '=NOMBRE' o una fórmula como
    '=L/2 - 40'. Cambiar la variable regenera todo el modelo."""

    name: str = Field(
        ...,
        pattern=r"^[A-Za-z_][A-Za-z0-9_]*$",
        max_length=40,
        title="Nombre",
        description="identificador, p. ej. L, ancho, paso_rodillo",
    )
    expression: str = Field(
        ...,
        min_length=1,
        max_length=200,
        title="Expresión",
        description="número o fórmula que puede usar otras variables, p. ej. 2*ancho + 40",
    )
