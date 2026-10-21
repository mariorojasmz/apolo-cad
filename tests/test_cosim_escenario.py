"""El escenario y el snapshot de la co-simulación (plan V8.3 D11.1, D12): todo lo que no se puede
correr se rechaza ANTES de simular, con un texto que dice qué poner («¿quisiste decir…?»)."""

from __future__ import annotations

import pickle

import pytest

from apolo.cosim.escenario import EscenarioInvalido, leer_escenario
from apolo.services.errors import ServiceError

pytest.importorskip("mujoco")

from apolo.services.cosim_snapshot import snapshot_cosim  # noqa: E402
from cosim_lazo_banco import PROGRAMAS, escenario_directo, escenario_variador, faja_directo, faja_variador  # noqa: E402


@pytest.fixture(scope="module")
def directo():
    return faja_directo()


@pytest.fixture(scope="module")
def variador():
    return faja_variador()


# ── el escenario, puro ───────────────────────────────────────────────────────────────────────


def test_un_escenario_completo_se_lee_ordenado():
    esc = leer_escenario({
        "duracion_s": 5, "condiciones": {"red_conectada": False, "selectores": {"-S5": "I"}},
        "acciones": [{"t": 2, "accion": "liberar", "dispositivo": "-S0"},
                     {"t": 1, "accion": "pulsar", "dispositivo": "-S1", "durante_s": 0.2}],
        "eventos": [{"t": 3, "tipo": "atasco", "junta": "j", "par_Nm": 80, "duracion_s": 1},
                    {"t": 0.5, "tipo": "producto", "nombre": "caja", "dims_mm": [1, 1, 1], "posicion_mm": [0, 0, 0]}],
        "trazas": {"analogicas_hz": 25}})
    assert [a.t for a in esc.acciones] == [1, 2] and not esc.red_conectada
    assert esc.eventos[0].datos == {"junta": "j", "par_Nm": 80.0} and esc.eventos[0].duracion_s == 1
    assert esc.productos == [{"nombre": "caja", "dims_mm": [1, 1, 1], "posicion_mm": [0, 0, 0], "desde_s": 0.5}]
    assert esc.analogicas_hz == 25 and esc.selectores == {"-S5": "I"}
    assert pickle.loads(pickle.dumps(esc)) == esc  # viaja al worker


@pytest.mark.parametrize("malo,texto", [
    ({"duracion_s": 2, "acciones": [{"t": 1, "accion": "pulsr", "dispositivo": "-S1"}]}, "¿Quisiste decir «pulsar»?"),
    ({"duracion_s": 2, "acciones": [{"t": 3, "accion": "pulsar", "dispositivo": "-S1"}]}, "fuera de [0.0, 2.0]"),
    ({"duracion_s": 2, "acciones": [{"t": 1, "accion": "presionar", "dispositivo": "-S0", "durante_s": 1}]},
     "«durante_s» es de «pulsar»"),
    ({"duracion_s": 2, "eventos": [{"t": 1, "tipo": "atasco", "junta": "j"}]}, "«atasco» pide «par_Nm»"),
    ({"duracion_s": 2, "eventos": [{"t": 1, "tipo": "corte_de_fase", "fase": "L4"}]}, "Opciones: L1, L2, L3"),
    ({"duracion_s": 2, "condiciones": {"plc_ru": True}}, "¿Quisiste decir «plc_run»?"),
    ({"duracion": 2}, "¿Quisiste decir «duracion_s»?"),
    ({"duracion_s": 2, "acoples": {"sensores": {"-B1": {"origen": [0, 0, 0]}}}}, "falta «direccion»"),
])
def test_un_escenario_malo_dice_que_corregir(malo, texto):
    with pytest.raises(EscenarioInvalido, match=None) as e:
        leer_escenario(malo)
    assert texto in str(e.value)


# ── el snapshot: contra el tablero y la mecánica del documento ──────────────────────────────


def _error(doc, esc, **kw) -> str:
    with pytest.raises(ServiceError) as e:
        snapshot_cosim(doc, esc, **kw)
    assert e.value.status_code == 400
    return e.value.detail


def test_un_motor_sin_acoplar_es_error_accionable(directo):
    esc = escenario_directo(1.0)
    esc["acoples"] = {}
    assert 'acoples.motores = {"-M1": {"junta"' in _error(directo, esc)


def test_un_dispositivo_que_no_existe_sugiere_el_parecido(directo):
    esc = escenario_directo(1.0, acciones=[{"t": 0.5, "accion": "pulsar", "dispositivo": "-S3"}])
    texto = _error(directo, esc)
    assert "no tiene el dispositivo «-S3»" in texto and "¿Quisiste decir" in texto


def test_una_accion_que_el_aparato_no_admite(directo):
    esc = escenario_directo(1.0, acciones=[{"t": 0.5, "accion": "presionar", "dispositivo": "-S2"}])
    assert "-S2 (PULS-22-VERDE-NA, pulsador) no admite «presionar»" in _error(directo, esc)


def test_un_atasco_en_una_junta_que_no_se_simula(directo):
    esc = escenario_directo(1.0, eventos=[{"t": 0.5, "tipo": "atasco", "junta": "c1_eje_motris", "par_Nm": 10}])
    assert "¿Quisiste decir «c1_eje_motriz»?" in _error(directo, esc)


def test_cable_cortado_corta_sus_hilos_y_uno_que_no_esta_en_las_redes_es_error(directo):
    from apolo.cosim.planificador import correr

    esc = escenario_directo(1.0, eventos=[{"t": 0.6, "tipo": "cable_cortado", "rama": "-W9"}])
    assert "«-W9» no es una rama" in _error(directo, esc) and "unión ideal" in _error(directo, esc)
    # el cable -W1 del motor (6 m declarados): cortado, el motor queda sin corriente
    esc = escenario_directo(1.0, eventos=[{"t": 0.6, "tipo": "cable_cortado", "rama": "-W1"}])
    res = correr(snapshot_cosim(directo, esc))
    assert res["final"]["-M1.I_A"] == 0.0 and res["final"]["-Q3.cerrado"]
    assert [e["evento"] for e in res["eventos"] if "evento" in e] == ["cable_cortado"]


def test_un_programa_que_no_compila_o_un_plc_que_no_existe(variador):
    malo = [{"plc": "-K1", "nombre": "Main", "fuente": "PROGRAM Main\nx := ;\nEND_PROGRAM"}]
    assert _error(variador, escenario_variador(1.0), programas=malo).startswith("programas[0] (-K1):")
    otro = [{**PROGRAMAS[0], "plc": "-A9"}]
    assert "«-A9» no es un PLC del tablero; PLC: -K1" in _error(variador, escenario_variador(1.0), programas=otro)


def test_un_documento_sin_tablero_no_se_cosimula():
    from apolo.doc.document import Document

    doc = Document("sin tablero")
    assert "no tiene tablero" in _error(doc, {"duracion_s": 1})


def test_el_snapshot_viaja_en_pickle_y_lleva_el_motor_por_placa(variador):
    snap = snapshot_cosim(variador, escenario_variador(1.0), programas=PROGRAMAS)
    vuelta = pickle.loads(pickle.dumps(snap))
    assert vuelta.red == snap.red and len(vuelta.dispositivos) == len(snap.dispositivos)
    [m] = snap.dinamica.motores
    assert m.info["modelo"].startswith("motor de inducción") and m.fuerza_max > 0  # forcelimited
    assert 'forcelimited="true"' in snap.dinamica.xml
    [a] = snap.motores
    assert (a.designacion, a.junta, a.actuador) == ("-M1", "c1_eje_motriz", m.nombre)
    assert snap.sensores[0].designacion == "-B1" and snap.programas[0].plc == "-K1"
