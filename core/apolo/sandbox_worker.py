"""Worker caliente del sandbox de scripts (plan sandbox-caliente, D1–D3).

Proceso hijo de vida larga que ``sandbox.py`` lanza con ``python -m apolo.sandbox_worker``:
importa build123d UNA vez y atiende scripts uno tras otro. Así un script cuesta su ``exec``
(~0,02 s en el proyecto 38) y no el import de build123d (~4,5 s).

PROTOCOLO, binario: cada mensaje es un FRAME = largo en 4 bytes big-endian + cuerpo.
  hijo → padre  ``R`` + JSON        listo: pid, de dónde importó ``apolo`` y sus ``apolo.*``
  padre → hijo  JSON                un script: ``{"code", "vars", "step"}`` (``step`` fuerza
                                    el respaldo STEP; sólo lo usan los tests)
  hijo → padre  ``B`` + BRep        el resultado en BinTools (``brep_io.serialize_robust``)
                ``S`` + STEP        respaldo: el shape no round-trip-ea en BRep
                ``E`` + texto       el mensaje COMPLETO del ``ScriptError``
El canal es una COPIA de los fd 0/1 originales: el fd 1 (``print`` del script, mensajes de
OCCT) pasa a ser stderr, que el padre drena, y el fd 0 pasa a ser ``devnull`` (un ``input()``
del script no se come un pedido).

Vida: un hilo lee los pedidos y, al ver EOF, sale con ``os._exit`` aun en medio de un script:
si el padre muere, el worker no queda huérfano. Namespace FRESCO por script (build123d
completo + ``math`` + ``V``); el padre recicla el worker tras cualquier error.

No importa ``apolo.kernel``, ``apolo.doc`` ni ``apolo.commands``: sólo ``brep_io``.
"""

from __future__ import annotations

import json
import os
import queue
import struct
import sys
import tempfile
import threading
import traceback

_LARGO = struct.Struct(">I")


# ── Protocolo (lo usan el padre y el hijo) ────────────────────────────────────

def write_frame(stream, body: bytes) -> None:
    """Escribe un frame (largo + cuerpo) y vacía el buffer."""
    stream.write(_LARGO.pack(len(body)))
    stream.write(body)
    stream.flush()


def _read_exact(stream, n: int) -> bytes | None:
    partes: list[bytes] = []
    falta = n
    while falta:
        parte = stream.read(falta)
        if not parte:
            return None
        partes.append(parte)
        falta -= len(parte)
    return b"".join(partes)


def read_frame(stream) -> bytes | None:
    """Lee un frame completo; None si el otro extremo cerró (EOF, también a medias)."""
    cabeza = _read_exact(stream, _LARGO.size)
    if cabeza is None:
        return None
    return _read_exact(stream, _LARGO.unpack(cabeza)[0])


def ultimas_lineas(texto: str, n: int = 6) -> str:
    """Las últimas ``n`` líneas no vacías: lo útil de un traceback o de un stderr."""
    lineas = [linea for linea in texto.splitlines() if linea.strip()]
    return "\n".join(lineas[-n:])


# ── El proceso hijo ───────────────────────────────────────────────────────────

def _tomar_canal():
    """Separa el canal del protocolo de los fd 0/1 que usan el script y OCCT."""
    entrada, salida = os.dup(0), os.dup(1)
    nulo = os.open(os.devnull, os.O_RDONLY)
    os.dup2(nulo, 0)
    os.close(nulo)
    os.dup2(2, 1)
    if sys.platform == "win32":  # sin traducción de \n en el canal binario
        import msvcrt

        msvcrt.setmode(entrada, os.O_BINARY)
        msvcrt.setmode(salida, os.O_BINARY)
    sys.stdout = sys.stderr
    return os.fdopen(entrada, "rb"), os.fdopen(salida, "wb")


def _leer_pedidos(entrada, pedidos: queue.Queue) -> None:
    while True:
        try:
            cuerpo = read_frame(entrada)
        except Exception:  # noqa: BLE001 — un canal roto es un EOF
            cuerpo = None
        if cuerpo is None:
            os._exit(0)  # el padre cerró o murió: salir YA, aun a mitad de un script
        pedidos.put(cuerpo)


def _error(mensaje: str) -> bytes:
    return b"E" + mensaje.encode("utf-8", "replace")


def _fallo(exc: BaseException, saltar_marco: bool) -> bytes:
    tb = exc.__traceback__
    if saltar_marco and tb is not None:
        tb = tb.tb_next  # el marco de `_atender` no le sirve a quien escribió el script
    traza = "".join(traceback.format_exception(type(exc), exc, tb))
    return _error("El script falló:\n" + ultimas_lineas(traza))


def _salida_explicita(exc: SystemExit) -> bytes:
    """``sys.exit`` en el script: lo mismo que decía el sandbox de un intérprete por script."""
    code = exc.code
    if code is None or code == 0:
        return _error("El script terminó sin producir geometría")
    if isinstance(code, int):
        return _error(f"El script falló:\ncódigo de salida {code}")
    return _error("El script falló:\n" + ultimas_lineas(str(code)))


def _a_step(objetivo) -> bytes:
    from build123d import export_step

    fd, ruta = tempfile.mkstemp(suffix=".step", dir=os.getcwd())
    os.close(fd)
    try:
        export_step(objetivo, ruta)
        with open(ruta, "rb") as fh:
            return fh.read()
    finally:
        try:
            os.remove(ruta)
        except OSError:
            pass


def _atender(cuerpo: bytes, base: dict) -> bytes:
    """Ejecuta UN script en un namespace fresco y devuelve el cuerpo de la respuesta."""
    import builtins

    from build123d import Compound

    from apolo.brep_io import serialize_robust

    try:
        pedido = json.loads(cuerpo.decode("utf-8"))
        ns = dict(base)
        ns["__builtins__"] = builtins
        ns["V"] = pedido.get("vars") or {}
        exec(compile(pedido["code"], "<script_ia>", "exec"), ns)  # noqa: S102 - sandbox deliberado
    except SystemExit as exc:
        return _salida_explicita(exc)
    except BaseException as exc:  # noqa: BLE001 — todo error del script vuelve como texto
        return _fallo(exc, saltar_marco=True)

    resultado = ns.get("result")
    if resultado is None:
        return _error("El script falló:\nEl script debe asignar la variable 'result' "
                      "(forma o lista de formas)")
    formas = list(resultado) if isinstance(resultado, (list, tuple)) else [resultado]
    if not formas:
        return _error("El script falló:\n'result' está vacío")
    try:
        objetivo = formas[0] if len(formas) == 1 else Compound(children=formas)
        if not hasattr(objetivo, "wrapped"):
            return _error("El script falló:\n'result' no es geometría de build123d: "
                          f"{type(resultado).__name__}")
        blob = None if pedido.get("step") else serialize_robust(objetivo.wrapped)
        if blob is not None:
            return b"B" + blob
        step = _a_step(objetivo)
    except BaseException as exc:  # noqa: BLE001
        return _fallo(exc, saltar_marco=False)
    if not step:
        return _error("El script terminó sin producir geometría")
    return b"S" + step


def main() -> int:
    entrada, salida = _tomar_canal()

    import math

    import build123d

    import apolo
    import apolo.brep_io  # noqa: F401 — se carga aquí, no en el primer script

    base = {name: getattr(build123d, name) for name in dir(build123d) if not name.startswith("_")}
    base["math"] = math
    listo = {
        "pid": os.getpid(),
        "apolo": apolo.__file__,
        "modulos": sorted(m for m in sys.modules if m == "apolo" or m.startswith("apolo.")),
    }
    write_frame(salida, b"R" + json.dumps(listo).encode("utf-8"))

    pedidos: queue.Queue = queue.Queue()
    threading.Thread(target=_leer_pedidos, args=(entrada, pedidos), daemon=True,
                     name="apolo-sandbox-pedidos").start()
    while True:
        write_frame(salida, _atender(pedidos.get(), base))


if __name__ == "__main__":
    sys.exit(main())
