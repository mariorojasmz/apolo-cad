"""La red de POTENCIA de la co-simulación (plan V8.3 F3, D15): fasorial cuasi-estática por fase.

Contra cálculo a mano y contra la norma: la caída de tensión de un cable largo (IEC 60364-5-52
anexo G, con la R de IEC 60228 a 70 °C), una carga monofásica entre dos fases que suma su
corriente a ESAS fases, L+N, la pérdida de una fase (motor en marcha → √3 en las otras dos;
detenido → √3/2 y no arranca), el desbalance por componentes simétricas, un corto que dispara el
ITM por magnético y la alterna de mando (bobina de 220 VAC entre fases).
"""

from __future__ import annotations

import cmath
import math

import pytest

from apolo.cosim.modelos import crear_modelo
from apolo.cosim.red import armar, desbalance_pct, fasores_nominales
from apolo.cosim.red.conductores import r20_ohm_km, reactancia, resistencia
from apolo.library.catalog import CATALOG

DT = 0.002
SQ3 = math.sqrt(3)
#: Lo que fuga cada nodo a tierra por G_MIN (0,1 µS · ~130 V ≈ 13 µA): la KCL cierra a esa cota.
FUGA = 1e-4


def modelo(ref: str, des: str, **ajustes):
    return crear_modelo(des, ref, CATALOG[ref].electrico.modelo, ajustes)


def red3f(*, largo_m: float = 1.0, seccion: float = 2.5, sistema: str = "3F", U: float = 220.0,
          cargas: list | None = None, extra: list | None = None) -> dict:
    """Red -G1 → cable -W1 (L1, L2, L3) hasta la barra -X1, y de ahí el motor -M1."""
    fases = ("L1", "L2", "L3")
    polos = {f"-G1:{p}": p for p in fases} | {"-G1:PE": "PE"}
    if sistema == "3F+N":
        polos["-G1:N"] = "N"
    ramas = [{"id": f"-W1.{k + 1}", "tipo": "conductor", "de": f"-G1:{p}", "a": f"-X1:{k + 1}",
              "seccion_mm2": seccion, "largo_m": largo_m} for k, p in enumerate(fases)]
    ramas += [{"id": f"u{k + 1}", "tipo": "union", "de": f"-X1:{k + 1}", "a": f"-M1:{b}"}
              for k, b in enumerate(("U1", "V1", "W1"))]
    return {"ramas": ramas + (extra or []),
            "fuentes": [{"id": "-G1", "tipo": "AC", "sistema": sistema, "U_V": U, "ideal": False, "polos": polos}],
            "cargas": [{"id": "-M1", "tipo": "motor", "bornes": ["-M1:U1", "-M1:V1", "-M1:W1"],
                        "modo": "potencia"}] + (cargas or [])}


def fuente_ideal(U: float = 220.0, sin: tuple = ()) -> dict:
    return {"-G1": {"fasores": {p: v for p, v in fasores_nominales("3F", U).items() if p not in sin},
                    "Z_ohm": 1e-6 + 0j}}


def S_motor(I: float, U: float = 220.0, fp: float = 0.8) -> complex:
    return SQ3 * U * I * complex(fp, math.sqrt(1 - fp * fp))


# ── conductores ──────────────────────────────────────────────────────────────────────────────


def test_resistencia_del_cobre_por_seccion_y_temperatura():
    assert r20_ohm_km(2.5) == 7.98 and r20_ohm_km(0.75) == 26.0  # IEC 60228 tabla 3, clase 5
    assert resistencia(2.5, 100, 20.0) == pytest.approx(0.798)
    assert resistencia(2.5, 100) == pytest.approx(0.798 * (1 + 0.00393 * 50))  # 70 °C del PVC
    assert reactancia(100) == pytest.approx(0.008)  # 0,08 mΩ/m (IEC 60364-5-52 anexo G)
    hip: list[str] = []
    assert resistencia(3.0, 1000, 20.0, hip) == pytest.approx(1 / 58 / 3 * 1000)
    assert hip and "IEC 60028" in hip[0]


# ── caída de tensión ─────────────────────────────────────────────────────────────────────────


def test_caida_de_tension_en_un_cable_largo_contra_calculo_a_mano():
    """100 m de 2,5 mm² a 70 °C con 10 A a fp 0,8: la fasorial da la caída EXACTA del circuito y
    la fórmula del anexo G de IEC 60364-5-52 (u = (R·cosφ + X·senφ)·I por fase) la aproxima."""
    R = 7.98e-3 * 100 * (1 + 0.00393 * 50)  # 0,9548 Ω (IEC 60228 a 70 °C)
    X = 0.08e-3 * 100
    S = S_motor(10.0)
    # impedancia: Y por rama del triángulo = conj(S/3)/U²; en estrella Z_Y = Z_Δ/3
    red = armar(red3f(largo_m=100, cargas=[])).potencia
    res = red.paso({}, fuente_ideal(), {"-M1": {"S": S, "modo": "impedancia"}})
    Zy = (1 / ((S / 3).conjugate() / 220 ** 2)) / 3
    I = (220 / SQ3) / (Zy + complex(R, X) + 1e-6)
    assert res.carga("-M1")["U_V"] == pytest.approx(SQ3 * abs(I * Zy), rel=1e-6)
    assert abs(res.corriente("-W1.1")) == pytest.approx(abs(I), rel=1e-6)
    # potencia constante (motor en marcha): la caída que da la red vs la del anexo G con su I
    res = red.paso({}, fuente_ideal(), {"-M1": {"S": S, "modo": "potencia"}})
    c = res.carga("-M1")
    i = c["I_A"][0]
    fi = cmath.phase(S)
    anexo_g = SQ3 * (R * math.cos(fi) + X * math.sin(fi)) * i  # de línea: √3 · u
    assert 220.0 - c["U_V"] == pytest.approx(anexo_g, rel=0.03)
    assert i == pytest.approx(abs(S) / (SQ3 * c["U_V"]), rel=1e-6)  # toma su potencia a la U real
    assert c["S_VA"] == pytest.approx(S, rel=1e-6)


# ── monofásicas ──────────────────────────────────────────────────────────────────────────────


def test_carga_monofasica_entre_dos_fases_suma_a_esas_fases():
    una = {"id": "-T1:L-N", "tipo": "alimentacion", "bornes": ["-T1:L", "-T1:N"], "modo": "potencia"}
    extra = [{"id": "a1", "tipo": "union", "de": "-X1:1", "a": "-T1:L"},
             {"id": "a2", "tipo": "union", "de": "-X1:2", "a": "-T1:N"}]
    red = armar(red3f(largo_m=20, cargas=[una], extra=extra)).potencia
    S1 = complex(300.0, 0.0)
    res = red.paso({}, fuente_ideal(), {"-M1": {"S": S_motor(5.0)}, "-T1:L-N": {"S": S1}})
    im = res.corrientes_carga("-M1")
    i1 = res.corrientes_carga("-T1:L-N")
    # KCL en la barra: el cable de L1 lleva motor + monofásica, el de L2 motor − monofásica, L3 sólo motor
    assert res.corriente("-W1.1") == pytest.approx(im[0] + i1[0], abs=FUGA)
    assert res.corriente("-W1.2") == pytest.approx(im[1] + i1[1], abs=FUGA)
    assert res.corriente("-W1.3") == pytest.approx(im[2], abs=FUGA)
    c1 = res.carga("-T1:L-N")
    assert c1["I_A"] == pytest.approx(300.0 / c1["U_V"], rel=1e-6) and c1["fases"] == 2
    assert abs(res.corriente("-W1.1")) > abs(res.corriente("-W1.3")) and abs(res.corriente("-W1.2")) > abs(res.corriente("-W1.3"))


def test_carga_fase_neutro_vuelve_por_el_neutro():
    e = {"ramas": [{"id": "-W1.L", "tipo": "conductor", "de": "-G1:L", "a": "-H1:X1", "seccion_mm2": 1.5,
                    "largo_m": 30},
                   {"id": "-W1.N", "tipo": "conductor", "de": "-G1:N", "a": "-H1:X2", "seccion_mm2": 1.5,
                    "largo_m": 30}],
         "fuentes": [{"id": "-G1", "tipo": "AC", "sistema": "1F+N", "U_V": 220, "ideal": False, "pe_a_neutro": True,
                      "polos": {"-G1:L": "L", "-G1:N": "N", "-G1:PE": "PE"}}],
         "cargas": [{"id": "-H1:X1-X2", "tipo": "otra", "bornes": ["-H1:X1", "-H1:X2"], "modo": "impedancia",
                     "R_ohm": 100.0}]}
    red_m = modelo("RED-1F-220V-60HZ", "-G1")
    res = armar(e).potencia.paso({}, {"-G1": red_m.salidas()})
    R = resistencia(1.5, 30)
    i = 220.0 / abs(100.0 + 2 * complex(R, reactancia(30)) + 2 * red_m.Z)  # Zk mitad en L, mitad en N
    assert abs(res.corriente("-W1.L")) == pytest.approx(i, abs=FUGA)
    assert res.corriente("-W1.N") == pytest.approx(-res.corriente("-W1.L"), abs=FUGA)  # vuelve entera por N


def test_dos_fases_de_la_red_peruana():
    e = {"ramas": [{"id": "-F1:1-2", "tipo": "contacto", "de": "-G1:L1", "a": "-T1:L", "contacto": "proteccion",
                    "actuador": "-F1.cerrado"},
                   {"id": "-F1:3-4", "tipo": "contacto", "de": "-G1:L2", "a": "-T1:N", "contacto": "proteccion",
                    "actuador": "-F1.cerrado"}],
         "fuentes": [{"id": "-G1", "tipo": "AC", "sistema": "2F", "U_V": 220, "ideal": False,
                      "polos": {"-G1:L1": "L1", "-G1:L2": "L2", "-G1:PE": "PE"}}],
         "cargas": [{"id": "-T1:L-N", "tipo": "alimentacion", "bornes": ["-T1:L", "-T1:N"], "modo": "potencia"}],
         "actuadores": {"-F1.cerrado": True}}
    red = armar(e).potencia
    g = modelo("RED-2F-220V-60HZ", "-G1")
    res = red.paso({}, {"-G1": g.salidas()}, {"-T1:L-N": {"S": complex(68.0, 0)}})
    c = res.carga("-T1:L-N")
    assert c["U_V"] == pytest.approx(220.0, rel=1e-3) and c["I_A"] == pytest.approx(68.0 / c["U_V"], rel=1e-6)
    assert res.corriente("-F1:1-2") == pytest.approx(-res.corriente("-F1:3-4"), abs=FUGA)
    res = red.paso({"-F1.cerrado": False}, {"-G1": g.salidas()})  # el ITM abierto: sin tensión ni corriente
    assert res.carga("-T1:L-N")["I_A"] == 0.0 and res.carga("-T1:L-N")["fases"] == 0


# ── pérdida de fase (D15) ────────────────────────────────────────────────────────────────────


def test_perdida_de_fase_motor_en_marcha_sube_raiz_de_tres_en_las_otras_dos():
    red = armar(red3f()).potencia
    g = modelo("RED-3F-220V-60HZ", "-G1")
    S = S_motor(3.18)
    antes = red.paso({}, {"-G1": g.salidas()}, {"-M1": {"S": S}}).carga("-M1")
    assert antes["fases"] == 3 and antes["I_A"][0] == pytest.approx(3.18, rel=0.01)
    g.accionar("perder_fase", "L3")
    res = red.paso({}, {"-G1": g.salidas()}, {"-M1": {"S": S}})
    c = res.carga("-M1")
    assert c["fases"] == 2
    assert c["I_A"][0] == pytest.approx(SQ3 * antes["I_A"][0], rel=0.005)
    assert c["I_A"][1] == pytest.approx(SQ3 * antes["I_A"][1], rel=0.005)
    assert c["I_A"][2] == pytest.approx(0.0, abs=1e-6) and abs(res.corriente("-W1.3")) < 1e-6
    # y el guardamotor reglado a In ve ~1,7 Ir en dos polos: dispara por térmico en su curva
    gm = modelo("GM-2.5-4A", "-Q2", Ir_A=3.2)
    t = 0.0
    while not gm.disparado and t < 600:
        gm.paso(0.1, {"I_A": c["I_A"]})
        t += 0.1
    assert gm.disparado and gm.causa == "térmico"
    assert t == pytest.approx(gm.termico.t_disparo(max(c["I_A"]) / 3.2), abs=0.2)


def test_perdida_de_fase_motor_detenido_no_arranca():
    red = armar(red3f()).potencia
    g = modelo("RED-3F-220V-60HZ", "-G1")
    motor = modelo("MOTOR-075", "-M1", conexion="triangulo")
    # rotor bloqueado: una impedancia que toma Ia a la tensión nominal
    S_bloqueo = S_motor(motor.Ia_In * motor.In, fp=0.4)
    tres = red.paso({}, {"-G1": g.salidas()}, {"-M1": {"S": S_bloqueo, "modo": "impedancia"}}).carga("-M1")
    g.accionar("perder_fase", "L3")
    dos = red.paso({}, {"-G1": g.salidas()}, {"-M1": {"S": S_bloqueo, "modo": "impedancia"}}).carga("-M1")
    assert dos["fases"] == 2
    assert dos["I_A"][0] == pytest.approx(SQ3 / 2 * tres["I_A"][0], rel=0.005)
    # el motor del F2 con las fases que da la red: detenido no hace par; girando, sí
    a = motor.actuador_fases(dos["U_V"], 60.0, dos["fases"], 0.0)
    assert a["forcerange_Nm"] == 0.0 and a["kv"] == 0.0
    w = 0.9 * motor.ws_n / motor.i
    assert motor.actuador_fases(dos["U_V"], 60.0, dos["fases"], w)["forcerange_Nm"] > 0


def test_desbalance_por_componentes_simetricas():
    a = cmath.rect(1, math.radians(120))
    v1, v2 = 220.0, 11.0  # 5 %
    lineas = [v1 * x + v2 * y for x, y in zip((1, a * a, a), (1, a, a * a))]
    assert desbalance_pct(*lineas) == pytest.approx(5.0)
    red = armar(red3f()).potencia
    c = red.paso({}, fuente_ideal(), {"-M1": {"S": S_motor(3.0)}}).carga("-M1")
    assert c["desbalance_pct"] == pytest.approx(0.0, abs=1e-9)


# ── protecciones y alterna de mando ──────────────────────────────────────────────────────────


def test_un_corto_entre_fases_dispara_el_itm_por_magnetico():
    extra = [{"id": f"-F1:{2 * k + 1}-{2 * k + 2}", "tipo": "contacto", "de": f"-X1:{k + 1}",
              "a": f"-X2:{k + 1}", "contacto": "proteccion", "actuador": "-F1.cerrado", "dispositivo": "-F1"}
             for k in range(3)]
    e = red3f(largo_m=10, extra=extra)
    e["actuadores"] = {"-F1.cerrado": True}
    red = armar(e).potencia
    g = modelo("RED-3F-220V-60HZ", "-G1")
    itm = modelo("ITM-C16-3P", "-F1")
    red.cortocircuito("corto", "-X2:1", "-X2:2")
    res = red.paso({"-F1.cerrado": itm.cerrado}, {"-G1": g.salidas()})
    I = [abs(res.corriente(f"-F1:{2 * k + 1}-{2 * k + 2}")) for k in range(3)]
    Zc = complex(resistencia(2.5, 10), reactancia(10))
    assert I[0] == pytest.approx(220.0 / abs(2 * (Zc + g.Z) + 0.001 + 2 * 0.01), rel=1e-3)  # bifásico
    itm.paso(DT, {"I_A": I})
    assert itm.disparado and itm.causa == "magnético"
    res = red.paso({"-F1.cerrado": itm.cerrado}, {"-G1": g.salidas()})
    assert abs(res.corriente("-F1:1-2")) < 1e-3


def test_bobina_de_220_vac_entre_fases_cierra_el_contactor():
    e = {"ramas": [{"id": "-S1:13-14", "tipo": "contacto", "de": "-G1:L1", "a": "-K1:A1", "contacto": "NA",
                    "actuador": "-S1.mano"},
                   {"id": "u", "tipo": "union", "de": "-G1:L2", "a": "-K1:A2"}],
         "fuentes": [{"id": "-G1", "tipo": "AC", "sistema": "2F", "U_V": 220, "ideal": False,
                      "polos": {"-G1:L1": "L1", "-G1:L2": "L2"}}],
         "cargas": [{"id": "-K1:A1-A2", "tipo": "bobina", "bornes": ["-K1:A1", "-K1:A2"], "modo": "impedancia",
                     "S_VA": 7.0, "Un_V": 220}]}
    red = armar(e).potencia
    g = modelo("RED-2F-220V-60HZ", "-G1")
    k = modelo("CONT-9A-220VAC", "-K1")
    for pulsado in (False, True):
        for _ in range(20):
            s_bobina = k.S_mant if k.estado == "cerrado" else k.S_llamada
            res = red.paso({"-S1.mano": pulsado}, {"-G1": g.salidas()}, {"-K1:A1-A2": {"S_VA": s_bobina}})
            k.paso(DT, {"U_bobina_V": res.carga("-K1:A1-A2")["U_V"]})
        assert k.cerrado is pulsado
    c = res.carga("-K1:A1-A2")
    assert c["I_A"] == pytest.approx(7.0 / 220.0, rel=1e-3)  # la de mantenimiento, cerrado


def test_salida_del_variador_es_una_fuente_ideal_de_su_frecuencia():
    e = red3f(largo_m=15, seccion=1.5)
    e["fuentes"][0].update(ideal=True)
    red = armar(e).potencia
    S = S_motor(4.0, U=110.0)  # a 30 Hz con V/f: la mitad de la tensión
    c = red.paso({}, {"-G1": {"fasores": fasores_nominales("3F", 110.0, sentido=-1)}}, {"-M1": {"S": S}}).carga("-M1")
    assert c["I_A"][0] == pytest.approx(abs(S) / (SQ3 * c["U_V"]), rel=1e-6)
    assert c["U_V"] < 110.0 and c["fases"] == 3
