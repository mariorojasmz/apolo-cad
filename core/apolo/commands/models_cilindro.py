"""Schema de `create_pneumatic_cylinder` (plan V8.9 D5, F2): el cilindro neumático en 3D. Sale de
`models.py` (congelado por el trinquete de tamaño). El executor está en `cilindro.py`; la
geometría, en `library/builders_neumatica.py`; las cotas de los montajes, en
`library/neumatica/montajes.py`.

El plan lo llama `create_cylinder`, pero ese nombre ya es la primitiva cilíndrica del registro
(`models.CreateCylinderParams`): el super-comando es `create_pneumatic_cylinder`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import Vec3

#: direcciones del mundo que aceptan `eje` y `puertos` (la FK sólo mueve ejes alineados)
DIRECCIONES = Literal["+X", "-X", "+Y", "-Y", "+Z", "-Z"]
MONTAJES = Literal["brida_delantera", "brida_trasera", "pies", "ninguno"]


def _cilindros() -> list[str]:
    from apolo.library.catalog import CATALOG

    return [r for r, c in CATALOG.items()
            if c.neumatico is not None and c.neumatico.tipo == "cilindro"
            and c.familia in ("cilindro_iso15552", "cilindro_iso6432")]


class Empujador(BaseModel):
    """Placa de acero al extremo del vástago, con su buje roscado que asienta en el hombro."""

    ancho: float = Field(..., gt=0, le=3000, title="Ancho", description="mm, a lo largo del eje local Y (⊥ a eje y puertos)")
    alto: float = Field(..., gt=0, le=3000, title="Alto", description="mm, hacia el lado de los puertos")
    espesor: float = Field(8.0, gt=0, le=100, title="Espesor", description="mm, a lo largo del avance")


class CreatePneumaticCylinderParams(BaseModel):
    """Coloca un CILINDRO NEUMÁTICO de catálogo (ISO 15552 o ISO 6432) con su carrera, su montaje
    y, opcional, el EMPUJADOR al extremo del vástago (plan V8.9 D5). Emite:
    - `{id}_cuerpo` (la ref, con la carrera: UNA fila de BOM por cilindro), `{id}_vastago`
      (viene con la ref: no se cobra aparte) y, según el montaje, `{id}_brida` o
      `{id}_pie_delantero` + `{id}_pie_trasero` (accesorios ISO 15552, cotas de Flowtech TS3017)
      y `{id}_empujador`;
    - la junta PRISMÁTICA `{id}_vastago` (cuerpo → vástago, de 0 = retraído a `carrera`, sin
      arrastrar): muévela con set_motion o en Cinemática; el empujador la sigue por su junta fija
      `{id}_jf_empujador`;
    - las uniones internas: accesorio ↔ cuerpo (los 4 tornillos de la tapa) y empujador ↔
      vástago (la rosca del extremo en el buje). El cilindro NO queda sujeto a la máquina: une la
      brida o los pies (join_bolted, o fasten + drill_hole en las anclas `brida_agujero_k` /
      `pie_*_agujero_k`); sin unión es «pieza sin unión».
    Anclas (coords mundo, en la pose retraída): en el cuerpo `eje` (la cara delantera, hacia el
    avance), `tapa_trasera`, los puertos `A` (fondo) y `B` (vástago), y en ISO 6432 `nariz` y
    `pasador`; en el vástago `extremo_vastago`; en la brida `brida` (su cara de apoyo) y
    `brida_agujero_1..4`; en cada pie `pie_delantero`/`pie_trasero` (su base) y sus 2 agujeros.

    - `ref`: un cilindro del catálogo (categoría cilindros_neumaticos).
    - `carrera` (mm, acepta `=expr`): dentro del rango de la ficha.
    - `position`: el centro de la cara DELANTERA del cuerpo (por donde sale el vástago).
    - `eje`: hacia dónde AVANZA el vástago; `puertos`: hacia dónde miran los puertos A y B
      (perpendicular a `eje`; los pies quedan del lado opuesto).
    - `montaje`: brida_delantera (MF1), brida_trasera (MF2), pies (MS1) o ninguno. ISO 6432 se
      monta por la NARIZ (brida_delantera = la rosca de la nariz con su tuerca en un agujero de
      la máquina, sin accesorio) o ninguno.
    - `empujador`: {ancho, alto, espesor} o null (sin placa)."""

    name: str = Field("Cilindro", max_length=60, title="Nombre",
                      description="prefijo de los nombres de sus piezas (por rol)")
    ref: str = Field(
        "CIL-ISO15552-32", title="Cilindro", description="ref de la categoría cilindros_neumaticos",
        json_schema_extra=lambda schema: schema.update({"enum": _cilindros()}),
    )
    carrera: float = Field(100.0, gt=0, le=3000, title="Carrera (mm)")
    position: Vec3 = Field(default_factory=Vec3, title="Posición",
                           description="centro de la cara delantera del cuerpo")
    eje: DIRECCIONES = Field("+X", title="Avance", description="dirección en que sale el vástago")
    puertos: DIRECCIONES = Field("+Z", title="Puertos", description="lado de los puertos A y B (⊥ a eje)")
    montaje: MONTAJES = Field("brida_delantera", title="Montaje")
    empujador: Empujador | None = Field(None, title="Empujador",
                                        description="placa al extremo del vástago; null = sin placa")

    @field_validator("ref")
    @classmethod
    def _ref_valida(cls, v: str) -> str:
        from apolo.library.electrico.referencias import sufijo_sugerencia

        validos = _cilindros()
        if v not in validos:
            raise ValueError(f"«{v}» no es un cilindro del catálogo; válidos: {', '.join(validos)}."
                             f"{sufijo_sugerencia(v, validos)}")
        return v

    @model_validator(mode="after")
    def _perpendiculares(self):
        if self.eje[1] == self.puertos[1]:
            raise ValueError(f"`puertos` ({self.puertos}) tiene que ser perpendicular a `eje` "
                             f"({self.eje}): elige otro eje del mundo")
        return self
