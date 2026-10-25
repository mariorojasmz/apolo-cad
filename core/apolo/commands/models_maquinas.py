"""Params de los super-comandos históricos: transportador de rodillos, bastidor
soldado, esqueleto, script del sandbox y brazo robótico.

Sale de `models.py` (fachada) por tamaño.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .models_base import Rot3, Vec3, _motor_refs, _profile_refs, _roller_refs


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


class CreateWeldmentParams(BaseModel):
    """Bastidor soldado paramétrico con lista de corte (BOM) y cordones opcionales.
    MONTAJE según `esquinas`: "tope" (histórico) = 4 postes a altura completa +
    anillos recortados a escuadra entre postes; "inglete" (V5.8) = marcos superior
    e inferior a INGLETE 45° tipo picture-frame (miembros a longitud EXTERIOR =
    ancho/fondo, se sueldan por el plano del bisector) + 4 postes A TOPE ENTRE los
    marcos (largo = alto − 2·sección) + anillos intermedios a tope (soportes
    ocultos). Editar cualquier parámetro regenera el bastidor entero."""

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
    esquinas: Literal["tope", "inglete"] = Field(
        "tope", title="Esquinas",
        description="tope = a escuadra (histórico); inglete = marcos sup/inf a 45° "
                    "con longitud exterior en la lista de corte",
    )
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
    dirección), con lista de corte (BOM) y cordones de soldadura en los nodos.
    Con `esquinas="inglete"` (V5.8): en nodos de GRADO 2 ambos miembros se cortan
    al plano BISECTOR (α = 90−θ/2, casado perfecto) y corren hasta el nodo
    (longitud exterior en la lista de corte); nodos de grado ≥3, colineales o con
    ángulo muy cerrado (α>75°) siguen a tope. Para A-frames, trípodes, cerchas."""

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
    esquinas: Literal["tope", "inglete"] = Field(
        "tope", title="Esquinas",
        description="tope = a escuadra (histórico); inglete = bisectriz en nodos de grado 2",
    )
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


class CreateRobotArmParams(BaseModel):
    """Brazo robótico articulado de 4 ejes (base giratoria, hombro, codo y
    muñeca) con sus juntas ya definidas. Muévelo desde el panel Cinemática y
    expórtalo a URDF/SDF. El alcance es la suma brazo + antebrazo."""

    name: str = Field("Robot", title="Nombre")
    alcance: float = Field(600, gt=200, le=3000, title="Alcance", description="mm")
    position: Vec3 = Field(default_factory=Vec3, title="Posición de la base")
