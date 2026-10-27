"""Schema de la cadena de IZAJE (`create_hoist_chain`, plan `docs/plans/cadena-de-izaje.md`): una
cadena de rodillos ABIERTA con sus dos extremos amarrados a una pieza que pasa por uno o más
piñones. El executor vive en `exec_izaje.py`, la matemática en `apolo/library/izaje.py` y la
geometría en `apolo/library/izaje_geom.py`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from .models_base import Vec3


def _cadenas_simples() -> list[str]:
    from apolo.library.catalog import CATALOG, refs_in_category

    return [r for r in refs_in_category("transmision")
            if r.startswith("CADENA-") and int(CATALOG[r].specs.get("hileras", 1)) == 1]


class CreateHoistChainParams(BaseModel):
    """Cadena de IZAJE: cadena de rodillos de catálogo ABIERTA, con sus dos extremos amarrados a
    la pieza que sube y baja (la plataforma de un elevador, el carro de una mesa elevadora) y que
    pasa por uno o más piñones ya colocados. Arma la cadena, las dos ANCLAS de amarre (horquilla
    roscada derivada de la norma de la cadena: el pasador es el perno del eslabón de unión con
    clip) con su varilla, tuerca y contratuerca DIN 934, TALADRA la pieza de amarre donde pasa la
    varilla y declara las uniones: pasador = perno cadena ↔ ancla (`{id}_pasador_a|b`), varilla =
    perno ancla ↔ pieza (`{id}_amarre_a|b`), contacto cadena ↔ cada piñón (`{id}_p1`, `{id}_p2`…).
    El ancla y sus tuercas cuelgan de la pieza con juntas `fija` (`{id}_jf_…`): en el estudio de
    movimiento, la verificación en pose y la puerta de entrega la cadena SIGUE a la pieza (el
    ramal que se mueve se mueve, el largo se conserva) y avisa si el amarre B se le escapa.

    CÓMO MONTAR (IMPORTANTE):
    - Coloca PRIMERO los piñones (insert_component con una ref PINON-…), la pieza de amarre y su
      junta (prismática de la plataforma, con arrastrar=true o juntas fija), y DESPUÉS la
      cadena: manda el orden del registro.
    - `pinones` en el ORDEN en que los recorre la cadena desde el extremo A hasta el B (elevador:
      [motriz de arriba, loco de abajo]); la cadena gira alrededor de todos en el MISMO sentido
      (lazo abierto por la pieza). `sentido` auto = el camino más corto (el que no se cruza).
    - `extremo_a` / `extremo_b` = el centro del PASADOR de cada amarre (mundo, mm; acepta
      =expresión), en el plano medio de la hilera de los piñones (≤ 1 mm). La varilla del ancla
      sale del pasador alejándose de la cadena por el ramal y atraviesa `pieza_a` / `pieza_b` (una
      placa de amarre soldada a la plataforma): la tuerca y la contratuerca van del otro lado. Deja
      entre el pasador y la placa al menos alto de placa/2 + 2 + Ø varilla + 1 mm (08B: 16.9).
    - Eslabones IMPARES (las dos puntas son eslabones interiores, por donde entra el pasador):
      vacío = el mayor impar que no pasa de B. Lo que le falta a la cadena para llegar a B lo toma
      el ancla B (queda más cerca del piñón y la varilla más afuera); el ajuste de tensado de cada
      ancla es el hueco entre su yugo y la placa. El desgaste de largo plazo lo toma el tensor
      del piñón loco.
    - Varilla por la rotura de la cadena: el límite elástico de una 8.8 (ISO 898-1) ≥ la rotura
      mínima (ASA 40, 08B y 10B → M8; 12B → M10): rompe antes la cadena, que es lo que se
      inspecciona.
    - `fase` auto gira cada piñón que no lleva otra cadena lo justo para que sus dientes
      asienten los rodillos; tal_cual respeta su giro.
    - Sólo cadenas simples en la hilera 1 de cada piñón (la doble y la aleta K1/K2 son otra fase
      del plan)."""

    name: str = Field("Cadena de izaje", title="Nombre")
    cadena: str = Field(
        "CADENA-08B-1", title="Cadena",
        description="referencia del catálogo (CADENA-…-1, simple): fija la norma y el paso",
        json_schema_extra=lambda schema: schema.update({"enum": _cadenas_simples()}),
    )
    pinones: list[str] = Field(
        ..., min_length=1, max_length=6, title="Piñones",
        description="ids de feature de los piñones, en el orden en que la cadena los recorre de A a B",
    )
    pieza_a: str = Field(..., title="Pieza de amarre A", description="id de la pieza donde se amarra el extremo A")
    pieza_b: str | None = Field(
        None, title="Pieza de amarre B",
        description="id de la pieza donde se amarra el extremo B; vacío = la misma que A",
    )
    extremo_a: Vec3 = Field(..., title="Pasador A", description="centro del pasador del amarre A (mm, mundo)")
    extremo_b: Vec3 = Field(..., title="Pasador B", description="centro del pasador del amarre B (mm, mundo)")
    sentido: Literal["auto", "horario", "antihorario"] = Field(
        "auto", title="Sentido de giro",
        description="cómo gira la cadena alrededor de los piñones, mirando el piñón A desde la "
                    "punta de su eje; auto = el camino más corto",
    )
    eslabones: int | None = Field(
        None, ge=3, le=2001, title="Eslabones",
        description="número IMPAR de pasos; vacío = el mayor impar que no pasa de B (acepta =expresión)",
    )
    fase: Literal["auto", "tal_cual"] = Field(
        "auto", title="Fase de los dientes",
        description="auto = gira los piñones libres para que asienten los rodillos; tal_cual = respeta su giro",
    )

    @field_validator("cadena")
    @classmethod
    def _cadena_simple(cls, v: str) -> str:
        refs = _cadenas_simples()
        if v not in refs:
            raise ValueError(f"cadena '{v}' no sirve para izaje en esta versión; usa una simple: {', '.join(refs)}")
        return v
