"""Escribir una variable del PLC (plan plc-en-el-lazo F1c1, D10): la tabla de símbolos del
programa compilado y `PLC.escribir`.

  - `Compilado.simbolos` = {ruta: (tipo, escribible)} con globales, PROGRAM, bloques estándar y del
    usuario (y sus miembros), ARRAY, CONSTANT y AT, con las rutas de `PLC.variables()`;
  - `escribir` por tipo (BOOL, INT, DINT, REAL, TIME, elemento de ARRAY) con la resolución de
    `leer`; entra antes del próximo scan y el programa puede pisarla;
  - cada rechazo dice por qué: ruta que no existe (con «¿quisiste decir…?»), ambigua, CONSTANT,
    AT de entrada y de salida, dirección, bloque y miembro de bloque, ARRAY sin índice o fuera de
    rango, valor de otro tipo o fuera de rango, y el PLC sin tensión;
  - `simbolos` viaja con el `Compilado` por pickle (al worker) y no se persiste.
"""

from __future__ import annotations

import pickle

import pytest

from apolo.plc import PLC, compilar
from apolo.plc.simbolos import valor_para

FUENTE = """
VAR_GLOBAL
  marcha AT %IX0.0 : BOOL;
  motor AT %QX0.0 : BOOL;
  consigna : INT := 10;
  ganancia : REAL;
END_VAR
VAR_GLOBAL CONSTANT
  MAXIMO : INT := 100;
END_VAR
FUNCTION_BLOCK Arranque
VAR_INPUT orden : BOOL; END_VAR
VAR_OUTPUT q : BOOL; END_VAR
VAR t : TON; END_VAR
t(IN := orden, PT := T#1s);
q := t.Q;
END_FUNCTION_BLOCK
PROGRAM Main
VAR
  tabla : ARRAY[1..3] OF DINT;
  espera : TIME;
  a1 : Arranque;
  listo : BOOL;
  total : DINT;
END_VAR
VAR CONSTANT
  paso : INT := 2;
END_VAR
motor := marcha AND listo;
a1(orden := listo);
total := total + consigna;
END_PROGRAM
"""


@pytest.fixture
def plc():
    return PLC(compilar(FUENTE))


def test_la_tabla_de_simbolos_con_globales_program_bloques_array_y_constant():
    assert compilar(FUENTE).simbolos == {
        "marcha": ("BOOL", False), "motor": ("BOOL", False),            # AT %I / %Q
        "consigna": ("INT", True), "ganancia": ("REAL", True),
        "maximo": ("INT", False),                                         # CONSTANT
        "Main.tabla": ("ARRAY[1..3] OF DINT", True), "Main.espera": ("TIME", True),
        "Main.a1": ("Arranque", False), "Main.a1.orden": ("BOOL", False), "Main.a1.q": ("BOOL", False),
        "Main.a1.t": ("TON", False), "Main.a1.t.in": ("BOOL", False), "Main.a1.t.pt": ("TIME", False),
        "Main.a1.t.q": ("BOOL", False), "Main.a1.t.et": ("TIME", False),
        "Main.listo": ("BOOL", True), "Main.total": ("DINT", True), "Main.paso": ("INT", False)}


def test_las_rutas_escribibles_son_las_de_variables(plc):
    escribibles = {r for r, (_, e) in plc.compilado.simbolos.items() if e}
    assert escribibles <= set(plc.variables())


@pytest.mark.parametrize("ruta,valor,leido", [
    ("consigna", 50, 50), ("consigna", 50.0, 50), ("consigna", -32768, -32768),
    ("ganancia", 2, 2.0), ("ganancia", -1.5, -1.5),
    ("Main.listo", True, True), ("listo", 1, True), ("Main.listo", 0, False),
    ("Main.tabla[2]", 7, [0, 7, 0]), ("tabla[3]", 2**31 - 1, [0, 0, 2**31 - 1]),
    ("Main.espera", 1500, 1500), ("MAIN.Total", 9, 9),
])
def test_escribir_por_tipo(plc, ruta, valor, leido):
    plc.escribir(ruta, valor)
    nombre = ruta.split("[")[0]
    assert plc.leer(nombre) == leido and type(plc.leer(ruta)) is type(leido if "[" not in ruta else leido[0])


def test_entra_antes_del_proximo_scan_y_el_programa_puede_pisarla(plc):
    plc.escribir("consigna", 7)
    plc.scan(0)
    assert plc.leer("Main.total") == 7      # el scan la leyó
    plc.escribir("Main.total", 100)
    plc.scan(10)
    assert plc.leer("Main.total") == 107    # y el programa la pisa
    plc.escribir("Main.listo", True)
    plc.escribir_entrada("I0.0", True)
    plc.scan(20)
    assert plc.salidas["Q0.0"] is True      # una escrita mueve una salida por el programa


@pytest.mark.parametrize("ruta,valor,error,texto", [
    ("consigan", 1, KeyError, "no existe la variable «consigan». ¿Quisiste decir «consigna»?"),
    ("Main.lsito", 1, KeyError, "¿Quisiste decir «Main.listo»?"),
    ("Main.a1.zz", 1, KeyError, "no existe la variable «Main.a1.zz»"),
    ("", 1, KeyError, "falta la variable"),
    ("MAXIMO", 5, ValueError, "«MAXIMO» es CONSTANT"),
    ("Main.paso", 5, ValueError, "«Main.paso» es CONSTANT"),
    ("marcha", True, ValueError, "«marcha» está en una entrada (%IX0.0): su valor lo da el borne"),
    ("motor", True, ValueError, "«motor» está en una salida (%QX0.0): la maneja el programa"),
    ("%QX0.0", True, ValueError, "«%QX0.0» es una dirección de E/S"),
    ("%IX0.0", True, ValueError, "es una dirección de E/S"),
    ("Main.a1", True, ValueError, "«Main.a1» es una instancia de Arranque: lo calcula el bloque"),
    ("Main.a1.q", True, ValueError, "«Main.a1.q» es un miembro de una instancia de Arranque"),
    ("Main.a1.t.PT", 5, ValueError, "es un miembro de una instancia de Arranque"),
    ("Main.tabla", 7, ValueError, "es un ARRAY[1..3] OF DINT: escribe un elemento, p. ej. «Main.tabla[1]»"),
    ("Main.tabla[4]", 7, KeyError, "índice fuera de rango en «Main.tabla[4]» (1 … 3)"),
    ("Main.tabla[0]", 7, KeyError, "índice fuera de rango"),
    ("consigna[1]", 7, KeyError, "«consigna» no es un ARRAY"),
    ("Main.listo.x", 7, KeyError, "no existe la variable"),
    ("consigna", 40000, ValueError, "«consigna» es INT: 40000 no cabe (-32768 … 32767)"),
    ("Main.total", 2**31, ValueError, "es DINT"),
    ("consigna", 1.5, ValueError, "«consigna» es INT: se escribe un número entero, llegó 1.5"),
    ("Main.espera", 2.5, ValueError, "es TIME: se escribe un número entero de ms"),
    ("consigna", True, ValueError, "se escribe un número, llegó True"),
    ("consigna", "7", ValueError, "se escribe un número, llegó '7'"),
    ("ganancia", float("inf"), ValueError, "el valor tiene que ser finito"),
    ("Main.listo", 2, ValueError, "es BOOL: se escribe true/false o 0/1, llegó 2"),
    ("Main.listo", 1.0, ValueError, "es BOOL"),
])
def test_cada_rechazo_dice_por_que(plc, ruta, valor, error, texto):
    antes = plc.variables()
    with pytest.raises(error) as exc:
        plc.escribir(ruta, valor)
    assert texto in str(exc.value)
    assert plc.variables() == antes  # nada a medias


def test_un_elemento_de_un_array_global_se_escribe_y_se_lee():
    plc = PLC(compilar("VAR_GLOBAL g : ARRAY[0..2] OF REAL; END_VAR\nPROGRAM Main g[0] := g[1]; END_PROGRAM"))
    plc.escribir("g[1]", 2)
    plc.scan(0)
    assert plc.leer("g") == [2.0, 2.0, 0.0] and plc.leer("g[0]") == 2.0  # antes `leer("g[0]")` no existía


def test_una_ruta_ambigua_y_el_plc_sin_tension():
    plc = PLC(compilar("PROGRAM A VAR x : INT; END_VAR x := x; END_PROGRAM\n"
                       "PROGRAM B VAR x : INT; END_VAR x := x; END_PROGRAM"))
    with pytest.raises(KeyError, match="es ambigua: usa «A.x» o «B.x»"):
        plc.escribir("x", 1)
    plc.escribir("B.x", 3)
    assert (plc.leer("A.x"), plc.leer("B.x")) == (0, 3)
    plc.cortar()
    with pytest.raises(ValueError, match="sin tensión: no atiende la escritura de «A.x»"):
        plc.escribir("A.x", 1)
    with pytest.raises(KeyError):  # la ruta mala se dice igual, con o sin tensión
        plc.escribir("A.y", 1)
    plc.stop()  # en STOP sí: la memoria atiende aunque el programa no corra
    plc.reponer(0)
    plc.stop()
    plc.escribir("A.x", 5)
    assert plc.leer("A.x") == 5


def test_valor_para_es_la_regla_de_tipos():
    assert valor_para("BOOL", 0, "b") is False and valor_para("REAL", 3, "r") == 3.0
    assert valor_para("TIME", 1e3, "t") == 1000 and isinstance(valor_para("DINT", 5.0, "d"), int)
    with pytest.raises(ValueError, match="es TON: no se escribe"):
        valor_para("TON", 1, "t1")


def test_simbolos_viaja_por_pickle_y_leer_sigue_igual(plc):
    c = pickle.loads(pickle.dumps(plc.compilado))
    assert c.simbolos == plc.compilado.simbolos
    otro = PLC(c)
    otro.escribir("Main.tabla[1]", 4)
    assert otro.leer("tabla") == [4, 0, 0] and otro.leer("Main.a1.t.ET") == 0
    with pytest.raises(KeyError, match="no existe la variable «nada»"):
        otro.leer("nada")
