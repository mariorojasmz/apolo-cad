"""Los comandos del tablero eléctrico en el documento (plan V8.1 F3: D2, D3, D4).

- `add_device`/`add_wire`/`add_cable` son del CARRIL: no crean geometría, no re-ejecutan la
  escena y su evaluador (`commands/electrico_eval.py`) arma `doc.electrico`, el
  `ModeloElectrico` que el ERC de F2 revisa: el arranque directo de `test_electrico_erc.py`
  declarado como comandos queda VERDE.
- Params estrictos al entrar (clave desconocida con «¿quisiste decir…?») y `=expr` en
  `seccion_mm2`, que sigue a la variable.
- D3: una designación vacía se MATERIALIZA al entrar (la siguiente libre de su letra) y se
  guarda en el log; borrar -Q1 no renombra -Q2.
- D4: una referencia que no resuelve es error accionable con sugerencias; borrar un
  dispositivo que sus cables nombran se rechaza (estricto) y en la carga se suprime (tolerante).
"""

from __future__ import annotations

import pytest
from tablero_electrico import arranque_directo, dev, no_ok, wire

from apolo.commands import registry as registry_mod
from apolo.commands.errors import CommandError
from apolo.doc.document import Document, DocumentError
from apolo.library.electrico.erc import erc, resumen
from apolo.library.electrico.modelo import ModeloElectrico


def _params(doc: Document, cmd_id: str) -> dict:
    return next(c["params"] for c in doc.commands if c["id"] == cmd_id)


@pytest.fixture
def ejecutados(monkeypatch):
    llamadas: list[str] = []
    real = registry_mod.run_executor

    def contar(spec, ctx, cmd_id, model):
        llamadas.append(cmd_id)
        return real(spec, ctx, cmd_id, model)

    monkeypatch.setattr(registry_mod, "run_executor", contar)
    return llamadas


# ------------------------------------------------------------------ el tablero entero
def test_el_arranque_directo_declarado_con_comandos_queda_verde():
    d = Document("tablero")
    ids = d.execute_many(arranque_directo())
    m = d.electrico
    assert isinstance(m, ModeloElectrico)
    assert len(m.dispositivos) == 14 and len(m.cables) == 1 and len(m.conductores) == 29
    assert d.scene == {}  # el carril no crea geometría
    reglas = erc(m)
    assert not no_ok(reglas), no_ok(reglas)
    assert resumen(reglas) == {"estado": "ok", "errores": 0, "avisos": 0}
    # trazabilidad: cada elemento lleva el comando que lo declaró
    assert {x.id for x in (*m.dispositivos, *m.cables, *m.conductores)} == set(ids)
    # el conductor del cable toma sección y color del hilo; los puntos quedan canónicos
    en_cable = next(c for c in m.conductores if c.cable == "-W1" and c.hilo == "PE")
    assert (en_cable.seccion_mm2, en_cable.color, en_cable.puntos) == (1.5, "GNYE",
                                                                       ("-X0:2", "-M1:PE"))
    gm = next(x for x in m.dispositivos if x.designacion == "-Q2")
    assert gm.ajustes == {"Ir_A": 3.2} and gm.ubicacion == "+TAB1"
    assert d.check_integrity() == []


def test_un_error_de_cableado_lo_ve_el_erc_no_la_mutacion():
    d = Document("tablero")
    d.execute_many(arranque_directo())
    # la bobina de 24 VDC colgada de la fase: el tablero se ARMA (la mutación pasa) y el ERC
    # lo marca (tensión cruzada)
    d.execute("add_wire", {"puntos": ["-Q1:2", "-Q3:A1"], "color": "BK", "seccion_mm2": 1})
    reglas = erc(d.electrico)
    assert any(r["regla"] in ("tensión cruzada", "cortocircuito") and r["estado"] == "error"
               for r in reglas)


# ------------------------------------------------------------------ params estrictos y =expr
def test_params_estrictos_al_entrar():
    d = Document()
    with pytest.raises(CommandError, match=r"seccion.*¿quisiste decir"):
        d.execute("add_wire", {"puntos": ["-G1:L1", "-Q1:1"], "seccion": 2.5})
    with pytest.raises(CommandError, match="borne"):
        d.execute("add_wire", {"puntos": ["-G1:L1", "-Q1"]})  # le falta el borne
    with pytest.raises(CommandError, match="color IEC 60757"):
        d.execute("add_wire", {"puntos": ["-G1:L1", "-Q1:1"], "color": "NEGRO"})
    with pytest.raises(CommandError, match="`cable` e `hilo` van juntos"):
        d.execute("add_wire", {"puntos": ["-G1:L1", "-Q1:1"], "cable": "-W1"})
    with pytest.raises(CommandError, match="referencia, no una designación"):
        d.execute("add_device", {"ref": "SECC-25A-3P", "designacion": "-Q1:1"})
    assert d.commands == []


def test_seccion_acepta_expresion_y_sigue_a_la_variable():
    d = Document()
    d.execute("set_variable", {"name": "S_MANDO", "expression": "0.75"})
    d.execute_many(arranque_directo(seccion_mando="=S_MANDO"))
    mando = [c for c in d.electrico.conductores if c.color == "BU"]
    assert mando and all(c.seccion_mm2 == 0.75 for c in mando)
    d.execute("set_variable", {"name": "S_MANDO", "expression": "1"})
    assert all(c.seccion_mm2 == 1.0 for c in d.electrico.conductores if c.color == "BU")
    with pytest.raises(DocumentError, match="NO_EXISTE"):
        d.execute_many([wire("-Q1:2", "-Q2:1", seccion_mm2="=NO_EXISTE*2")])


def test_el_carril_no_reejecuta_la_escena(ejecutados):
    d = Document()
    d.execute_many([{"type": "create_box", "params": {"name": f"B{i}", "width": 10,
                                                      "depth": 10, "height": 10}}
                    for i in range(20)])
    ejecutados.clear()
    ids = d.execute_many(arranque_directo())
    d.edit(ids[2], {"ajustes": {"Ir_A": 3.6}}, merge=True)
    d.remove_commands([ids[-1]])
    d.undo()
    assert ejecutados == []
    assert len(d._regen_sigs) == 20


# ------------------------------------------------------------------ D3: designación materializada
def test_designacion_vacia_se_materializa_y_se_guarda():
    d = Document()
    ids = d.execute_many([dev("CONT-9A-24VDC"), dev("GM-2.5-4A"), dev("RELE-INT-24VDC"),
                          dev("CONT-9A-220VAC", "-Q7"), dev("CONT-12A-24VDC"),
                          {"type": "add_cable", "params": {"ref": "CABLE-5G1"}}])
    assert [_params(d, i)["designacion"] for i in ids] == ["-Q1", "-Q2", "-K1", "-Q7", "-Q3",
                                                          "-W1"]
    # borrar -Q1 no renombra -Q2; la próxima vacía toma la menor libre
    d.remove_commands([ids[0]])
    assert _params(d, ids[1])["designacion"] == "-Q2"
    nuevo = d.execute("add_device", {"ref": "GM-1-1.6A"})
    assert _params(d, nuevo)["designacion"] == "-Q1"
    assert "-Q1" in d.undo_labels[0]  # la etiqueta de deshacer nombra la designación asignada
    # el log guardado ya la trae: abrirlo da lo mismo, sin volver a numerar
    otro = Document.from_apolo_bytes(d.to_apolo_bytes())
    assert sorted(x.designacion for x in otro.electrico.dispositivos) == [
        "-K1", "-Q1", "-Q2", "-Q3", "-Q7"]


def test_editar_con_designacion_vacia_la_vuelve_a_asignar():
    d = Document()
    a, b = d.execute_many([dev("CONT-9A-24VDC", "-Q5"), dev("CONT-9A-24VDC", "-Q1")])
    d.edit(a, {"designacion": ""}, merge=True)
    assert _params(d, a)["designacion"] == "-Q2"  # la menor libre, sin contarse a sí mismo
    d.edit_many([{"command_id": b, "params": {"designacion": ""}}], merge=True)
    assert _params(d, b)["designacion"] == "-Q1"


def test_designacion_repetida_se_rechaza():
    d = Document()
    d.execute("add_device", {"ref": "CONT-9A-24VDC", "designacion": "-Q1"})
    with pytest.raises(DocumentError, match="designación -Q1 ya la usa"):
        d.execute("add_device", {"ref": "GM-2.5-4A", "designacion": "-Q1"})
    with pytest.raises(DocumentError, match="ya la usa"):
        d.execute("add_cable", {"ref": "CABLE-5G1", "designacion": "-Q1"})


# ------------------------------------------------------------------ D4: referencias
def test_una_referencia_que_no_resuelve_es_error_con_sugerencia():
    d = Document()
    d.execute_many(arranque_directo())
    n = len(d.commands)
    with pytest.raises(DocumentError, match=r"-Q1 \(SECC-25A-3P\) no tiene el borne 22.*"
                                            r"¿Quisiste decir: 2"):
        d.execute("add_wire", {"puntos": ["-Q1:22", "-Q2:1"]})
    with pytest.raises(DocumentError, match=r"el dispositivo -Q9 no existe"):
        d.execute("add_wire", {"puntos": ["-Q9:1", "-Q2:1"]})
    with pytest.raises(DocumentError, match=r"el cable -W2 no existe"):
        d.execute("add_wire", {"puntos": ["-Q3:2", "-M1:U1"], "cable": "-W2", "hilo": "1"})
    with pytest.raises(DocumentError, match=r"no tiene el hilo 5; hilos: 1, 2, 3, PE"):
        d.execute("add_wire", {"puntos": ["-Q3:2", "-M1:U1"], "cable": "-W1", "hilo": "5"})
    assert len(d.commands) == n


def test_borrar_un_dispositivo_cableado_se_rechaza_y_la_carga_lo_suprime():
    d = Document()
    ids = d.execute_many(arranque_directo())
    with pytest.raises(DocumentError, match=r"el dispositivo -Q1 no existe"):
        d.remove_commands([ids[1]])  # -Q1: sus cables lo nombran
    datos = Document.from_apolo_bytes(d.to_apolo_bytes())
    sin_q1 = [c for c in datos.commands if c["id"] != ids[1]]
    roto = Document("roto")
    roto.commands = sin_q1
    roto._seq = d._seq
    abierto = Document.from_apolo_bytes(roto.to_apolo_bytes(), tolerant=True)
    caidos = {s["command_id"] for s in abierto.regen_suppressed}
    assert caidos and all(_params(d, c)["puntos"] for c in caidos)  # sólo conductores de -Q1
    assert all(any(p.startswith("-Q1:") for p in _params(d, c)["puntos"]) for c in caidos)
    assert len(abierto.electrico.dispositivos) == 13


def test_ref_ajustes_cantidad_y_tipo_se_validan():
    d = Document()
    with pytest.raises(DocumentError, match=r"no está en el catálogo.*¿Quisiste decir"):
        d.execute("add_device", {"ref": "CONT-9A-24V"})
    with pytest.raises(DocumentError, match="pieza mecánica"):
        d.execute("add_device", {"ref": "6205"})
    with pytest.raises(DocumentError, match="decláralo con add_cable"):
        d.execute("add_device", {"ref": "CABLE-4G1.5"})
    with pytest.raises(DocumentError, match=r"no tiene el ajuste «Ir»; .*¿Quisiste decir: Ir_A"):
        d.execute("add_device", {"ref": "GM-2.5-4A", "ajustes": {"Ir": 3}})
    with pytest.raises(DocumentError, match="va entre 2.5 y 4"):
        d.execute("add_device", {"ref": "GM-2.5-4A", "ajustes": {"Ir_A": 5}})
    with pytest.raises(DocumentError, match="sólo vale en una bornera"):
        d.execute("add_device", {"ref": "CONT-9A-24VDC", "cantidad": 3})
    d.execute_many([dev("SECC-25A-3P", "-Q1"), dev("GM-2.5-4A", "-Q2")])
    with pytest.raises(DocumentError, match="es un cable multipolar"):
        d.execute("add_wire", {"puntos": ["-Q1:2", "-Q2:1"], "tipo": "CABLE-4G1.5"})
    with pytest.raises(DocumentError, match="no es la de COND-H07VK-2.5"):
        d.execute("add_wire", {"puntos": ["-Q1:2", "-Q2:1"], "tipo": "COND-H07VK-2.5",
                               "seccion_mm2": 4})
    puente = d.execute("add_wire", {"puntos": ["-Q1:2", "-Q1:4"], "tipo": "puente"})
    assert next(c for c in d.electrico.conductores if c.id == puente).tipo == "puente"


def test_pieza_liga_el_dispositivo_a_un_solido():
    d = Document()
    motor = d.execute("insert_component", {"component": "MOTOR-075", "name": "Motorreductor"})
    caja = d.execute("create_box", {"name": "Caja", "width": 10, "depth": 10, "height": 10})
    fid = next(f for f, feat in d.scene.items() if feat.command_id == motor)
    d.execute("add_device", {"ref": "MOTOR-075", "designacion": "-M1", "pieza": motor})
    assert d.electrico.dispositivos[0].pieza == fid  # el command_id resuelve a su pieza
    with pytest.raises(DocumentError, match="es el componente MOTOR-075, no MOTOR-150"):
        d.execute("add_device", {"ref": "MOTOR-150", "pieza": fid})
    with pytest.raises(DocumentError, match=r"no existe en el modelo"):
        d.execute("add_device", {"ref": "MOTOR-150", "pieza": "c99"})
    d.execute("add_device", {"ref": "GAB-6040", "pieza": caja})  # pieza a medida: vale
    assert d.electrico.dispositivos[1].pieza == caja
