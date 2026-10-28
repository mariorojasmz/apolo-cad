"""Schema de `create_roller_conveyor` (plan `plantilla-rodillos-cadena`, D1). Las listas de
catálogo y la regla del paso salen de `apolo/library/rodillos_cadena.py`; el executor está en
`exec_rodillos_cadena.py` y la receta de comandos, en `receta_rodillos_cadena.py`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from .models import Vec3


def _rodillos() -> list[str]:
    from apolo.library.rodillos_cadena import RODILLOS

    return list(RODILLOS)


def _motores() -> list[str]:
    from apolo.library.rodillos_cadena import MOTORES

    return list(MOTORES)


class CreateRollerConveyorParams(BaseModel):
    """Transportador de rodillos MOTORIZADO POR CADENA rodillo a rodillo, completo, fabricable y
    sostenido, en UNA orden (super-comando): bastidor de 2 largueros de ángulo L 75x6 (ala
    vertical por dentro, ala horizontal ABAJO y hacia AFUERA), rodillos de tubo redondo sobre
    eje fijo HEXAGONAL 11 (barra EN 10278, extremos con doble plano) CALZADO en una ranura
    abierta hacia arriba en el ala vertical de cada larguero (no gira ni corre: el rodillo se saca
    levantándolo, sin tocar una tuerca), con un rodamiento 6202-HEX11 de compra en el alojamiento
    de cada tapa y un separador sobre el eje que deja el juego axial del rodillo en 0.5 mm por lado,
    piñón doble-simple ASA 40 Z15 soldado a un buje en cada rodillo, cadenas ASA 40 1:1
    alternando las dos hileras, motorreductor bajo el último rodillo con su piñón y cadena
    motriz, patas de tubo 2x2 en H (travesaño ENTRE las patas) con pie nivelador de catálogo
    (tuerca soldada bajo la placa de la pata; con `anclaje`, base del pie con 2 anclajes y
    `ground`), guarda de cadenas sobre separadores soldados, guarda de la transmisión CERRADA
    (cárter que corre con el motor + guarda fija atornillada al larguero, ISO 14120) y bandeja
    inferior de cadenas en tramos atornillados. Todas las uniones van declaradas (`fasten` en
    conjuntos) y las piezas quedan en el grupo `name` con sus subgrupos Bastidor, Rodillos,
    Cadenas, Patas, Motorreductor y Guardas.

    CÓMO MONTAR (IMPORTANTE):
    - Transporte a lo largo de +X: la alimentación en x = position.x y la motriz (motor) en
      x = position.x + largo. El centro de los tubos en y = position.y; la transmisión va hacia
      +Y. position.z es el piso (las bases o los discos de los pies apoyan en z = position.z). Para girarlo o moverlo después, transform_group sobre el grupo
      `name`; no lleva rotation.
    - `altura` = cara superior de los rodillos (altura de trabajo), con los pies niveladores a
      la mitad de su recorrido. El eje queda a altura − Ø/2.
    - Pies niveladores: la familia sale de la carga por pata ((masa + carga_kg) / patas × 1.5
      contra la carga del pie); engineering_check publica la carga por pie y el recorrido de
      nivelación (±). Cada vástago lleva su contratuerca (traba la altura nivelada).
      `anclaje: true` (default) = la BASE del pie atornillada al concreto con 2 anclajes de
      expansión M12 de compra, por FUERA de la placa de la pata (entran el taladro y el dado),
      sin soldar: se re-nivela con la contratuerca suelta, sin tocar el anclaje; `false` = disco
      directo al piso.
    - `paso`: con `motriz: cadena` NO es libre: con cadena 1:1 sólo cierran sin sobrante 95.25,
      107.95 o 120.65 mm (30, 32 o 34 eslabones). Con `motriz: libre` va de Ø del tubo + 20 mm
      (luz entre tubos) a 300 mm (TUBOR-2: 70.8–300). El número de rodillos sale de `largo`
      (par, ≥ 50 mm del eje extremo al final del larguero) y los rodillos quedan centrados.
    - `ancho_util` = largo del tubo (lo que ve el producto). Con `motriz: cadena` el motor va
      entre las patas, bajo los rodillos: si no cabe, el error dice el ancho mínimo.
    - La cadena motriz va inclinada 20° hacia la alimentación y se TENSA sobre su línea de
      centros: el travesaño portamotor (con base, motor y cárter) va atornillado a las patas por
      orejas de ranuras paralelas a esa línea; corre lo que pide el estirado de reemplazo (3 %
      del largo de la cadena) y 3 mm hacia adentro para montar el eslabón de unión. Sus
      eslabones y centros salen solos (centros exactos, nunca una cota a mano).
    - `velocidad_m_s` (opcional) = velocidad del PRODUCTO: elige el piñón del motor (ASA 40
      simple del catálogo) que la da dentro de ±10 %; si ninguno, el error dice las velocidades
      que salen con ese motor y qué motor + piñón da la pedida. Sin ella, piñón Z30. El motor
      sigue siendo el que diga `motor`.
    - Todas las estaciones llevan el travesaño a la misma altura (la del portamotor; a media
      pata con `motriz: libre`).
    - Las estaciones de patas quedan con el mismo voladizo en los dos extremos y se agregan
      intermedias para que el vano del larguero (ángulo libre, flecha L/240 con `carga_kg`
      repartida) no pase de 1.8 m. `carga_kg` es la carga TOTAL sobre el transportador; con
      cadena también verifica que el motor alcance (rodadura, rendimiento de los lazos).
    - `motriz: libre` = rodillos locos (gravedad o empuje a mano): sin piñones, cadenas, motor
      ni guardas; el bastidor queda simétrico.
    - Las piezas tienen id `{id del comando}_{rol}` (p. ej. c5_larg_p = larguero +Y, c5_trav_e0
      = travesaño de la alimentación, c5_motor): úsalos para unir lo que agregues después.
    Editar cualquier parámetro regenera la máquina entera; para atarla a variables, da los
    params como =expresión."""

    name: str = Field(
        "Transportador de rodillos", pattern=r"^[^\s,][^,]*$", max_length=40, title="Nombre",
        description="nombre de la máquina y de su grupo (único en el proyecto, sin comas)",
    )
    largo: float = Field(2000, ge=1000, le=12000, title="Largo", description="mm, largo del bastidor")
    ancho_util: float = Field(
        500, ge=150, le=1500, title="Ancho útil", description="mm, largo del tubo de rodillo",
    )
    paso: float = Field(
        95.25, title="Paso de rodillos",
        description="mm entre ejes. Con cadena: 95.25, 107.95 o 120.65 (cadena 1:1 sin "
                    "sobrante). Libre: de Ø del tubo + 20 mm a 300 mm",
    )
    rodillo: str = Field(
        "TUBOR-2", title="Tubo del rodillo",
        json_schema_extra=lambda schema: schema.update({"enum": _rodillos()}),
    )
    altura: float = Field(
        750, gt=0, le=2500, title="Altura de trabajo", description="mm, cara superior de rodillos",
    )
    carga_kg: float = Field(
        100, gt=0, le=5000, title="Carga", description="kg sobre todo el transportador, repartidos",
    )
    motriz: Literal["cadena", "libre"] = Field(
        "cadena", title="Transmisión",
        description="cadena = motorizado rodillo a rodillo; libre = rodillos locos",
    )
    motor: str = Field(
        "MOTOR-037", title="Motorreductor", description="sólo con transmisión por cadena",
        json_schema_extra=lambda schema: schema.update({"enum": _motores()}),
    )
    velocidad_m_s: float | None = Field(
        None, gt=0, le=3, title="Velocidad",
        description="m/s del producto (opcional): elige el piñón del motor; vacío = piñón Z30",
    )
    anclaje: bool = Field(
        True, title="Anclaje al piso",
        description="true = cada pie nivelador anclado al concreto con 2 anclajes de expansión; "
                    "false = el disco del pie apoya directo en el piso",
    )
    # F6, FUERA del schema (criterio de Apolo, no del modelador): eje trabado entre dos tuercas
    # con separadores, 6201 de compra en el alojamiento de la tapa, contratuerca del pie y
    # anclajes de compra por fuera de la placa de la pata. Lo pone el sello de entrada
    # (`exec_rodillos_cadena.sellar`) a todo comando NUEVO; un log v3 no lo trae → False → igual.
    taller: SkipJsonSchema[bool] = Field(False)
    # F7, también FUERA del schema: «hexagonal» = barra hexagonal calzada en ranuras abiertas
    # hacia arriba del ala (sale levantándola), sobre 6202 de agujero hexagonal; «roscado» = el
    # M12 trabado de F6. El sello la pone en «hexagonal» junto con `taller`; un log F6 no la
    # trae → «roscado» → igual.
    eje: SkipJsonSchema[Literal["roscado", "hexagonal"]] = Field("roscado")
    # F8, también FUERA del schema: «base» = con `anclaje`, pie nivelador con base de anclaje
    # atornillada al concreto por sus 2 agujeros (sin placa de piso ni soldadura al pie zincado);
    # «disco» = el disco del pie soldado a una placa de piso anclada (F5–F7). El sello la pone en
    # «base» junto con `taller`; un log F6/F7 no la trae → «disco» → igual.
    pie: SkipJsonSchema[Literal["disco", "base"]] = Field("disco")
    position: Vec3 = Field(default_factory=Vec3, title="Posición")

    @model_validator(mode="after")
    def _paso_segun_motriz(self):
        """Con cadena, el paso de la lista (se ajusta al exacto); libre, dentro del rango del
        tubo. Corre después de validar `rodillo` (si no, ni llega)."""
        from apolo.library.rodillos_cadena import validar_paso

        self.paso = validar_paso(self.paso, self.rodillo, self.motriz == "cadena")
        return self

    @field_validator("rodillo")
    @classmethod
    def _rodillo_conocido(cls, v: str) -> str:
        if v not in _rodillos():
            raise ValueError(f"rodillo '{v}': usa uno de {', '.join(_rodillos())}")
        return v

    @field_validator("motor")
    @classmethod
    def _motor_conocido(cls, v: str) -> str:
        if v not in _motores():
            raise ValueError(f"motor '{v}': usa uno de {', '.join(_motores())}")
        return v
