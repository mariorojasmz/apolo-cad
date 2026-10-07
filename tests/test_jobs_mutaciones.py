"""sandbox-caliente D8 — `set_variable`, `run_command` y `edit_command` encolan como job.

Un `set_variable` en el proyecto 38 replaya el log entero (~170 s antes de F1) y la tool MCP lo
llamaba síncrona con httpx a 120 s: el agente recibía «timed out» mientras el servidor SÍ aplicaba
el cambio, y no sabía si se había aplicado. Ahora las tres rutas aceptan `?async=true` (el MISMO
closure por `_sync_or_job`) y las tools usan `_submit_and_wait`: el brief de siempre si el job
termina dentro de la espera, o un RECIBO para `get_job`. Sin `?async` el REST queda como estaba
(la UI no cambia). Los lotes ya lo hacían: `tests/test_jobs.py`.
"""

import asyncio
import copy
import importlib.util
import json
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.doc.document import Document

CAJA = {"name": "A", "width": 50, "depth": 50, "height": 50}


def _con_caja(doc):
    doc.execute("create_box", CAJA)


def _con_variable(doc):  # el caso que dolió: editar una variable que ya existe y se usa
    doc.execute("set_variable", {"name": "L", "expression": "50"})
    doc.execute("create_box", {**CAJA, "width": "=L"})


# tipo de job → (preparación del documento, método, ruta, query, cuerpo válido, cuerpo inválido)
RUTAS = {
    "run_command": (None, "POST", "/api/commands", {},
                    {"type": "create_box", "params": CAJA},
                    {"type": "fillet", "params": {"feature": "noexiste", "radius": 2}}),
    "edit_command": (_con_caja, "PUT", "/api/commands/c1", {"merge": "true"},
                     {"params": {"width": 80}}, {"params": {"anchura": 3}}),
    "set_variable": (_con_variable, "POST", "/api/variables", {},
                     {"name": "L", "expression": "80"}, {"name": "L", "expression": "2*"}),
}


def _doc(tipo: str) -> Document:
    doc = Document("d8")
    preparar = RUTAS[tipo][0]
    if preparar:
        preparar(doc)
    return doc


def _pedir(client, tipo: str, valido: bool = True, async_: bool = False):
    _, metodo, ruta, query, bueno, malo = RUTAS[tipo]
    params = {**query, **({"async": "true"} if async_ else {})}
    return client.request(metodo, ruta, params=params, json=bueno if valido else malo)


def _await_job(client, job_id, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/jobs/{job_id}", params={"wait_s": 5})
        assert r.status_code == 200, r.text
        if r.json()["estado"] in ("ok", "error"):
            return r.json()
    raise AssertionError(f"el job {job_id} no terminó en {timeout}s")


def _sin_volatiles(payload: dict) -> dict:
    """El payload sin `rev` (revisión por IDENTIDAD del shape: otro documento, otro número)."""
    p = copy.deepcopy(payload)
    for f in p["features"]:
        f.pop("rev", None)
    return p


# ------------------------------------------------------------------------------ la API
@pytest.mark.parametrize("tipo", list(RUTAS))
def test_async_da_202_y_el_job_trae_el_payload_sincrono(tipo):
    client = TestClient(api.app)
    api.DOC = _doc(tipo)
    r = _pedir(client, tipo)
    assert r.status_code == 200 and "job_id" not in r.json(), r.text
    sincrono = r.json()

    api.DOC = doc = _doc(tipo)
    r = _pedir(client, tipo, async_=True)
    assert r.status_code == 202, r.text
    assert r.json()["estado"] == "encolado"
    job = _await_job(client, r.json()["job_id"])
    assert job["estado"] == "ok" and job["tipo"] == tipo, job
    assert _sin_volatiles(job["resultado"]) == _sin_volatiles(sincrono)
    assert job["resultado"]["affected_command_ids"]  # la mutación se aplicó al documento
    assert doc.can_undo


@pytest.mark.parametrize("tipo", list(RUTAS))
def test_sin_async_la_ruta_sigue_sincrona_y_con_su_serializador(tipo):
    """Sin `?async` responde 200 con el payload, como antes. Las tres declaraban `-> dict`: si
    perdieran `response_model=dict`, FastAPI cambiaría de serializador y los bytes también
    (pydantic escribe `1e-7`; `jsonable_encoder` + `json.dumps`, `1e-07`)."""
    _, metodo, ruta, _, _, _ = RUTAS[tipo]
    plantilla = ruta.replace("c1", "{command_id}")
    route = next(r for r in api.app.routes
                 if getattr(r, "path", None) == plantilla and metodo in r.methods)
    assert route.response_model is dict

    api.DOC = _doc(tipo)
    antes = {j["id"] for j in api.JOBS.briefs()}
    r = _pedir(TestClient(api.app), tipo)
    assert r.status_code == 200 and r.headers["content-type"] == "application/json"
    assert {"features", "document", "affected_command_ids"} <= set(r.json())
    assert {j["id"] for j in api.JOBS.briefs()} <= antes  # nada pasó por la cola


def test_put_de_un_id_inexistente_con_async_da_404_al_instante():
    """El pre-chequeo con «¿quisiste decir…?» sigue ANTES de encolar: un id malo no se vuelve
    un job fallido que el agente tenga que ir a recoger."""
    api.DOC = _doc("edit_command")
    antes = {j["id"] for j in api.JOBS.briefs()}
    r = TestClient(api.app).put("/api/commands/c99", params={"async": "true", "merge": "true"},
                                json={"params": {"width": 80}})
    assert r.status_code == 404
    assert r.json()["detail"].startswith("No existe el comando 'c99'")
    assert {j["id"] for j in api.JOBS.briefs()} <= antes


@pytest.mark.parametrize("tipo", list(RUTAS))
def test_un_error_en_el_job_es_el_mismo_400_y_no_aplica_nada(tipo):
    client = TestClient(api.app)
    api.DOC = _doc(tipo)
    r = _pedir(client, tipo, valido=False)
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]

    api.DOC = doc = _doc(tipo)
    comandos = json.loads(json.dumps(doc.commands))
    r = _pedir(client, tipo, valido=False, async_=True)
    assert r.status_code == 202, r.text
    job = _await_job(client, r.json()["job_id"])
    assert job["estado"] == "error" and job["http_status"] == 400, job
    assert job["error"] == detail
    assert json.loads(json.dumps(doc.commands)) == comandos


# ------------------------------------------------------------------------- el cliente MCP
@pytest.fixture
def mcp_server():
    pytest.importorskip("mcp")  # el cliente MCP necesita el paquete mcp
    import apolo.mcp_server as mod

    return mod


# tool → (llamada, método, ruta, query que debe salir)
TOOLS = {
    "run_command": (lambda m: m.run_command(type="create_box", params=CAJA),
                    "POST", "/api/commands", {"async": "true"}),
    "edit_command": (lambda m: m.edit_command(command_id="c1", params={"width": 80}),
                     "PUT", "/api/commands/c1", {"merge": "true", "async": "true"}),
    "set_variable": (lambda m: m.set_variable(name="L", expression="80"),
                     "POST", "/api/variables", {"async": "true"}),
}

RESULTADO = {
    "document": {"name": "t", "variables": [{"name": "L", "expression": "80", "value": 80.0}],
                 "can_undo": True, "can_redo": False},
    "features": [{"id": "c1", "name": "A", "visible": True, "bbox": {}, "volume_mm3": 1.0,
                  "component": None, "command_id": "c1"},
                 {"id": "c2", "name": "B", "visible": True, "bbox": {}, "volume_mm3": 2.0,
                  "component": None, "command_id": "c2"}],
    "total_features": 2,
    "affected_command_ids": ["c1"],
}


class _Respuesta:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


def _api_falsa(monkeypatch, mcp_server, sondeos):
    """`_api` del cliente fino: 202 al enviar y `sondeos` en cada GET del job."""
    llamadas, cola = [], list(sondeos)

    def falsa(method, path, **kwargs):
        llamadas.append((method, path, kwargs))
        if path.startswith("/api/jobs/"):
            return _Respuesta(200, cola.pop(0) if len(cola) > 1 else cola[0])
        return _Respuesta(202, {"job_id": "j1", "estado": "encolado"})

    monkeypatch.setattr(mcp_server, "_api", falsa)
    return llamadas


@pytest.mark.parametrize("tool", list(TOOLS))
def test_la_tool_devuelve_recibo_y_no_timed_out_si_el_job_no_termina(monkeypatch, mcp_server, tool):
    llamar, metodo, ruta, query = TOOLS[tool]
    monkeypatch.setattr(mcp_server, "APOLO_MCP_WAIT_S", 0.3)
    llamadas = _api_falsa(monkeypatch, mcp_server, [{"estado": "corriendo"}])
    assert json.loads(llamar(mcp_server)) == {
        "job": "j1", "estado": "corriendo",
        "seguir": "llama get_job('j1') para recoger el resultado"}
    assert llamadas[0][:2] == (metodo, ruta)
    assert llamadas[0][2]["params"] == query  # el camino seguro NO es opt-in (y merge no se pierde)


@pytest.mark.parametrize("tool", list(TOOLS))
def test_la_tool_devuelve_el_brief_de_siempre_si_el_job_termina(monkeypatch, mcp_server, tool):
    from apolo.brief import _scene_brief

    llamar = TOOLS[tool][0]
    _api_falsa(monkeypatch, mcp_server, [{"estado": "corriendo"},
                                         {"estado": "ok", "resultado": RESULTADO}])
    assert json.loads(llamar(mcp_server)) == _scene_brief(RESULTADO, "diff")


@pytest.mark.parametrize("tool", list(TOOLS))
def test_la_tool_con_el_job_en_error_lanza_como_el_400(monkeypatch, mcp_server, tool):
    _api_falsa(monkeypatch, mcp_server, [{"estado": "error", "http_status": 400,
                                          "error": "Variable 'L': Expresión inválida"}])
    with pytest.raises(RuntimeError, match=r"Apolo rechazó la operación \(400\): Variable 'L'"):
        TOOLS[tool][0](mcp_server)


class _SinLifespan:
    """Presta un TestClient sin entrar (entrar correría el lifespan: la SQLite real)."""

    def __init__(self, cliente):
        self._cliente = cliente

    def __enter__(self):
        return self._cliente

    def __exit__(self, *exc):
        return False


def test_set_variable_lento_de_punta_a_punta_da_recibo_y_get_job_trae_lo_mismo(
        monkeypatch, mcp_server):
    """La tool contra la API REAL (TestClient, sin lifespan): con la cola ocupada —lo que hace un
    replay largo— devuelve el RECIBO en vez de «timed out», y `get_job` trae el MISMO brief que
    habría dado la vía síncrona sobre un documento igual."""
    from apolo.brief import _scene_brief
    from apolo.tools.destino import Destino, apuntar

    cliente = TestClient(api.app)
    destino = Destino("http://testserver", lambda: _SinLifespan(cliente))
    api.DOC = _doc("set_variable")
    esperado = _scene_brief(_pedir(cliente, "set_variable").json(), "diff")

    api.DOC = doc = _doc("set_variable")
    monkeypatch.setattr(mcp_server, "APOLO_MCP_WAIT_S", 0.3)
    puerta = threading.Event()
    api.JOBS.submit("bloqueo", lambda: (puerta.wait(10), {})[1])  # el worker, ocupado
    try:
        with apuntar(destino):
            recibo = json.loads(mcp_server.set_variable(name="L", expression="80"))
        en_cola = next(c["params"]["expression"] for c in doc.commands
                       if c["type"] == "set_variable")
    finally:
        puerta.set()
    assert set(recibo) == {"job", "estado", "seguir"}, recibo
    assert en_cola == "50"  # el recibo llegó antes de aplicar: el resultado se difiere

    with apuntar(destino):
        brief = json.loads(mcp_server.get_job(recibo["job"], wait_s=10))
    assert brief.pop("job") == recibo["job"]
    assert brief == esperado
    assert next(v for v in brief["variables"] if v["name"] == "L")["expression"] == "80"


# ------------------------------------------------------------------- el guion E2E
def _e2e():
    """El guion por ruta (`scripts/` no es paquete). Va a `sys.modules` antes de ejecutarse: sus
    `@dataclass` con `from __future__ import annotations` buscan ahí su propio módulo."""
    nombre = "e2e_mcp_bajo_prueba"
    if nombre not in sys.modules:
        ruta = Path(__file__).resolve().parents[1] / "scripts" / "e2e_mcp.py"
        spec = importlib.util.spec_from_file_location(nombre, ruta)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[nombre] = mod
        spec.loader.exec_module(mod)
    return sys.modules[nombre]


class _Sesion:
    """Sesión MCP falsa: una respuesta por `call_tool`, en orden."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []

    async def call_tool(self, tool, args, read_timeout_seconds=None):
        self.llamadas.append((tool, args))
        texto = json.dumps(self.respuestas.pop(0), ensure_ascii=False)
        return SimpleNamespace(isError=False, content=[SimpleNamespace(type="text", text=texto)])


RECIBO = {"job": "j9", "estado": "corriendo", "seguir": "llama get_job('j9') para recoger el resultado"}
HECHO = {"variables": [{"name": "L", "expression": "80", "value": 80.0}]}


def _fija(e2e):
    def check(res):
        d = e2e._json(res)
        return f"L = {d['variables'][0]['expression']}", d
    return check


def _correr_e2e(e2e, respuestas, plazo_s):
    g = e2e.Guion(_Sesion(respuestas), "http://e2e.test", 5)

    async def guion():
        valor = await g.paso("set_variable", {"name": "L", "expression": "80"},
                             e2e._o_recibo(_fija(e2e)))
        return await e2e.recoger(g, valor, _fija(e2e), "get_job (set_variable)", plazo_s)

    return g, asyncio.run(guion())


def test_el_e2e_recoge_el_recibo_de_set_variable_con_get_job():
    pytest.importorskip("mcp")
    e2e = _e2e()
    g, final = _correr_e2e(e2e, [RECIBO, RECIBO, {**HECHO, "job": "j9"}], plazo_s=60)
    assert final["variables"] == HECHO["variables"]
    assert [t for t, _ in g.sesion.llamadas] == ["set_variable", "get_job", "get_job"]
    assert g.sesion.llamadas[1][1] == {"job_id": "j9", "wait_s": 20}
    assert all(p.ok for p in g.pasos)


def test_el_e2e_falla_si_el_job_no_termina_en_su_plazo():
    pytest.importorskip("mcp")
    e2e = _e2e()
    g, final = _correr_e2e(e2e, [RECIBO], plazo_s=-1)
    assert final is None
    assert [p.ok for p in g.pasos] == [True, False]
    assert "no terminó" in g.pasos[-1].nota
