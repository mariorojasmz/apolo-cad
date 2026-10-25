"""El worker de la co-simulación: un proceso aparte por corrida (plan V8.3 D11.2).

`proceso.py` lo lanza con `python -m apolo.cosim.worker` (`subprocess.Popen`, nunca
`multiprocessing`, como el sandbox) y BLAS de un hilo (`OPENBLAS_NUM_THREADS=1`: en las matrices
de 60 nodos los hilos multiplican el costo, F3). Corre SIN `STATE_LOCK` ni `PHYSICS_LOCK`: la
API sigue atendiendo `gravity_test` y la puerta de entrega mientras dura.

PROTOCOLO, binario (frame = largo en 4 bytes big-endian + cuerpo, el del sandbox):
  hijo → padre  `R` + JSON     listo: pid, de dónde importó `apolo`, hora y costo del import
  padre → hijo  pickle         el `CosimSnapshot` (lo hornea el propio proceso de la API)
  hijo → padre  `K` + JSON     el resultado de `planificador.correr` + `proceso`
                `E` + texto    el error, con las últimas líneas de la traza
                `L` + texto    el lazo con un PLC externo se cortó o no se abrió (plan
                               plc-en-el-lazo D8), con su hora: sin resultado parcial
Modo VIVO (V8.4 D1): si el primer frame del padre es `V` + JSON (la configuración: `ritmo`,
`max_s`), el segundo es el snapshot y la sesión sigue con el protocolo de `worker_vivo.py`
(acciones `A` que entran; tabla, acks y fin `J` y fotogramas `F` que salen) hasta EOF o «parar».
El resultado vuelve en JSON y no en pickle: el hijo corre código ST del usuario (compilado y
verificado, D6) y el padre no des-serializa objetos que vengan de él. Una corrida por proceso:
el estado de MuJoCo, del PLC y de los modelos no se arrastra de una prueba a la otra.

No importa OCCT, build123d ni el catálogo (`tests/test_cosim_worker.py`): sólo `cosim`, `plc`
y los módulos de datos de la física.
"""

from __future__ import annotations

import json
import os
import struct
import sys
import time
import traceback

_LARGO = struct.Struct(">I")
#: Lo que el worker NO debe cargar (lo mira el test y lo informa cada corrida).
PESADOS = ("OCP", "build123d", "vtk", "apolo.library", "apolo.kernel", "apolo.doc", "apolo.commands",
           "apolo.state", "apolo.api")


def write_frame(stream, body: bytes) -> None:
    stream.write(_LARGO.pack(len(body)))
    stream.write(body)
    stream.flush()


def _read_exact(stream, n: int) -> bytes | None:
    partes, falta = [], n
    while falta:
        parte = stream.read(falta)
        if not parte:
            return None
        partes.append(parte)
        falta -= len(parte)
    return b"".join(partes)


def read_frame(stream) -> bytes | None:
    cabeza = _read_exact(stream, _LARGO.size)
    if cabeza is None:
        return None
    return _read_exact(stream, _LARGO.unpack(cabeza)[0])


def frames(datos: bytes) -> list[bytes]:
    """Los frames completos de un buffer (lo que el padre leyó de la salida del hijo)."""
    out, i = [], 0
    while i + _LARGO.size <= len(datos):
        n = _LARGO.unpack_from(datos, i)[0]
        i += _LARGO.size
        if i + n > len(datos):
            break
        out.append(datos[i: i + n])
        i += n
    return out


def pesados_cargados() -> list[str]:
    return sorted(m for m in sys.modules if any(m == p or m.startswith(p + ".") for p in PESADOS))


def _json(x):
    """numpy y otros escalares → Python (el resultado ya es casi todo nativo)."""
    if hasattr(x, "item"):
        return x.item()
    if hasattr(x, "tolist"):
        return x.tolist()
    if isinstance(x, complex):
        return [x.real, x.imag]
    return str(x)


def _tomar_canal():
    """Separa el canal del protocolo de los fd 0/1: lo que MuJoCo escriba en stdout va a stderr."""
    entrada, salida = os.dup(0), os.dup(1)
    nulo = os.open(os.devnull, os.O_RDONLY)
    os.dup2(nulo, 0)
    os.close(nulo)
    os.dup2(2, 1)
    if sys.platform == "win32":
        import msvcrt

        msvcrt.setmode(entrada, os.O_BINARY)
        msvcrt.setmode(salida, os.O_BINARY)
    sys.stdout = sys.stderr
    return os.fdopen(entrada, "rb"), os.fdopen(salida, "wb")


def main() -> int:
    t0 = time.perf_counter()
    entrada, salida = _tomar_canal()
    import pickle

    import mujoco  # noqa: F401 — se carga aquí: el arranque cuenta todo el import

    import apolo
    from apolo.cosim import planificador
    from apolo.cosim.modelos import registrar_modelos
    from apolo.cosim.puerto_plc import LazoCortado

    import_s = time.perf_counter() - t0
    write_frame(salida, b"R" + json.dumps({"pid": os.getpid(), "apolo": apolo.__file__,
                                           "t_listo": time.time(), "import_s": import_s}).encode("utf-8"))
    cuerpo = read_frame(entrada)
    if cuerpo is None:
        return 0
    config = None
    if cuerpo[:1] == b"V":  # modo vivo (V8.4 D1): la configuración y después el snapshot
        config = json.loads(cuerpo[1:].decode("utf-8"))
        cuerpo = read_frame(entrada)
        if cuerpo is None:
            return 0
    try:
        snap = pickle.loads(cuerpo)  # noqa: S301 — lo serializó el proceso de la API
        # los modelos de extensión del tablero vienen en el snapshot (nucleo-abierto A3)
        registrar_modelos(getattr(snap, "modelos_extension", None) or {})
        if config is not None:
            from apolo.cosim.worker_vivo import correr_vivo

            correr_vivo(snap, config, entrada, salida)
            return 0
        res = planificador.correr(snap)
        res["proceso"] = {"pid": os.getpid(), "import_s": round(import_s, 4),
                          "modulos_pesados": pesados_cargados(),
                          "blas_hilos": os.environ.get("OPENBLAS_NUM_THREADS")}
        write_frame(salida, b"K" + json.dumps(res, default=_json).encode("utf-8"))
    except LazoCortado as exc:  # plc-en-el-lazo D8: el lazo con el PLC de afuera, con su hora
        write_frame(salida, b"L" + str(exc).encode("utf-8"))
    except BaseException as exc:  # noqa: BLE001 — todo error vuelve como texto
        traza = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        lineas = [x for x in traza.splitlines() if x.strip()][-8:]
        write_frame(salida, b"E" + (f"{type(exc).__name__}: {exc}\n" + "\n".join(lineas)).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
