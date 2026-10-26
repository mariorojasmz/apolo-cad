"""Schemas del circuito de AIRE en el carril (plan V8.9 D1, F1b): `add_tubo` y el `servicio` de
un cilindro (`add_device.servicio`).

Son del MISMO carril que lo eléctrico (`kind="electrico"`, `doc/carril.py`): una numeración
IEC 81346 para la máquina, un solo `get_circuit` y un ERC que cruza los dos lados (la bobina de
la válvula contra la salida del PLC). Aquí sólo va la FORMA: lo que se rechaza sin mirar el
resto del circuito (una referencia mal escrita, un extremo sin puerto). Qué significa cada uno
(qué puerto existe, qué ref es tubo) lo resuelve el evaluador (`neumatica_eval.py`).
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from apolo.library.electrico.referencias import ReferenciaError, parse_referencia


def _refs_tubo() -> list[str]:
    from apolo.library.catalog import CATALOG

    return [r for r, c in CATALOG.items() if c.neumatico is not None and c.neumatico.tubo is not None]


class ServicioCilindro(BaseModel):
    """Lo que el cilindro tiene que HACER en la máquina (V8.9 F1b): con esto el ERC neumático
    revisa el pandeo del vástago, la energía al fin de carrera y si el caudal de su válvula
    alcanza la velocidad pedida. Sólo en un cilindro."""

    carrera_mm: float = Field(..., gt=0, le=5000, title="Carrera",
                              description="mm, dentro del rango de la ficha (acepta =expr)")
    velocidad_m_s: float | None = Field(
        None, gt=0, le=10, title="Velocidad de régimen",
        description="m/s del vástago en RÉGIMEN, la que el ciclo necesita (≈ carrera / tiempo de avance), "
                    "NO el pico transitorio de un escenario: el ERC la compara con la cota de régimen del "
                    "escape y la memoria toma el pico de la co-simulación por su cuenta (sin ella no se "
                    "revisan caudal ni impacto)")
    masa_kg: float | None = Field(None, ge=0, le=10000, title="Masa movida",
                                  description="kg de la carga que arrastra el vástago (además de la suya)")
    fuerza_N: float | None = Field(None, ge=0, le=1e6, title="Fuerza a vencer",
                                   description="N de la carga (informativo; el pandeo usa la teórica)")
    caso_euler: int | None = Field(None, ge=1, le=4, title="Caso de Euler",
                                   description="montaje: 1 empotrado-libre, 2 articulado, 3, 4 empotrado")
    largo_libre_mm: float | None = Field(None, gt=0, le=10000, title="Largo libre",
                                         description="mm del vástago como columna; vacío = la carrera")
    ciclos_min: float | None = Field(None, gt=0, le=600, title="Cadencia",
                                     description="ciclos dobles por minuto: el consumo por minuto y la "
                                                 "demanda de aire de la memoria")
    amortiguador_avance: str | None = Field(
        None, max_length=60, title="Amortiguador externo al avance",
        description="ref de catálogo (AMORT-HID-…) del amortiguador hidráulico que frena la carga al FINAL "
                    "del avance (vástago afuera): ese extremo se revisa con la energía de SU ficha (por ciclo "
                    "y por hora) en vez de la amortiguación del cilindro. Vacío = la del cilindro")
    amortiguador_retroceso: str | None = Field(
        None, max_length=60, title="Amortiguador externo al retroceso",
        description="ref del amortiguador que frena la carga al final del retroceso (vástago adentro); "
                    "vacío = la amortiguación del cilindro")


class AddTuboParams(BaseModel):
    """Une dos PUERTOS de aire con un tubo de catálogo: «-QM1:4» → «-MM1:A» (V8.9 D1). Es del
    mismo carril que el cableado eléctrico: no crea geometría y no re-ejecuta la escena.

    - `desde` / `hasta`: puertos `[=función][+ubicación]-dispositivo:puerto`. Las vías de una
      válvula son las de ISO 5599-3 (1 alimentación, 2 y 4 trabajo, 3 y 5 escape); el cilindro
      tiene A (fondo) y B (vástago); el FRL 1 (entrada) y 2 (salida). Los puertos de cada ref
      están en get_catalog → campo `neumatico.puertos`. Un tubo a un borne eléctrico (A1, A2)
      es error: los bornes se cablean con add_wire.
    - `ref`: el tubo del catálogo (TUBO-PU-4, -6, -8, -10: Ø exterior × interior en su ficha).
    - `largo_m`: opcional y DECLARADO: la BOM compra el tubo por metro con él; sin largo, la fila
      sale «sin largo» y sin costo (no se inventa). La BOM suma sola un RACOR recto macho por cada
      extremo en un puerto roscado (rosca × Ø del tubo).
    - Un SILENCIADOR (SIL-G18…) va roscado al escape: únelo con add_tubo SIN largo («-QM2:3» →
      «-RZ1:1»), que la BOM lee como roscado directo (ni tubo ni racor). Un regulador de caudal en
      línea (REG-CAUDAL-L-6…) va entre dos tubos con su puerto 2 hacia el cilindro (regula el escape).
    Revisa el circuito de aire con electrical_check (sección neumática) y míralo con get_circuit."""

    desde: str = Field(..., max_length=60, title="Desde", description="puerto, p. ej. «-QM1:4»")
    hasta: str = Field(..., max_length=60, title="Hasta", description="puerto, p. ej. «-MM1:A»")
    ref: str = Field(
        ..., title="Tubo",
        json_schema_extra=lambda schema: schema.update({"enum": _refs_tubo()}),
    )
    largo_m: float | None = Field(None, gt=0, le=10000, title="Largo",
                                  description="m, declarado (la BOM compra por metro)")

    @field_validator("desde", "hasta")
    @classmethod
    def _puerto(cls, v: str) -> str:
        try:
            parse_referencia(v, exige_borne=True)
        except ReferenciaError as exc:
            raise ValueError(str(exc).replace("borne", "puerto").replace("«-K1:A1»", "«-QM1:4»")) from None
        return v.strip()
