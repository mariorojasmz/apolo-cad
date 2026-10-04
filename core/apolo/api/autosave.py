"""Autosave de la API: debounce, flush durable y cambio de proyecto atómico.

Movido tal cual desde `main.py` (F5b del plan `docs/plans/partir-api-main.md`): los MISMOS
objetos lock y el programador sin tocar. `main` re-exporta por IDENTIDAD lo que usan sus
endpoints y los tests (`_autosave`, `_flush_autosave`, `_autosave_sched`, `_flush_lock`,
`_project_switch`). Los tiempos (`_AUTOSAVE_DEBOUNCE`, `_AUTOSAVE_CEILING`) NO se
re-exportan: el programador los lee de ESTE módulo, así que un test que quiera cambiarlos
parchea `apolo.api.autosave` (en `main` el parche sería un no-op silencioso).

Orden ÚNICO de locks: `_flush_lock → STATE_LOCK`, jamás al revés.
"""

from __future__ import annotations

import contextlib
import os
import threading
import time

from apolo.state import STATE_LOCK

from .errorlog import log_error
from .session import S
from .ws import WS

# backoff del autosave: reintentos con espera TOTAL ≤0.6 s (solo se paga en el caso
# EXCEPCIONAL de fallo — el camino feliz guarda al primer intento).
_AUTOSAVE_RETRIES = (0.0, 0.1, 0.5)

# Debounce del autosave (V6.2d): la escritura deja de ser inline tras cada mutación. Cada
# mutación marca "sucio" y (re)programa un flush ÚNICO: 500 ms desde la última mutación, con
# TECHO de 3 s desde la primera pendiente (una ráfaga de edición directa no puede posponer el
# guardado para siempre). El flush toma bytes + pack BAJO STATE_LOCK y escribe SQLite FUERA.
_AUTOSAVE_DEBOUNCE = 0.5   # s desde la última mutación
_AUTOSAVE_CEILING = 3.0    # s máx. desde la primera pendiente
# (project_id, sig) de la última caché de geometría escrita → no re-empacar sin cambios.
_GEOM_MARK: tuple[int, str] | None = None


# Serializa los flushes REALES entre sí (Timer + forzoso). ORDEN GLOBAL DE LOCKS (V6.2e
# Fix 1): _flush_lock SIEMPRE se adquiere ANTES que STATE_LOCK, nunca al revés → sin deadlock
# entre un flush del Timer (que quiere STATE_LOCK) y un cambio de proyecto (que quiere
# flushear). Sostenerlo durante TODOS los reintentos evita que un flush con bytes VIEJOS pise
# a otro con bytes NUEVOS (los reintentos duermen hasta 0.6 s > el debounce de 0.5 s).
_flush_lock = threading.Lock()


def _flush_body() -> None:
    """Cuerpo del flush del autosave. Asume ``_flush_lock`` sostenido. (a) BAJO STATE_LOCK:
    captura STORE/PROJECT_ID + serializa el .apolo + empaca la caché — TODO atómico con el
    doc (un cambio de proyecto swapea DOC y PROJECT_ID bajo el MISMO lock, así que jamás se
    escribe el proyecto A con bytes de B). (b) escribe SQLite con reintentos (durabilidad
    V6.1). Si el caller YA sostiene STATE_LOCK (camino de switch), la escritura ocurre bajo él
    — aceptable, es raro. Un fallo de SERIALIZACIÓN también enciende AUTOSAVE_ERROR + WS (antes
    moría en el excepthook del Timer con `dirty` ya limpio = contrato V6.1 «el cliente se
    entera» roto para fallos de serialización)."""
    global _GEOM_MARK
    with STATE_LOCK:  # snapshot ATÓMICO con el doc (STORE/PROJECT_ID/bytes de la MISMA foto)
        store, project_id = S.store, S.project_id
        if store is None or project_id is None:
            return
        try:
            name, pieces, data = S.doc.name, len(S.doc.scene), S.doc.to_apolo_bytes()
            sig = S.doc._regen_sigs[-1] if S.doc._regen_sigs else None
            geom_blob = None
            if (sig is not None and os.environ.get("APOLO_GEOM_CACHE") != "0"
                    and _GEOM_MARK != (project_id, sig)):
                from apolo.doc.geomcache import pack

                geom_blob = pack(S.doc)
        except Exception as exc:  # noqa: BLE001 — fallo de SERIALIZACIÓN: el cliente SE ENTERA
            S.autosave_error = repr(exc)
            log_error("backend.autosave", repr(exc))
            WS.notify_changed({"type": "autosave_failed", "error": S.autosave_error})
            return
    last: Exception | None = None
    for delay in _AUTOSAVE_RETRIES:
        if delay:
            time.sleep(delay)
        try:
            store.save_raw(project_id, name, pieces, data)  # durabilidad: reintentado
        except Exception as exc:  # noqa: BLE001 — el autosave nunca rompe la operación
            last = exc
            continue
        S.autosave_error = None
        if geom_blob is not None:  # caché de geometría: BEST-EFFORT (no re-guarda el .apolo si falla)
            try:
                store.save_geom_cache(project_id, sig, geom_blob)
                _GEOM_MARK = (project_id, sig)
            except Exception as exc2:  # noqa: BLE001 — perderla solo cuesta un replay
                log_error("backend.geomcache", repr(exc2))
        return
    S.autosave_error = repr(last)
    log_error("backend.autosave", repr(last))
    WS.notify_changed({"type": "autosave_failed", "error": S.autosave_error})


class _AutosaveScheduler:
    """Programador del flush con debounce (V6.2d/e). ``self._lock`` es un LEAF que solo
    protege el estado del programador; los flushes REALES se serializan con ``_flush_lock``
    (orden global _flush_lock→STATE_LOCK). ``pending()`` = sucio O flush en vuelo."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._first: float | None = None   # monotonic de la primera mutación pendiente
        self._dirty = False
        self._flushing = False              # hay un flush REAL en vuelo (para pending())

    def schedule(self) -> None:
        # sin almacén/proyecto no hay adónde guardar (la mayoría de tests) → no armar Timer
        if S.store is None or S.project_id is None:
            return
        with self._lock:
            self._dirty = True
            now = time.monotonic()
            if self._first is None:
                self._first = now
            delay = min(_AUTOSAVE_DEBOUNCE, max(0.0, self._first + _AUTOSAVE_CEILING - now))
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(delay, self._fire)
            self._timer.daemon = True
            self._timer.start()

    def _fire(self) -> None:
        with self._lock:
            self._timer = None
            self._first = None
            if not self._dirty:
                return
        # V6.3 Fase 0: NO se limpia `dirty` aquí. El clear ocurre DENTRO de _flush_lock (en
        # _run) para que un _project_switch que gane _flush_lock primero vea dirty=True vía
        # take_pending y persista el doc VIEJO antes del swap — si se adelantara al lock, esas
        # últimas mutaciones de A se evaporarían (lost update; pending() parpadeaba a False).
        self._run()

    def _run(self) -> None:
        """Un flush REAL bajo _flush_lock (marca _flushing para pending()). Limpia `dirty`
        DENTRO del lock (V6.3 Fase 0): el clear no puede adelantarse a que otro flush —el del
        switch— consuma el estado pendiente. Sigue flusheando incondicionalmente (el switch,
        que ya consumió dirty vía take_pending, lo dejó en False → aquí es una reescritura del
        proyecto ACTUAL, correcta e inocua; nunca un lost update)."""
        with _flush_lock:
            with self._lock:
                self._dirty = False
                self._flushing = True
            try:
                _flush_body()
            finally:
                with self._lock:
                    self._flushing = False

    def flush(self, *, force: bool = False) -> None:
        """Flush forzoso SÍNCRONO. Adquiere _flush_lock SIEMPRE (aunque no esté sucio) →
        ESPERA a un flush del Timer en vuelo antes de volver. Cancela el Timer pendiente. El
        clear de `dirty` lo hace _run bajo _flush_lock (V6.3 Fase 0), no aquí."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            do_it = self._dirty or force
            self._first = None
        if do_it:
            self._run()
        else:
            with _flush_lock:  # nada que guardar, pero espera al Timer en vuelo (disco al día)
                pass

    def clear(self) -> None:
        """Limpia el estado pendiente SIN guardar (teardown de tests: sin Timers huérfanos)."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._dirty = False
            self._first = None

    def take_pending(self) -> bool:
        """Lee y LIMPIA el estado pendiente, devolviendo si HABÍA cambios sin guardar. Lo
        llama el switch de proyecto bajo _flush_lock+STATE_LOCK: si True, el switch hace un
        _flush_body ANTES del swap (ninguna mutación puede colarse — la mutación toma
        STATE_LOCK para poner dirty). Evita escribir el proyecto viejo si no tenía cambios."""
        with self._lock:
            was = self._dirty
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
            self._dirty = False
            self._first = None
            return was

    def pending(self) -> bool:
        with self._lock:
            return self._dirty or self._flushing

    def cancel(self) -> None:
        self.clear()


_autosave_sched = _AutosaveScheduler()


def _autosave() -> None:
    """Programa el autoguardado con debounce (V6.2d): marca sucio y arma el flush único. Ya
    NO escribe inline (una ráfaga de 20 ediciones = 1 escritura a disco, no 20)."""
    _autosave_sched.schedule()


def _flush_autosave(*, force: bool = False) -> None:
    """Fuerza el flush pendiente AHORA (shutdown, restore, tests). Espera al Timer en vuelo."""
    _autosave_sched.flush(force=force)


@contextlib.contextmanager
def _project_switch():
    """Cambio de proyecto ATÓMICO (V6.2e Fix 1): persiste el doc ACTUAL (si tenía cambios
    pendientes) y cede el control con STATE_LOCK sostenido para el swap → sin ventana donde
    una mutación al doc VIEJO se evapore ni donde el proyecto A se pise con bytes de B. Orden
    global de locks: _flush_lock → STATE_LOCK (el switch adquiere _flush_lock ANTES; jamás al
    revés → sin deadlock con el flush del Timer)."""
    with _flush_lock:
        with STATE_LOCK:
            if _autosave_sched.take_pending():
                _flush_body()  # persiste el doc ACTUAL (PROJECT_ID aún es el viejo)
            yield              # el endpoint swapea DOC/PROJECT_ID aquí, bajo ambos locks
