"""`add_program`, el programa del PLC en el carril eléctrico (plan V8.3 D3–D4).

  - se COMPILA en la mutación contra los bornes del PLC: un error de sintaxis, de tipos o una
    dirección que el PLC no tiene rechaza el comando con línea, columna y «¿quisiste decir…?» y
    el documento queda como estaba;
  - un PLC que no existe o no es PLC, un segundo programa para el mismo PLC o un `ciclos` con un
    PROGRAM que no está también son errores accionables;
  - en la CARGA es tolerante: el programa roto se suprime y el resto abre;
  - viaja en `insert_project` con el aspecto de función de la instancia;
  - la tabla de tags sale en `get_circuit` y la co-simulación toma el programa del carril.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from cosim_lazo_banco import PROGRAMA
from tablero_electrico import arranque_variador_plc

from apolo.doc.document import Document, DocumentError
from apolo.services.electrico import circuito


def _tablero(nombre: str = "tablero") -> Document:
    doc = Document(nombre)
    doc.execute_many(arranque_variador_plc())
    return doc


@pytest.fixture(scope="module")
def con_programa():
    doc = _tablero()
    doc.execute("create_box", {"name": "Gabinete", "width": 600, "depth": 200, "height": 800})
    cid = doc.execute("add_program", {"plc": "-K1", "fuente": PROGRAMA, "ciclo_ms": 5})
    return doc, cid


def test_el_programa_se_compila_y_publica_sus_tags(con_programa):
    doc, cid = con_programa
    [p] = doc.electrico.programas
    assert (p.plc, p.nombre, p.ciclo_ms, p.id, p.lenguaje) == ("-K1", "Main", 5, cid, "st")
    assert p.compilado is not None and [n for n, _, _ in p.compilado.programas] == ["Main"]
    tags = {t["variable"]: (t["direccion"], t["borne"], t["sentido"]) for t in p.tags}
    assert tags["marcha"] == ("%IX0.2", "I0.2", "entrada") and tags["vfd_marcha"] == ("%QX0.0", "Q0.0", "salida")
    c = circuito(doc)
    assert c["resumen"]["n_programas"] == 1
    [prog] = c["programas"]
    assert prog["plc"] == "-K1" and prog["comando"] == cid and len(prog["tags"]) == len(p.tags)
    assert circuito(doc, "-K1")["programas"] and "programas" not in circuito(doc, "-T2")


@pytest.mark.parametrize("params,textos", [
    ({"plc": "-K1", "fuente": PROGRAMA.replace("en_marcha := TRUE", "en_marca := TRUE")},
     ["no compila", "línea 18, columna 3", "¿Quisiste decir «en_marcha»?"]),
    ({"plc": "-K1", "fuente": "PROGRAM Main\nVAR x : BOOL; END_VAR\nx := 3;\nEND_PROGRAM"},
     ["no compila", "línea 3"]),
    ({"plc": "-K1", "fuente": PROGRAMA.replace("%IX0.4", "%IX9.9")}, ["no compila", "%IX9.9"]),
    ({"plc": "-K2", "fuente": PROGRAMA}, ["-K2 no existe en el tablero", "PLC del tablero: -K1"]),
    ({"plc": "-T2", "fuente": PROGRAMA}, ["-T2 no es un PLC"]),
    ({"plc": "-K1", "fuente": PROGRAMA, "ciclos": {"Mian": 5}}, ["no tiene PROGRAM «Mian»", "¿Quisiste decir"]),
])
def test_un_programa_que_no_compila_rechaza_el_comando(params, textos):
    doc = _tablero()
    antes = (list(doc.commands), doc.electrico)
    with pytest.raises(DocumentError) as e:
        doc.execute("add_program", params)
    for t in textos:
        assert t in str(e.value), str(e.value)
    assert (doc.commands, doc.electrico) == antes  # el documento quedó como estaba


def test_un_plc_lleva_un_programa_y_editarlo_lo_recompila():
    doc = _tablero()
    cid = doc.execute("add_program", {"plc": "-K1", "fuente": PROGRAMA})
    with pytest.raises(DocumentError, match=r"ya tiene su programa \(" + cid):
        doc.execute("add_program", {"plc": "-K1", "fuente": PROGRAMA})
    antes = doc.electrico.programas[0].compilado
    doc.edit(cid, {"plc": "-K1", "fuente": PROGRAMA.replace("cuenta : INT", "cuenta : DINT"),
                   "nombre": "Faja"})
    [p] = doc.electrico.programas
    assert p.nombre == "Faja" and p.compilado is not antes and "DINT" in p.fuente
    doc.undo()
    assert doc.electrico.programas[0].nombre == "Main"
    doc.undo()
    assert doc.electrico.programas == ()


def test_el_programa_puede_ir_antes_que_su_plc_en_el_log():
    doc = Document("orden")
    lote =[{"type": "add_program", "params": {"plc": "-K1", "fuente": PROGRAMA}}] + arranque_variador_plc()
    doc.execute_many(lote)
    assert [p.plc for p in doc.electrico.programas] == ["-K1"]


def _con_log_roto(doc: Document) -> bytes:
    """El `.apolo` del documento con la fuente del programa rota a mano (un archivo viejo)."""
    datos = doc.to_apolo_bytes()
    entrada, salida = io.BytesIO(datos), io.BytesIO()
    with zipfile.ZipFile(entrada) as zi, zipfile.ZipFile(salida, "w") as zo:
        for nombre in zi.namelist():
            contenido = zi.read(nombre)
            if nombre == "commands.json":
                log = json.loads(contenido)
                for c in log:
                    if c["type"] == "add_program":
                        c["params"]["fuente"] = "PROGRAM Main\nx := ;\nEND_PROGRAM"
                contenido = json.dumps(log).encode()
            zo.writestr(nombre, contenido)
    return salida.getvalue()


def test_la_carga_es_tolerante_y_la_mutacion_estricta(con_programa):
    doc, cid = con_programa
    vuelta = Document.from_apolo_bytes(doc.to_apolo_bytes())
    assert vuelta.electrico == doc.electrico and vuelta.electrico.programas[0].compilado is not None
    roto = _con_log_roto(doc)
    with pytest.raises(DocumentError, match="no compila"):
        Document.from_apolo_bytes(roto)
    abierto = Document.from_apolo_bytes(roto, tolerant=True)
    assert [s["command_id"] for s in abierto.regen_suppressed] == [cid]
    assert abierto.electrico.programas == () and len(abierto.electrico.dispositivos) == len(doc.electrico.dispositivos)


def test_insert_project_trae_el_programa_con_el_aspecto_de_funcion(con_programa):
    origen, _ = con_programa
    lay = Document("layout")
    digest = lay.add_attachment(origen.to_apolo_bytes())
    c1 = lay.execute("insert_project", {"attachment": digest, "name": "Faja 1"})
    lay.execute("insert_project", {"attachment": digest, "name": "Faja2"})
    progs = {p.plc: p for p in lay.electrico.programas}
    assert set(progs) == {"=Faja1-K1", "=Faja2-K1"}
    assert progs["=Faja1-K1"].id.startswith(f"{c1}_") and progs["=Faja1-K1"].ciclo_ms == 5
    assert progs["=Faja1-K1"].tags == origen.electrico.programas[0].tags
    assert lay.regen_suppressed == []


def test_la_cosimulacion_toma_el_programa_del_carril_y_test_plc_lo_reemplaza(con_programa):
    pytest.importorskip("mujoco")
    from cosim_lazo_banco import escenario_variador, faja_variador

    from apolo.services.cosim_snapshot import snapshot_cosim

    doc = faja_variador()
    doc.execute("add_program", {"plc": "-K1", "fuente": PROGRAMA, "ciclo_ms": 5})
    snap = snapshot_cosim(doc, escenario_variador(0.5))
    [p] = snap.programas
    assert (p.plc, p.ciclo_ms) == ("-K1", 5) and p.compilado is doc.electrico.programas[0].compilado
    otra = PROGRAMA.replace("piloto := en_marcha;", "piloto := TRUE;")
    snap = snapshot_cosim(doc, escenario_variador(0.5),
                          programas=[{"plc": "-K1", "nombre": "Prueba", "fuente": otra}])
    [p] = snap.programas
    assert (p.nombre, p.ciclo_ms) == ("Prueba", 10) and p.compilado is not doc.electrico.programas[0].compilado
