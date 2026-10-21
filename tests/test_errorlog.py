"""El registro de errores de la suite NO toca el `logs/errors.log` real (conftest), y varios
procesos lo comparten sin perder líneas (plan varias-maquinas-a-la-vez, D7)."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import apolo


def test_errorlog_redirigido_fuera_del_repo(_errorlog_aislado):
    from apolo import paths
    from apolo.api import errorlog

    real = (paths.logs_dir() / "errors.log").resolve()
    antes = real.read_bytes() if real.exists() else None
    marca = f"línea de prueba aislada {uuid.uuid4().hex}"
    errorlog.log_error("test.aislamiento", marca)

    assert Path(errorlog.LOG_FILE).resolve() != real
    assert Path(errorlog.LOG_FILE).parent == _errorlog_aislado
    assert marca in errorlog.read_log()
    assert (real.read_bytes() if real.exists() else None) == antes


_HIJO = r"""
import os, sys
from apolo.anexar import anexar_linea
ruta, n = sys.argv[1], int(sys.argv[2])
for i in range(n):
    anexar_linea(ruta, f"{os.getpid()} {i} " + "x" * 300)
"""


def test_varios_procesos_anexan_al_mismo_log_sin_perder_ni_mezclar_lineas(tmp_path):
    """F0: con 5 procesos × 3000 líneas, el `FileHandler` de antes perdió el 27 % y abrir en
    `'a'` + escribir, el 13 % (en Windows el append del CRT es seek + write). El append
    atómico del sistema no pierde ninguna."""
    ruta = tmp_path / "compartido.log"
    core = str(Path(apolo.__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": core + os.pathsep + os.environ.get("PYTHONPATH", ""),
           "PYTHONDONTWRITEBYTECODE": "1"}
    procs, n = 4, 1500
    hijos = [subprocess.Popen([sys.executable, "-B", "-c", _HIJO, str(ruta), str(n)], env=env)
             for _ in range(procs)]
    for h in hijos:
        assert h.wait(timeout=300) == 0
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    sanas = [ln for ln in lineas if len(ln.split(" ")) == 3 and ln.endswith(" " + "x" * 300)]
    assert len(lineas) == len(sanas) == procs * n
    por_hijo = {}
    for ln in sanas:
        pid, i, _ = ln.split(" ")
        por_hijo.setdefault(pid, set()).add(int(i))
    assert len(por_hijo) == procs and all(v == set(range(n)) for v in por_hijo.values())


def test_anexar_escapa_los_saltos_y_crea_el_archivo(tmp_path):
    from apolo.anexar import anexar_linea

    ruta = tmp_path / "nuevo.log"
    anexar_linea(ruta, "uno\ndos\r\ntres")
    anexar_linea(ruta, "cuatro")
    assert ruta.read_bytes().decode("utf-8") == "uno\\ndos\\ntres\ncuatro\n"
