"""Banco del motor a un eje lineal (plan motor-a-eje-lineal F2): un elevador mínimo.

`elevador()`: una columna anclada al piso y una plataforma de chapa (600 × 600 × 50, ~141 kg de
acero) en una junta PRISMÁTICA vertical (`JUNTA`, 0 a 1600 mm), con el tablero (b) del banco de la
faja (`tablero_electrico.arranque_variador_plc`: VFD-2K2-220 → NMRV-090, aquí i = 40, rampas de
1 y 0,8 s como el elevador real) y un sensor
-B1 que lee la junta. `PROGRAMA`: la marcha sube hasta que -B1 ve la plataforma (el nivel) y para.
`escenario(...)`: el potenciómetro a fondo y la marcha a 0,3 s; la transmisión, el piñón Z15 de
paso 08B (d0 = 61,09 mm, el del elevador real) declarado o la pieza del piñón.
"""

from __future__ import annotations

from tablero_electrico import arranque_variador_plc

from apolo.doc.document import Document

JUNTA = "j_plataforma"
D0_MM = 61.09                     # PINON-08B-1-Z15 (111_cadenas_pinones.yaml)
Z0_MM = 300.0                     # altura de la cara inferior de la plataforma en diseño
NIVEL_MM = 500.0                  # el sensor de nivel, sobre la junta

PROGRAMA = """
VAR_GLOBAL
  nivel AT %IX0.0 : BOOL;
  seta_ok AT %IX0.1 : BOOL;
  marcha AT %IX0.2 : BOOL;
  paro AT %IX0.3 : BOOL;
  falla_vfd AT %IX0.4 : BOOL;
  vfd_marcha AT %QX0.0 : BOOL;
  piloto AT %QX0.1 : BOOL;
END_VAR
PROGRAM Main
VAR
  subiendo : BOOL;
END_VAR
IF marcha AND seta_ok AND paro AND NOT falla_vfd AND NOT nivel THEN
  subiendo := TRUE;
END_IF;
IF nivel OR NOT paro OR NOT seta_ok OR falla_vfd THEN
  subiendo := FALSE;
END_IF;
vfd_marcha := subiendo;
piloto := subiendo;
END_PROGRAM
"""
PROGRAMAS = [{"plc": "-K1", "nombre": "Main", "fuente": PROGRAMA, "ciclo_ms": 10}]


def elevador(pinon: bool = False) -> Document:
    """La máquina; con `pinon` suma la pieza del piñón de catálogo (sin junta: sólo su ficha)."""
    doc = Document("elevador-minimo")
    col = doc.execute("create_box", {"name": "Columna", "width": 200, "depth": 200, "height": 2200,
                                     "position": {"x": 0, "y": -500, "z": 1100}})
    doc.execute("ground", {"name": "g_columna", "feature": col})
    plat = doc.execute("create_box", {"name": "Plataforma", "width": 600, "depth": 600, "height": 50,
                                      "position": {"x": 0, "y": 0, "z": Z0_MM + 25}})
    doc.execute("add_joint", {"name": JUNTA, "type": "prismatica", "parent": col, "child": plat,
                              "origin": {"x": 0, "y": 0, "z": Z0_MM}, "axis": {"x": 0, "y": 0, "z": 1},
                              "lower": -250, "upper": 1600})
    if pinon:
        doc.execute("insert_component", {"component": "PINON-08B-1-Z15", "name": "Piñón motriz",
                                         "position": {"x": 0, "y": -500, "z": 2300}})
    doc.execute_many(arranque_variador_plc(ajustes_motor={"i": 40, "eta_reductor": 0.65},
                                           ajustes_variador={"acel_s": 1.0, "decel_s": 0.8}))
    return doc


def transmision(**extra) -> dict:
    return {"diametro_primitivo_mm": D0_MM, "fuente": "PINON-08B-1-Z15, d0 de la ficha", **extra}


def escenario(duracion_s: float = 7.0, *, tr: dict | None = None, marcha: bool = True,
              acciones=(), eventos=()) -> dict:
    motor = {"junta": JUNTA, "direccion_transporte": [0, 0, 1]}
    if tr is not False:
        motor["transmision"] = tr or transmision()
    acc = [{"t": 0.0, "accion": "girar", "dispositivo": "-S1", "valor": 1.0}]
    if marcha:
        acc.append({"t": 0.3, "accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha", "durante_s": 0.2})
    return {"duracion_s": duracion_s,
            "acoples": {"motores": {"-M1": motor},
                        "sensores": {"-B1": {"junta": JUNTA, "en_mm": NIVEL_MM, "ventana_mm": 10}}},
            "acciones": [*acc, *acciones], "eventos": list(eventos)}
