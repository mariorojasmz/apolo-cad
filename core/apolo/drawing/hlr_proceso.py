"""El lado del padre del HLR en procesos (plan visor-para-evaluar D6, F0b): `correr(formas,
tareas)` lanza `python -m apolo.drawing.hlr_worker` por tarea (una vista o el corte), hasta
`PARALELO` a la vez, les pasa las formas en BinTools y junta los resultados en orden.

`subprocess.Popen` y no `multiprocessing` (el patrón del sandbox y de la co-simulación): el hijo
arranca limpio y no hereda el estado de la API. Sin `STATE_LOCK`: las formas ya se copiaron. Si
el worker no arranca (un empaquetado raro), la tarea se resuelve en este proceso con el mismo
código y se avisa en el log: la lámina no puede desaparecer.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import queue
import subprocess
import sys
import threading
from typing import Callable

log = logging.getLogger(__name__)

#: Tareas a la vez: una vista por núcleo, sin pasar de 4 (la lámina de conjunto tiene 4 vistas y
#: el corte) ni ahogar la máquina (se deja un núcleo a la API).
PARALELO = max(1, min(4, (os.cpu_count() or 2) - 1))
TIMEOUT_S = 1800.0
BLAS_UN_HILO = {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}


class HlrError(Exception):
    """El worker no devolvió un resultado: el texto dice por qué."""


def _uno(cuerpo: bytes) -> dict:
    cmd = [sys.executable] + (["-B"] if sys.flags.dont_write_bytecode else []) + ["-m", "apolo.drawing.hlr_worker"]
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env={**os.environ, **BLAS_UN_HILO})
    except OSError as exc:
        log.warning("El worker del HLR no arrancó (%s): se calcula en el proceso de la API", exc)
        from .hlr_worker import resolver

        return resolver(pickle.loads(cuerpo))
    try:
        out, err = proc.communicate(input=cuerpo, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        proc.communicate()
        raise HlrError(f"El cálculo de las vistas pasó de {TIMEOUT_S:.0f} s y se cortó.") from exc
    if proc.returncode != 0:
        cola = err.decode("utf-8", "replace").strip().splitlines()[-3:]
        raise HlrError("El cálculo de las vistas falló: " + " | ".join(cola))
    return json.loads(out.decode("utf-8"))


def correr(formas: list, tareas: list[dict], *, avance: Callable[[int, int, str], None] | None = None,
           nombres: list[str] | None = None, paralelo: int | None = None) -> list[dict]:
    """El resultado de cada tarea, en el orden de `tareas`. `avance(hechas, total, que)` cada vez
    que una termina (`que` = la primera que sigue pendiente), llamado desde ESTE hilo: el progreso
    del job es hilo-local (`api/jobs.avance`). Lanza la primera excepción."""
    n = len(tareas)
    resultados: list = [None] * n
    terminadas: queue.Queue = queue.Queue()
    cupo = threading.Semaphore(paralelo or PARALELO)
    cortar = threading.Event()
    nombres = nombres or [str(i) for i in range(n)]

    def trabajar(i: int) -> None:
        with cupo:
            if cortar.is_set():
                terminadas.put((i, None, None))
                return
            try:
                r = _uno(pickle.dumps({"formas": formas, "tarea": tareas[i]}, protocol=pickle.HIGHEST_PROTOCOL))
            except BaseException as exc:  # noqa: BLE001 — viaja al llamador
                cortar.set()
                terminadas.put((i, None, exc))
                return
        terminadas.put((i, r, None))

    for i in range(n):
        threading.Thread(target=trabajar, args=(i,), daemon=True, name=f"apolo-hlr-{i}").start()
    error = None
    for hechas in range(1, n + 1):
        i, r, exc = terminadas.get()
        if exc is not None and error is None:
            error = exc
        resultados[i] = r
        if avance and error is None:
            pendiente = next((nombres[k] for k in range(n) if resultados[k] is None), "listo")
            avance(hechas, n, pendiente)
    if error is not None:
        raise error
    return resultados
