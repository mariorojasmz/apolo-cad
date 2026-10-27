"""La API y el MCP dicen lo mismo de una extensión (plan nucleo-abierto-extensiones-privadas, F1c):

- la `webui` nunca rechaza la extensión: sin build, o una segunda UI, se descarta con `aviso` y
  la extensión carga igual (antes, la API la rechazaba entera y el MCP registraba su tool);
- la API publica por extensión lo que sumó (`GET /api/extensiones`: comandos, tools, rutas,
  refs, modelos, ui), sacado de la `Extension` al cargarla y no del proceso del MCP;
- el MCP por stdio registra sólo las tools de las extensiones que SU API reporta cargadas con la
  misma versión; si la API no responde, ninguna.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest

import apolo.api.main as api  # al importar corre cargar() (apagadas): antes del aislado de cada test
from apolo.extensiones import Extension
from test_extensiones import EXTRA, _mcp_hijo

CARGADA = {"nombre": "ext-prueba", "version": "0.1.0", "cargada": True}


# ── la UI no rechaza ─────────────────────────────────────────────────────────────────────────

def test_una_webui_sin_build_carga_la_extension_sin_ui_y_avisa(extensiones_aisladas, monkeypatch,
                                                                tmp_path):
    import ext_prueba

    from apolo.commands.registry import REGISTRY

    monkeypatch.setattr(ext_prueba, "SIN_BUILD", replace(ext_prueba.EXTENSION, webui=tmp_path),
                        raising=False)
    monkeypatch.setenv(EXTRA, "ext_prueba:SIN_BUILD")
    (e,) = extensiones_aisladas.cargar()
    assert e["cargada"] and "no tiene index.html" in e["aviso"], e
    assert "prueba.hola" in REGISTRY and extensiones_aisladas.webui() is None
    assert extensiones_aisladas.detalle()[0]["ui"] is False


def test_una_segunda_ui_se_descarta_y_la_extension_carga(extensiones_aisladas, monkeypatch,
                                                         tmp_path):
    import ext_prueba

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    for d in ("a", "b"):
        (tmp_path / d / "index.html").write_text("<html></html>", encoding="utf-8")
    monkeypatch.setattr(ext_prueba, "CON_UI", replace(ext_prueba.EXTENSION, webui=tmp_path / "a"),
                        raising=False)
    monkeypatch.setattr(ext_prueba, "OTRA_UI", Extension(nombre="ext-otra", prefijo="otra",
                                                         version="1.0", webui=tmp_path / "b"),
                        raising=False)
    monkeypatch.setenv(EXTRA, "ext_prueba:CON_UI,ext_prueba:OTRA_UI")
    primera, segunda = extensiones_aisladas.cargar()
    assert primera == CARGADA
    assert segunda["cargada"] and "ya sirve la suya la extensión «ext-prueba»" in segunda["aviso"]
    assert extensiones_aisladas.webui() == tmp_path / "a"


# ── la API publica lo que sumó cada extensión ────────────────────────────────────────────────

def test_detalle_sale_de_la_extension_y_lo_sirve_la_api(extensiones_aisladas, monkeypatch):
    from fastapi.testclient import TestClient

    from apolo.tools import catalogo

    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION,ext_prueba:CONTRATO_VIEJO")
    extensiones_aisladas.cargar()
    assert "prueba_hola" not in catalogo.DE_EXTENSION  # nadie registró tools en este proceso
    ok, vieja = TestClient(api.app).get("/api/extensiones").json()
    assert ok == {**CARGADA, "comandos": ["prueba.hola"], "tools": ["prueba_hola", "prueba_informe"],
                  "rutas": ["GET /api/prueba/hola", "POST /api/prueba/caja",
                            "GET /api/prueba/piezas", "GET /api/prueba/nota",
                            "PUT /api/prueba/nota", "GET /api/prueba/informe.txt"],
                  "refs": ["prueba.caja"],
                  "modelos_cosim": ["prueba.lampara"], "conectores_plc": ["prueba.tcp"], "builders": [],
                  "puerta": ["prueba.nota_ok", "prueba.siempre"],
                  "costeo": ["prueba.conexionado", "prueba.revision"],
                  "entrega": ["prueba.nota_entrega", "prueba.tablero"], "ui": False}
    assert not vieja["cargada"] and "contrato" in vieja["motivo"] and "comandos" not in vieja
    # /api/health sigue con la forma corta
    assert TestClient(api.app).get("/api/health").json()["extensiones"][0] == CARGADA


def test_sin_extensiones_la_api_lista_vacio():
    from fastapi.testclient import TestClient

    assert TestClient(api.app).get("/api/extensiones").json() == []


# ── el MCP no expone lo que la API no tiene ──────────────────────────────────────────────────

class _Respuesta:
    def __init__(self, datos):
        self._datos = datos

    def json(self):
        return self._datos


def _servidor(responde):
    pedidos = []

    def api(metodo, ruta, **kw):
        pedidos.append((metodo, ruta, kw.get("timeout")))
        if isinstance(responde, Exception):
            raise responde
        return _Respuesta(responde)

    return {"_api": api, "_mutacion": None, "_submit_and_wait": None}, pedidos


@pytest.mark.parametrize(("responde", "registradas", "dice"), [
    ([CARGADA], ["prueba_hola", "prueba_informe"], None),
    ([{**CARGADA, "version": "0.0.9"}], [], "la API tiene la versión 0.0.9"),
    ([{**CARGADA, "cargada": False, "motivo": "x"}], [], "la API no la tiene cargada"),
    ([], [], "la API no la tiene cargada"),
    (RuntimeError("No hay conexión con Apolo"), [], "no pude preguntar a la API"),
])
def test_el_mcp_registra_solo_lo_que_la_api_tiene(extensiones_aisladas, monkeypatch, capsys,
                                                  responde, registradas, dice):
    from apolo.tools.fastmcp_limpio import FastMCPLimpio

    monkeypatch.setenv(EXTRA, "ext_prueba:EXTENSION")  # sin cargar(): es el MCP por stdio
    mcp = FastMCPLimpio("prueba")
    servidor, pedidos = _servidor(responde)
    assert extensiones_aisladas.registrar_tools(mcp, servidor) == registradas
    assert [t.name for t in asyncio.run(mcp.list_tools())] == registradas
    assert pedidos == [("GET", "/api/extensiones", extensiones_aisladas.ESPERA_API_S)]
    if dice:
        assert dice in capsys.readouterr().err


def test_sin_extensiones_el_mcp_no_pregunta_a_la_api(extensiones_aisladas, monkeypatch):
    from apolo.tools.fastmcp_limpio import FastMCPLimpio

    monkeypatch.setenv("APOLO_EXTENSIONES", "0")
    servidor, pedidos = _servidor([CARGADA])
    assert extensiones_aisladas.registrar_tools(FastMCPLimpio("prueba"), servidor) == []
    assert pedidos == []  # el arranque del MCP del núcleo solo no cambia


def test_el_mcp_por_stdio_no_registra_la_tool_si_su_api_no_la_tiene():
    from apolo.pruebas import api_falsa

    with api_falsa({"/api/extensiones": [{**CARGADA, "cargada": False, "motivo": "otra cosa"}]}) as url:
        out = _mcp_hijo(url)
    assert out.returncode == 0, out.stderr[-3000:]
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["n"] == 93 and "prueba_hola" not in res["nombres"]
    assert "ext-prueba no se registran" in out.stderr  # sin tildes: el stderr del hijo es cp1252
