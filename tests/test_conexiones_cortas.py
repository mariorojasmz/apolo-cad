"""Uniones y sujeción en corto (plan mcp-sin-friccion, D1 y D2).

`GET /api/connectivity` filtra por piezas (`ids`: feature ids, grupos o comandos) y por tipo
(`kind`) y resume por raíz de patrón (`resumen=si`, o `auto` con más de 40 uniones); sin
parámetros responde lo de siempre (la UI). `POST /api/assembly/soundness` con `resumen` da los
conteos y lo que flota, sin los ids sujetos. Las tools `get_connections` y `check_assembly` del
MCP piden el modo corto por defecto.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc import Document
from apolo.services import conexiones


def _ok(r) -> dict:
    assert r.status_code == 200, r.text
    return r.json()


def _modelo(copias: int = 5) -> Document:
    """Una base anclada, una viga soldada y `copias` ejes de un patrón (c3, c3_1…) apernados a la
    viga; un eje suelto flota (sin unión) y una tapa se apoya en la base."""
    doc = Document("conexiones-cortas")
    doc.execute("create_box", {"name": "Base", "width": 400, "depth": 400, "height": 20})  # c1
    doc.execute("create_box", {"name": "Viga", "width": 400, "depth": 40, "height": 40,
                               "position": {"z": 30}})  # c2
    doc.execute("create_box", {"name": "Eje", "width": 10, "depth": 10, "height": 60,
                               "position": {"x": -150, "z": 80}})  # c3
    doc.execute("pattern_linear", {"feature": "c3", "count": copias,
                                   "spacing": {"x": 60}})  # c4 → c4_1…
    doc.execute("create_box", {"name": "Suelto", "width": 10, "depth": 10, "height": 10,
                               "position": {"z": 900}})  # c5
    doc.execute("create_box", {"name": "Tapa", "width": 50, "depth": 50, "height": 5,
                               "position": {"x": 300, "z": 15}})  # c6
    doc.execute("create_group", {"name": "Ejes", "members": ["c3", "c4"]})  # c7
    doc.execute("ground", {"name": "piso_base", "feature": "c1"})
    doc.execute("fasten", {"name": "viga_base", "a": "c2", "b": "c1", "kind": "soldadura"})
    ejes = ["c3"] + [f"c4_{i}" for i in range(1, copias)]
    for k, eje in enumerate(ejes):
        doc.execute("fasten", {"name": f"eje{k}_viga", "a": eje, "b": "c2", "kind": "perno",
                               "size": "M12", "qty": 1})
    doc.execute("fasten", {"name": "tapa_base", "a": "c6", "b": "c1", "kind": "contacto"})
    return doc


def _cliente(doc: Document) -> TestClient:
    api.DOC = doc
    return TestClient(api.app)


# ------------------------------------------------------------------ GET /api/connectivity
def test_sin_parametros_es_la_lista_de_siempre():
    doc = _modelo()
    out = _ok(_cliente(doc).get("/api/connectivity"))
    assert out == {"fasteners": list(doc.fasteners.values()),
                   "grounds": list(doc.grounds.values())}


def test_filtro_por_pieza_grupo_y_comando():
    client = _cliente(_modelo())
    por_pieza = _ok(client.get("/api/connectivity", params={"ids": "c6"}))
    assert [f["name"] for f in por_pieza["fasteners"]] == ["tapa_base"]
    assert por_pieza["grounds"] == []
    # un grupo se expande a sus piezas; un comando, a las suyas (las copias del patrón)
    por_grupo = _ok(client.get("/api/connectivity", params={"ids": "Ejes"}))
    assert {f["name"] for f in por_grupo["fasteners"]} == {f"eje{k}_viga" for k in range(5)}
    por_comando = _ok(client.get("/api/connectivity", params={"ids": "c4"}))
    assert {f["name"] for f in por_comando["fasteners"]} == {f"eje{k}_viga" for k in range(1, 5)}
    base = _ok(client.get("/api/connectivity", params={"ids": "c1"}))
    assert [g["name"] for g in base["grounds"]] == ["piso_base"]


def test_filtro_por_tipo_y_anclaje():
    client = _cliente(_modelo())
    pernos = _ok(client.get("/api/connectivity", params={"kind": "perno"}))
    assert len(pernos["fasteners"]) == 5 and pernos["grounds"] == []
    assert all(f["kind"] == "perno" for f in pernos["fasteners"])
    anclajes = _ok(client.get("/api/connectivity", params={"kind": "anclaje"}))
    assert anclajes["fasteners"] == [] and len(anclajes["grounds"]) == 1
    combinado = _ok(client.get("/api/connectivity", params={"ids": "c1", "kind": "soldadura"}))
    assert [f["name"] for f in combinado["fasteners"]] == ["viga_base"]


def test_errores_accionables():
    client = _cliente(_modelo())
    r = client.get("/api/connectivity", params={"kind": "remache"})
    assert r.status_code == 400 and "perno, soldadura, pegado, contacto, anclaje" in r.json()["detail"]
    r = client.get("/api/connectivity", params={"ids": "c4_9x"})
    assert r.status_code == 404 and "c4_9x" in r.json()["detail"]
    assert "¿Quisiste decir" in r.json()["detail"]
    assert client.get("/api/connectivity", params={"resumen": "quizas"}).status_code == 422


def test_resumen_agrupa_por_par_de_piezas():
    client = _cliente(_modelo())
    out = _ok(client.get("/api/connectivity", params={"resumen": "si"}))
    assert out["n_fijadores"] == 7 and out["n_anclajes"] == 1
    assert out["por_tipo"] == {"perno": 5, "soldadura": 1, "contacto": 1}
    filas = {(f["kind"], f["a"], f["b"]): f["n"] for f in out["resumen"]}
    # eje0_viga … eje4_viga (la fuente c3 y sus copias c4_k) = UNA fila, la más larga primero;
    # por el par de piezas, no por el nombre de la unión (D9 de mcp-sin-friccion)
    assert filas == {("perno", "Eje", "Viga"): 5, ("soldadura", "Base", "Viga"): 1,
                     ("contacto", "Base", "Tapa"): 1}
    fila = out["resumen"][0]
    assert fila["ejemplo"] == {"nombre": "eje0_viga", "a": "c3", "b": "c2",
                               "piezas": ["Eje", "Viga"]}
    assert out["anclajes"] == [{"nombre": "piso_base", "pieza": "c1"}]
    assert "fasteners" not in out and "get_connections" in out["seguir"]


def test_auto_resume_solo_con_muchas_uniones(monkeypatch):
    client = _cliente(_modelo())
    assert "fasteners" in _ok(client.get("/api/connectivity", params={"resumen": "auto"}))
    monkeypatch.setattr(conexiones, "MAX_UNIONES", 3)
    assert "resumen" in _ok(client.get("/api/connectivity", params={"resumen": "auto"}))
    # un filtro chico vuelve a la lista aunque el documento tenga muchas
    filtrado = _ok(client.get("/api/connectivity", params={"resumen": "auto", "ids": "c6"}))
    assert [f["name"] for f in filtrado["fasteners"]] == ["tapa_base"]


# ------------------------------------------------------------------ soundness en corto
def test_sujecion_corta_sin_los_ids_sujetos():
    client = _cliente(_modelo())
    completo = _ok(client.post("/api/assembly/soundness", json={}))
    corto = _ok(client.post("/api/assembly/soundness", json={"resumen": True}))
    for k in ("has_ground", "n_total", "n_grounded", "n_floating"):
        assert corto[k] == completo[k]
    assert corto["n_floating"] == 1 and corto["n_isolated"] == 1
    assert corto["floating_detail"] == [{"id": "c5", "nombre": "Suelto"}]
    assert corto["isolated"] == ["c5"] and corto["n_componentes"] == len(completo["components"])
    for k in ("grounded", "floating", "components"):
        assert k not in corto


def test_sujecion_corta_recorta_lo_que_flota():
    doc = Document("todo-flota")
    doc.execute("create_box", {"name": "Bloque"})
    doc.execute("pattern_linear", {"feature": "c1", "count": 60, "spacing": {"x": 200}})
    corto = _ok(_cliente(doc).post("/api/assembly/soundness", json={"resumen": True}))
    assert corto["has_ground"] is False and corto["n_floating"] == 60
    assert len(corto["floating_detail"]) == 40 and corto["floating_detail_omitidas"] == 20
    assert len(corto["isolated"]) == 40 and corto["isolated_omitidas"] == 20


# ------------------------------------------------------------------ las tools del MCP
@pytest.fixture
def mcp(monkeypatch):
    pytest.importorskip("mcp")
    from apolo import mcp_server

    llamadas: list[tuple] = []
    client = _cliente(_modelo())

    def por_la_api(method, path, **kwargs):
        llamadas.append((method, path, kwargs))
        r = client.request(method, path, **kwargs)
        if r.status_code >= 400:
            raise mcp_server._reject(r.status_code, r.json().get("detail"))
        return r

    monkeypatch.setattr(mcp_server, "_api", por_la_api)
    return mcp_server, llamadas


def test_get_connections_pide_auto_y_pasa_los_filtros(mcp):
    mcp_server, llamadas = mcp
    out = json.loads(mcp_server.get_connections())
    assert len(out["fasteners"]) == 7  # 8 uniones ≤ 40: la lista
    assert llamadas[-1] == ("GET", "/api/connectivity", {"params": {"resumen": "auto"}})
    out = json.loads(mcp_server.get_connections(ids=["Ejes", "c6"], kind="perno", resumen=True))
    assert out["n_fijadores"] == 5 and "resumen" in out
    assert llamadas[-1][2]["params"] == {"resumen": "si", "ids": "Ejes,c6", "kind": "perno"}
    json.loads(mcp_server.get_connections(resumen=False))
    assert llamadas[-1][2]["params"] == {"resumen": "no"}


def test_check_assembly_corto_por_defecto(mcp):
    mcp_server, llamadas = mcp
    corto = json.loads(mcp_server.check_assembly())
    assert "grounded" not in corto and corto["floating_detail"][0]["id"] == "c5"
    assert llamadas[-1][2]["json"] == {"with_autodetect": False, "resumen": True}
    completo = json.loads(mcp_server.check_assembly(detail="full"))
    assert "grounded" in completo and llamadas[-1][2]["json"]["resumen"] is False
