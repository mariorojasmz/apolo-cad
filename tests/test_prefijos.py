"""`doc/prefijos.py`: la escena tras los primeros k comandos, para k ascendente (plan
publicacion-tienda, F1).

Lo que se prueba, sobre un log sintético de ~20 comandos que cruza lo que más rompe un replay
(variables con expresión, booleana que consume su herramienta, patrón, super-comando, mate,
grupos, redondeo y mover en sitio, borrar):
  - cada prefijo k es IGUAL a regenerar `commands[:k]` desde cero (ids, bbox, volumen);
  - el recorrido no toca el documento fuente y cuesta un regenerate (cada executor corre
    una vez), no n²;
  - una pieza que no cambió conserva el MISMO shape (`is`) entre prefijos, también el hijo
    de un mate, que `solve_mates` recoloca en cada regenerate;
  - un comando suprimido en la fuente, un prefijo que no regenera, `insert_project` y
    `run_script` no rompen el recorrido.
"""

from __future__ import annotations

import copy
import math

import pytest

from apolo.doc import document as document_mod
from apolo.doc.document import Document
from apolo.doc.prefijos import iter_prefijos


def _log_rico() -> tuple[Document, dict]:
    d = Document("Banco de pruebas")
    d.execute("set_variable", {"name": "L", "expression": "600"})
    d.execute("set_variable", {"name": "H", "expression": "=L/3"})
    ids = {}
    ids["placa"] = d.execute("create_box", {"name": "Placa base", "width": "=L/2", "depth": 100,
                                            "height": 10})
    ids["agujero"] = d.execute("create_cylinder", {"name": "Agujero", "radius": 10, "height": 40})
    ids["bool"] = d.execute("boolean_op", {"name": "Placa perforada", "operation": "cut",
                                           "target": ids["placa"], "tools": [ids["agujero"]]})
    ids["fillet"] = d.execute("fillet", {"feature": ids["bool"], "radius": 2})
    ids["torre"] = d.execute("create_box", {"name": "Torre", "width": 20, "depth": 20,
                                            "height": 80, "position": {"x": 200, "y": 0, "z": 45}})
    ids["patron"] = d.execute("pattern_linear", {"feature": ids["torre"], "count": 3,
                                                 "spacing": {"x": 0, "y": 40, "z": 0}})
    ids["tapa"] = d.execute("create_box", {"name": "Tapa", "width": 30, "depth": 30, "height": 5,
                                           "position": {"x": -300, "y": 0, "z": 0}})
    ids["mate"] = d.execute("add_mate", {
        "name": "m_tapa", "type": "coincidente", "feature_a": ids["torre"],
        "feature_b": ids["tapa"],
        "ref_a": {"mode": "cara", "face": "tope"}, "ref_b": {"mode": "cara", "face": "base"}})
    ids["fasten"] = d.execute("fasten", {"name": "f_torre", "a": ids["bool"], "b": ids["torre"],
                                         "kind": "perno", "size": "M10", "qty": 4})
    ids["ground"] = d.execute("ground", {"name": "g_placa", "feature": ids["bool"]})
    ids["g_base"] = d.execute("create_group", {"name": "Base", "members": [ids["placa"],
                                               ids["agujero"], ids["bool"]]})
    ids["g_torres"] = d.execute("create_group", {"name": "Torres", "parent": "Base", "members": [
        ids["torre"], ids["patron"], ids["tapa"]]})
    ids["mover"] = d.execute("transform", {"feature": f"{ids['patron']}_1",
                                           "translate": {"x": 5, "y": 0, "z": 0}})
    ids["soporte"] = d.execute("create_box", {"name": "Soporte", "width": 10, "depth": 10,
                                              "height": 10, "position": {"x": 0, "y": -200, "z": 0}})
    ids["borrar"] = d.execute("delete_feature", {"feature": ids["soporte"]})
    ids["copia"] = d.execute("duplicate_feature", {"feature": ids["torre"],
                                                   "offset": {"x": 60, "y": 0, "z": 0}})
    # el super-comando al final: es lo caro (0,3 s) y la prueba en frío regenera cada prefijo
    ids["conv"] = d.execute("create_conveyor", {"largo": "=L", "ancho": 400, "altura": "=H+300",
                                                "paso": 100, "position": {"x": 0, "y": 600, "z": 0}})
    ids["g_conv"] = d.execute("create_group", {"name": "Transporte", "members": [ids["conv"]]})
    return d, ids


@pytest.fixture(scope="module")
def rico():
    return _log_rico()


def _huella(escena: dict) -> dict:
    out = {}
    for fid, feat in escena.items():
        bb = feat.shape.bounding_box(optimal=False)  # el óptimo cuesta 4 ms por pieza
        out[fid] = (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z,
                    float(feat.shape.volume))
    return out


def _en_frio(doc: Document, k: int) -> Document:
    fresco = Document(doc.name)
    fresco.commands = copy.deepcopy(doc.commands[:k])
    fresco.attachments = dict(doc.attachments)
    fresco.hidden = set(doc.hidden)
    fresco.regenerate()
    return fresco


def test_el_log_cubre_lo_que_rompe_un_replay(rico):
    doc, _ = rico
    tipos = {c["type"] for c in doc.commands}
    assert {"set_variable", "boolean_op", "pattern_linear", "create_conveyor", "create_group",
            "add_mate", "fillet", "transform", "delete_feature"} <= tipos
    assert 20 <= len(doc.commands) <= 24


def test_cada_prefijo_es_igual_a_regenerar_en_frio(rico):
    doc, _ = rico
    vistos = []
    for pre in iter_prefijos(doc):
        vistos.append(pre.k)
        assert pre.cmd is not None and pre.cmd["id"] == doc.commands[pre.k - 1]["id"]
        esperado = _huella(_en_frio(doc, pre.k).scene)
        obtenido = _huella(pre.escena)
        assert list(obtenido) == list(esperado), f"ids distintos en k={pre.k}"
        for fid, valores in esperado.items():
            for a, b in zip(obtenido[fid], valores):
                assert math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-6), (pre.k, fid)
    # desde el fin del bloque de variables (2) hasta el último comando, todos
    assert vistos == list(range(2, len(doc.commands) + 1))


def test_el_ultimo_prefijo_es_el_documento(rico):
    doc, _ = rico
    *_, ultimo = iter_prefijos(doc)
    assert ultimo.k == len(doc.commands)
    assert list(ultimo.escena) == list(doc.scene)
    assert set(ultimo.grupos) == set(doc.groups) == {"Base", "Torres", "Transporte"}
    assert ultimo.suprimidos == ()


def test_no_toca_el_documento_fuente(rico):
    doc, _ = rico
    comandos = copy.deepcopy(doc.commands)
    escena = {fid: (f, f.shape) for fid, f in doc.scene.items()}
    ckpts = dict(doc._regen_ckpts)
    sigs = list(doc._regen_sigs)
    hidden, grupos = set(doc.hidden), copy.deepcopy(doc.groups)
    for _ in iter_prefijos(doc):
        pass
    assert doc.commands == comandos
    assert set(doc.scene) == set(escena)
    for fid, (feat, shape) in escena.items():
        assert doc.scene[fid] is feat and feat.shape is shape
    assert doc._regen_ckpts.keys() == ckpts.keys()
    assert all(doc._regen_ckpts[k] is v for k, v in ckpts.items())
    assert doc._regen_sigs == sigs and doc.hidden == hidden and doc.groups == grupos


def test_cuesta_un_regenerate_no_n_cuadrado(rico, monkeypatch):
    doc, _ = rico
    llamadas = []
    real = document_mod.execute_command

    def contar(state, cmd_id, *args, **kwargs):
        llamadas.append(cmd_id)
        return real(state, cmd_id, *args, **kwargs)

    monkeypatch.setattr(document_mod, "execute_command", contar)
    for _ in iter_prefijos(doc):
        pass
    # cada executor corre UNA vez en todo el recorrido, en el orden del log
    assert llamadas == [c["id"] for c in doc.commands]


def test_lo_que_no_cambia_conserva_su_shape(rico):
    doc, ids = rico
    previo = None
    no_visuales = {ids["fasten"], ids["ground"], ids["g_base"], ids["g_torres"], ids["g_conv"]}
    revisados = 0
    for pre in iter_prefijos(doc):
        if previo is not None and pre.cmd["id"] in no_visuales:
            assert set(pre.escena) == set(previo.escena)
            for fid, feat in pre.escena.items():
                assert feat.shape is previo.escena[fid].shape, (pre.k, fid)
            assert pre.escena[ids["tapa"]].shape is previo.escena[ids["tapa"]].shape
            revisados += 1
        if previo is not None and pre.cmd["id"] == ids["fillet"]:
            # el redondeo REEMPLAZA en sitio: mismo id, otro shape
            assert pre.escena[ids["bool"]].shape is not previo.escena[ids["bool"]].shape
        previo = pre
    assert revisados == len(no_visuales)


def test_el_hijo_del_mate_queda_donde_lo_pone_el_mate(rico):
    doc, ids = rico
    escenas = {pre.k: pre.escena for pre in iter_prefijos(doc)}
    k_mate = next(i for i, c in enumerate(doc.commands, 1) if c["id"] == ids["mate"])
    antes, despues = escenas[k_mate - 1][ids["tapa"]], escenas[k_mate][ids["tapa"]]
    assert antes.shape is not despues.shape  # el mate la mueve: es un paso visual
    torre_tope = escenas[k_mate][ids["torre"]].shape.bounding_box().max.Z
    assert math.isclose(despues.shape.bounding_box().min.Z, torre_tope, abs_tol=1e-6)


def test_cortes_explicitos_y_su_validacion(rico):
    doc, _ = rico
    n = len(doc.commands)
    assert [p.k for p in iter_prefijos(doc, cortes=[n, 5, 9, 5])] == [5, 9, n]
    for malo in (0, n + 1, True, 2.0):
        with pytest.raises(ValueError, match="Corte inválido"):
            iter_prefijos(doc, cortes=[malo])


def test_un_comando_suprimido_en_la_fuente_no_rompe_el_recorrido():
    d = Document("con suprimido")
    a = d.execute("create_box", {"name": "A", "width": 10, "depth": 10, "height": 10})
    d.execute("create_box", {"name": "B", "width": 10, "depth": 10, "height": 10,
                             "position": {"x": 30, "y": 0, "z": 0}})
    d.commands.insert(1, {"id": "c99", "type": "fillet", "params": {"feature": "nada"}})
    fuente = Document.from_apolo_bytes(d.to_apolo_bytes(), tolerant=True)
    assert [s["command_id"] for s in fuente.regen_suppressed] == ["c99"]
    prefijos = list(iter_prefijos(fuente))
    assert [p.k for p in prefijos] == [1, 2, 3]
    assert prefijos[0].suprimidos == () and prefijos[1].suprimidos[0]["command_id"] == "c99"
    assert list(prefijos[-1].escena) == list(fuente.scene) == [a, "c2"]


def test_un_prefijo_que_no_regenera_se_salta_y_el_siguiente_lo_arrastra(monkeypatch):
    """Un regenerate tolerante sólo lanza si las variables no resuelven, y `set_variable` ya
    lo impide al ejecutarse: el caso es defensivo, así que se fuerza el fallo del prefijo 2."""
    from apolo.commands.expressions import ExpressionError

    d = Document("prefijo roto")
    for i in range(3):
        d.execute("create_box", {"name": f"Caja {i}", "width": 10, "depth": 10, "height": 10,
                                 "position": {"x": 30 * i, "y": 0, "z": 0}})
    real, llamadas = document_mod.resolve_all, []

    def falla_la_segunda(variables):
        llamadas.append(1)
        if len(llamadas) == 2:
            raise ExpressionError("forzado")
        return real(variables)

    monkeypatch.setattr(document_mod, "resolve_all", falla_la_segunda)
    prefijos = list(iter_prefijos(d))
    assert [p.k for p in prefijos] == [1, 3]
    assert list(prefijos[-1].escena) == ["c1", "c2", "c3"]


def test_insert_project_recorre_sin_romper():
    donante = Document("mini")
    base = donante.execute("create_box", {"name": "Base", "width": 100, "depth": 50, "height": 10})
    donante.execute("create_box", {"name": "Torre", "width": 20, "depth": 20, "height": 60,
                                   "position": {"x": 0, "y": 0, "z": 40}})
    donante.execute("create_group", {"name": "Estructura", "members": [base]})
    anfitrion = Document("layout")
    digest = anfitrion.add_attachment(donante.to_apolo_bytes())
    anfitrion.execute("create_box", {"name": "Piso", "width": 400, "depth": 400, "height": 5,
                                     "position": {"x": 0, "y": 0, "z": -20}})
    cid = anfitrion.execute("insert_project", {"attachment": digest, "name": "M1"})
    prefijos = list(iter_prefijos(anfitrion))
    assert [p.k for p in prefijos] == [1, 2]
    assert list(prefijos[-1].escena) == list(anfitrion.scene)
    assert f"{cid}_{base}" in prefijos[-1].escena
    assert "M1" in prefijos[-1].grupos
