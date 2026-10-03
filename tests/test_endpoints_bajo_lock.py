"""Los endpoints que buscan en el log y luego mutan lo hacen en UNA adquisición de
STATE_LOCK (dentro del closure de `_state_or_error`).

Antes `set_variable`, `delete_variable`, `delete_joint` y `delete_mate` buscaban en
`DOC.commands` FUERA del lock y mutaban en otra adquisición (TOCTOU): una petición
concurrente podía cambiar el log entre la búsqueda y la mutación. `delete_project`
comparaba `PROJECT_ID` sin lock: un open concurrente podía volver activo el proyecto que
se estaba borrando. Los mensajes 404/400 no cambian.
"""

import sys
import threading

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.state import STATE_LOCK


class _DocVigilado(Document):
    """Anota cada lectura de `commands` hecha SIN STATE_LOCK en el hilo que lee
    (`_is_owned` del RLock de CPython). `vigilar` se enciende tras armar el modelo."""

    def __init__(self, *args, **kwargs):
        self.vigilar = False
        self.fuera_del_lock: list[str] = []
        super().__init__(*args, **kwargs)

    @property
    def commands(self):
        if self.vigilar and not STATE_LOCK._is_owned():
            self.fuera_del_lock.append(sys._getframe(1).f_code.co_name)
        return self.__dict__["_commands"]

    @commands.setter
    def commands(self, value):
        self.__dict__["_commands"] = value


@pytest.fixture()
def doc(monkeypatch):
    d = _DocVigilado("bajo-lock")
    monkeypatch.setattr(api, "DOC", d)
    return d


def _dejar_de_vigilar(doc) -> list[str]:
    doc.vigilar = False
    return doc.fuera_del_lock


def test_variables_buscan_en_el_log_bajo_el_lock(doc):
    client = TestClient(api.app)
    doc.vigilar = True
    assert client.post("/api/variables", json={"name": "L", "expression": "100"}).status_code == 200
    r = client.post("/api/variables", json={"name": "L", "expression": "200"})  # edita, no duplica
    assert r.status_code == 200
    r404 = client.delete("/api/variables/nada")
    assert client.delete("/api/variables/L").status_code == 200

    assert _dejar_de_vigilar(doc) == []
    assert r404.status_code == 404 and r404.json()["detail"] == "No existe la variable 'nada'"
    tipos = [c["type"] for c in r.json()["document"]["commands"]]
    assert tipos == ["set_variable"] and r.json()["document"]["variables"][0]["value"] == 200.0
    assert doc.commands == []


def _modelo_con_junta_y_mate(doc) -> None:
    doc.execute("create_box", {"name": "A"})
    doc.execute("create_box", {"name": "B", "position": {"x": 300}})
    doc.execute("add_joint", {"name": "puerta", "parent": "c1", "child": "c2", "origin": {"x": 150}})
    doc.execute("add_mate", {
        "name": "m1", "type": "coincidente", "feature_a": "c1", "feature_b": "c2",
        "ref_a": {"mode": "cara", "face": "tope"}, "ref_b": {"mode": "cara", "face": "base"}})
    # junta y mate «de plantilla»: su comando dueño no es add_joint/add_mate
    doc.joints["de_plantilla"] = {**doc.joints["puerta"], "command_id": "c1"}
    doc.mates["de_plantilla"] = {**doc.mates["m1"], "command_id": "c1"}


def test_juntas_y_mates_buscan_y_borran_bajo_el_lock(doc):
    _modelo_con_junta_y_mate(doc)
    client = TestClient(api.app)
    doc.vigilar = True
    j404 = client.delete("/api/joints/no_existe")
    j400 = client.delete("/api/joints/de_plantilla")
    m404 = client.delete("/api/mates/nope")
    m400 = client.delete("/api/mates/de_plantilla")
    m200 = client.delete("/api/mates/m1")
    j200 = client.delete("/api/joints/puerta")

    assert _dejar_de_vigilar(doc) == []
    assert j404.status_code == 404 and j404.json()["detail"] == "No existe la junta 'no_existe'"
    assert j400.status_code == 400 and j400.json()["detail"] == (
        "Esta junta pertenece a una plantilla (p. ej. un brazo): edita o elimina su comando")
    assert m404.status_code == 404 and m404.json()["detail"] == "No existe el mate 'nope'"
    assert m400.status_code == 400 and m400.json()["detail"] == "Este mate pertenece a una plantilla"
    assert m200.status_code == 200 and j200.status_code == 200
    assert [c["type"] for c in doc.commands] == ["create_box", "create_box"]


def test_borrar_proyecto_compara_el_activo_bajo_el_lock(monkeypatch):
    """Un open que gana el lock mientras el borrado espera vuelve activo al proyecto 2:
    el borrado debe ver ESE estado (400), no el que leyó antes de esperar."""

    class _Store:
        def __init__(self):
            self.borrados: list[int] = []

        def delete(self, project_id):
            self.borrados.append(project_id)

    store = _Store()
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(api, "PROJECT_ID", 1)
    resultado: list = []

    def borrar():
        try:
            resultado.append(api.delete_project(2))
        except HTTPException as exc:
            resultado.append(exc)

    with STATE_LOCK:  # el «open» concurrente: sostiene el lock y activa el proyecto 2
        hilo = threading.Thread(target=borrar)
        hilo.start()
        hilo.join(0.3)
        assert hilo.is_alive()  # el borrado espera el lock: no decidió con el PROJECT_ID viejo
        api.PROJECT_ID = 2
    hilo.join(5)

    assert store.borrados == []
    assert isinstance(resultado[0], HTTPException) and resultado[0].status_code == 400
    assert resultado[0].detail == "No puedes borrar el proyecto abierto"
    assert api.delete_project(3) == {"ok": True} and store.borrados == [3]
