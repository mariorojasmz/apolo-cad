"""Banco de la co-simulación en lazo cerrado (plan V8.3 F4): una faja pequeña con su tablero.

  - `faja_directo()`: `create_belt_conveyor` 3000×500×800 con el tablero de arranque directo de
    V8.1 (`tablero_electrico.arranque_directo`: guardamotor, contactor con autorretención, seta);
  - `faja_variador()`: la misma faja con el tablero (b) por variador y PLC
    (`tablero_electrico.arranque_variador_plc`), rampas de 1 s para que la prueba sea corta;
  - `PROGRAMA`: marcha/paro con autorretención en el PLC, seta, falla del variador y conteo de
    cajas con la fotocelda.
Más lectores de las trazas: `cambios`, `primer_cambio`, `serie`, `en`.
"""

from __future__ import annotations

from apolo.doc.document import Document
from tablero_electrico import arranque_directo, arranque_variador_plc

JUNTA = "c1_eje_motriz"
MOTOR = {"-M1": {"junta": JUNTA, "direccion_transporte": [1, 0, 0]}}
FOTO = {"-B1": {"origen": [0, -400, 850], "direccion": [0, 1, 0], "alcance_mm": 800}}
MECANICA = {"con_autodeteccion": True}

PROGRAMA = """
VAR_GLOBAL
  foto AT %IX0.0 : BOOL;
  seta_ok AT %IX0.1 : BOOL;      (* NC de la seta: TRUE = liberada *)
  marcha AT %IX0.2 : BOOL;
  paro AT %IX0.3 : BOOL;         (* NC: TRUE = sin pulsar *)
  falla_vfd AT %IX0.4 : BOOL;
  vfd_marcha AT %QX0.0 : BOOL;
  piloto AT %QX0.1 : BOOL;
END_VAR
PROGRAM Main
VAR
  en_marcha : BOOL;
  cuenta : INT;
  flanco : R_TRIG;
END_VAR
IF marcha AND seta_ok AND paro AND NOT falla_vfd THEN
  en_marcha := TRUE;
END_IF;
IF NOT paro OR NOT seta_ok OR falla_vfd THEN
  en_marcha := FALSE;
END_IF;
vfd_marcha := en_marcha;
piloto := en_marcha;
flanco(CLK := foto);
IF flanco.Q THEN
  cuenta := cuenta + 1;
END_IF;
END_PROGRAM
"""
PROGRAMAS = [{"plc": "-K1", "nombre": "Main", "fuente": PROGRAMA, "ciclo_ms": 10}]


def _faja(nombre: str) -> Document:
    doc = Document(nombre)
    doc.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    return doc


def faja_directo() -> Document:
    doc = _faja("faja-directo")
    doc.execute_many(arranque_directo())
    return doc


def faja_variador() -> Document:
    doc = _faja("faja-variador")
    doc.execute_many(arranque_variador_plc(ajustes_variador={"acel_s": 1.0, "decel_s": 1.0}))
    return doc


def escenario_variador(duracion_s: float, *, acciones=(), eventos=(), cajas: bool = False) -> dict:
    """Potenciómetro a fondo en t = 0 y marcha por la botonera a 0,3 s, más lo que se pida."""
    ev = list(eventos)
    if cajas:
        ev.append({"t": 0.0, "tipo": "producto", "nombre": "caja", "dims_mm": [150, 120, 100], "masa_kg": 2.0,
                   "cada_s": 0.5, "posicion_mm": [-500, 0, 850.5]})
    return {"duracion_s": duracion_s, "mecanica": MECANICA, "acoples": {"motores": MOTOR, "sensores": FOTO},
            "acciones": [{"t": 0.0, "accion": "girar", "dispositivo": "-S1", "valor": 1.0},
                         {"t": 0.3, "accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha", "durante_s": 0.2},
                         *acciones],
            "eventos": ev}


def escenario_directo(duracion_s: float, *, acciones=(), eventos=()) -> dict:
    """Marcha por -S2 a 0,2 s (el contactor se autorretiene), más lo que se pida."""
    return {"duracion_s": duracion_s, "mecanica": MECANICA, "acoples": {"motores": MOTOR},
            "acciones": [{"t": 0.2, "accion": "pulsar", "dispositivo": "-S2", "durante_s": 0.2}, *acciones],
            "eventos": list(eventos)}


def cambios(res: dict, senal: str) -> list:
    return res["trazas"]["discretas"][senal]


def primer_cambio(res: dict, senal: str, valor, desde: float = 0.0) -> float | None:
    return next((t for t, v in cambios(res, senal) if v == valor and t >= desde - 1e-9), None)


def serie(res: dict, senal: str) -> list[tuple[float, float]]:
    an = res["trazas"]["analogicas"]
    return [(t, v) for t, v in zip(an["t"], an["senales"][senal]) if v is not None]


def en(res: dict, senal: str, t: float) -> float:
    """La muestra analógica más cercana a t."""
    return min(serie(res, senal), key=lambda tv: abs(tv[0] - t))[1]
