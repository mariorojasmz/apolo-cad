"""El snapshot de una co-simulación: datos PUROS que viajan en pickle al worker (plan V8.3 D11).

Lo arma `services/cosim_snapshot.py` bajo `STATE_LOCK` desde el documento; aquí sólo están las
clases, sin OCCT ni el catálogo, para que el worker las des-serialice sin cargar la geometría:
  - `dinamica`: el `DynamicsSnapshot` de V8.2 (MJCF horneado, cuerpos, bandas, fotoceldas), con
    un motor POR PLACA por cada motor del tablero acoplado a su junta (D8);
  - `red`: el formato plano de `cosim/red/entrada.py`;
  - `dispositivos`: ref, `modelo` y `ajustes` de cada aparato (los modelos de F2 se arman en el
    worker);
  - `programas`: el ST ya compilado de cada PLC (`plc.Compilado` es picklable y se re-verifica);
  - los acoples motor ↔ actuador de MuJoCo y sensor ↔ rayo, y el escenario.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DispositivoCosim:
    designacion: str
    ref: str
    modelo: dict
    ajustes: dict
    cantidad: int = 1
    pieza: str | None = None     # la pieza 3D ligada (`add_device.pieza`): la tabla del vivo, V8.4
    color: str | None = None     # el color físico de su ficha (`specs.color`): mandos y pilotos


@dataclass(frozen=True)
class ProgramaCosim:
    plc: str                     # designación del PLC («-A1»)
    nombre: str
    compilado: object            # apolo.plc.Compilado
    ciclo_ms: int = 10
    ciclos: dict = field(default_factory=dict)  # PROGRAM → ciclo propio (tareas)


@dataclass(frozen=True)
class AcopleMotor:
    designacion: str             # «-M1»
    junta: str                   # junta Apolo que mueve
    actuador: str                # nombre MJCF del `<velocity>` («a0»)
    signo: float                 # +1/−1: el sentido de marcha (D7) en la junta


@dataclass(frozen=True)
class AcopleSensor:
    designacion: str             # «-B1»
    rayo: str                    # nombre de la fotocelda de V8.2


@dataclass(frozen=True)
class AcopleCilindro:
    """V8.9 D4/D8: el cilindro del tablero ↔ la junta prismática de su vástago."""
    designacion: str             # «-MM1»
    junta: str                   # «<cmd>_vastago»
    actuador: str                # nombre MJCF del `<motor>` que recibe la fuerza media


@dataclass(frozen=True)
class AcopleReed:
    """V8.9 D8: un `Sensor` del tablero que lee la posición de una junta (el detector magnético
    del cilindro): detecta mientras la junta está a ± `ventana_mm` de `en_mm`."""
    designacion: str
    junta: str
    en_mm: float
    ventana_mm: float


@dataclass
class CosimSnapshot:
    dinamica: object             # apolo.physics.dinamica_datos.DynamicsSnapshot
    red: dict
    dispositivos: list
    programas: list
    motores: list
    sensores: list
    escenario: object            # apolo.cosim.escenario.Escenario
    hipotesis: list = field(default_factory=list)
    avisos: list = field(default_factory=list)
    # Plan nucleo-abierto-extensiones-privadas (A4): los modelos de EXTENSIÓN que usa el tablero
    # ({tipo: clase}: pickle los importa por nombre en el worker, que los registra) y
    # {extensión: versión}, que el resultado guardado anota. Vacíos sin extensiones.
    modelos_extension: dict = field(default_factory=dict)
    extensiones: dict = field(default_factory=dict)
    # V8.9 F3: el circuito de aire ({presion_red_bar, tubos}: `services/cosim_aire.py`) y sus
    # acoples (cilindro ↔ junta, detector ↔ junta). Vacíos sin aire: la corrida de siempre.
    aire: dict = field(default_factory=dict)
    cilindros: list = field(default_factory=list)
    reeds: list = field(default_factory=list)
    # plc-en-el-lazo D6: los PLC de AFUERA que pidió la corrida ({designación: (clase del
    # conector, config)}; la clase viaja por pickle como `modelos_extension`). Vacío sin externo:
    # la corrida de siempre. Nunca sale del documento: lo elige el pedido.
    externos: dict = field(default_factory=dict)
    # D5 de cotizacion-identificada-y-ajustes-por-escenario: los ajustes de PRUEBA que el
    # escenario puso encima de los del proyecto ([{dispositivo, ajuste, valor, proyecto}]: ya
    # están en `dispositivos`; esto es lo que el resultado lista). Vacío sin `ajustes`.
    ajustes: list = field(default_factory=list)
