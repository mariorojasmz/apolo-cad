"""Servidor MCP de Genix Apolo CAD (stdio).

Expone el CAD como tools estándar MCP para que CUALQUIER agente (Claude Code, Claude Desktop…)
pueda diseñar en Apolo. Es un cliente fino de la API HTTP: exactamente las mismas operaciones
que la UI y el chat integrado, y los cambios aparecen en vivo en el navegador (WebSocket).

Uso: `python -m apolo.mcp_server` (APOLO_URL, por defecto http://127.0.0.1:8000; la API arriba).
"""

from __future__ import annotations

import json
import os
import time

import httpx

from apolo import extensiones
from apolo.brief import _one_or_many, _scene_brief, brief_paso  # noqa: F401 (re-export, D2)
from apolo.design.instrucciones import instrucciones_mcp
from apolo.tools import calidad, cirugia, cosim, destino, entregable, estructura, fastmcp_limpio
from apolo.tools import mcp_electrico, notas, simulacion
from apolo.tools import (calculo, consulta, fabricacion, introspeccion, proyectos, topologia,
                         validacion, visibilidad)
from apolo.tools.recibo import job_receipt as _job_receipt, job_result as _job_result

APOLO_URL = os.environ.get("APOLO_URL", "http://127.0.0.1:8000")

# Espera TOTAL de un lote antes del recibo (V6.5e): 90 s, bajo los 120 s de httpx y los ~180
# del host MCP, así que un lote lento no deja ciego al agente; cada poll es corto (_JOB_POLL_S).
APOLO_MCP_WAIT_S = float(os.environ.get("APOLO_MCP_WAIT_S", "90"))
_JOB_POLL_S = 20.0

# Instructions: una sola guía para el MCP y el chat (design/instrucciones.py); docstrings limpios.
mcp = fastmcp_limpio.FastMCPLimpio("apolo-cad", instructions=instrucciones_mcp())


def _api(method: str, path: str, **kwargs):
    # El chat de la app fija en su hilo la API que lo atiende (tools/destino.py); el MCP por
    # stdio no fija nada y habla con APOLO_URL, leído aquí para que los tests lo parcheen.
    d = destino.actual()
    base = d.base_url if d else APOLO_URL
    try:
        cliente = d.abrir() if d else httpx.Client(base_url=APOLO_URL, timeout=120)
        with cliente as client:
            response = client.request(method, path, **kwargs)
    except httpx.ConnectError as exc:
        raise RuntimeError(
            f"No hay conexión con Apolo en {base}: arranca el servidor "
            "(uvicorn apolo.api.main:app --port 8000)"
        ) from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise _reject(response.status_code, detail)
    return response


def _reject(status: int, detail) -> RuntimeError:
    """Error de rechazo — fuente única del texto. Un job fallido lo reusa: para el agente
    un ContractError diferido se ve IGUAL que el 400 de hoy."""
    return RuntimeError(f"Apolo rechazó la operación ({status}): {detail}")


def _submit_and_wait(method: str, path: str, body: dict, params: dict | None = None):
    """Envía una mutación como JOB y la espera (V6.5e) → (payload, job_id).

    El camino seguro NO puede ser opt-in: el agente no sabe cuánto tardará un regenerate, así
    que los lotes, run_command, edit_command y set_variable SIEMPRE encolan. Devuelve:
      - (payload, None) si el job terminó dentro del presupuesto → la tool responde
        EXACTAMENTE lo de hoy;
      - (None, job_id) si no llegó → RECIBO, no error (el resultado no se pierde, se
        difiere: sigue en el servidor esperando a get_job).
    `estado=error` → RuntimeError con el detail (UX idéntica al 400 actual).
    """
    p = {**(params or {}), "async": "true"}
    response = _api(method, path, params=p, json=body)
    if response.status_code != 202:  # servidor sin jobs (no debería): payload directo
        return response.json(), None
    job_id = response.json()["job_id"]
    deadline = time.monotonic() + APOLO_MCP_WAIT_S
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, job_id
        job = _api(
            "GET", f"/api/jobs/{job_id}", params={"wait_s": min(_JOB_POLL_S, remaining)}
        ).json()
        if job["estado"] == "ok":
            return job["resultado"], None
        if job["estado"] == "error":
            raise _reject(job.get("http_status") or 400, job.get("error"))


def _mutacion(method: str, path: str, body: dict, detail: str, params: dict | None = None) -> str:
    """Una mutación por JOB: el brief de la vía síncrona si termina a tiempo, o el RECIBO."""
    payload, job_id = _submit_and_wait(method, path, body, params)
    if job_id:
        return _job_receipt(job_id)
    return json.dumps(_job_result(payload, detail), ensure_ascii=False)


# ----------------------------------------------------------------- consulta
globals().update(consulta.registrar(mcp, lambda *a, **k: _api(*a, **k)))


# ----------------------------------------------------------------- modelado
@mcp.tool()
def run_command(type: str, params: dict, detail: str = "diff") -> str:
    """Ejecuta un comando CAD (ver get_command_schemas). Los campos numéricos
    aceptan '=expresión' con variables del proyecto. `detail`: "diff" (def.) devuelve
    solo los sólidos nuevos + `total_solidos`; "full" toda la escena; "summary" solo
    id/nombre de lo nuevo y `comandos` (el id del comando; con más de 40 sólidos, "diff" y
    "summary" resumen `por_comando`). El bloque
    `variables` solo aparece si la operación tocó alguna (o detail="full"), y sólo con las tocadas
    y las que dependen de ellas (`variables_omitidas` cuenta el resto); usa get_scene para
    verlas siempre. Si tarda, recibes un RECIBO {"job": id}: recógelo con get_job(id) y NO
    reenvíes el comando."""
    return _mutacion("POST", "/api/commands", {"type": type, "params": params}, detail)


@mcp.tool()
def run_batch(actions: list[dict], detail: str = "diff", expect: list[dict] | None = None) -> str:
    """Ejecuta un lote ordenado de comandos [{type, params}, …]. Usa '$k' en los
    campos de id de feature para referenciar el sólido creado por la k-ésima
    acción del lote. `detail`: "diff" (def.) devuelve solo los sólidos creados por el
    lote + `total_solidos`; "full" toda la escena; "summary" solo id/nombre y `comandos`: el id
    de comando de cada acción EN ORDEN (`$k` = `comandos[k-1]`, también de lo que no crea
    sólidos: add_device, add_wire, fasten). Un `fasten` por conjuntos suma `uniones_expandidas`
    (cuántas uniones declaró cada uno).
    `expect` (CONTRATO, V6.5b) = lista de ASERCIONES estilo verify (distancia/volumen/bbox/
    sin_interferencia/existe) que DEBEN cumplirse tras el lote; si alguna falla, el lote se
    revierte POR COMPLETO (el documento queda intacto, sin escombro) y el error lista lo
    fallido (medido vs esperado). Los `$k` valen también en las aserciones (referencian lo
    recién creado). EN POSE (V6.8-C): `distancia`/`sin_interferencia` aceptan `joint_values`
    {junta: valor} por aserción — «este lote no puede romper ninguna pose declarada» (costo ≈
    un check_interference posado por pose distinta). Muta con contrato cuando el resultado deba
    cumplir una condición y ahórrate el ciclo mutar→leer→verificar→undo.
    El lote se ejecuta como JOB: si tarda más que el presupuesto de espera, en vez de un error
    de timeout recibes un RECIBO {"job": id} y lo recoges con get_job(id) — el resultado nunca
    se pierde, solo se difiere. NO reenvíes el lote al recibir un recibo (lo duplicarías)."""
    body: dict = {"actions": actions, **({"expect": expect} if expect else {})}
    return _mutacion("POST", "/api/commands/batch", body, detail)


@mcp.tool()
def edit_command(command_id: str, params: dict, merge: bool = True, detail: str = "diff") -> str:
    """Edita los parámetros de un comando pasado y regenera (edición paramétrica del
    historial). Por defecto hace PATCH (`merge=True`): combina con los params actuales,
    así que basta enviar los campos a cambiar. Merge SUPERFICIAL: un sub-objeto
    (position, rotation) se reemplaza entero. `merge=False` reemplaza todos los params
    (los omitidos vuelven a su default). `detail` como en run_command. Si tarda, recibes un
    RECIBO {"job": id}: recógelo con get_job(id) y NO reenvíes la edición."""
    return _mutacion("PUT", f"/api/commands/{command_id}", {"params": params}, detail,
                     params={"merge": str(merge).lower()})


@mcp.tool()
def edit_batch(
    edits: list[dict], merge: bool = True, detail: str = "diff", expect: list[dict] | None = None
) -> str:
    """Edita VARIOS comandos en UN lote ATÓMICO: un solo regenerate y un solo paso de
    undo (frente a N round-trips + N regenerates de llamar edit_command en bucle). Úsalo
    al reparametrizar muchas piezas a la vez. edits = [{"command_id": "c38", "params":
    {...}}, …]. PATCH por defecto (merge=True, superficial: un sub-objeto position/rotation
    se reemplaza entero); merge=False reemplaza todos los params. Si una edición falla,
    revierte TODO el lote. `expect` (CONTRATO, V6.5b) = aserciones estilo verify que deben
    cumplirse tras el lote; si alguna falla, se revierte TODO (doc intacto) — úsalo para
    reparametrizar con garantía (p. ej. tras encoger, `sin_interferencia`; con `joint_values`
    por aserción, V6.8-C, el contrato protege también las POSES del mecanismo). `detail` como en
    run_command (y `variables` solo aparece si el lote tocó alguna).
    Como run_batch, se ejecuta como JOB: si tarda, devuelve un RECIBO {"job": id} en vez de un
    error de timeout → recógelo con get_job(id) y NO reenvíes el lote."""
    body: dict = {"edits": edits}
    if expect:
        body["expect"] = expect
    return _mutacion("PATCH", "/api/commands/batch", body, detail,
                     params={"merge": str(merge).lower()})


@mcp.tool()
def get_job(job_id: str, detail: str = "diff", wait_s: float = 20, path: str | None = None) -> str:
    """Recoge el resultado de una mutación que devolvió un RECIBO {"job": id} (run_command,
    edit_command, set_variable, run_batch, edit_batch o remove_commands tardaron más que la
    espera; también calc_report, assembly_manual, drawing_set y drawing: guarda el archivo en su
    `path` o en `path`; y las lecturas delivery_check, check_interference y engineering_check:
    lo mismo que la tool).
    Espera hasta `wait_s` segundos (long-poll: responde en cuanto el job termina) y
    devuelve lo MISMO que habría devuelto la tool (sólidos + `contrato`), o
    `{"estado": "corriendo"}` si aún no acaba — vuelve a llamar. El de publication_gate llega
    RESUMIDO como la tool (`detail="full"`: todos los ítems). El resultado queda CACHEADO:
    re-preguntar es SIEMPRE seguro (no re-ejecuta nada). Si falló (p. ej. contrato incumplido)
    da el mismo error que daría en directo, y el documento quedó intacto.
    Job desconocido (404) = el servidor se reinició o el job ya se desalojó: la mutación PUDO
    haber aplicado (el autosave lo habría guardado) → verifícalo con get_scene antes de nada.
    NUNCA la reintentes a ciegas: la duplicarías."""
    job = _api("GET", f"/api/jobs/{job_id}", params={"wait_s": wait_s}).json()
    if job["estado"] == "error":
        raise _reject(job.get("http_status") or 400, job.get("error"))
    if job["estado"] != "ok":
        return _job_receipt(job_id, job["estado"])
    if "archivo" in (job.get("resultado") or {}):
        return entregable.recoger(_api, job_id, job["resultado"], path)
    lectura = validacion.de_job(job)  # delivery_check, check_interference, engineering_check
    if lectura is not None:
        return json.dumps({**lectura, "job": job_id}, ensure_ascii=False)
    puerta = calidad.de_job(job.get("resultado") or {}, detail)
    if puerta is not None:
        return json.dumps({**puerta, "job": job_id}, ensure_ascii=False)
    return json.dumps({**_job_result(job.get("resultado") or {}, detail), "job": job_id},
                      ensure_ascii=False)


def _paso(path: str, clave: str, detail: str) -> str:
    if detail == "full":
        return json.dumps(brief_paso(_api("POST", path).json(), clave), ensure_ascii=False)
    return json.dumps(_api("POST", path, params={"detail": "diff"}).json(), ensure_ascii=False)


@mcp.tool()
def undo(detail: str = "diff") -> str:
    """Deshace la última operación. `detail`: "diff" (def.) responde lo que cambió el paso
    —`deshecho` (qué revirtió), comandos quitados/restaurados/editados, piezas y uniones nuevas o
    borradas, `variables` cambiadas y `total_solidos`—; "full" lista toda la escena."""
    return _paso("/api/undo", "deshecho", detail)


@mcp.tool()
def set_variable(name: str, expression: str) -> str:
    """Define o actualiza una variable de proyecto (p. ej. L = 2000). Cambiarla
    regenera todo lo que la usa. Devuelve sólo esa variable y las que dependen de ellas (con
    su valor nuevo) y `avisos_expresion` si la expresión casi seguro dice otra cosa (sin/cos/tan
    toman GRADOS: no conviertas con pi/180). Si tarda, recibes un RECIBO {"job": id}: recógelo con
    get_job(id) y NO la reenvíes."""
    return _mutacion("POST", "/api/variables", {"name": name, "expression": expression}, "diff")


# -------------------------------------------------------------- validación
globals().update(validacion.registrar(
    mcp, lambda *a, **k: _api(*a, **k), lambda *a, **k: _submit_and_wait(*a, **k)))


# ---------------------------------------------------------------- proyectos
globals().update(proyectos.registrar(mcp, lambda *a, **k: _api(*a, **k)))


# ---------------------------------------------------------- lectura/introspección
globals().update(introspeccion.registrar(
    mcp, lambda *a, **k: _api(*a, **k), lambda *a, **k: _paso(*a, **k),
    lambda *a, **k: _submit_and_wait(*a, **k)))


# ----------------------------------------------------- topología / selectores
globals().update(topologia.registrar(mcp, lambda *a, **k: _api(*a, **k)))


# ----------------------------------------------------- despiece de fabricación
globals().update(fabricacion.registrar(
    mcp, lambda *a, **k: _api(*a, **k), lambda *a, **k: _submit_and_wait(*a, **k)))


# ------------------------------------------------------------------ visibilidad
globals().update(visibilidad.registrar(mcp, lambda *a, **k: _api(*a, **k)))


# ------------------------------------------------------------------ expresiones
globals().update(calculo.registrar(mcp, lambda *a, **k: _api(*a, **k)))


# Tools sin bloque propio aquí, a ESTE `mcp` (`__main__` con `-m`) y a su `_api`/`_mutacion`.
mcp_electrico.registrar(mcp, lambda *a, **k: _api(*a, **k))  # tablero eléctrico (V8.1 D8)
simulacion.registrar(mcp, lambda *a, **k: _api(*a, **k), lambda *a, **k: _submit_and_wait(*a, **k))
cosim.registrar(mcp, lambda *a, **k: _api(*a, **k), lambda *a, **k: _submit_and_wait(*a, **k))
estructura.registrar(mcp, lambda *a, **k: _api(*a, **k))  # declare_structure (uniones-en-lote D3)
cirugia.registrar(mcp, lambda *a, **k: _mutacion(*a, **k))  # remove_commands (cirugia-liviana)
calidad.registrar(mcp, lambda *a, **k: _submit_and_wait(*a, **k), lambda *a, **k: _api(*a, **k))
notas.registrar(mcp, lambda *a, **k: _api(*a, **k))  # memoria del agente (F6 de la puerta)
extensiones.registrar_tools(mcp, globals())  # las de extensiones, al final (nucleo-abierto A3)


def main() -> None:
    """Punto de entrada del script `apolo-mcp` (y de `python -m apolo.mcp_server`)."""
    mcp.run()


if __name__ == "__main__":
    main()
