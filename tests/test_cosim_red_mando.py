"""La red de MANDO de la co-simulación (plan V8.3 F3, marco V8 D3): MNA real con la LU en caché.

El tablero de arranque directo del ERC de V8.1 (`test_electrico_erc.arranque_directo`) pasa por
el adaptador (`services/cosim_red`) a las redes y se acopla a los modelos de F2 de sus
dispositivos (`cosim_red_banco.Banco`): la autorretención marcha/paro funciona como en el
tablero real. Más un fusible del mando que abre ante un corto en el tiempo de su imagen térmica,
la fuente que limita y se recupera, una entrada del PLC y las fallas del escenario.
"""

from __future__ import annotations

import math

import pytest

from apolo.cosim.modelos import crear_modelo
from apolo.cosim.modelos.protecciones import FUSIBLE_K, FUSIBLE_TAU_S
from apolo.cosim.red import armar
from apolo.library.catalog import CATALOG
from cosim_red_banco import DT, Banco
from test_electrico_erc import arranque_directo


def banco_directo() -> Banco:
    b = Banco(arranque_directo(), ajustes={"-Q2": {"Ir_A": 3.2}})
    b.correr(0.1)  # la fuente de 24 V levanta con la red
    return b


def bobina(b: Banco) -> float:
    return b.mando.carga("-Q3:A1-A2")["U_V"]


# ── autorretención ───────────────────────────────────────────────────────────────────────────


def test_autorretencion_marcha_paro_con_contactor():
    b = banco_directo()
    k, marcha, paro = b.modelos["-Q3"], b.modelos["-S2"], b.modelos["-S1"]
    assert b.mando.fuente("-T1")["U_V"] == pytest.approx(24.0)
    assert not k.cerrado and bobina(b) == pytest.approx(0.0, abs=0.05)
    # pulsar marcha 0,2 s: la bobina recibe tensión y el contactor cierra en su tiempo de ficha
    marcha.accionar("pulsar", 0.2)
    b.correr(0.1)
    assert bobina(b) == pytest.approx(24.0, abs=0.1)
    assert k.cerrado
    # al soltar sigue: el 13-14 del contactor retiene
    b.correr(0.3)
    assert not marcha.actuadores()["mano"]
    assert k.cerrado and bobina(b) == pytest.approx(24.0, abs=0.1)
    assert b.modelos["-P1"].encendido  # piloto de marcha por el bloque auxiliar -Q3A (acople)
    # paro (NC) abre el lazo: la bobina cae y el contactor abre; al soltar NO rearranca
    paro.accionar("pulsar", 0.2)
    b.correr(0.1)
    assert not k.cerrado and bobina(b) == pytest.approx(0.0, abs=0.05)
    b.correr(0.3)
    assert not k.cerrado
    assert not b.modelos["-P1"].encendido


def test_la_seta_retenida_corta_y_no_rearranca_al_liberarla():
    b = banco_directo()
    k = b.modelos["-Q3"]
    b.modelos["-S2"].accionar("pulsar", 0.2)
    b.correr(0.4)
    assert k.cerrado
    b.modelos["-S0"].accionar("presionar")
    b.correr(0.1)
    assert not k.cerrado
    b.modelos["-S2"].accionar("pulsar", 0.2)  # con la seta retenida, la marcha no hace nada
    b.correr(0.4)
    assert not k.cerrado
    b.modelos["-S0"].accionar("liberar")
    b.correr(0.2)
    assert not k.cerrado  # liberar no rearranca (ISO 13850): hace falta una marcha nueva
    b.modelos["-S2"].accionar("pulsar", 0.2)
    b.correr(0.4)
    assert k.cerrado


def test_la_lu_se_refactoriza_solo_al_conmutar():
    b = banco_directo()
    red = b.redes.mando
    antes = red.factorizaciones
    b.correr(0.2)  # sin cambios de estado: cero factorizaciones
    assert red.factorizaciones == antes
    b.modelos["-S2"].accionar("pulsar", 0.2)
    b.correr(0.5)
    # pulsar, cerrar el contactor (13-14 y el auxiliar) y soltar: pocas, una por evento
    assert 2 <= red.factorizaciones - antes <= 4


# ── fuente con límite y fusible del mando ───────────────────────────────────────────────────


def _mando_con_fusible(cartucho_A: float, curva: str = "T") -> dict:
    """+24 → fusible -F3 (unidad 1) → bobina de -K1 → 0 V, con un corto agendable en la bobina."""
    return {
        "ramas": [
            {"id": "w1", "tipo": "conductor", "de": "-T1:L+", "a": "-F3:1.1", "seccion_mm2": 0.75, "largo_m": 1.0},
            {"id": "-F3:1.1-1.2", "tipo": "contacto", "de": "-F3:1.1", "a": "-F3:1.2", "contacto": "proteccion",
             "actuador": "-F3.1.cerrado", "dispositivo": "-F3"},
            {"id": "w2", "tipo": "conductor", "de": "-F3:1.2", "a": "-K1:A1", "seccion_mm2": 0.75, "largo_m": 1.0},
            {"id": "w3", "tipo": "conductor", "de": "-K1:A2", "a": "-T1:M", "seccion_mm2": 0.75, "largo_m": 1.0},
        ],
        "fuentes": [{"id": "-T1", "tipo": "DC", "U_V": 24, "polos": {"-T1:L+": "+", "-T1:M": "-"}}],
        "cargas": [{"id": "-K1:A1-A2", "tipo": "bobina", "bornes": ["-K1:A1", "-K1:A2"], "modo": "impedancia",
                    "S_VA": 2.4, "Un_V": 24}],
        "actuadores": {"-F3.1.cerrado": True},
    }


def _fuente_y_fusible(cartucho_A: float):
    fuente = crear_modelo("-T1", "FUENTE-24VDC-2.5A", CATALOG["FUENTE-24VDC-2.5A"].electrico.modelo)
    fus = crear_modelo("-F3", "BORNE-FUS-5X20", CATALOG["BORNE-FUS-5X20"].electrico.modelo,
                       {"cartucho_In_A": cartucho_A})
    return fuente, fus


def test_fusible_del_mando_abre_ante_un_corto_y_la_fuente_se_recupera():
    red = armar(_mando_con_fusible(1.0)).mando
    fuente, fus = _fuente_y_fusible(1.0)
    t, t_fundido = 0.0, None
    red.cortocircuito("corto", "-K1:A1", "-K1:A2")  # la bobina en corto franco
    for _ in range(round(3.0 / DT)):
        estados = {"-F3.1.cerrado": not fus.fundido[0]}
        fuente.paso(DT, {"U_entrada_V": 220.0, "I_carga_A": red.pedidas(estados)["-T1"]})
        res = red.paso(estados, {"-T1": fuente.U})
        assert abs(res.corriente("-F3:1.1-1.2")) <= 1.3 * 2.5 * 1.0001  # el límite actúa en el mismo paso
        fus.paso(DT, {"I_A": [abs(res.corriente("-F3:1.1-1.2"))]})
        t += DT
        if fus.fundido[0] and t_fundido is None:
            t_fundido = t
    # la fuente limitó a 130 % de 2,5 A = 3,25 A: x = 3,25 en un cartucho de 1 A T
    x = 1.3 * 2.5 / 1.0
    esperado = FUSIBLE_TAU_S["T"] * math.log(x * x / (x * x - FUSIBLE_K ** 2))
    assert t_fundido == pytest.approx(esperado, abs=3 * DT)
    # fundido: el corto quedó aislado y la fuente vuelve a sus 24 V sin limitar
    assert fuente.U == pytest.approx(24.0) and not fuente.limitando
    assert abs(res.corriente("-F3:1.1-1.2")) < 1e-6


def test_la_fuente_limita_a_corriente_constante_y_baja_su_tension():
    red = armar(_mando_con_fusible(6.3)).mando
    fuente, _ = _fuente_y_fusible(6.3)
    red.cortocircuito("sobrecarga", "-K1:A1", "-K1:A2", R_ohm=3.0)  # 24 V / 3 Ω ≈ 8 A pedidos
    fuente.paso(DT, {"U_entrada_V": 220.0, "I_carga_A": red.pedidas()["-T1"]})
    res = red.paso({}, {"-T1": fuente.U})
    assert fuente.limitando
    assert res.fuente("-T1")["I_A"] == pytest.approx(1.3 * 2.5, rel=1e-9)  # entrega su límite
    assert res.fuente("-T1")["I_pedida_A"] > 7.0  # lo que la carga tomaría a 24 V
    assert bobina_de(res) < 12.0  # la tensión cae (la bobina del contactor ya no retiene)
    red.quitar_falla("sobrecarga")
    fuente.paso(DT, {"U_entrada_V": 220.0, "I_carga_A": red.pedidas()["-T1"]})
    res = red.paso({}, {"-T1": fuente.U})
    assert not fuente.limitando and bobina_de(res) == pytest.approx(24.0, abs=0.05)


def bobina_de(res) -> float:
    return res.carga("-K1:A1-A2")["U_V"]


def test_una_rama_cortada_deja_la_bobina_sin_tension():
    red = armar(_mando_con_fusible(1.0)).mando
    assert bobina_de(red.paso()) == pytest.approx(24.0, abs=0.05)
    red.cortar("w2")
    assert bobina_de(red.paso()) == pytest.approx(0.0, abs=0.01)
    red.reponer("w2")
    assert bobina_de(red.paso()) == pytest.approx(24.0, abs=0.05)


def test_caida_en_el_mando_por_largo_y_seccion():
    """Tres tramos de 50 m de 0,75 mm² a 70 °C: R = 26 Ω/km · (1 + 0,00393·50) cada uno (IEC 60228),
    en serie con el contacto del fusible (R_on) y la bobina (24²/2,4 = 240 Ω)."""
    e = _mando_con_fusible(1.0)
    for r in e["ramas"]:
        if r["tipo"] == "conductor":
            r["largo_m"] = 50.0
    res = armar(e).mando.paso()
    R = 26.0e-3 * 50 * (1 + 0.00393 * 50)
    i = 24.0 / (3 * R + 240.0 + 0.01)
    assert res.corriente("w3") == pytest.approx(i, rel=1e-4)
    assert bobina_de(res) == pytest.approx(i * 240.0, rel=1e-4)


# ── el PLC lee su entrada ────────────────────────────────────────────────────────────────────


def test_un_sensor_pnp_enciende_la_entrada_del_plc():
    e = {
        "ramas": [
            {"id": "w1", "tipo": "union", "de": "-T1:L+", "a": "-B1:BN"},
            {"id": "-B1:BN-BK", "tipo": "contacto", "de": "-B1:BN", "a": "-B1:BK", "contacto": "NA",
             "actuador": "-B1.señal"},
            {"id": "w2", "tipo": "union", "de": "-B1:BK", "a": "-A1:I0.0"},
            {"id": "w3", "tipo": "union", "de": "-A1:1M", "a": "-T1:M"},
            {"id": "w4", "tipo": "union", "de": "-B1:BU", "a": "-T1:M"},
        ],
        "fuentes": [{"id": "-T1", "tipo": "DC", "U_V": 24, "polos": {"-T1:L+": "+", "-T1:M": "-"}}],
        "cargas": [
            {"id": "-A1:I0.0-1M", "tipo": "entrada", "bornes": ["-A1:I0.0", "-A1:1M"], "modo": "impedancia",
             "R_ohm": 7500},
            {"id": "-B1:BN-BU", "tipo": "alimentacion", "bornes": ["-B1:BN", "-B1:BU"], "modo": "ninguna"},
            {"id": "-A1:I0.1-1M", "tipo": "entrada", "bornes": ["-A1:I0.1", "-A1:1M"], "modo": "impedancia",
             "R_ohm": 7500},
        ],
    }
    red = armar(e).mando
    plc = crear_modelo("-A1", "PLC-14DI-10DO-24VDC", CATALOG["PLC-14DI-10DO-24VDC"].electrico.modelo)
    for activo in (False, True):
        res = red.paso({"-B1.señal": activo}, {"-T1": 24.0})
        assert res.carga("-B1:BN-BU")["U_V"] == pytest.approx(24.0)  # el sensor está alimentado
        u = res.carga("-A1:I0.0-1M")["U_V"]
        for _ in range(10):  # el filtro de entrada (6,4 ms)
            s = plc.paso(DT, {"L+": 24.0, "I0.0": u, "I0.1": res.carga("-A1:I0.1-1M")["U_V"]})
        assert s["%IX0.0"] is activo
        assert (u > 23.9) is activo and (u < 1.0) is not activo
        assert res.carga("-A1:I0.0-1M")["I_A"] == pytest.approx(3.2e-3 if activo else 0.0, abs=1e-4)
    assert res.carga("-A1:I0.1-1M")["U_V"] == 0.0  # sin cablear: 0 V
    assert not s["%IX0.1"]


def test_determinismo_dos_corridas_dan_lo_mismo_bit_a_bit():
    def corrida():
        b = banco_directo()
        b.modelos["-S2"].accionar("pulsar", 0.2)
        trazas = []
        for _ in range(300):
            b.paso()
            trazas.append((b.mando.x.tobytes(), b.potencia.x.tobytes(), b.modelos["-Q3"].estado))
        return trazas

    assert corrida() == corrida()
