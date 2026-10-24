"""La faja de prueba de categoría 3 (plan mandos-de-seguridad D6): la pareja verde/roja que usa la
verificación de un plan de seguridad. Faja del banco (`cosim_lazo_banco`) por variador y PLC.

- ROJA: el tablero de un solo NC (`arranque_variador_plc`: 11-12 en paralelo a S1 y S2 del STO)
  con ese contacto pegado (falla de red `pegado`, cosim-fallas D3): la seta no corta el par.
- VERDE: la seta de dos NC (`arranque_variador_plc_cat3`: 11-12 a S1, 21-22 a S2) con el MISMO
  contacto pegado: la otra rama corta y la máquina para igual que sana.
- Con resguardo + relé de seguridad (`arranque_variador_rele_seguridad`): abrir el resguardo para;
  con un NC del interruptor pegado para igual y el relé NO rearma (la falla se nota en el ciclo
  siguiente); con un NA del relé soldado también para (el otro canal del STO).
- Los escenarios de antes (sin estos aparatos) dan la misma huella: D5, en `test_cosim_epoch.py`
  y la bitácora F1.
"""

from __future__ import annotations

import pytest
from tablero_electrico import arranque_variador_plc_cat3, arranque_variador_rele_seguridad, no_ok

from apolo.library.electrico.erc import erc

pytest.importorskip("mujoco")

from apolo.cosim.planificador import correr  # noqa: E402
from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from cosim_lazo_banco import PROGRAMAS, _faja, escenario_variador, faja_variador  # noqa: E402

VFD = {"acel_s": 1.0, "decel_s": 1.0}
SETA = {"t": 1.5, "accion": "presionar", "dispositivo": "-S0"}
PEGA_11 = {"t": 1.0, "tipo": "falla", "rama": "-S0:11-12", "falla": "pegado"}
REARME = {"t": 0.05, "accion": "pulsar", "dispositivo": "-S3", "durante_s": 0.1}
ABRE = {"t": 1.5, "accion": "abrir", "dispositivo": "-B2"}


@pytest.fixture(scope="module")
def un_nc():
    return faja_variador()


@pytest.fixture(scope="module")
def cat3():
    doc = _faja("faja-cat3")
    doc.execute_many(arranque_variador_plc_cat3(ajustes_variador=VFD))
    return doc


@pytest.fixture(scope="module")
def con_rele():
    doc = _faja("faja-rele")
    doc.execute_many(arranque_variador_rele_seguridad(ajustes_variador=VFD))
    return doc


def _correr(doc, *eventos, acciones=(SETA,), dur=2.2):
    return correr(snapshot_cosim(doc, escenario_variador(dur, acciones=acciones, eventos=eventos),
                                 programas=PROGRAMAS))


def _para(res) -> bool:
    f = res["final"]
    return f["-T2.sto"] and not f["-T2.par_habilitado"]


def test_los_tableros_de_prueba_quedan_como_el_de_un_nc_en_el_erc(un_nc, cat3, con_rele):
    base = no_ok(erc(un_nc.electrico))
    assert no_ok(erc(cat3.electrico)) == base
    assert no_ok(erc(con_rele.electrico)) == base


def test_la_pareja_verde_roja_de_la_seta_con_un_nc_pegado(un_nc, cat3):
    sano_1, sano_2 = _correr(un_nc), _correr(cat3)
    assert _para(sano_1) and _para(sano_2)
    assert sano_1["final"]["-M1.rpm"] == pytest.approx(sano_2["final"]["-M1.rpm"])  # misma parada
    rojo = _correr(un_nc, PEGA_11)
    assert not _para(rojo) and rojo["final"]["-M1.rpm"] > 1700  # sigue a plena marcha
    assert rojo["final"]["-S0.accionado"]  # la seta apretada y su único NC cerrado
    verde = _correr(cat3, PEGA_11)
    assert _para(verde) and verde["final"]["-S0.accionado"]
    assert verde["final"]["-M1.rpm"] == pytest.approx(sano_2["final"]["-M1.rpm"])  # para igual que sana
    pegada = [e for e in verde["eventos"] if e.get("evento") == "falla"]
    assert pegada == [{"t": 1.0, "programado_s": 1.0, "evento": "falla", "rama": "-S0:11-12",
                       "falla": "pegado", "valor": True}]


def test_el_otro_canal_tambien_salva(cat3):
    pega_21 = {**PEGA_11, "rama": "-S0:21-22"}
    assert _para(_correr(cat3, pega_21))
    ambos = _correr(cat3, PEGA_11, pega_21)  # con los DOS pegados ya no (la categoría 3 tolera UNA)
    assert not _para(ambos)


def test_el_rele_arma_y_el_resguardo_abierto_para(con_rele):
    marcha = _correr(con_rele, acciones=(REARME,))
    f = marcha["final"]
    assert f["-K2.salidas"] and f["-B2.cerrado"] and not _para(marcha) and f["-M1.rpm"] > 1700
    assert any("discrepancia" in h for h in marcha["hipotesis"])
    abre = _correr(con_rele, acciones=(REARME, ABRE))
    assert _para(abre) and not abre["final"]["-K2.salidas"] and not abre["final"]["-B2.cerrado"]
    sin_rearme = _correr(con_rele, acciones=())
    assert not sin_rearme["final"]["-K2.salidas"] and sin_rearme["final"]["-M1.rpm"] < 1  # nunca arrancó


def _cerrar_y_rearmar(t: float) -> list[dict]:
    return [{"t": t, "accion": "cerrar", "dispositivo": "-B2"},
            {"t": t + 0.1, "accion": "pulsar", "dispositivo": "-S3", "durante_s": 0.1}]


def test_un_nc_del_resguardo_pegado_para_igual_y_el_rele_no_rearma(con_rele):
    sano = _correr(con_rele, acciones=(REARME, ABRE, *_cerrar_y_rearmar(1.8)), dur=2.4)
    assert sano["final"]["-K2.salidas"] and not sano["final"]["-K2.espera_ciclo"]  # rearma
    pega = {"t": 1.0, "tipo": "falla", "rama": "-B2:11-12", "falla": "pegado"}
    parada = _correr(con_rele, pega, acciones=(REARME, ABRE))
    assert _para(parada)  # el canal 2 cortó
    malo = _correr(con_rele, pega, acciones=(REARME, ABRE, *_cerrar_y_rearmar(1.8)), dur=2.4)
    f = malo["final"]
    assert not f["-K2.salidas"] and f["-K2.espera_ciclo"] and _para(malo)  # el canal pegado se nota


def test_un_na_del_rele_soldado_el_otro_canal_del_sto_corta(con_rele):
    soldada = {"t": 1.0, "tipo": "falla", "dispositivo": "-K2", "falla": "salida_pegada", "valor": "13-14"}
    res = _correr(con_rele, soldada, acciones=(REARME, ABRE))
    assert _para(res) and res["final"]["-K2.averia"] == "salida_pegada 13-14"
    assert not res["final"]["-K2.salidas"]
