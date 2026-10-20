"""D6: un programa ST no puede salir a Python.

Tres llaves, cada una probada sola:
1. el lenguaje: el lexer rechaza `__`, todo identificador se renombra a `v_<nombre>` y sólo
   las entradas y salidas de un bloque se leen con `.`;
2. el verificador re-lee el Python generado con una lista blanca (y caza Python hostil
   escrito a mano, como si el compilador tuviera un bug);
3. el `exec` corre sin `__builtins__`.
"""

from __future__ import annotations

import pickle

import pytest

from apolo.plc import PLC, ErrorCompilacion, compilar
from apolo.plc.verificador import CodigoInseguro, verificar


@pytest.mark.parametrize("cuerpo", [
    "x := __import__(1);",
    "x := t1.__class__;",
    "x := t1._ini;",
    "x := t1.Q.real;",
    "x := eval(1);",
    "x := open(1);",
    "x := getattr(t1, 1);",
    "x := exec(1);",
    "x := s.v_x;",
    "x := _G.v_x;",
])
def test_lo_que_no_es_st_no_compila(cuerpo):
    fuente = f"PROGRAM Main\nVAR x : DINT; t1 : TON; s : TON; END_VAR\n{cuerpo}\nEND_PROGRAM"
    with pytest.raises(ErrorCompilacion):
        compilar(fuente)


def test_nombres_de_python_como_variables_son_solo_variables():
    fuente = """
    PROGRAM Main
    VAR eval, exec, open, print, len, s, t, e, o, _G, _wd, _i, _n1 : DINT; END_VAR
    eval := 1; exec := eval + 1; open := exec + 1; print := open + 1; len := print + 1;
    s := len + 1; t := s + 1; e := t + 1; o := e + 1; _G := o + 1; _wd := _G + 1;
    _i := _wd + 1; _n1 := _i + 1;
    WHILE _n1 < 20 DO _n1 := _n1 + 1; END_WHILE;
    END_PROGRAM"""
    plc = PLC(compilar(fuente))
    plc.scan(0)
    assert plc.leer("_n1") == 20 and plc.leer("_wd") == 11 and plc.estado == "RUN"


def test_el_codigo_corre_sin_builtins():
    plc = PLC(compilar("PROGRAM Main VAR x : INT; END_VAR x := x + 1; END_PROGRAM"))
    for t in plc.tareas:
        assert t.fn.__globals__["__builtins__"] == {}
    ns = plc.tareas[0].fn.__globals__
    prohibidos = {"__import__", "open", "eval", "exec", "getattr", "type", "object", "print"}
    assert not prohibidos & set(ns)


def test_el_python_generado_solo_tiene_textos_de_bornes():
    c = compilar("VAR_GLOBAL a AT %IX0.0 : BOOL; q AT %QX0.1 : BOOL; v AT %IW1 : INT; END_VAR\n"
                 "PROGRAM Main q := a AND v > 5; END_PROGRAM")
    import ast
    textos = {n.value for n in ast.walk(ast.parse(c.fuente_py))
              if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert textos == {"I0.0", "Q0.1", "AI1"}


@pytest.mark.parametrize("hostil", [
    "import os",
    "from os import system",
    "def _p_main(s, t):\n    s.__class__",
    "def _p_main(s, t):\n    __import__('os')",
    "def _p_main(s, t):\n    (lambda: 1)()",
    "def _p_main(s, t):\n    open('x')",
    "def _p_main(s, t):\n    s.v_x.__dict__",
    "def _p_main(s, t):\n    x = 'rm -rf /'",
    "class A:\n    pass",
    "def _p_main(s, t):\n    [x for x in s]",
    "def _p_main(s, t):\n    getattr(s, 'v_x')",
    "def f():\n    pass",
    "def _p_main(s, t):\n    s.v_x()",
    "def _p_main(s, t):\n    try:\n        pass\n    except Exception:\n        pass",
    "def _p_main(s, t):\n    global x",
    "def _p_main(s, t):\n    del s.v_x",
    "def _p_main(s, t, *a):\n    pass",
    "def _p_main(s, t=print):\n    pass",
    "def _p_main(s, t):\n    _G.d_ix0_0 = e['../etc']",
    "def _p_main(s, t):\n    yield 1",
    "def _p_main(s, t):\n    _abs(x=1)",
    "def _p_main(s, t):\n    with s:\n        pass",
    "def _p_main(s, t):\n    _b_ton.__globals__",
    "def _p_main(s, t):\n    x = b'abc'",
])
def test_el_verificador_rechaza_python_hostil(hostil):
    with pytest.raises(CodigoInseguro):
        verificar(hostil)


def test_un_compilado_adulterado_no_corre():
    c = compilar("PROGRAM Main VAR x : INT; END_VAR x := 1; END_PROGRAM")
    copia = pickle.loads(pickle.dumps(c))
    copia.fuente_py += "import os\n"
    with pytest.raises(CodigoInseguro):
        PLC(copia)


def test_el_verificador_acepta_todo_lo_que_emite_el_compilador():
    """Un programa que usa todas las construcciones pasa la lista blanca (no es demasiado
    estrecha)."""
    fuente = """
    VAR_GLOBAL a AT %IX0.0 : BOOL; q AT %QX0.0 : BOOL; ai AT %IW0 : INT; g : REAL; END_VAR
    FUNCTION F : REAL VAR_INPUT x : REAL; END_VAR VAR v : ARRAY[0..2] OF INT := [1, 2]; END_VAR
      F := x * 2.0 + v[1]; RETURN;
    END_FUNCTION
    FUNCTION_BLOCK Pulsador VAR_INPUT i : BOOL; END_VAR VAR_OUTPUT o : BOOL; END_VAR
      VAR t : TP; END_VAR t(IN := i, PT := T#1s, Q => o);
    END_FUNCTION_BLOCK
    PROGRAM Main
    VAR p1 : Pulsador; n : INT; k : INT; arr : ARRAY[1..4] OF DINT; END_VAR
    p1(i := a, o => q);
    g := F(INT_TO_REAL(ai)) / 3.0 + SQRT(ABS(g)) + EXPT(2, 3);
    CASE n OF 1, 2: n := 3; 4..6: n := 0; ELSE n := n + 1; END_CASE;
    FOR k := 1 TO 4 BY 1 DO arr[k] := arr[k] + k; IF k > 3 THEN EXIT; END_IF; END_FOR;
    REPEAT n := n MOD 5; UNTIL TRUE END_REPEAT;
    WHILE n > 100 DO n := n / 2; END_WHILE;
    q := SEL(a, FALSE, TRUE) XOR (LIMIT(0, n, 10) = MIN(n, 3));
    IF NOT a THEN RETURN; END_IF;
    END_PROGRAM"""
    c = compilar(fuente)
    verificar(c.fuente_py)
    plc = PLC(c)
    plc.scan(0)
    assert plc.estado == "RUN"
