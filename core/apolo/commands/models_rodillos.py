"""Schemas de los rodillos tipo trotadora (`create_take_up`, `create_drive_roller`).

Salen de `models.py` (congelado por el trinquete de tamaño) con sus listas de catálogo; la
geometría que comparten vive en `apolo/library/take_up.py`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from .models import Rot3, Vec3


def _bearing_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("rodamientos")


def _perno_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("pernos")


class CreateTakeUpParams(BaseModel):
    """Rodillo de cola TENSABLE tipo trotadora (eje fijo), paramétrico. Rodillo tubular (engomado
    opcional) sobre 2 rodamientos con seeger; eje FIJO que sobresale a cada lado; por lado un
    TENSOR: un soporte en «C» (alma soldada al larguero + 2 aletas) y un perno horizontal que pasa
    por las 2 aletas y por el eje (que tiene HILO ahí = hace de tuerca). Sin chumacera.

    PARA QUÉ SIRVE: rodillo de cola (no motriz) de una faja de banda, con tensado integrado.

    CORONADO (`coronado_mm`, opcional; 0 = cilindro recto): con banda PLANA sobre rodillo de
    ACERO LISO (sin engomado) es lo que CENTRA la banda, que migra hacia el Ø mayor: un rodillo
    más alto al centro la devuelve sola al eje de la faja. Forma TRAPEZOIDAL: centro recto = 1/2
    de la cara y un cono en el 1/4 de cada punta que baja `coronado_mm` en el RADIO (Ø114 con
    0.5 → Ø113 en las puntas). Se fabrica en TORNO: cilindrar el tubo al Ø nominal y tornear los
    dos conos en el mismo montaje que los alojamientos de los rodamientos (quedan concéntricos).
    Con `engomado`, el caucho copia el coronado. Poco basta: un coronado excesivo arruga y gasta
    los bordes de la banda. Si el tambor motriz también va coronado, ata los dos a UNA variable.

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
    coronado_mm: float = Field(
        0, ge=0, le=10, title="Coronado (en el radio)",
        description="mm que BAJA el radio en cada punta: coronado trapezoidal (centro recto 1/2 "
                    "de la cara, conos en el 1/4 de cada punta) que centra la banda plana; "
                    "0 = cilindro recto",
    )
    holgura_eje: float = Field(20, ge=0, le=100, title="Holgura del eje (en desuso)", description="EN DESUSO: el recorrido lo da el claro entre aletas")
    eje_fit: str | None = Field(
        None, max_length=6, title="Ajuste ISO 286 del eje",
        description="clase del asiento del eje (p. ej. 'g6' — eje FIJO/anillo interior "
                    "estacionario, carga rotatoria exterior): se anota en el nombre del eje "
                    "y la memoria verifica el asiento del rodamiento contra la norma",
    )
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
