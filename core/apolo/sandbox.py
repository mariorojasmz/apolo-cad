"""Sandbox de ejecución de scripts build123d (IA Nivel 2).

El código corre en un PROCESO HIJO de vida larga (``sandbox_worker.py``, plan
sandbox-caliente) que importa build123d una sola vez; el resultado vuelve como BRep binario
(STEP de respaldo). La frontera de seguridad principal del producto es la revisión humana:
el usuario ve el código en la tarjeta de acción antes de aceptar. El sandbox añade
aislamiento de fallos y límite de tiempo: un timeout, un crash o CUALQUIER error del script
matan al worker y el siguiente script levanta uno nuevo; se recicla también cada
``WORKER_MAX_SCRIPTS`` scripts. ``SCRIPT_TIMEOUT_S`` cuenta sólo la ejecución: el arranque
del worker tiene su propio límite y no rechaza un script.

Caché LRU por hash(código + TODAS las variables), con tope en BYTES: la regeneración del
documento no re-ejecuta scripts que no cambiaron, y cada acierto devuelve una forma NUEVA.

LOCK: ``SANDBOX_LOCK`` guarda el worker y la caché. El executor de ``run_script`` llega con
``STATE_LOCK`` tomado; ``POST /api/script/test`` llama sin él. Orden único
``STATE_LOCK → SANDBOX_LOCK``: este módulo jamás importa ``apolo.state``.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from collections import OrderedDict, deque
from pathlib import Path

from apolo.brep_io import wrap_topods
from apolo.sandbox_worker import read_frame, ultimas_lineas, write_frame

SCRIPT_TIMEOUT_S = 60
WORKER_START_TIMEOUT_S = 300
WORKER_MAX_SCRIPTS = 500
_CACHE_MAX_BYTES = 64 * 1024 * 1024
#: Sólo tests: el worker responde STEP en vez de BRep (prueba el respaldo de D3).
_FORZAR_STEP = False
_STDERR_LINEAS = 400

SANDBOX_LOCK = threading.Lock()
_cache: OrderedDict[str, tuple[bytes, bytes]] = OrderedDict()  # clave -> (etiqueta, blob)
_cache_bytes = 0


class ScriptError(Exception):
    pass


class _Caido(Exception):
    """El worker murió o cerró su salida en medio de un pedido (crash, ``os._exit``)."""


class _Worker:
    """Un proceso ``apolo.sandbox_worker`` con sus dos hilos lectores: el de la salida
    (frames → cola, para esperar con timeout: en Windows no hay ``select`` sobre pipes) y el
    que drena stderr a un buffer acotado (si nadie lo lee, el pipe se llena y el hijo se
    traba)."""

    def __init__(self) -> None:
        self._cwd = tempfile.mkdtemp(prefix="apolo_sandbox_")
        try:
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "apolo.sandbox_worker"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                cwd=self._cwd,
            )
        except OSError as exc:
            shutil.rmtree(self._cwd, ignore_errors=True)
            raise ScriptError(f"El sandbox no pudo arrancar:\n{exc}") from exc
        self.info: dict = {}
        self.scripts = 0
        self._salida: queue.Queue = queue.Queue()
        self._err: deque[str] = deque(maxlen=_STDERR_LINEAS)
        self._err_total = 0
        self._err_lock = threading.Lock()
        self._hilos = [
            threading.Thread(target=self._leer_salida, daemon=True, name="apolo-sandbox-salida"),
            threading.Thread(target=self._drenar_err, daemon=True, name="apolo-sandbox-stderr"),
        ]
        for hilo in self._hilos:
            hilo.start()

    def _leer_salida(self) -> None:
        try:
            while (cuerpo := read_frame(self.proc.stdout)) is not None:
                self._salida.put(cuerpo)
        except Exception:  # noqa: BLE001 — un pipe roto es un EOF
            pass
        self._salida.put(None)

    def _drenar_err(self) -> None:
        try:
            for linea in self.proc.stderr:
                with self._err_lock:
                    self._err.append(linea.decode("utf-8", "replace").rstrip())
                    self._err_total += 1
        except Exception:  # noqa: BLE001
            pass

    def _marca(self) -> int:
        with self._err_lock:
            return self._err_total

    def _err_desde(self, marca: int) -> str:
        with self._err_lock:
            nuevas = min(self._err_total - marca, len(self._err))
            return "\n".join(list(self._err)[len(self._err) - nuevas:])

    def vivo(self) -> bool:
        return self.proc.poll() is None

    def esperar_listo(self) -> None:
        try:
            cuerpo = self._salida.get(timeout=WORKER_START_TIMEOUT_S)
        except queue.Empty:
            raise ScriptError(f"El sandbox no arrancó en {WORKER_START_TIMEOUT_S}s") from None
        if cuerpo is None or cuerpo[:1] != b"R":
            raise ScriptError(f"El sandbox no pudo arrancar:\n{self.detalle_caida(0)}")
        self.info = json.loads(cuerpo[1:].decode("utf-8"))

    def pedir(self, cuerpo: bytes, timeout: float) -> bytes:
        """Manda un pedido y espera su respuesta. ``TimeoutError`` si no llega a tiempo;
        ``_Caido`` (con el detalle) si el worker murió."""
        marca = self._marca()
        try:
            write_frame(self.proc.stdin, cuerpo)
        except OSError:
            raise _Caido(self.detalle_caida(marca)) from None
        try:
            respuesta = self._salida.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError from None
        if respuesta is None:
            raise _Caido(self.detalle_caida(marca))
        return respuesta

    def detalle_caida(self, marca: int) -> str:
        """Lo que el worker dejó en stderr desde ``marca`` o, si nada, su código de salida."""
        try:
            rc = self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            rc = None
        self._hilos[1].join(timeout=5)  # stderr hasta su EOF: la traza llega tras la muerte
        return ultimas_lineas(self._err_desde(marca)) or f"código de salida {rc}"

    def matar(self) -> None:
        try:
            self.proc.kill()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        for hilo in self._hilos:
            hilo.join(timeout=5)
        for pipe in (self.proc.stdin, self.proc.stdout, self.proc.stderr):
            try:
                pipe.close()
            except Exception:  # noqa: BLE001
                pass
        shutil.rmtree(self._cwd, ignore_errors=True)


_worker: _Worker | None = None


def _worker_listo() -> _Worker:
    """El worker vivo, o uno nuevo (espera su «listo» hasta ``WORKER_START_TIMEOUT_S``).
    Bajo ``SANDBOX_LOCK``."""
    global _worker
    if _worker is not None and _worker.vivo():
        return _worker
    _retirar()
    nuevo = _Worker()
    try:
        nuevo.esperar_listo()
    except BaseException:
        nuevo.matar()
        raise
    _worker = nuevo
    return nuevo


def _retirar() -> None:
    global _worker
    if _worker is not None:
        _worker.matar()
        _worker = None


def _ejecutar(code: str, variables: dict) -> tuple[bytes, bytes]:
    """Corre el script en el worker: ``(etiqueta, blob)`` o ``ScriptError``. Bajo el lock."""
    worker = _worker_listo()
    pedido = json.dumps({"code": code, "vars": variables, "step": _FORZAR_STEP}, default=str)
    try:
        respuesta = worker.pedir(pedido.encode("utf-8"), SCRIPT_TIMEOUT_S)
    except TimeoutError:
        _retirar()
        raise ScriptError(f"El script superó el límite de {SCRIPT_TIMEOUT_S}s") from None
    except _Caido as exc:
        _retirar()
        raise ScriptError(f"El script falló:\n{exc}") from None
    etiqueta, blob = respuesta[:1], respuesta[1:]
    if etiqueta not in (b"B", b"S"):
        _retirar()  # tras CUALQUIER error del script: un global de build123d pudo quedar sucio
        if etiqueta == b"E":
            raise ScriptError(blob.decode("utf-8", "replace"))
        raise ScriptError(f"El sandbox respondió algo inesperado ({etiqueta!r})")
    worker.scripts += 1
    if worker.scripts >= WORKER_MAX_SCRIPTS:
        _retirar()  # acota la memoria de OCCT
    return etiqueta, blob


def _cache_key(code: str, variables: dict) -> str:
    payload = code + "\n#vars#" + json.dumps(variables, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _cache_drop(key: str) -> None:
    global _cache_bytes
    vieja = _cache.pop(key, None)
    if vieja is not None:
        _cache_bytes -= len(vieja[1])


def _cache_put(key: str, entrada: tuple[bytes, bytes]) -> None:
    global _cache_bytes
    _cache_drop(key)
    _cache[key] = entrada
    _cache_bytes += len(entrada[1])
    while _cache and _cache_bytes > _CACHE_MAX_BYTES:
        _, (_, blob) = _cache.popitem(last=False)
        _cache_bytes -= len(blob)


def _desde_brep(blob: bytes):
    """BRep → forma de build123d con el MISMO tipo que entregaba el viaje por STEP (D3):
    el writer STEP escribe una forma con ubicación PROPIA como instancia ubicada de un
    ensamblaje, e ``import_step`` la devuelve como ``Compound``; sin ubicación propia, un
    compound de UN sólido (y nada más) vuelve como ese ``Solid``. Medido sobre los 48
    scripts del 38 y en ``tests/test_sandbox_worker.py``."""
    from build123d import Compound
    from build123d.persistence import deserialize_shape

    forma = wrap_topods(deserialize_shape(blob))
    if not forma.wrapped.Location().IsIdentity():
        return forma if isinstance(forma, Compound) else Compound([forma])
    if isinstance(forma, Compound):
        solidos = forma.solids()
        if len(solidos) == 1 and len(forma.faces()) == len(solidos[0].faces()):
            return solidos[0]
    return forma


def run_script_to_shape(code: str, variables: dict | None = None):
    """Ejecuta el script en el sandbox (o lo toma de la caché) y devuelve una forma NUEVA
    de build123d. ``ScriptError`` con el motivo si el script no produce geometría."""
    variables = variables or {}
    key = _cache_key(code, variables)
    with SANDBOX_LOCK:
        entrada = _cache.get(key)
        if entrada is not None:
            _cache.move_to_end(key)
        else:
            try:
                compile(code, "<script_ia>", "exec")
            except SyntaxError as exc:
                raise ScriptError(
                    f"Error de sintaxis en el script (línea {exc.lineno}): {exc.msg}"
                ) from exc
            entrada = _ejecutar(code, variables)
            _cache_put(key, entrada)
        etiqueta, blob = entrada
        try:
            return step_bytes_to_shape(blob) if etiqueta == b"S" else _desde_brep(blob)
        except Exception as exc:  # noqa: BLE001 — una entrada ilegible no se queda en caché
            _cache_drop(key)
            raise ScriptError(f"El script falló:\nno se pudo leer su geometría: {exc}") from exc


def step_bytes_to_shape(data: bytes):
    """Importa un STEP (bytes) como forma de build123d."""
    from build123d import import_step

    with tempfile.TemporaryDirectory(prefix="apolo_step_") as tmp:
        path = Path(tmp) / "in.step"
        path.write_bytes(data)
        return import_step(str(path))


def prewarm() -> None:
    """Levanta el worker en un hilo, sin bloquear (la API lo llama al arrancar). Idempotente:
    con un worker vivo no hace nada; si el arranque falla, el primer script dará el error."""
    if _worker is not None and _worker.vivo():
        return

    def _calentar() -> None:
        with SANDBOX_LOCK:
            try:
                _worker_listo()
            except ScriptError:
                pass

    threading.Thread(target=_calentar, daemon=True, name="apolo-sandbox-prewarm").start()


def worker_info() -> dict | None:
    """pid, origen de ``apolo`` y módulos ``apolo.*`` del worker vivo, y cuántos scripts
    lleva. None si no hay worker (para tests y diagnóstico)."""
    worker = _worker
    if worker is None or not worker.vivo():
        return None
    return {**worker.info, "scripts": worker.scripts}


def cache_info() -> dict:
    with SANDBOX_LOCK:
        return {"entradas": len(_cache), "bytes": _cache_bytes, "max_bytes": _CACHE_MAX_BYTES}


def clear_cache() -> None:
    global _cache_bytes
    with SANDBOX_LOCK:
        _cache.clear()
        _cache_bytes = 0


def shutdown() -> None:
    """Mata al worker (``atexit``; también para tests). No toma el lock: al salir, un hilo
    puede estar esperando una respuesta que ya no importa."""
    worker = _worker
    if worker is not None:
        worker.matar()


atexit.register(shutdown)
