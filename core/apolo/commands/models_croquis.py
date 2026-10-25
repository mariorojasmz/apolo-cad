"""Params de croquis, revolución, extrusión, importación STEP, barrido, loft,
superficies y engrosado.

Sale de `models.py` (fachada) por tamaño.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .models_base import Rot3, Vec3
from .models_selectores import EdgeSelector


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


class CurveSpec(BaseModel):
    """Una curva del contorno de una superficie: puntos [x,y,z] unidos recto a tramos,
    o suave con spline. Acepta '=expresión' por componente."""

    points: list[list[float]] = Field(
        ..., min_length=2, title="Puntos", description="[x,y,z] (≥2); '=expresión' por componente",
    )
    smooth: bool = Field(False, title="Suave (spline)")


class BoundarySurfaceParams(BaseModel):
    """Superficie (Face) acotada por un contorno cerrado de curvas. Para geometría de
    doble curvatura del vertical (chutes, tolvas, deflectores, guardas curvas): úsala
    con `thicken` para darle espesor de chapa → pared fabricable. Una o varias curvas
    que juntas cierren el lazo; `points` la levantan a un parche NO plano; `holes` abren
    lazos interiores. Es geometría de CONSTRUCCIÓN (volumen 0) hasta engrosarla."""

    name: str = Field("Superficie", title="Nombre")
    curves: list[CurveSpec] = Field(..., min_length=1, title="Contorno")
    points: list[list[float]] | None = Field(
        None, title="Puntos de forma",
        description="puntos 3D [x,y,z] que la superficie toca → parche no plano (opcional)",
    )
    holes: list[list[CurveSpec]] | None = Field(None, title="Huecos (lazos interiores)")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")


class FillSurfaceParams(BaseModel):
    """Parche (Face) que cubre la región acotada por las aristas seleccionadas de un
    sólido: tapar un hueco o cerrar un borde. tangent=True busca continuidad tangente
    (G1) con las caras vecinas — solo posible en geometría de continuación suave; en
    paredes perpendiculares avisa. Combínalo con `thicken` para hacerlo pared."""

    name: str = Field("Parche", title="Nombre")
    feature: str = Field(..., title="Sólido", description="id de feature")
    edges: EdgeSelector = Field(
        default_factory=EdgeSelector, title="Aristas del contorno",
        json_schema_extra={"x-selector": "edge"},
    )
    tangent: bool = Field(False, title="Continuidad tangente (G1)")


class ThickenParams(BaseModel):
    """Da espesor a una superficie (de boundary_surface / fill_surface) a lo largo de su
    normal → sólido de pared fabricable. `both` engruesa `thickness` a CADA lado (espesor
    total 2×, centrado); `flip` invierte el lado. Muta la superficie en el sólido."""

    feature: str = Field(..., title="Superficie", description="id de feature")
    thickness: float = Field(3, gt=0, le=1000, title="Espesor", description="mm")
    both: bool = Field(False, title="Ambos lados")
    flip: bool = Field(False, title="Invertir lado")
