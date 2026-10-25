"""Cifras eléctricas medidas en el resultado de un escenario (plan pedidos-de-extensiones F4, D7, D8).

  - la caída de tensión del arranque directo del banco (`cosim_lazo_banco.faja_directo`) contra la
    cuenta a mano con la R y la X de `cosim/red/conductores`, cifra por cifra: rotor bloqueado (el
    primer paso), el mínimo del arranque (carga de potencia constante) y el régimen;
  - un disparo con su hora, su corriente (la de la línea) y su causa, retenida hasta el final;
  - un motor tras un variador lleva `tras_variador` y no lleva ΔU;
  - sin motores ni disparos, el compacto de siempre; un resultado viejo sin `electrico` se lee
    con su aviso;
  - `set_scenario` acepta una aserción sobre `-M1.U_V` (número) y el resultado guardado por la API
    trae `electrico`;
  - los modelos: `I_disparo_A` sólo tras disparar, retenida hasta rearmar (0.0 después).
"""

from __future__ import annotations

import cmath
import math

import pytest
from fastapi.testclient import TestClient

from apolo.cosim.modelos import Parametros
from apolo.cosim.modelos.diferencial import Diferencial
from apolo.cosim.modelos.protecciones import Fusible, Guardamotor, Itm, ReleTermico
from apolo.cosim.red.conductores import reactancia, resistencia
from apolo.cosim.red.mna import R_ON
from apolo.services import escenarios as E
from apolo.services.errors import ServiceError
from apolo.services.medidas_electricas import SIN_CIFRAS, cifras, referencias, resumen_electrico

DT = 0.002


# ── los modelos (sin MuJoCo) ───────────────────────────────────────────────────────────────


def _itm():
    return Itm(Parametros("-F1", "ITM", {"tipo": "itm", "In_A": 10, "curva": "C", "polos": 3}))


def test_el_itm_publica_la_corriente_de_disparo_solo_tras_disparar_y_la_suelta_al_rearmar():
    q = _itm()
    s = q.paso(DT, {"I_A": [5.0, 5.0, 5.0]})
    assert "I_disparo_A" not in s and "I_disparo_A" not in q.publicadas()  # las salidas de siempre
    s = q.paso(DT, {"I_A": [80.0, 120.0, 90.0]})  # 12 × In ≥ 7,5 × In: magnético en el mismo paso
    assert s["disparado"] and s["causa"] == "magnético" and s["I_disparo_A"] == 120.0
    assert q.paso(DT, {"I_A": [0.0, 0.0, 0.0]})["I_disparo_A"] == 120.0  # retenida
    q.accionar("rearmar")
    assert q.salidas()["I_disparo_A"] == 0.0 and not q.salidas()["disparado"]


def test_el_guardamotor_por_termico_retiene_la_corriente_del_paso_del_disparo():
    gm = Guardamotor(Parametros("-Q2", "GM", {"tipo": "guardamotor", "Ir_A": [2.5, 4.0], "clase": "10",
                                              "Ii_A": 52}, {"Ir_A": 3.2}))
    I = 3.2 * 6
    t = 0.0
    while not gm.disparado:
        s = gm.paso(DT, {"I_A": I})
        t += DT
    assert s["causa"] == "térmico" and s["I_disparo_A"] == pytest.approx(I)
    assert t == pytest.approx(gm.termico.t_disparo(6.0), abs=DT)


def test_el_rele_termico_con_rearme_automatico_vuelve_a_cero():
    r = ReleTermico(Parametros("-F3", "RT", {"tipo": "rele_termico", "Ir_A": [1, 2], "clase": "10",
                                             "rearme": "automatico"}, {"Ir_A": 1.0}))
    while not r.disparado:
        r.paso(0.01, {"I_A": 8.0})
    assert r.salidas()["I_disparo_A"] == 8.0
    while r.disparado:
        r.paso(0.5, {"I_A": 0.0})
    assert r.salidas()["I_disparo_A"] == 0.0


def test_la_averia_abierto_retiene_la_corriente_que_cortaba():
    q = _itm()
    q.paso(DT, {"I_A": 4.0})
    q.fallar("abierto")
    assert q.publicadas()["I_disparo_A"] == 4.0 and q.salidas()["causa"] == "avería"


def test_el_fusible_retiene_la_del_primer_cartucho_y_la_suelta_al_reponerlos_todos():
    f = Fusible(Parametros("-F5", "PF", {"tipo": "fusible", "cartucho_In_A": [1, 10], "In_max_A": 10,
                                         "cartucho_curva": "F"}, {"cartucho_In_A": 2.0}), cantidad=2)
    assert "I_disparo_A" not in f.paso(DT, {"I_A": [1.0, 1.0]})
    while not f.salidas()["disparado"]:
        f.paso(DT, {"I_A": [20.0, 1.0]})
    assert f.salidas()["I_disparo_A"] == 20.0 and f.salidas()["1.disparado"]
    f.accionar("reponer")
    assert f.salidas()["I_disparo_A"] == 0.0


def test_el_diferencial_retiene_la_mayor_corriente_de_sus_polos_no_la_residual():
    d = Diferencial(Parametros("-F6", "DIF", {"tipo": "diferencial", "In_A": 25, "IDn_mA": 30,
                                              "clase_residual": "A", "polos": 2}))
    while not d.disparado:
        d.paso(DT, {"I_fasores": [complex(2.0, 0.0), complex(-1.9, 0.0)]})  # 100 mA a tierra
    assert d.salidas()["causa"] == "diferencial" and d.salidas()["I_disparo_A"] == 2.0
    d.accionar("rearmar")
    assert d.salidas()["I_disparo_A"] == 0.0


# ── el resumen, sintético ─────────────────────────────────────────────────────────────────


def _res(t, senales, discretas=None, final=None):
    return {"trazas": {"analogicas": {"t": t, "senales": senales}, "discretas": discretas or {}},
            "final": final or {}, "resumen": {"huella": "h", "duracion_s": t[-1] if t else 0}}


def test_sin_motores_ni_disparos_el_compacto_de_siempre():
    res = _res([0.0, 0.02], {"-T1.U_V": [24.0, 24.0]}, {"-Q1.disparado": [[0.0, False]]})
    assert resumen_electrico(res, {}) is None
    ver = {"veredicto": "pasa", "aserciones": []}
    out = E.resultado_compacto(ver, res, firma="2:x", hash_esc="h", simulacion="s1", referencias_electricas={})
    assert set(out) == {"veredicto", "aserciones", "firma_documento", "hash_escenario", "cosim_epoch",
                        "fecha", "huella", "duracion_s", "factor_tiempo_real", "simulacion"}


def test_un_resultado_viejo_sin_electrico_sigue_vigente_y_se_lee_con_su_aviso():
    viejo = {"veredicto": "pasa", "aserciones": []}
    assert cifras(viejo, ["-M1"]) == {"aviso": SIN_CIFRAS} and "córrelo de nuevo" in SIN_CIFRAS
    assert cifras(viejo, []) is None
    assert cifras({**viejo, "electrico": {"motores": {}}}, ["-M1"]) == {"motores": {}}


def test_el_tramo_de_arranque_y_la_ventana_del_regimen():
    t = [round(0.1 * k, 6) for k in range(12)]
    U = [0.0, 200.0, 205.0, 210.0, 219.0, 219.0, 219.2, 219.0, 219.4, 219.0, 0.0, 0.0]
    I = [0.0, 20.0, 15.0, 6.0, 2.0, 2.0, 2.0, 2.0, 2.0, 2.0, 0.0, 0.0]
    m = resumen_electrico(_res(t, {"-M1.U_V": U, "-M1.I_A": I}),
                          {"-M1": {"U_ref_V": 220.0, "In_A": 3.0, "tras_variador": False}})["motores"]["-M1"]
    # arranque: de 0,1 s (U > 0) a 0,4 s (I < 4,5 A); régimen: 0,4–0,9 s, la mediana de lo último 0,5 s
    assert m == {"U_ref_V": 220.0, "U_min_arranque_V": 200.0, "U_regimen_V": 219.0,
                 "dU_arranque_pct": 9.091, "dU_regimen_pct": 0.455}
    nunca = resumen_electrico(_res(t, {"-M1.U_V": [0.0] * 12, "-M1.I_A": [0.0] * 12}),
                              {"-M1": {"U_ref_V": 220.0, "In_A": 3.0, "tras_variador": False}})
    assert nunca["motores"]["-M1"] == {"U_ref_V": 220.0, "alimentado": False}


# ── el banco (MuJoCo) ────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def directo():
    pytest.importorskip("mujoco")
    from cosim_lazo_banco import faja_directo

    return faja_directo()


def _correr(doc, esc, programas=None):
    from apolo.cosim.planificador import correr
    from apolo.services.cosim_snapshot import snapshot_cosim

    snap = snapshot_cosim(doc, esc, programas=programas)
    return snap, correr(snap)


def _z_linea(red) -> complex:
    """La impedancia de UNA fase de la red al motor, a mano (IEC 60228 clase 5 a 70 °C, λ de
    IEC 60364-5-52): la red (Icc 10 kA, X/R 1,5), tres tramos de 2,5 mm² × 1 m (-G1→-Q1→-Q2→-Q3),
    tres contactos cerrados (seccionador, guardamotor, contactor: R_ON) y el hilo de -W1 (1,5 mm²
    × 6 m)."""
    R = red.Z.real + 3 * resistencia(2.5, 1.0) + 3 * R_ON + resistencia(1.5, 6.0)
    X = red.Z.imag + 3 * reactancia(1.0) + reactancia(6.0)
    assert (round(red.Z.real, 7), round(red.Z.imag, 7)) == (0.0070456, 0.0105685)
    assert (round(resistencia(2.5, 1.0), 8), round(resistencia(1.5, 6.0), 7)) == (0.00954807, 0.0954807)
    assert (round(R, 7), round(X, 7)) == (0.1611705, 0.0112885)
    return complex(R, X)


def _u_potencia_constante(Vs: float, Z: complex, S_fase: complex) -> float:
    """U de línea de una carga de potencia constante S_fase (por fase) tras Z: |Vl + Z·conj(S/Vl)|
    = Vs con Vl real, por bisección."""
    lo, hi = 0.5 * Vs, Vs
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if abs(mid + Z * (S_fase / mid).conjugate()) < Vs else (lo, mid)
    return math.sqrt(3) * lo


def test_la_caida_del_arranque_directo_contra_la_cuenta_a_mano(directo):
    from apolo.cosim.tablero import FP_ROTOR_BLOQUEADO, Tablero
    from cosim_lazo_banco import escenario_directo, serie

    refs = referencias(directo)
    assert refs == {"-M1": {"tras_variador": False, "U_ref_V": 220.0, "In_A": 3.18}}
    snap, res = _correr(directo, {**escenario_directo(1.5), "trazas": {"analogicas_hz": 500}})
    tab = Tablero(snap.red, snap.dispositivos)
    red, m = tab.modelos["-G1"], tab.modelos["-M1"]
    Z, Vs = _z_linea(red), red.Un / math.sqrt(3)
    U, I = serie(res, "-M1.U_V"), dict(serie(res, "-M1.I_A"))
    vivas = [(t, u) for t, u in U if u > 0]
    # 1) rotor bloqueado (el primer paso alimentado): una impedancia S = √3·Un_motor·Ia·In a FP 0,4
    #    que la red estampa a SU tensión entre fases (220 V): Z_Y = 220²/S*
    S = math.sqrt(3) * m.Un * m.Ia_In * m.In
    assert round(S, 1) == 6967.5
    Zy = red.Un ** 2 / S * cmath.rect(1.0, math.acos(FP_ROTOR_BLOQUEADO))
    U_bloqueado = math.sqrt(3) * abs(Vs * Zy / (Zy + Z))
    assert round(U_bloqueado, 3) == 217.611
    assert vivas[0][1] == pytest.approx(U_bloqueado, abs=0.005)
    # 2) el mínimo: girando ya (> 1 % de ns) es potencia constante con la I y la U del paso anterior
    #    y el cos φ de placa: más R efectiva que a rotor bloqueado → cae más
    k = min(range(len(vivas)), key=lambda j: vivas[j][1])
    (t0, u0), (_t1, u1) = vivas[k - 1], vivas[k]
    S_fase = u0 * I[t0] / math.sqrt(3) * cmath.rect(1.0, math.acos(m.cos_phi))
    assert u1 == pytest.approx(_u_potencia_constante(Vs, Z, S_fase), abs=0.005)
    # 3) régimen: la I de régimen (la da la mecánica) a cos φ de placa
    t_fin, u_fin = vivas[-1]
    ZI = Z * I[t_fin] * cmath.rect(1.0, -math.acos(m.cos_phi))
    U_regimen = math.sqrt(3) * (-ZI.real + math.sqrt(Vs ** 2 - ZI.imag ** 2))
    assert u_fin == pytest.approx(U_regimen, abs=0.005)
    # el resumen guarda esas cifras y su ΔU contra los 220 V de la red
    el = resumen_electrico(res, refs)
    mot = el["motores"]["-M1"]
    assert mot["U_min_arranque_V"] == pytest.approx(u1, abs=1e-3) and round(u1, 2) == 216.37
    assert mot["U_regimen_V"] == pytest.approx(U_regimen, abs=0.005) and round(U_regimen, 2) == 219.59
    assert mot["dU_arranque_pct"] == pytest.approx(100 * (220 - u1) / 220, abs=1e-3)
    assert mot["dU_regimen_pct"] == pytest.approx(100 * (220 - U_regimen) / 220, abs=3e-3)
    assert (round(mot["dU_arranque_pct"], 2), round(mot["dU_regimen_pct"], 2)) == (1.65, 0.19)
    assert "disparos" not in el and "cada 2 ms" in el["medicion"]
    # a 50 Hz (lo de siempre) el mínimo puede caer entre muestras: la cifra queda del lado alto
    _, res50 = _correr(directo, escenario_directo(1.5))
    m50 = resumen_electrico(res50, refs)["motores"]["-M1"]
    assert u1 - 1e-3 <= m50["U_min_arranque_V"] <= U_bloqueado + 1e-3
    assert m50["U_regimen_V"] == pytest.approx(mot["U_regimen_V"], abs=1e-3)


def test_un_disparo_con_su_hora_su_corriente_y_su_causa(directo):
    from cosim_lazo_banco import JUNTA, en, escenario_directo, primer_cambio, serie

    _, res = _correr(directo, escenario_directo(17.0, eventos=[
        {"t": 1.0, "tipo": "atasco", "junta": JUNTA, "par_Nm": 500}]))
    t_disparo = primer_cambio(res, "-Q2.disparado", True)
    el = resumen_electrico(res, referencias(directo))
    [d] = el["disparos"]
    assert d["dispositivo"] == "-Q2" and d["causa"] == "térmico" and d["t_s"] == pytest.approx(t_disparo)
    # la corriente es la de la línea (el hilo -W1.1 en serie con el polo), no la del modelo del motor
    assert d["I_A"] == pytest.approx(en(res, "-W1.1.I_A", t_disparo - 0.01), abs=1e-3)
    assert 15.0 < d["I_A"] < 17.0
    retenida = [v for t, v in serie(res, "-Q2.I_disparo_A")]
    assert len(set(retenida)) == 1 and serie(res, "-Q2.I_disparo_A")[0][0] >= t_disparo - 1e-9
    assert el["motores"]["-M1"]["dU_regimen_pct"] < 1  # el régimen es el de antes del atasco


def test_un_motor_tras_variador_no_lleva_caida():
    pytest.importorskip("mujoco")
    from cosim_lazo_banco import PROGRAMAS, escenario_variador, faja_variador

    doc = faja_variador()
    refs = referencias(doc)
    assert refs["-M1"]["tras_variador"] is True
    _, res = _correr(doc, escenario_variador(1.0), programas=PROGRAMAS)
    assert resumen_electrico(res, refs)["motores"] == {"-M1": {"tras_variador": True}}


def test_set_scenario_acepta_la_tension_del_motor_y_el_resultado_guardado_la_trae(directo, monkeypatch):
    import apolo.api.main as api
    from cosim_lazo_banco import escenario_directo

    esc = {**escenario_directo(1.0), "aserciones": ["-M1.U_V >= 215 al_final", "-Q2.I_disparo_A == 0 al_final"]}
    with pytest.raises(ServiceError, match="U_V"):
        E.poner(directo, "malo", {**esc, "aserciones": ["-M1.U_V == true al_final"]})
    monkeypatch.setattr(api, "DOC", directo)
    c = TestClient(api.app)
    puesto = c.put("/api/escenarios/marcha", json={"escenario": esc}).json()
    assert puesto["avisos"] == [] and puesto["n_aserciones"] == 2
    out = c.post("/api/cosim/run", json={"escenario": "marcha"}).json()
    assert out["guardado"] is True
    res = c.get("/api/escenarios", params={"nombre": "marcha"}).json()["resultado"]
    mot = res["electrico"]["motores"]["-M1"]
    assert mot["U_ref_V"] == 220.0 and 0 < mot["dU_regimen_pct"] < mot["dU_arranque_pct"] < 2
    # la protección no disparó: su señal no existe y la aserción sobre ella no pasa (no inventa un 0)
    assert [a["pasa"] for a in res["aserciones"]] == [True, False]
