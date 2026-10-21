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
