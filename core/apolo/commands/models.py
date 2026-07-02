"""Schemas pydantic de los parámetros de cada comando.

Estos modelos son la única fuente de verdad: de su JSON Schema se generan
los formularios de la UI y las tools del agente IA.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _floor_to_int(v: Any) -> Any:
    """Trunca a entero (floor) un número ya resuelto, dejando pasar lo demás.

    Permite que un campo entero acepte '=expresión': resolve_params convierte la
    expresión a float ANTES de validar, y este before-validator lo lleva a int
    (p. ej. '=largo/paso' = 13.33 → 13). Un int literal pasa intacto."""
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return math.floor(v)
    return v


class Vec3(BaseModel):
    x: float = Field(0, description="mm")
    y: float = Field(0, description="mm")
    z: float = Field(0, description="mm")

    def tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


class Rot3(BaseModel):
    x: float = Field(0, ge=-360, le=360, description="grados")
    y: float = Field(0, ge=-360, le=360, description="grados")
    z: float = Field(0, ge=-360, le=360, description="grados")

    def tuple(self) -> tuple[float, float, float]:
        return (self.x, self.y, self.z)


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


class InsertComponentParams(BaseModel):
    """Inserta un componente del catálogo (biblioteca). Los componentes
    cortables (perfiles, rodillos, patas, guardas) aceptan length a medida."""

    component: str = Field(
        ...,
        title="Componente",
        description="referencia del catálogo",
        json_schema_extra=lambda schema: schema.update(
            {"enum": _catalog_refs()}
        ),
    )
    name: str = Field("", title="Nombre", description="vacío = nombre del catálogo")
    length: float | None = Field(
        None, gt=0, le=12000, title="Longitud", description="mm, solo componentes cortables; vacío = estándar"
    )
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @field_validator("component")
    @classmethod
    def _known_ref(cls, v: str) -> str:
        if v not in _catalog_refs():
            raise ValueError(f"componente desconocido '{v}'")
        return v


def _catalog_refs() -> list[str]:
    from apolo.library.catalog import CATALOG

    return list(CATALOG.keys())


def _roller_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("rodillos")


def _profile_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("perfiles")


def _motor_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("motorreductores")


def _drum_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("tambores")


def _tube_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("tubos_estructurales")


def _takeup_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("tensores_trotadora")


def _bearing_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("rodamientos")


def _perno_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("pernos")


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


class CreateConveyorParams(BaseModel):
    """Transportador de rodillos completo y paramétrico: largueros 40x80,
    rodillos del catálogo, 4 patas regulables, arriostrado y motor opcional.
    Editar cualquier parámetro regenera el transportador entero."""

    name: str = Field("Transportador", title="Nombre")
    largo: float = Field(2000, gt=0, le=20000, title="Largo", description="mm")
    ancho: float = Field(600, gt=0, le=3000, title="Ancho total", description="mm")
    altura: float = Field(750, gt=0, le=2500, title="Altura de trabajo", description="mm, cara superior de rodillos")
    paso: float = Field(100, gt=0, le=1000, title="Paso de rodillos", description="mm entre ejes")
    rodillo: str = Field(
        "RODILLO-50", title="Rodillo",
        json_schema_extra=lambda schema: schema.update({"enum": _roller_refs()}),
    )
    motor: str = Field(
        "ninguno", title="Motorreductor",
        json_schema_extra=lambda schema: schema.update({"enum": ["ninguno"] + _motor_refs()}),
    )
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @field_validator("rodillo")
    @classmethod
    def _known_roller(cls, v: str) -> str:
        if v not in _roller_refs():
            raise ValueError(f"rodillo desconocido '{v}'")
        return v

    @field_validator("motor")
    @classmethod
    def _known_motor(cls, v: str) -> str:
        if v != "ninguno" and v not in _motor_refs():
            raise ValueError(f"motor desconocido '{v}'")
        return v


class CreateBeltConveyorParams(BaseModel):
    """Faja de banda plana paramétrica con cama de deslizamiento y 2 tambores de
    extremo: bastidor de tubo estructural, banda envolvente, tambor motriz engomado +
    tambor de cola con tensor tipo TROTADORA (sin chumacera), motorreductor de eje
    hueco y guardas opcionales. Editar cualquier parámetro regenera la faja entera."""

    name: str = Field("Faja de banda", title="Nombre")
    largo: float = Field(4000, gt=0, le=30000, title="Largo entre tambores", description="mm")
    ancho_banda: float = Field(600, gt=0, le=3000, title="Ancho de banda", description="mm")
    altura: float = Field(900, gt=0, le=2500, title="Altura de trabajo", description="mm, cara superior de la banda")
    espesor_banda: float = Field(4, gt=0, le=30, title="Espesor de banda", description="mm")
    tambor_motriz: str = Field(
        "TAMBOR-102", title="Tambor motriz",
        json_schema_extra=lambda schema: schema.update({"enum": _drum_refs()}),
    )
    tambor_cola: str = Field(
        "TAMBOR-102-COLA", title="Tambor de cola",
        json_schema_extra=lambda schema: schema.update({"enum": _drum_refs()}),
    )
    tubo: str = Field(
        "TUBO-4X2", title="Tubo del bastidor",
        json_schema_extra=lambda schema: schema.update({"enum": _tube_refs()}),
    )
    tensor: str = Field(
        "TENSOR-TROT-25", title="Tensor (trotadora)",
        json_schema_extra=lambda schema: schema.update({"enum": ["ninguno"] + _takeup_refs()}),
    )
    motor: str = Field(
        "MOTOR-150-EH", title="Motorreductor",
        json_schema_extra=lambda schema: schema.update({"enum": ["ninguno"] + _motor_refs()}),
    )
    guardas: bool = Field(True, title="Guardas laterales")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @field_validator("tambor_motriz", "tambor_cola")
    @classmethod
    def _known_drum(cls, v: str) -> str:
        if v not in _drum_refs():
            raise ValueError(f"tambor desconocido '{v}'")
        return v

    @field_validator("tubo")
    @classmethod
    def _known_tube(cls, v: str) -> str:
        if v not in _tube_refs():
            raise ValueError(f"tubo desconocido '{v}'")
        return v

    @field_validator("tensor")
    @classmethod
    def _known_tensor(cls, v: str) -> str:
        if v != "ninguno" and v not in _takeup_refs():
            raise ValueError(f"tensor desconocido '{v}'")
        return v

    @field_validator("motor")
    @classmethod
    def _known_motor_eh(cls, v: str) -> str:
        if v != "ninguno" and v not in _motor_refs():
            raise ValueError(f"motor desconocido '{v}'")
        return v


class CreateTakeUpParams(BaseModel):
    """Rodillo de cola TENSABLE tipo trotadora (eje fijo), paramétrico. Rodillo tubular (engomado
    opcional) sobre 2 rodamientos con seeger; eje FIJO que sobresale a cada lado; por lado un
    TENSOR: un soporte en «C» (alma soldada al larguero + 2 aletas) y un perno horizontal que pasa
    por las 2 aletas y por el eje (que tiene HILO ahí = hace de tuerca). Sin chumacera.

    PARA QUÉ SIRVE: rodillo de cola (no motriz) de una faja de banda, con tensado integrado.

    CÓMO MONTAR (orientación, IMPORTANTE):
    - Insertar con `position` = (X del extremo de cola, 0, altura del eje del tambor). El eje queda
      a lo largo de Y (cruzado a la banda); NO rotar el conjunto.
    - `ancho_banda` = CARA del rodillo (≈ ancho de banda + holgura); el rodillo queda centrado en Y.
    - `rodamiento` fija el Ø del eje (6206→Ø30, 6207→Ø35).
    - El perno es HORIZONTAL (a lo largo de la banda), cabeza al exterior; al girarlo JALA el eje y
      tensa. `dir_tensor` = -1: cabeza hacia -X (cola); +1: hacia +X (cabeza).
    - El alma del soporte en «C» va SOLDADA al larguero (al interior del bastidor).
    Editar cualquier parámetro regenera el conjunto entero."""

    name: str = Field("Tensor de cola", title="Nombre")
    diam_rodillo: float = Field(101.6, gt=0, le=1000, title="Ø del rodillo", description="mm")
    ancho_banda: float = Field(700, gt=0, le=3000, title="Ancho de banda (cara del rodillo)", description="mm")
    rodamiento: str = Field(
        "6207", title="Rodamiento (fija el Ø del eje)",
        json_schema_extra=lambda schema: schema.update({"enum": _bearing_refs()}),
    )
    perno: str = Field(
        "PERNO-M16", title="Perno tensor (comercial)",
        json_schema_extra=lambda schema: schema.update({"enum": _perno_refs()}),
    )
    espesor_soporte: float = Field(9.5, gt=0, le=40, title="Espesor del soporte en C", description='mm (3/8"=9.5, 1/2"=12.7)')
    voladizo: float = Field(50, gt=0, le=400, title="Voladizo del eje", description="mm que el eje sobresale del rodillo (ahí va el soporte, dentro del bastidor; mín ~45)")
    dir_tensor: float = Field(-1, title="Dirección del tensor (X)", description="-1 hacia -X (cola), +1 hacia +X (cabeza): hacia qué extremo apunta la cabeza del perno")
    engomado: bool = Field(False, title="Engomado (lagging)", description="rodillo de cola normalmente bare; engomar es del tambor motriz")
    holgura_eje: float = Field(20, ge=0, le=100, title="Holgura del eje (en desuso)", description="EN DESUSO: el recorrido lo da el claro entre aletas")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @field_validator("rodamiento")
    @classmethod
    def _known_bearing(cls, v: str) -> str:
        if v not in _bearing_refs():
            raise ValueError(f"rodamiento desconocido '{v}'")
        return v

    @field_validator("perno")
    @classmethod
    def _known_perno(cls, v: str) -> str:
        if v not in _perno_refs():
            raise ValueError(f"perno desconocido '{v}'")
        return v


class CreateDriveRollerParams(BaseModel):
    """Rodillo MOTRIZ tipo trotadora (eje fijo), paramétrico. Rodillo tubular sobre 2 rodamientos
    con seeger; en el lado -Y un TENSOR (soporte en «C» de una pieza + perno horizontal que pasa por
    las 2 aletas y por el eje roscado) y en el lado +Y un EJE LARGO para acoplar el motorreductor.
    Comparte geometría con `create_take_up`.

    PARA QUÉ SIRVE: tambor motriz de una faja de banda accionado por motorreductor de eje hueco.

    CÓMO MONTAR (orientación, IMPORTANTE):
    - Insertar con `position` = (X del extremo de cabeza, 0, altura del eje del tambor). Eje a lo
      largo de Y; NO rotar el conjunto.
    - El EJE LARGO sale por +Y: alinéalo con el eje hueco del reductor (mismo X, misma Z). Ajusta
      `largo_eje_motor` para que cruce el reductor.
    - El perno del take-up (lado -Y) es horizontal, cabeza al exterior; `dir_tensor` = +1 (hacia +X).
    - El alma del soporte en «C» va soldada al larguero. `rodamiento` fija el Ø del eje (6206→Ø30, 6207→Ø35).
    Editar cualquier parámetro regenera el conjunto entero."""

    name: str = Field("Rodillo motriz", title="Nombre")
    diam_rodillo: float = Field(101.6, gt=0, le=1000, title="Ø del rodillo", description="mm")
    ancho_banda: float = Field(700, gt=0, le=3000, title="Ancho de banda (cara del rodillo)", description="mm")
    rodamiento: str = Field(
        "6207", title="Rodamiento (fija el Ø del eje)",
        json_schema_extra=lambda schema: schema.update({"enum": _bearing_refs()}),
    )
    perno: str = Field(
        "PERNO-M16", title="Perno tensor (comercial)",
        json_schema_extra=lambda schema: schema.update({"enum": _perno_refs()}),
    )
    espesor_soporte: float = Field(9.5, gt=0, le=40, title="Espesor del soporte en C", description='mm (3/8"=9.5)')
    voladizo: float = Field(50, gt=0, le=400, title="Voladizo del eje (lado take-up)", description="mm que el eje sobresale del rodillo (ahí va el soporte, dentro del bastidor; mín ~45)")
    largo_eje_motor: float = Field(250, gt=0, le=2000, title="Largo del eje al motor", description="mm que sobresale para el motorreductor")
    dir_tensor: float = Field(1, title="Dirección del tensor (X)", description="+1 hacia +X (cabeza), -1 hacia -X (cola): hacia qué extremo apunta la cabeza del perno")
    engomado: bool = Field(False, title="Engomado (lagging)", description="acero desnudo por defecto")
    holgura_eje: float = Field(20, ge=0, le=100, title="Holgura del eje (en desuso)", description="EN DESUSO: el recorrido lo da el claro entre aletas")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @field_validator("rodamiento")
    @classmethod
    def _known_bearing(cls, v: str) -> str:
        if v not in _bearing_refs():
            raise ValueError(f"rodamiento desconocido '{v}'")
        return v

    @field_validator("perno")
    @classmethod
    def _known_perno(cls, v: str) -> str:
        if v not in _perno_refs():
            raise ValueError(f"perno desconocido '{v}'")
        return v


class CreateWeldmentParams(BaseModel):
    """Bastidor soldado paramétrico: 4 postes + perímetros superior/inferior (y
    anillos intermedios opcionales) del perfil elegido, recortados a tope. Genera
    la lista de corte (BOM) y cordones de soldadura opcionales. Editar cualquier
    parámetro regenera el bastidor entero."""

    name: str = Field("Bastidor", title="Nombre")
    ancho: float = Field(800, gt=0, le=10000, title="Ancho (X)", description="mm")
    fondo: float = Field(600, gt=0, le=10000, title="Fondo (Y)", description="mm")
    alto: float = Field(900, gt=0, le=10000, title="Alto (Z)", description="mm")
    perfil: str = Field(
        "PERFIL-4040", title="Perfil",
        json_schema_extra=lambda schema: schema.update({"enum": _profile_refs()}),
    )
    anillos_intermedios: int = Field(0, ge=0, le=20, title="Anillos intermedios")
    cordones: bool = Field(True, title="Cordones de soldadura")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @field_validator("perfil")
    @classmethod
    def _known_profile(cls, v: str) -> str:
        if v not in _profile_refs():
            raise ValueError(f"perfil desconocido '{v}'")
        return v


class CreateFrameParams(BaseModel):
    """Bastidor de esqueleto ARBITRARIO: nodos 3D + aristas (pares de índices) →
    un miembro de perfil del catálogo a lo largo de cada arista (cualquier
    dirección), recortado a tope, con lista de corte (BOM) y cordones de soldadura
    en los nodos. Para A-frames, trípodes, bastidores inclinados, cerchas."""

    name: str = Field("Esqueleto", title="Nombre")
    nodes: list[list[float]] = Field(
        ..., min_length=2, title="Nodos",
        description="lista de [x, y, z] (mm); cada componente acepta '=expresión'",
    )
    edges: list[list[int]] = Field(
        ..., min_length=1, title="Aristas",
        description="lista de [i, j] (índices de nodo, base 0)",
    )
    perfil: str = Field(
        "PERFIL-4040", title="Perfil",
        json_schema_extra=lambda schema: schema.update({"enum": _profile_refs()}),
    )
    cordones: bool = Field(True, title="Cordones de soldadura")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @field_validator("perfil")
    @classmethod
    def _known_profile(cls, v: str) -> str:
        if v not in _profile_refs():
            raise ValueError(f"perfil desconocido '{v}'")
        return v

    @field_validator("nodes")
    @classmethod
    def _nodes_shape(cls, v: list[list[float]]) -> list[list[float]]:
        if any(len(n) != 3 for n in v):
            raise ValueError("cada nodo es [x, y, z]")
        return v

    @field_validator("edges")
    @classmethod
    def _edges_shape(cls, v: list[list[int]]) -> list[list[int]]:
        if any(len(e) != 2 for e in v):
            raise ValueError("cada arista es [i, j] (índices de nodo)")
        return v


SheetSide = Literal["frente", "atras", "izquierda", "derecha"]


class Hole(BaseModel):
    """Taladro pasante en la base de una chapa (coords centradas en la base, mm)."""

    x: float = Field(0, title="X en la base", description="mm, 0 = centro")
    y: float = Field(0, title="Y en la base", description="mm, 0 = centro")
    d: float = Field(8, gt=0, le=500, title="Diámetro", description="mm")


class SheetMetalParams(BaseModel):
    """Pieza de chapa plegada tipo bandeja: base rectangular de `espesor` con
    pestañas (flanges) opcionales en los 4 lados (frente=+Y, atras=−Y,
    izquierda=−X, derecha=+X), cada una con altura, ángulo y radio. Generaliza el
    soporte en L (1 pestaña), el canal en U (2) y la bandeja (4). El radio interior
    alimenta el cálculo del DESPLEGADO (flat pattern) exportable a DXF/SVG para
    corte láser; los taladros salen en el 3D y en el desplegado. Editar cualquier
    parámetro regenera la chapa entera."""

    name: str = Field("Chapa", title="Nombre")
    ancho: float = Field(200, gt=0, le=10000, title="Ancho (X)", description="mm")
    fondo: float = Field(150, gt=0, le=10000, title="Fondo (Y)", description="mm")
    espesor: float = Field(2.0, gt=0, le=50, title="Espesor", description="mm")
    lados: list[SheetSide] = Field(
        default_factory=lambda: ["frente", "atras", "izquierda", "derecha"],
        title="Lados con pestaña",
    )
    altura_pestana: float = Field(40, gt=0, le=2000, title="Altura de pestaña", description="mm")
    angulo: float = Field(90, gt=0, le=170, title="Ángulo de plegado", description="grados desde la base")
    radio: float = Field(2.0, ge=0, le=200, title="Radio interior de plegado", description="mm")
    k_factor: float = Field(0.4, ge=0, le=0.5, title="Factor K", description="posición de la fibra neutra")
    holes: list[Hole] = Field(default_factory=list, title="Taladros en la base")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @field_validator("lados")
    @classmethod
    def _lados_unicos(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("lados duplicados")
        return v


class RunScriptParams(BaseModel):
    """Ejecuta un script Python de build123d en el sandbox y añade su resultado
    como sólido. El script debe asignar `result` (forma o lista de formas);
    dispone del namespace de build123d, `math` y `V` (variables del proyecto
    resueltas). Para geometría que la biblioteca y las primitivas no cubren."""

    name: str = Field("Pieza IA", title="Nombre")
    code: str = Field(..., min_length=10, max_length=20000, title="Código")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @field_validator("code")
    @classmethod
    def _syntax_ok(cls, v: str) -> str:
        try:
            compile(v, "<script_ia>", "exec")
        except SyntaxError as exc:
            raise ValueError(f"sintaxis inválida en línea {exc.lineno}: {exc.msg}") from exc
        return v


class EdgeSelector(BaseModel):
    """Selección declarativa de aristas/caras (estable ante regeneraciones):
    todas | direccion (paralelas a x/y/z) | cara (del bbox) | longitud (rango)
    | cerca (la más próxima a un punto, lo que genera el clic en el viewport)."""

    mode: Literal["todas", "direccion", "cara", "longitud", "cerca"] = Field("todas", title="Modo")
    direction: Literal["x", "y", "z"] | None = Field(None, title="Dirección")
    face: Literal["tope", "base", "min_x", "max_x", "min_y", "max_y"] | None = Field(None, title="Cara")
    min: float | None = Field(None, title="Longitud mín.", description="mm")
    max: float | None = Field(None, title="Longitud máx.", description="mm")
    point: list[float] | None = Field(None, title="Punto", description="[x,y,z] mm")
    count: int = Field(1, ge=1, le=200, title="Cuántas")


class FilletParams(BaseModel):
    """Redondea aristas de un sólido con el radio dado."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    edges: EdgeSelector = Field(
        default_factory=EdgeSelector, title="Aristas",
        json_schema_extra={"x-selector": "edge"},
    )
    radius: float = Field(3, gt=0, le=1000, title="Radio", description="mm")


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
    depth=0 lo hace pasante. Caladrillo (counterbore) opcional."""

    feature: str = Field(..., title="Sólido", description="id de feature")
    position: Vec3 = Field(..., title="Punto de entrada")
    axis: DRILL_AXES = Field("-z", title="Dirección de avance")
    diameter: float = Field(8, gt=0, le=500, title="Diámetro", description="mm")
    depth: float = Field(0, ge=0, le=5000, title="Profundidad", description="mm, 0 = pasante")
    counterbore_d: float | None = Field(None, gt=0, le=600, title="Ø caladrillo", description="mm")
    counterbore_depth: float | None = Field(None, gt=0, le=500, title="Prof. caladrillo", description="mm")


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


class CreateRevolveParams(BaseModel):
    """Sólido de revolución: el perfil (puntos [r, z] con r ≥ 0, polígono
    cerrado) gira alrededor del eje Z. Por defecto el eje del sólido es Z; usa
    `axis` para orientarlo a lo largo de X o Y sin rotarlo manualmente."""

    name: str = Field("Revolución", title="Nombre")
    profile: list[list[float]] = Field(
        ..., min_length=3, title="Perfil",
        description="puntos [r,z] en mm, r ≥ 0, sin auto-intersecciones",
    )
    angle: float = Field(360, gt=0, le=360, title="Ángulo", description="grados")
    axis: Literal["x", "y", "z"] = Field("z", title="Eje", description="eje del sólido (z por defecto)")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @field_validator("profile")
    @classmethod
    def _radios_positivos(cls, pts: list[list[float]]) -> list[list[float]]:
        for p in pts:
            if len(p) != 2:
                raise ValueError("cada punto del perfil es [r, z]")
            if p[0] < 0:
                raise ValueError("el radio r no puede ser negativo")
        return pts


class CreateExtrudePolyParams(BaseModel):
    """Polígono 2D (puntos [x, y]) extruido en Z, centrado en el origen. Por
    defecto la extrusión va a lo largo de Z; usa `axis` para extruir a lo largo
    de X o Y sin rotarlo manualmente."""

    name: str = Field("Extrusión", title="Nombre")
    points: list[list[float]] = Field(
        ..., min_length=3, title="Polígono", description="puntos [x,y] en mm, sin auto-intersecciones"
    )
    height: float = Field(50, gt=0, le=20000, title="Altura", description="mm")
    axis: Literal["x", "y", "z"] = Field("z", title="Eje", description="eje de extrusión (z por defecto)")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @field_validator("points")
    @classmethod
    def _puntos_2d(cls, pts: list[list[float]]) -> list[list[float]]:
        if any(len(p) != 2 for p in pts):
            raise ValueError("cada punto del polígono es [x, y]")
        return pts


class ImportStepParams(BaseModel):
    """Importa un archivo STEP adjunto al documento. Con split, cada sólido
    del archivo se convierte en una pieza independiente."""

    attachment: str = Field(..., title="Adjunto", description="hash del archivo subido")
    name: str = Field("Importado", title="Nombre")
    split: bool = Field(False, title="Separar sólidos")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")


SKETCH_DOC = """Formato del croquis:
points: {"p1": [x,y], ...} (posiciones APROXIMADAS: el solver las hace exactas);
entities: line {id, from, to} | circle {id, center, radius} | arc {id, center, from, to, ccw};
constraints: horizontal/vertical {entity} | length {entity, value} | distance {a, b, value}
| coincident {a, b} | parallel/perpendicular {a, b} | angle {a, b, value°}
| radius {entity, value} (círculo o arco) | point_on_line {point, entity}
| equal_length {a, b} | fix {point}
| tangent {a, b} (línea↔círculo/arco o curva↔curva) | symmetric {a, b, line}
| equal_radius {a, b} | concentric {a, b} | midpoint {point, entity}
| distance_point_line {point, entity, value}.
Las líneas/arcos deben encadenar en un lazo cerrado; los círculos son agujeros
(o el perfil, si no hay lazo). Los valores numéricos aceptan '=expresión'.
El solve (test_sketch / POST /api/sketch/solve) devuelve además dof (grados de
libertad restantes; 0 = totalmente restringido), redundantes y conflictivas
(restricciones identificadas por nombre) — úsalo para iterar hasta dof=0 sin
redundancias."""


class SketchExtrudeParams(BaseModel):
    """Croquis 2D restringido extruido en la normal de su plano. El solver de
    restricciones hace exactas las posiciones aproximadas; si las restricciones
    son incompatibles, el error indica cuáles fallan."""

    name: str = Field("Croquis extruido", title="Nombre")
    sketch: dict = Field(..., title="Croquis", description=SKETCH_DOC)
    plane: Literal["xy", "xz", "yz"] = Field("xy", title="Plano")
    height: float = Field(20, gt=0, le=20000, title="Altura", description="mm")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")


class SketchRevolveParams(BaseModel):
    """Croquis 2D restringido girado alrededor del eje Z (el croquis se
    interpreta en el plano XZ: x = radio ≥ 0, y = altura)."""

    name: str = Field("Croquis revolucionado", title="Nombre")
    sketch: dict = Field(..., title="Croquis", description=SKETCH_DOC)
    angle: float = Field(360, gt=0, le=360, title="Ángulo", description="grados")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")


class HelixSpec(BaseModel):
    """Hélice como trayectoria de barrido (resortes, roscas, espirales)."""

    radius: float = Field(..., gt=0, title="Radio", description="mm")
    pitch: float = Field(..., gt=0, title="Avance por vuelta", description="mm")
    turns: float = Field(..., gt=0, title="Vueltas")
    lefthand: bool = Field(False, title="Hélice a izquierdas")


class SketchSweepParams(BaseModel):
    """Barrido: un perfil de croquis (cerrado) recorre una trayectoria 3D. El
    perfil se orienta perpendicular al inicio del path. La trayectoria es una lista
    de puntos [x, y, z] (recta a tramos, o suave con spline); con `closed` se cierra
    en lazo (bandas), o usa `helix` para una hélice (resortes/roscas)."""

    name: str = Field("Barrido", title="Nombre")
    sketch: dict = Field(..., title="Perfil", description=SKETCH_DOC)
    path: list[list[float]] | None = Field(
        None, title="Trayectoria",
        description="puntos [x,y,z] (≥2); acepta '=expresión' por componente. Omite si usas helix.",
    )
    smooth: bool = Field(False, title="Suave (spline)")
    closed: bool = Field(False, title="Trayectoria cerrada (lazo)")
    helix: HelixSpec | None = Field(None, title="Hélice")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @model_validator(mode="after")
    def _path_or_helix(self) -> "SketchSweepParams":
        if self.helix is None and (self.path is None or len(self.path) < 2):
            raise ValueError("Indica una trayectoria de ≥2 puntos o una hélice (helix)")
        return self


class LoftSection(BaseModel):
    sketch: dict = Field(..., description=SKETCH_DOC)
    z: float = Field(..., description="altura del perfil en el plano XY (mm)")


class SketchLoftParams(BaseModel):
    """Transición (loft): el sólido pasa suavemente entre varios perfiles de
    croquis colocados a distintas alturas Z. Tolvas rectángulo→círculo,
    adaptadores. ruled=True usa caras rectas en vez de splines."""

    name: str = Field("Transición", title="Nombre")
    sections: list[LoftSection] = Field(..., min_length=2, title="Secciones")
    ruled: bool = Field(False, title="Caras rectas")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")


JOINT_TYPES = Literal["fija", "giratoria", "continua", "prismatica"]


class AddJointParams(BaseModel):
    """Define una junta cinemática entre dos sólidos (padre → hijo). El hijo y
    todo lo unido a él se mueve respecto al padre: giratoria/continua rotan
    alrededor del eje (grados), prismática desliza a lo largo del eje (mm).
    Cada sólido solo puede ser hijo de UNA junta (estructura de árbol)."""

    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=40, title="Nombre")
    type: JOINT_TYPES = Field("giratoria", title="Tipo")
    parent: str = Field(..., title="Sólido padre", description="id de feature")
    child: str = Field(..., title="Sólido hijo", description="id de feature")
    origin: Vec3 = Field(default_factory=Vec3, title="Origen", description="punto del eje, coords. mundo")
    axis: Vec3 = Field(default_factory=lambda: Vec3(z=1), title="Eje", description="dirección")
    lower: float = Field(-180, title="Límite inferior", description="grados o mm")
    upper: float = Field(180, title="Límite superior", description="grados o mm")


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


class FastenParams(BaseModel):
    """Fijador PERSISTENTE que declara que dos sólidos están unidos (perno, soldadura,
    pegado o contacto). NO mueve geometría ni corta nada: solo registra la unión para la
    validación de ensamblaje (¿cada pieza tiene sujeción hasta el piso?). Espejo de
    add_mate, pero estructural. El tipo 'contacto' lo emite la auto-detección (apoyo más
    débil); perno/soldadura/pegado los declara el usuario."""

    name: str = Field(..., pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", max_length=40, title="Nombre")
    a: str = Field(..., title="Sólido A", description="id de feature")
    b: str = Field(..., title="Sólido B", description="id de feature")
    kind: Literal["perno", "soldadura", "pegado", "contacto"] = Field("perno", title="Tipo de unión")
    size: str | None = Field(
        None, pattern=r"^M\d{1,2}$", title="Métrica del perno",
        description="solo kind='perno' (M6–M24); si falta, el chequeo la reporta como no verificable",
    )
    qty: int | None = Field(None, ge=1, le=100, title="Nº de pernos de la unión")
    throat_mm: float | None = Field(
        None, gt=0, title="Garganta del cordón (mm)",
        description="solo kind='soldadura'; garganta a = 0.707·cateto",
    )
    length_mm: float | None = Field(None, gt=0, title="Longitud total de cordón (mm)")
    nota: str = Field("", max_length=120, title="Nota")


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


class CreateRobotArmParams(BaseModel):
    """Brazo robótico articulado de 4 ejes (base giratoria, hombro, codo y
    muñeca) con sus juntas ya definidas. Muévelo desde el panel Cinemática y
    expórtalo a URDF/SDF. El alcance es la suma brazo + antebrazo."""

    name: str = Field("Robot", title="Nombre")
    alcance: float = Field(600, gt=200, le=3000, title="Alcance", description="mm")
    position: Vec3 = Field(default_factory=Vec3, title="Posición de la base")


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
