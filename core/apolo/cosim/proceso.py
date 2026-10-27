"""El lado del padre del worker de la co-simulación (plan V8.3 D11.2–3).

`correr_en_proceso(snap)` serializa el `CosimSnapshot`, lanza `python -m apolo.cosim.worker`
con `subprocess.Popen` (patrón del sandbox: nada de `multiprocessing`) y BLAS de un hilo, le
pasa el snapshot y espera el resultado con un límite de tiempo; un timeout mata al hijo. Sin
`STATE_LOCK` ni `PHYSICS_LOCK`: el snapshot ya se tomó.

Hasta `COSIM_PARALELO` co-simulaciones a la vez (`COSIM_LOCK`, semáforo bloqueante; la variable
`APOLO_COSIM_PARALELO`, 1 = en fila): cada corrida es su propio proceso sin estado compartido y el
cupo sólo cuida CPU y RAM ([cosim-en-paralelo](../../../docs/plans/cosim-en-paralelo.md)). La cola
de jobs con recibo y el endpoint son de F5. Este módulo no importa `apolo.state` ni la API.
"""

from __future__ import annotations

import json
import os
import pickle
import subprocess
import sys
import threading
import time
import warnings

from .worker import frames  # el mismo protocolo del hijo

#: Tope del default: con 4 corridas a la vez una PC de 8 núcleos sigue atendiendo la API, la UI y
#: los modeladores (plan cosim-en-paralelo D2, medido); `APOLO_COSIM_PARALELO` lo pasa si se pide.
PARALELO_TOPE_DEFECTO = 4
#: RAM que se reserva por worker: ~3,5× el pico medido (145 MB, la faja 77 con desviador), margen
#: para una máquina más grande (D2).
RAM_POR_WORKER = 512 * 2**20
#: Lo más que acepta la variable: un número mayor es un error de tipeo, no un plan.
PARALELO_MAX = 64


def _ram_total() -> int | None:
    """La RAM física en bytes, o None si el sistema no la dice (sin psutil: no es dependencia)."""
    try:
        if sys.platform == "win32":
            import ctypes

            class _Estado(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            e = _Estado()
            e.dwLength = ctypes.sizeof(_Estado)
            return int(e.ullTotalPhys) if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(e)) else None
        return int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        return None


def paralelo_por_defecto(nucleos: int | None = None, ram: int | None = None) -> int:
    """mín(núcleos − 2, RAM / 4 / `RAM_POR_WORKER`, 4), al menos 1: dos núcleos y tres cuartos de
    la RAM quedan para la API, el modelo OCCT y el sistema (D2)."""
    n = (os.cpu_count() or 1) if nucleos is None else nucleos
    cupos = [PARALELO_TOPE_DEFECTO, n - 2]
    ram = _ram_total() if ram is None else ram
    if ram:
        cupos.append(ram // 4 // RAM_POR_WORKER)
    return max(1, min(cupos))


def paralelo(crudo: str | None, *, defecto: int | None = None) -> int:
    """Cuántas corridas a la vez según `APOLO_COSIM_PARALELO` (`crudo`): vacío → el default; un
    entero de 1 a `PARALELO_MAX` → ese; otra cosa → el default CON aviso (no tumba la API)."""
    base = paralelo_por_defecto() if defecto is None else defecto
    texto = (crudo or "").strip()
    if not texto:
        return base
    if texto.isdigit() and 1 <= int(texto) <= PARALELO_MAX:
        return int(texto)
    warnings.warn(f"APOLO_COSIM_PARALELO debe ser un entero entre 1 y {PARALELO_MAX} (vale «{texto}»): "
                  f"corren {base} co-simulaciones a la vez", RuntimeWarning, stacklevel=2)
    return base


COSIM_PARALELO = paralelo(os.environ.get("APOLO_COSIM_PARALELO"))
COSIM_LOCK = threading.BoundedSemaphore(COSIM_PARALELO)
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
