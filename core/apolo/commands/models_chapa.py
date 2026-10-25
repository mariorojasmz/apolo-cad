"""Params de la chapa plegada: pestañas ricas, taladros y recortes, pestaña hija.

Sale de `models.py` (fachada) por tamaño.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .models_base import Rot3, Vec3


SheetSide = Literal["frente", "atras", "izquierda", "derecha"]


class Hole(BaseModel):
    """Taladro pasante en la base de una chapa (coords centradas en la base, mm)."""

    x: float = Field(0, title="X en la base", description="mm, 0 = centro")
    y: float = Field(0, title="Y en la base", description="mm, 0 = centro")
    d: float = Field(8, gt=0, le=500, title="Diámetro", description="mm")


class FlapHole(BaseModel):
    """Taladro pasante en una pestaña. u = mm a lo largo del pliegue (0 = centro;
    + = +X mundo en frente/atras, +Y en izquierda/derecha). v = mm desde el BORDE
    LIBRE de la pestaña hacia el pliegue (no depende del radio)."""

    u: float = Field(0, title="u (a lo largo del pliegue)", description="mm, 0 = centro")
    v: float = Field(10, gt=0, title="v (desde el borde libre)", description="mm")
    d: float = Field(8, gt=0, le=500, title="Diámetro", description="mm")


class FlapCutout(BaseModel):
    """Recorte rectangular pasante en una pestaña, centrado en (u, v); `ancho` a lo
    largo de u y `alto` a lo largo de v. No puede invadir la zona de pliegue (se
    rechaza con el dominio válido en el error)."""

    u: float = Field(0, title="u (centro)", description="mm, 0 = centro del pliegue")
    v: float = Field(20, gt=0, title="v (centro, desde el borde libre)", description="mm")
    ancho: float = Field(40, gt=0, title="Ancho (según u)", description="mm")
    alto: float = Field(20, gt=0, title="Alto (según v)", description="mm")


class ChildFlap(BaseModel):
    """Pestaña de pestaña (2º pliegue, en el borde libre de la padre): perfiles
    C/Z, solapas de caja, hem de rigidez. `angulo` respecto al plano de la padre;
    `direccion`: 'interior' pliega hacia el mismo lado que el pliegue padre
    (perfil C), 'exterior' hacia el lado opuesto (perfil Z)."""

    altura: float = Field(15, gt=0, le=2000, title="Altura", description="mm")
    angulo: float = Field(90, gt=0, le=170, title="Ángulo", description="grados respecto a la padre")
    radio: float | None = Field(None, ge=0, le=200, title="Radio", description="mm; vacío = el de la padre")
    direccion: Literal["interior", "exterior"] = Field("interior", title="Dirección")
    holes: list[FlapHole] = Field(default_factory=list, title="Taladros")
    cutouts: list[FlapCutout] = Field(default_factory=list, title="Recortes")


class FlapSpec(BaseModel):
    """Pestaña rica: features propias (taladros/recortes en coords u,v) y hasta
    UNA pestaña hija (multi-pliegue de un nivel)."""

    lado: SheetSide = Field(..., title="Lado")
    altura: float = Field(40, gt=0, le=2000, title="Altura", description="mm")
    angulo: float = Field(90, gt=0, le=170, title="Ángulo", description="grados desde la base")
    radio: float | None = Field(None, ge=0, le=200, title="Radio", description="mm; vacío = el global")
    holes: list[FlapHole] = Field(default_factory=list, title="Taladros en la pestaña")
    cutouts: list[FlapCutout] = Field(default_factory=list, title="Recortes en la pestaña")
    child: ChildFlap | None = Field(None, title="Pestaña hija")


class SheetMetalParams(BaseModel):
    """Pieza de chapa plegada: base rectangular de `espesor` con pestañas (flanges)
    opcionales en los 4 lados (frente=+Y, atras=−Y, izquierda=−X, derecha=+X).
    Generaliza el soporte en L, el canal en U, la bandeja — y con `flaps` (V5.5)
    los perfiles C/Z, solapas y hems: cada FlapSpec lleva sus propios taladros y
    RECORTES rectangulares (coords locales: u a lo largo del pliegue alineada con
    el eje mundial, v desde el BORDE LIBRE) y hasta una pestaña hija. Si `flaps`
    viene, SUSTITUYE a lados/altura_pestana/angulo (que se ignoran). `k_factor`
    vacío = por MATERIAL de la pieza (acero 0.40 · inox 0.45 · aluminio 0.35 ·
    latón 0.35). El radio alimenta el DESPLEGADO (flat pattern DXF/SVG para corte
    láser); taladros y recortes salen en el 3D y proyectados en el desplegado.
    Editar cualquier parámetro regenera la chapa entera."""

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
    k_factor: float | None = Field(
        None, ge=0, le=0.5, title="Factor K",
        description="posición de la fibra neutra; vacío = según el material de la pieza",
    )
    holes: list[Hole] = Field(default_factory=list, title="Taladros en la base")
    flaps: list[FlapSpec] = Field(
        default_factory=list, title="Pestañas ricas (V5.5)",
        description="si se da, sustituye a lados/altura_pestana/angulo",
    )
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")

    @field_validator("lados")
    @classmethod
    def _lados_unicos(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("lados duplicados")
        return v

    @field_validator("flaps")
    @classmethod
    def _flaps_unicos(cls, v: list["FlapSpec"]) -> list["FlapSpec"]:
        lados = [f.lado for f in v]
        if len(set(lados)) != len(lados):
            raise ValueError("flaps con lado duplicado")
        return v
