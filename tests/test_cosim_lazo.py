"""La máquina en lazo cerrado (plan V8.3 F4, D8 y D9): red → tablero → PLC → variador o
contactor → motor → MuJoCo → fotocelda → PLC, sobre una faja pequeña (`cosim_lazo_banco.py`).

  - el PLC con marcha/paro en ST arranca el variador, que rampa en su tiempo, y la banda llega a
    la velocidad que da el motor (ωs(1 − s)/i·r);
  - la seta corta el par en < 0,5 s, por el STO del variador y por el contactor del arranque
    directo, y liberarla no rearranca;
  - un atasco frena el tambor, la corriente sube a la de rotor casi bloqueado y el guardamotor
    dispara por térmico en el tiempo de su curva de clase 10 (IEC 60947-4-1);
  - el corte de una fase queda registrado y el variador falla por pérdida de fase en su tiempo.
"""

import math

import pytest

pytest.importorskip("mujoco")

from apolo.cosim.modelos.protecciones import BANDA_CLASE, TP_7_2  # noqa: E402
from apolo.cosim.planificador import AVISO, correr  # noqa: E402
from apolo.cosim.tablero import Tablero  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from cosim_lazo_banco import (  # noqa: E402
    JUNTA,
    PROGRAMAS,
    cambios,
    en,
    escenario_directo,
    escenario_variador,
    faja_directo,
    faja_variador,
    primer_cambio,
    serie,
)

DT = 0.002


@pytest.fixture(scope="module")
def variador():
    return faja_variador()


@pytest.fixture(scope="module")
def directo():
    return faja_directo()


def test_el_plc_arranca_el_variador_la_banda_llega_a_su_velocidad_y_la_seta_corta_el_par(variador):
    esc = escenario_variador(4.0, acciones=[{"t": 2.5, "accion": "presionar", "dispositivo": "-S0"},
                                            {"t": 3.0, "accion": "liberar", "dispositivo": "-S0"}])
    snap = snapshot_cosim(variador, esc, programas=PROGRAMAS)
    res = correr(snap)
    assert res["aviso"] == AVISO
    # el PLC ve la marcha tras su filtro de entrada y cierra Q0.0 → DI1 del variador
    t_marcha = primer_cambio(res, "-K1.Main.en_marcha", True)
    assert 0.3 < t_marcha < 0.33
    assert primer_cambio(res, "-K1.%QX0.0", True) == pytest.approx(t_marcha, abs=0.005)
    # rampa de 0 a 60 Hz en el acel_s de 1 s
    f = serie(res, "-T2.f_Hz")
    t60 = next(t for t, v in f if v >= 59.9)
    assert t60 - t_marcha == pytest.approx(1.0, abs=0.03)
    assert en(res, "-T2.f_Hz", t_marcha + 0.5) == pytest.approx(30.0, abs=1.5)
    # la banda llega a la velocidad del motor: casi síncrono en vacío, ωs(1 − s)/i·r
    m = Tablero(snap.red, snap.dispositivos).modelos["-M1"]
    rpm = en(res, "-M1.rpm", 2.4)
    assert 0.99 * m.ns < rpm < m.ns
    r = snap.dinamica.bandas[0].radio
    v = en(res, "c1_banda.v_m_s", 2.4)
    assert v == pytest.approx(rpm / m.i * 2 * math.pi / 60 * r, rel=2e-3)
    assert en(res, "-M1.par_Nm", 2.4) > 0 and en(res, "-M1.I_A", 2.4) == pytest.approx(m.I0, rel=0.1)
    # seta: el STO actúa en su tiempo y el par cae a cero en < 0,5 s; liberarla NO rearranca
    t_sto = primer_cambio(res, "-T2.sto", True)
    assert 2.5 < t_sto < 2.5 + 0.02
    t_cero = next(t for t, p in serie(res, "-M1.par_Nm") if t >= 2.5 and abs(p) < 1e-9)
    assert t_cero - 2.5 < 0.5
    assert cambios(res, "-K1.Main.en_marcha")[-1] == [pytest.approx(2.51, abs=0.01), False]
    assert res["final"]["-T2.f_Hz"] == 0.0 and not res["final"]["-K1.Main.en_marcha"]
    assert res["final"]["c1_banda.v_m_s"] < v  # gira libre y frena por su carga
    # la red de potencia sólo se re-resuelve mientras algo cambia (la rampa), no en régimen
    r_ = res["resumen"]
    assert r_["resoluciones_potencia"] < 0.5 * r_["intercambios"]
    assert not res["plc"]["-K1"]["fallas"]


def test_la_seta_del_arranque_directo_abre_el_contactor_y_corta_el_par(directo):
    esc = escenario_directo(2.2, acciones=[{"t": 1.5, "accion": "presionar", "dispositivo": "-S0"}])
    res = correr(snapshot_cosim(directo, esc))
    assert primer_cambio(res, "-Q3.cerrado", True) == pytest.approx(0.2 + 0.063, abs=0.004)  # cierre_ms
    assert en(res, "-M1.rpm", 1.4) > 1700
    t_abre = primer_cambio(res, "-Q3.cerrado", False, desde=1.0)
    assert t_abre - 1.5 == pytest.approx(0.020, abs=0.004)  # apertura_ms del contactor
    t_cero = next(t for t, p in serie(res, "-M1.par_Nm") if t >= 1.5 and abs(p) < 1e-9)
    assert t_cero - 1.5 < 0.5
    assert not res["final"]["-P1.encendido"]


def test_una_caida_de_red_suelta_el_contactor_y_al_volver_no_rearranca(directo):
    """La fuente de 24 V retiene 20 ms; un hueco de 0,2 s deja la bobina sin tensión, el contactor
    cae y pierde su autorretención: al volver la red el motor queda parado (como un tablero real
    sin rearme automático). Un hueco más corto que la retención no hace nada."""
    esc = escenario_directo(2.5, eventos=[{"t": 1.0, "tipo": "caida_de_red", "factor": 0.0, "duracion_s": 0.2},
                                          {"t": 1.8, "tipo": "caida_de_red", "factor": 0.0, "duracion_s": 0.01}])
    res = correr(snapshot_cosim(directo, esc))
    assert [e["evento"] for e in res["eventos"] if "evento" in e] == [
        "caida_de_red", "caida_de_red.fin", "caida_de_red", "caida_de_red.fin"]
    t_sin_24 = primer_cambio(res, "-T1.ok", False, desde=1.0)  # el DC OK de la fuente
    assert t_sin_24 - 1.0 == pytest.approx(0.020, abs=DT + 1e-9)  # su retención de 20 ms
    t_abre = primer_cambio(res, "-Q3.cerrado", False, desde=1.0)
    assert t_sin_24 < t_abre < t_sin_24 + 0.03  # la apertura del contactor
    assert primer_cambio(res, "-T1.ok", False, desde=1.5) is None  # el hueco de 10 ms no se nota
    assert res["final"]["-T1.U_V"] == pytest.approx(24.0) and not res["final"]["-Q3.cerrado"]
    assert res["final"]["-M1.I_A"] == 0.0


def test_un_atasco_dispara_el_guardamotor_en_su_tiempo_de_norma(directo):
    """Con el tambor trabado el motor queda en la zona inestable de Kloss, casi a rotor
    bloqueado: la corriente sube hacia Ia y la imagen térmica de clase 10 dispara en su t(x)."""
    t_atasco = 1.0
    esc = escenario_directo(17.0, eventos=[{"t": t_atasco, "tipo": "atasco", "junta": JUNTA, "par_Nm": 500}])
    snap = snapshot_cosim(directo, esc)
    res = correr(snap)
    gm = Tablero(snap.red, snap.dispositivos).modelos["-Q2"]
    m = Tablero(snap.red, snap.dispositivos).modelos["-M1"]
    I = en(res, "-M1.I_A", 5.0)
    assert 0.8 * m.Ia_In * m.In < I < m.Ia_In * m.In  # casi a rotor bloqueado
    assert en(res, "-M1.rpm", 5.0) < 0.05 * m.ns
    t_disparo = primer_cambio(res, "-Q2.disparado", True)
    assert t_disparo is not None and cambios(res, "-Q2.causa")[-1][1] == "térmico"
    theta0 = en(res, "-Q2.termico_pct", t_atasco) / 100 * gm.termico.k2
    esperado = gm.termico.t_disparo(I / gm.nominal, theta0)
    assert t_disparo - t_atasco == pytest.approx(esperado, rel=0.02)
    lo, hi = BANDA_CLASE[gm.clase]
    tp = gm.termico.t_disparo(7.2)  # la misma imagen, en el punto de la norma: clase 10 a 7,2 Ir
    assert tp == pytest.approx(TP_7_2[gm.clase]) and lo <= tp <= hi
    # disparado, el motor queda sin tensión
    assert res["final"]["-M1.I_A"] == 0.0 and res["final"]["-Q2.disparado"]


def test_el_corte_de_fase_queda_registrado_y_el_variador_falla_en_su_tiempo(variador):
    esc = escenario_variador(3.5, eventos=[{"t": 2.0, "tipo": "corte_de_fase", "fase": "L3"}])
    snap = snapshot_cosim(variador, esc, programas=PROGRAMAS)
    res = correr(snap)
    [corte] = [e for e in res["eventos"] if e.get("evento") == "corte_de_fase"]
    assert corte["t"] == 2.0 and corte["fase"] == "L3"
    vfd = Tablero(snap.red, snap.dispositivos).modelos["-T2"]
    t_falla = primer_cambio(res, "-T2.falla", "perdida_fase")
    assert t_falla - 2.0 == pytest.approx(vfd.t_fase, abs=2 * DT)
    # el relé de falla llega al PLC (I0.4), que suelta la marcha
    assert primer_cambio(res, "-K1.%IX0.4", True) == pytest.approx(t_falla, abs=0.012)
    assert not res["final"]["-K1.Main.en_marcha"] and res["final"]["-T2.estado"] == "falla"
    # la fuente de 24 V cuelga de L1–L2: el mando sigue vivo
    assert res["final"]["-T1.U_V"] == pytest.approx(24.0)
