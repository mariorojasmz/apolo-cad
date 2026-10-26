"""La discrepancia entre los dos canales del STO (plan pedidos-de-extensiones-iii, F2, D5–D7).

El variador (como SINAMICS G120, § 5.10 y § 6.3.3 de su manual de seguridad) vigila que S1 y S2
digan lo mismo: una diferencia breve se tolera, una de más de `STO_discrepancia_ms` es falla y no
se borra con el rearme hasta acusarla con los dos canales (bajarlos y subirlos juntos) o cortando
la red. Con un canal PEGADO los dos nunca bajan juntos: la máquina no rearranca.

Pareja verde/roja en el banco (el relé de seguridad y la seta de dos NC): sana, la marcha repetida
vuelve a arrancar; con S1 del STO pegado, la seta corta igual (el otro canal) pero la marcha
repetida NO arranca y el variador queda en `sto_discrepancia`.
"""

from __future__ import annotations

import pytest
from tablero_electrico import arranque_variador_rele_seguridad

from apolo.cosim.modelos import crear_modelo
from apolo.library.catalog import CATALOG

DT = 0.002
RED = {"U_red_V": [220.0, 220.0, 220.0]}
MARCHA = {**RED, "S1": 24.0, "S2": 24.0, "DI1": 24.0, "AI1": 10.0}


def vfd():
    return crear_modelo("-T2", "VFD-2K2-220", CATALOG["VFD-2K2-220"].electrico.modelo, {})


def correr(m, segundos: float, entradas: dict) -> dict:
    out = {}
    for _ in range(round(segundos / DT)):
        out = m.paso(DT, entradas)
    return out


def test_la_ficha_trae_el_tiempo_de_discrepancia_con_su_fuente():
    for ref in ("VFD-1K5-220", "VFD-2K2-220"):
        assert CATALOG[ref].electrico.modelo["STO_discrepancia_ms"] == 500
    assert vfd().t_disc_max == pytest.approx(0.5)


def test_una_discrepancia_breve_se_tolera():
    m = vfd()
    correr(m, 1.0, MARCHA)
    s = correr(m, 0.4, {**MARCHA, "S1": 0.0})  # un canal abre antes que el otro: 400 ms
    assert s["sto"] and s["falla"] == ""
    correr(m, 0.2, {**MARCHA, "DI1": 0.0})
    assert correr(m, 1.0, MARCHA)["f_Hz"] > 0  # orden de marcha nueva: arranca


def test_una_discrepancia_larga_es_falla_y_el_rearme_no_la_borra_hasta_acusarla():
    m = vfd()
    correr(m, 1.0, MARCHA)
    s = correr(m, 0.6, {**MARCHA, "S2": 0.0})  # un cable cortado en S2
    assert s["falla"] == "sto_discrepancia" and s["rele_falla"] and s["f_Hz"] == 0
    correr(m, 0.1, MARCHA)  # el cable reparado: los dos canales iguales y altos
    m.accionar("rearmar")
    assert correr(m, 0.1, MARCHA)["falla"] == "sto_discrepancia"  # sin acusar
    correr(m, 0.1, {**MARCHA, "S1": 0.0, "S2": 0.0, "DI1": 0.0})  # seleccionar el STO…
    correr(m, 0.1, {**MARCHA, "DI1": 0.0})                         # …y deseleccionarlo
    assert correr(m, 0.05, {**MARCHA, "DI1": 0.0})["falla"] == "sto_discrepancia"  # falta el rearme
    m.accionar("rearmar")
    assert correr(m, 0.05, {**MARCHA, "DI1": 0.0})["falla"] == ""
    assert correr(m, 1.0, MARCHA)["f_Hz"] > 0


def test_cortar_la_red_acusa_la_discrepancia():
    m = vfd()
    correr(m, 1.0, MARCHA)
    correr(m, 0.6, {**MARCHA, "S2": 0.0})
    correr(m, 0.1, {**MARCHA, "U_red_V": [0.0, 0.0, 0.0], "S1": 0.0, "S2": 0.0, "DI1": 0.0})
    correr(m, 0.1, {**MARCHA, "DI1": 0.0})
    m.accionar("rearmar")
    assert correr(m, 0.05, {**MARCHA, "DI1": 0.0})["falla"] == ""


def test_con_un_canal_pegado_la_marca_no_se_acusa():
    sano, malo = vfd(), vfd()
    malo.fallar("canal_sto_pegado", "S1")
    for m in (sano, malo):
        correr(m, 1.0, MARCHA)
        correr(m, 0.8, {**MARCHA, "S1": 0.0, "S2": 0.0, "DI1": 0.0})  # la seta: los dos abren
        correr(m, 0.1, {**MARCHA, "DI1": 0.0})
        m.accionar("rearmar")
        correr(m, 0.05, {**MARCHA, "DI1": 0.0})
    assert correr(sano, 1.0, MARCHA)["f_Hz"] > 0
    s = correr(malo, 1.0, MARCHA)
    assert s["falla"] == "sto_discrepancia" and s["f_Hz"] == 0 and not s["par_habilitado"]
    assert any("SINAMICS G120" in h and "discrepancia" in h for h in malo.hipotesis)


# ── el banco: el relé de seguridad con la seta de dos NC (categoría 3 / 4) ───────────────────

VFD = {"acel_s": 1.0, "decel_s": 1.0}
REARME_RELE = ({"t": 0.05, "accion": "pulsar", "dispositivo": "-S3", "durante_s": 0.1},
               {"t": 1.8, "accion": "pulsar", "dispositivo": "-S3", "durante_s": 0.1})
SETA = ({"t": 1.0, "accion": "presionar", "dispositivo": "-S0"},
        {"t": 1.6, "accion": "liberar", "dispositivo": "-S0"})
DE_NUEVO = ({"t": 2.3, "accion": "rearmar", "dispositivo": "-T2"},
            {"t": 2.5, "accion": "pulsar", "dispositivo": "-S1", "actuador": "marcha", "durante_s": 0.2})
PEGA_S1 = {"t": 0.8, "tipo": "falla", "dispositivo": "-T2", "falla": "canal_sto_pegado", "valor": "S1"}


@pytest.fixture(scope="module")
def con_rele():
    pytest.importorskip("mujoco")
    from cosim_lazo_banco import _faja

    doc = _faja("faja-rele-disc")
    doc.execute_many(arranque_variador_rele_seguridad(ajustes_variador=VFD))
    return doc


def _correr(doc, *eventos):
    from apolo.cosim.planificador import correr as correr_cosim
    from apolo.services.cosim_snapshot import snapshot_cosim
    from cosim_lazo_banco import PROGRAMAS, escenario_variador

    esc = escenario_variador(4.0, acciones=(*REARME_RELE, *SETA, *DE_NUEVO), eventos=eventos)
    return correr_cosim(snapshot_cosim(doc, esc, programas=PROGRAMAS))


def _par_en(res, t: float) -> bool:
    serie = res["trazas"]["discretas"]["-T2.par_habilitado"]
    return [v for tt, v in serie if tt <= t][-1]


def test_verde_sana_la_marcha_repetida_vuelve_a_arrancar(con_rele):
    res = _correr(con_rele)
    assert not _par_en(res, 1.5)  # la seta corta
    f = res["final"]
    assert f["-T2.falla"] == "" and f["-T2.par_habilitado"] and f["-M1.rpm"] > 1000


def test_rojo_con_s1_pegado_la_seta_corta_pero_no_rearranca(con_rele):
    res = _correr(con_rele, PEGA_S1)
    assert not _par_en(res, 1.5)  # el otro canal corta igual: la función no se pierde
    f = res["final"]
    # la marcha repetida (y el rearme del variador) no la arrancan: el motor sigue en su inercia
    assert f["-T2.falla"] == "sto_discrepancia" and not f["-T2.par_habilitado"] and f["-T2.f_Hz"] == 0
    assert not any(v for t, v in res["trazas"]["discretas"]["-T2.par_habilitado"] if t > 1.5)
    t_falla = next(t for t, v in res["trazas"]["discretas"]["-T2.falla"] if v == "sto_discrepancia")
    assert 1.5 <= t_falla <= 1.6  # seta a 1,0 s + 500 ms de discrepancia (+ el relé y el filtro)


def test_el_tiempo_entra_a_la_firma_del_documento(con_rele):
    """D7: un resultado guardado antes del cambio (con un canal pegado) queda VENCIDO por la firma:
    el `modelo` del variador, con su `STO_discrepancia_ms`, entra a ella."""
    from apolo.services.escenarios import _fichas_electricas

    t2 = next(d for d in _fichas_electricas(con_rele)[0] if d["designacion"] == "-T2")
    assert t2["modelo"]["STO_discrepancia_ms"] == 500
