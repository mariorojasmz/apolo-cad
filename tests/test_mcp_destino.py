"""El cliente fino del MCP habla con el destino fijado en su hilo (plan chat-cliente-igual, F2).

Sin destino, todo sigue yendo a `APOLO_URL` (lo congela `test_mcp_golden.py`). Con
`destino.apuntar(...)`, las tools corridas con `asyncio.run(mcp.call_tool)` en ESE hilo van a
otra API (la del chat de la app) sin tocar nada global: otro hilo, o el MCP por stdio, no se
enteran. También: el brief y las instructions salieron de `mcp_server.py` sin cambiar.
"""

from __future__ import annotations

import ast
import asyncio
import json
import threading
from pathlib import Path

import httpx
import pytest

pytest.importorskip("mcp")  # el cliente MCP necesita el paquete mcp

from mcp.server.fastmcp.exceptions import ToolError  # noqa: E402

from apolo import brief, mcp_server  # noqa: E402
from apolo.design import design_brief  # noqa: E402
from apolo.design.instrucciones import (  # noqa: E402
    AVISO_CONEXION,
    GUIA_TECNICA,
    instrucciones_mcp,
)
from apolo.tools import destino  # noqa: E402

CORE = Path(__file__).resolve().parents[1] / "core" / "apolo"


def _destino_falso(base: str, vistos: list, status: int = 200, cuerpo=None) -> destino.Destino:
    """Destino con transporte en memoria: registra (hilo, url, cabeceras) de cada petición."""

    def handler(req: httpx.Request) -> httpx.Response:
        vistos.append((threading.get_ident(), str(req.url), dict(req.headers)))
        return httpx.Response(status, json=cuerpo if cuerpo is not None else {"base": base})

    return destino.Destino(base, lambda: httpx.Client(
        base_url=base, transport=httpx.MockTransport(handler), headers={"X-Apolo-Documento": "t1"}))


def _texto(out) -> str:
    bloques = out[0] if isinstance(out, tuple) else out
    return bloques[0].text


@pytest.fixture
def sin_api(monkeypatch):
    """APOLO_URL a un puerto imposible: si algo se escapa del destino, falla con conexión."""
    monkeypatch.setattr(mcp_server, "APOLO_URL", "http://127.0.0.1:9")


# ------------------------------------------------------------------- el destino
def test_sin_destino_actual_es_none():
    assert destino.actual() is None


def test_call_tool_va_al_destino_del_hilo(sin_api):
    vistos: list = []
    with destino.apuntar(_destino_falso("http://chat.test", vistos)):
        out = asyncio.run(mcp_server.mcp.call_tool("get_kinematics", {}))
    assert json.loads(_texto(out)) == {"base": "http://chat.test"}
    assert vistos[0][1] == "http://chat.test/api/kinematics"
    assert vistos[0][2]["x-apolo-documento"] == "t1"  # la cabecera del destino viaja
    assert destino.actual() is None  # restaurado al salir


def test_un_lote_encolado_tambien_espera_en_el_destino(sin_api):
    """`run_batch` encola y hace long-poll: el POST y los GET van al MISMO destino."""
    vistos: list = []

    def handler(req: httpx.Request) -> httpx.Response:
        vistos.append(req.url.path)
        if req.method == "POST":
            return httpx.Response(202, json={"job_id": "j9", "estado": "encolado"})
        return httpx.Response(200, json={"estado": "ok", "resultado": {"features": []}})

    d = destino.Destino("http://chat.test", lambda: httpx.Client(
        base_url="http://chat.test", transport=httpx.MockTransport(handler)))
    with destino.apuntar(d):
        out = asyncio.run(mcp_server.mcp.call_tool("run_batch", {"actions": []}))
    assert json.loads(_texto(out))["total_solidos"] == 0
    assert vistos == ["/api/commands/batch", "/api/jobs/j9"]


def test_el_destino_es_por_hilo():
    """Dos hilos con destinos distintos a la vez no se cruzan; el principal no ve ninguno."""
    vistos: list = []
    barrera = threading.Barrier(2)
    resultados: dict = {}

    def trabajar(nombre: str):
        with destino.apuntar(_destino_falso(f"http://{nombre}.test", vistos)):
            barrera.wait(5)  # los dos destinos fijados a la vez
            resultados[nombre] = json.loads(_texto(
                asyncio.run(mcp_server.mcp.call_tool("get_mates", {}))))["base"]

    hilos = [threading.Thread(target=trabajar, args=(n,)) for n in ("a", "b")]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(10)
    assert resultados == {"a": "http://a.test", "b": "http://b.test"}
    assert destino.actual() is None


def test_apuntar_anida_y_restaura_aunque_lance():
    uno = destino.Destino("http://uno", lambda: None)
    dos = destino.Destino("http://dos", lambda: None)
    with destino.apuntar(uno):
        with pytest.raises(RuntimeError):
            with destino.apuntar(dos):
                assert destino.actual() is dos
                raise RuntimeError("x")
        assert destino.actual() is uno
    assert destino.actual() is None


def test_errores_del_destino_iguales_que_por_stdio(sin_api):
    vistos: list = []
    d = _destino_falso("http://chat.test", vistos, status=400, cuerpo={"detail": "malo"})
    with destino.apuntar(d), pytest.raises(ToolError, match=r"rechazó la operación \(400\): malo"):
        asyncio.run(mcp_server.mcp.call_tool("undo", {}))


def test_conexion_rechazada_nombra_el_destino():
    def handler(req):
        raise httpx.ConnectError("rechazada", request=req)

    d = destino.Destino("http://chat.test", lambda: httpx.Client(
        base_url="http://chat.test", transport=httpx.MockTransport(handler)))
    with destino.apuntar(d), pytest.raises(RuntimeError, match="No hay conexión con Apolo en http://chat.test"):
        mcp_server._api("GET", "/api/scene")


def test_destino_http_del_chat():
    """D2: loopback sin proxies del entorno, timeout del cliente fino y cabeceras fijas."""
    d = destino.Destino.http("http://127.0.0.1:8123", {"X-Apolo-Documento": "abc"})
    with d.abrir() as cliente:
        assert str(cliente.base_url) == "http://127.0.0.1:8123"
        assert cliente.timeout.read == destino.TIMEOUT_S == 120
        assert cliente.trust_env is False
        assert cliente.headers["X-Apolo-Documento"] == "abc"


# --------------------------------------------------- brief e instructions movidos
def test_brief_reexportado_por_identidad():
    """D17: lo que un test o un cliente importa de mcp_server sigue ahí, y es lo mismo."""
    assert mcp_server._scene_brief is brief._scene_brief
    assert mcp_server._one_or_many is brief._one_or_many


def test_instrucciones_identicas_y_compuestas():
    assert mcp_server.mcp.instructions == instrucciones_mcp()
    assert instrucciones_mcp() == design_brief() + "\n\n" + GUIA_TECNICA + " " + AVISO_CONEXION


def _imports(ruta: Path) -> set[str]:
    mods: set[str] = set()
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Import):
            mods |= {a.name for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            mods.add(("." * nodo.level) + nodo.module)
    return mods


def test_brief_es_puro():
    assert _imports(CORE / "brief.py") <= {"__future__"}


def test_destino_no_toca_el_documento():
    """Las tools son clientes HTTP: ni `apolo.state` ni `apolo.api` (gate de capas, D4a)."""
    for ruta in (CORE / "tools" / "destino.py", CORE / "tools" / "__init__.py"):
        prohibidos = {m for m in _imports(ruta) if m.startswith(("apolo", "."))}
        assert not prohibidos, f"{ruta.name} importa {prohibidos}"
