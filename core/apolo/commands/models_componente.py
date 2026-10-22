"""Params de `insert_component` y de su orientación declarativa (plan perfiles-con-acuerdo D3).

Salieron de `models.py` (congelado por el trinquete de tamaño) cuando el comando ganó
`orientacion`; `models.py` los re-exporta con el mismo nombre. La traducción a rotación vive en
`apolo/library/perfiles_abiertos.py` (necesita la familia del catálogo).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from .models import Rot3, Vec3

Direccion = Literal["+x", "-x", "+y", "-y", "+z", "-z", "x", "y", "z"]


class OrientacionPerfil(BaseModel):
    """Orientación DECLARATIVA de un perfil abierto del catálogo (UPN, IPE, ángulo L) por ejes
    del mundo, en lugar de `rotation`. Canal U: `largo` + `abre_hacia`; viga I: `largo` +
    `canto`; ángulo L: `alas` (`largo` opcional). Sólo giros rectos: para inclinarlo,
    después `transform` o `snap_to`."""

    largo: Direccion | None = Field(
        None, title="Largo", description="eje del mundo a lo largo del perfil (U e I; en L se "
        "deduce de las alas). El signo no importa",
    )
    abre_hacia: Direccion | None = Field(
        None, title="Abre hacia", description="canal U: hacia dónde abre, del alma a la punta de "
        "las alas (= eje del ancla cara_alma_interior), p. ej. '-y'",
    )
    canto: Direccion | None = Field(
        None, title="Canto", description="viga I: eje de la altura h (el alma queda en ese "
        "plano). El signo no importa",
    )
    alas: list[Direccion] | None = Field(
        None, min_length=2, max_length=2, title="Alas",
        description="ángulo L: [ala_1, ala_2] = hacia dónde sale cada ala desde el talón, "
        "p. ej. ['+z', '-y'] (ala vertical que sube y horizontal hacia −y)",
    )


class InsertComponentParams(BaseModel):
    """Inserta un componente del catálogo (biblioteca). Los componentes
    cortables (perfiles, rodillos, patas, guardas) aceptan length a medida, y la TORNILLERÍA
    de largo a medida (PERNO-HEX-*, PERNO-M*, PERNO-COCHE-*…: specs `largo_min_mm`/
    `largo_max_mm` en `catalog`) también: `length` = largo NOMINAL bajo cabeza de la serie
    normalizada dentro de ese rango (M6x20 → length 20); sin length, el largo de referencia del
    builder (50). La BOM lo compra por ese largo. Para una unión atornillada completa (taladros
    + perno + tuerca con el largo calculado) usa join_bolted.
    Perfiles abiertos (UPN, IPE, ángulo L): en vez de `rotation` puedes dar `orientacion`
    por ejes del mundo (U: largo + abre_hacia; I: largo + canto; L: alas) y publican anclas
    para mates: U/I `cara_alma_interior`, `dorso_alma` (U) / `cara_alma_opuesta` (I),
    `zona_plana` (centro de la parte PLANA del alma: el perfil real tiene acuerdos r1) y sus
    límites `zona_plana_1`/`zona_plana_2` (eje hacia el centro: un taladro o asiento de radio ρ
    va a ≥ ρ de ambos); L `talon`, `cara_ala_1`/`cara_ala_2`, `zona_plana_ala_1`/`_2`.
    get_topology las lista en coordenadas del mundo."""

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
        None, gt=0, le=12000, title="Longitud",
        description="mm: largo de corte de un cortable, o largo NOMINAL de la tornillería de "
        "largo a medida (de su serie de catálogo); vacío = estándar",
    )
    position: Vec3 = Field(default_factory=Vec3, title="Posición")
    rotation: Rot3 = Field(default_factory=Rot3, title="Rotación")
    # None = la rotación de siempre (`rotation`): un log viejo regenera igual
    orientacion: OrientacionPerfil | None = Field(
        None, title="Orientación (perfil abierto)",
        description="sólo UPN/IPE/ángulo L; excluye rotation. U: {largo, abre_hacia}; I: "
        "{largo, canto}; L: {alas: [ala_1, ala_2]}",
    )

    # Fuera del schema: lo pone el sello de entrada (`exec_componente.sellar`) a cada comando
    # NUEVO. 1 = log viejo: `length` se ignora en lo no cortable (regenera igual); 2 = la
    # tornillería de largo a medida usa `length` y lo que no lo admite lo rechaza (F6).
    criterio: SkipJsonSchema[int] = Field(1, ge=1, le=2)

    @field_validator("component")
    @classmethod
    def _known_ref(cls, v: str) -> str:
        refs = _catalog_refs()
        if v not in refs:
            # el schema del agente ya no lista las refs (D3 de mcp-sin-friccion): la sugerencia
            # vive aquí, en la entrada
            import difflib

            cerca = difflib.get_close_matches(v, refs, n=3, cutoff=0.6)
            pista = f"; ¿quisiste decir: {', '.join(cerca)}?" if cerca else ""
            raise ValueError(f"componente desconocido '{v}'{pista}")
        return v

    @model_validator(mode="after")
    def _orientacion_o_rotacion(self) -> "InsertComponentParams":
        if self.orientacion is not None and any(self.rotation.tuple()):
            raise ValueError("orientacion y rotation se excluyen: deja rotation en 0 (para "
                             "inclinar el perfil, después transform o snap_to)")
        return self


def _catalog_refs() -> list[str]:
    from apolo.library.catalog import CATALOG

    return list(CATALOG.keys())
