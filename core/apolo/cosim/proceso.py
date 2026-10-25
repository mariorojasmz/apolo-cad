"""El lado del padre del worker de la co-simulación (plan V8.3 D11.2–3).

`correr_en_proceso(snap)` serializa el `CosimSnapshot`, lanza `python -m apolo.cosim.worker`
con `subprocess.Popen` (patrón del sandbox: nada de `multiprocessing`) y BLAS de un hilo, le
pasa el snapshot y espera el resultado con un límite de tiempo; un timeout mata al hijo. Sin
`STATE_LOCK` ni `PHYSICS_LOCK`: el snapshot ya se tomó.

UNA co-simulación a la vez (`COSIM_LOCK`, bloqueante): la cola de jobs con recibo y el endpoint
son de F5. Este módulo no importa `apolo.state` ni la API.
"""

from __future__ import annotations

import json
import os
import pickle
import subprocess
import sys
import threading
import time

from .worker import frames  # el mismo protocolo del hijo

COSIM_LOCK = threading.Lock()
TIMEOUT_S = 1800.0
BLAS_UN_HILO = {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"}


class CosimError(Exception):
    """El worker no devolvió un resultado: el texto dice por qué."""


class LazoCortadoError(CosimError):
    """El lazo con un PLC externo se cortó o no se abrió (plan plc-en-el-lazo D8): no es una
    falla del núcleo sino del PLC de afuera o de su red; el texto trae la hora."""


def _cuerpo_frame(body: bytes) -> bytes:
    import struct

    return struct.pack(">I", len(body)) + body


def correr_en_proceso(snap, *, timeout_s: float | None = None) -> dict:
    """El resultado de `planificador.correr(snap)` corrido en un proceso aparte, más `proceso`
    (pid, arranque y total). `CosimError` si el hijo falla, se cae o se pasa del tiempo."""
    cuerpo = _cuerpo_frame(pickle.dumps(snap, protocol=pickle.HIGHEST_PROTOCOL))
    cmd = [sys.executable] + (["-B"] if sys.flags.dont_write_bytecode else []) + ["-m", "apolo.cosim.worker"]
    limite = TIMEOUT_S if timeout_s is None else float(timeout_s)
    with COSIM_LOCK:
        t_popen = time.time()
        t0 = time.perf_counter()
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, env={**os.environ, **BLAS_UN_HILO})
        except OSError as exc:
            raise CosimError(f"el worker de la co-simulación no pudo arrancar: {exc}") from exc
        try:
            out, err = proc.communicate(input=cuerpo, timeout=limite)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            raise CosimError(f"la co-simulación superó el límite de {limite:g} s") from None
        total = time.perf_counter() - t0
    partes = frames(out)
    if not partes or partes[0][:1] != b"R":
        cola = "\n".join(err.decode("utf-8", "replace").splitlines()[-8:])
        raise CosimError(f"el worker de la co-simulación no arrancó (código {proc.returncode}):\n{cola}")
    listo = json.loads(partes[0][1:].decode("utf-8"))
    if len(partes) < 2:
        cola = "\n".join(err.decode("utf-8", "replace").splitlines()[-8:])
        raise CosimError(f"el worker de la co-simulación se cayó (código {proc.returncode}):\n{cola}")
    etiqueta, resto = partes[1][:1], partes[1][1:]
    if etiqueta == b"E":
        raise CosimError(f"la co-simulación falló:\n{resto.decode('utf-8', 'replace')}")
    if etiqueta == b"L":
        raise LazoCortadoError(resto.decode("utf-8", "replace"))
    if etiqueta != b"K":
        raise CosimError(f"el worker respondió algo inesperado ({etiqueta!r})")
    res = json.loads(resto.decode("utf-8"))
    res.setdefault("proceso", {}).update({
        "apolo": listo.get("apolo"), "arranque_s": round(listo["t_listo"] - t_popen, 4),
        "total_s": round(total, 4)})
    return res
