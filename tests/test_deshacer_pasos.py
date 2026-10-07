"""Deshacer y rehacer con etiqueta, y de a varios cambios (plan deshacer-con-etiqueta, F1).

Sobre un `Document` real con cajas: cada puerta de mutación etiqueta su cambio (D1), deshacer
N ≡ N veces deshacer —documento y AMBAS pilas— con un solo regenerate (D6), describir nunca
hace fallar la mutación (D10), la edición coalescente recalcula su etiqueta (D11) y deshacer
no toca la visibilidad (D12). La gramática de la etiqueta está en `tests/test_pasos.py`.
"""

from __future__ import annotations

import copy

import pytest

from apolo.doc import Document, DocumentError
from apolo.doc import pasos


def _caja(nombre: str, x: float = 0, **extra) -> dict:
    return {"name": nombre, "width": 50, "depth": 50, "height": 50, "position": {"x": x}, **extra}


def _modelo() -> tuple[Document, dict[str, str]]:
    """Seis cambios distintos: crear ×3, mover, editar y un lote."""
    doc = Document("deshacer")
    ids = {n: doc.execute("create_box", _caja(n, x)) for n, x in
           (("Guarda", 0), ("Tapa", 200), ("Motor", 400))}
    doc.execute("transform", {"feature": ids["Guarda"], "translate": {"x": 30}})
    doc.edit(ids["Tapa"], {"width": 80}, merge=True)
    doc.execute_many([{"type": "create_box", "params": _caja(n, 600 + 200 * i)}
                      for i, n in enumerate(("Pata A", "Pata B"))])
    return doc, ids


def _pila(pila: list[dict]) -> list:
    return [(copy.deepcopy(e["commands"]), e["seq"], e["etiqueta"], set(e["hidden"]))
            for e in pila]


def _estado(doc: Document) -> dict:
    return {
        "commands": copy.deepcopy(doc.commands),
        "escena": sorted(doc.scene),
        "visibles": sorted(fid for fid, f in doc.scene.items() if f.visible),
        "hidden": set(doc.hidden),
        "seq": doc._seq,
        "undo_labels": doc.undo_labels,
        "redo_labels": doc.redo_labels,
        "undo": _pila(doc._undo),
        "redo": _pila(doc._redo),
    }


# ------------------------------------------------------------------ cada puerta etiqueta
def test_cada_puerta_de_mutacion_etiqueta_su_cambio():
    doc, ids = _modelo()
    assert doc.undo_labels == [
        "Caja ×2: «Pata A» y «Pata B»",
        "Editar Caja «Tapa»: Ancho (X)",
        "Mover «Guarda»",
        "Caja «Motor»",
        "Caja «Tapa»",
        "Caja «Guarda»",
    ]
    assert doc.redo_labels == []
    doc.edit_many([{"command_id": ids["Tapa"], "params": {"height": 70}},
                   {"command_id": ids["Motor"], "params": {"height": 70}}], merge=True)
    assert doc.undo_labels[0] == "Editar Caja ×2: «Tapa» y «Motor»"
    doc.remove_commands([ids["Motor"]])
    assert doc.undo_labels[0] == "Eliminar Caja «Motor»"
    doc.edit(ids["Tapa"], {"height": 70}, merge=True)  # no cambia nada
    assert doc.undo_labels[0] == "Editar Caja «Tapa» (sin cambios)"
    var = doc.execute("set_variable", {"name": "L", "expression": "2000"})
    doc.edit(var, {"name": "L", "expression": "3200"})
    assert doc.undo_labels[:2] == ["Variable «L»: 2000 → 3200", "Variable «L» = 2000"]


def test_aplicar_variante_dice_la_variante():
    doc = Document()
    doc.execute("set_variable", {"name": "largo_total", "expression": "4000"})
    doc.execute("create_box", {"name": "Cama", "width": "=largo_total"})
    doc.save_configuration("4m", ["largo_total"])
    doc.set_configuration("3.2m (prueba paramétrica)", {"largo_total": "3200"})
    doc.apply_configuration("3.2m (prueba paramétrica)")
    assert doc.undo_labels[0] == "Aplicar variante «3.2m (prueba paramétrica)»"


# ------------------------------------------------------------------ D6: N pasos de una vez
def test_deshacer_n_es_n_veces_deshacer():
    uno, _ = _modelo()
    varios, _ = _modelo()
    for _ in range(3):
        uno.undo()
    varios.undo(3)
    assert _estado(varios) == _estado(uno)
    assert varios.redo_labels == ["Mover «Guarda»", "Editar Caja «Tapa»: Ancho (X)",
                                  "Caja ×2: «Pata A» y «Pata B»"]
    assert varios.undo_labels == ["Caja «Motor»", "Caja «Tapa»", "Caja «Guarda»"]


def test_rehacer_n_es_n_veces_rehacer():
    uno, _ = _modelo()
    varios, _ = _modelo()
    uno.undo(5)
    varios.undo(5)
    for _ in range(2):
        uno.redo()
    varios.redo(2)
    assert _estado(varios) == _estado(uno)
    assert varios.undo_labels[0] == "Caja «Motor»" and varios.redo_labels[0] == "Mover «Guarda»"


def test_deshacer_todo_y_rehacer_todo_vuelve_al_mismo_documento():
    doc, _ = _modelo()
    antes = _estado(doc)
    doc.undo(6)
    assert doc.scene == {} and doc.undo_labels == [] and len(doc.redo_labels) == 6
    doc.redo(6)
    despues = _estado(doc)
    assert {k: despues[k] for k in ("commands", "escena", "seq", "undo_labels")} == {
        k: antes[k] for k in ("commands", "escena", "seq", "undo_labels")}


def test_las_etiquetas_van_y_vuelven():
    doc, _ = _modelo()
    arriba = doc.undo_labels[0]
    doc.undo()
    assert doc.redo_labels == [arriba] and arriba not in doc.undo_labels
    doc.redo()
    assert doc.undo_labels[0] == arriba and doc.redo_labels == []
    doc.undo()
    assert doc.redo_labels == [arriba]


@pytest.mark.parametrize("pasos_malos", [0, -2, 7, 1.5, True])
def test_pasos_invalidos_no_tocan_nada(pasos_malos):
    doc, _ = _modelo()
    antes = _estado(doc)
    with pytest.raises(DocumentError):
        doc.undo(pasos_malos)
    assert _estado(doc) == antes
    with pytest.raises(DocumentError, match="Nada que rehacer"):
        doc.redo()


def test_fuera_de_rango_dice_cuantos_hay():
    doc, _ = _modelo()
    with pytest.raises(DocumentError, match="Sólo hay 6 cambios para deshacer"):
        doc.undo(7)
    doc.undo(5)
    with pytest.raises(DocumentError, match="Sólo hay 1 cambio para deshacer"):
        doc.undo(2)
    with pytest.raises(DocumentError, match="Sólo hay 5 cambios para rehacer"):
        doc.redo(6)
    doc.undo()
    with pytest.raises(DocumentError, match="Nada que deshacer"):
        doc.undo()


def test_peek_then_commit_con_varios_pasos(monkeypatch):
    """Si restaurar el destino revienta, el documento y las DOS pilas quedan intactos."""
    doc, _ = _modelo()
    doc.undo()  # que también haya algo para rehacer
    antes = _estado(doc)
    original = Document._restore
    llamadas = []

    def falla_el_destino(self, snap):
        llamadas.append(len(snap["commands"]))
        if len(llamadas) == 1:
            raise DocumentError("restauración inyectada a fallar")
        return original(self, snap)

    monkeypatch.setattr(Document, "_restore", falla_el_destino)
    with pytest.raises(DocumentError, match="inyectada"):
        doc.undo(3)
    assert len(llamadas) == 2  # el destino falló; se volvió al estado actual
    assert _estado(doc) == antes
    monkeypatch.setattr(Document, "_restore", original)
    doc.undo(3)
    assert len(doc._undo) == 2 and len(doc._redo) == 4


def test_el_tope_de_cincuenta_vale_para_las_dos_pilas():
    doc = Document()
    for i in range(Document._UNDO_CAP + 10):
        doc.execute("create_box", {"name": f"P{i}", "width": 10 + i})
    assert len(doc.undo_labels) == Document._UNDO_CAP
    assert doc.undo_labels[0] == f"Caja «P{Document._UNDO_CAP + 9}»"
    doc.undo(Document._UNDO_CAP)
    assert len(doc._undo) == 0 and len(doc._redo) == Document._UNDO_CAP
    assert len(doc.scene) == 10
    doc.redo(Document._UNDO_CAP)
    assert len(doc.scene) == Document._UNDO_CAP + 10


# ------------------------------------------------------------------ D10, D11, D12
def test_d10_describir_nunca_hace_fallar_la_mutacion(monkeypatch):
    def revienta(*_a, **_k):
        raise RuntimeError("descriptor roto")

    monkeypatch.setattr(pasos, "describir", revienta)
    doc = Document()
    fid = doc.execute("create_box", _caja("A"))
    assert fid in doc.scene
    assert doc.undo_labels == ["Cambio en el modelo"]
    doc.undo()
    assert doc.redo_labels == ["Cambio en el modelo"] and doc.scene == {}


def test_d11_la_edicion_coalescente_nombra_todo_lo_que_cambio():
    doc = Document()
    fid = doc.execute("create_box", _caja("Soporte"))
    doc.edit(fid, {"width": 60}, coalesce=True, merge=True)
    assert doc.undo_labels[0] == "Editar Caja «Soporte»: Ancho (X)"
    doc.edit(fid, {"width": 70}, coalesce=True, merge=True)
    doc.edit(fid, {"height": 90}, coalesce=True, merge=True)
    assert doc.undo_labels == ["Editar Caja «Soporte»: Ancho (X) y Alto (Z)", "Caja «Soporte»"]
    doc.undo()
    assert doc.commands[0]["params"]["width"] == 50  # un solo paso revierte el arrastre


def test_d12_deshacer_y_rehacer_no_tocan_la_visibilidad():
    doc = Document()
    a = doc.execute("create_box", _caja("A"))
    b = doc.execute("create_box", _caja("B", 200))
    doc.set_visibility(a, False)
    doc.undo()  # deshace B, no el ocultar A
    assert b not in doc.scene and a in doc.hidden and doc.scene[a].visible is False
    doc.redo()
    assert b in doc.scene and doc.scene[a].visible is False and doc.scene[b].visible is True
    doc.undo(2)
    doc.redo(2)
    assert doc.scene[a].visible is False


def test_d12_un_id_reciclado_tras_deshacer_no_nace_oculto():
    doc = Document()
    doc.execute("create_box", _caja("A"))
    b = doc.execute("create_box", _caja("B", 200))
    doc.set_visibility(b, False)
    doc.undo()  # deshacer devuelve `seq`: el próximo comando vuelve a llamarse como B
    nueva = doc.execute("create_box", _caja("C", 400))
    assert nueva == b and doc.scene[nueva].visible is True
