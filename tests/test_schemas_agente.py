"""Schemas del agente sin enums gigantes del catálogo (plan mcp-sin-friccion, D3).

`GET /api/schemas` (vista agente) y `/api/schemas/{type}` publican un campo de refs del catálogo
como `x-catalogo` (cuántas refs y de qué categorías) en vez de la lista; la vista persona (el
desplegable de la UI) y `command_schemas()` la conservan, y la entrada sigue validando con
«¿quisiste decir…?».
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.commands import CommandError, command_schemas, command_schemas_persona
from apolo.commands.vista_agente import MAX_ENUM, command_schemas_agente
from apolo.doc import Document
from apolo.library.catalog import CATALOG


def _componente(entrada: dict) -> dict:
    return entrada["schema"]["properties"]["component"]


def test_el_agente_ve_x_catalogo_y_no_las_refs():
    client = TestClient(api.app)
    uno = client.get("/api/schemas/insert_component").json()
    campo = _componente(uno)
    assert "enum" not in campo and campo["x-catalogo"]["refs"] == len(CATALOG)
    assert "rodamientos" in campo["x-catalogo"]["categorias"]
    assert "get_catalog" in campo["description"]
    todos = {e["type"]: e for e in client.get("/api/schemas").json()}
    assert "enum" not in _componente(todos["insert_component"])
    ref = todos["add_device"]["schema"]["properties"]["ref"]
    assert "enum" not in ref and "proteccion_electrica" in ref["x-catalogo"]["categorias"]
    assert len(json.dumps(uno)) * 3 < len(json.dumps(command_schemas("insert_component")[0])) * 2


def test_los_enums_chicos_y_la_persona_no_cambian():
    agente = {e["type"]: e for e in command_schemas_agente()}
    rodamiento = agente["create_take_up"]["schema"]["properties"]["rodamiento"]
    assert len(rodamiento["enum"]) <= MAX_ENUM  # 41 rodamientos: quedan
    persona = {e["type"]: e for e in command_schemas_persona()}
    assert len(_componente(persona["insert_component"])["enum"]) == len(CATALOG)
    assert len(_componente(command_schemas("insert_component")[0])["enum"]) == len(CATALOG)
    vista = TestClient(api.app).get("/api/schemas", params={"vista": "persona"}).json()
    assert "enum" in _componente(next(e for e in vista if e["type"] == "insert_component"))


def test_la_entrada_valida_y_sugiere():
    ref = next(iter(CATALOG))
    with pytest.raises(CommandError) as exc:
        Document("ref-mala").execute("insert_component", {"component": ref[:-1] + "Z"})
    assert "componente desconocido" in str(exc.value) and "¿quisiste decir" in str(exc.value)
    assert ref in str(exc.value)
