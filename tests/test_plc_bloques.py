"""Bloques estándar contra IEC 61131-3 (3.ª ed., tablas 43–46) con reloj virtual.

Se prueban los diagramas de tiempo de la norma llamando la función del bloque con `t` en ms
(así cada borde es exacto) y, al final, los mismos bloques desde un programa ST en scans de
10 ms.
"""

from __future__ import annotations

from apolo.plc import PLC, compilar
from apolo.plc import bloques as B


def _ton(s, t, entrada):
    s.v_in = entrada
    B.ton(s, t)
    return s.v_q, s.v_et


def test_ton_retardo_a_la_conexion():
    s = B.TON()
    s.v_pt = 500
    assert _ton(s, 0, False) == (False, 0)
    assert _ton(s, 100, True) == (False, 0)
    assert _ton(s, 599, True) == (False, 499)
    assert _ton(s, 600, True) == (True, 500)
    assert _ton(s, 900, True) == (True, 500)       # ET se queda en PT
    assert _ton(s, 901, False) == (False, 0)       # IN en FALSE lo repone


def test_ton_un_pulso_mas_corto_que_pt_no_da_salida_y_reinicia():
    s = B.TON()
    s.v_pt = 500
    _ton(s, 0, True)
    assert _ton(s, 400, False) == (False, 0)
    _ton(s, 450, True)
    assert _ton(s, 900, True) == (False, 450)
    assert _ton(s, 950, True) == (True, 500)


def test_ton_con_pt_cero_conecta_en_el_mismo_scan():
    s = B.TON()
    assert _ton(s, 10, True) == (True, 0)


def _tof(s, t, entrada):
    s.v_in = entrada
    B.tof(s, t)
    return s.v_q, s.v_et


def test_tof_retardo_a_la_desconexion():
    s = B.TOF()
    s.v_pt = 300
    assert _tof(s, 0, False) == (False, 0)          # arranca en FALSE: no hay flanco
    assert _tof(s, 50, True) == (True, 0)
    assert _tof(s, 100, False) == (True, 0)
    assert _tof(s, 399, False) == (True, 299)
    assert _tof(s, 400, False) == (False, 300)
    assert _tof(s, 800, False) == (False, 300)      # ET se queda en PT hasta que IN suba
    assert _tof(s, 810, True) == (True, 0)


def test_tof_reengancha_si_in_vuelve_antes_de_pt():
    s = B.TOF()
    s.v_pt = 300
    _tof(s, 0, True)
    _tof(s, 100, False)
    assert _tof(s, 200, True) == (True, 0)
    assert _tof(s, 300, False) == (True, 0)         # nuevo flanco: cuenta desde 300
    assert _tof(s, 599, False) == (True, 299)
    assert _tof(s, 600, False) == (False, 300)


def _tp(s, t, entrada):
    s.v_in = entrada
    B.tp(s, t)
    return s.v_q, s.v_et


def test_tp_pulso_de_duracion_fija():
    s = B.TP()
    s.v_pt = 300
    assert _tp(s, 0, False) == (False, 0)
    assert _tp(s, 100, True) == (True, 0)
    assert _tp(s, 399, True) == (True, 299)
    assert _tp(s, 400, True) == (False, 300)        # IN sigue alto: ET se queda en PT
    assert _tp(s, 500, False) == (False, 0)


def test_tp_no_se_redispara_durante_el_pulso_y_dura_aunque_in_baje():
    s = B.TP()
    s.v_pt = 300
    _tp(s, 100, True)
    assert _tp(s, 150, False) == (True, 50)
    assert _tp(s, 200, True) == (True, 100)         # flanco ignorado
    assert _tp(s, 400, True) == (False, 300)        # termina a los 300 del PRIMER flanco
    assert _tp(s, 410, False) == (False, 0)
    assert _tp(s, 420, True) == (True, 0)           # nuevo flanco, nuevo pulso


def _llamar(f, bloque, **entradas):
    for k, v in entradas.items():
        setattr(bloque, "v_" + k, v)
    f(bloque, 0)


def test_ctu_cuenta_flancos_reset_con_prioridad_y_satura():
    s = B.CTU()
    s.v_pv = 3
    for cu in (True, True, False, True, False, True):
        _llamar(B.ctu, s, cu=cu, r=False)
    assert s.v_cv == 3 and s.v_q is True             # tres flancos, no tres scans en TRUE
    _llamar(B.ctu, s, cu=False, r=True)
    assert s.v_cv == 0 and s.v_q is False
    _llamar(B.ctu, s, cu=True, r=True)                # R gana al flanco
    assert s.v_cv == 0
    s.v_cv = 32767
    _llamar(B.ctu, s, cu=False, r=False)
    _llamar(B.ctu, s, cu=True, r=False)
    assert s.v_cv == 32767                            # PVmax


def test_ctd_carga_cuenta_hacia_abajo_y_satura():
    s = B.CTD()
    _llamar(B.ctd, s, ld=True, pv=2, cd=False)
    assert s.v_cv == 2 and s.v_q is False
    for cd in (True, False, True):
        _llamar(B.ctd, s, ld=False, cd=cd)
    assert s.v_cv == 0 and s.v_q is True
    s.v_cv = -32768
    _llamar(B.ctd, s, cd=False)
    _llamar(B.ctd, s, cd=True)
    assert s.v_cv == -32768                           # PVmin


def test_ctud_arriba_abajo_simultaneo_y_prioridades():
    s = B.CTUD()
    s.v_pv = 2
    _llamar(B.ctud, s, cu=True)
    _llamar(B.ctud, s, cu=False)
    _llamar(B.ctud, s, cu=True)
    assert s.v_cv == 2 and s.v_qu is True and s.v_qd is False
    _llamar(B.ctud, s, cu=False, cd=False)
    _llamar(B.ctud, s, cu=True, cd=True)              # los dos a la vez: no cambia
    assert s.v_cv == 2
    _llamar(B.ctud, s, cu=False, cd=False)
    _llamar(B.ctud, s, cd=True)
    assert s.v_cv == 1
    _llamar(B.ctud, s, r=True, ld=True)               # R gana a LD
    assert s.v_cv == 0 and s.v_qd is True
    _llamar(B.ctud, s, r=False, ld=True)
    assert s.v_cv == 2


def test_r_trig_y_f_trig():
    r, f = B.R_TRIG(), B.F_TRIG()
    salidas_r, salidas_f = [], []
    for clk in (True, True, False, False, True, False):
        _llamar(B.r_trig, r, clk=clk)
        _llamar(B.f_trig, f, clk=clk)
        salidas_r.append(r.v_q)
        salidas_f.append(f.v_q)
    assert salidas_r == [True, False, False, False, True, False]   # CLK TRUE al arrancar: pulso
    assert salidas_f == [False, False, True, False, False, True]
    f2 = B.F_TRIG()
    _llamar(B.f_trig, f2, clk=False)
    assert f2.v_q is False                            # sin pulso falso al arrancar


def test_sr_prioridad_set_y_rs_prioridad_reset():
    sr, rs = B.SR(), B.RS()
    _llamar(B.sr, sr, s1=True, r=True)
    _llamar(B.rs, rs, s=True, r1=True)
    assert sr.v_q1 is True and rs.v_q1 is False
    _llamar(B.sr, sr, s1=False, r=False)
    _llamar(B.rs, rs, s=True, r1=False)
    _llamar(B.rs, rs, s=False, r1=False)
    assert sr.v_q1 is True and rs.v_q1 is True        # memoria
    _llamar(B.sr, sr, r=True)
    assert sr.v_q1 is False


def test_los_bloques_desde_st_en_scans_de_10_ms():
    fuente = """
    PROGRAM Main
    VAR
      in : BOOL; t_on : TON; t_off : TOF; pulso : TP; cuenta : CTU; bajar : CTD;
      ud : CTUD; sube : R_TRIG; baja : F_TRIG; mem : SR; mem2 : RS;
      q_on, q_off, q_p, flancos : BOOL; ns, nb : INT;
    END_VAR
    t_on(IN := in, PT := T#50ms, Q => q_on);
    t_off(IN := in, PT := T#30ms, Q => q_off);
    pulso(IN := in, PT := T#20ms, Q => q_p);
    sube(CLK := in);
    baja(CLK := in);
    IF sube.Q THEN ns := ns + 1; END_IF;
    IF baja.Q THEN nb := nb + 1; END_IF;
    cuenta(CU := in, R := FALSE, PV := 2);
    bajar(CD := in, LD := FALSE, PV := 0);
    ud(CU := in, CD := FALSE, R := FALSE, LD := FALSE, PV := 5);
    mem(S1 := in, R := NOT in);
    mem2(S := in, R1 := NOT in);
    END_PROGRAM"""
    plc = PLC(compilar(fuente), ciclo_ms=10)
    inst = plc.tareas[0].instancia
    trazas = []
    for t in range(0, 200, 10):
        inst.v_in = 30 <= t < 110          # IN en TRUE de 30 a 100 ms
        plc.paso(t)
        trazas.append((t, plc.leer("q_on"), plc.leer("q_off"), plc.leer("q_p")))
    on = [t for t, q, _, _ in trazas if q]
    off = [t for t, _, q, _ in trazas if q]
    pulso = [t for t, _, _, q in trazas if q]
    assert on == [80, 90, 100]                 # 30 + 50
    assert off == list(range(30, 140, 10))     # hasta 110 + 30 (exclusive)
    assert pulso == [30, 40]                   # 20 ms desde 30
    assert plc.leer("ns") == 1 and plc.leer("nb") == 1
    assert plc.leer("Main.cuenta.CV") == 1 and plc.leer("Main.bajar.CV") == -1
    assert plc.leer("Main.ud.CV") == 1
    assert plc.leer("Main.mem.Q1") is False and plc.leer("Main.mem2.Q1") is False
