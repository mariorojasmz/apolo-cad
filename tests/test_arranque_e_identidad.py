"""Cada proceso de una flota abre SU máquina y dice quién es (plan
`docs/plans/varias-maquinas-a-la-vez.md`, D3 y D7).

- `APOLO_PROJECT=<id>` elige qué abre el arranque; si no existe, `startup_error` y doc vacío
  con `project_id=None`, sin crear nada (como el reciente corrupto).
- `GET /api/health` trae `pid`, `puerto` y `proyecto`; cada línea de `errors.log`, pid y puerto.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo import identidad
from apolo.api import errorlog
from apolo.api.session import S, initialize_store
from apolo.doc import Document
from apolo.projects import ProjectStore


@pytest.fixture
def base(tmp_path):
    """Dos proyectos: «pedido» (el viejo) y «reciente» (el que abriría el arranque)."""
    st = ProjectStore(tmp_path / "flota.db")
    viejo = Document("pedido")
    viejo.execute("create_box", {"width": 10})
    pedido = st.create(viejo)
    reciente = st.create(Document("reciente"))
    with st._conn() as con:  # el orden de «reciente» es por updated_at: sin empates
        con.execute("UPDATE projects SET updated_at='2000-01-01T00:00:00' WHERE id=?", (pedido,))
    return st.path, pedido, reciente


def test_sin_apolo_project_abre_el_reciente(base, monkeypatch):
    ruta, _pedido, reciente = base
    monkeypatch.delenv("APOLO_PROJECT", raising=False)
    initialize_store(ruta)
    assert (S.project_id, S.doc.name, S.startup_error) == (reciente, "reciente", None)


def test_apolo_project_abre_el_pedido_y_no_el_reciente(base, monkeypatch):
    ruta, pedido, _reciente = base
    monkeypatch.setenv("APOLO_PROJECT", str(pedido))
    initialize_store(ruta)
    assert (S.project_id, S.doc.name, S.startup_error) == (pedido, "pedido", None)
    assert len(S.doc.scene) == 1


def test_apolo_project_inexistente_deja_startup_error_sin_crear_nada(base, monkeypatch):
    ruta, _pedido, reciente = base
    antes = ProjectStore(ruta).list_projects()
    monkeypatch.setenv("APOLO_PROJECT", "999")
    initialize_store(ruta)
    assert S.project_id is None
    assert "999" in S.startup_error and "APOLO_PROJECT" in S.startup_error
    assert len(S.doc.scene) == 0 and len(S.doc.commands) == 0
    assert ProjectStore(ruta).list_projects() == antes  # ni «Sin título» ni nada
    assert ProjectStore(ruta).most_recent_id() == reciente
    assert "No existe el proyecto 999" in errorlog.read_log()
    health = TestClient(api.app).get("/api/health").json()
    assert health["ok"] is False and health["startup_error"] == S.startup_error


def test_apolo_project_en_una_base_vacia_no_crea_el_sin_titulo(tmp_path, monkeypatch):
    ruta = str(tmp_path / "vacia.db")
    monkeypatch.setenv("APOLO_PROJECT", "1")
    initialize_store(ruta)
    assert S.project_id is None and S.startup_error
    assert ProjectStore(ruta).list_projects() == []


def test_apolo_project_que_no_es_un_numero(base, monkeypatch):
    ruta, _pedido, _reciente = base
    monkeypatch.setenv("APOLO_PROJECT", "faja")
    initialize_store(ruta)
    assert S.project_id is None and "'faja'" in S.startup_error


def test_health_trae_pid_puerto_y_proyecto(monkeypatch):
    monkeypatch.setenv("APOLO_PORT", "8123")
    monkeypatch.setattr(api, "DOC", Document("faja de prueba"))
    monkeypatch.setattr(api, "PROJECT_ID", 74)
    h = TestClient(api.app).get("/api/health").json()
    assert h["pid"] == os.getpid()
    assert h["puerto"] == 8123
    assert h["proyecto"] == {"id": 74, "nombre": "faja de prueba"}
    assert h["project_id"] == 74  # el campo de siempre sigue


def test_health_sin_puerto_conocido_usa_el_de_la_peticion(monkeypatch):
    monkeypatch.delenv("APOLO_PORT", raising=False)
    monkeypatch.setattr(identidad, "_puerto_de_argv", lambda argv: None)
    h = TestClient(api.app, base_url="http://127.0.0.1:8456").get("/api/health").json()
    assert h["puerto"] == 8456


@pytest.mark.parametrize("argv, esperado", [
    (["C:/venv/Lib/site-packages/uvicorn/__main__.py", "apolo.api.main:app", "--port", "8101"],
     8101),
    (["/x/uvicorn/__main__.py", "apolo.api.main:app", "--port=8102"], 8102),
    (["/x/uvicorn/__main__.py", "apolo.api.main:app"], 8000),  # el default de uvicorn
    (["/x/bin/uvicorn", "apolo.api.main:app", "--reload"], 8000),
    (["/x/pytest/__main__.py", "tests", "-q"], None),
    (["apolo", "--port", "no"], None),
])
def test_el_puerto_sale_de_la_linea_de_comandos(argv, esperado, monkeypatch):
    monkeypatch.delenv("APOLO_PORT", raising=False)
    assert identidad.puerto(argv) == esperado


def test_apolo_port_gana_a_la_linea_de_comandos(monkeypatch):
    monkeypatch.setenv("APOLO_PORT", "8200")
    assert identidad.puerto(["/x/uvicorn/__main__.py", "app", "--port", "8101"]) == 8200


def test_cada_linea_de_errors_log_dice_pid_y_puerto(monkeypatch, tmp_path):
    monkeypatch.setenv("APOLO_PORT", "8124")
    monkeypatch.setattr(errorlog, "LOG_FILE", tmp_path / "logs" / "errors.log")
    errorlog.log_error("test.identidad", "dos\nlíneas", detalle="x")
    errorlog.session_marker("marca")
    lineas = errorlog.read_log().splitlines()
    assert len(lineas) == 2
    for linea in lineas:
        assert f"| pid={os.getpid()} puerto=8124 |" in linea
    assert lineas[0].endswith('| test.identidad | dos\\nlíneas | {"detalle": "x"}')
    assert "===== marca ·" in lineas[1]
