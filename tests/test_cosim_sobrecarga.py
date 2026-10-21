"""La sobrecarga TÉRMICA en lazo cerrado con un atasco PARCIAL (plan V8.3 F6, defecto 6).

La FAT de la faja 73 trabó el tambor con 1500 N·m: la corriente saltó al disparo INSTANTÁNEO
(sobrecorriente del variador) y la curva térmica no se ejercitó. Aquí el atasco FRENA sin trabar
(`cosim_lazo_banco.atasco_parcial`): el motor sigue girando en la parte estable de su curva con la
corriente en la zona térmica, y se compara lo que da el lazo con la curva analítica de la imagen:

  - variador (150 % durante 60 s de placa, I²t de primer orden): con la placa REAL dispararía en
    ~6 min de simulación; el banco la ajusta a `sobrecarga_s` = 1 s (la forma no cambia: t escala
    con `sobrecarga_s`) y la falla es «sobrecarga», no «sobrecorriente», en el t(x, θ0) de su
    imagen; el relé de falla llega al PLC, que suelta la marcha;
  - guardamotor clase 10 en arranque directo (1,5 × Ir): la imagen sigue θ(t) = x² + (θ0 − x²)·
    e^(−t/τ) en el lazo; el disparo queda a ~3,5 min y una corrida llega a 60 s, así que el
    disparo mismo (con el dial más bajo, ~49 s) va en `-m torture`.
"""

import math

import pytest

pytest.importorskip("mujoco")

from apolo.cosim.modelos.variador import _SOBRECARGA_K2  # noqa: E402
from apolo.cosim.planificador import correr  # noqa: E402
from apolo.cosim.tablero import Tablero  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from cosim_lazo_banco import (  # noqa: E402
    PAR_PARCIAL_DIRECTO_NM,
    PAR_PARCIAL_VARIADOR_NM,
    PROGRAMAS,
    atasco_parcial,
    cambios,
    en,
    escenario_directo,
    escenario_variador,
    faja_directo,
    faja_variador,
    primer_cambio,
)

T_ATASCO = 1.5


def test_el_variador_dispara_por_sobrecarga_termica_en_su_curva():
    doc = faja_variador(sobrecarga_s=1.0)
    esc = escenario_variador(8.0, eventos=[atasco_parcial(T_ATASCO, PAR_PARCIAL_VARIADOR_NM)])
    snap = snapshot_cosim(doc, esc, programas=PROGRAMAS)
    res = correr(snap)
    tab = Tablero(snap.red, snap.dispositivos)
    vfd, m = tab.modelos["-T2"], tab.modelos["-M1"]
    # la curva pasa por el punto de placa: 150 % durante sobrecarga_s desde régimen (θ = 1)
    assert vfd.tau_sc * math.log((1.5 ** 2 - 1) / (1.5 ** 2 - _SOBRECARGA_K2)) == pytest.approx(1.0)
    # atasco PARCIAL: el motor sigue girando, la corriente en la zona térmica, sin límite ni pico
    t_med = T_ATASCO + 1.5
    I, rpm = en(res, "-M1.I_A", t_med), en(res, "-M1.rpm", t_med)
    x = I / vfd.In
    assert rpm > 0.85 * m.ns and 1.2 < x < vfd.I_lim / vfd.In
    assert cambios(res, "-T2.limitando") == [[0.0, False]]
    # falla por SOBRECARGA (no la instantánea) en el t(x) de la imagen desde el θ0 del atasco
    t_falla = primer_cambio(res, "-T2.falla", "sobrecarga")
    assert t_falla is not None and primer_cambio(res, "-T2.falla", "sobrecorriente") is None
    theta0 = en(res, "-T2.termico_pct", T_ATASCO - 0.02) / 100 * _SOBRECARGA_K2
    esperado = vfd.tau_sc * math.log((x * x - theta0) / (x * x - _SOBRECARGA_K2))
    assert t_falla - T_ATASCO == pytest.approx(esperado, rel=0.02)
    # el relé de falla llega al PLC (I0.4) y el programa suelta la marcha
    assert primer_cambio(res, "-K1.%IX0.4", True) == pytest.approx(t_falla, abs=0.012)
    assert not res["final"]["-K1.Main.en_marcha"] and res["final"]["-T2.estado"] == "falla"


def _directo_parcial(duracion_s: float, guardamotor=None):
    snap = snapshot_cosim(faja_directo(guardamotor), escenario_directo(
        duracion_s, eventos=[atasco_parcial(T_ATASCO, PAR_PARCIAL_DIRECTO_NM)]))
    tab = Tablero(snap.red, snap.dispositivos)
    return correr(snap), tab.modelos["-Q2"], tab.modelos["-M1"]


def test_el_guardamotor_sigue_su_imagen_termica_con_un_atasco_parcial():
    """θ medido en el lazo contra θ(t) analítico con la corriente del lazo: es la misma curva de
    clase 10 que dispara el atasco franco de `test_cosim_lazo.py` en su t(x)."""
    res, gm, m = _directo_parcial(6.0)
    a, b = T_ATASCO + 1.0, 5.9
    I = en(res, "-M1.I_A", a)
    assert en(res, "-M1.I_A", b) == pytest.approx(I, rel=1e-3)  # régimen: el motor no se traba
    assert en(res, "-M1.rpm", b) > 0.8 * m.ns
    x = I / gm.nominal
    assert 1.3 < x < 2.0 and x * x > gm.termico.k2  # en la zona térmica: va a disparar
    th_a = en(res, "-Q2.termico_pct", a) / 100 * gm.termico.k2
    th_b = en(res, "-Q2.termico_pct", b) / 100 * gm.termico.k2
    assert th_b == pytest.approx(x * x + (th_a - x * x) * math.exp(-(b - a) / gm.termico.tau), rel=0.01)
    assert not res["final"]["-Q2.disparado"]
    # y lo que falta para disparar, por la misma imagen, cae en la banda de clase 10 a 1,5 Ir
    # (< 2 min desde CALIENTE, IEC 60947-4-1): aquí arranca casi frío, tarda más
    assert 120 < gm.termico.t_disparo(x, th_b) < 400


@pytest.mark.torture
def test_el_guardamotor_dispara_por_termico_con_el_atasco_parcial():
    """El disparo mismo. A 1,5 × Ir tarda ~3,5 min y una corrida llega a 60 s: con el dial de un
    GM-1.6-2.5A a 1,7 A (bajo la In de 3,18 A, en vacío no dispara: 1,09 × Ir < k) el MISMO
    atasco parcial es ~2,8 × Ir y la clase 10 dispara en ~49 s. Corre aparte con `-m torture`."""
    res, gm, m = _directo_parcial(55.0, guardamotor=("GM-1.6-2.5A", 1.7))
    I = en(res, "-M1.I_A", T_ATASCO + 1.0)
    assert en(res, "-M1.rpm", T_ATASCO + 1.0) > 0.8 * m.ns  # parcial: sigue girando
    theta0 = en(res, "-Q2.termico_pct", T_ATASCO - 0.02) / 100 * gm.termico.k2
    t_disparo = primer_cambio(res, "-Q2.disparado", True)
    assert t_disparo is not None and cambios(res, "-Q2.causa")[-1][1] == "térmico"
    assert t_disparo - T_ATASCO == pytest.approx(gm.termico.t_disparo(I / gm.nominal, theta0), rel=0.02)
    assert res["final"]["-M1.I_A"] == 0.0
