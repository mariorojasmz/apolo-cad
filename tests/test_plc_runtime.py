"""Runtime del PLC (D4, D6): imagen de E/S, STOP, RETAIN tras un corte, watchdog
determinista, fallas con su línea y la tabla de tags contra los bornes del catálogo."""

from __future__ import annotations

import pickle
from pathlib import Path

import pytest
import yaml

from apolo.plc import PLC, RUN, SIN_TENSION, STOP, compilar

CATALOGO = Path(__file__).resolve().parents[1] / "core/apolo/library/data/122_maniobra_control.yaml"


def bornes_del_plc_del_catalogo() -> set[str]:
    datos = yaml.safe_load(CATALOGO.read_text(encoding="utf-8"))
    ref = next(i for i in datos["components"] if i.get("ref") == "PLC-14DI-10DO-24VDC")
    return {b["id"] for b in ref["electrico"]["bornes"]}


MARCHA_PARO = """
VAR_GLOBAL
  marcha AT %IX0.0 : BOOL;
  paro AT %IX0.1 : BOOL;     (* NC: TRUE = sin pulsar *)
  motor AT %QX0.0 : BOOL;
  piloto AT %QX0.1 : BOOL;
END_VAR
PROGRAM Main
motor := (marcha OR motor) AND paro;
piloto := motor;
END_PROGRAM
"""


def test_autorretencion_con_la_imagen_de_salidas():
    plc = PLC(compilar(MARCHA_PARO, bornes=bornes_del_plc_del_catalogo()))
    plc.escribir_entrada("I0.1", True)
    plc.scan(0)
    assert plc.salidas == {"Q0.0": False, "Q0.1": False}
    plc.escribir_entrada("I0.0", True)
    assert plc.salidas["Q0.0"] is False            # el borne cambia, la imagen no hasta el scan
    plc.scan(10)
    plc.escribir_entrada("I0.0", False)
    plc.scan(20)
    assert plc.salidas == {"Q0.0": True, "Q0.1": True}   # se retiene
    plc.escribir_entrada("I0.1", False)
    plc.scan(30)
    assert plc.salidas == {"Q0.0": False, "Q0.1": False}


def test_las_salidas_se_copian_al_final_del_scan():
    fuente = ("PROGRAM Main\nVAR x : BOOL; END_VAR\n"
              "%QX0.0 := TRUE;\nx := %QX0.0;\n%QX0.0 := FALSE;\nEND_PROGRAM")
    plc = PLC(compilar(fuente))
    plc.scan(0)
    assert plc.leer("x") is True and plc.salidas == {"Q0.0": False}


def test_tabla_de_tags_sale_del_programa():
    fuente = MARCHA_PARO.replace("piloto := motor;", "piloto := motor;\n%QX1.1 := %IX1.5;")
    c = compilar(fuente, bornes=bornes_del_plc_del_catalogo())
    assert [(t["variable"], t["direccion"], t["borne"], t["sentido"]) for t in c.tags] == [
        ("marcha", "%IX0.0", "I0.0", "entrada"), ("paro", "%IX0.1", "I0.1", "entrada"),
        (None, "%IX1.5", "I1.5", "entrada"), ("motor", "%QX0.0", "Q0.0", "salida"),
        ("piloto", "%QX0.1", "Q0.1", "salida"), (None, "%QX1.1", "Q1.1", "salida"),
    ]
    assert c.entradas == ["I0.0", "I0.1", "I1.5"]


def test_stop_apaga_salidas_y_run_arranca_en_caliente():
    plc = PLC(compilar(MARCHA_PARO))
    plc.escribir_entrada("I0.0", True)
    plc.escribir_entrada("I0.1", True)
    plc.scan(0)
    assert plc.salidas["Q0.0"] is True
    plc.stop()
    assert plc.estado == STOP and plc.salidas["Q0.0"] is False
    plc.scan(10)
    assert plc.salidas["Q0.0"] is False            # en STOP no ejecuta
    plc.run(20)
    plc.scan(20)
    assert plc.estado == RUN and plc.salidas["Q0.0"] is True


RETENCION = """
VAR_GLOBAL RETAIN total : DINT; END_VAR
VAR_GLOBAL vuelta : INT; END_VAR
FUNCTION_BLOCK Contador
VAR RETAIN propio : INT; END_VAR
VAR volatil : INT; END_VAR
propio := propio + 1; volatil := volatil + 1;
END_FUNCTION_BLOCK
PROGRAM Main
VAR RETAIN cuenta : INT; piezas : CTU; END_VAR
VAR temporal : INT; espera : TON; c : Contador; END_VAR
cuenta := cuenta + 1; temporal := temporal + 1; total := total + 10; vuelta := vuelta + 1;
piezas(CU := NOT piezas.Q AND (cuenta MOD 2 = 0), PV := 100);
espera(IN := TRUE, PT := T#1h);
c();
%QX0.0 := TRUE;
END_PROGRAM
"""


def test_retain_sobrevive_a_un_corte_y_el_resto_vuelve_al_inicio():
    plc = PLC(compilar(RETENCION))
    for n in range(6):
        plc.paso(n * 10)
    assert (plc.leer("cuenta"), plc.leer("temporal"), plc.leer("total")) == (6, 6, 60)
    assert plc.leer("Main.piezas.CV") == 3 and plc.leer("Main.espera.ET") == 50
    assert plc.salidas["Q0.0"] is True
    plc.cortar()
    assert plc.estado == SIN_TENSION and plc.salidas["Q0.0"] is False
    plc.paso(60)
    assert plc.leer("cuenta") == 6                 # sin tensión no ejecuta
    plc.reponer(1000)
    assert (plc.leer("cuenta"), plc.leer("total")) == (6, 60)          # RETAIN
    assert (plc.leer("temporal"), plc.leer("vuelta")) == (0, 0)        # volátiles
    assert plc.leer("Main.piezas.CV") == 3                             # FB en RETAIN, entero
    assert plc.leer("Main.espera.ET") == 0                             # TON volátil
    assert plc.leer("Main.c.propio") == 6 and plc.leer("Main.c.volatil") == 0
    plc.paso(1000)
    assert plc.leer("cuenta") == 7 and plc.leer("temporal") == 1
    plc.arranque_en_frio(2000)
    assert (plc.leer("cuenta"), plc.leer("total"), plc.leer("Main.piezas.CV")) == (0, 0, 0)


def test_watchdog_en_un_while_true_para_el_plc_y_las_salidas_caen():
    fuente = """
    PROGRAM Main
    VAR n : DINT; atascar : BOOL; END_VAR
    %QX0.0 := TRUE;
    IF atascar THEN
      WHILE TRUE DO
        n := n + 1;
      END_WHILE;
    END_IF;
    END_PROGRAM"""
    plc = PLC(compilar(fuente), ciclo_ms=10)
    plc.scan(0)
    assert plc.salidas["Q0.0"] is True
    plc.tareas[0].instancia.v_atascar = True
    plc.scan(10)
    assert plc.estado == STOP
    assert plc.falla["tipo"] == "watchdog" and plc.falla["linea"] == 6
    assert "watchdog" in plc.falla["mensaje"] and plc.falla["t_ms"] == 10
    assert plc.salidas["Q0.0"] is False
    # determinista: el presupuesto es de vueltas (3 × 10 ms × 10 000), no de tiempo de pared
    assert plc.leer("n") == 300_000
    plc.run(20)
    assert plc.estado == RUN and len(plc.fallas) == 1


@pytest.mark.parametrize("bucle", [
    "REPEAT n := n + 1; UNTIL FALSE END_REPEAT;",
    "FOR i := 0 TO 10 BY paso DO n := n + 1; END_FOR;",
    "WHILE TRUE DO FOR i := 1 TO 3 DO n := n + 1; END_FOR; END_WHILE;",
    "n := Girar(5);",
    "f();",
])
def test_watchdog_en_cualquier_bucle(bucle):
    fuente = """
    FUNCTION Girar : DINT
    VAR_INPUT x : INT; END_VAR
    VAR k : DINT; END_VAR
    WHILE x > 0 DO k := k + 1; END_WHILE;
    Girar := k;
    END_FUNCTION
    FUNCTION_BLOCK Fb
    VAR k : DINT; END_VAR
    REPEAT k := k + 1; UNTIL k < 0 END_REPEAT;
    END_FUNCTION_BLOCK
    PROGRAM Main
    VAR n : DINT; i : INT; paso : INT; f : Fb; END_VAR
    """ + bucle + "\nEND_PROGRAM"
    plc = PLC(compilar(fuente), watchdog_ms=1)
    plc.scan(0)
    assert plc.estado == STOP and plc.falla["tipo"] == "watchdog"


def test_un_bucle_largo_pero_legitimo_no_dispara_el_watchdog():
    fuente = """
    PROGRAM Main
    VAR i : DINT; s : DINT; END_VAR
    s := 0;
    FOR i := 1 TO 100000 DO s := s + 1; END_FOR;
    END_PROGRAM"""
    plc = PLC(compilar(fuente), ciclo_ms=10)       # presupuesto 300 000 vueltas
    plc.scan(0)
    plc.scan(10)
    assert plc.estado == RUN and plc.leer("s") == 100000


def test_el_watchdog_es_determinista():
    fuente = """
    PROGRAM Main
    VAR n : DINT; END_VAR
    WHILE TRUE DO n := n + 1; END_WHILE;
    END_PROGRAM"""
    a, b = PLC(compilar(fuente)), PLC(compilar(fuente))
    a.scan(0)
    b.scan(0)
    assert a.leer("n") == b.leer("n") and a.falla == b.falla


def test_paso_respeta_el_ciclo_y_salta_los_atrasados():
    plc = PLC(compilar("PROGRAM Main VAR n : INT; END_VAR n := n + 1; END_PROGRAM"),
              ciclo_ms=10)
    for t in (0, 2, 4, 10, 12, 45, 46, 50):
        plc.paso(t)
    assert plc.leer("n") == 4                      # 0, 10, 45, 50


def test_leer_variables_y_errores_de_ruta():
    fuente = """
    VAR_GLOBAL g : INT := 1; END_VAR
    PROGRAM A VAR x : INT := 2; v : ARRAY[1..3] OF INT := [7, 8, 9]; END_VAR END_PROGRAM
    PROGRAM B VAR x : INT := 3; solo_b : BOOL; END_VAR END_PROGRAM"""
    plc = PLC(compilar(fuente))
    assert plc.leer("g") == 1 and plc.leer("A.x") == 2 and plc.leer("B.x") == 3
    assert plc.leer("solo_b") is False and plc.leer("A.v[3]") == 9 and plc.leer("v") == [7, 8, 9]
    with pytest.raises(KeyError, match="ambigua"):
        plc.leer("x")
    with pytest.raises(KeyError, match="no existe"):
        plc.leer("nada")
    assert plc.variables() == {"g": 1, "A.x": 2, "A.v": [7, 8, 9], "B.x": 3, "B.solo_b": False}


def test_el_compilado_viaja_en_pickle_y_corre_igual():
    c = compilar(MARCHA_PARO)
    assert c.codigo is not None                     # se arma antes de viajar
    copia = pickle.loads(pickle.dumps(c))
    plc = PLC(copia)
    plc.escribir_entrada("I0.0", True)
    plc.escribir_entrada("I0.1", True)
    plc.scan(0)
    assert plc.salidas["Q0.0"] is True
