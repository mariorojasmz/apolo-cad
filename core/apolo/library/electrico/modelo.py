"""El modelo eléctrico EVALUADO: dispositivos con sus bornes, conductores, cables (V8.1 D2, D5)
y los programas de los PLC (V8.3 D3).

Es lo que el carril eléctrico del documento deja en `doc.electrico` (F3) y lo que lee el ERC:
datos puros e inmutables, sin referencias al documento ni a la geometría. Un dispositivo trae
COPIADO lo que dice su ficha de catálogo (bornes, caminos internos, cargas, fuentes, modelo),
así el ERC no consulta el catálogo.

Vocabulario (ficha de catálogo, `ficha.py`):
  - `Borne`: punto de conexión del aparato, con su ROL (potencia, mando, bobina, contacto,
    tierra, señal) y su lado (línea/carga) opcional.
  - `Camino`: unión INTERNA entre dos bornes. `fijo` (borne pasante, puente interno), `NA`/`NC`
    (contacto movido por la bobina, la mano, el disparo, un acople o una señal) o `proteccion`
    (el polo de un ITM o de un guardamotor).
  - `Carga`: bornes entre los que el aparato CONSUME, con su tensión nominal (bobina A1–A2,
    motor U1/V1/W1, entrada de una fuente o de un PLC).
  - `Fuente`: bornes a los que el aparato IMPONE un potencial (la red, la salida de 24 VDC, la
    salida del variador).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .tension import Tension


@dataclass(frozen=True)
class Borne:
    id: str
    rol: str
    lado: str | None = None
    obligatorio: bool = False


@dataclass(frozen=True)
class Camino:
    de: str
    a: str
    tipo: str  # fijo | NA | NC | proteccion
    accion: str | None = None  # bobina | mano | disparo | acople | señal
    grupo: str | None = None  # actuador: NA y NC del mismo grupo nunca cierran a la vez

    @property
    def actuador(self) -> str:
        """Clave del actuador que mueve el camino (`grupo`, o la acción si no se nombra)."""
        return self.grupo or self.accion or self.tipo


@dataclass(frozen=True)
class Carga:
    bornes: tuple[str, ...]
    tension: Tension
    tipo: str = "otra"  # bobina | motor | alimentacion | entrada | piloto | otra
    obligatoria: bool = True
    polar: bool = False


@dataclass(frozen=True)
class Fuente:
    polos: tuple[tuple[str, str], ...]  # (borne, polo)
    tension: Tension

    def polo_de(self, borne: str) -> str | None:
        return next((p for b, p in self.polos if b == borne), None)


@dataclass(frozen=True)
class Hilo:
    id: str
    color: str | None = None


@dataclass(frozen=True)
class Dispositivo:
    """Una instancia de catálogo en el tablero o en campo. `designacion` es la de IEC 81346
    COMPLETA («-K1», o «=Faja1-K1» si `insert_project` le puso el aspecto de función);
    `ubicacion` el aspecto de lugar («+TAB1»); `funcion` la letra IEC 81346-2 de su ficha."""

    designacion: str
    ref: str
    funcion: str
    bornes: tuple[Borne, ...]
    caminos: tuple[Camino, ...] = ()
    cargas: tuple[Carga, ...] = ()
    fuentes: tuple[Fuente, ...] = ()
    ubicacion: str = ""
    ajustes: dict = field(default_factory=dict)
    pieza: str | None = None
    modelo: dict = field(default_factory=dict)
    protege_motor: bool = False
    parada_emergencia: bool = False
    bornera: bool = False
    id: str | None = None  # comando que lo declaró (trazabilidad)
    cantidad: int = 1  # unidades de una bornera (la BOM compra un borne por unidad)
    #: ajustes que no declaró el `add_device` y salieron de la pieza ligada (V8.3 F6), con su
    #: origen: {clave: «del nombre de la pieza c682 (…)»}. Ya están en `ajustes`.
    deducidos: dict = field(default_factory=dict)

    def borne(self, borne_id: str) -> Borne | None:
        return next((b for b in self.bornes if b.id == borne_id), None)

    @property
    def ids_bornes(self) -> tuple[str, ...]:
        return tuple(b.id for b in self.bornes)


@dataclass(frozen=True)
class Conductor:
    """Un conductor que une ≥ 2 puntos «-Q1:2», en ese orden (el orden de cableado). Dentro de
    un cable multipolar lleva `cable` («-W1») e `hilo` («1», «PE»)."""

    puntos: tuple[str, ...]
    seccion_mm2: float | None = None
    color: str | None = None
    tipo: str | None = None  # ref de conductor del catálogo o «puente»
    cable: str | None = None
    hilo: str | None = None
    potencial: str | None = None  # nombre declarado («L1», «24V»)
    id: str | None = None
    largo_m: float | None = None  # declarado (el ruteo real es de V8.5): la BOM compra por metro

    @property
    def etiqueta(self) -> str:
        return " → ".join(self.puntos)


@dataclass(frozen=True)
class Cable:
    designacion: str
    ref: str
    hilos: tuple[Hilo, ...] = ()
    seccion_mm2: float | None = None
    desde: str | None = None
    hasta: str | None = None
    largo_m: float | None = None
    id: str | None = None

    def hilo(self, hilo_id: str) -> Hilo | None:
        return next((h for h in self.hilos if h.id == hilo_id), None)


@dataclass(frozen=True)
class Programa:
    """El programa de un PLC (`add_program`, V8.3 D3), ya COMPILADO contra los bornes de su
    ficha. `compilado` es el `apolo.plc.Compilado` (picklable; fuera de la igualdad: la fuente
    y los ajustes lo determinan); `tags` = la tabla de direcciones IEC que sale del programa
    (D4: variable, dirección, borne, tipo, sentido)."""

    plc: str
    nombre: str
    fuente: str
    lenguaje: str = "st"
    ciclo_ms: int = 10
    ciclos: dict = field(default_factory=dict)  # PROGRAM → ciclo propio (tareas)
    tags: tuple = ()
    id: str | None = None
    compilado: object = field(default=None, compare=False, repr=False)


@dataclass(frozen=True)
class ModeloElectrico:
    dispositivos: tuple[Dispositivo, ...] = ()
    conductores: tuple[Conductor, ...] = ()
    cables: tuple[Cable, ...] = ()
    programas: tuple[Programa, ...] = ()


@dataclass(frozen=True)
class Red:
    """Un nodo eléctrico: puntos unidos por conductores y caminos `fijo`. `potenciales` son los
    que puede recibir en el PEOR caso (todo contacto y protección cerrados); `directos`, los que
    tiene sin cerrar nada. `tension` es la inferida, legible («-G1:L1 · 220 VAC 3F 60 Hz»)."""

    id: str
    puntos: tuple[str, ...]
    potenciales: tuple[str, ...] = ()
    directos: tuple[str, ...] = ()
    tension: str | None = None
    nombre: str | None = None
    conductores: tuple[int, ...] = ()


def expandir_bornera(bornes: tuple[Borne, ...], caminos: tuple[Camino, ...],
                     cantidad: int) -> tuple[tuple[Borne, ...], tuple[Camino, ...]]:
    """Una bornera declara en su ficha los bornes de UNA unidad; `cantidad` los repite. Unidad k
    de un solo punto → borne «k»; de varios → «k.<id>» (el portafusible: «1.1», «1.2»)."""
    if cantidad < 1:
        raise ValueError(f"cantidad de bornes inválida: {cantidad} (mínimo 1)")
    simple = len(bornes) == 1

    def nombre(k: int, borne_id: str) -> str:
        return str(k) if simple else f"{k}.{borne_id}"

    nuevos_b: list[Borne] = []
    nuevos_c: list[Camino] = []
    for k in range(1, cantidad + 1):
        nuevos_b += [Borne(nombre(k, b.id), b.rol, b.lado, b.obligatorio) for b in bornes]
        nuevos_c += [Camino(nombre(k, c.de), nombre(k, c.a), c.tipo, c.accion,
                            f"{k}.{c.actuador}" if c.tipo in ("NA", "NC") else c.grupo)
                     for c in caminos]
    return tuple(nuevos_b), tuple(nuevos_c)


def dispositivo_desde_ficha(designacion: str, ref: str, ficha, *, ubicacion: str = "",
                            ajustes: dict | None = None, pieza: str | None = None,
                            cantidad: int | None = None, id: str | None = None,
                            deducidos: dict | None = None) -> Dispositivo:
    """Instancia un `Dispositivo` desde la ficha de catálogo (`FichaElectrica`). La ficha llega
    como argumento: este módulo no importa el catálogo (que arrastra la geometría)."""
    bornes, caminos = ficha.bornes, ficha.caminos
    if ficha.bornera:
        bornes, caminos = expandir_bornera(bornes, caminos, int(cantidad or 1))
    elif cantidad not in (None, 1):
        raise ValueError(f"{designacion} ({ref}): `cantidad` sólo vale en una bornera")
    return Dispositivo(
        designacion=designacion, ref=ref, funcion=ficha.funcion, bornes=bornes, caminos=caminos,
        cargas=() if ficha.bornera else ficha.cargas, fuentes=() if ficha.bornera else ficha.fuentes,
        ubicacion=ubicacion or "", ajustes=dict(ajustes or {}), pieza=pieza,
        modelo=dict(ficha.modelo), protege_motor=ficha.protege_motor,
        parada_emergencia=ficha.parada_emergencia, bornera=ficha.bornera, id=id,
        cantidad=int(cantidad or 1) if ficha.bornera else 1, deducidos=dict(deducidos or {}),
    )
