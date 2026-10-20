"""Conformidad del subconjunto de ST de V8.3 (D5): un caso por construcción, corrido de verdad.

Cada caso compila un programa con `apolo.plc.compilar`, lo corre en el runtime con reloj
virtual y lee las variables con `PLC.leer`. Los bloques estándar contra la norma están en
`test_plc_bloques.py`; RETAIN, watchdog y la imagen de E/S, en `test_plc_runtime.py`.
"""

from __future__ import annotations

import math

import pytest

from apolo.plc import PLC, STOP, compilar


def correr(cuerpo: str, decl: str = "", scans: int = 1, extra: str = "", **kw) -> PLC:
    fuente = f"{extra}\nPROGRAM Main\nVAR\n{decl}\nEND_VAR\n{cuerpo}\nEND_PROGRAM\n"
    plc = PLC(compilar(fuente), **kw)
    for n in range(scans):
        plc.scan(n * 10)
    return plc


def test_asignacion_y_tipos_elementales():
    p = correr("b := TRUE; i := -5; d := 100000; r := 1.5; t := T#1s500ms;",
               "b : BOOL; i : INT; d : DINT; r : REAL; t : TIME;")
    assert (p.leer("b"), p.leer("i"), p.leer("d"), p.leer("r"), p.leer("t")) == \
        (True, -5, 100000, 1.5, 1500)


def test_valores_iniciales_y_constant():
    p = correr("y := x + N;", "x : INT := 7; y : INT; r : REAL := 2; b : BOOL := TRUE;"
               "\nEND_VAR\nVAR CONSTANT N : INT := 3;")
    assert p.leer("y") == 10 and p.leer("r") == 2.0 and isinstance(p.leer("r"), float)
    assert p.leer("b") is True


@pytest.mark.parametrize("expr, esperado", [
    ("2 + 3 * 4", 14), ("(2 + 3) * 4", 20), ("10 - 4 - 3", 3), ("20 / 2 / 5", 2),
    ("7 MOD 4 + 1", 4), ("-2 + 5", 3),
])
def test_precedencia_aritmetica(expr, esperado):
    assert correr(f"x := {expr};", "x : DINT;").leer("x") == esperado


def test_potencia_unario_y_asociatividad():
    p = correr("a := -2 ** 2; b := 2 ** 3 ** 2; c := EXPT(9, 0.5);", "a, b, c : REAL;")
    assert p.leer("a") == 4.0        # la negación liga más que ** (tabla 71)
    assert p.leer("b") == 64.0       # ** asocia a la izquierda
    assert p.leer("c") == 3.0


@pytest.mark.parametrize("expr, esperado", [
    ("NOT a AND b", False), ("a OR b AND c", True), ("a XOR b OR c", True),
    ("a AND b XOR c", False), ("NOT (a AND b)", True), ("a & c", False),
    ("1 < 2 = TRUE", True), ("3 >= 3 AND 2 <> 3", True),
])
def test_precedencia_booleana(expr, esperado):
    p = correr(f"x := {expr};", "x : BOOL; a : BOOL := TRUE; b : BOOL; c : BOOL;")
    assert p.leer("x") is esperado


def test_if_elsif_else():
    cuerpo = ("IF x < 0 THEN y := -1; ELSIF x = 0 THEN y := 0; ELSIF x < 10 THEN y := 1; "
              "ELSE y := 2; END_IF;")
    for x, y in ((-3, -1), (0, 0), (5, 1), (50, 2)):
        assert correr(cuerpo, f"x : INT := {x}; y : INT;").leer("y") == y


def test_case_valores_listas_rangos_y_else():
    cuerpo = """
    CASE x OF
      1: y := 10;
      2, 3: y := 20;
      5..9: y := 30;
      -4..-1: y := 40;
    ELSE
      y := 99;
    END_CASE;"""
    for x, y in ((1, 10), (3, 20), (7, 30), (-2, 40), (4, 99), (100, 99)):
        assert correr(cuerpo, f"x : INT := {x}; y : INT;").leer("y") == y


def test_for_con_paso_negativo_y_exit():
    p = correr("""
    s := 0; FOR i := 1 TO 10 DO s := s + i; END_FOR;
    b := 0; FOR j := 10 TO 1 BY -3 DO b := b * 100 + j; END_FOR;
    c := 0; FOR k := 1 TO 100 DO IF k > 4 THEN EXIT; END_IF; c := c + 1; END_FOR;
    """, "s, i, j, k, c : INT; b : DINT;")
    assert p.leer("s") == 55
    assert p.leer("b") == 10070401      # 10, 7, 4, 1
    assert p.leer("c") == 4


def test_for_con_paso_variable():
    p = correr("n := 0; FOR i := 0 TO 20 BY paso DO n := n + 1; END_FOR;",
               "i, n : INT; paso : INT := 5;")
    assert p.leer("n") == 5


def test_while_y_repeat():
    p = correr("""
    n := 0; WHILE n < 7 DO n := n + 1; END_WHILE;
    m := 0; REPEAT m := m + 2; UNTIL m >= 5 END_REPEAT;
    z := 0; REPEAT z := z + 1; UNTIL TRUE END_REPEAT;
    """, "n, m, z : INT;")
    assert (p.leer("n"), p.leer("m"), p.leer("z")) == (7, 6, 1)


def test_return_en_program_y_exit_en_bucles_anidados():
    p = correr("""
    a := 1;
    FOR i := 1 TO 3 DO
      FOR j := 1 TO 3 DO
        IF j = 2 THEN EXIT; END_IF;
        n := n + 1;
      END_FOR;
    END_FOR;
    IF a = 1 THEN RETURN; END_IF;
    a := 2;
    """, "a, i, j, n : INT;")
    assert p.leer("a") == 1 and p.leer("n") == 3


def test_function_con_argumentos_con_nombre_posicionales_y_por_defecto():
    extra = """
    FUNCTION Escalar : REAL
    VAR_INPUT x : INT; k : REAL := 2.0; END_VAR
    VAR tmp : REAL; END_VAR
    tmp := INT_TO_REAL(x) * k;
    IF tmp > 100.0 THEN Escalar := 100.0; RETURN; END_IF;
    Escalar := tmp;
    END_FUNCTION
    """
    p = correr("a := Escalar(3, 1.5); b := Escalar(x := 4); c := Escalar(k := 10.0, x := 50);",
               "a, b, c : REAL;", extra=extra)
    assert (p.leer("a"), p.leer("b"), p.leer("c")) == (4.5, 8.0, 100.0)


def test_function_block_del_usuario_con_estado_salidas_y_bloque_anidado():
    extra = """
    FUNCTION_BLOCK Arranque
    VAR_INPUT marcha : BOOL; paro : BOOL; END_VAR
    VAR_OUTPUT motor : BOOL; arranques : INT; END_VAR
    VAR flanco : R_TRIG; espera : TON; END_VAR
    flanco(CLK := marcha);
    IF flanco.Q THEN arranques := arranques + 1; END_IF;
    espera(IN := marcha AND NOT paro, PT := T#20ms);
    motor := espera.Q;
    END_FUNCTION_BLOCK
    """
    fuente = extra + """
    PROGRAM Main
    VAR a1 : Arranque; m : BOOL; n : INT; marcha : BOOL; END_VAR
    a1(marcha := marcha, paro := FALSE, motor => m, arranques => n);
    END_PROGRAM"""
    plc = PLC(compilar(fuente))
    for t in range(0, 60, 10):
        plc.scan(t)
    assert plc.leer("m") is False and plc.leer("n") == 0
    inst = plc.tareas[0].instancia      # `marcha` es del PROGRAM: se escribe en su memoria
    inst.v_marcha = True
    for t in range(60, 100, 10):
        plc.scan(t)
    assert plc.leer("n") == 1 and plc.leer("m") is True
    assert plc.leer("Main.a1.arranques") == 1


def test_arrays_con_inicial_repetido_indice_variable_y_constante():
    p = correr("""
    s := 0; FOR i := 1 TO 5 DO s := s + v[i]; END_FOR;
    v[2] := 9; w[0] := TRUE;
    """, "v : ARRAY[1..5] OF INT := [3(1), 4]; w : ARRAY[0..1] OF BOOL; s, i : INT;")
    assert p.leer("s") == 7
    assert p.leer("v") == [1, 9, 1, 4, 0] and p.leer("v[2]") == 9 and p.leer("w[0]") is True


def test_indice_fuera_de_rango_en_ejecucion_para_el_plc():
    p = correr("k := 6; v[k] := 1;", "v : ARRAY[1..5] OF INT; k : INT;")
    assert p.estado == STOP and p.falla["tipo"] == "indice"
    assert "6" in p.falla["mensaje"] and p.falla["linea"] == 6


@pytest.mark.parametrize("lit, ms", [
    ("T#1s500ms", 1500), ("T#1.5s", 1500), ("TIME#2m", 120000), ("t#1h", 3_600_000),
    ("T#1d2h", 93_600_000), ("T#100ms", 100), ("T#-5s", -5000), ("T#1m_30s", 90000),
    ("T#250us", None),
])
def test_literales_de_tiempo(lit, ms):
    if ms is None:
        with pytest.raises(Exception, match="milisegundos"):
            correr(f"t := {lit};", "t : TIME;")
    else:
        assert correr(f"t := {lit};", "t : TIME;").leer("t") == ms


def test_literales_numericos():
    p = correr("a := 16#FF; b := 2#1010; c := 8#17; d := 1_000; r := 1.5E3; q := 2.5;",
               "a, b, c, d : DINT; r, q : REAL;")
    assert (p.leer("a"), p.leer("b"), p.leer("c"), p.leer("d")) == (255, 10, 15, 1000)
    assert p.leer("r") == 1500.0 and p.leer("q") == 2.5


def test_division_y_mod_como_la_norma():
    p = correr("a := -7 / 2; b := -7 MOD 2; c := 7 MOD -2; d := 5 MOD 0; e := 7 / 2;",
               "a, b, c, d, e : INT;")
    assert (p.leer("a"), p.leer("b"), p.leer("c"), p.leer("d"), p.leer("e")) == \
        (-3, -1, 1, 0, 3)


def test_division_entera_por_cero_para_el_plc_y_la_real_da_infinito():
    p = correr("r := 1.0 / z; x := 1 / cero;", "r : REAL; z : REAL; x, cero : INT;")
    assert math.isinf(p.leer("r"))
    assert p.estado == STOP and p.falla["tipo"] == "division"


def test_desborde_de_int_y_dint_da_la_vuelta():
    p = correr("a := a + 1; b := b * 2; c := -c;",
               "a : INT := 32767; b : DINT := 2147483647; c : INT := -32768;")
    assert (p.leer("a"), p.leer("b"), p.leer("c")) == (-32768, -2, -32768)


def test_conversiones():
    p = correr("""
    r := INT_TO_REAL(i); a := REAL_TO_INT(2.5); b := REAL_TO_INT(-2.5); c := TRUNC(-2.7);
    d := DINT_TO_INT(70000); e := BOOL_TO_INT(TRUE); f := TIME_TO_DINT(T#2s);
    g := DINT_TO_TIME(1500); h := INT_TO_BOOL(3); k := DINT_TO_REAL(dd);
    """, "r, k : REAL; i : INT := 3; a, b, d, e : INT; c, f, dd : DINT; g : TIME; h : BOOL;")
    assert p.leer("r") == 3.0 and isinstance(p.leer("r"), float)
    assert (p.leer("a"), p.leer("b"), p.leer("c")) == (3, -3, -2)
    assert (p.leer("d"), p.leer("e"), p.leer("f"), p.leer("g")) == (4464, 1, 2000, 1500)
    assert p.leer("h") is True and p.leer("k") == 0.0


def test_funciones_estandar():
    p = correr("""
    a := ABS(-5); b := SQRT(16.0); c := MIN(4, 2, 9); d := MAX(T#1s, T#3s);
    e := LIMIT(0, 150, 100); f := SEL(TRUE, 1, 2); g := SQRT(-1.0);
    """, "a, c, e, f : INT; b, g : REAL; d : TIME;")
    assert (p.leer("a"), p.leer("b"), p.leer("c"), p.leer("d")) == (5, 4.0, 2, 3000)
    assert (p.leer("e"), p.leer("f")) == (100, 2) and math.isnan(p.leer("g"))


def test_aritmetica_de_tiempo():
    p = correr("a := T#1s + T#500ms; b := T#2s * 3; c := T#3s / 2; d := T#1s * 1.5;"
               " x := a > T#1s;", "a, b, c, d : TIME; x : BOOL;")
    assert (p.leer("a"), p.leer("b"), p.leer("c"), p.leer("d")) == (1500, 6000, 1500, 1500)
    assert p.leer("x") is True


def test_real_mezcla_con_int_y_no_crece_como_entero():
    p = correr("r := r * 10 + i;", "r : REAL := 1.0; i : INT := 2;", scans=400)
    assert isinstance(p.leer("r"), float) and math.isinf(p.leer("r"))


def test_comentarios_y_mayusculas_minusculas():
    p = correr("""
    (* comentario
       de varias líneas *)
    // de línea
    /* estilo C */
    X := x + 1; (* en medio *) x := X + 1;
    """, "x : int;")
    assert p.leer("x") == 2


def test_var_global_en_program_visible_desde_un_fb_y_otro_program():
    fuente = """
    FUNCTION_BLOCK Sumar
    VAR_INPUT k : INT; END_VAR
    total := total + k;
    END_FUNCTION_BLOCK
    PROGRAM A
    VAR_GLOBAL total : INT; END_VAR
    VAR s : Sumar; END_VAR
    s(k := 2);
    END_PROGRAM
    PROGRAM B
    VAR copia : INT; END_VAR
    copia := total;
    END_PROGRAM"""
    plc = PLC(compilar(fuente))
    plc.scan(0)
    plc.scan(10)
    assert plc.leer("total") == 4 and plc.leer("B.copia") == 4


def test_direcciones_directas_en_el_codigo_sin_declarar():
    plc = PLC(compilar("PROGRAM Main\n%QX0.1 := %IX0.3 AND NOT %IX0.4;\nEND_PROGRAM"))
    plc.escribir_entrada("I0.3", True)
    plc.scan(0)
    assert plc.salidas == {"Q0.1": True}
    assert plc.leer("%IX0.3") is True


def test_entrada_analogica_como_int():
    fuente = """
    VAR_GLOBAL nivel AT %IW0 : INT; pct : REAL; END_VAR
    PROGRAM Main
    pct := INT_TO_REAL(nivel) * 100.0 / 27648.0;
    END_PROGRAM"""
    plc = PLC(compilar(fuente))
    plc.escribir_entrada("AI0", 13824)
    plc.scan(0)
    assert plc.leer("pct") == 50.0
    plc.escribir_entrada("AI0", 99999)              # el conversor no entrega más que un INT
    plc.scan(10)
    assert plc.leer("nivel") == 32767


def test_varios_programas_con_su_ciclo():
    fuente = """
    PROGRAM Rapido VAR n : DINT; END_VAR n := n + 1; END_PROGRAM
    PROGRAM Lento VAR n : DINT; END_VAR n := n + 1; END_PROGRAM"""
    plc = PLC(compilar(fuente), ciclos={"Rapido": 10, "Lento": 50})
    for t in range(0, 1000, 2):
        plc.paso(t)
    assert plc.leer("Rapido.n") == 100 and plc.leer("Lento.n") == 20
