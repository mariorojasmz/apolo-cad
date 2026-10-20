"""Errores de compilación de ST (D3): en español, con línea y columna, accionables y con
«¿quisiste decir…?» para los identificadores."""

from __future__ import annotations

import pytest

from apolo.plc import ErrorCompilacion, compilar

BORNES = {f"I{b}.{i}" for b in (0, 1) for i in range(8) if not (b == 1 and i > 5)} | \
    {f"Q0.{i}" for i in range(8)} | {"Q1.0", "Q1.1", "AI0", "AI1", "L+", "M", "PE"}


def errores(fuente: str, **kw) -> list:
    with pytest.raises(ErrorCompilacion) as e:
        compilar(fuente, **kw)
    return e.value.errores


def uno(fuente: str, **kw):
    errs = errores(fuente, **kw)
    assert len(errs) == 1, errs
    return errs[0]


def prog(cuerpo: str, decl: str = "") -> str:
    # línea 1: PROGRAM, línea 2: VAR …, línea 3 en adelante: el cuerpo
    return f"PROGRAM Main\nVAR {decl} END_VAR\n{cuerpo}\nEND_PROGRAM\n"


def test_variable_mal_escrita_sugiere_la_correcta():
    e = uno(prog("  marhca := TRUE;", "marcha : BOOL;"))
    assert (e.linea, e.columna) == (3, 3)
    assert e.mensaje == "no existe la variable «marhca». ¿Quisiste decir «marcha»?"
    assert str(e).startswith("línea 3, columna 3: ")
    assert e.a_dict() == {"linea": 3, "columna": 3, "mensaje": e.mensaje}


def test_miembro_de_bloque_mal_escrito():
    e = uno(prog("x := t1.QQ;", "t1 : TON; x : BOOL;"))
    assert (e.linea, e.columna) == (3, 8)
    assert "TON no tiene «QQ» (entradas IN, PT; salidas Q, ET)" in e.mensaje
    assert "¿Quisiste decir «Q»?" in e.mensaje


def test_asignar_con_igual():
    e = uno(prog("x = 1;", "x : INT;"))
    assert (e.linea, e.columna) == (3, 3) and "se usa «:=», no «=»" in e.mensaje


def test_falta_end_if():
    e = uno(prog("IF TRUE THEN x := 1;", "x : INT;"))
    assert e.linea == 4 and e.mensaje == "falta «END_IF» antes de «END_PROGRAM»"


def test_falta_punto_y_coma():
    e = uno(prog("x := 1\ny := 2;", "x, y : INT;"))
    assert (e.linea, e.columna) == (4, 1)
    assert "se esperaba «;» al final de la asignación y encontré «y»" in e.mensaje


def test_tipo_desconocido():
    e = uno(prog("", "x : INTT;"))
    assert (e.linea, e.columna) == (2, 9) and "¿Quisiste decir «INT»?" in e.mensaje


@pytest.mark.parametrize("palabra", ["STRUCT", "STRING", "LREAL", "VAR_IN_OUT", "POINTER"])
def test_fuera_del_subconjunto(palabra):
    e = uno(prog(f"x := 1; {palabra}", "x : INT;"))
    assert e.linea == 3 and "queda fuera del subconjunto" in e.mensaje


def test_direccion_que_el_plc_del_catalogo_no_tiene():
    e = uno("PROGRAM Main\nVAR s AT %IX1.6 : BOOL; END_VAR\nEND_PROGRAM", bornes=BORNES)
    assert (e.linea, e.columna) == (2, 10)
    assert "«%IX1.6» no existe en este PLC (sería su borne I1.6)" in e.mensaje
    assert "¿Quisiste decir «%IX1.5»?" in e.mensaje or "¿Quisiste decir" in e.mensaje
    assert "Tiene %IX0.0 … %IX1.5." in e.mensaje
    e = uno("PROGRAM Main\n%QX1.2 := TRUE;\nEND_PROGRAM", bornes=BORNES)
    assert "Tiene %QX0.0 … %QX1.1." in e.mensaje
    e = uno("PROGRAM Main\nVAR a AT %IW2 : INT; END_VAR\nEND_PROGRAM", bornes=BORNES)
    assert "Tiene %IW0 … %IW1." in e.mensaje


@pytest.mark.parametrize("texto, pedazo", [
    ("%IX0.8", "el bit va de 0 a 7"), ("%IX0", "lleva bit"), ("%MX0.0", "no es una dirección"),
    ("%QW0", "salidas analógicas"), ("%IW0.1", "no lleva bit"),
])
def test_direcciones_mal_formadas(texto, pedazo):
    e = uno(prog(f"x := {texto};", "x : BOOL;"))
    assert pedazo in e.mensaje


def test_escribir_una_entrada():
    e = uno(prog("%IX0.0 := TRUE;"))
    assert "%IX0.0 es una entrada: el programa la lee, no la escribe" in e.mensaje
    e = uno("VAR_GLOBAL b AT %IX0.0 : BOOL; END_VAR\nPROGRAM Main\nb := TRUE;\nEND_PROGRAM")
    assert e.linea == 3 and "está en la entrada %IX0.0" in e.mensaje


def test_una_salida_tiene_un_solo_dueño_y_su_tipo():
    e = uno("VAR_GLOBAL a AT %QX0.0 : BOOL; END_VAR\n"
            "PROGRAM Main\nVAR b AT %QX0.0 : BOOL; END_VAR\nEND_PROGRAM")
    assert e.linea == 3 and "ya es de «a»" in e.mensaje
    e = uno("VAR_GLOBAL a AT %IW0 : BOOL; END_VAR\nPROGRAM Main\nEND_PROGRAM")
    assert "que es INT: declárala INT" in e.mensaje


def test_literal_fuera_de_rango_y_tipos_incompatibles_con_pista():
    e = uno(prog("", "x : INT := 40000;"))
    assert "40000 no cabe en INT (-32768 … 32767). Declárala DINT." in e.mensaje
    e = uno(prog("i := r;", "i : INT; r : REAL;"))
    assert e.mensaje == "«i» es INT y le das REAL. Convierte con REAL_TO_INT(…)."
    e = uno(prog("r := d + r;", "d : DINT; r : REAL;"))
    assert "DINT y REAL" in e.mensaje and "DINT_TO_REAL" in e.mensaje


def test_condicion_no_booleana():
    e = uno(prog("IF x THEN x := 0; END_IF;", "x : INT;"))
    assert (e.linea, e.columna) == (3, 4) and "la condición del IF es BOOL" in e.mensaje


def test_recursion_y_bloque_que_se_contiene():
    e = uno("FUNCTION F : INT\nVAR_INPUT x : INT; END_VAR\nF := G(x);\nEND_FUNCTION\n"
            "FUNCTION G : INT\nVAR_INPUT x : INT; END_VAR\nG := F(x);\nEND_FUNCTION\n"
            "PROGRAM Main\nEND_PROGRAM")
    assert "no admite recursión" in e.mensaje and "F → G → F" in e.mensaje
    e = uno("FUNCTION_BLOCK A\nVAR hijo : B; END_VAR\nEND_FUNCTION_BLOCK\n"
            "FUNCTION_BLOCK B\nVAR padre : A; END_VAR\nEND_FUNCTION_BLOCK\nPROGRAM Main\nEND_PROGRAM")
    assert "se contiene a sí mismo" in e.mensaje


def test_exit_fuera_de_bucle_y_variable_del_for():
    e = uno(prog("EXIT;"))
    assert "EXIT sólo va dentro de un FOR, WHILE o REPEAT" in e.mensaje
    e = uno(prog("FOR i := 1 TO 3 DO i := 5; END_FOR;", "i : INT;"))
    assert "variable de control del FOR" in e.mensaje


def test_una_function_no_escribe_globales_ni_tiene_estado():
    e = uno("VAR_GLOBAL g : INT; END_VAR\nFUNCTION F : INT\nVAR_INPUT x : INT; END_VAR\n"
            "g := x;\nF := x;\nEND_FUNCTION\nPROGRAM Main\nEND_PROGRAM")
    assert e.linea == 4 and "una FUNCTION no escribe variables globales" in e.mensaje
    e = uno("FUNCTION F : INT\nVAR t : TON; END_VAR\nEND_FUNCTION\nPROGRAM Main\nEND_PROGRAM")
    assert "no tiene instancias de bloques" in e.mensaje


def test_llamadas_a_bloques_mal_hechas():
    e = uno(prog("t1(TRUE, T#1s);", "t1 : TON;"))
    assert "nombra cada entrada: «t1(IN := …, PT := …)»" in e.mensaje
    e = uno(prog("t1(IN := TRUE, Q := x);", "t1 : TON; x : BOOL;"))
    assert "se lee con «Q => variable»" in e.mensaje
    e = uno(prog("x := t1;", "t1 : TON; x : BOOL;"))
    assert "es un bloque TON: lee una salida, p. ej. «t1.Q»" in e.mensaje
    e = uno(prog("x := TON(IN := TRUE);", "x : BOOL;"))
    assert "declara una instancia" in e.mensaje
    e = uno(prog("x := t1(IN := TRUE);", "t1 : TON; x : BOOL;"))
    assert "un bloque se llama como sentencia" in e.mensaje


def test_case_con_etiqueta_repetida():
    e = uno(prog("CASE x OF 1: x := 2; 0..3: x := 4; END_CASE;", "x : INT;"))
    assert "ya está en la rama de la línea 3" in e.mensaje


def test_varios_errores_se_juntan_en_orden():
    errs = errores(prog("a := 1;\nb := TRUE;\nc := 2;", "b : INT;"))
    assert [(e.linea, e.mensaje.split(".")[0]) for e in errs] == [
        (3, "no existe la variable «a»"), (4, "«b» es INT y le das BOOL"),
        (5, "no existe la variable «c»")]


@pytest.mark.parametrize("fuente, pedazo", [
    ("PROGRAM Main\n(* sin cerrar\nEND_PROGRAM", "comentario sin cerrar"),
    ("PROGRAM Main\nVAR año : INT; END_VAR\nEND_PROGRAM", "sin tildes ni ñ"),
    ("", "el programa está vacío"),
    ("FUNCTION F : INT\nF := 1;\nEND_FUNCTION", "falta un PROGRAM"),
    ("PROGRAM Main\nVAR x : INT; x : BOOL; END_VAR\nEND_PROGRAM", "ya está declarada"),
    ("PROGRAM Main\nVAR ton : INT; END_VAR\nEND_PROGRAM", "nombre de una POU o de un bloque"),
    ("PROGRAM Main\nVAR a : ARRAY[1..3, 1..2] OF INT; END_VAR\nEND_PROGRAM",
     "una sola dimensión"),
    ("PROGRAM Main\nVAR x : INT; END_VAR\nx := 3 + ;\nEND_PROGRAM", "se esperaba un valor"),
    ("PROGRAM Main\nVAR x : INT; END_VAR\nx := 'hola';\nEND_PROGRAM", "STRING queda fuera"),
    ("PROGRAM Main\nVAR x : INT; END_VAR\nx := INT#5;\nEND_PROGRAM", "literal tipado"),
    ("PROGRAM Main\nVAR x : BOOL; END_VAR\nx := NOT 3;\nEND_PROGRAM", "NOT niega un BOOL"),
    ("PROGRAM Main\nVAR x : REAL; END_VAR\nx := 1.5 MOD 2.0;\nEND_PROGRAM", "MOD opera enteros"),
    ("PROGRAM Main\nVAR x : TIME; END_VAR\nx := T#1s + 5;\nEND_PROGRAM", "otro TIME"),
    ("PROGRAM Main\nVAR x : INT; END_VAR\nx := Fooo(1);\nEND_PROGRAM", "no existe la función"),
    ("PROGRAM Main\nVAR_INPUT x : INT; END_VAR\nEND_PROGRAM", "un PROGRAM no tiene VAR_INPUT"),
    ("FUNCTION_BLOCK F\nVAR x AT %IX0.0 : BOOL; END_VAR\nEND_FUNCTION_BLOCK\n"
     "PROGRAM Main\nEND_PROGRAM", "las direcciones (AT) van"),
    ("PROGRAM Main\nVAR RETAIN x AT %QX0.0 : BOOL; END_VAR\nEND_PROGRAM", "no lleva RETAIN"),
    ("PROGRAM Main\nVAR CONSTANT k : INT := 1; END_VAR\nk := 2;\nEND_PROGRAM", "es CONSTANT"),
    ("PROGRAM Main\nVAR v : ARRAY[1..3] OF INT; END_VAR\nv[4] := 1;\nEND_PROGRAM",
     "fuera de «v»"),
    ("PROGRAM Main\nVAR v : ARRAY[1..2] OF INT := [1, 2, 3]; END_VAR\nEND_PROGRAM",
     "tiene 2 elementos y le das 3"),
    ("PROGRAM Main\nVAR x : INT := y; y : INT; END_VAR\nEND_PROGRAM", "es un literal"),
])
def test_mensajes_accionables(fuente, pedazo):
    errs = errores(fuente)
    assert any(pedazo in e.mensaje for e in errs), [str(e) for e in errs]
    assert all(e.linea >= 1 and e.columna >= 1 for e in errs)


@pytest.mark.parametrize("expr", [
    " + ".join(["1"] * 400),                    # cadena larga: Python no anida > 200 paréntesis
    "(" * 400 + "1" + ")" * 400,                # anidamiento profundo: el parser recursivo
])
def test_una_expresion_monstruosa_es_un_error_y_no_un_crash(expr):
    errs = errores(prog(f"x := {expr};", "x : DINT;"))
    assert any("demasiado" in e.mensaje for e in errs) and errs[0].linea == 3


def test_una_expresion_larga_pero_razonable_compila():
    from apolo.plc import PLC
    plc = PLC(compilar(prog("x := " + " + ".join(["1"] * 150) + ";", "x : DINT;")))
    plc.scan(0)
    assert plc.leer("x") == 150
