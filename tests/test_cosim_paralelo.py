"""Varias co-simulaciones a la vez (plan cosim-en-paralelo D1–D3).

`cosim.proceso.COSIM_LOCK` es un semáforo de `APOLO_COSIM_PARALELO` cupos: con N = 2 dos corridas
lanzadas a la vez están DENTRO al mismo tiempo; con N = 1 (lo de antes) la segunda espera a que
salga la primera. Se mide con eventos sobre un `Popen` falso (regla del reloj de pared del
CLAUDE.md raíz): el worker real no aporta nada al cupo y cuesta segundos por corrida.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from apolo.cosim import proceso

CORE = Path(__file__).resolve().parents[1] / "core"


def _frame(cuerpo: bytes) -> bytes:
    return struct.pack(">I", len(cuerpo)) + cuerpo


class _Banco:
    """Un `Popen` falso que se queda DENTRO de `communicate` hasta que el test lo suelte."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.activos = 0
        self.max_activos = 0
        self.entraron: list[threading.Event] = [threading.Event() for _ in range(4)]
        self.soltar = threading.Event()
        self._n = 0

    def popen(self, *_a, **_k):
        banco = self

        class _Proc:
            returncode = 0

            def communicate(self, input=None, timeout=None):  # noqa: A002 — la firma de Popen
                with banco._lock:
                    i = banco._n
                    banco._n += 1
                    banco.activos += 1
                    banco.max_activos = max(banco.max_activos, banco.activos)
                banco.entraron[i].set()
                assert banco.soltar.wait(30), "el test nunca soltó la corrida"
                with banco._lock:
                    banco.activos -= 1
                listo = json.dumps({"apolo": "falso", "t_listo": 0.0}).encode()
                return _frame(b"R" + listo) + _frame(b"K" + json.dumps({"resumen": {}}).encode()), b""

            def kill(self):
                pass

        return _Proc()


@pytest.fixture
def banco(monkeypatch):
    b = _Banco()
    monkeypatch.setattr(proceso.subprocess, "Popen", b.popen)
    yield b
    b.soltar.set()


def _lanzar(n: int) -> tuple[list[threading.Thread], list]:
    errores: list = []

    def una():
        try:
            proceso.correr_en_proceso({"snap": "falso"}, timeout_s=60)
        except BaseException as exc:  # noqa: BLE001 — el test lo muestra
            errores.append(exc)

    hilos = [threading.Thread(target=una, daemon=True) for _ in range(n)]
    for h in hilos:
        h.start()
    return hilos, errores


def test_con_dos_cupos_dos_corridas_se_solapan(banco, monkeypatch):
    monkeypatch.setattr(proceso, "COSIM_LOCK", threading.BoundedSemaphore(2))
    hilos, errores = _lanzar(2)
    # las dos están DENTRO del worker antes de que ninguna termine
    assert banco.entraron[0].wait(30) and banco.entraron[1].wait(30)
    assert banco.activos == 2
    banco.soltar.set()
    for h in hilos:
        h.join(30)
    assert not errores and banco.max_activos == 2


def test_con_un_cupo_la_segunda_espera_a_la_primera(banco, monkeypatch):
    monkeypatch.setattr(proceso, "COSIM_LOCK", threading.BoundedSemaphore(1))
    hilos, errores = _lanzar(2)
    assert banco.entraron[0].wait(30)
    # la segunda no entra mientras la primera sigue dentro (con carga, este negativo sólo
    # puede pasar de más, nunca fallar en falso)
    assert not banco.entraron[1].wait(0.5)
    banco.soltar.set()
    assert banco.entraron[1].wait(30)
    for h in hilos:
        h.join(30)
    assert not errores and banco.max_activos == 1


def test_el_cupo_se_devuelve_aunque_el_worker_falle(monkeypatch):
    monkeypatch.setattr(proceso, "COSIM_LOCK", threading.BoundedSemaphore(1))

    def roto(*_a, **_k):
        raise OSError("sin ejecutable")

    monkeypatch.setattr(proceso.subprocess, "Popen", roto)
    for _ in range(2):  # la segunda no se cuelga: el cupo volvió
        with pytest.raises(proceso.CosimError, match="no pudo arrancar"):
            proceso.correr_en_proceso({"snap": "falso"})
    assert proceso.COSIM_LOCK.acquire(blocking=False)
    proceso.COSIM_LOCK.release()


def test_la_variable_valida_y_lo_invalido_cae_al_default_con_aviso():
    assert proceso.paralelo(None, defecto=3) == 3
    assert proceso.paralelo("  ", defecto=3) == 3
    assert proceso.paralelo("1", defecto=3) == 1  # = lo de antes, en fila
    assert proceso.paralelo(" 6 ", defecto=3) == 6
    for malo in ("0", "-2", "dos", "2.5", str(proceso.PARALELO_MAX + 1)):
        with pytest.warns(RuntimeWarning, match="APOLO_COSIM_PARALELO"):
            assert proceso.paralelo(malo, defecto=3) == 3


def test_el_default_deja_nucleos_y_ram_y_no_pasa_de_cuatro():
    gib = 2**30
    assert proceso.paralelo_por_defecto(8, 32 * gib) == 4   # la PC de escritorio
    assert proceso.paralelo_por_defecto(16, 64 * gib) == 4  # el tope
    assert proceso.paralelo_por_defecto(4, 16 * gib) == 2   # núcleos − 2
    assert proceso.paralelo_por_defecto(8, 4 * gib) == 2    # un cuarto de la RAM, 512 MB c/u
    assert proceso.paralelo_por_defecto(2, 2 * gib) == 1    # nunca menos de uno
    assert proceso.paralelo_por_defecto(8, 0) == 4          # RAM desconocida: sólo los núcleos
    assert 1 <= proceso.paralelo_por_defecto() <= proceso.PARALELO_TOPE_DEFECTO


def _al_importar(valor: str) -> subprocess.CompletedProcess:
    codigo = ("import warnings; warnings.simplefilter('always')\n"
              "from apolo.cosim import proceso as p\n"
              "print(p.COSIM_PARALELO, p.paralelo_por_defecto())\n")
    env = {**os.environ, "APOLO_COSIM_PARALELO": valor,
           "PYTHONPATH": os.pathsep.join([str(CORE), os.environ.get("PYTHONPATH", "")])}
    return subprocess.run([sys.executable, "-B", "-c", codigo], capture_output=True, text=True,
                          timeout=120, env=env)


def test_la_api_lee_la_variable_al_arrancar():
    uno = _al_importar("1")
    assert uno.returncode == 0, uno.stderr[-2000:]
    assert uno.stdout.split()[0] == "1"
    malo = _al_importar("muchos")
    assert malo.returncode == 0, malo.stderr[-2000:]
    cupos, defecto = malo.stdout.split()
    assert cupos == defecto and "APOLO_COSIM_PARALELO" in malo.stderr
