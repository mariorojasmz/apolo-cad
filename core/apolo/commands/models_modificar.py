"""Params de lo que modifica un sólido: fillet, chaflán, shell, modelado directo de
caras, taladro, patrón circular, espejo y ebanistería.

Sale de `models.py` (fachada) por tamaño.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .models_base import Vec3, _floor_to_int
from .models_selectores import EdgeSelector, SlideUV


class FilletParams(BaseModel):
    """Redondea aristas de un sólido con el radio dado."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    edges: EdgeSelector = Field(
        default_factory=EdgeSelector, title="Aristas",
        json_schema_extra={"x-selector": "edge"},
    )
    radius: float = Field(3, gt=0, le=1000, title="Radio", description="mm")


class DeleteFacesParams(BaseModel):
    """Borra CARAS de un sólido y CURA el hueco extendiendo las vecinas (modelado
    directo, V5.3): quitar fillets, barrenos o bosses de un STEP de fabricante — o
    de cualquier sólido. Un barreno suele ser cilindro + cono de avellanado y un
    fillet una CADENA de caras: usa mode=cerca con count>1 (mira get_topology para
    verlas) o tangentes=true para expandir la selección a la cadena tangente.
    Para MOVER un barreno: delete_faces del barreno viejo + drill_hole nuevo (queda
    paramétrico). Si las vecinas no pueden cerrar el hueco, el comando falla con
    un error claro (no rompe el sólido)."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    faces: EdgeSelector = Field(
        ..., title="Caras", json_schema_extra={"x-selector": "face"}
    )
    tangentes: bool = Field(
        False, title="Expandir cadena de fillet",
        description="expande a las caras CURVAS vecinas tangentes o de MISMO radio (el anillo "
                    "completo del fillet); las planas no se agregan (chaflanes: cerca+count)",
    )


class PushFaceParams(BaseModel):
    """Empuja o jala UNA cara PLANA extruyendo su contorno (modelado directo, V5.3):
    distance>0 añade material (JALAR), <0 quita (EMPUJAR). Casos: alargar/acortar
    un eje importado, engrosar una brida, rebajar una base. Semántica honesta: las
    paredes nuevas salen RECTAS (no extiende caras inclinadas vecinas). Para caras
    cilíndricas (barrenos) usa delete_faces + drill_hole."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    face: EdgeSelector = Field(
        ..., title="Cara", json_schema_extra={"x-selector": "face"},
        description="debe resolver a UNA cara plana (cerca con count=1, o cara del bbox)",
    )
    distance: float = Field(
        ..., ge=-10000, le=10000, title="Distancia",
        description="mm; >0 jala (añade material), <0 empuja (quita); acepta =expresión",
    )


class ChamferParams(BaseModel):
    """Achaflana aristas de un sólido con la distancia dada."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    edges: EdgeSelector = Field(
        default_factory=EdgeSelector, title="Aristas",
        json_schema_extra={"x-selector": "edge"},
    )
    distance: float = Field(2, gt=0, le=1000, title="Distancia", description="mm")


class ShellParams(BaseModel):
    """Vacía el sólido dejando paredes del espesor dado; las caras de apertura
    quedan abiertas."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    openings: EdgeSelector = Field(
        default_factory=lambda: EdgeSelector(mode="cara", face="tope"),
        title="Caras de apertura",
        json_schema_extra={"x-selector": "face"},
    )
    thickness: float = Field(3, gt=0, le=500, title="Espesor", description="mm")


DRILL_AXES = Literal["x", "-x", "y", "-y", "z", "-z"]


class DrillHoleParams(BaseModel):
    """Taladro: avanza desde el punto de entrada en la dirección del eje.
    depth=0 lo hace pasante. Caladrillo (counterbore) opcional. Con `thread`
    (rosca M8, M10x1.25…) el 3D taladra a la BROCA DE MACHUELADO.
    Entrada DECLARATIVA (V6.8-E): en vez de `position`, pasa `cara` (selector de
    cara PLANA) + `en_cara` {u,v} (mm desde el CENTRO de la cara; u = eje mayor) —
    el taladro entra por ese punto y avanza por −normal (perpendicular a la cara,
    aunque esté rotada) SIN trigonometría; un `axis` explícito gana sobre la normal.
    `position` y `cara` son excluyentes; `en_cara` fuera de la cara → error."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    position: Vec3 | None = Field(None, title="Punto de entrada")
    axis: DRILL_AXES = Field("-z", title="Dirección de avance")
    cara: EdgeSelector | None = Field(
        None, title="Cara de entrada", json_schema_extra={"x-selector": "face"},
        description="cara PLANA por la que entra el taladro (alternativa a position)",
    )
    en_cara: SlideUV = Field(
        default_factory=SlideUV, title="Punto en la cara",
        description="{u,v} mm desde el CENTRO de la cara (u = eje mayor); solo con `cara`",
    )
    diameter: float = Field(8, gt=0, le=500, title="Diámetro", description="mm")
    depth: float = Field(0, ge=0, le=5000, title="Profundidad", description="mm, 0 = pasante")
    counterbore_d: float | None = Field(None, gt=0, le=600, title="Ø caladrillo", description="mm")
    counterbore_depth: float | None = Field(None, gt=0, le=500, title="Prof. caladrillo", description="mm")
    fit: str = Field(
        "", max_length=6, title="Ajuste ISO 286",
        description="clase de AGUJERO (H7, G7, JS7, K7…) — anotación para el plano y "
                    "la verificación de asientos; la geometría queda al nominal",
    )
    thread: str = Field(
        "", max_length=12, title="Rosca (machuelo)",
        description="métrica ISO ('M8', 'M10x1.25'): el 3D taladra a la BROCA de "
                    "machuelado publicada (M8→Ø6.8) e IGNORA `diameter`; el plano "
                    "rotula 'M8 - 6H (broca Ø6.8)' + cosmético ISO 6410 en capa "
                    "ROSCA. Incompatible con `fit` (la rosca interior es 6H)",
    )

    @field_validator("fit")
    @classmethod
    def _fit_is_hole_class(cls, v: str) -> str:
        if not v:
            return ""
        from apolo.library.engineering.fits import parse_fit

        try:
            _, letter, grade = parse_fit(v)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc
        if not letter[0].isupper():
            raise ValueError(f"'{v}' es clase de EJE; un taladro lleva clase de AGUJERO (p. ej. H7)")
        return f"{letter}{grade}"

    @field_validator("thread")
    @classmethod
    def _thread_known(cls, v: str) -> str:
        if not v:
            return ""
        from apolo.library.engineering.threads import thread_designation

        try:
            return thread_designation(v)
        except KeyError as exc:
            raise ValueError(str(exc).strip("'\"")) from exc

    @model_validator(mode="after")
    def _fit_xor_thread(self):
        if self.fit and self.thread:
            raise ValueError(
                "fit y thread son excluyentes: la rosca interior va 6H (ISO 262); "
                "el ajuste ISO 286 es para agujeros LISOS"
            )
        return self

    @model_validator(mode="after")
    def _position_xor_cara(self):
        if (self.position is None) == (self.cara is None):
            raise ValueError(
                "Pasa exactamente uno: `position` (punto de entrada en mundo) o "
                "`cara` + `en_cara` (entrada declarativa por cara, V6.8-E)"
            )
        return self


class PatternCircularParams(BaseModel):
    """Copias equiespaciadas alrededor de un eje."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    count: int = Field(
        6, ge=2, le=200, title="Nº total de instancias",
        description="entero 2–200; acepta =expresión (p. ej. =360/paso_ang)",
    )
    axis_point: Vec3 = Field(default_factory=Vec3, title="Punto del eje")
    axis_dir: Literal["x", "y", "z"] = Field("z", title="Eje")
    total_angle: float = Field(360, gt=0, le=360, title="Ángulo total", description="grados")

    _count_floor = field_validator("count", mode="before")(_floor_to_int)


class MirrorParams(BaseModel):
    """Crea la copia espejada de un sólido respecto a un plano global."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    plane: Literal["xy", "xz", "yz"] = Field("yz", title="Plano")
    offset: float = Field(0, title="Desfase del plano", description="mm")


JOINERY_TYPES = Literal["espiga_mortaja", "dado", "dowel", "rebaje"]


class AddJoineryParams(BaseModel):
    """Unión de ebanistería entre dos piezas de madera (corta la geometría de encaje
    por booleana, en sitio — conserva ids/juntas). `position` = centro de la junta
    (coords mundo), `axis` = dirección de inserción (±X/Y/Z; A se mete en B por ahí).
    - espiga_mortaja: ESPIGA que sale de A (tenón width×height×depth) + MORTAJA (caja con
      holgura) en B. Encajan.
    - dado: canal/ranura en B (ancho=width, profundidad=depth, largo=height) donde entra A.
    - dowel: `count` espigas/clavijas Ø=width repartidas (paso `spacing`): taladros pasantes
      en A y B + las clavijas insertadas.
    - rebaje: corta una caja width(X)×height(Y)×depth(Z) en B centrada en `position`, EN SITIO
      (conserva el id). Para galces de vidrio: posiciona la caja en el canto para dejar un escalón
      (rebaje) en lugar de un canal. `feature_a` es solo contexto (p. ej. el vidrio); no se usa."""

    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=40, title="Nombre")
    type: JOINERY_TYPES = Field("espiga_mortaja", title="Tipo de unión")
    feature_a: str = Field(..., title="Pieza A (espiga/entra)", description="id de feature")
    feature_b: str = Field(..., title="Pieza B (mortaja/recibe)", description="id de feature")
    position: Vec3 = Field(default_factory=Vec3, title="Centro de la junta", description="coords mundo")
    axis: Vec3 = Field(default_factory=lambda: Vec3(y=1), title="Eje de inserción", description="±X/Y/Z")
    width: float = Field(20, gt=0, le=2000, title="Ancho", description="mm (espiga/ranura/Ø clavija)")
    height: float = Field(30, gt=0, le=2000, title="Alto / largo", description="mm (alto de espiga o largo de ranura)")
    depth: float = Field(25, gt=0, le=2000, title="Profundidad", description="mm (largo de espiga/mortaja/taladro)")
    count: int = Field(2, ge=1, le=50, title="Nº de clavijas")
    spacing: float = Field(32, gt=0, le=2000, title="Paso de clavijas", description="mm")
    clearance: float = Field(0.2, ge=0, le=5, title="Holgura", description="mm")
