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
    from apolo.library.rodillos_cadena import MOTOR_AUTO, MOTORES

    return [MOTOR_AUTO, *MOTORES]


def _anclajes() -> list[str]:
    from apolo.library.rodillos_cadena_pies import ANCLAJE_AUTO, anclajes

    return [ANCLAJE_AUTO, *anclajes()]


class CreateRollerConveyorParams(BaseModel):
    """Transportador de rodillos MOTORIZADO POR CADENA rodillo a rodillo, completo, fabricable y
    sostenido, en UNA orden (super-comando): 2 largueros de ángulo L 75x6 (ala horizontal ABAJO y
    hacia AFUERA), rodillos de tubo sobre eje HEXAGONAL calzado en una ranura abierta hacia
    arriba del ala (el rodillo sale levantándolo) con 6202-HEX11 en cada tapa, piñón doble-simple
    ASA 40 Z15 por rodillo y cadenas 1:1 alternando hileras, motorreductor bajo el último rodillo
    con su cadena motriz, patas de tubo 2x2 en H con pie nivelador (y anclajes con `anclaje`),
    guarda de cadenas con peine y tapas extremas, guarda de la transmisión CERRADA (cárter que
    corre con el motor + guarda fija) y bandeja inferior atornillada. Todas las uniones van
    declaradas y las piezas en el grupo `name` (subgrupos Bastidor, Rodillos, Cadenas, Patas,
    Motorreductor, Guardas).

    CÓMO MONTAR (IMPORTANTE):
    - Transporte a lo largo de +X: la alimentación en x = position.x y la motriz en x =
      position.x + largo; el centro de los tubos en y = position.y, la transmisión hacia +Y;
      position.z es el piso. Para moverlo, transform_group sobre `name` (no lleva rotation).
    - `altura` = cara superior de los rodillos, con los pies a la mitad de su recorrido.
    - Pies: la familia sale de (masa + carga_kg) / patas × 1.5; cada vástago con contratuerca.
      `anclaje: true` = la base del pie atornillada al concreto con 2 anclajes M12, sin soldar;
      `false` = disco directo al piso. Con calza o mortero bajo la base en obra, dalo en
      `calza_mm`: `anclaje_ref: auto` elige el M12 cuyo tfix fija base + calza.
    - `paso`: con cadena sólo 95.25, 107.95 o 120.65 mm (1:1 sin sobrante); libre, de Ø + 20 a
      300 mm. Los rodillos (par) salen de `largo` y quedan centrados.
    - `ancho_util` = largo del tubo. `motor: auto` (el de todo comando nuevo) = sinfín NMRV con el
      motor a lo largo (cabe desde 400 de ancho), el más chico que da la potencia de `carga_kg` a
      la tensión `red_v` y cuya cadena aguanta su par nominal (FS ≥ 1.2, piñón ≥ Z17); si ninguno,
      el error dice qué falta. Con un `motor` explícito, la plantilla no lo cambia.
    - `union: empernado` = patas atornilladas al ala del larguero y travesaños a las patas.
    - La cadena motriz va inclinada 20° y se TENSA sobre su línea de centros (portamotor sobre
      orejas ranuradas, con tornillo tensor): corre el 3 % del largo de la cadena y 3 mm para el
      eslabón de unión. Eslabones y centros salen solos.
    - `velocidad_m_s` = la del PRODUCTO (± 10 %); sin ella, la de siempre (0.266 m/s).
    - Estaciones de patas con el mismo voladizo en los extremos e intermedias para un vano ≤
      1.8 m (flecha L/240 con `carga_kg`, la carga TOTAL; con cadena también dimensiona el motor).
    - `motriz: libre` = rodillos locos: sin piñones, cadenas, motor ni guardas.
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
        "MOTOR-037", title="Motorreductor",
        description="auto (lo pone el sello) = el sinfín más chico que da la cuenta a red_v",
        json_schema_extra=lambda schema: schema.update({"enum": _motores()}),
    )
    red_v: float = Field(220, ge=100, le=1000, title="Tensión de la red",
                         description="V entre fases (Lima 220): con motor auto")
    union: Literal["soldado", "empernado"] = Field(
        "soldado", title="Bastidor",
        description="empernado = largueros, patas y travesaños con pernos (se desarma)")
    velocidad_m_s: float | None = Field(
        None, gt=0, le=3, title="Velocidad",
        description="m/s del producto (opcional): elige el piñón del motor; vacío = piñón Z30",
    )
    anclaje: bool = Field(
        True, title="Anclaje al piso",
        description="true = cada pie nivelador anclado al concreto con 2 anclajes de expansión; "
                    "false = el disco del pie apoya directo en el piso",
    )
    # Default «auto» / 0 = el anclaje de siempre (ANCLA-EXP-M12): un log sin estos campos
    # regenera idéntico (`rodillos_cadena_pies.elegir_anclaje`).
    anclaje_ref: str = Field(
        "auto", title="Anclaje",
        description="auto = el M12 más corto cuyo tfix cubre la base del pie + calza_mm; o una "
                    "ref de anclaje (error si su tfix no alcanza). Con anclaje: true",
        json_schema_extra=lambda schema: schema.update({"enum": _anclajes()}),
    )
    calza_mm: float = Field(
        0, ge=0, le=100, title="Calza bajo la base",
        description="mm de calza o mortero de nivelación que irá bajo la base de los pies en "
                    "obra (no se modela; la ETA del anclaje la cuenta en el espesor a fijar): el "
                    "anclaje auto la fija junto con la base. Con anclaje: true",
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
    # F9, también FUERA del schema: tornillo empujador en el portamotor, cárter atornillado a la
    # base, tapas extremas de la guarda de cadenas y el largo de toda unión perno (E15–E18). El
    # sello lo pone con `taller`; un log v4 no lo trae → False → igual.
    mantenimiento: SkipJsonSchema[bool] = Field(False)
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

    @field_validator("anclaje_ref")
    @classmethod
    def _anclaje_conocido(cls, v: str) -> str:
        if v not in _anclajes():
            raise ValueError(f"anclaje_ref '{v}': usa uno de {', '.join(_anclajes())}")
        return v
