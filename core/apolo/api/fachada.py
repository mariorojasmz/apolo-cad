"""La fachada del documento para las rutas de una extensión (plan
nucleo-abierto-extensiones-privadas, F1d): leer y mutar el documento ACTIVO con la coreografía de
la API sin importar `apolo.state` ni los internos de `apolo.api`. Se importa por la superficie
estable (`from apolo.extensiones_api import mutar_documento, …`); los nombres de aquí son
contrato (`extensiones_api.SUPERFICIE`).

Lo que hace por la extensión, igual que una ruta del núcleo:

- `leer_documento(fn)`: `fn(doc)` bajo `STATE_LOCK` y devuelve lo que dé. `fn` sólo EXTRAE
  (datos puros, sin el shape vivo: fuera del lock OCCT no es seguro) y no muta.
- `mutar_documento(fn, asincrono=, tipo=, armar=)`: `fn(doc)` muta por las puertas de
  `Document` (`execute`, `edit`, `execute_many`, `edit_many`, `remove_commands`, `undo`…: cada
  una deja su undo) dentro del embudo de toda mutación (`common._state_or_error`): guardia del
  documento (`X-Apolo-Documento`) y sólo lectura → 409 sin aplicar nada; `CommandError` o
  `DocumentError` → 400 con su texto; autosave; la respuesta de siempre (escena, o `armar(doc)`
  liviano, más `affected_command_ids` = lo que devuelva `fn`); aviso por WebSocket DESPUÉS de
  armarla. Con `asincrono=True` va como job (202 + recibo, `GET /api/jobs/{id}`), con la guardia
  de proyecto y de documento de `_sync_or_job`.
- `leer_ext(nombre)` / `poner_ext(nombre, datos)`: los datos de la extensión en el manifest (clave
  `ext`, `doc/ext_manifest.py`). Escribir pasa la guardia y el sólo lectura, valida que `nombre`
  sea una extensión CARGADA, guarda (autosave) y avisa por WebSocket; no deja undo (metadato).
- `proyecto_activo()`: el id del proyecto abierto (None sin almacén).
- `entregable_documento(extraer, componer, tipo=, asincrono=)`: un ARCHIVO de la extensión con
  las dos fases de la API (plan pedidos-de-extensiones, D6): `extraer(doc)` bajo `STATE_LOCK`
  (sólo datos puros, como `leer_documento`) y `componer(datos) -> (bytes, media_type, nombre)`
  FUERA de todo lock, donde va lo lento (PDF, ZIP, DWG). Sin `asincrono`, la `Response` con el
  archivo y su `Content-Disposition`; con él, 202 + recibo en la cola de entregables del núcleo
  (`GET /api/jobs/{id}` → `{archivo, bytes, tipo, nombre}`; el archivo se baja de `archivo`) y,
  si mientras espera se abrió otro proyecto, 409 sin generar. `CommandError`/`DocumentError` de
  cualquiera de las dos fases → 400 con su texto; una `HTTPException` propia pasa tal cual. Del
  lado MCP, la tool de la extensión lo pide con `pedir_entregable` y `get_job` lo guarda.

Una ruta de extensión que necesite otra cosa del documento la pide aquí (subir el contrato), no
la importa de `apolo.api`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Response

from apolo.commands import CommandError
from apolo.doc import DocumentError, ext_manifest
from apolo.state import STATE_LOCK

from .common import (
    WS,
    _autosave,
    _job_entregable,
    _mismo_proyecto,
    _state_or_error,
    _sync_or_job,
    _verificar_documento,
)
from .session import S


def leer_documento(fn: Callable[[Any], Any]):
    """`fn(doc)` sobre el documento activo, bajo `STATE_LOCK`; un error de dominio → 400."""
    with STATE_LOCK:
        try:
            return fn(S.doc)
        except (CommandError, DocumentError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


def mutar_documento(fn: Callable[[Any], Any], *, asincrono: bool = False, tipo: str = "extension",
                    armar: Callable[[Any], dict] | None = None):
    """`fn(doc)` como toda mutación de la API (ver el docstring del módulo). Devuelve el payload
    (dict) o, con `asincrono`, la respuesta 202 con el recibo del job."""
    liviano = None if armar is None else (lambda: armar(S.doc))

    def trabajo():
        return _state_or_error(lambda: fn(S.doc), armar=liviano)

    return _sync_or_job(tipo, trabajo, asincrono)


def leer_ext(nombre: str) -> dict | None:
    """Una copia de los datos de la extensión `nombre` en el documento activo (None si no hay)."""
    with STATE_LOCK:
        return ext_manifest.leer(S.doc, nombre)


def poner_ext(nombre: str, datos) -> dict | None:
    """Reemplaza los datos de la extensión `nombre` (None los borra) y devuelve lo que quedó."""
    from apolo import extensiones

    with STATE_LOCK:
        _verificar_documento()  # mutación fuera de _state_or_error: guardia a mano
        try:
            out = ext_manifest.poner(S.doc, nombre, datos,
                                     conocidas=[e.nombre for e in extensiones.cargadas()])
        except DocumentError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        _autosave()
    WS.notify_changed()
    return out


def proyecto_activo() -> int | None:
    with STATE_LOCK:
        return S.project_id


def entregable_documento(extraer: Callable[[Any], Any],
                         componer: Callable[[Any], tuple[bytes, str, str]], *, tipo: str,
                         asincrono: bool = False):
    """Un archivo de la extensión en dos fases (ver el docstring del módulo). Devuelve la
    `Response` con el archivo o, con `asincrono`, la 202 con el recibo del job."""

    def trabajo(proyecto) -> Response:
        with STATE_LOCK:
            _mismo_proyecto(proyecto)
            datos = _dominio(extraer, S.doc)
        data, media_type, nombre = _dominio(componer, datos)  # fuera de todo lock
        return Response(content=bytes(data), media_type=media_type,
                        headers={"Content-Disposition": f'attachment; filename="{_nombre(nombre)}"'})

    return _job_entregable(tipo, trabajo, asincrono)


def _dominio(fn: Callable[[Any], Any], arg):
    try:
        return fn(arg)
    except (CommandError, DocumentError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _nombre(nombre: str) -> str:
    """El nombre del archivo tal cual, si cabe en la cabecera; si no, es un error de la
    extensión (no se recorta en silencio: el recibo diría otro nombre que el pedido)."""
    if (not isinstance(nombre, str) or not nombre.strip() or '"' in nombre
            or any(ord(c) < 32 or ord(c) > 255 for c in nombre)):
        raise ValueError(f"entregable_documento: nombre de archivo inválido {nombre!r} "
                         "(texto no vacío, sin comillas ni saltos, en latin-1)")
    return nombre
