"""E2E del MCP por stdio: un cliente MCP real contra una API de Apolo levantada.

    python -B scripts/e2e_mcp.py                          # API en :8012, proyecto 38
    python -B scripts/e2e_mcp.py --puerto 8011 --proyecto 28 --md

Lanza `python -B -m apolo.mcp_server` por STDIO con el cliente del SDK `mcp` (`stdio_client` +
`ClientSession`) y `APOLO_URL=http://127.0.0.1:<puerto>`, y recorre un guion de tools sobre un
proyecto: lectura (escena, comandos, interferencia, consultas espaciales, ensamblaje, gravedad,
puerta de entrega, verify, render, BOM, plano, ingeniería), un ensayo fantasma (`preview`) y dos
mutaciones que se deshacen solas: un `run_batch` cuyo contrato FALLA (debe revertirse) y
`set_variable` + `undo`. Imprime por paso la tool, ok/ERROR, el tiempo y lo esencial; con `--md`
repite la tabla en Markdown (para la bitácora de un plan). Sale con 1 si un paso falla.

El proyecto debe quedar como estaba: al final se compara el resumen de escena (`get_scene`
summary) y el número de comandos con los del inicio. El árbitro del número de comandos es
`GET /api/health`, fuera del MCP (ninguna tool lo expone). El MCP hijo usa el `core/` de ESTE
árbol (PYTHONPATH), como `scripts/golden_mcp.py`. Córrelo contra una API sobre una COPIA de la
base: el guion muta y deshace, y un corte a medias dejaría el cambio en el autosave.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import struct
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

RAIZ = Path(__file__).resolve().parents[1]

# Una caja lejos de todo (50 m): el fantasma de `preview` y la acción del lote que se revierte.
CAJA = {
    "type": "create_box",
    "params": {
        "name": "E2E fantasma", "width": 100, "depth": 100, "height": 100,
        "position": {"x": 50000, "y": 50000, "z": 0},
    },
}


class Fallo(Exception):
    """El paso respondió, pero no lo que el guion espera."""


class Abortar(Exception):
    """Falló un paso del que dependen los demás: no tiene sentido seguir."""


@dataclass
class Paso:
    n: int
    tool: str
    ok: bool
    seg: float
    nota: str


def _corto(texto: str, n: int = 170) -> str:
    texto = " ".join(str(texto).split())
    return texto if len(texto) <= n else texto[: n - 1] + "…"


def _texto(res) -> str:
    return "\n".join(b.text for b in res.content if b.type == "text")


def _json(res):
    if res.isError:
        raise Fallo(f"la tool dio error: {_corto(_texto(res))}")
    return json.loads(_texto(res))


def _exige(cond, msg: str) -> None:
    if not cond:
        raise Fallo(msg)


def _kb(obj) -> str:
    return f"{len(json.dumps(obj, ensure_ascii=False).encode()) / 1024:.1f} KB"


def _difs(a: dict, b: dict) -> list[str]:
    return sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))


def _estados(reglas) -> str:
    if reglas is None:
        return "no aplica"  # sin transportador ni requisitos: la API devuelve null
    if not isinstance(reglas, list):
        return str(reglas)
    return ", ".join(f"{n} {e}" for e, n in sorted(Counter(r.get("estado") for r in reglas).items()))


class Guion:
    """Sesión MCP + registro de pasos. Cada `paso` llama una tool y aplica su `check`."""

    def __init__(self, sesion: ClientSession, url: str, espera_s: float):
        self.sesion = sesion
        self.url = url
        self.espera = timedelta(seconds=espera_s)
        self.pasos: list[Paso] = []

    def salud(self) -> dict:
        """El árbitro fuera del MCP: proyecto activo, nº de features y de comandos."""
        return httpx.get(f"{self.url}/api/health", timeout=30).json()

    def registra(self, tool: str, ok: bool, t0: float, nota: str):
        p = Paso(len(self.pasos) + 1, tool, ok, time.perf_counter() - t0, nota)
        self.pasos.append(p)
        print(f"{p.n:>2}. {p.tool:<30} {'ok' if ok else 'ERROR':<5} {p.seg:7.1f} s  {nota}",
              flush=True)

    async def paso(self, tool: str, args: dict, check, etiqueta: str | None = None):
        """Llama `tool` por MCP; `check(res) -> (nota, valor)`. Devuelve valor (None si falla)."""
        nombre = etiqueta or tool
        t0 = time.perf_counter()
        try:
            res = await self.sesion.call_tool(tool, args, read_timeout_seconds=self.espera)
        except Exception as exc:  # transporte: timeout del cliente, hijo muerto
            self.registra(nombre, False, t0, f"excepción del cliente: {_corto(repr(exc))}")
            return None
        try:
            nota, valor = check(res)
        except Fallo as exc:
            self.registra(nombre, False, t0, str(exc))
            return None
        except (KeyError, TypeError, ValueError, IndexError, StopIteration,
                httpx.HTTPError) as exc:
            self.registra(nombre, False, t0,
                          f"respuesta inesperada ({exc!r}): {_corto(_texto(res))}")
            return None
        self.registra(nombre, True, t0, nota)
        return valor


# ------------------------------------------------------------------------------- checks
def _resumen(res):
    d = _json(res)
    bbox = " × ".join(f"{x:g}" for x in d["bbox_conjunto_mm"])
    return (f"{d['total_solidos']} sólidos, {len(d['grupos'])} grupos, "
            f"{d['masa_total_kg']} kg, bbox {bbox}, {len(d['variables'])} variables"), d


def _igual_a(g: Guion, ref: dict, salud0: dict, que: str):
    """El resumen y el nº de comandos/features son los del inicio."""
    def check(res):
        d = _json(res)
        difs = _difs(d, ref)
        _exige(not difs, f"{que}: el resumen cambió en {difs}")
        s = g.salud()
        for k in ("project_id", "features", "commands"):
            _exige(s.get(k) == salud0.get(k), f"{que}: {k} {salud0.get(k)} → {s.get(k)}")
        return f"{que}: resumen idéntico; {s['commands']} comandos, {s['features']} features", d
    return check


def _png(res):
    _exige(not res.isError, f"la tool dio error: {_corto(_texto(res))}")
    img = next(b for b in res.content if b.type == "image")
    data = base64.b64decode(img.data)
    _exige(data[:8] == b"\x89PNG\r\n\x1a\n", f"no es un PNG ({img.mimeType})")
    ancho, alto = struct.unpack(">II", data[16:24])
    return f"{img.mimeType} {ancho} × {alto}, {len(data) / 1024:.0f} KB", None


def _error_esperado(*claves: str):
    """La tool DEBE fallar y el mensaje debe nombrar `claves`."""
    def check(res):
        texto = _texto(res)
        _exige(res.isError, f"se esperaba error y respondió: {_corto(texto)}")
        faltan = [c for c in claves if c.lower() not in texto.lower()]
        _exige(not faltan, f"el error no menciona {faltan}: {_corto(texto)}")
        return f"error claro: {_corto(texto, 150)}", texto
    return check


def _variable(pedida: str | None, variables: list[dict]) -> tuple[str, str, str]:
    """(nombre, expresión actual, expresión nueva). Sin `pedida`: la 1.ª numérica × 1.1."""
    actuales = {v["name"]: v for v in variables}
    if pedida:
        nombre, _, nueva = pedida.partition("=")
        _exige(nombre in actuales, f"la variable {nombre!r} no existe en el proyecto")
        return nombre, str(actuales[nombre]["expression"]), nueva
    v = next(v for v in variables if isinstance(v.get("value"), (int, float)) and v["value"])
    return v["name"], str(v["expression"]), f"{round(v['value'] * 1.1, 3):g}"


# ------------------------------------------------------------------------------- guion
async def recorrer(g: Guion, a) -> None:
    t0 = time.perf_counter()
    nombres = [t.name for t in (await g.sesion.list_tools()).tools]
    g.registra("list_tools", len(nombres) == a.tools, t0,
               f"{len(nombres)} tools (esperadas {a.tools})")

    def proyectos(res):
        lista = _json(res)
        mio = next((p for p in lista if p.get("id") == a.proyecto), None)
        _exige(mio is not None, f"el proyecto {a.proyecto} no está en la lista")
        return f"{len(lista)} proyectos; el {a.proyecto} es {mio.get('name')!r}", mio
    await g.paso("list_projects", {}, proyectos)

    def abrir(res):
        d = _json(res)
        b = d.get("briefing") or {}
        _exige(b, "open_project no trae briefing")
        return (f"{d['proyecto']}: {d['total_solidos']} sólidos; briefing {_kb(b)} "
                f"({', '.join(sorted(b))})"), d
    if await g.paso("open_project", {"project_id": a.proyecto}, abrir) is None:
        raise Abortar("no se pudo abrir el proyecto")
    salud0 = g.salud()
    print(f"    árbitro /api/health: proyecto {salud0['project_id']}, {salud0['features']} "
          f"features, {salud0['commands']} comandos", flush=True)

    r0 = await g.paso("get_scene", {"summary": True}, _resumen, "get_scene (summary)")
    if r0 is None:
        raise Abortar("sin resumen inicial no hay contra qué comparar")

    # El grupo más chico con ≥ 2 piezas da las piezas A y B (render y consultas baratas).
    grupos = sorted((x for x in r0["grupos"] if x["n_piezas"] >= 2), key=lambda x: x["n_piezas"])
    grupo = grupos[0]["grupo"] if grupos else None
    filtro = {"ids": [grupo]} if grupo else {"limit": 2}

    def filtrada(res):
        d = _json(res)
        sol = d["solidos"]
        _exige(len(sol) >= 2, f"la escena filtrada trae {len(sol)} sólidos")
        _exige(not any("mesh" in s or "malla" in s for s in sol), "el brief filtrado trae mallas")
        _exige("variables" not in d, "el brief filtrado trae variables")
        return (f"{filtro}: {d['total_filtrado']} de {d['total_solidos']}; "
                f"A={sol[0]['id']} ({sol[0]['nombre']}), B={sol[1]['id']}"), sol
    sol = await g.paso("get_scene", filtro, filtrada, "get_scene (filtrada)")
    if sol is None:
        raise Abortar("sin piezas A y B no hay a qué apuntar")
    pa, pb = sol[0], sol[1]
    a_id, b_id = pa["id"], pb["id"]
    foco = [grupo] if grupo else [a_id]

    def buscar(res):
        d = _json(res)
        ids = [c["id"] for c in d["commands"]]
        _exige(pa["comando"] in ids, f"find_commands no devuelve el creador {pa['comando']}")
        tipos = Counter(c["type"] for c in d["commands"])
        return f"{d['total']} comandos tocan {a_id}: {dict(tipos)}", None
    await g.paso("find_commands", {"feature": a_id}, buscar)

    def comando(res):
        d = _json(res)
        return f"{pa['comando']} = {d['type']} ({len(d['params'])} params)", None
    await g.paso("get_command", {"command_id": pa["comando"]}, comando)

    def interferencia(res):
        d = _json(res)
        return f"{len(d['interferencias'])} interferencias en pares con {a_id}", None
    await g.paso("check_interference", {"ids": [a_id]}, interferencia, "check_interference (ids)")

    def cerca(res):
        d = _json(res)
        ids = [c["id"] for c in d["cercanas"]]
        return f"{len(ids)} piezas a ≤ 50 mm de {a_id}: {', '.join(ids[:6])}", None
    await g.paso("near", {"feature": a_id, "radius": 50}, cerca)

    def medir(res):
        d = _json(res)
        return f"{a_id} ↔ {b_id}: {d['dist_mm']} mm", None
    await g.paso("measure", {"a": a_id, "b": b_id}, medir)

    def sujecion(res):
        d = _json(res)
        return (f"{d['n_grounded']}/{d['n_total']} sujetas, {d['n_floating']} flotantes, "
                f"{len(d.get('isolated') or [])} aisladas"), None
    await g.paso("check_assembly", {}, sujecion)

    def gravedad(res):
        d = _json(res)
        return (f"{d['n_grounded']} sujetas, {d['n_dynamic']} dinámicas, "
                f"{len(d['fell'] or [])} caen, settled={d['settled']}"), None
    await g.paso("gravity_test", {}, gravedad)

    def puerta(res):
        d = _json(res)
        _exige(d["veredicto"] in ("VERDE", "AMARILLO", "ROJO"), f"veredicto {d['veredicto']!r}")
        return (f"{d['veredicto']}: {len(d['bloqueantes'])} bloqueantes, {len(d['avisos'])} "
                f"avisos, {len(d['no_aplica'])} no aplica"), None
    await g.paso("delivery_check", {}, puerta)

    def aserciones(res):
        d = _json(res)
        oks = [r["ok"] for r in d["resultados"]]
        _exige(d["ok"] is False and oks == [True, False], f"esperado [True, False]: {oks}")
        falla = d["resultados"][1]
        return (f"pasa «existe {a_id}»; falla «volumen» (medido {falla['actual']}, esperado "
                f"{falla['esperado']})"), None
    checks = [{"tipo": "existe", "id": a_id},
              {"tipo": "volumen", "id": a_id, "max": round(pa["volumen_mm3"] / 2, 1)}]
    await g.paso("verify", {"checks": checks}, aserciones)

    await g.paso("render_view", {"isolate": foco, "fit_ids": foco, "zoom": 1.2}, _png,
                 "render_view (isolate)")

    def fantasma(res):
        d = _json(res)
        _exige(len(d["fantasmas"]) == 1, f"{len(d['fantasmas'])} fantasmas")
        return (f"1 fantasma ({d['fantasmas'][0]['volumen_mm3']:g} mm³), "
                f"{len(d['colisiones_nuevas'])} colisiones nuevas"), None
    await g.paso("preview", {"actions": [CAJA], "data": True}, fantasma, "preview (data)")

    contrato = [{"tipo": "volumen", "id": "$1", "max": 1, "nombre": "e2e-debe-fallar"}]
    await g.paso("run_batch", {"actions": [CAJA], "expect": contrato},
                 _error_esperado("contrato"), "run_batch (expect falla)")
    await g.paso("get_scene", {"summary": True}, _igual_a(g, r0, salud0, "tras el lote"),
                 "get_scene (summary)")

    try:
        var, antes, nueva = _variable(a.variable, r0["variables"])
    except (Fallo, StopIteration) as exc:
        raise Abortar(f"sin variable que editar: {exc or 'ninguna numérica'}") from exc

    def fija(res):
        d = _json(res)
        v = next(x for x in d["variables"] if x["name"] == var)
        _exige(str(v["expression"]) == nueva, f"{var} quedó en {v['expression']!r}")
        return f"{var}: {antes} → {v['value']:g}", d

    def distinto(res):
        d = _json(res)
        difs = _difs(d, r0)
        _exige(difs, "el resumen no cambió tras set_variable")
        bbox = " × ".join(f"{x:g}" for x in d["bbox_conjunto_mm"])
        return f"cambió {difs}: bbox {bbox}, {d['masa_total_kg']} kg", d

    def deshecho(res):
        d = _json(res)
        v = next(x for x in d["variables"] if x["name"] == var)
        _exige(d.get("puede_rehacer") is True, "undo no dejó nada para rehacer")
        return f"{var} = {v['value']:g}; puede_rehacer", d

    hecho = await g.paso("set_variable", {"name": var, "expression": nueva}, fija)
    if hecho is not None:
        await g.paso("get_scene", {"summary": True}, distinto, "get_scene (summary)")
        deshacer = True
    else:
        # Un rechazo deja el documento intacto. Un timeout del cliente no frena al servidor: el
        # resumen (espera al STATE_LOCK) lo distingue y, si la edición se aplicó, se deshace.
        intacto = await g.paso("get_scene", {"summary": True},
                               _igual_a(g, r0, salud0, "tras el rechazo"), "get_scene (summary)")
        deshacer = intacto is None
    if deshacer:
        await g.paso("undo", {}, deshecho)
        await g.paso("get_scene", {"summary": True}, _igual_a(g, r0, salud0, "tras undo"),
                     "get_scene (summary)")

    def bom(res):
        d = _json(res)
        filas = d if isinstance(d, list) else next(v for v in d.values() if isinstance(v, list))
        _exige(filas, "BOM vacío")
        return f"{len(filas)} filas", None
    await g.paso("get_bom", {}, bom)

    def plano(res):
        d = _json(res)
        _exige(d.get("ok") and d["bytes"] > 1000, f"plano de {d.get('bytes')} bytes")
        return f"PDF de {d['bytes'] / 1024:.0f} KB (isolate + dims {a_id}, sin path)", None
    spec = {"sheet": "A3", "isolate": [a_id], "dims": [a_id]}
    await g.paso("drawing", {"spec": spec}, plano, "drawing (sin path)")

    await g.paso("get_job", {"job_id": "e2e-no-existe", "wait_s": 1},
                 _error_esperado("404"), "get_job (inexistente)")

    def ingenieria(res):
        d = _json(res)
        _exige("ingenieria" in d and "estructura" in d, f"faltan bloques: {sorted(d)}")
        return (f"ingeniería: {_estados(d['ingenieria'])} · estructura: "
                f"{_estados(d['estructura'])}"), None
    await g.paso("engineering_check", {}, ingenieria)

    await g.paso("get_scene", {"summary": True}, _igual_a(g, r0, salud0, "al final"),
                 "get_scene (summary)")


async def correr(a) -> Guion | None:
    url = f"http://127.0.0.1:{a.puerto}"
    env = dict(os.environ)
    env["APOLO_URL"] = url
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(RAIZ / "core"), os.environ.get("PYTHONPATH")) if p)
    servidor = StdioServerParameters(
        command=sys.executable, args=["-B", "-m", "apolo.mcp_server"], env=env, cwd=str(RAIZ))
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as stderr_hijo:
        try:
            async with stdio_client(servidor, errlog=stderr_hijo) as (leer, escribir):
                async with ClientSession(leer, escribir) as sesion:
                    init = await sesion.initialize()
                    print(f"MCP {init.serverInfo.name} {init.serverInfo.version} por stdio → {url}"
                          f" (proyecto {a.proyecto})\n", flush=True)
                    g = Guion(sesion, url, a.espera)
                    try:
                        await recorrer(g, a)
                    except Abortar as exc:
                        print(f"\nABORTADO: {exc}", flush=True)
                        g.pasos.append(Paso(len(g.pasos) + 1, "(guion)", False, 0.0, str(exc)))
                    return g
        finally:
            stderr_hijo.seek(0)
            cola = stderr_hijo.read().strip().splitlines()[-15:]
            errores = [x for x in cola if "Error" in x or "Traceback" in x]
            if errores:
                print("\nstderr del MCP (cola):\n  " + "\n  ".join(cola), flush=True)


def tabla_md(pasos: list[Paso]) -> str:
    filas = ["| # | tool | resultado | tiempo | lo esencial |", "|---|---|---|---|---|"]
    for p in pasos:
        nota = p.nota.replace("|", "\\|")
        filas.append(f"| {p.n} | `{p.tool}` | {'ok' if p.ok else 'ERROR'} | {p.seg:.1f} s | "
                     f"{nota} |")
    return "\n".join(filas)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--puerto", type=int, default=8012, help="puerto de la API (def. 8012)")
    ap.add_argument("--proyecto", type=int, default=38, help="id del proyecto (def. 38)")
    ap.add_argument("--variable", help="NOMBRE=EXPR para set_variable (def. la 1.ª × 1.1)")
    ap.add_argument("--tools", type=int, default=79, help="nº de tools esperado (def. 79)")
    ap.add_argument("--espera", type=float, default=300.0,
                    help="segundos que el cliente espera cada tool (def. 300)")
    ap.add_argument("--md", action="store_true", help="repite la tabla en Markdown")
    ap.add_argument("--forzar", action="store_true",
                    help="permite el puerto 8000 (la API de trabajo: el guion muta y deshace)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if a.puerto == 8000 and not a.forzar:
        print("El :8000 es la API de trabajo y el guion muta (y deshace): levanta una API sobre "
              "una COPIA de la base en otro puerto, o pasa --forzar.")
        return 2
    try:
        salud = httpx.get(f"http://127.0.0.1:{a.puerto}/api/health", timeout=10).json()
    except httpx.HTTPError as exc:
        print(f"No responde la API en :{a.puerto} ({exc!r}): levántala antes.")
        return 2
    print(f"API :{a.puerto} — salud ok={salud.get('ok')}, documento {salud.get('documento')}, "
          f"proyecto activo {salud.get('project_id')}")
    t0 = time.perf_counter()
    g = asyncio.run(correr(a))
    pasos = g.pasos if g else []
    malos = [p for p in pasos if not p.ok]
    if a.md:
        print("\n" + tabla_md(pasos))
    print(f"\n{len(pasos) - len(malos)}/{len(pasos)} pasos ok en {time.perf_counter() - t0:.0f} s"
          + (f"; fallaron: {', '.join(f'#{p.n} {p.tool}' for p in malos)}" if malos else ""))
    return 1 if malos or not pasos else 0


if __name__ == "__main__":
    sys.exit(main())
