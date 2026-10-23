"""Una sesión de gmsh (``initialize`` … ``finalize``) que no le deja secuelas al proceso.

``gmshInitialize`` (la librería C) reinstala SIGPIPE en ``SIG_DFL`` a espaldas de Python, que
arranca con ``SIG_IGN`` para que escribir a un pipe cerrado sea un ``BrokenPipeError`` y no la
muerte del proceso. Después de un FEA, cualquier escritura a un hijo que ya murió mataba a la API
entera (o a pytest: el CI de Linux moría con código 141 en ``test_media_codificar``, al escribir
a un ffmpeg que había fallado). Windows no tiene SIGPIPE: ahí esto no hace nada.
"""

from __future__ import annotations

import ctypes
import signal
import threading
from contextlib import contextmanager


def restaurar_sigpipe() -> None:
    """Devuelve SIGPIPE a lo que Python cree que tiene (``signal.getsignal``).

    Desde el hilo principal basta ``signal.signal``; los endpoints sync corren en el threadpool,
    donde Python no deja tocar señales: ahí se reinstala ``SIG_IGN``/``SIG_DFL`` con la ``signal``
    de libc, que vale para todo el proceso. Un handler de Python fuera del hilo principal no se
    puede reinstalar y se deja como está."""
    if not hasattr(signal, "SIGPIPE"):
        return
    previo = signal.getsignal(signal.SIGPIPE)
    if previo is None:  # instalado fuera de Python: no hay a qué volver
        return
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGPIPE, previo)
    elif previo in (signal.SIG_IGN, signal.SIG_DFL):
        libc = ctypes.CDLL(None)
        libc.signal.argtypes = (ctypes.c_int, ctypes.c_void_p)
        libc.signal.restype = ctypes.c_void_p
        libc.signal(int(signal.SIGPIPE), int(previo))


@contextmanager
def sesion(gmsh):
    """``gmsh.initialize(interruptible=False)`` + ``finalize``, con SIGPIPE intacto en medio y
    al salir. ``interruptible=False``: no instala el handler de SIGINT, que sólo funciona en el
    hilo principal (los endpoints sync corren en un threadpool; con él el primer análisis da
    500)."""
    gmsh.initialize(interruptible=False)
    restaurar_sigpipe()
    try:
        yield gmsh
    finally:
        try:
            gmsh.finalize()
        finally:
            restaurar_sigpipe()
