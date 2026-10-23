"""gmsh no le deja SIGPIPE en SIG_DFL al proceso (`apolo.fea.sesion_gmsh`).

`gmshInitialize` reinstala SIGPIPE en SIG_DFL a espaldas de Python. Después de un FEA, escribir
a un hijo muerto mataba al proceso entero en vez de dar `BrokenPipeError`: el CI de Linux moría
con código 141 en `test_media_codificar` (ffmpeg que falla a mitad), sin traceback. Windows no
tiene SIGPIPE: ahí no hay nada que probar.

Lo que toca a gmsh corre en un subproceso: si la guarda fallara, el SIGPIPE mataría a pytest.
"""
import ctypes
import importlib.util
import signal
import subprocess
import sys
import threading

import pytest

pytestmark = pytest.mark.skipif(not hasattr(signal, "SIGPIPE"), reason="sin SIGPIPE (Windows)")

_GMSH_OK = importlib.util.find_spec("gmsh") is not None


def _libc_signal():
    libc = ctypes.CDLL(None)
    libc.signal.argtypes = (ctypes.c_int, ctypes.c_void_p)
    libc.signal.restype = ctypes.c_void_p
    return libc.signal


def _disposicion() -> int:
    """La disposición REAL de SIGPIPE (la de libc, no la que Python cree): 0 DFL, 1 IGN."""
    sig = _libc_signal()
    actual = sig(int(signal.SIGPIPE), int(signal.SIG_IGN)) or 0
    sig(int(signal.SIGPIPE), actual)
    return actual


@pytest.mark.parametrize("hilo", [False, True], ids=["principal", "threadpool"])
def test_restaurar_sigpipe_vuelve_a_lo_que_python_cree(hilo):
    from apolo.fea.sesion_gmsh import restaurar_sigpipe

    assert signal.getsignal(signal.SIGPIPE) is signal.SIG_IGN
    sig = _libc_signal()
    try:
        sig(int(signal.SIGPIPE), int(signal.SIG_DFL))  # lo que hace gmshInitialize
        assert _disposicion() == int(signal.SIG_DFL)
        if hilo:  # los endpoints sync de FastAPI: signal.signal no vale fuera del principal
            t = threading.Thread(target=restaurar_sigpipe)
            t.start()
            t.join()
        else:
            restaurar_sigpipe()
        assert _disposicion() == int(signal.SIG_IGN)
    finally:
        sig(int(signal.SIGPIPE), int(signal.SIG_IGN))


_GUION = r"""
import os, subprocess, sys, threading
import gmsh
from apolo.fea.sesion_gmsh import sesion

def con_gmsh():
    if sys.argv[1] == "crudo":
        gmsh.initialize(interruptible=False)
        gmsh.finalize()
    else:
        with sesion(gmsh):
            gmsh.model.add("x")

if sys.argv[2] == "threadpool":
    t = threading.Thread(target=con_gmsh); t.start(); t.join()
else:
    con_gmsh()

hijo = subprocess.Popen([sys.executable, "-c", "pass"], stdin=subprocess.PIPE)
hijo.wait()
try:
    os.write(hijo.stdin.fileno(), b"x" * 65536)  # como el Codificador ante un ffmpeg que murió
except BrokenPipeError:
    print("BrokenPipeError")
"""


def _correr(modo: str, hilo: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", _GUION, modo, hilo], capture_output=True,
                          text=True, timeout=120)


@pytest.mark.skipif(not _GMSH_OK, reason="extra [fea] no instalado")
@pytest.mark.parametrize("hilo", ["principal", "threadpool"])
def test_tras_una_sesion_gmsh_un_pipe_roto_es_una_excepcion(hilo):
    crudo = _correr("crudo", hilo)
    if crudo.returncode != -signal.SIGPIPE:
        pytest.skip(f"este gmsh ya no deja SIGPIPE en SIG_DFL (código {crudo.returncode}): "
                    "la prueba no distinguiría nada")
    res = _correr("sesion", hilo)
    assert res.returncode == 0, res.stderr
    assert res.stdout.strip() == "BrokenPipeError"
