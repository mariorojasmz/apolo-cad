"""Protecciones de la co-simulación contra su NORMA (plan V8.3 F2, D7): guardamotor y relé
térmico (IEC 60947-4-1), ITM (IEC 60898-1) y cartucho 5×20 (IEC 60127-2), con los datos del
catálogo. Se simula paso a paso con el intercambio de 2 ms de D10."""

from __future__ import annotations

import pytest

from apolo.cosim.modelos import ModeloIncompleto, crear_modelo
from apolo.cosim.modelos.protecciones import (
    BANDA_CLASE,
    BANDA_FUSIBLE,
    BANDA_MAGNETICA_ITM,
    ITM_BANDA_2_55_S,
    LIMITE_1_5_CALIENTE_S,
)
from apolo.library.catalog import CATALOG

DT = 0.002


def modelo(ref: str, des: str = "-Q1", **ajustes):
    return crear_modelo(des, ref, CATALOG[ref].electrico.modelo, ajustes)


def t_disparo(m, I, t_max: float, *, previo: float | None = None) -> float | None:
    """Segundos hasta `disparado` con la corriente I constante (None si no dispara en t_max).
    `previo`: corriente de régimen con la que se calienta antes (hasta el equilibrio)."""
    if previo is not None:
        tau = m.termico.tau
        for _ in range(int(10 * tau / 0.05)):
            m.paso(0.05, {"I_A": previo})
        assert not m.salidas()["disparado"]
    t = 0.0
    while t < t_max:
        m.paso(DT, {"I_A": I})
        t += DT
        if m.salidas()["disparado"]:
            return t
    return None


# ── guardamotor (IEC 60947-4-1) ──────────────────────────────────────────────────────────────


def test_guardamotor_clase_10_a_7_2_ir_dispara_entre_4_y_10_s():
    gm = modelo("GM-2.5-4A", Ir_A=3.2)
    lo, hi = BANDA_CLASE["10"]
    assert (lo, hi) == (4.0, 10.0)
    t = t_disparo(gm, 7.2 * 3.2, 12)
    assert t is not None and lo < t <= hi, t
    assert gm.salidas()["causa"] == "térmico" and not gm.salidas()["cerrado"]


def test_guardamotor_sigue_al_dial_en_todo_el_rango():
    for ir in (2.5, 3.2, 4.0):
        t = t_disparo(modelo("GM-2.5-4A", Ir_A=ir), 7.2 * ir, 12)
        assert 4.0 < t <= 10.0, (ir, t)


def test_guardamotor_no_dispara_a_1_05_ir_y_dispara_a_1_2_desde_caliente():
    gm = modelo("GM-2.5-4A", Ir_A=3.2)
    assert gm.termico.t_disparo(1.05) == float("inf")  # 1,05 Ir: no dispara nunca (≥ 2 h)
    assert gm.termico.t_disparo(1.2, theta0=1.0) < 2 * 3600
    t = t_disparo(modelo("GM-2.5-4A", Ir_A=3.2), 1.5 * 3.2, 200, previo=3.2)
    assert t is not None and t < LIMITE_1_5_CALIENTE_S["10"], t


def test_magnetico_fijo_en_ii_13_ir_max_no_sigue_al_dial():
    ii = CATALOG["GM-2.5-4A"].electrico.modelo["Ii_A"]
    assert ii == pytest.approx(13 * 4.0)
    for ir in (2.5, 4.0):
        bajo = modelo("GM-2.5-4A", Ir_A=ir)
        bajo.paso(DT, {"I_A": ii - 0.5})
        assert not bajo.salidas()["disparado"], ir  # el térmico tarda: no es instantáneo
        gm = modelo("GM-2.5-4A", Ir_A=ir)
        gm.paso(DT, {"I_A": [ii, 0.0, 0.0]})  # basta un polo
        assert gm.salidas()["disparado"] and gm.salidas()["causa"] == "magnético", ir


def test_guardamotor_sin_ajuste_de_ir_es_error_accionable():
    with pytest.raises(ModeloIncompleto, match=r"-Q1 \(GM-2\.5-4A\): falta el ajuste «Ir_A».*entre 2\.5 y 4.*add_device\.ajustes"):
        modelo("GM-2.5-4A")
    with pytest.raises(ModeloIncompleto, match="va entre 2.5 y 4"):
        modelo("GM-2.5-4A", Ir_A=5)


def test_guardamotor_rearma_cuando_enfria_y_la_manija_abre():
    gm = modelo("GM-2.5-4A", Ir_A=3.2)
    t_disparo(gm, 10 * 3.2, 5)
    gm.accionar("rearmar")
    assert gm.salidas()["disparado"]  # caliente: no rearma
    for _ in range(4000):
        gm.paso(0.5, {"I_A": 0.0})
    gm.accionar("rearmar")
    assert gm.salidas()["cerrado"]
    gm.accionar("abrir")
    assert not gm.salidas()["cerrado"] and not gm.salidas()["disparado"]
    with pytest.raises(ValueError, match="no admite «pulsar»"):
        gm.accionar("pulsar")


# ── relé térmico (clase 10A, rearme manual) ──────────────────────────────────────────────────


def test_rele_termico_clase_10a_normalizada_y_en_su_banda():
    assert CATALOG["RT-2.5-4A"].electrico.modelo["clase"] == "10A"
    assert CATALOG["GM-2.5-4A"].electrico.modelo["clase"] == "10"  # misma forma: texto
    rt = modelo("RT-2.5-4A", "-F2", Ir_A=3.0)
    lo, hi = BANDA_CLASE["10A"]
    t = t_disparo(rt, 7.2 * 3.0, 12)
    assert lo < t <= hi, t
    rt.paso(DT, {"I_A": 0})
    assert rt.salidas()["disparado"]  # manual: queda disparado
    assert rt.ACCIONES == ("rearmar",)


# ── ITM curva C (IEC 60898-1) ────────────────────────────────────────────────────────────────


def test_itm_curva_c_magnetico_entre_5_y_10_in():
    assert BANDA_MAGNETICA_ITM["C"] == (5.0, 10.0)
    In = CATALOG["ITM-C10-3P"].electrico.modelo["In_A"]
    a5 = modelo("ITM-C10-3P", "-F1")
    assert t_disparo(a5, 5 * In, 0.1) is None  # en el borde bajo: no dispara en 0,1 s
    a10 = modelo("ITM-C10-3P", "-F1")
    t = t_disparo(a10, 10 * In, 0.1)
    assert t is not None and t <= 0.1 and a10.salidas()["causa"] == "magnético"
    assert 5 < a10.Im_In < 10


def test_itm_termico_en_las_bandas_de_la_norma():
    In = 10.0
    itm = modelo("ITM-C10-3P", "-F1")
    assert itm.termico.t_disparo(1.13) == float("inf")  # 1,13 In: no dispara
    assert itm.termico.t_disparo(1.45, theta0=1.13 ** 2) < 3600
    t = t_disparo(itm, 2.55 * In, 70)
    lo, hi = ITM_BANDA_2_55_S
    assert lo < t < hi, t


def test_itm_1p_n_protege_un_polo():
    itm = modelo("ITM-C2-1PN", "-F3")
    assert itm.polos == 1


# ── fusible 5×20 (IEC 60127-2) ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("curva", ["F", "T"])
def test_cartucho_en_las_bandas_de_su_hoja(curva):
    for x, (lo, hi) in BANDA_FUSIBLE[curva].items():
        f = modelo("BORNE-FUS-5X20", "-F9", cartucho_In_A=2.0, cartucho_curva=curva)
        t = f.termico.t_disparo(x)
        assert lo <= t <= hi, (curva, x, t)
    f = modelo("BORNE-FUS-5X20", "-F9", cartucho_In_A=2.0, cartucho_curva=curva)
    assert f.termico.t_disparo(1.5) == float("inf")


def test_portafusible_cada_unidad_su_cartucho_y_el_cartucho_es_ajuste():
    f = crear_modelo("-F9", "BORNE-FUS-5X20", CATALOG["BORNE-FUS-5X20"].electrico.modelo,
                     {"cartucho_In_A": 1.0}, cantidad=2)
    assert f.curva == "T" and "punto medio" not in " ".join(f.hipotesis)
    for _ in range(int(0.5 / DT)):
        f.paso(DT, {"I_A": [10.0, 0.5]})
    s = f.senales()
    assert s["-F9.1.disparado"] and not s["-F9.2.disparado"] and s["-F9.disparado"]
    f.accionar("reponer", 1)
    assert not f.salidas()["disparado"]
    with pytest.raises(ModeloIncompleto, match="falta el ajuste «cartucho_In_A»"):
        modelo("BORNE-FUS-5X20", "-F9")
