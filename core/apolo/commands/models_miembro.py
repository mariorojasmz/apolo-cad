"""Params de `create_brace` (plan uniones-que-tocan, D3/D3b): un miembro de perfil de catálogo
entre dos piezas, con cada extremo cortado como se une. La geometría, en `library/miembro.py`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .models_base import Vec3

TipoUnion = Literal["a_tope", "boca_de_pescado", "inglete"]


class ExtremoMiembro(BaseModel):
    """Un extremo del miembro: la pieza que lo recibe, un punto del EJE del miembro en ese extremo
    (sobre la cara de la pieza o dentro de ella: p. ej. su eje) y cómo se une."""

    pieza: str | None = Field(
        None, title="Pieza que recibe",
        description="id de la pieza a la que llega este extremo (un poste, un larguero, otro tubo). "
        "Obligatoria salvo en 'inglete' contra un miembro que todavía no existe: la soldadura la "
        "declara entonces el comando del vecino",
    )
    punto: Vec3 = Field(..., title="Punto del eje",
                        description="mm: el eje del miembro pasa por aquí (en o dentro de la pieza)")
    union: TipoUnion = Field(
        "a_tope", title="Unión",
        description="a_tope = corte plano a ras de la cara PLANA que recibe (sierra, con su ángulo); "
        "boca_de_pescado = tubo contra tubo REDONDO: el extremo copiado al cilindro que recibe; "
        "inglete = contra otro miembro que sale del mismo nodo (`punto` = el nodo, `hacia` = el otro "
        "extremo del vecino): corte por el plano bisector",
    )
    hacia: Vec3 | None = Field(
        None, title="Hacia (inglete)",
        description="sólo 'inglete': el otro extremo del miembro vecino que sale del nodo",
    )


class CreateBraceParams(BaseModel):
    """Miembro de perfil de catálogo ENTRE dos piezas —riostra, diagonal, pasamanos que llega a un
    poste, zanca, travesaño inclinado— con cada extremo cortado A RAS de lo que lo recibe y su
    unión SOLDADA declarada con el cordón MEDIDO sobre la línea de contacto (la puerta lo exige:
    `union.contacto_real`). Úsalo en vez de girar un insert_component a mano: un tubo recto girado
    queda con los extremos a escuadra, toca su poste por una arista (o no lo toca) y la soldadura
    declarada es fantasma.

    El eje va de `a.punto` a `b.punto` (pon cada punto en la cara de su pieza o en su eje: el
    comando busca la cara que el eje corta primero viniendo del centro del miembro). Cada extremo
    se genera por su `union`: `a_tope` (cara plana: corte de sierra con su ángulo),
    `boca_de_pescado` (tubo redondo contra tubo redondo: el extremo copiado al cilindro, como una
    copiadora de tubos) o `inglete` (contra otro miembro del mismo nodo; `hacia` = el otro extremo
    del vecino; el vecino se crea con su propio create_brace en inglete hacia éste). Solapada y
    cartela no entran: dilo y únelo a_tope a una placa.

    La sección: z = eje, x = la vertical del plano que contiene al eje (X si el eje es vertical),
    girada `giro`°: una riostra en un plano vertical queda con dos caras en ese plano, a ras de
    las caras de sus postes. La BOM y la lista de corte llevan la ref de catálogo, el largo de
    corte EXTERIOR (`cut_length`) y el ángulo de cada extremo desde el corte recto (∠α_a/α_b).
    Declara `{id}_a` y `{id}_b` (soldadura pieza ↔ miembro, garganta `garganta_mm`, largo = el
    cordón medido); un extremo que no toca su pieza es error con la cifra. Paramétrico: los puntos
    aceptan expresiones (=x_poste) y se recalcula al regenerar.
    MONTAJE: se presenta el miembro cortado entre las dos piezas, se puntea y se suelda todo el
    perímetro del extremo (filete, garganta a = 0,7·cateto)."""

    name: str = Field("Riostra", title="Nombre", description="el ROL (Riostra lateral, Pasamanos…)")
    perfil: str = Field(
        "TUBO-1X1", title="Perfil",
        description="ref de catálogo CORTABLE (tubo cuadrado, rectangular o redondo, ángulo…)",
    )
    a: ExtremoMiembro = Field(..., title="Extremo A")
    b: ExtremoMiembro = Field(..., title="Extremo B")
    giro: float = Field(0, ge=-360, le=360, title="Giro de la sección",
                        description="grados sobre el eje del miembro")
    garganta_mm: float = Field(3.0, gt=0, le=20, title="Garganta del cordón",
                               description="mm (a = 0,707·cateto) de las dos soldaduras")

    @field_validator("perfil")
    @classmethod
    def _cortable(cls, v: str) -> str:
        from apolo.library.catalog import CATALOG

        comp = CATALOG.get(v)
        if comp is None:
            import difflib

            cerca = difflib.get_close_matches(v, list(CATALOG), n=3, cutoff=0.6)
            pista = f"; ¿quisiste decir: {', '.join(cerca)}?" if cerca else ""
            raise ValueError(f"perfil desconocido '{v}'{pista}")
        if not comp.cuttable:
            raise ValueError(f"{v} no es un perfil cortable (tubo, ángulo, perfil): no se le puede "
                             "dar largo")
        return v
