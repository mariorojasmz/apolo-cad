"""Golden del servidor MCP: congela lo que ve un cliente MCP y avisa si cambia.

    python scripts/golden_mcp.py --comparar    # exit 1 y diff si algo cambió
    python scripts/golden_mcp.py --congelar    # reescribe tests/data/mcp_golden/ (revisar el diff)

Qué congela (plan chat-cliente-igual, F1): (a) las instructions; (b) `list_tools()` canónico
(orden de tools y de params incluido: se compara el TEXTO, no el dict); (c) por cada una de las
tools, al menos una `mcp.call_tool(...)` real (validación de FastMCP incluida) contra un
`httpx.MockTransport` con respuestas canónicas por ruta: las peticiones que salen (método, URL,
query, cuerpo, cabeceras y config del `httpx.Client`) y lo que vuelve (texto literal, sha256 de
imágenes y archivos, o `str(ToolError)`), con los caminos de error: 400 con `detail`, job en
error, 404 de job, conexión rechazada. `tests/test_mcp_golden.py` lo corre en cada suite.

Las cabeceras omiten `user-agent`, `accept-encoding` y `content-length`: dependen de la versión
e instalación de httpx (brotli/zstd, separadores del JSON), no de Apolo; el cuerpo va entero.
Si sube `mcp` o `pydantic` y sólo cambia el schema, se revisa el diff y se re-congela.
"""

from __future__ import annotations

import asyncio
import base64
import difflib
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import parse_qsl

import httpx

RAIZ = Path(__file__).resolve().parents[1]
# Mide ESTE árbol: en un worktree el venv apunta al checkout principal (CLAUDE.md raíz).
if str(RAIZ / "core") not in sys.path:
    sys.path.insert(0, str(RAIZ / "core"))


def _cargar_casos():
    """Los casos viven al lado; se cargan por ruta para no meter `scripts/` en sys.path."""
    ruta = Path(__file__).with_name("golden_mcp_casos.py")
    spec = importlib.util.spec_from_file_location("golden_mcp_casos", ruta)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_casos = _cargar_casos()
CASOS, RUTAS, URL_GOLDEN = _casos.CASOS, _casos.RUTAS, _casos.URL_GOLDEN

DIR_GOLDEN = RAIZ / "tests" / "data" / "mcp_golden"
ARCHIVOS = ("instructions.txt", "list_tools.json", "llamadas.json")
_SIN = {"user-agent", "accept-encoding", "content-length"}


def _texto(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _respuesta(spec, req: httpx.Request) -> httpx.Response:
    if callable(spec):
        spec = spec(req)
    if spec.get("conexion"):
        raise httpx.ConnectError("conexión rechazada (golden)", request=req)
    if "json" in spec:
        return httpx.Response(spec.get("status", 200), json=spec["json"])
    return httpx.Response(spec.get("status", 200), content=spec["bytes"],
                          headers={"content-type": spec.get("tipo", "application/octet-stream")})


def _buscar(metodo: str, ruta: str, tabla):
    for m, rx, spec in tabla:
        if m == metodo and re.fullmatch(rx, ruta):
            return spec
    raise AssertionError(f"golden: sin respuesta canónica para {metodo} {ruta}")


def _registrar(req: httpx.Request, cliente: dict) -> dict:
    cuerpo = None
    if req.content:
        try:
            cuerpo = json.loads(req.content)
        except ValueError:
            cuerpo = {"sha256": _sha(req.content), "bytes": len(req.content)}
    return {
        "metodo": req.method,
        "url": f"{req.url.scheme}://{req.url.host}:{req.url.port}{req.url.path}",
        "query": [list(p) for p in parse_qsl(req.url.query.decode(), keep_blank_values=True)],
        "cuerpo": cuerpo,
        "cabeceras": {k: v for k, v in sorted(req.headers.items()) if k.lower() not in _SIN},
        "cliente": cliente,
    }


def _contenido(bloques) -> list:
    out = []
    for b in bloques:
        if b.type == "text":
            out.append({"texto": b.text})
        elif b.type == "image":
            out.append({"imagen": b.mimeType, "sha256": _sha(base64.b64decode(b.data))})
        else:
            out.append({"tipo": b.type})
    return out


def _correr_caso(mcp_server, caso: dict, carpeta: Path) -> dict:
    """Una llamada real a `mcp.call_tool` con el transporte HTTP falso."""
    from mcp.server.fastmcp.exceptions import ToolError

    sobre = [(m, rx, spec) for (m, rx), spec in caso.get("rutas", {}).items()]
    secuencias: dict = {}
    peticiones: list = []
    real = httpx.Client

    def fabrica(*args, **kwargs):
        cliente = {k: (v if isinstance(v, (str, int, float, bool, type(None))) else repr(v))
                   for k, v in sorted(kwargs.items())}

        def handler(req: httpx.Request) -> httpx.Response:
            peticiones.append(_registrar(req, cliente))
            try:
                spec = _buscar(req.method, req.url.path, sobre)
            except AssertionError:
                spec = _buscar(req.method, req.url.path, RUTAS)
            if isinstance(spec, list):  # secuencia: una respuesta por llamada, la última se repite
                i = secuencias.setdefault(id(spec), 0)
                secuencias[id(spec)] = i + 1
                spec = spec[min(i, len(spec) - 1)]
            return _respuesta(spec, req)

        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    previos = (mcp_server.APOLO_URL, mcp_server.APOLO_MCP_WAIT_S)
    httpx.Client = fabrica
    mcp_server.APOLO_URL = URL_GOLDEN
    mcp_server.APOLO_MCP_WAIT_S = caso.get("espera", 90.0)
    registro: dict = {"caso": caso["caso"], "tool": caso["tool"], "args": caso["args"]}
    try:
        try:
            out = asyncio.run(mcp_server.mcp.call_tool(caso["tool"], caso["args"]))
        except ToolError as exc:
            registro["error"] = str(exc)
        else:
            bloques, estructurado = out if isinstance(out, tuple) else (out, None)
            registro["salida"] = _contenido(bloques)
            if estructurado is not None:
                texto = bloques[0].text if bloques and bloques[0].type == "text" else None
                registro["estructurado"] = (
                    "= {result: texto}" if estructurado == {"result": texto} else estructurado
                )
    finally:
        httpx.Client = real
        mcp_server.APOLO_URL, mcp_server.APOLO_MCP_WAIT_S = previos
    registro["peticiones"] = peticiones
    archivos = {}
    for f in sorted(carpeta.rglob("*")):
        if f.is_file():
            archivos[f.relative_to(carpeta).as_posix()] = _sha(f.read_bytes())
            f.unlink()
    if archivos:
        registro["archivos"] = archivos
    return registro


def generar() -> dict[str, str]:
    """Texto de cada archivo del golden, generado desde el código de ESTE árbol."""
    from apolo import mcp_server

    tools = asyncio.run(mcp_server.mcp.list_tools())
    lista = [t.model_dump(mode="json", exclude_none=True) for t in tools]
    llamadas = []
    previo = os.getcwd()
    with tempfile.TemporaryDirectory(prefix="mcp-golden-") as tmp:
        os.chdir(tmp)  # las tools que escriben archivos reciben nombres pelados → sin rutas
        try:
            for caso in CASOS:
                llamadas.append(_correr_caso(mcp_server, caso, Path(tmp)))
        finally:
            os.chdir(previo)
    return {
        "instructions.txt": mcp_server.mcp.instructions,
        "list_tools.json": _texto(lista),
        "llamadas.json": _texto(llamadas),
    }


def tools_sin_caso() -> list[str]:
    """Tools registradas sin ninguna llamada en el golden (una tool nueva necesita su caso)."""
    from apolo import mcp_server

    nombres = [t.name for t in asyncio.run(mcp_server.mcp.list_tools())]
    con_caso = {c["tool"] for c in CASOS}
    return [n for n in nombres if n not in con_caso]


def comparar(actual: dict[str, str] | None = None) -> list[str]:
    """Diferencias entre el golden congelado y el código actual ([] = idéntico)."""
    actual = actual or generar()
    difs = []
    for nombre in ARCHIVOS:
        ruta = DIR_GOLDEN / nombre
        congelado = ruta.read_text(encoding="utf-8") if ruta.is_file() else ""
        if congelado != actual[nombre]:
            diff = list(difflib.unified_diff(
                congelado.splitlines(), actual[nombre].splitlines(),
                f"congelado/{nombre}", f"actual/{nombre}", lineterm="", n=2))
            recorte = diff[:80] + ([f"… ({len(diff) - 80} líneas más)"] if len(diff) > 80 else [])
            difs.append("\n".join(recorte) or f"{nombre}: distinto")
    return difs


def congelar() -> None:
    DIR_GOLDEN.mkdir(parents=True, exist_ok=True)
    for nombre, texto in generar().items():
        with open(DIR_GOLDEN / nombre, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texto)


def main(argv: list[str]) -> int:
    if argv == ["--congelar"]:
        congelar()
        print(f"golden congelado en {DIR_GOLDEN.relative_to(RAIZ).as_posix()} ({len(CASOS)} llamadas)")
        return 0
    if argv == ["--comparar"]:
        faltan = tools_sin_caso()
        difs = comparar()
        for d in difs:
            print(d)
        if faltan:
            print("tools sin caso en el golden:", ", ".join(faltan))
        print("golden MCP:", "IDÉNTICO" if not (difs or faltan) else "DISTINTO")
        return 1 if difs or faltan else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
