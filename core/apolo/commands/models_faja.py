"""Schema de la faja de banda (`create_belt_conveyor`) con sus listas de catálogo.

Sale de `models.py` (congelado por el trinquete de tamaño). Las cotas viven en
`apolo/library/belt_conveyor*.py`; el executor y el sello de entrada (`cierres`, v5;
`tramo_max` y `criterio`, v6), en `exec_faja.py`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic.json_schema import SkipJsonSchema

from .models import Rot3, Vec3, _motor_refs


def _drum_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("tambores")


def _tube_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return refs_in_category("tubos_estructurales")


def _takeup_refs() -> list[str]:
    """Las unidades tensoras de carro de catálogo (UCT, con su carrera de ficha)."""
    from apolo.library.belt_conveyor_cotas import unidades_tensoras

    return unidades_tensoras()


def _takeup_v3_refs() -> list[str]:
    """Los tensores tipo trotadora que aceptaba la v3: un log viejo los trae y regenera con la
    unidad tensora UCT del mismo eje (no se ofrecen: no tienen carrera de tensado)."""
    from apolo.library.catalog import refs_in_category

    return refs_in_category("tensores_trotadora")


class CreateBeltConveyorParams(BaseModel):
    """Faja de banda plana paramétrica con cama de deslizamiento y 2 tambores de extremo,
    montada como en la industria: bastidor de 2 largueros de tubo (acero) con 4 patas soldadas y
    pies niveladores; tambor motriz de eje vivo en 2 chumaceras de brida UCF por fuera de los
    largueros; tambor de cola en 2 unidades tensoras de carro UCT de catálogo (`tensor`; su
    carrera de ficha cubre el estiramiento de la banda; 'ninguno' = cola en chumaceras, sin
    tensado); motorreductor coaxial del lado +Y con acople flexible sobre una base en voladizo
    soldada a la pata; cama atornillada sobre soportes (la banda se cambia de costado quitando
    pernos); guardas atornilladas (`guardas`: laterales en L, cajas de los tambores, tapas de los
    extremos de eje, cubierta del acople y guardas inferiores bajo la ranura entre el borde de la
    banda y el larguero); las puntas de los largueros, cerradas con placa soldada. Una faja
    larga sale en tramos (`tramo_max`, 6000 mm por defecto en toda faja nueva: la barra
    comercial): largueros, cama y guardas laterales por tramo, unidos por placas de empalme
    soldadas a las puntas y atornilladas entre sí por fuera del tubo, con una estación de patas
    junto a cada empalme; pide un `tramo_max` menor si el transporte lo exige. Con más de 3 m
    entre tambores lleva rodillos de retorno de catálogo bajo el ramal de retorno (cada ≤ 3 m),
    en soportes atornillados a los largueros; lo que se atornilla a la cara interior de un
    larguero va con perno pasante y buje soldado (la tuerca queda por fuera, con llave).
    `lado_abierto` ('+y' o '-y', el costado de los operarios que toman o dejan producto): con
    guardas, ese costado no lleva la pared de la guarda lateral sino una guarda cubre-ranura a
    ras de la banda que sigue tapando la ranura banda ↔ larguero (las guardas de los tambores,
    del retorno y los cierres siguen); el motorreductor va del lado +Y. Declara
    sus uniones (perno/soldadura/contacto) y sus anclajes (los pies), así que sale con camino de
    carga a tierra. Editar cualquier parámetro regenera la faja entera."""

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
        "TAMBOR-102-RET", title="Tambor de cola",
        json_schema_extra=lambda schema: schema.update({"enum": _drum_refs()}),
    )
    tubo: str = Field(
        "TUBO-4X2", title="Tubo del bastidor",
        json_schema_extra=lambda schema: schema.update({"enum": _tube_refs()}),
    )
    tensor: str = Field(
        "UCT205-150", title="Tensor de cola",
        json_schema_extra=lambda schema: schema.update({"enum": ["ninguno"] + _takeup_refs()}),
    )
    motor: str = Field(
        "MOTOR-150-EH", title="Motorreductor",
        json_schema_extra=lambda schema: schema.update({"enum": ["ninguno"] + _motor_refs()}),
    )
    guardas: bool = Field(True, title="Guardas")
    # v5, FUERA del schema (criterio de Apolo, no del modelador): placas de cierre de los
    # largueros y guardas inferiores bajo la ranura banda ↔ larguero. Lo pone el sello de
    # entrada (`exec_faja.sellar`) a todo comando NUEVO; un log v4 no lo trae → False → igual.
    cierres: SkipJsonSchema[bool] = Field(False)
    # v6 (plan faja-larga-en-tramos): VISIBLE, lo puede pedir el modelador; sin él (log viejo)
    # el bastidor sale en una pieza. El sello lo pone en 6000 a toda faja nueva.
    tramo_max: float | None = Field(
        None, ge=1000, le=12000, title="Largo máximo de tramo",
        description="mm; el bastidor se parte en tramos iguales empernados de hasta este largo "
                    "(vacío: una pieza)")
    # F1b (D7), VISIBLE: el costado sin pared de guarda lateral; «ninguno» = lo de siempre.
    lado_abierto: Literal["ninguno", "+y", "-y"] = Field(
        "ninguno", title="Lado abierto",
        description="costado de los operarios: sin la pared de la guarda lateral, con una guarda "
                    "cubre-ranura a ras de la banda (sólo con guardas)")
    # v6, FUERA del schema: 6 = rodillos de retorno y pernos pasantes con buje; 7 (F1b) = el 6
    # con el pie de tuerca soldada y contratuerca y los brazos del motor a tope contra la pata;
    # 8 (F1c) = el 7 con los agujeros de cada unión, sin tuercas dentro de los tubos, paños ≤ 3 m,
    # cama calculada y el largo de cada perno. Un log de antes no lo trae → 5 → la v5 tal cual.
    criterio: SkipJsonSchema[int] = Field(5)
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
        if v != "ninguno" and v not in _takeup_refs() + _takeup_v3_refs():
            raise ValueError(f"tensor desconocido '{v}' (válidos: ninguno, "
                             f"{', '.join(_takeup_refs())})")
        return v

    @field_validator("motor")
    @classmethod
    def _known_motor_eh(cls, v: str) -> str:
        if v != "ninguno" and v not in _motor_refs():
            raise ValueError(f"motor desconocido '{v}'")
        return v
