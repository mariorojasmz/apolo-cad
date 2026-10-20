"""Mando de la co-simulación (plan V8.3 F2, D7): contactor y relé (IEC 60947-4-1), PLC con
entradas tipo 1 (IEC 61131-2), fuente con límite, red 1F/2F/3F y los mandos que vuelven por
resorte o quedan retenidos. Con el catálogo real y el intercambio de 2 ms."""

from __future__ import annotations

import cmath
import math

import pytest

from apolo.cosim.modelos import ModeloIncompleto, crear_modelo, direccion_iec
from apolo.library.catalog import CATALOG

DT = 0.002


def modelo(ref: str, des: str = "-K1", **ajustes):
    return crear_modelo(des, ref, CATALOG[ref].electrico.modelo, ajustes)


def correr(m, segundos: float, entradas: dict) -> dict:
    out = {}
    for _ in range(round(segundos / DT)):
        out = m.paso(DT, entradas)
    return out


def t_hasta(m, entradas: dict, cond, t_max: float) -> float | None:
    t = 0.0
    while t < t_max:
        s = m.paso(DT, entradas)
        t += DT
        if cond(s):
            return t
    return None


# ── contactor ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref,uc", [("CONT-9A-24VDC", 24.0), ("CONT-9A-220VAC", 220.0)])
def test_contactor_cierra_desde_85_y_cae_bajo_40_por_ciento(ref, uc):
    m = CATALOG[ref].electrico.modelo
    k = modelo(ref)
    assert t_hasta(k, {"U_bobina_V": 0.84 * uc}, lambda s: s["cerrado"], 0.5) is None
    t = t_hasta(k, {"U_bobina_V": 0.85 * uc}, lambda s: s["cerrado"], 0.5)
    lo, hi = m["cierre_ms"]
    assert lo / 1000 <= t <= hi / 1000 + DT, t  # en la banda de la ficha (su punto medio)
    assert correr(k, 0.5, {"U_bobina_V": 0.41 * uc})["cerrado"]  # 41 %: retiene
    t = t_hasta(k, {"U_bobina_V": 0.39 * uc}, lambda s: not s["cerrado"], 0.5)
    lo, hi = m["apertura_ms"]
    assert lo / 1000 <= t <= hi / 1000 + DT, t
    assert any("punto medio" in h for h in k.hipotesis)


def test_bobina_de_contactor_consume_su_placa():
    dc = modelo("CONT-9A-24VDC")
    assert dc.paso(DT, {"U_bobina_V": 24})["I_bobina_A"] == pytest.approx(2.4 / 24)
    ac = modelo("CONT-9A-220VAC")
    assert ac.paso(DT, {"U_bobina_V": 220})["I_bobina_A"] == pytest.approx(70 / 220)  # llamada
    s = correr(ac, 0.1, {"U_bobina_V": 220})
    assert s["cerrado"] and s["I_bobina_A"] == pytest.approx(7 / 220)  # mantenimiento


def test_contactor_coherente_con_la_tension_de_su_bobina():
    for ref, c in CATALOG.items():
        m = c.electrico.modelo if c.electrico else {}
        if m.get("tipo") not in ("contactor", "rele"):
            continue
        [bobina] = [x for x in c.electrico.cargas if x.tipo == "bobina"]
        assert m["Uc_V"] in bobina.tension.valores, ref
        assert m["Uc"] == bobina.tension.tipo, ref


def test_rele_de_interfaz_opera_con_su_ficha():
    r = modelo("RELE-INT-24VDC", "-K5")
    t = t_hasta(r, {"U_bobina_V": 24}, lambda s: s["cerrado"], 0.1)
    assert 0.005 <= t <= 0.008 + DT
    assert correr(r, 0.1, {"U_bobina_V": 0.3 * 24})["cerrado"]
    assert not correr(r, 0.1, {"U_bobina_V": 0.2 * 24})["cerrado"]


# ── PLC: entradas tipo 1, filtro, analógica, salidas ─────────────────────────────────────────


def test_plc_entradas_tipo_1_con_histeresis_y_filtro():
    plc = modelo("PLC-14DI-10DO-24VDC", "-A1")
    base = {"L+": 24.0}
    assert not correr(plc, 0.05, {**base, "I0.0": 14.9})["%IX0.0"]   # bajo 15 V: OFF
    t = t_hasta(plc, {**base, "I0.0": 15.0}, lambda s: s["%IX0.0"], 0.1)
    assert t == pytest.approx(0.0064, abs=DT)                         # tras el filtro de 6,4 ms
    assert correr(plc, 0.05, {**base, "I0.0": 5.1})["%IX0.0"]         # sobre 5 V: sigue ON
    assert not correr(plc, 0.05, {**base, "I0.0": 5.0})["%IX0.0"]     # ≤ 5 V: OFF
    plc.paso(DT, {**base, "I0.1": 24.0})                              # un pulso de 2 ms
    assert not correr(plc, 0.02, base)["%IX0.1"]                      # no pasa el filtro


def test_plc_analogica_y_salidas():
    plc = modelo("PLC-14DI-10DO-24VDC", "-A1")
    s = plc.paso(DT, {"L+": 24.0, "AI0": 5.0, "AI1": 12.0, "salidas": {"Q0.0": True}})
    assert s["%IW0"] == 13824 and s["%IW1"] == 27648 and s["%QX0.0"] and not s["%QX1.1"]
    s = plc.paso(DT, {"L+": 20.0, "salidas": {"Q0.0": True}})          # bajo 20,4 V: no corre
    assert not s["alimentado"] and not s["%QX0.0"]
    assert set(plc.salidas()) >= {"%IX1.5", "%QX1.1"} and "%IX1.6" not in plc.salidas()
    assert direccion_iec("I1.5") == "%IX1.5" and direccion_iec("AI1") == "%IW1"


# ── fuente de 24 VDC ─────────────────────────────────────────────────────────────────────────


def test_fuente_limita_a_corriente_constante_y_se_recupera():
    f = modelo("FUENTE-24VDC-2.5A", "-T1")
    s = f.paso(DT, {"U_entrada_V": 220, "I_carga_A": 2.0})
    assert s["U_V"] == 24 and s["I_A"] == 2.0 and not s["limitando"] and s["ok"]
    s = f.paso(DT, {"U_entrada_V": 220, "I_carga_A": 6.5})               # cortocircuito parcial
    assert s["limitando"] and s["I_A"] == pytest.approx(1.3 * 2.5)
    assert s["U_V"] == pytest.approx(24 * 3.25 / 6.5) and not s["ok"]
    assert f.paso(DT, {"U_entrada_V": 220, "I_carga_A": 1.0})["U_V"] == 24


def test_fuente_retiene_ante_un_corte_de_la_entrada():
    f = modelo("FUENTE-24VDC-5A", "-T1")
    f.paso(DT, {"U_entrada_V": 220, "I_carga_A": 1})
    assert correr(f, 0.018, {"U_entrada_V": 0, "I_carga_A": 1})["U_V"] == 24   # 18 ms: sostiene
    assert correr(f, 0.004, {"U_entrada_V": 0, "I_carga_A": 1})["U_V"] == 0    # 22 ms: cae


# ── red 1F / 2F / 3F (D15) ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("ref,polos,ll", [("RED-3F-220V-60HZ", {"L1", "L2", "L3"}, ("L1", "L2")),
                                          ("RED-3F-380-220V-60HZ", {"L1", "L2", "L3", "N"}, ("L1", "L2")),
                                          ("RED-2F-220V-60HZ", {"L1", "L2"}, ("L1", "L2")),
                                          ("RED-1F-220V-60HZ", {"L", "N"}, ("L", "N"))])
def test_red_sus_polos_y_su_tension(ref, polos, ll):
    red = modelo(ref, "-G1")
    fz = red.salidas()["fasores"]
    assert set(fz) == polos
    assert abs(fz[ll[0]] - fz[ll[1]]) == pytest.approx(CATALOG[ref].electrico.modelo["U_V"])
    # Zk = Un/(√3·Icc) con su X/R
    m = CATALOG[ref].electrico.modelo
    z = red.salidas()["Z_ohm"]
    assert z.imag / z.real == pytest.approx(m["X_R"])
    assert any("SUPUESTA" in h for h in red.hipotesis)


def test_red_eventos_del_mundo():
    red = modelo("RED-3F-220V-60HZ", "-G1")
    red.accionar("perder_fase", "L2")
    assert set(red.salidas()["fasores"]) == {"L1", "L3"} and not red.salidas()["fases_ok"]
    red.accionar("caida", 0.8)
    assert abs(red.salidas()["fasores"]["L1"]) == pytest.approx(0.8 * 220 / math.sqrt(3))
    red.accionar("cortar")
    assert red.senales() == {"-G1.conectada": False, "-G1.U_V": 0.0, "-G1.fases_ok": False}
    red.accionar("restaurar")
    assert red.salidas()["fases_ok"] and cmath.phase(red.salidas()["fasores"]["L2"]) == pytest.approx(-2 * math.pi / 3)
    with pytest.raises(ValueError, match="«N» no es una fase"):
        red.accionar("perder_fase", "N")


# ── mandos, piloto y sensores ────────────────────────────────────────────────────────────────


def test_pulsador_vuelve_por_resorte_y_la_seta_queda_retenida():
    s1 = modelo("PULS-22-VERDE-NA", "-S1")
    s1.accionar("pulsar", 0.2)
    assert correr(s1, 0.1, {})["accionado"]
    assert not correr(s1, 0.12, {})["accionado"]  # a los 0,2 s vuelve solo
    s1.accionar("pulsar")
    assert correr(s1, 5, {})["accionado"]          # sin duración: hasta soltar
    s1.accionar("soltar")
    assert not s1.paso(DT)["accionado"]
    s0 = modelo("ESTOP-40", "-S0")
    s0.accionar("presionar")
    assert correr(s0, 10, {})["accionado"] and s0.senales() == {"-S0.accionado": True}
    s0.accionar("liberar")
    assert not s0.paso(DT)["accionado"]


def test_botonera_un_actuador_por_grupo_y_selector_mantenido():
    b = modelo("BOTONERA-2", "-S9")
    b.accionar("pulsar", {"actuador": "paro", "durante_s": 0.1})
    assert b.actuadores() == {"marcha": False, "paro": True}
    assert set(b.senales()) == {"-S9.marcha", "-S9.paro", "-S9.potenciometro"}
    s5 = modelo("SEL-22-3POS-2NA", "-S5")
    assert s5.salidas()["posicion"] == "0"
    s5.accionar("girar", "II")
    assert correr(s5, 1, {}) == {"posicion": "II", "posicion_I": False, "posicion_II": True}
    with pytest.raises(ValueError, match="no es una posición"):
        s5.accionar("girar", "III")


def test_piloto_y_sensor():
    h1 = modelo("PILOTO-24V-VERDE", "-H1")
    assert h1.paso(DT, {"U_V": 24})["I_A"] == pytest.approx(0.018)
    assert not h1.paso(DT, {"U_V": 15})["encendido"]
    b1 = modelo("FOTO-M18", "-B1")
    assert b1.t_resp == pytest.approx(0.001)
    assert b1.paso(DT, {"detecta": True, "U_alim_V": 24})["activo"]  # 1 ms < un intercambio
    assert not correr(b1, 0.01, {"detecta": True, "U_alim_V": 5})["activo"]  # sin alimentación
    b1.accionar("forzar", True)                                                # sensor_pegado
    assert correr(b1, 0.01, {"detecta": False, "U_alim_V": 24})["activo"]


def test_un_modelo_sin_su_parametro_es_error_accionable():
    m = dict(CATALOG["CONT-9A-24VDC"].electrico.modelo)
    del m["U_caida_pct"]
    with pytest.raises(ModeloIncompleto, match=r"-K1 \(CONT-X\): falta «U_caida_pct».*electrico\.modelo.*criterio de diseño"):
        crear_modelo("-K1", "CONT-X", m)
    with pytest.raises(ModeloIncompleto, match="no hay modelo para el tipo «turbina»"):
        crear_modelo("-K1", "X", {"tipo": "turbina"})
