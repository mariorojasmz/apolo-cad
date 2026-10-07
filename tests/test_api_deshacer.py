"""Deshacer y rehacer por la API y el MCP (plan deshacer-con-etiqueta, F2: D5, D6 y D9).

`document` publica `undo_labels`/`redo_labels` (el cambio más próximo primero) tras cada puerta
de mutación; `POST /api/undo|redo?pasos=N` mueve N cambios de una vez y deja lo mismo que N
llamadas sueltas; fuera de rango → 400 con el texto del documento y nada cambia; sin `pasos`,
lo de siempre. Las tools `undo`/`redo` del MCP suman `deshecho`/`rehecho` con la etiqueta del
cambio revertido y la omiten si el payload no trae las listas. La gramática de la etiqueta está
en `tests/test_pasos.py`; el documento, en `tests/test_deshacer_pasos.py`.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.brief import _scene_brief, brief_paso
from apolo.doc import Document

#: Las claves de `document` antes de este plan: las listas son aditivas (D5).
CLAVES_DE_ANTES = {"name", "commands", "can_undo", "can_redo", "variables", "configurations",
                   "configuration_values", "groups", "project_id", "suppressed_commands",
                   "autosave_failed"}

#: Las etiquetas de `_modelo()`, la más próxima primero.
ETIQUETAS = ["Eliminar Caja «Motor»", "Caja ×2: «Tapa» y «Motor»",
             "Editar Caja «Guarda»: Ancho (X)", "Mover «Guarda»", "Caja «Guarda»"]


def _caja(nombre: str, x: float = 0) -> dict:
    return {"name": nombre, "width": 50, "depth": 50, "height": 50, "position": {"x": x}}


def _ok(r) -> dict:
    assert r.status_code == 200, r.text
    return r.json()


def _modelo() -> TestClient:
    """Cinco cambios por cinco puertas distintas: crear, mover, editar, lote y eliminar."""
    api.DOC = Document("deshacer-api")
    client = TestClient(api.app)
    crear = _ok(client.post("/api/commands", json={"type": "create_box", "params": _caja("Guarda")}))
    guarda = crear["affected_command_ids"][0]
    fid = next(f["id"] for f in crear["features"] if f["command_id"] == guarda)
    _ok(client.post("/api/commands", json={"type": "transform",
                                           "params": {"feature": fid, "translate": {"x": 30}}}))
    _ok(client.put(f"/api/commands/{guarda}", params={"merge": True},
                   json={"params": {"width": 80}}))
    lote = _ok(client.post("/api/commands/batch", json={"actions": [
        {"type": "create_box", "params": _caja("Tapa", 200)},
        {"type": "create_box", "params": _caja("Motor", 400)}]}))
    motor = lote["affected_command_ids"][-1]
    _ok(client.post("/api/commands/remove", json={"ids": [motor]}))
    return client


def _vista(client: TestClient) -> dict:
    """Lo que un cliente ve del documento: log, pilas y piezas (sin revs ni mallas)."""
    doc = _ok(client.get("/api/document"))
    escena = _ok(client.get("/api/scene"))
    return {
        **{k: doc[k] for k in ("commands", "can_undo", "can_redo", "undo_labels", "redo_labels")},
        "piezas": sorted((f["id"], f["name"], json.dumps(f["bbox"])) for f in escena["features"]),
    }


# ------------------------------------------------------------------ D5: las listas viajan
def test_cada_puerta_publica_su_etiqueta_en_el_documento():
    client = _modelo()
    doc = _ok(client.get("/api/document"))
    assert doc["undo_labels"] == ETIQUETAS and doc["redo_labels"] == []
    assert doc["can_undo"] is True and doc["can_redo"] is False  # los booleanos no cambian
    escena = _ok(client.get("/api/scene"))["document"]  # el payload de escena las lleva igual
    assert escena["undo_labels"] == ETIQUETAS and escena["redo_labels"] == []


def test_la_respuesta_de_cada_mutacion_trae_las_listas():
    api.DOC = Document("deshacer-api")
    client = TestClient(api.app)
    r = _ok(client.post("/api/commands", json={"type": "create_box", "params": _caja("Base")}))
    assert r["document"]["undo_labels"] == ["Caja «Base»"]
    assert r["document"]["redo_labels"] == []
    r = _ok(client.post("/api/undo"))
    assert r["document"]["undo_labels"] == [] and r["document"]["redo_labels"] == ["Caja «Base»"]


def test_variables_y_variante_por_la_api():
    api.DOC = Document("variante-api")
    client = TestClient(api.app)
    _ok(client.post("/api/variables", json={"name": "L", "expression": "2000"}))
    _ok(client.post("/api/commands", json={"type": "create_box",
                                           "params": {"name": "Cama", "width": "=L"}}))
    _ok(client.post("/api/configurations", json={"name": "2m", "variables": ["L"]}))
    _ok(client.put("/api/configurations/3.2m", json={"values": {"L": "3200"}}))
    r = _ok(client.post("/api/configurations/3.2m/apply"))
    assert r["document"]["undo_labels"][:3] == [
        "Aplicar variante «3.2m»", "Caja «Cama»", "Variable «L» = 2000"]
    r = _ok(client.post("/api/variables", json={"name": "L", "expression": "2500"}))
    assert r["document"]["undo_labels"][0] == "Variable «L»: 3200 → 2500"


# ------------------------------------------------------------------ D6: N cambios de una vez
def test_deshacer_tres_es_tres_veces_deshacer():
    client = _modelo()
    for _ in range(3):
        ultima = _ok(client.post("/api/undo"))
    de_a_uno = _vista(client)

    client = _modelo()
    r = _ok(client.post("/api/undo", params={"pasos": 3}))
    assert _vista(client) == de_a_uno
    assert r["document"] == ultima["document"] and r["affected_command_ids"] == []
    assert r["document"]["undo_labels"] == ETIQUETAS[3:]
    assert r["document"]["redo_labels"] == ETIQUETAS[2::-1]


def test_rehacer_dos_es_dos_veces_rehacer():
    client = _modelo()
    _ok(client.post("/api/undo", params={"pasos": 4}))
    for _ in range(2):
        _ok(client.post("/api/redo"))
    de_a_uno = _vista(client)

    client = _modelo()
    _ok(client.post("/api/undo", params={"pasos": 4}))
    r = _ok(client.post("/api/redo", params={"pasos": 2}))
    assert _vista(client) == de_a_uno
    assert r["document"]["undo_labels"] == ETIQUETAS[2:]
    assert r["document"]["redo_labels"] == ETIQUETAS[1::-1]


def test_sin_pasos_es_lo_de_siempre():
    """Sin `pasos` se deshace UN cambio y la respuesta es la de siempre + las dos listas."""
    client = _modelo()
    r = _ok(client.post("/api/undo"))
    assert set(r) == {"features", "definitions", "document", "total_features", "epoch",
                      "affected_command_ids"}
    assert set(r["document"]) == CLAVES_DE_ANTES | {"undo_labels", "redo_labels"}
    assert r["affected_command_ids"] == [] and r["document"]["redo_labels"] == ETIQUETAS[:1]
    sin_pasos = _vista(client)

    client = _modelo()
    _ok(client.post("/api/undo", params={"pasos": 1}))
    assert _vista(client) == sin_pasos


# ------------------------------------------------------------------ fuera de rango: 400, nada cambia
@pytest.mark.parametrize("verbo, pasos, texto", [
    ("undo", 0, "La cantidad de cambios a deshacer debe ser un entero mayor o igual a 1"),
    ("undo", -2, "La cantidad de cambios a deshacer debe ser un entero mayor o igual a 1"),
    ("undo", 99, "Sólo hay 5 cambios para deshacer"),
    ("redo", 0, "La cantidad de cambios a rehacer debe ser un entero mayor o igual a 1"),
    ("redo", None, "Nada que rehacer"),
    ("redo", 2, "Nada que rehacer"),
])
def test_fuera_de_rango_da_400_con_el_texto_del_documento(verbo, pasos, texto):
    client = _modelo()
    antes = _vista(client)
    r = client.post(f"/api/{verbo}", params={} if pasos is None else {"pasos": pasos})
    assert r.status_code == 400 and r.json()["detail"] == texto
    assert _vista(client) == antes


def test_pila_vacia_y_pasos_que_no_son_un_entero():
    api.DOC = Document("vacio")
    client = TestClient(api.app)
    for params in ({}, {"pasos": 3}):
        r = client.post("/api/undo", params=params)
        assert r.status_code == 400 and r.json()["detail"] == "Nada que deshacer"
    client = _modelo()
    antes = _vista(client)
    assert client.post("/api/undo", params={"pasos": "dos"}).status_code == 422  # FastAPI
    assert _vista(client) == antes


# ------------------------------------------------------------------ D9: el MCP dice qué revirtió
def test_brief_paso_lleva_la_etiqueta_del_cambio_revertido():
    client = _modelo()
    deshecho = _ok(client.post("/api/undo"))
    out = brief_paso(deshecho, "deshecho")
    assert list(out)[0] == "deshecho" and out["deshecho"] == "Eliminar Caja «Motor»"
    assert {k: v for k, v in out.items() if k != "deshecho"} == _scene_brief(deshecho)
    rehecho = _ok(client.post("/api/redo"))
    assert brief_paso(rehecho, "rehecho")["rehecho"] == "Eliminar Caja «Motor»"


@pytest.mark.parametrize("documento", [
    {"name": "viejo", "can_undo": True, "can_redo": True},  # una API sin las listas
    {"name": "vacio", "can_undo": False, "can_redo": False, "undo_labels": [], "redo_labels": []},
    None,
])
def test_brief_paso_omite_la_clave_sin_etiqueta(documento):
    """Opcionales omitidos, nunca `null`: sin lista (o vacía) no hay `deshecho` ni `rehecho`."""
    payload = {"features": [], "total_features": 0, "affected_command_ids": []}
    if documento is not None:
        payload["document"] = documento
    for clave in ("deshecho", "rehecho"):
        out = brief_paso(payload, clave)
        assert clave not in out and out == _scene_brief(payload)


def test_las_tools_undo_y_redo_dicen_que_revirtieron(monkeypatch):
    """Por las tools reales, contra la API en proceso: `deshecho`/`rehecho` sin params nuevos."""
    pytest.importorskip("mcp")
    from apolo import mcp_server

    client = _modelo()
    llamadas: list[tuple] = []

    def por_la_api(method, path, **kwargs):
        llamadas.append((method, path, kwargs))
        return client.request(method, path, **kwargs)

    monkeypatch.setattr(mcp_server, "_api", por_la_api)
    deshecho = json.loads(mcp_server.undo())
    assert deshecho["deshecho"] == "Eliminar Caja «Motor»" and "rehecho" not in deshecho
    assert deshecho["puede_rehacer"] is True
    rehecho = json.loads(mcp_server.redo())
    assert rehecho["rehecho"] == "Eliminar Caja «Motor»" and "deshecho" not in rehecho
    assert llamadas == [("POST", "/api/undo", {}), ("POST", "/api/redo", {})]
