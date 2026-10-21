"""Las aserciones de un escenario y su veredicto (plan V8.3 D12), puras, sobre un resultado de
co-simulación armado a mano (la forma del JSON del worker): cada ventana en verde y en rojo, el
alias de las variables del PLC, la señal que no existe y los errores al leerlas. Y la lectura
por partes de `get_simulation` (`cosim/consulta.py`)."""

from __future__ import annotations

import pytest

from apolo.cosim.consulta import compacto, parte
from apolo.cosim.escenario import EscenarioInvalido, leer_escenario
from apolo.cosim.veredicto import evaluar

ACCIONES = [{"t": 0.3, "accion": "pulsar", "dispositivo": "-S1", "durante_s": 0.2},
            {"t": 2.2, "accion": "presionar", "dispositivo": "-S0"}]
EVENTOS = [{"t": 2.0, "tipo": "atasco", "junta": "j", "par_Nm": 500, "duracion_s": 1.0},
           {"t": 3.0, "tipo": "corte_de_fase", "fase": "L3"}]

#: Lo que devolvería el worker: discretas por cambio, analógicas a 2 Hz, eventos con su hora real.
RES = {
    "resumen": {"duracion_s": 4.0, "intercambios": 2000, "huella": "h"},
    "trazas": {
        "discretas": {
            "-Q2.disparado": [[0.0, False], [2.5, True]],
            "-K1.Main.en_marcha": [[0.0, False], [0.31, True], [2.21, False]],
            "-K1.Main.cuenta": [[0.0, 0], [1.5, 1], [2.0, 2]],
            "-K1.Aux.cuenta": [[0.0, 0]],
            "-K1.%QX0.0": [[0.0, False], [0.31, True], [2.21, False]],
            "-T2.estado": [[0.0, "parado"], [0.3, "marcha"], [3.0, "falla"]],
        },
        "analogicas": {"t": [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
                       "senales": {"-M1.rpm": [0.0, 600.0, 1200.0, 1750.0, 1760.0, 1755.0, 800.0, 10.0, 0.0],
                                   "caja.x_mm": [None, None, -500.0, -300.0, 0.0, 200.0, 400.0, 600.0, 800.0]}},
    },
    "eventos": [
        {"t": 0.3, "programado_s": 0.3, "accion": "pulsar", "dispositivo": "-S1"},
        {"t": 2.0, "programado_s": 2.0, "evento": "atasco", "junta": "j", "par_Nm": 500.0},
        {"t": 2.2, "programado_s": 2.2, "accion": "presionar", "dispositivo": "-S0"},
        {"t": 3.0, "programado_s": 3.0, "evento": "atasco.fin", "junta": "j", "par_Nm": 500.0},
        {"t": 3.0, "programado_s": 3.0, "evento": "corte_de_fase", "fase": "L3"},
    ],
    "final": {"-Q2.disparado": True, "-K1.Main.en_marcha": False, "-K1.Main.cuenta": 2,
              "-K1.Aux.cuenta": 0, "-T2.estado": "falla", "-M1.rpm": 0.0, "caja.x_mm": 800.0},
}


def _una(asercion):
    esc = leer_escenario({"duracion_s": 4, "acciones": ACCIONES, "eventos": EVENTOS,
                          "aserciones": [asercion]})
    [fila] = evaluar(esc.aserciones, RES)["aserciones"]
    return fila


@pytest.mark.parametrize("asercion,pasa", [
    # al_final (con el alias del PLC: «-K1.cuenta» no es ambigua… salvo con otro PROGRAM)
    ("-K1.Main.cuenta == 2 al_final", True),
    ("-K1.Main.cuenta == 3 al_final", False),
    ("-T2.estado == falla al_final", True),
    ("-Q2.disparado al_final", True),
    # en t: retención de orden cero en las discretas, la muestra vigente en las analógicas
    ("-M1.rpm > 1700 en 2 s", True),
    ("-M1.rpm > 1700 en 1,2 s", False),
    ("-K1.%QX0.0 == true en 0,31 s", True),
    ("-K1.%QX0.0 == true en 0,3 s", False),
    # dentro_de Δ desde una acción o un evento (con la hora REAL del ancla)
    ("-M1.rpm >= 1700 dentro_de 1,5 s desde pulsar -S1", True),
    ("-M1.rpm >= 1700 dentro_de 1 s desde pulsar -S1", False),
    ("-Q2.disparado dentro_de 1 s desde atasco", True),
    ("-Q2.disparado dentro_de 0,4 s desde atasco", False),
    ("-K1.%QX0.0 == false dentro_de 0,05 s desde presionar -S0", True),
    ("-K1.%QX0.0 == false dentro_de 0,005 s desde presionar -S0", False),
    ("-T2.estado == falla dentro_de 0,1 s desde atasco.fin", True),
    ("-T2.estado == falla dentro_de 0,1 s desde corte_de_fase L3", True),
    # siempre / nunca, en toda la corrida o desde un ancla
    ("-M1.rpm <= 1800 siempre", True),
    ("-M1.rpm <= 1700 siempre", False),
    ("-M1.rpm > 2000 nunca", True),
    ("-Q2.disparado nunca", False),
    ("-K1.Main.en_marcha nunca desde corte_de_fase L3", True),
    ("-K1.Main.en_marcha nunca desde presionar -S0", False),  # 10 ms de scan: aún en marcha en t0
    ("-Q2.disparado siempre desde atasco.fin", True),
    # una analógica que todavía no existe (None) no cumple ni rompe
    ("caja.x_mm >= 0 dentro_de 1 s desde pulsar -S1", False),
    ("caja.x_mm >= 0 dentro_de 2 s desde pulsar -S1", True),
])
def test_cada_ventana_en_verde_y_en_rojo(asercion, pasa):
    fila = _una(asercion)
    assert fila["pasa"] is pasa, fila
    assert fila["detalle"]


def test_dentro_de_dice_cuando_se_cumplio_y_por_que_no():
    ok = _una("-M1.rpm >= 1700 dentro_de 1,5 s desde pulsar -S1")
    assert ok["t"] == 1.5 and "a los 1.2 s" in ok["detalle"]
    malo = _una("-M1.rpm >= 1700 dentro_de 1 s desde pulsar -S1")
    assert "no se cumple en [0.3, 1.3] s" in malo["detalle"] and "máximo 1200" in malo["detalle"]


def test_el_alias_del_plc_y_la_senal_que_no_existe():
    assert _una("-K1.Main.en_marcha == false al_final")["pasa"]
    ambigua = _una("-K1.cuenta == 2 al_final")  # Main.cuenta y Aux.cuenta
    assert not ambigua["pasa"] and "ambigua" in ambigua["detalle"]
    assert _una("-K1.en_marcha == false al_final")["senal"] == "-K1.Main.en_marcha"
    assert _una("-k1.MAIN.EN_MARCHA == false al_final")["pasa"]  # ST no distingue mayúsculas
    falta = _una("-M2.rpm > 0 al_final")
    assert not falta["pasa"] and "no está en las trazas" in falta["detalle"] and "«-M1.rpm»" in falta["detalle"]


def test_el_veredicto():
    esc = leer_escenario({"duracion_s": 4, "acciones": ACCIONES,
                          "aserciones": ["-M1.rpm > 2000 nunca", "-Q2.disparado al_final"]})
    assert evaluar(esc.aserciones, RES)["veredicto"] == "pasa"
    esc = leer_escenario({"duracion_s": 4, "aserciones": ["-M1.rpm > 2000 nunca", "-Q2.disparado nunca"]})
    v = evaluar(esc.aserciones, RES)
    assert v["veredicto"] == "falla" and v["n_fallidas"] == 1
    assert evaluar([], RES) == {"veredicto": "sin_aserciones", "aserciones": [], "n_fallidas": 0}


def test_texto_y_objeto_dan_la_misma_asercion():
    esc = leer_escenario({"duracion_s": 4, "acciones": ACCIONES, "aserciones": [
        "-M1.rpm >= 1700 dentro de 1,5 s desde pulsar -S1",
        {"senal": "-M1.rpm", "op": ">=", "valor": 1700, "ventana": "dentro_de", "delta_s": 1.5,
         "desde": {"accion": "pulsar", "dispositivo": "-S1"}}]})
    a, b = esc.aserciones
    assert a == b and a["texto"] == "-M1.rpm >= 1700 dentro_de 1.5 s desde pulsar -S1"
    tol = leer_escenario({"duracion_s": 4, "aserciones": [{"senal": "-M1.rpm", "valor": 1760.4,
                                                           "ventana": "en", "t": 2, "tol": 0.5}]})
    assert evaluar(tol.aserciones, RES)["veredicto"] == "pasa"


@pytest.mark.parametrize("malo,texto", [
    ("-M1.rpm >= 1700 dentro_de 3 s desde pulsar -S9", "¿Quisiste decir «pulsar -S1»?"),
    ("-M1.rpm >= 1700 dentro_de 3 s desde pulsr -S1", "no es una acción ni un evento"),
    ("-M1.rpm >= 1700 dentro_de 3 s", "pide «desde <ancla>»"),
    ("-M1.rpm >= 1700 al_fina", "¿Quisiste decir «al_final»?"),
    ("-M1.rpm => 1700 al_final", "comparación «=>» no válida"),
    ("-M1.rpm >= 1700", "falta la ventana"),
    ("-Q2.disparado >= true al_final", "sólo se compara con == o !="),
    ("-M1.rpm > 1 en 9 s", "fuera de la corrida"),
    ("-M1.rpm > 1 al_final desde pulsar -S1", "«desde» va con dentro_de, siempre o nunca"),
    ("rpm > 1 al_final", "«<designación>.<señal>»"),
    ({"senal": "-M1.rpm", "ventana": "al_final", "valr": 3}, "¿Quisiste decir «valor»?"),
    ("-Q2.disparado dentro_de 1 s desde caida_de_red", "no tiene «caida_de_red»"),
])
def test_una_asercion_mala_dice_que_corregir(malo, texto):
    with pytest.raises(EscenarioInvalido) as e:
        leer_escenario({"duracion_s": 4, "acciones": ACCIONES, "eventos": EVENTOS,
                        "aserciones": [malo]})
    assert texto in str(e.value) and "aserciones[0]" in str(e.value)


# ── get_simulation por partes ──────────────────────────────────────────────────────────────


def _base():
    esc = leer_escenario({"duracion_s": 4, "aserciones": ["-Q2.disparado al_final"]})
    return compacto(RES, evaluar(esc.aserciones, RES), simulacion="s1", escenario="atasco")


def test_el_compacto_no_lleva_trazas_y_el_resumen_nombra_las_senales():
    base = _base()
    assert base["veredicto"] == "pasa" and "trazas" not in base and base["n_eventos"] == 5
    r = parte(RES, base, "resumen")
    assert "-M1.rpm" in r["senales"]["analogicas"] and "-Q2.disparado" in r["senales"]["discretas"]


def test_las_trazas_por_ventana_patron_y_pagina():
    base = _base()
    tr = parte(RES, base, "trazas", senales=["-K1.en_marcha", "-M1.*"], desde_s=1.0, hasta_s=3.0,
               limite=3, offset=1)
    assert tr["discretas"]["-K1.Main.en_marcha"]["cambios"] == [[2.21, False]]  # [1,0 vigente, 2,21]: pág. 2
    assert tr["discretas"]["-K1.Main.en_marcha"]["total"] == 2
    an = tr["analogicas"]
    assert an["t"] == [1.5, 2.0, 2.5] and an["senales"]["-M1.rpm"] == [1750.0, 1760.0, 1755.0]
    assert an["total"] == 5 and an["truncado"]
    malo = parte(RES, base, "trazas", senales=["-Z9.*", "-M1.rmp"])
    assert len(malo["problemas"]) == 2 and "«-M1.rpm»" in malo["problemas"][1]
    with pytest.raises(ValueError, match="pide `senales`"):
        parte(RES, base, "trazas")
    with pytest.raises(ValueError, match="partes: resumen"):
        parte(RES, base, "todo")
    assert parte(RES, base, "eventos", limite=2, offset=4) == {
        "simulacion": "s1", "eventos": [RES["eventos"][4]], "total": 5, "offset": 4, "truncado": False}
    assert parte(RES, base, "final", senales=["-K1.Main.cuenta"])["final"] == {"-K1.Main.cuenta": 2}
