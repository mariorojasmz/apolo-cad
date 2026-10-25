"""La co-simulación del aire, pieza por pieza (plan V8.9 F3, D3/D4/D6/D8).

  - el orificio de `cosim/neumatica` es la MISMA fórmula de ISO 6358-1 que la de la memoria
    (`library/neumatica/iso6358.py`);
  - el acople con MuJoCo (D4: 8 sub-pasos de 0,25 ms, posición extrapolada, fuerza media) contra
    la referencia fina integrada aparte, en los casos de la F0 y sus extremos: ±1 % del tiempo de
    carrera y del consumo (`neumatica_referencia.py`); bit a bit dos veces; su costo;
  - la electroválvula (D6): mando, tiempos de conmutación, histéresis, manual; las vías por posición;
  - la topología de la red de aire (cadenas, regulador de caudal en línea, errores) y el escenario.
"""

from __future__ import annotations

import math
import time

import pytest
from neumatica_referencia import CASOS, Caso, acoplado, caminos, cilindro, referencia_fina

from apolo.cosim.datos import DispositivoCosim
from apolo.cosim.escenario import EscenarioInvalido, leer_escenario
from apolo.cosim.modelos import ModeloIncompleto, crear_modelo
from apolo.cosim.neumatica import crear_modelo_aire, orificio
from apolo.cosim.neumatica.componentes import Toma
from apolo.cosim.neumatica.red import RedAire
from apolo.cosim.neumatica.valvula import tabla
from apolo.library.catalog import CATALOG
from apolo.library.neumatica import iso6358
from apolo.services.cosim_aire import ficha_plana

DT = 0.002


# ── el orificio es el de la memoria ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("p1,p2", [(7.0, 1.0), (7.0, 5.5), (6.0, 5.99), (3.0, 1.2), (1.5, 1.5)])
def test_el_orificio_es_el_de_iso6358_de_la_memoria(p1, p2):
    via = (0.8, 0.3, 0.5)
    assert orificio.caudal(via, p1 * 1e5, p2 * 1e5) == pytest.approx(
        iso6358.caudal_masico(0.8, 0.3, p1, p2), rel=1e-12, abs=1e-15)
    assert orificio.P_ATM_PA == iso6358.P_ATM_ESTANDAR_BAR * 1e5 and orificio.RHO0 == iso6358.RHO_ANR_KG_M3
    assert orificio.serie([(0.8, 0.3, 0.5)]) == (0.8, 0.3, 0.5)
    C, b, _ = orificio.serie([(4.0, 0.3, 0.5), (0.15, 0.2, 0.5)])
    assert C == pytest.approx(iso6358.c_serie(4.0, 0.15)) and b == 0.2   # el b de la más restrictiva


def test_el_caudal_cambia_de_sentido():
    ida, vuelta = (1.0, 0.3, 0.5), (0.2, 0.3, 0.5)
    assert orificio.caudal_signado(ida, vuelta, 7e5, 2e5) > 0
    assert orificio.caudal_signado(ida, vuelta, 2e5, 7e5) == pytest.approx(-orificio.caudal(vuelta, 7e5, 2e5))


# ── el acople (D4) contra la referencia fina ─────────────────────────────────────────────────


@pytest.fixture(scope="module")
def medidos():
    pytest.importorskip("mujoco")
    return {c.nombre: (referencia_fina(c), acoplado(c)) for c in CASOS}


@pytest.mark.parametrize("caso", [c.nombre for c in CASOS])
def test_carrera_y_consumo_a_1_pct_de_la_referencia_fina(medidos, caso):
    ref, aco = medidos[caso]
    assert aco["t_carrera"] == pytest.approx(ref["t_carrera"], rel=0.01), (ref, aco)
    assert aco["consumo_NL"] == pytest.approx(ref["consumo_NL"], rel=0.01), (ref, aco)


def test_la_referencia_da_el_regimen_a_mano(medidos):
    """Escape sónico: v = C·p_ANR / A_anular (F0 § 1, el ejemplo resuelto de F1a)."""
    ref, aco = medidos["Ø32 s300, C 0,8"]
    a_mano = iso6358.velocidad_regimen_sonica(0.8, math.pi / 4 * (32 ** 2 - 12 ** 2))
    assert ref["v_max"] == pytest.approx(a_mano, rel=0.01) and aco["v_max"] == pytest.approx(a_mano, rel=0.02)


def test_el_acople_es_determinista_bit_a_bit():
    pytest.importorskip("mujoco")
    c = CASOS[3]
    assert acoplado(c) == acoplado(c)


def test_costo_de_las_camaras_por_intercambio():
    c = Caso("costo", 32, 12, 300, 1.0, 0.8, 0.8)
    cil = cilindro(c)
    cA, cB = caminos(c, Toma())
    n = 2000
    t = time.process_time()  # CPU, no pared: otro worker de la suite no lo infla (≥ 80 ms: el tic de Windows es 15,6)
    for k in range(n):
        cil.intercambio(DT, 0.1 + 1e-6 * k, 0.5, cA, cB)
    us = (time.process_time() - t) / n * 1e6
    print(f"cámaras de un cilindro: {us:.1f} µs de CPU por intercambio")
    assert us < 1000.0  # F0: 41 µs; sólo atrapa un desastre


# ── la electroválvula (D6) ───────────────────────────────────────────────────────────────────


def valvula(ref: str):
    c = CATALOG[ref]
    return crear_modelo("-QM1", ref, {**c.electrico.modelo, "aire": ficha_plana(c.neumatico)})


def correr(m, s: float, **u) -> dict:
    out = {}
    for _ in range(round(s / DT)):
        out = m.paso(DT, {f"U_{k[1:]}": v for k, v in u.items()})
    return out


def test_monoestable_conmuta_con_sus_tiempos_y_su_histeresis():
    v = valvula("VAL-52-MONO-G18")
    assert v.BOBINAS == {"14": "A1"} and v.posicion == "12"
    assert correr(v, 0.012, b14=24.0)["posicion"] == "12"       # t_on = 14 ms
    assert correr(v, 0.002, b14=24.0) == {"posicion": "14", "bobina14": True, "manual": "0"}
    assert correr(v, 0.1, b14=12.0)["posicion"] == "14"         # 50 % de Uc: no suelta (40 %)
    assert correr(v, 0.020, b14=0.0)["posicion"] == "14"        # t_off = 22 ms
    assert correr(v, 0.002, b14=0.0)["posicion"] == "12"
    assert correr(v, 0.1, b14=20.0)["posicion"] == "12"         # bajo el 90 %: no conmuta


def test_biestable_conserva_y_la_5_3_se_centra():
    b = valvula("VAL-52-BI-G18")
    assert b.BOBINAS == {"14": "14A1", "12": "12A1"}
    correr(b, 0.05, b14=24.0)
    assert correr(b, 0.2)["posicion"] == "14"                    # sin tensión conserva
    assert correr(b, 0.05, b12=24.0)["posicion"] == "12"
    c = valvula("VAL-53-CC-G18")
    assert c.posicion == "0" and correr(c, 0.05, b12=24.0)["posicion"] == "12"
    assert correr(c, 0.05)["posicion"] == "0"


def test_accionamiento_manual_y_sus_errores():
    v = valvula("VAL-52-MONO-G18")
    assert v.salidas()["manual"] == "0"
    v.accionar("accionar_manual", "14")
    assert correr(v, 0.05)["posicion"] == "14" and v.salidas()["bobina14"] is False
    assert v.salidas()["manual"] == "14"   # V8.9 F6: el enclavamiento es una señal (una fuente)
    v.accionar("accionar_manual", "0")
    assert correr(v, 0.05)["posicion"] == "12" and v.salidas()["manual"] == "0"
    b = valvula("VAL-52-BI-G18")
    b.accionar("accionar_manual", "12")
    b.accionar("accionar_manual", "14")
    assert b.salidas()["manual"] == "14+12"
    with pytest.raises(ValueError, match="pide el lado"):
        v.accionar("accionar_manual", "12")
    with pytest.raises(ModeloIncompleto, match="aire"):
        crear_modelo("-QM1", "VAL-52-MONO-G18", CATALOG["VAL-52-MONO-G18"].electrico.modelo)


@pytest.mark.parametrize("vias,mando,reposo,pos,esperado", [
    (5, "monoestable", None, "14", {"4": "1", "2": "3"}),
    (5, "biestable", None, "12", {"2": "1", "4": "5"}),
    (5, "centro_cerrado", None, "0", {"2": None, "4": None}),
    (5, "centro_escape", None, "0", {"2": "3", "4": "5"}),
    (5, "centro_presion", None, "0", {"2": "1", "4": "1"}),
    (3, "monoestable", "NC", "12", {"2": "1"}),
    (3, "monoestable", "NC", "0", {"2": "3"}),
    (3, "monoestable", "NA", "0", {"2": "1"}),
    (2, "monoestable", "NC", "0", {"2": None}),
])
def test_las_vias_de_cada_posicion(vias, mando, reposo, pos, esperado):
    assert tabla(vias, mando, reposo, pos) == esperado


# ── la red de aire ───────────────────────────────────────────────────────────────────────────


def _red(tubos, extra_disp=(), ajustes_reg=None):
    disp = []
    modelos = {}

    def add(des, ref=None, aire=None, ajustes=None):
        a = aire if aire is not None else ficha_plana(CATALOG[ref].neumatico)
        modelo = {**(CATALOG[ref].electrico.modelo if ref and CATALOG[ref].electrico else {}), "aire": a}
        if a.get("tipo") == "cilindro":
            a["carrera_mm"] = 200.0
        disp.append(DispositivoCosim(des, ref or "SINTETICO", modelo, ajustes or {}))
        m = crear_modelo(des, ref, modelo, ajustes) or crear_modelo_aire(des, ref or "SINTETICO", a, ajustes)
        if m is not None:
            modelos[des] = m

    add("-AZ1", "FR-G14", ajustes={"p_regulada_bar": 6})
    add("-QM2", "VAL-52-MONO-G14")
    add("-MM1", "CIL-ISO15552-32")
    for x in extra_disp:
        add(*x[:1], aire=x[1], ajustes=ajustes_reg)
    return RedAire({"presion_red_bar": 7.0, "tubos": tubos}, disp, modelos), modelos


REG = {"tipo": "regulador_caudal", "caudal": {"C": 1.0, "b": 0.3, "m": 0.5}, "C_regulado": [0.02, 1.0],
       "p_max_bar": 10}
TUBOS = [{"desde": "-AZ1:2", "hasta": "-QM2:1", "D_int_mm": 5, "largo_m": 1.0},
         {"desde": "-QM2:4", "hasta": "-MM1:A", "D_int_mm": 4, "largo_m": 2.0},
         {"desde": "-QM2:2", "hasta": "-RZ1:1", "D_int_mm": 4, "largo_m": 0.5},
         {"desde": "-RZ1:2", "hasta": "-MM1:B", "D_int_mm": 4, "largo_m": 0.5}]


def test_el_regulador_en_linea_estrangula_el_escape():
    red, m = _red(TUBOS, [("-RZ1", REG)], {"C_regulado": 0.15})
    cil = m["-MM1"]
    assert cil.V_tubo_A == pytest.approx(math.pi * 0.004 ** 2 / 4 * 2.0)
    assert cil.V_tubo_B == pytest.approx(math.pi * 0.004 ** 2 / 4 * 1.0)   # las dos líneas de la cadena
    camB = red.camaras[("-MM1", "B")]
    assert camB.puertos == {"-MM1:B", "-RZ1:2", "-RZ1:1", "-QM2:2"}
    # en reposo («12») B se alimenta por el sentido libre; en «14» escapa por el regulado
    (c,) = red.caminos(camB)
    assert c.toma is m["-AZ1"].toma and c.p == pytest.approx(6e5 + orificio.P_ATM_PA)  # la regulada
    assert c.ida[0] == pytest.approx(orificio.serie([(4.0, .3, .5), m["-AZ1"].via, (1.0, .3, .5)])[0])
    m["-QM2"].posicion = "14"
    (c,) = red.caminos(camB)
    assert c.p == orificio.P_ATM_PA and c.vuelta[0] == pytest.approx(iso6358.c_serie(3.1, 0.15))
    assert c.toma is None


def test_la_red_de_aire_rechaza_lo_que_no_sabe_simular():
    with pytest.raises(ModeloIncompleto, match="no llega a ninguna válvula"):
        _red(TUBOS[:2])
    with pytest.raises(ModeloIncompleto, match="falta el ajuste «C_regulado»"):
        _red(TUBOS, [("-RZ1", REG)], {})
    red, _ = _red(TUBOS, [("-RZ1", REG)], {"C_regulado": 0.15})
    with pytest.raises(ValueError, match="¿Quisiste decir «-MM1:[AB]»"):
        red.fuga("-MM1:X", 0.05, None, False)


# ── el escenario (D8) ────────────────────────────────────────────────────────────────────────


def test_el_escenario_lee_el_aire():
    e = leer_escenario({"duracion_s": 2, "condiciones": {"presion_red_bar": 6},
                        "acoples": {"cilindros": {"-MM1": {"junta": "c1_vastago"}},
                                    "sensores": {"-BG1": {"junta": "c1_vastago", "en_mm": 0, "ventana_mm": 3}}},
                        "acciones": [{"t": 0.5, "accion": "accionar_manual", "dispositivo": "-QM1", "valor": "14"}],
                        "eventos": [{"t": 1, "tipo": "corte_de_aire", "duracion_s": 0.2},
                                    {"t": 1, "tipo": "presion_de_red", "bar": 4},
                                    {"t": 1, "tipo": "fuga", "puerto": "-MM1:A", "C": 0.05}]})
    assert e.presion_red_bar == 6 and e.cilindros == {"-MM1": {"junta": "c1_vastago"}}
    assert e.sensores["-BG1"] == {"junta": "c1_vastago", "en_mm": 0.0, "ventana_mm": 3.0}
    assert [x.datos for x in e.eventos] == [{}, {"bar": 4.0}, {"puerto": "-MM1:A", "C": 0.05}]


@pytest.mark.parametrize("cambio,mensaje", [
    ({"condiciones": {"presion_red_bar": 600}}, "presion_red_bar"),
    ({"acciones": [{"t": 0, "accion": "accionar_manual", "dispositivo": "-QM1"}]}, "pide «valor»"),
    ({"eventos": [{"t": 0, "tipo": "fuga", "puerto": "-MM1:A"}]}, "la fuga pide «C»"),
    ({"eventos": [{"t": 0, "tipo": "fuga", "puerto": "MM1A", "C": 0.1}]}, "designación:puerto"),
    ({"acoples": {"sensores": {"-BG1": {"junta": "j", "en_mm": 0}}}}, "falta «ventana_mm»"),
    ({"acoples": {"cilindros": {"-MM1": {"junta": "j", "carrera": 1}}}}, "clave desconocida «carrera»"),
])
def test_el_escenario_rechaza_el_aire_mal_escrito(cambio, mensaje):
    with pytest.raises(EscenarioInvalido, match=mensaje):
        leer_escenario({"duracion_s": 1, **cambio})
