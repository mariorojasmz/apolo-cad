"""El catálogo de tools del chat y su adaptador (plan chat-cliente-igual, F4, D1/D4/D5).

- `tools/catalogo.py`: cada tool del MCP está en `CHAT` o en `FUERA_DEL_CHAT`, nunca en los
  dos; una tool nueva sin clasificar pone esto rojo. Lo que escribe archivos queda fuera u
  oculto. Las etiquetas pasan el mismo gate de texto que las pistas (`test_pistas.py`).
- `agent/herramientas.py`: las definiciones salen de `mcp.list_tools()` (orden del catálogo,
  sin ocultos, deterministas byte a byte, sin tocar el schema del MCP); `ejecutar` corre la
  tool en el destino del hilo, convierte la salida a bloques de Anthropic, da el MISMO texto
  de error que un cliente MCP y hace cumplir el modo; importar el MCP no ensucia el logger
  raíz. Y cada tool que dice NO mutar, corrida contra la API real (TestClient), no cambia el
  documento ni programa un autoguardado.
"""

from __future__ import annotations

import ast
import asyncio
import base64
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import httpx
import pytest

pytest.importorskip("mcp")  # el adaptador del chat corre las tools del MCP

from fastapi.testclient import TestClient  # noqa: E402
from mcp.server.fastmcp.exceptions import ToolError  # noqa: E402

import apolo.api.main as api  # noqa: E402
from apolo import mcp_server  # noqa: E402
from apolo.agent import herramientas  # noqa: E402
from apolo.doc import Document  # noqa: E402
from apolo.tools import catalogo, destino  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
CHAT, FUERA = catalogo.CHAT, catalogo.FUERA_DEL_CHAT


def _tools_mcp() -> dict:
    return {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}


# ------------------------------------------------------------------ el catálogo
def test_cada_tool_del_mcp_esta_en_un_solo_lado():
    mcp = set(_tools_mcp())
    assert set(CHAT) & set(FUERA) == set(), "una tool no puede estar en CHAT y FUERA_DEL_CHAT"
    sin_clasificar = mcp - set(CHAT) - set(FUERA)
    assert not sin_clasificar, (
        f"tools del MCP sin clasificar en tools/catalogo.py: {sorted(sin_clasificar)} — ponlas "
        "en CHAT (muta/etiqueta) o en FUERA_DEL_CHAT (con el motivo)")
    assert (set(CHAT) | set(FUERA)) - mcp == set(), "el catálogo nombra tools que no existen"


def test_lo_que_escribe_archivos_esta_fuera_o_oculto():
    for nombre, tool in _tools_mcp().items():
        rutas = {p for p in tool.inputSchema.get("properties", {})
                 if p == "path" or p.endswith("_path")}
        if rutas and nombre not in FUERA:
            assert rutas <= set(CHAT[nombre].ocultar), f"{nombre}: {rutas} sin ocultar"


def test_lo_oculto_existe_y_es_opcional():
    tools = _tools_mcp()
    for nombre, en_chat in CHAT.items():
        schema = tools[nombre].inputSchema
        for p in en_chat.ocultar:
            assert p in schema.get("properties", {}), f"{nombre}.{p} no es un parámetro"
            assert p not in schema.get("required", []), f"{nombre}.{p} es obligatorio: va FUERA"


def test_fuera_del_chat_dice_por_que():
    for nombre, motivo in FUERA.items():
        assert isinstance(motivo, str) and len(motivo) > 20, nombre


def _imports(ruta: Path) -> set[str]:
    mods: set[str] = set()
    for nodo in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
        if isinstance(nodo, ast.Import):
            mods |= {a.name for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            mods.add(("." * nodo.level) + nodo.module)
    return mods


def test_catalogo_y_adaptador_no_tocan_el_documento():
    """Clientes HTTP (D4a): el catálogo es puro y el adaptador no importa estado ni dominio."""
    core = RAIZ / "core" / "apolo"
    assert not {m for m in _imports(core / "tools" / "catalogo.py") if m.startswith(("apolo", "."))}
    prohibidos = ("apolo.state", "apolo.api", "apolo.doc", "apolo.kernel", "apolo.commands", ".")
    assert not {m for m in _imports(core / "agent" / "herramientas.py") if m.startswith(prohibidos)}


def _gate_de_texto():
    """`faltas()` de test_pistas: el mismo estándar que el texto de los diálogos."""
    spec = importlib.util.spec_from_file_location("_pistas_gate", RAIZ / "tests" / "test_pistas.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.faltas


def test_las_etiquetas_cumplen_el_estandar_de_texto():
    faltas = _gate_de_texto()
    etiquetas = {n: e.etiqueta for n, e in CHAT.items()}
    etiquetas[herramientas.PROPONER] = herramientas.ETIQUETA_PROPONER
    for nombre, texto in etiquetas.items():
        assert faltas(texto + ".") == [], f"{nombre}: «{texto}» {faltas(texto + '.')}"
        assert texto[0].isupper() and len(texto) <= 40, f"{nombre}: «{texto}»"
    assert len(set(etiquetas.values())) == len(etiquetas), "dos tools con el mismo chip"
    assert herramientas.etiqueta("get_scene") == "Leyendo el modelo"
    assert herramientas.etiqueta("no_existe") == "no_existe"


# -------------------------------------------------------------- las definiciones
def _claves_de_schema(nodo, out: set) -> set:
    """Palabras clave en posición de schema (no nombres de parámetro)."""
    if isinstance(nodo, dict):
        for k, v in nodo.items():
            out.add(k)
            if k == "properties":
                for sub in v.values():
                    _claves_de_schema(sub, out)
            elif k in ("items", "additionalProperties", "anyOf"):
                _claves_de_schema(v, out)
    elif isinstance(nodo, list):
        for v in nodo:
            _claves_de_schema(v, out)
    return out


def test_definiciones_en_orden_del_catalogo_y_sin_lo_oculto():
    tools = _tools_mcp()
    defs = herramientas.definiciones()
    assert [d["name"] for d in defs] == [*CHAT, herramientas.PROPONER]
    for d in defs[:-1]:
        assert set(d) == {"name", "description", "input_schema"}
        assert d["description"] == tools[d["name"]].description  # el docstring del MCP, tal cual
        props = d["input_schema"].get("properties", {})
        original = tools[d["name"]].inputSchema["properties"]
        assert list(props) == [p for p in original if p not in CHAT[d["name"]].ocultar]
        assert "title" not in _claves_de_schema(d["input_schema"], set()), d["name"]
    assert "path" not in defs[[d["name"] for d in defs].index("drawing")]["input_schema"]["properties"]
    proponer = defs[-1]
    assert proponer["input_schema"]["required"] == ["actions"]


def test_definiciones_no_tocan_el_schema_del_mcp():
    antes = [t.model_dump(mode="json") for t in asyncio.run(mcp_server.mcp.list_tools())]
    herramientas.definiciones()
    despues = [t.model_dump(mode="json") for t in asyncio.run(mcp_server.mcp.list_tools())]
    assert antes == despues


def _sha_definiciones() -> str:
    texto = json.dumps(herramientas.definiciones(), ensure_ascii=False)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


_SONDA = """
import hashlib, json, logging, sys
raiz = logging.getLogger()
from apolo.agent import herramientas
perezoso = "apolo.mcp_server" not in sys.modules
antes = (raiz.level, list(raiz.handlers), logging.getLogger("httpx").getEffectiveLevel())
defs = herramientas.definiciones()
despues = (raiz.level, list(raiz.handlers), logging.getLogger("httpx").getEffectiveLevel())
texto = json.dumps(defs, ensure_ascii=False)
print(json.dumps({"perezoso": perezoso, "logger_intacto": antes == despues,
                  "sha": hashlib.sha256(texto.encode("utf-8")).hexdigest(),
                  "bytes": len(texto.encode("utf-8"))}))
"""


@pytest.fixture(scope="module")
def sonda():
    """Un proceso NUEVO (otro PYTHONHASHSEED, sin el MCP importado): lo que la API vería."""
    entorno = {**os.environ, "PYTHONHASHSEED": "12345",
               "PYTHONPATH": os.pathsep.join([str(RAIZ / "core"), os.environ.get("PYTHONPATH", "")])}
    out = subprocess.run([sys.executable, "-B", "-c", _SONDA], capture_output=True, text=True,
                         env=entorno, timeout=300, cwd=RAIZ)
    assert out.returncode == 0, out.stderr[-2000:]
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_definiciones_deterministas_byte_a_byte(sonda):
    assert _sha_definiciones() == _sha_definiciones()
    assert sonda["sha"] == _sha_definiciones(), "otro proceso genera otras definiciones"


def test_el_mcp_se_importa_perezoso_y_sin_tocar_el_logger_raiz(sonda):
    assert sonda["perezoso"], "importar herramientas no debe importar apolo.mcp_server"
    assert sonda["logger_intacto"], "importar el MCP reconfiguró el logger raíz (D4d)"


# --------------------------------------------------------------------- ejecutar
@pytest.fixture
def sin_api(monkeypatch):
    """APOLO_URL a un puerto imposible: si una llamada se escapa del destino, falla."""
    monkeypatch.setattr(mcp_server, "APOLO_URL", "http://127.0.0.1:9")


def _destino(vistos: list, respuesta=None) -> destino.Destino:
    def handler(req: httpx.Request) -> httpx.Response:
        vistos.append((req.method, str(req.url), dict(req.headers)))
        if respuesta is not None:
            return respuesta(req)
        return httpx.Response(200, json={"ok": True, "ruta": req.url.path})

    return destino.Destino("http://chat.test", lambda: httpx.Client(
        base_url="http://chat.test", transport=httpx.MockTransport(handler),
        headers={"X-Apolo-Documento": "t1"}))


def test_ejecutar_va_al_destino_y_devuelve_bloques_de_texto(sin_api):
    vistos: list = []
    out = herramientas.ejecutar("get_kinematics", {}, _destino(vistos), "propuesta")
    assert out == {"content": [{"type": "text", "text": '{"ok": true, "ruta": "/api/kinematics"}'}]}
    assert vistos[0][1] == "http://chat.test/api/kinematics"
    assert vistos[0][2]["x-apolo-documento"] == "t1"
    assert destino.actual() is None  # restaurado


def test_ejecutar_convierte_imagenes(sin_api):
    png = b"\x89PNG\r\n\x1a\n chat"
    out = herramientas.ejecutar("render_view", {"isolate": ["c1"]}, _destino(
        [], lambda r: httpx.Response(200, content=png, headers={"content-type": "image/png"})),
        "propuesta")
    assert out == {"content": [{"type": "image", "source": {
        "type": "base64", "media_type": "image/png", "data": base64.b64encode(png).decode()}}]}


def _error_mcp(nombre: str, args: dict, d: destino.Destino) -> str:
    with destino.apuntar(d), pytest.raises(ToolError) as exc:
        asyncio.run(mcp_server.mcp.call_tool(nombre, args))
    return str(exc.value)


@pytest.mark.parametrize("nombre, args", [
    ("undo", {}),                                          # 400 de la API
    ("get_fit", {"nominal_mm": "treinta y cinco"}),        # validación de FastMCP
    ("near", {}),                                          # error propio del cliente fino
])
def test_ejecutar_da_el_mismo_error_que_el_mcp(sin_api, nombre, args):
    d = _destino([], lambda r: httpx.Response(400, json={"detail": "nada que deshacer"}))
    out = herramientas.ejecutar(nombre, args, d, "autonomo")
    assert out["is_error"] is True
    assert out["content"] == [{"type": "text", "text": _error_mcp(nombre, args, d)}]


def test_en_propuesta_lo_que_muta_no_corre_y_en_autonomo_si(sin_api):
    vistos: list = []
    out = herramientas.ejecutar("run_command", {"type": "create_box", "params": {}},
                                _destino(vistos), "propuesta")
    assert out["is_error"] and "propose_commands" in out["content"][0]["text"]
    assert vistos == []
    herramientas.ejecutar("set_variable", {"name": "L", "expression": "10"},
                          _destino(vistos, lambda r: httpx.Response(200, json={"features": []})),
                          "autonomo")
    # set_variable encola como job (sandbox-caliente D8); un 200 sin recibo = payload directo
    assert [v[1] for v in vistos] == ["http://chat.test/api/variables?async=true"]


@pytest.mark.parametrize("nombre, args, texto", [
    ("drawing", {"spec": {}, "path": "C:/x.pdf"}, "path no está disponible"),
    ("gravity_test", {"path": "/tmp/g.gif"}, "path no está disponible"),
    ("export_step", {"path": "x.step"}, "no está disponible en el chat"),
    ("open_project", {"project_id": 1}, "no está disponible en el chat"),
    ("no_existe", {}, "tool desconocida"),
])
def test_ni_oculto_ni_fuera_ni_desconocido_llegan_a_la_api(sin_api, nombre, args, texto):
    vistos: list = []
    out = herramientas.ejecutar(nombre, args, _destino(vistos), "autonomo")
    assert out["is_error"] and texto in out["content"][0]["text"]
    assert vistos == []


def test_ejecutar_rechaza_lo_que_no_le_toca():
    with pytest.raises(ValueError, match="la atiende el chat"):
        herramientas.ejecutar(herramientas.PROPONER, {}, _destino([]), "propuesta")
    with pytest.raises(ValueError, match="modo desconocido"):
        herramientas.ejecutar("get_scene", {}, _destino([]), "auto")


# ------------------------------- lo que no muta, contra la API real, no cambia nada
class _SinLifespan:
    """`_api` abre el cliente con `with`: un TestClient que ENTRA corre el lifespan (la SQLite
    real). Este envoltorio lo presta sin entrar."""

    def __init__(self, cliente: TestClient):
        self._cliente = cliente

    def __enter__(self) -> TestClient:
        return self._cliente

    def __exit__(self, *exc) -> bool:
        return False


@pytest.fixture(scope="module")
def modelo():
    """Mecanismo chico con todo lo que las lecturas consultan: piezas, variable, junta,
    estudio de movimiento, anclaje, unión, requisitos y una nota."""
    doc = Document("catalogo-chat")
    doc.execute("set_variable", {"name": "L", "expression": "2000"})
    base = doc.execute("create_box", {"name": "Base", "width": 100, "depth": 100, "height": 100})
    brazo = doc.execute("create_box", {"name": "Brazo", "width": 100, "depth": 60, "height": 200})
    obst = doc.execute("create_box", {"name": "Tope", "width": 60, "depth": 60, "height": 60,
                                      "position": {"x": 300}})
    doc.execute("add_joint", {"name": "desliza", "type": "prismatica", "parent": base,
                              "child": brazo, "axis": {"x": 1}, "lower": 0, "upper": 400})
    doc.execute("ground", {"name": "g0", "feature": base})
    doc.execute("fasten", {"name": "f0", "a": base, "b": obst, "kind": "perno"})
    doc.set_motion("barrido", [{"t": 0, "values": {"desliza": 0}},
                               {"t": 1, "values": {"desliza": 100}}])
    doc.requirements = {"carga_kg": 15.0, "largo_paquete_mm": 400.0}
    doc.agent_notes = ["nota de prueba"]
    return doc, {"base": base, "brazo": brazo, "tope": obst,
                 "cmd": doc.commands[1]["id"]}


_CAJA = {"type": "create_box", "params": {"name": "Fantasma", "width": 10, "depth": 10,
                                          "height": 10, "position": {"x": -500}}}
_CROQUIS = {
    "points": {"a": [0, 0], "b": [100, 0], "c": [100, 50], "d": [0, 50]},
    "entities": [{"type": "line", "id": f"l{i}", "from": p, "to": q}
                 for i, (p, q) in enumerate(["ab", "bc", "cd", "da"], 1)],
    "constraints": [{"type": "fix", "point": "a"}, {"type": "horizontal", "entity": "l1"},
                    {"type": "length", "entity": "l1", "value": 100}],
}

#: Una entrada de muestra por cada tool del chat que dice NO mutar.
MUESTRAS = {
    "get_scene": lambda i: {},
    "get_command": lambda i: {"command_id": i["cmd"]},
    "find_commands": lambda i: {"type": "create_box"},
    "get_command_schemas": lambda i: {"command_type": "create_box"},
    "get_catalog": lambda i: {"category": "rodamientos", "names_only": True},
    "get_groups": lambda i: {},
    "get_topology": lambda i: {"feature_id": i["base"], "only": "caras"},
    "get_kinematics": lambda i: {},
    "get_mates": lambda i: {},
    "get_connections": lambda i: {},
    "get_motion": lambda i: {},
    "get_requirements": lambda i: {},
    "get_agent_notes": lambda i: {},
    "get_design_guidelines": lambda i: {},
    "get_expression_grammar": lambda i: {},
    "resolve_expression": lambda i: {"expression": "=L/2"},
    "get_fit": lambda i: {"nominal_mm": 35, "hole": "H7", "shaft": "k6"},
    "get_job": lambda i: {"job_id": "no-existe", "wait_s": 0},
    "preview": lambda i: {"actions": [_CAJA], "data": True},
    "render_view": lambda i: {"isolate": [i["base"]], "labels": True},
    "pick_point": lambda i: {"u": 0.5, "v": 0.5},
    "measure": lambda i: {"a": i["base"], "b": i["tope"]},
    "near": lambda i: {"feature": i["base"]},
    "verify": lambda i: {"checks": [{"tipo": "existe", "id": i["base"]},
                                    {"tipo": "sin_interferencia",
                                     "joint_values": {"desliza": 50}}]},
    "check_interference": lambda i: {"joint_values": {"desliza": 100}},
    "check_assembly": lambda i: {},
    "autodetect_connections": lambda i: {},
    "get_dof": lambda i: {},
    "gravity_test": lambda i: {"seconds": 0.2},
    "scan_motion": lambda i: {"name": "barrido", "steps": 3},
    "delivery_check": lambda i: {},
    "test_sketch": lambda i: {"sketch": _CROQUIS},
    "test_script": lambda i: {"code": "result = Box(10, 10, 10)"},
    "engineering_check": lambda i: {},
    "get_mass_properties": lambda i: {},
    "get_stackup": lambda i: {},
    "get_bom": lambda i: {"by_group": True},
    "get_costing": lambda i: {},
    "cut_list": lambda i: {},
    "nesting": lambda i: {"mode": "1d", "stock_w": 6000},
    "drawing": lambda i: {"spec": {"format": "svg", "isolate": [i["base"]]}},
}
#: Su error es el camino que se prueba (un job inexistente → 404, sin tocar nada).
ERROR_ESPERADO = {"get_job"}
#: Rasterizan con VTK: sin contexto OpenGL la API responde 503 y se saltan (el MCP, igual).
VTK = {"render_view", "pick_point"}


def test_cada_lectura_del_chat_tiene_muestra():
    lecturas = {n for n, e in CHAT.items() if not e.muta}
    assert set(MUESTRAS) == lecturas, (
        f"sin muestra: {sorted(lecturas - set(MUESTRAS))}; "
        f"sobran: {sorted(set(MUESTRAS) - lecturas)}")


def _huella(doc: Document):
    with zipfile.ZipFile(io.BytesIO(doc.to_apolo_bytes())) as z:
        archivos = {n: z.read(n) for n in z.namelist()}  # sin las fechas del zip
    piezas = sorted((f.id, f.name, f.visible) for f in doc.scene.values())
    return archivos, piezas, len(doc._undo), len(doc._redo)


@pytest.mark.parametrize("nombre", sorted(MUESTRAS))
def test_lo_que_no_muta_no_cambia_el_documento(monkeypatch, sin_api, modelo, nombre):
    doc, ids = modelo
    monkeypatch.setattr(api, "DOC", doc)
    autoguardados: list = []
    monkeypatch.setattr(api._autosave_sched, "schedule", lambda: autoguardados.append(nombre))
    cliente = TestClient(api.app, raise_server_exceptions=False)
    d = destino.Destino("http://testserver", lambda: _SinLifespan(cliente))
    antes = _huella(doc)

    out = herramientas.ejecutar(nombre, MUESTRAS[nombre](ids), d, "propuesta")

    assert api.DOC is doc, "la tool cambió el documento activo"
    assert _huella(doc) == antes, f"{nombre} dice no mutar pero cambió el documento"
    assert autoguardados == [], f"{nombre} programó un autoguardado"
    texto = " ".join(b.get("text", "") for b in out["content"])
    if nombre in VTK and out.get("is_error") and "(503)" in texto:
        pytest.skip(f"VTK sin contexto OpenGL: {texto[:120]}")
    assert bool(out.get("is_error")) == (nombre in ERROR_ESPERADO), texto[:500]
