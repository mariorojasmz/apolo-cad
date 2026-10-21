"""Los entregables en archivo que tardan (memoria, manual, planos) van como JOB.

Plan manual-rapido F2: la memoria de la piloto tardaba más que los 120 s del httpx del MCP y el
agente recibía «timed out» sin PDF; F2b suma el juego de planos y el plano por intención (sus
isométricas sombreadas). Ahora la tool pide la ruta con `?async=true` (la cola
`ENTREGABLES_JOBS` de la API), espera lo mismo que una mutación (`_submit_and_wait`) y:
  - si el job termina, baja el archivo de `resultado.archivo` y lo escribe en `path`: la tool
    responde lo de siempre, `{ok, path, bytes}`;
  - si no, devuelve el RECIBO `{job, seguir}` y recuerda `path`: `get_job(id)` baja el archivo
    cuando el job termine y lo escribe ahí (o en el `path` que se le pase).

Cliente fino: sólo HTTP. Recibe `api` y `esperar` (el `_api` y el `_submit_and_wait` del
servidor, buscados en CADA llamada para que los tests los parcheen) y NO importa
`apolo.mcp_server` (con `-m` sería `__main__` y cargaría otra copia).
"""

from __future__ import annotations

import json
import pathlib

#: job → `path` donde lo pidió la tool (lo usa `get_job` si no le pasan otro). En memoria del
#: proceso del MCP: un reinicio lo pierde y `get_job` pide el `path`.
_PENDIENTES: dict[str, str] = {}
PLANO = "/api/drawing/spec"


def _recibo(job_id: str, path: str) -> str:
    seguir = f"llama get_job('{job_id}') para guardar el archivo en {path} cuando termine"
    return json.dumps({"job": job_id, "estado": "corriendo", "seguir": seguir},
                      ensure_ascii=False)


def avisos_de_cobro(resp) -> dict:
    """`{avisos, monto_en_riesgo_usd}` de la cabecera `X-Apolo-Avisos` de la cotización (V8.1
    F4c: lo que se cobraría dos veces o no se cobra); {} si no hay."""
    crudo = (getattr(resp, "headers", None) or {}).get("X-Apolo-Avisos")
    return json.loads(crudo) if crudo else {}


def escribir(path: str, data: bytes) -> pathlib.Path:
    """Escribe `data` en `path` creando sus carpetas (los exports del MCP); devuelve la ruta."""
    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return target


def _guardar(api, resultado: dict, path: str) -> dict:
    data = api("GET", resultado["archivo"]).content
    pathlib.Path(path).write_bytes(data)
    return {"ok": True, "path": path, "bytes": len(data)}


def pedir(api, esperar, ruta: str, params: dict, path: str, *, metodo: str = "GET",
          cuerpo: dict | None = None) -> str:
    """La tool: el entregable de `ruta` como job, guardado en `path` o, si tarda, el recibo."""
    resultado, job_id = esperar(metodo, ruta, cuerpo, params)
    if job_id:
        _PENDIENTES[job_id] = path
        return _recibo(job_id, path)
    return json.dumps(_guardar(api, resultado, path), ensure_ascii=False)


def plano(api, esperar, spec: dict, path: str | None) -> str:
    """La tool `drawing`: con `path`, como `pedir`; sin él, el SVG en texto (format="svg") o
    `{ok, bytes, hint}`, como siempre. Si tarda, el recibo (sin `path`, `get_job` lo pide)."""
    if path:
        return pedir(api, esperar, PLANO, {}, path, metodo="POST", cuerpo=spec)
    resultado, job_id = esperar("POST", PLANO, spec, {})
    if job_id:
        return json.dumps({"job": job_id, "estado": "corriendo", "seguir":
                           f"llama get_job('{job_id}') con path para guardar el plano"},
                          ensure_ascii=False)
    if spec.get("format") == "svg":
        return api("GET", resultado["archivo"]).text
    return json.dumps({"ok": True, "bytes": resultado["bytes"],
                       "hint": "pasa path=... para guardar el pdf/dxf"}, ensure_ascii=False)


def recoger(api, job_id: str, resultado: dict, path: str | None) -> str:
    """`get_job` de un entregable terminado: lo guarda en `path` o donde lo pidió la tool."""
    destino = path or _PENDIENTES.get(job_id)
    if not destino:
        return json.dumps({"job": job_id, "estado": "ok", "bytes": resultado.get("bytes"),
                           "seguir": f"pasa path a get_job('{job_id}') para guardar el archivo"},
                          ensure_ascii=False)
    out = _guardar(api, resultado, destino)
    _PENDIENTES.pop(job_id, None)
    return json.dumps({**out, "job": job_id}, ensure_ascii=False)
