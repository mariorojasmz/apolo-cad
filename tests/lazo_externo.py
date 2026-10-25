"""El PLC FALSO en otro proceso para las pruebas del lazo con un PLC de afuera (plan
plc-en-el-lazo, D15): lo usan el lote (`test_cosim_plc_externo.py`) y la sesión en vivo
(`test_cosim_vivo_ws.py`).

  - `entorno()`: el del proceso hijo (el PLC falso y el worker importan `ext_prueba`);
  - `plc_falso(tmp_path, …)`: el PLC falso escuchando, (proceso, puerto); se apaga al salir del
    bloque y, si el test muere, solo (cierra con su stdin): nunca queda huérfano;
  - `pedido(puerto)`: el `plc_externo` con el conector `prueba.tcp`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def entorno() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(RAIZ / "core"), str(RAIZ / "tests"), os.environ.get("PYTHONPATH")) if p)
    return env


@contextmanager
def plc_falso(tmp_path, *, avisar: int = 0, puerto: int = 0):
    """El PLC falso escuchando: (proceso, puerto). Se apaga al salir (y solo si el test muere)."""
    from cosim_lazo_banco import PROGRAMA

    fuente = tmp_path / "main.st"
    fuente.write_text(PROGRAMA, encoding="utf-8")
    cmd = [sys.executable, "-B", "-m", "ext_prueba.plc_falso", str(fuente), "--avisar", str(avisar),
           "--puerto", str(puerto)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, env=entorno())
    try:
        linea = proc.stdout.readline()
        assert linea.startswith("PUERTO "), (linea, proc.stderr.read() if proc.poll() is not None else "")
        yield proc, int(linea.split()[1])
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass
        proc.kill()
        proc.wait(timeout=30)
        proc.stdout.close()
        proc.stderr.close()


def pedido(puerto: int) -> dict:
    return {"-K1": {"conector": "prueba.tcp", "config": {"host": "127.0.0.1", "puerto": puerto}}}
