"""Candado por proyecto entre procesos de la API (D4 del plan
`docs/plans/varias-maquinas-a-la-vez.md`).

Con varios procesos sobre la misma SQLite, «el último que guarda gana» borraría en silencio el
trabajo del otro. Cada proceso toma el candado del proyecto que abre (tabla `project_leases`,
SQL en `ProjectStore`), lo suelta al cambiar de proyecto y al apagar, y late cada `LATIDO_S`
desde un hilo daemon. Abrir uno ajeno y vivo da 409; el autosave no escribe si lo perdió.

- **Dueño** = `host:pid:puerto`, fijado UNA vez por proceso: el mismo proceso reabre sin 409
  (la suite crea muchos almacenes y TestClient en un solo proceso).
- **Dueño muerto**: latido de ≥ 30 s, o (misma máquina) su pid ya no existe. Lo segundo es lo
  que deja arrancar al `:8000` con `--reload`: el reloader mata el worker sin su shutdown y el
  nuevo, con otro pid, encontraría el candado del muerto con latido fresco.
- Un almacén SIN candados (los falsos de los tests, sin `tomar_candado`) no los usa: todo es
  no-op y el autosave escribe como siempre.

No importa `session` (la usa `session` en el arranque): quien llama pasa el almacén.
"""

from __future__ import annotations

import os
import socket
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from apolo import identidad

from .errorlog import log_error

#: cada cuánto late el proceso (el candado vence a los `CANDADO_VENCE_S` = 30 s del almacén)
LATIDO_S = 10.0

_DUENO: tuple[int, str] | None = None


def dueno() -> str:
    """`host:pid:puerto` de este proceso, calculado una vez (por pid: un fork recalcula)."""
    global _DUENO
    pid = os.getpid()
    if _DUENO is None or _DUENO[0] != pid:
        puerto = identidad.puerto()
        _DUENO = (pid, f"{socket.gethostname()}:{pid}:{puerto if puerto is not None else '?'}")
    return _DUENO[1]


def _partes(otro: str) -> tuple[str, str, str]:
    """(host, pid, puerto) de un dueño `host:pid:puerto` (el host podría traer `:`)."""
    partes = otro.rsplit(":", 2)
    return (partes[0], partes[1], partes[2]) if len(partes) == 3 else (otro, "?", "?")


def mensaje_ocupado(project_id: int, otro: str) -> str:
    """«El proyecto 74 está abierto en el puerto 8102 (pid 1234)»."""
    _host, pid, puerto = _partes(otro)
    donde = f"en el puerto {puerto}" if puerto != "?" else "en otro proceso"
    return f"El proyecto {project_id} está abierto {donde} (pid {pid})"


def mensaje_perdido(project_id: int, otro: str) -> str:
    return (f"No se guardó: este proceso perdió el candado del proyecto {project_id}. "
            f"{mensaje_ocupado(project_id, otro)}; ábrelo de nuevo cuando ese proceso lo suelte.")


class ProyectoOcupado(HTTPException):
    """409: el proyecto lo tiene abierto otro proceso vivo."""

    def __init__(self, project_id: int, otro: str):
        super().__init__(status_code=409, detail=mensaje_ocupado(project_id, otro))
        self.otro = otro


def _con_candados(store) -> bool:
    return store is not None and hasattr(store, "tomar_candado")


def pid_vivo(pid: int) -> bool:
    """¿Existe el proceso `pid` en ESTA máquina? Ante la duda, sí (no se roba un candado)."""
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":  # os.kill(pid, 0) en Windows MANDA un CTRL_C: nunca
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        k32.CloseHandle.argtypes = (wintypes.HANDLE,)
        h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5  # ERROR_ACCESS_DENIED: existe, es de otro
        try:
            codigo = wintypes.DWORD()
            if not k32.GetExitCodeProcess(h, ctypes.byref(codigo)):
                return True
            return codigo.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _dueno_muerto(otro: str) -> bool:
    host, pid, _puerto = _partes(otro)
    if host != socket.gethostname():
        return False
    try:
        return not pid_vivo(int(pid))
    except ValueError:
        return False


def tomar(store, project_id: int) -> None:
    """Toma el candado de `project_id` para este proceso o lanza `ProyectoOcupado` (409)."""
    if not _con_candados(store):
        return
    yo = dueno()
    for _ in range(3):  # carrera con otro que lo toma o lo suelta entre medio: se reintenta
        otro = store.tomar_candado(project_id, yo)
        if otro is None:
            return
        if not _dueno_muerto(otro):
            raise ProyectoOcupado(project_id, otro)
        if store.robar_candado(project_id, yo, otro):
            log_error("backend.candado", f"Candado del proyecto {project_id} tomado de un "
                      f"proceso muerto ({otro})")
            return
    raise ProyectoOcupado(project_id, otro)


def soltar(store, project_id: int | None) -> None:
    """Suelta el candado si es de este proceso. Best-effort: si falla, vence solo."""
    if project_id is None or not _con_candados(store):
        return
    try:
        store.soltar_candado(project_id, dueno())
    except Exception as exc:  # noqa: BLE001 — soltar nunca rompe un cambio de proyecto
        log_error("backend.candado", f"No se pudo soltar el candado del proyecto "
                  f"{project_id}: {exc!r}")


def asegurar(store, project_id: int) -> str | None:
    """Antes de escribir (autosave): None si el candado sigue (o vuelve a ser) de este
    proceso; si no, el dueño ajeno y el autosave NO escribe."""
    if not _con_candados(store):
        return None
    return store.asegurar_candado(project_id, dueno())


def ajeno_vivo(store, project_id: int) -> str | None:
    """El dueño de un candado de OTRO proceso vivo, o None (borrar un proyecto lo consulta)."""
    if not _con_candados(store):
        return None
    otro = store.candado_vivo_ajeno(project_id, dueno())
    return None if otro is None or _dueno_muerto(otro) else otro


@contextmanager
def cambio_a(store, project_id: int, actual: int | None) -> Iterator[None]:
    """Dentro de `_project_switch`, alrededor de cargar y swapear `project_id`: toma su candado
    ANTES (409 sin tocar nada); si el bloque lanza lo suelta (salvo que fuera el ya abierto);
    si sale bien suelta el de `actual`, el proyecto que se deja."""
    tomar(store, project_id)
    try:
        yield
    except BaseException:
        if project_id != actual:
            soltar(store, project_id)
        raise
    if actual != project_id:
        soltar(store, actual)


def tras_crear(store, nuevo: int | None, actual: int | None) -> None:
    """Un proyecto recién creado (id nuevo: nadie más lo tiene) toma su candado y suelta el
    que se deja."""
    if nuevo is not None:
        tomar(store, nuevo)
    if actual != nuevo:
        soltar(store, actual)


# ---------------------------------------------------------------------------- latido
_parar = threading.Event()
_hilo: threading.Thread | None = None
_perdido: int | None = None  # último proyecto cuyo latido falló (se anota una vez)


def latir(store, project_id: int | None) -> bool | None:
    """Un latido del proyecto activo. None si no hay nada que latir; False si el candado ya
    no es de este proceso (no lo re-toma: lo decide el próximo autosave)."""
    global _perdido
    if project_id is None or not _con_candados(store):
        return None
    try:
        ok = store.latir_candado(project_id, dueno())
    except Exception as exc:  # noqa: BLE001 — un latido fallido se repite en LATIDO_S
        log_error("backend.candado", f"Latido del proyecto {project_id}: {exc!r}")
        return False
    if ok:
        _perdido = None
    elif _perdido != project_id:
        _perdido = project_id
        log_error("backend.candado", f"El candado del proyecto {project_id} ya no es de este "
                  "proceso: el autosave no escribirá")
    return ok


def iniciar_latido(actual: Callable[[], tuple], intervalo: float = LATIDO_S) -> threading.Thread:
    """Hilo daemon que late cada `intervalo` el proyecto que da `actual()` → (store, id).
    NO toma `STATE_LOCK`: un regenerate de 40 s no puede dejar vencer el candado."""
    global _hilo
    if _hilo is not None and _hilo.is_alive():
        return _hilo
    _parar.clear()

    def bucle() -> None:
        while not _parar.wait(intervalo):
            latir(*actual())

    _hilo = threading.Thread(target=bucle, name="apolo-candado-latido", daemon=True)
    _hilo.start()
    return _hilo


def detener_latido() -> None:
    global _hilo
    _parar.set()
    if _hilo is not None:
        _hilo.join(timeout=2)
    _hilo = None
