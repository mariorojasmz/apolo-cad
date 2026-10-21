"""El carril eléctrico tras la FAT por MCP (plan V8.3 F6, defectos 2 y 3):

  - el -M1 con NMRV pedía `i` y `eta_reductor` de a uno, en `test_plc`, aunque su pieza ligada
    se llamara «… i=30»: ahora la relación y el η que dice el NOMBRE de la pieza ligada entran
    como ajustes DEDUCIDOS (declarados en `get_circuit` y en las hipótesis de la co-simulación),
    y lo que falta lo pide el ERC en UN aviso por dispositivo, con el `edit_command` listo; el
    snapshot también los pide todos juntos;
  - `find_commands` resumía cada dispositivo como «add_device»: ahora dice designación y ref (y
    `name` busca en ellas).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tablero_electrico import arranque_directo, arranque_variador_plc

import apolo.api.main as api
from apolo.doc.document import Document
from apolo.library.electrico.ajustes import deducir_de_la_pieza
from apolo.services.cosim_snapshot import snapshot_cosim
from apolo.services.electrico import chequeo, circuito
from apolo.services.errors import ServiceError

RANGOS = {"tipo": "motor", "i": [7.5, 100], "eta_reductor": [0.45, 0.90]}
NOMBRE_73 = "Motorreductor NMRV-090 (eje hueco, i=30)"  # la pieza c682 de la faja 73


@pytest.mark.parametrize("nombre,esperado", [
    (NOMBRE_73, {"i": 30.0}),
    ("Motorreductor NMRV-090 1:40", {"i": 40.0}),
    ("NMRV-090 i = 12,5 η=0,7", {"i": 12.5, "eta_reductor": 0.7}),
    ("NMRV-090 i: 30 eta=70 %", {"i": 30.0, "eta_reductor": 0.7}),
    ("NMRV-090 i=200", {}),            # fuera del rango de la ficha: no se toma
    ("NMRV-090 eta=0,95", {}),         # ídem (0,45–0,90)
    ("Motorreductor NMRV-090", {}),    # el nombre no lo dice
    ("Eje motriz Ø35 h7", {}),
])
def test_la_relacion_y_el_eta_salen_del_nombre_de_la_pieza(nombre, esperado):
    d = deducir_de_la_pieza(nombre, "c682", RANGOS, {})
    assert {k: x["valor"] for k, x in d.items()} == esperado
    assert all(x["origen"] == f"del nombre de la pieza c682 («{nombre}»)" for x in d.values())


def test_un_ajuste_declarado_gana_al_nombre():
    assert deducir_de_la_pieza(NOMBRE_73, "c682", RANGOS, {"i": 25}) == {}


def _faja_nmrv(nombre: str, *, eta: float | None = None) -> tuple[Document, str]:
    """Una faja de prueba con un NMRV-090 de catálogo llamado `nombre`, ligado al -M1 del tablero
    por variador SIN los ajustes del reductor (salvo `eta`)."""
    doc = Document("nmrv")
    doc.execute("create_belt_conveyor", {"largo": 3000, "ancho_banda": 500, "altura": 800})
    cid = doc.execute("insert_component", {"component": "NMRV-090", "name": nombre,
                                           "position": {"x": 1500, "y": -600, "z": 300}})
    cmds = arranque_variador_plc(pieza_motor=cid)
    m1 = next(c for c in cmds if c["params"].get("designacion") == "-M1")
    m1["params"]["ajustes"] = {"conexion": "triangulo", **({"eta_reductor": eta} if eta else {})}
    doc.execute_many(cmds)
    return doc, next(c["id"] for c in doc.commands if c["params"].get("designacion") == "-M1")


def _avisos_ajustes(doc) -> list[dict]:
    return [r for r in chequeo(doc)["reglas"] if r["regla"] == "ajustes para simular"]


def test_el_erc_pide_juntos_los_ajustes_que_faltan():
    doc, m1 = _faja_nmrv("Motorreductor NMRV-090")
    [aviso] = _avisos_ajustes(doc)
    assert aviso["estado"] == "aviso" and aviso["elementos"] == ["-M1"]
    det = aviso["detalle"]
    assert "-M1 (NMRV-090)" in det and "i (relación del reductor" in det and "eta_reductor (" in det
    assert f"edit_command('{m1}', " in det
    assert '{"ajustes": {"conexion": "triangulo", "i": 53.75, "eta_reductor": 0.675}}' in det
    assert chequeo(doc)["errores"] == 0  # no es un error de cableado: el tablero se arma igual
    # el snapshot los pide también juntos (antes: el primero, y test_plc tras test_plc)
    with pytest.raises(ServiceError) as e:
        snapshot_cosim(doc, {"duracion_s": 1})
    assert "le faltan los ajustes" in e.value.detail and "eta_reductor" in e.value.detail
    assert " i (relación" in e.value.detail


def test_la_pieza_ligada_da_la_relacion_y_el_erc_pide_solo_el_eta():
    doc, m1 = _faja_nmrv(NOMBRE_73)
    [aviso] = _avisos_ajustes(doc)
    assert "eta_reductor (" in aviso["detalle"] and "i (relación" not in aviso["detalle"]
    assert '"i": 30.0' in aviso["detalle"]  # el ejemplo ya lleva lo deducido
    [m] = circuito(doc, "-M1")["dispositivos"]
    assert m["ajustes"]["i"] == 30.0 and m["ajustes_deducidos"]["i"].startswith("del nombre de la pieza")


def test_con_el_eta_declarado_no_hay_aviso_y_la_cosimulacion_declara_lo_deducido():
    doc, _ = _faja_nmrv(NOMBRE_73, eta=0.7)
    assert _avisos_ajustes(doc) == []
    esc = {"duracion_s": 0.2, "mecanica": {"con_autodeteccion": True},
           "acoples": {"motores": {"-M1": {"junta": "c1_eje_motriz", "direccion_transporte": [1, 0, 0]}}}}
    snap = snapshot_cosim(doc, esc)
    [h] = [x for x in snap.hipotesis if x.startswith("-M1:")]
    assert h.startswith("-M1: i = 30, del nombre de la pieza") and NOMBRE_73 in h
    m = next(d for d in snap.dispositivos if d.designacion == "-M1")
    assert m.ajustes["i"] == 30.0 and m.ajustes["eta_reductor"] == 0.7


# ── defecto 3: find_commands nombra el carril ───────────────────────────────────────────────


@pytest.fixture
def c(monkeypatch):
    doc = Document("tablero")
    motor = doc.execute("insert_component", {"component": "MOTOR-075", "name": "Motorreductor"})
    doc.execute_many(arranque_directo(pieza_motor=motor))
    doc.execute("add_device", {"ref": "PLC-14DI-10DO-24VDC", "designacion": "-K1"})
    doc.execute("add_program", {"plc": "-K1", "nombre": "Main",
                                "fuente": "PROGRAM Main VAR x : BOOL; END_VAR x := TRUE; END_PROGRAM"})
    monkeypatch.setattr(api, "DOC", doc)
    return TestClient(api.app)


def _resumenes(c, **params) -> list[str]:
    r = c.get("/api/commands", params=params)
    assert r.status_code == 200, r.text
    return [f["resumen"] for f in r.json()["commands"]]


def test_find_commands_resume_el_carril_por_designacion_y_ref(c):
    dispositivos = _resumenes(c, type="add_device")
    assert "-M1 MOTOR-075 (pieza c1)" in dispositivos and "-Q2 GM-2.5-4A" in dispositivos
    assert not any(r == "add_device" for r in dispositivos)
    assert _resumenes(c, type="add_cable") == ["-W1 CABLE-4G1.5 (+TAB1 → -M1)"]
    cables = _resumenes(c, type="add_wire")
    assert "-G1:L1 → -Q1:1" in cables and "-Q3:2 → -M1:U1 (-W1 hilo 1)" in cables
    assert _resumenes(c, type="add_program") == ["programa Main de -K1"]


def test_find_commands_busca_por_designacion_ref_y_borne(c):
    m1 = _resumenes(c, name="-M1")
    assert m1[0] == "-M1 MOTOR-075 (pieza c1)" and "-Q3:4 → -M1:V1 (-W1 hilo 2)" in m1
    assert _resumenes(c, name="gm-2.5") == ["-Q2 GM-2.5-4A"]  # sin mayúsculas
    assert _resumenes(c, name="Motorreductor") == ["Motorreductor"]  # el `name` de siempre
