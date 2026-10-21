"""Del modelo eléctrico de V8.1 al formato plano de las redes (plan V8.3 F3): `services/cosim_red`.

Los dos tableros del ERC (`test_electrico_erc`): arranque directo y por variador con PLC. Se mira
qué actuador mueve cada contacto (el bloque auxiliar sigue a su contactor), cómo entran las
fuentes (la red detrás de su Zk, la salida del variador ideal, sus 10 V del potenciómetro), las
cargas (bobina, piloto, entradas de IEC 61131-2, potencia) y los conductores (sección y largo del
conductor o de su cable), y que el resultado viaja como JSON. Además, el formato rechaza lo que
no puede armar con un error en español.
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from apolo.cosim.modelos import crear_modelo
from apolo.cosim.red import EntradaInvalida, armar, leer_entrada
from apolo.library.catalog import CATALOG
from apolo.services.cosim_red import R_ENTRADA_ANALOGICA_OHM, R_ENTRADA_DIGITAL_OHM, entrada_red
from test_electrico_erc import arranque_directo, arranque_variador


def por_id(lista: list[dict]) -> dict:
    return {x["id"]: x for x in lista}


def con_largos(modelo):
    """El tablero del ERC con el cable del motor de 6 m y 1 m por conductor suelto."""
    conds = tuple(c if c.cable else dataclasses.replace(c, largo_m=1.0) for c in modelo.conductores)
    cables = tuple(dataclasses.replace(c, largo_m=6.0) for c in modelo.cables)
    return dataclasses.replace(modelo, conductores=conds, cables=cables)


def test_arranque_directo_en_formato_plano():
    e = entrada_red(con_largos(arranque_directo()))
    json.dumps(e)  # viaja en el snapshot de F4
    ramas, cargas, fuentes = por_id(e["ramas"]), por_id(e["cargas"]), por_id(e["fuentes"])
    # contactos: el auxiliar -Q3A sigue a la bobina de -Q3; el guardamotor por su estado
    assert ramas["-Q3A:53-54"]["actuador"] == "-Q3.bobina" and ramas["-Q3A:53-54"]["contacto"] == "NA"
    assert ramas["-Q3:13-14"]["actuador"] == "-Q3.bobina"
    assert ramas["-Q2:1-2"]["contacto"] == "proteccion" and ramas["-Q2:1-2"]["actuador"] == "-Q2.cerrado"
    assert ramas["-S1:11-12"]["contacto"] == "NC" and ramas["-S0:11-12"]["actuador"] == "-S0.mano"
    assert e["actuadores"]["-Q2.cerrado"] is True and e["actuadores"]["-Q1.mano"] is True
    assert e["actuadores"]["-Q3.bobina"] is False and e["actuadores"]["-S2.mano"] is False
    # fuentes: la red detrás de su impedancia, la de 24 V ideal
    assert fuentes["-G1"]["sistema"] == "3F" and fuentes["-G1"]["ideal"] is False
    assert fuentes["-T1"]["tipo"] == "DC" and fuentes["-T1"]["U_V"] == 24.0
    # cargas
    assert cargas["-Q3:A1-A2"] == {"id": "-Q3:A1-A2", "tipo": "bobina", "bornes": ["-Q3:A1", "-Q3:A2"],
                                   "dispositivo": "-Q3", "modo": "impedancia", "Un_V": 24.0, "S_VA": 2.4}
    assert cargas["-P1:X1-X2"]["R_ohm"] == pytest.approx(24 / 0.018)
    assert cargas["-T1:L-N"]["modo"] == "potencia" and cargas["-M1:U1-V1-W1"]["modo"] == "potencia"
    # conductores: el cable -W1 de 6 m y 1,5 mm² (del cable), los sueltos con su sección
    assert ramas["-W1.1"]["seccion_mm2"] == 1.5 and ramas["-W1.1"]["largo_m"] == 6.0
    tramos = [r for r in e["ramas"] if r["tipo"] == "conductor" and r["de"] == "-T1:L+"]
    assert tramos and tramos[0]["largo_m"] == pytest.approx(0.5)  # 3 puntos: dos tramos de 1 m / 2


def test_sin_largo_los_conductores_son_uniones_ideales_y_se_declara():
    e = entrada_red(arranque_directo())
    assert not [r for r in e["ramas"] if r["tipo"] == "conductor"]
    assert any("sin largo" in h for h in e["hipotesis"])


def test_las_dos_redes_del_tablero_directo():
    redes = armar(entrada_red(con_largos(arranque_directo())))
    mando, pot = redes.mando, redes.potencia
    assert "-Q3:A1-A2" in mando._carga_idx and "-P1:X1-X2" in mando._carga_idx
    assert "-T1:L-N" in pot._carga_idx and "-M1:U1-V1-W1" in pot._carga_idx
    assert "-Q3.bobina" in mando.claves and "-Q2.cerrado" in pot.claves
    red = crear_modelo("-G1", "RED-3F-220V-60HZ", CATALOG["RED-3F-220V-60HZ"].electrico.modelo)
    res = pot.paso({}, {"-G1": red.salidas()})
    assert res.carga("-T1:L-N")["U_V"] == pytest.approx(220.0, rel=1e-3)  # entre L1 y L2 por el ITM
    assert res.carga("-M1:U1-V1-W1")["fases"] == 0  # el contactor abierto: el motor sin tensión
    res = pot.paso({"-Q3.bobina": True}, {"-G1": red.salidas()})
    assert res.carga("-M1:U1-V1-W1")["fases"] == 3
    assert res.carga("-M1:U1-V1-W1")["U_V"] == pytest.approx(220.0, rel=1e-3)


def test_arranque_por_variador_con_plc_y_potenciometro():
    e = entrada_red(arranque_variador())
    fuentes, cargas, ramas = por_id(e["fuentes"]), por_id(e["cargas"]), por_id(e["ramas"])
    assert fuentes["-T2.1"]["tipo"] == "AC" and fuentes["-T2.1"]["ideal"] is True  # la salida U V W
    assert fuentes["-T2.2"]["tipo"] == "DC" and fuentes["-T2.2"]["U_V"] == 10.0  # +10V / GND
    assert cargas["-K1:I0.2-1M"]["R_ohm"] == R_ENTRADA_DIGITAL_OHM
    assert cargas["-T2:AI1-GND"]["R_ohm"] == R_ENTRADA_ANALOGICA_OHM
    assert cargas["-T2:L1-L2-L3"]["modo"] == "potencia"
    pote = ramas["-S1:potenciometro"]
    assert (pote["de"], pote["cursor"], pote["a"]) == ("-S1:P1", "-S1:P2", "-S1:P3")
    assert ramas["-K1:3L+-Q0.0"]["actuador"] == "-K1.Q0.0"  # la salida del PLC por su grupo
    assert any("-K1" in h and "no declara su consumo" in h for h in e["hipotesis"])
    mando = armar(e).mando
    est = {"-K1.Q0.0": True, "-S1.potenciometro": 0.5}
    res = mando.paso(est, {"-T1": 24.0, "-T2.2": 10.0})
    assert res.carga("-T2:DI1-COM")["U_V"] == pytest.approx(24.0, abs=0.01)  # marcha por Q0.0
    assert res.carga("-T2:S1-SCM")["U_V"] == pytest.approx(24.0, abs=0.01)  # STO con la seta libre
    # el cursor al medio de 10 kΩ cargado por los 10 kΩ de AI1: 10 V · (5k ∥ 10k) / (5k + 5k ∥ 10k)
    assert res.carga("-T2:AI1-GND")["U_V"] == pytest.approx(4.0, rel=1e-3)
    res = mando.paso({**est, "-S0.mano": True}, {"-T1": 24.0, "-T2.2": 10.0})  # seta presionada
    assert res.carga("-T2:S1-SCM")["U_V"] == pytest.approx(0.0, abs=0.3)
    assert res.carga("-K1:I0.1-1M")["U_V"] == pytest.approx(0.0, abs=0.3)


@pytest.mark.parametrize("malo,error", [
    ({"ramas": [{"id": "r", "tipo": "cable", "de": "-A:1", "a": "-B:1"}]}, "tipo «cable» no válido"),
    ({"ramas": [{"id": "r", "tipo": "contacto", "de": "-A:1", "a": "-B:1", "contacto": "NA"}]}, "actuador"),
    ({"ramas": [{"id": "r", "tipo": "conductor", "de": "-A:1", "a": "-B:1", "seccion_mm2": 1.5}]}, "largo_m"),
    ({"ramas": [{"id": "r", "tipo": "union", "de": "A1", "a": "-B:1"}]}, "designación:borne"),
    ({"fuentes": [{"id": "-T1", "tipo": "DC", "U_V": 24, "polos": {"-T1:L+": "+"}}]}, "sus dos polos"),
    ({"fuentes": [{"id": "-G1", "tipo": "AC", "U_V": 220, "sistema": "3F", "polos": {"-G1:N": "N"}}]},
     "el polo «N» no existe en 3F"),
    ({"cargas": [{"id": "c", "bornes": ["-A:1"], "modo": "impedancia"}]}, "son 2"),
    ({"cargas": [{"id": "c", "bornes": ["-A:1", "-A:2"], "modo": "constante"}]}, "«modo»"),
    ({"ramas": [{"id": "r", "tipo": "union", "de": "-A:1", "a": "-B:1"},
                {"id": "r", "tipo": "union", "de": "-A:1", "a": "-B:1"}]}, "repetida"),
])
def test_el_formato_rechaza_lo_que_no_puede_armar(malo, error):
    with pytest.raises(EntradaInvalida, match=error):
        leer_entrada(malo)


def test_el_formato_ida_y_vuelta():
    e = leer_entrada(entrada_red(con_largos(arranque_directo())))
    assert leer_entrada(json.loads(json.dumps(e.como_dict()))) == e
