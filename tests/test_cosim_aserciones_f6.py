"""Las aserciones tras la FAT por MCP (plan V8.3 F6, defectos 4 y 5), puras, sobre el resultado
armado a mano de `test_cosim_aserciones.py`:

  - `siempre`/`nunca desde X + 50 ms` (`tras_ms`): el margen explícito para el tiempo de
    reacción del tablero; sin margen (el default) la violación a pocos ms del ancla lo sugiere;
  - `dentro_de Δ desde X y se mantiene [D s]` (`mantener_s`): tocar el valor una vez no basta;
  - la comparación tipa: «-T2.falla == true» no se cumple con el texto «sobrecorriente».
"""

from __future__ import annotations

import copy

import pytest

from apolo.cosim.escenario import EscenarioInvalido, leer_escenario
from apolo.cosim.veredicto import evaluar
from test_cosim_aserciones import ACCIONES, EVENTOS, RES as _RES

RES = copy.deepcopy(_RES)
RES["trazas"]["discretas"]["-T2.falla"] = [[0.0, ""], [2.5, "sobrecorriente"]]
RES["trazas"]["discretas"]["-T2.rele_falla"] = [[0.0, False], [2.5, True]]
#: toca 1700 a 0,5 s, cae a 100 y vuelve a 1,5 s para quedarse
RES["trazas"]["analogicas"]["senales"]["-M2.rpm"] = [0.0, 1750.0, 100.0, 1750.0, 1760.0, 1770.0,
                                                     1780.0, 1790.0, 1800.0]
RES["final"].update({"-T2.falla": "sobrecorriente", "-T2.rele_falla": True, "-M2.rpm": 1800.0})


def _una(asercion):
    esc = leer_escenario({"duracion_s": 4, "acciones": ACCIONES, "eventos": EVENTOS,
                          "aserciones": [asercion]})
    [fila] = evaluar(esc.aserciones, RES)["aserciones"]
    return fila


# ── defecto 4: el margen de «siempre/nunca desde X» ─────────────────────────────────────────


def test_sin_margen_la_reaccion_del_tablero_es_roja_y_el_detalle_sugiere_el_margen():
    """El PLC suelta la marcha 10 ms después de la seta (2,2 → 2,21 s): sin margen, «nunca desde
    presionar -S0» mira también ese instante (default deliberado: no esconde un retardo)."""
    malo = _una("-K1.Main.en_marcha nunca desde presionar -S0")
    assert not malo["pasa"] and malo["t"] == 2.2
    assert "a 0 ms del ancla" in malo["detalle"] and "«… desde presionar -S0 + 50 ms»" in malo["detalle"]
    # lejos del ancla no es reacción: no lo sugiere
    lejos = _una("-M1.rpm <= 1700 siempre desde pulsar -S1")
    assert not lejos["pasa"] and "margen" not in lejos["detalle"]


@pytest.mark.parametrize("asercion,pasa", [
    ("-K1.Main.en_marcha nunca desde presionar -S0 + 50 ms", True),
    ("-K1.Main.en_marcha nunca desde presionar -S0 +50ms", True),
    ("-K1.Main.en_marcha nunca desde presionar -S0 + 0,02 s", True),
    ("-K1.Main.en_marcha nunca desde presionar -S0 + 5 ms", False),  # 2,205 < 2,21: aún en marcha
    ("-K1.%QX0.0 == false siempre desde presionar -S0 + 20 ms", True),
    ("-K1.%QX0.0 == false siempre desde presionar -S0", False),
    ({"senal": "-K1.Main.en_marcha", "ventana": "nunca", "desde": "presionar -S0", "tras_ms": 50}, True),
])
def test_el_margen_explicito_empieza_la_ventana_despues_del_ancla(asercion, pasa):
    fila = _una(asercion)
    assert fila["pasa"] is pasa, fila
    if not pasa:
        assert "margen" not in fila["detalle"] or "+" not in str(asercion)


def test_el_margen_en_texto_y_objeto_es_la_misma_asercion():
    esc = leer_escenario({"duracion_s": 4, "acciones": ACCIONES, "aserciones": [
        "-K1.Main.en_marcha nunca desde presionar -S0 + 50 ms",
        {"senal": "-K1.Main.en_marcha", "ventana": "nunca", "desde": "presionar -S0", "tras_ms": 50}]})
    a, b = esc.aserciones
    assert a == b and a["texto"] == "-K1.Main.en_marcha == true nunca desde presionar -S0 + 50 ms"


# ── defecto 5: «y se mantiene» y la comparación que tipa ────────────────────────────────────


@pytest.mark.parametrize("asercion,pasa,t", [
    # tocar basta sin «se mantiene»: -M2 llega a 1750 a 0,5 s y cae
    ("-M2.rpm >= 1700 dentro_de 1,5 s desde pulsar -S1", True, 0.5),
    # con «se mantiene 1 s» el toque de 0,5 s no cuenta; sí el de 1,5 s, que se queda
    ("-M2.rpm >= 1700 dentro_de 1,5 s desde pulsar -S1 y se mantiene 1 s", True, 1.5),
    ("-M2.rpm >= 1700 dentro_de 0,9 s desde pulsar -S1 y se mantiene 1 s", False, 1.0),
    ("-M2.rpm >= 1700 dentro_de 1,5 s desde pulsar -S1 y se mantiene", True, 1.5),  # hasta el final
    # -M1 llega a 1,5 s y la seta lo baja a 3 s
    ("-M1.rpm >= 1700 dentro_de 1,5 s desde pulsar -S1 y se mantiene 1 s", True, 1.5),
    ("-M1.rpm >= 1700 dentro_de 1,5 s desde pulsar -S1 y se mantiene 2 s", False, 3.0),
    ("-M1.rpm >= 1700 dentro_de 1,5 s desde pulsar -S1 y se mantiene", False, 3.0),
    # discretas: el PLC mantiene la marcha hasta la seta
    ("-K1.Main.en_marcha dentro_de 0,1 s desde pulsar -S1 y se mantiene 1,5 s", True, 0.31),
    ("-K1.Main.en_marcha dentro_de 0,1 s desde pulsar -S1 y se mantiene 2 s", False, 2.21),
])
def test_dentro_de_y_se_mantiene(asercion, pasa, t):
    fila = _una(asercion)
    assert fila["pasa"] is pasa, fila
    assert fila["t"] == pytest.approx(t)
    if not pasa:
        assert "no se mantiene" in fila["detalle"]


def test_se_mantiene_mas_alla_de_la_corrida_no_se_confirma():
    fila = _una("-M2.rpm >= 1700 dentro_de 1,5 s desde pulsar -S1 y se mantiene 5 s")
    assert not fila["pasa"] and "la corrida termina antes" in fila["detalle"]


def test_se_mantiene_en_texto_y_objeto():
    esc = leer_escenario({"duracion_s": 4, "acciones": ACCIONES, "aserciones": [
        "-M1.rpm >= 1700 dentro_de 1,5 s desde pulsar -S1 y se mantiene 1 s",
        {"senal": "-M1.rpm", "op": ">=", "valor": 1700, "ventana": "dentro_de", "delta_s": 1.5,
         "desde": "pulsar -S1", "mantener_s": 1},
        {"senal": "-M1.rpm", "op": ">=", "valor": 1700, "ventana": "dentro_de", "delta_s": 1.5,
         "desde": "pulsar -S1", "mantener_s": "fin"}]})
    a, b, c = esc.aserciones
    assert a == b and a["texto"] == "-M1.rpm >= 1700 dentro_de 1.5 s desde pulsar -S1 y se mantiene 1 s"
    assert c["texto"].endswith("desde pulsar -S1 y se mantiene")


@pytest.mark.parametrize("asercion,pasa", [
    ("-T2.falla == sobrecorriente dentro_de 1 s desde atasco", True),
    ('-T2.falla != "" dentro_de 1 s desde atasco', True),
    ('-T2.falla == "" al_final', False),
    ("-T2.rele_falla dentro_de 1 s desde atasco", True),
    ("-Q2.disparado == 1 al_final", True),  # una booleana admite 0/1
])
def test_comparaciones_bien_tipadas(asercion, pasa):
    fila = _una(asercion)
    assert fila["pasa"] is pasa, fila
    assert "comparación de tipos" not in fila["detalle"]


@pytest.mark.parametrize("asercion,pista", [
    ("-T2.falla == true dentro_de 1 s desde atasco", "-T2.rele_falla"),
    ("-T2.falla dentro_de 1 s desde atasco", "«-T2.falla == sobrecorriente»"),
    ("-T2.falla == 1 al_final", "es un texto"),
    ("-M1.rpm == true al_final", "«-M1.rpm > 0»"),
    ("-Q2.disparado == falla al_final", "«-Q2.disparado == true»"),
])
def test_una_comparacion_mal_tipada_es_error_claro(asercion, pista):
    """«-T2.falla == true» se cumplía con «sobrecorriente» (un texto no vacío es verdadero en
    Python): ahora la aserción falla siempre y dice cómo escribirla."""
    fila = _una(asercion)
    assert not fila["pasa"] and fila["detalle"].startswith("comparación de tipos")
    assert pista in fila["detalle"]


@pytest.mark.parametrize("malo,texto", [
    ("-K1.Main.en_marcha dentro_de 1 s desde presionar -S0 + 50 ms", "va con siempre o nunca"),
    ({"senal": "-K1.Main.en_marcha", "ventana": "nunca", "tras_ms": 50}, "va con siempre o nunca"),
    ({"senal": "-K1.Main.en_marcha", "ventana": "nunca", "desde": "presionar -S0", "tras_ms": -5}, "≥ 0"),
    ("-M1.rpm >= 1 siempre desde pulsar -S1 y se mantiene 1 s", "va con dentro_de"),
    ("-M1.rpm >= 1 dentro_de 1 s desde pulsar -S1 y se mantiene un rato", "«y se mantiene 1 s»"),
    ({"senal": "-M1.rpm", "valor": 1, "ventana": "dentro_de", "delta_s": 1, "desde": "pulsar -S1",
      "mantener_s": 0}, "> 0"),
])
def test_los_modificadores_mal_puestos_dicen_que_corregir(malo, texto):
    with pytest.raises(EscenarioInvalido) as e:
        leer_escenario({"duracion_s": 4, "acciones": ACCIONES, "eventos": EVENTOS, "aserciones": [malo]})
    assert texto in str(e.value)
