"""Schema de la cadena de rodillos entre dos piñones (`create_chain`, plan `cadenas-pinones`
D7). Sale de `models.py` (congelado por el trinquete de tamaño) con su lista de catálogo; el
executor vive en `exec_transmision.py` y la matemática, en `apolo/library/transmision.py`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


def _chain_refs() -> list[str]:
    from apolo.library.catalog import refs_in_category

    return [r for r in refs_in_category("transmision") if r.startswith("CADENA-")]


class CreateChainParams(BaseModel):
    """Cadena de rodillos de catálogo ARMADA entre dos piñones ya colocados (relacional, como
    snap_to): en cada regenerate lee las anclas VIVAS de `pinon_a` (A = el motriz) y `pinon_b`
    y cierra el lazo con eslabones PARES, cada rodillo sentado en un asiento de diente, con
    cualquier fase de los dientes. Si la variable que mueve un piñón cambia, la cadena lo sigue.
    Es UNA pieza: `component` = la cadena (la BOM pesa kg/m × largo) y `cut_length` = eslabones
    × paso; declara el contacto cadena ↔ cada piñón (`fasten` contacto `{id}_a` y `{id}_b`).

    CÓMO MONTAR (IMPORTANTE):
    - Coloca PRIMERO los dos piñones (insert_component con una ref PINON-…, ubicados con
      position/rotation, transform o snap_to) y DESPUÉS la cadena: manda el orden del registro.
      Un piñón que se mueve DESPUÉS de la cadena no la arrastra, y add_mate tampoco (los mates
      se resuelven al final del regenerate): la regla «transmisión por cadena» avisa el desfase.
    - Ejes paralelos (≤ 0.5°) e hileras en el MISMO plano (≤ 1 mm): da el mismo giro a los dos
      piñones. El origen del piñón es el plano medio de su hilera 1 (el cubo sale hacia −Z
      local) y un piñón volteado (eje opuesto) vale.
    - Norma: ASA 40 (ANSI B29.1, la que más se vende en Lima) y 08B (ISO 606, «BS» o europea)
      son de 1/2" las dos pero NO son intercambiables: cadena y piñones de la MISMA serie (el
      `cadena` de las specs del piñón dice cuál va).
    - Cadena doble (-2) sólo sobre piñón dúplex, en `hilera` 1 (cubre las dos). Un piñón
      doble-simple lleva DOS cadenas simples, una por hilera (`hilera_a`/`hilera_b` = 1 o 2):
      así se encadena rodillo a rodillo, cada rodillo con UN piñón y un lazo a cada vecino.
    - Eslabones = el menor número PAR cuyo centro exacto es ≥ los centros medidos; lo que sobra
      queda como flecha del ramal inferior y la regla lo publica: ajusta los centros al exacto o
      deja recorrido de tensado (motor sobre ranuras).
    - `eslabones` = N (par) fija el largo: la cadena acepta centros hasta 0.05 mm sobre el
      exacto de N (redondear la cota no hace saltar a N + 2); más lejos falla y dice el exacto.
      Para COLOCAR los piñones a ese centro, usa la expresión
      `=centros_cadena(paso, z_a, z_b, N)` en la variable de la distancia (p. ej.
      `=centros_cadena(12.7, 30, 15, 48)` = 159.0349).
    - Rodillo a rodillo (1:1, piñones iguales): L = z + 2·t/p, así que el paso de rodillos t va
      en múltiplos de p/2 con L par y no sobra cadena: Z14 → 76.2 (26 eslabones) o 101.6 (30);
      Z15 → 95.25 (30) o 107.95 (32).
    - `fase`: a centros exactos la cadena sólo engrana si los dientes de A y B están en fase (en
      1:1, fase relativa 0 con z par y MEDIO diente con z impar: 12° en Z15); si no, un eslabón
      queda estirado. «auto» gira sobre su eje el piñón que todavía no lleva otra cadena (B si
      está libre, si no A) lo justo para que engrane, y no toca nada si ya engrana: así un
      patrón de piñones iguales sale engranado rodillo a rodillo. «tal_cual» respeta el giro
      que les diste. Con los dos piñones ya cargados por otras cadenas, «auto» falla y dice
      cuánto girar uno.
    - `potencia_kw` + `rpm_a` activan la verificación de capacidad (tabla ACA de la ASA 40-1;
      la 08B la usa como sustituto DECLARADO; 10B/12B sin tabla publicada → no aplica).
      `servicio`: suave 1.0, moderado 1.3, fuerte 1.5 (motor eléctrico).
    - `detalle`: «eslabones» (rodillos, pernos y placas) o «simple» (sólo las bandas de placas a
      cada lado de los dientes: liviano). Lazos idénticos comparten la geometría (se teselan una
      vez)."""

    name: str = Field("Cadena", title="Nombre")
    cadena: str = Field(
        "CADENA-ASA40-1", title="Cadena",
        description="referencia del catálogo (CADENA-…): fija la norma, el paso y las hileras",
        json_schema_extra=lambda schema: schema.update({"enum": _chain_refs()}),
    )
    pinon_a: str = Field(..., title="Piñón motriz (A)", description="id de feature")
    pinon_b: str = Field(..., title="Piñón conducido (B)", description="id de feature")
    hilera_a: int = Field(
        1, ge=1, le=2, title="Hilera en A",
        description="1 o 2: en qué hilera de un piñón doble-simple corre esta cadena",
    )
    hilera_b: int = Field(
        1, ge=1, le=2, title="Hilera en B",
        description="1 o 2: en qué hilera de un piñón doble-simple corre esta cadena",
    )
    detalle: Literal["eslabones", "simple"] = Field(
        "eslabones", title="Detalle",
        description="eslabones = rodillos, pernos y placas; simple = sólo las bandas de placas",
    )
    eslabones: int | None = Field(
        None, ge=4, le=1000, title="Eslabones",
        description="número PAR que fija el largo; vacío = el menor par que alcanza (acepta "
                    "=expresión)",
    )
    fase: Literal["tal_cual", "auto"] = Field(
        "tal_cual", title="Fase de los dientes",
        description="auto = gira el piñón libre lo justo para que la cadena engrane; tal_cual = "
                    "respeta el giro de los piñones",
    )
    potencia_kw: float | None = Field(
        None, gt=0, le=1000, title="Potencia transmitida",
        description="kW; acepta =expresión; con rpm_a se verifica la capacidad de la cadena",
    )
    rpm_a: float | None = Field(
        None, gt=0, le=20000, title="rpm del piñón motriz",
        description="rpm de A; acepta =expresión; da la velocidad de la cadena",
    )
    servicio: Literal["suave", "moderado", "fuerte"] = Field(
        "moderado", title="Tipo de servicio",
        description="factor de servicio con motor eléctrico: suave 1.0, moderado 1.3, fuerte 1.5",
    )

    @field_validator("cadena")
    @classmethod
    def _known_chain(cls, v: str) -> str:
        refs = _chain_refs()
        if v not in refs:
            raise ValueError(f"cadena desconocida '{v}'; usa una de {', '.join(refs)}")
        return v
