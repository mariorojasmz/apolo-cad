"""Params del ensamblaje: juntas, mates, riel y restricciones, grupos,
transform_group, insert_project y anclaje a tierra.

Sale de `models.py` (fachada) por tamaño.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .models_base import Rot3, Vec3
from .models_selectores import EdgeSelector


JOINT_TYPES = Literal["fija", "giratoria", "continua", "prismatica"]


class AddJointParams(BaseModel):
    """Define una junta cinemática entre dos sólidos (padre → hijo). El FK mueve
    SOLO al hijo y a los hijos de juntas colgadas de él — NO a "todo lo unido":
    un cuerpo rígido multi-pieza se completa con juntas 'fija', o con
    `arrastrar=true`, que las materializa por ti: las piezas unidas al hijo por
    FIJADORES declarados (fasten: perno/soldadura/pegado/contacto) y no
    alcanzables desde el padre reciben juntas fija `jf_<junta>_<fid>`; una pieza
    en disputa (alcanzable por ambos lados) NO se arrastra y queda en
    `frontera` (visible en get_kinematics — tú decides). Declara las uniones
    ANTES que la junta (el flood ve el log hasta este punto). SIGNO de
    giratoria/continua: valor + = rotación HORARIA mirando desde el extremo
    positivo del eje (convención Rotation de build123d) — calíbralo contra
    get_kinematics, no contra un render. Prismática desliza en mm a lo largo
    del eje. Cada sólido solo puede ser hijo de UNA junta (árbol)."""

    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=40, title="Nombre")
    type: JOINT_TYPES = Field("giratoria", title="Tipo")
    parent: str = Field(..., title="Sólido padre", description="id de feature")
    child: str = Field(..., title="Sólido hijo", description="id de feature")
    origin: Vec3 = Field(default_factory=Vec3, title="Origen", description="punto del eje, coords. mundo")
    axis: Vec3 = Field(default_factory=lambda: Vec3(z=1), title="Eje", description="dirección")
    lower: float = Field(-180, title="Límite inferior", description="grados o mm")
    upper: float = Field(180, title="Límite superior", description="grados o mm")
    arrastrar: bool = Field(
        False, title="Arrastrar cuerpo rígido",
        description="materializa juntas fija jf_* hacia lo unido al hijo por fijadores "
        "(no alcanzable desde el padre); False = comportamiento clásico",
    )


MATE_TYPES = Literal["coincidente", "distancia", "concentrico", "paralelo", "angulo"]


class AddMateParams(BaseModel):
    """Relación de ensamblaje PERSISTENTE entre dos sólidos por sus CARAS. A es
    la base; B se recoloca para cumplir el mate y SIGUE a A si A cambia (a
    diferencia de attach, que es one-shot). Elige cada cara con el selector
    (clic '📍 Elegir en viewport').
    - coincidente: caras a ras (normales opuestas).
    - distancia: caras enfrentadas separadas `value` mm.
    - concentrico: ejes de caras cilíndricas alineados (p. ej. tornillo en agujero).
    - paralelo: normal de B paralela a la de A (orienta; no mueve la posición). `value` se ignora.
    - angulo: normal de B a `value` GRADOS de la de A (orientación; no mueve la posición)."""

    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=40, title="Nombre")
    type: MATE_TYPES = Field("coincidente", title="Tipo")
    feature_a: str = Field(..., title="Sólido base (A)", description="id de feature")
    feature_b: str = Field(..., title="Sólido que se mueve (B)", description="id de feature")
    ref_a: EdgeSelector = Field(
        default_factory=lambda: EdgeSelector(mode="cara", face="tope"),
        title="Cara de A", json_schema_extra={"x-selector": "face"},
    )
    ref_b: EdgeSelector = Field(
        default_factory=lambda: EdgeSelector(mode="cara", face="base"),
        title="Cara de B", json_schema_extra={"x-selector": "face"},
    )
    value: float = Field(0, title="Distancia/holgura", description="mm")
    flip: bool = Field(False, title="Invertir lado")


class AddRailConstraintParams(BaseModel):
    """Restricción cinemática de LAZO CERRADO. Obliga a que un punto ancla
    (rígidamente unido al hijo de `joint`) permanezca SOBRE una recta (riel).
    El valor de `joint` deja de ser libre: se RESUELVE en cada pose (búsqueda
    1D) para cumplir la restricción, de modo que la OTRA junta de la cadena la
    maneja como driver. Modela un carro que desliza por un riel (p. ej. el
    borde de ataque de una puerta plegable top-hung). El árbol cinemático no
    cambia; solo se acopla un grado de libertad."""

    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=40, title="Nombre")
    joint: str = Field(
        ..., max_length=40, title="Junta dependiente",
        description="nombre de la junta cuyo valor se resuelve para cumplir el riel",
    )
    anchor: Vec3 = Field(
        default_factory=Vec3, title="Punto ancla",
        description="punto del hijo (coords mundo, pose de diseño) que debe seguir el riel",
    )
    point: Vec3 = Field(
        default_factory=Vec3, title="Punto del riel", description="un punto cualquiera de la recta",
    )
    axis: Vec3 = Field(
        default_factory=lambda: Vec3(x=1), title="Dirección del riel", description="dirección de la recta",
    )


CONSTRAINT_TYPES = Literal["punto_en_recta", "punto_en_plano", "punto_coincidente", "distancia"]


class AddConstraintParams(BaseModel):
    """Restricción cinemática GENÉRICA (generaliza add_rail_constraint a multi-restricción /
    N-GDL). Obliga a que un punto ancla (unido al hijo de `joint`) cumpla una condición; el
    valor de `joint` deja de ser libre y se RESUELVE (junto con las demás juntas dependientes)
    en cada pose. Tipos: `punto_en_recta` (riel: sobre la recta point+axis), `punto_en_plano`
    (sobre el plano de normal `axis` por `point`), `punto_coincidente` (en `point`), `distancia`
    (a `value` mm de `point`). Varias restricciones se resuelven a la vez (lazos N-GDL)."""

    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=40, title="Nombre")
    tipo: CONSTRAINT_TYPES = Field("punto_en_recta", title="Tipo")
    joint: str = Field(
        ..., max_length=40, title="Junta dependiente",
        description="nombre de la junta cuyo valor se resuelve para cumplir la restricción",
    )
    anchor: Vec3 = Field(
        default_factory=Vec3, title="Punto ancla",
        description="punto del hijo (coords mundo, pose de diseño) que debe cumplir la condición",
    )
    point: Vec3 = Field(default_factory=Vec3, title="Punto de referencia")
    axis: Vec3 = Field(
        default_factory=lambda: Vec3(x=1), title="Dirección (recta) / normal (plano)",
    )
    value: float = Field(0.0, title="Distancia (mm)", description="solo tipo 'distancia'; acepta =expr")


class CreateGroupParams(BaseModel):
    """Declara un GRUPO / sub-ensamblaje con nombre: un conjunto de COMANDOS cuyas
    piezas (presentes y futuras) se operan/muestran como unidad. La membresía es por
    command_id (la unidad estable del log): editar un count o añadir instancias del
    comando NO rompe el grupo. Anidable vía `parent` (el padre debe declararse antes).
    Un comando vive en UN solo grupo. `role` opcional clasifica el subsistema
    (estructura/transmision/rodillos/banda/guardas/tornilleria/electrico/otro u otro
    texto corto) para consultas de ingeniería."""

    # sin comas (el nombre se usa como token en los CSV de isolate/highlight)
    name: str = Field(..., pattern=r"^[^\s,][^,]*$", max_length=40, title="Nombre")
    members: list[str] = Field(
        ..., min_length=1, max_length=500, title="Comandos miembro",
        description="command_ids cuyas piezas forman el grupo (p. ej. ['c412', 'c455'])",
    )
    parent: str | None = Field(None, title="Grupo padre", description="anidación; el padre va antes en el log")
    role: str | None = Field(
        None, max_length=24, title="Rol del subsistema",
        description="sugeridos: estructura, transmision, rodillos, banda, guardas, tornilleria, electrico, otro",
    )


class TransformGroupParams(BaseModel):
    """Mueve/rota un GRUPO entero como cuerpo rígido (incluye sub-grupos): todas sus
    piezas se trasladan y giran sobre el centro del bbox CONJUNTO. Las juntas y
    restricciones INTERNAS (ambos extremos dentro del grupo) viajan con él; si una
    junta/mate/restricción CRUZA la frontera del grupo, el comando se rechaza (mueve
    primero la pieza suelta o incluye al otro extremo en el grupo). Acepta `=expr`."""

    group: str = Field(..., max_length=40, title="Grupo")
    translate: Vec3 = Field(default_factory=Vec3, title="Traslación", description="mm; acepta =expr")
    rotate: Vec3 = Field(default_factory=Vec3, title="Rotación", description="grados sobre el centro del grupo; acepta =expr")


class InsertProjectParams(BaseModel):
    """Instancia un PROYECTO guardado COMPLETO como sub-ensamblaje (layouts
    multi-máquina, V5.2b). Da `project_id` (descúbrelo con list_projects): la API
    embebe su SNAPSHOT .apolo como attachment, así el layout queda AUTOCONTENIDO y
    los cambios posteriores en el proyecto origen NO se propagan solos. Refresh
    explícito: edita este comando con {"attachment": ""} (merge) para re-embeber la
    versión actual del origen. Editar el INTERIOR de la instancia se hace ABRIENDO
    el proyecto origen, no aquí (aquí solo overrides/posición/rotación). Crea un
    grupo raíz `name` (y los grupos internos del origen como '{name}/{grupo}'):
    isolate/transform_group/BOM/manual lo tratan como sub-ensamblaje. `overrides`
    pisa variables del origen — parametricidad por instancia (dos fajas de largos
    distintos). Las juntas/restricciones/fijadores/anclajes internos viajan; los
    mates del origen llegan ya resueltos (baked)."""

    project_id: int | None = Field(
        None, ge=1, title="Proyecto",
        description="id del proyecto guardado (list_projects); la API lo materializa a attachment",
    )
    attachment: str = Field(
        "", title="Snapshot",
        description="hash del .apolo embebido (lo rellena la API; vacío = (re)materializar desde project_id)",
    )
    # sin comas (token en los CSV de isolate/highlight) ni '/' (separador de los
    # nombres de grupo internos '{name}/{grupo}')
    name: str = Field(
        ..., pattern=r"^[^\s,/][^,/]*$", max_length=30, title="Nombre",
        description="nombre de la instancia = grupo raíz (único en el documento)",
    )
    overrides: dict[str, float] = Field(
        default_factory=dict, title="Overrides",
        description='pisa variables del origen: {"largo": 3000} o {"largo": "=L_faja2"} (=expr usa variables de ESTE proyecto)',
    )
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")
    keep_grounds: bool = Field(
        True, title="Conservar anclajes",
        description="importa los anclajes a tierra del origen (máquina apoyada en piso sigue apoyada); desactívalo al elevarla",
    )

    @model_validator(mode="after")
    def _source_required(self) -> "InsertProjectParams":
        if self.project_id is None and not self.attachment:
            raise ValueError("indica project_id (o un attachment ya materializado)")
        return self


class GroundParams(BaseModel):
    """Ancla un sólido a TIERRA (fijo al piso/cimiento). En la validación de ensamblaje las
    piezas ancladas son el origen del 'camino de sujeción': una pieza está bien sujeta si
    se conecta (por juntas/mates/fijadores) hasta alguna pieza anclada."""

    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=40, title="Nombre")
    feature: str = Field(..., title="Sólido anclado", description="id de feature")
    nota: str = Field("", max_length=120, title="Nota")
