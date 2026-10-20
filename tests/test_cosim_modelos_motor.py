"""Motor de la co-simulación contra su PLACA del catálogo (plan V8.3 F2, D7, D8): rpm y par
nominales, Tk, el par por FLUJO (Φ/Φn = (U/f)/(Un/fn)) a 30 Hz en V/f, la corriente y el
adaptador de las claves del catálogo a la `placa` de V8.2 (`kloss_linealizado`)."""

from __future__ import annotations

import math

import pytest

from apolo.cosim.modelos import ModeloIncompleto, crear_modelo, placa_v82
from apolo.library.catalog import CATALOG, refs_in_category
from apolo.library.engineering.motor_induccion import inercia_rotor_estimada, kloss_linealizado

MOTORES = ["MOTOR-037", "MOTOR-075", "MOTOR-150", "MOTOR-150-EH"] + refs_in_category("motorreductores_sinfin")
DT = 0.002


def motor(ref: str = "NMRV-090", **ajustes):
    if CATALOG[ref].electrico.modelo.get("i") == [7.5, 100]:
        ajustes = {"i": 30, "eta_reductor": 0.75, **ajustes}
    return crear_modelo("-M1", ref, CATALOG[ref].electrico.modelo, ajustes)


@pytest.mark.parametrize("ref", MOTORES)
def test_reproduce_rpm_y_par_nominales_y_su_tk(ref):
    m = motor(ref)
    placa = CATALOG[ref].electrico.modelo
    Tn = placa["P_kW"] * 1000 / (placa["n_rpm"] * 2 * math.pi / 60)
    assert m.par(m.Un, m.fn, placa["n_rpm"]) == pytest.approx(Tn, rel=1e-9)
    # el máximo de la curva es Tk = Tk_Tn·Tn, en el deslizamiento sk
    rpms = [m.ns * (1 - s / 2000) for s in range(1, 2000)]
    pico = max(m.par(m.Un, m.fn, r) for r in rpms)
    assert pico == pytest.approx(placa["Tk_Tn"] * Tn, rel=1e-3)
    assert m.corriente(m.Un, m.fn, Tn, placa["n_rpm"]) == pytest.approx(m.In)
    assert m.corriente(m.Un, m.fn, 0.0, m.ns) == pytest.approx(m.I0)
    # rotor bloqueado en directo: Ia = Ia_In·In
    assert m.corriente(m.Un, m.fn, m.par(m.Un, m.fn, 0), 0) == pytest.approx(placa["Ia_In"] * m.In)


def test_par_por_flujo_a_30_hz_en_v_f_es_el_nominal():
    m = motor()
    rpm_30 = m.ns * 30 / 60 - (m.ns - m.nn)  # misma velocidad de deslizamiento que la nominal
    assert m.flujo(m.Un / 2, 30) == pytest.approx(1.0)
    assert m.par(m.Un / 2, 30, rpm_30) == pytest.approx(m.Tn, rel=1e-9)
    a30, a60 = m.actuador(m.Un / 2, 30), m.actuador(m.Un, 60)
    assert a30["forcerange_Nm"] == pytest.approx(a60["forcerange_Nm"])
    assert a30["kv"] == pytest.approx(a60["kv"]) and a30["ctrl_rad_s"] == pytest.approx(a60["ctrl_rad_s"] / 2)
    # arranque directo con 10 % de caída: k = 0,81; debilitamiento a 90 Hz: k = (60/90)²
    assert m.actuador(0.9 * m.Un, 60)["k"] == pytest.approx(0.81)
    assert m.actuador(m.Un, 90)["forcerange_Nm"] == pytest.approx(a60["forcerange_Nm"] * (60 / 90) ** 2)
    # sin tensión: k = 0, el eje queda libre (lo frenan su carga y la fricción del reductor)
    libre = m.actuador(0.0, 60)
    assert libre["kv"] == 0 and libre["forcerange_Nm"] == 0 and libre["friccion_Nm"] > 0


@pytest.mark.parametrize("ref", MOTORES)
def test_lo_mismo_que_kloss_linealizado_de_v8_2_por_el_adaptador(ref):
    m = motor(ref)
    placa = placa_v82(CATALOG[ref].electrico.modelo)
    assert set(placa) == {"potencia_kW", "rpm", "frecuencia_hz", "polos", "tk_tn", "inercia_rotor_kgm2"}
    k = kloss_linealizado(placa, m.i, m.eta_red)
    assert k["hipotesis"] == []  # la placa del catálogo ya no deja nada por suponer
    a = m.actuador(m.Un, m.fn)
    assert a["kv"] == pytest.approx(k["kv"], rel=1e-12)
    assert a["forcerange_Nm"] == pytest.approx(k["par_max_Nm"], rel=1e-12)
    assert a["ctrl_rad_s"] == pytest.approx(k["omega_sinc_rad_s"], rel=1e-12)
    assert (m.Tn, m.Tk, m.sn, m.sk) == pytest.approx((k["Tn_Nm"], k["Tk_Nm"], k["sn"], k["sk"]), rel=1e-12)
    assert m.J * m.i ** 2 == pytest.approx(k["inercia_reflejada_kgm2"])


def test_adaptador_no_inventa():
    assert placa_v82({"P_kW": 1.5, "n_rpm": 1720}) == {"potencia_kW": 1.5, "rpm": 1720}
    with pytest.raises(ModeloIncompleto, match="falta «n_rpm»"):
        placa_v82({"P_kW": 1.5})


@pytest.mark.parametrize("ref", MOTORES)
def test_datos_nuevos_de_la_placa_son_fisicos(ref):
    p = CATALOG[ref].electrico.modelo
    sen_phi = math.sqrt(1 - p["cos_phi"] ** 2)
    assert 0 < p["I0_A"] < p["In_A"] * sen_phi, ref  # la de vacío no pasa la reactiva a plena carga
    assert 0.5 <= p["J_kgm2"] / inercia_rotor_estimada(p["P_kW"]) <= 2.0, ref


def test_reductor_del_nmrv_es_ajuste_obligatorio():
    modelo = CATALOG["NMRV-090"].electrico.modelo
    with pytest.raises(ModeloIncompleto, match=r"-M1 \(NMRV-090\): falta el ajuste «i».*entre 7\.5 y 100"):
        crear_modelo("-M1", "NMRV-090", modelo, {})
    with pytest.raises(ModeloIncompleto, match="falta el ajuste «eta_reductor»"):
        crear_modelo("-M1", "NMRV-090", modelo, {"i": 30})
    helicoidal = motor("MOTOR-075")
    assert helicoidal.i == pytest.approx(1700 / 60, rel=0.01) and helicoidal.eta_red == 0.94


def test_conexion_estrella_dobla_la_tension_por_raiz_de_3():
    tri, est = motor("MOTOR-075"), motor("MOTOR-075", conexion="estrella")
    assert est.Un == pytest.approx(tri.Un * math.sqrt(3)) and est.In == pytest.approx(tri.In / math.sqrt(3))
    assert est.Tn == pytest.approx(tri.Tn)


def test_paso_traduce_el_par_de_la_junta_a_par_y_corriente_del_motor():
    m = motor()
    w_out = m.nn * 2 * math.pi / 60 / m.i
    T_out = m.Tn * m.i * m.eta_red
    s = m.paso(DT, {"U_V": m.Un, "f_Hz": 60, "omega_salida_rad_s": w_out, "par_salida_Nm": T_out})
    assert s["rpm"] == pytest.approx(m.nn) and s["par_Nm"] == pytest.approx(m.Tn) and s["I_A"] == pytest.approx(m.In)
    assert set(m.senales()) >= {"-M1.rpm", "-M1.par_Nm", "-M1.I_A"}
    # pérdida de una fase en marcha: √3 de corriente; detenido no arranca
    s2 = m.paso(DT, {"U_V": m.Un, "f_Hz": 60, "omega_salida_rad_s": w_out, "par_salida_Nm": T_out, "fases": 2})
    assert s2["I_A"] == pytest.approx(math.sqrt(3) * m.In)
    assert m.actuador_fases(m.Un, 60, 2, 0.0)["forcerange_Nm"] == 0
    assert m.actuador_fases(m.Un, 60, 2, w_out)["forcerange_Nm"] > 0
    assert any("fricción del reductor" in h for h in m.hipotesis)
