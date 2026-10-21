"""Los entregables en archivo que tardan (memoria de cálculo, manual de ensamblaje) van como JOB.

Plan manual-rapido F2: la memoria de la piloto tardaba más que los 120 s del httpx del MCP y el
agente recibía «timed out» sin PDF. Ahora la tool pide la ruta con `?async=true` (la cola
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


def _recibo(job_id: str, path: str) -> str:
    seguir = f"llama get_job('{job_id}') para guardar el archivo en {path} cuando termine"
    return json.dumps({"job": job_id, "estado": "corriendo", "seguir": seguir},
                      ensure_ascii=False)


def _guardar(api, resultado: dict, path: str) -> dict:
    data = api("GET", resultado["archivo"]).content
    pathlib.Path(path).write_bytes(data)
    return {"ok": True, "path": path, "bytes": len(data)}


def pedir(api, esperar, ruta: str, params: dict, path: str) -> str:
    """La tool: el entregable de `ruta` como job, guardado en `path` o, si tarda, el recibo."""
    resultado, job_id = esperar("GET", ruta, None, params)
    if job_id:
        _PENDIENTES[job_id] = path
        return _recibo(job_id, path)
    return json.dumps(_guardar(api, resultado, path), ensure_ascii=False)


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
