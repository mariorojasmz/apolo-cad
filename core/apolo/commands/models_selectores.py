"""Schemas de la selección declarativa de caras y aristas (`EdgeSelector`) y del punto {u, v}
sobre la cara elegida (`SlideUV`).

Salieron de `models.py` (congelado por el trinquete de tamaño) cuando `cerca` ganó `medir`
(plan `docs/plans/fea-chapa-empernada.md`, D5); `models.py` los re-exporta con el mismo nombre
y el JSON Schema publicado no cambia (salvo el campo nuevo). Los resuelve
`kernel/selectors.py`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EdgeSelector(BaseModel):
    """Selección declarativa de aristas/caras (estable ante regeneraciones):
    todas | direccion (paralelas a x/y/z) | cara (del bbox) | longitud (rango)
    | cerca (la más próxima a un punto, lo que genera el clic en el viewport)
    | ancla (mate: frame de conexión con nombre publicado por el componente, `name`).
    En mates, `entidad`="arista" resuelve la selección como ARISTA CIRCULAR (borde de un
    barreno/tapa) en vez de como cara (default); "ancla" = frame nombrado (usa `name`)."""

    mode: Literal["todas", "direccion", "cara", "longitud", "cerca", "ancla"] = Field("todas", title="Modo")
    direction: Literal["x", "y", "z"] | None = Field(None, title="Dirección")
    face: Literal["tope", "base", "min_x", "max_x", "min_y", "max_y"] | None = Field(None, title="Cara")
    min: float | None = Field(None, title="Longitud mín.", description="mm")
    max: float | None = Field(None, title="Longitud máx.", description="mm")
    point: list[float] | None = Field(None, title="Punto", description="[x,y,z] mm")
    count: int = Field(1, ge=1, le=200, title="Cuántas")
    # None = "centro" (el de siempre): así `model_dump(exclude_none=True)` de una selección
    # vieja no cambia y su log regenera igual
    medir: Literal["centro", "superficie"] | None = Field(
        None, title="Medir a",
        description="solo modo cerca. centro (default) = distancia al centro de cada cara o "
        "arista (el que publica get_topology); superficie = distancia a la cara o arista misma, "
        "con desempate por el centro. Usa superficie para cargar un taladro o una cara grande "
        "junto a taladros, con el punto SOBRE la cara: con centro puede ganar un taladro vecino. "
        "En una arista entre dos caras la distancia es 0 a ambas y desempata el centro",
    )
    entidad: Literal["cara", "arista", "ancla"] | None = Field(
        None, title="Entidad", description="mates: cara (def.) | arista (circular) | ancla",
    )
    name: str | None = Field(None, max_length=40, title="Ancla", description="nombre del ancla (entidad/modo 'ancla')")


class SlideUV(BaseModel):
    """Desplazamiento {u, v} en el PLANO de una cara (V6.8-E): u = eje MAYOR de la
    cara (mayor extensión, signo hacia su componente mundial dominante positiva),
    v = normal × u. Lo usan snap_to cara-a-cara (`deslizar`) y drill_hole (`en_cara`,
    medido desde el CENTRO de la cara). Acepta '=expresión'."""

    u: float = Field(0, title="u", description="mm a lo largo del eje MAYOR de la cara")
    v: float = Field(0, title="v", description="mm a lo largo del eje menor")
