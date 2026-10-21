"""Schemas de los comandos del tablero eléctrico (plan V8.1, D2): `add_device`, `add_wire`,
`add_cable`, y el programa del PLC (plan V8.3, D3): `add_program`.

Son comandos del CARRIL (`kind="electrico"`, `doc/carril.py`): viven en el log pero fuera de la
firma encadenada y no crean geometría; el cuerpo 3D del tablero es de V8.5. Lo que cada uno
SIGNIFICA (resolver refs, bornes y piezas) lo hace el evaluador del carril
(`electrico_eval.py`) contra la escena y las variables finales. Aquí sólo va la forma: lo que se
puede rechazar sin mirar el resto del tablero (una referencia mal escrita, un color que no es
IEC 60757). Salen de `models.py` (congelado por el trinquete de tamaño), como
`models_rodillos.py`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from apolo.library.electrico.ficha import COLORES
from apolo.library.electrico.referencias import (
    ReferenciaError,
    parse_designacion,
    parse_referencia,
    sufijo_sugerencia,
)

_UBICACION = r"^\+?[A-Za-z0-9_.]*$"


def _refs_dispositivo() -> list[str]:
    from apolo.library.catalog import CATALOG

    return [r for r, c in CATALOG.items() if c.electrico is not None and c.electrico.conductor is None]


def _refs_cable() -> list[str]:
    from apolo.library.catalog import CATALOG

    return [r for r, c in CATALOG.items()
            if c.electrico is not None and c.electrico.conductor is not None
            and c.electrico.conductor.hilos]


def _designacion(v: str) -> str:
    v = (v or "").strip()
    if v:
        try:
            parse_designacion(v)
        except ReferenciaError as exc:
            raise ValueError(str(exc)) from None
    return v


def _color(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    v = str(v).strip().upper()
    if v not in COLORES:
        raise ValueError(f"«{v}» no es un color IEC 60757; colores: {', '.join(COLORES)}."
                         f"{sufijo_sugerencia(v, COLORES)}")
    return v


class AddDeviceParams(BaseModel):
    """Declara un DISPOSITIVO del tablero o de campo (contactor, guardamotor, ITM, fuente, PLC,
    pulsador, seta, sensor, motor, bornera, la RED de suministro…): una ref del catálogo
    eléctrico con su designación IEC 81346. No crea geometría (el cuerpo 3D del tablero es de
    V8.5): sus bornes quedan disponibles para `add_wire`.

    - `ref`: del catálogo eléctrico. Los bornes, caminos internos y tensiones de cada ref salen
      en get_catalog(category=…) → campo `electrico` (categorías alimentacion_electrica,
      proteccion_electrica, maniobra_control, mandos, sensores, conexion_electrica,
      motorreductores, motorreductores_sinfin, variadores, tableros).
    - `designacion`: «-Q1», «-K1», «-M1»… con la letra IEC 81346-2 de su ficha (el contactor y
      el guardamotor son Q; el relé y el PLC, K; el ITM, F; la fuente y el variador, T). VACÍA =
      la siguiente libre de su letra, que se escribe en el comando al ejecutarlo (léela con
      get_circuit o get_command). Nunca se renumera: borrar -Q1 no renombra -Q2.
    - `ubicacion`: el lugar, «+TAB1» (tablero), «+CAMPO», «+PUPITRE»…
    - `pieza`: opcional, LIGA el dispositivo a un sólido que ya existe (su id, o el command_id
      que lo creó: p. ej. el motorreductor de una create_belt_conveyor se encuentra por su
      ref). Un dispositivo ligado ya cuenta en la BOM por su pieza: no se duplica.
    - `ajustes`: lo que el instalador fija, validado contra el `modelo` de la ficha: el Ir del
      guardamotor dentro de su rango ({"Ir_A": 3.2}), la conexión del motor
      ({"conexion": "triangulo"}).
    - `cantidad`: sólo en una bornera: cuántos bornes (quedan «1»…«N»).
    La red de suministro también es un dispositivo (RED-3F-220V-60HZ, designación «-G1»): es la
    fuente de L1/L2/L3/PE y la BOM no la compra. Revisa con electrical_check."""

    ref: str = Field(
        ..., title="Referencia",
        json_schema_extra=lambda schema: schema.update({"enum": _refs_dispositivo()}),
    )
    designacion: str = Field(
        "", max_length=40, title="Designación",
        description="IEC 81346, p. ej. «-Q1»; vacía = la siguiente libre de su letra",
    )
    ubicacion: str = Field(
        "", max_length=30, pattern=_UBICACION, title="Ubicación",
        description="aspecto de lugar, p. ej. «+TAB1» o «+CAMPO»",
    )
    pieza: str | None = Field(
        None, title="Pieza",
        description="id del sólido (o command_id que lo creó) que ES este dispositivo",
    )
    ajustes: dict = Field(
        default_factory=dict, title="Ajustes",
        description='validados contra el modelo de la ficha: {"Ir_A": 3.2}, {"conexion": "triangulo"}',
    )
    cantidad: int | None = Field(
        None, ge=1, le=500, title="Cantidad de bornes",
        description="sólo en una bornera: cuántos bornes lleva",
    )

    _v_designacion = field_validator("designacion")(_designacion)

    @field_validator("ubicacion")
    @classmethod
    def _ubicacion(cls, v: str) -> str:
        v = (v or "").strip()
        return f"+{v}" if v and not v.startswith("+") else v


class AddWireParams(BaseModel):
    """Conecta dos o más BORNES con un conductor: «-Q1:2» → «-Q3:1». Con N puntos encadena en
    ese orden (es el orden de cableado) y todos quedan en la misma red. Un PUENTE entre bornes
    vecinos es un add_wire con `tipo: "puente"`.

    - `puntos`: referencias `[=función][+ubicación]-dispositivo:borne` («-K1:A1»;
      «=Faja1-Q1:2» para un dispositivo de un proyecto insertado). Los bornes de cada ref están
      en get_catalog → `electrico.bornes`.
    - `seccion_mm2`: acepta «=expr»; si falta, sale del `tipo` o del cable.
    - `color`: IEC 60757 (BK negro potencia, RD rojo mando AC, BU azul mando DC, LBU azul claro
      neutro, GNYE verde-amarillo SOLO tierra; también BN, OG, YE, GN, VT, GY, WH, PK, TQ).
    - `tipo`: conductor del catálogo (COND-H07VK-2.5…) o «puente».
    - `cable` + `hilo`: cuando el conductor va dentro de un cable multipolar declarado con
      add_cable (p. ej. cable «-W1», hilo «1» o «PE»): toma la sección y el color del hilo.
    - `potencial`: nombre opcional de la red («L1», «24V», «0V»).
    - `largo_m`: opcional y DECLARADO (el ruteo real es de V8.5): la BOM compra por metro; sin
      largo, la fila sale sin costo y con aviso (no se inventa)."""

    puntos: list[str] = Field(..., min_length=2, title="Puntos",
                              description="bornes a unir, en orden: [«-Q1:2», «-Q3:1»]")
    seccion_mm2: float | None = Field(None, gt=0, le=300, title="Sección",
                                      description="mm² (acepta =expr)")
    color: str | None = Field(None, title="Color", description="IEC 60757: BK, RD, BU, LBU, GNYE…")
    tipo: str | None = Field(None, title="Tipo de conductor",
                             description="ref de conductor del catálogo o «puente»")
    cable: str | None = Field(None, title="Cable", description="designación del cable, «-W1»")
    hilo: str | None = Field(None, title="Hilo", description="hilo del cable: «1», «2», «PE»…")
    potencial: str | None = Field(None, max_length=20, title="Potencial",
                                  description="nombre de la red: «L1», «24V»")
    largo_m: float | None = Field(None, gt=0, le=10000, title="Largo",
                                  description="m, declarado (la BOM compra por metro)")

    _v_color = field_validator("color")(_color)

    @field_validator("puntos")
    @classmethod
    def _puntos(cls, v: list[str]) -> list[str]:
        out = []
        for p in v:
            try:
                parse_referencia(p, exige_borne=True)
            except ReferenciaError as exc:
                raise ValueError(str(exc)) from None
            out.append(p.strip())
        return out

    @field_validator("cable")
    @classmethod
    def _cable(cls, v: str | None) -> str | None:
        return (_designacion(v) or None) if v is not None else None

    @model_validator(mode="after")
    def _cable_e_hilo(self) -> "AddWireParams":
        if bool(self.cable) != bool(self.hilo):
            raise ValueError("`cable` e `hilo` van juntos: el conductor va dentro del cable «-W1» "
                             "como su hilo «1» (o ninguno de los dos)")
        if self.cable and self.tipo:
            raise ValueError("un conductor dentro de un cable no lleva `tipo`: el cable ya es la "
                             "ref que se compra")
        return self


class AddCableParams(BaseModel):
    """Declara un CABLE MULTIPOLAR (4G2,5 al motor, 5G1 a la botonera…): lo que se compra, se
    rotula y se rutea. Sus hilos quedan disponibles para `add_wire` con `cable` + `hilo` (los
    ids y colores de los hilos salen en get_catalog → `electrico.conductor.hilos`).

    - `designacion`: «-W1»…; VACÍA = la siguiente libre (se escribe en el comando).
    - `ref`: cable del catálogo (CABLE-4G1.5, CABLE-5G1, CABLE-3X0.75…).
    - `desde` / `hasta`: ubicación («+TAB1») o dispositivo («-M1») de cada extremo.
    - `largo_m`: opcional y DECLARADO (el ruteo real es de V8.5): la BOM compra por metro; sin
      largo, la fila sale sin costo y con aviso.
    - `piezas`: opcional, LIGA el cable a los tramos que lo modelan en 3D (ids de sólido o el
      command_id que los creó). Un cable 3D no se fabrica: lo cobra su add_cable; uno que ningún
      add_cable cubre (ligado, o con los mismos hilos × sección en el nombre) no se cobra en
      ninguna parte y el ERC lo avisa."""

    designacion: str = Field("", max_length=40, title="Designación",
                             description="IEC 81346, p. ej. «-W1»; vacía = la siguiente libre")
    ref: str = Field(
        ..., title="Referencia",
        json_schema_extra=lambda schema: schema.update({"enum": _refs_cable()}),
    )
    desde: str | None = Field(None, max_length=40, title="Desde",
                              description="ubicación («+TAB1») o dispositivo («-Q1»)")
    hasta: str | None = Field(None, max_length=40, title="Hasta",
                              description="ubicación («+CAMPO») o dispositivo («-M1»)")
    largo_m: float | None = Field(None, gt=0, le=10000, title="Largo",
                                  description="m, declarado (la BOM compra por metro)")
    piezas: list[str] = Field(default_factory=list, max_length=200, title="Piezas 3D",
                              description="ids (o command_id) de los tramos 3D que modelan el cable")

    _v_designacion = field_validator("designacion")(_designacion)


class AddProgramParams(BaseModel):
    """Carga el PROGRAMA de un PLC del tablero (V8.3 D3): texto estructurado (ST, IEC 61131-3)
    que se COMPILA al ejecutar el comando contra los bornes de la ficha del PLC; un error de
    sintaxis o de tipos rechaza el comando con línea, columna y «¿quisiste decir…?».

    - `plc`: designación del PLC declarado con add_device («-K1»).
    - `nombre`: rótulo del programa; vacío = el del primer PROGRAM de la fuente.
    - `lenguaje`: «st» (la escalera y el SFC llegan como VISTAS en V8.4).
    - `fuente`: el ST. Entradas y salidas por dirección IEC ligada al borne del PLC:
      `VAR_GLOBAL marcha AT %IX0.2 : BOOL; motor AT %QX0.0 : BOOL; END_VAR` (%IX0.2 = borne
      I0.2, %QX0.0 = Q0.0, %IW1 = AI1 escalada 0–27648). Subconjunto: BOOL, INT, DINT, REAL,
      TIME, ARRAY; IF/CASE/FOR/WHILE/REPEAT; PROGRAM, FUNCTION, FUNCTION_BLOCK; TON, TOF, TP,
      CTU, CTD, CTUD, R_TRIG, F_TRIG, SR, RS; RETAIN.
    - `ciclo_ms`: ciclo de scan (10 ms por defecto); el watchdog es 3 × ciclo.
    - `ciclos`: {PROGRAM: ms} para tareas con ciclo propio (varios PROGRAM en la misma fuente).
    Un PLC lleva UN add_program. Pruébalo sin guardarlo con test_plc; sus variables se leen en
    las trazas como «-K1.Main.cuenta» (o «-K1.cuenta» si no es ambigua)."""

    plc: str = Field(..., max_length=40, title="PLC", description="designación del PLC, «-K1»")
    nombre: str = Field("", max_length=60, title="Nombre",
                        description="vacío = el del primer PROGRAM")
    lenguaje: Literal["st"] = Field("st", title="Lenguaje", description="texto estructurado")
    fuente: str = Field(..., min_length=1, max_length=200_000, title="Fuente",
                        description="el programa en ST (IEC 61131-3)")
    ciclo_ms: int = Field(10, ge=1, le=10_000, title="Ciclo", description="ms por scan")
    ciclos: dict[str, int] = Field(default_factory=dict, title="Ciclos por tarea",
                                   description="{PROGRAM: ms} para tareas con ciclo propio")

    @field_validator("plc")
    @classmethod
    def _plc(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("falta `plc`: la designación del PLC («-K1»)")
        return _designacion(v)

    @field_validator("ciclos")
    @classmethod
    def _ciclos(cls, v: dict) -> dict:
        malos = {k: ms for k, ms in v.items() if ms < 1}
        if malos:
            raise ValueError(f"cada ciclo es un entero ≥ 1 (ms): {malos}")
        return v
