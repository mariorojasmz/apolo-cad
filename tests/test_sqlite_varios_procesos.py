"""La SQLite de proyectos aguanta varios procesos de la API a la vez (plan
`docs/plans/varias-maquinas-a-la-vez.md`, D2): WAL + `busy_timeout` de 30 s.

F0 del plan: con el `_conn` viejo (rollback, 5 s) cinco procesos que guardan en bucle dieron
`database is locked`; con WAL + 30 s, ninguno (y una espera llegÃ³ a 7,3 s).
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import apolo
from apolo.doc import Document
from apolo.projects import BUSY_TIMEOUT_S, ProjectStore

#: lo que hace un autosave (bytes .apolo + geom_cache) y lo que hace otro proceso al abrir o
#: al insertar un proyecto (leer), N veces sobre el MISMO proyecto
_HIJO = r"""
import os, sqlite3, sys
from apolo.projects import ProjectStore
st = ProjectStore(sys.argv[1])
pid, vueltas = int(sys.argv[2]), int(sys.argv[3])
apolo_bytes, blob = os.urandom(20 * 1024), os.urandom(128 * 1024)
fallos = 0
for i in range(vueltas):
    try:
        st.save_raw(pid, f"vuelta {i}", i, apolo_bytes)
        st.save_geom_cache(pid, f"sig{i}", blob)
        st.load_bytes(pid)
    except sqlite3.OperationalError as exc:
        fallos += 1
        print("FALLO", exc, flush=True)
print("FALLOS", fallos, flush=True)
"""


def _env_hijo() -> dict:
    core = str(Path(apolo.__file__).resolve().parents[1])
    previo = os.environ.get("PYTHONPATH")
    return {**os.environ, "PYTHONPATH": core + (os.pathsep + previo if previo else ""),
            "PYTHONDONTWRITEBYTECODE": "1"}


def test_dos_procesos_guardan_200_veces_el_mismo_archivo_sin_un_locked(tmp_path):
    st = ProjectStore(tmp_path / "flota.db")
    pid = st.create(Document("compartido"))
    hijos = [subprocess.Popen([sys.executable, "-B", "-c", _HIJO, st.path, str(pid), "200"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                              env=_env_hijo()) for _ in range(2)]
    salidas = [h.communicate(timeout=600)[0] for h in hijos]
    for h, salida in zip(hijos, salidas):
        assert h.returncode == 0, salida
        assert "FALLOS 0" in salida and "locked" not in salida, salida
    assert st.load_bytes(pid)  # la base sigue sana y legible


def test_el_almacen_deja_la_base_en_wal_y_con_30_s_de_espera(tmp_path):
    st = ProjectStore(tmp_path / "w.db")
    assert st.journal_mode == "wal"
    with st._conn() as con:
        assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert con.execute("PRAGMA busy_timeout").fetchone()[0] == int(BUSY_TIMEOUT_S * 1000)
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_una_base_vieja_en_rollback_pasa_a_wal_y_conserva_sus_proyectos(tmp_path):
    ruta = tmp_path / "vieja.db"
    st = ProjectStore(ruta)
    pid = st.create(Document("de antes"))
    con = sqlite3.connect(ruta)
    assert con.execute("PRAGMA journal_mode=DELETE").fetchone()[0] == "delete"
    con.close()
    st2 = ProjectStore(ruta)
    assert st2.journal_mode == "wal"
    assert [p["name"] for p in st2.list_projects()] == ["de antes"]
    assert st2.load(pid).name == "de antes"


def test_un_lector_no_espera_a_un_escritor_con_la_transaccion_abierta(tmp_path):
    """En rollback, una transacciÃ³n EXCLUSIVE bloquea a los lectores hasta el timeout; en WAL
    leen la Ãºltima versiÃ³n confirmada al instante."""
    st = ProjectStore(tmp_path / "l.db")
    pid = st.create(Document("leible"))
    otro = sqlite3.connect(st.path, timeout=0, isolation_level=None)
    try:
        otro.execute("BEGIN EXCLUSIVE")
        otro.execute("UPDATE projects SET name='a medias' WHERE id=?", (pid,))
        t0 = time.perf_counter()
        assert st.list_projects()[0]["name"] == "leible"
        assert st.load_bytes(pid)
        assert time.perf_counter() - t0 < 2.0
    finally:
        otro.execute("ROLLBACK")
        otro.close()


def test_cada_operacion_cierra_su_conexion(tmp_path):
    """Sin conexiones vivas, sqlite hace checkpoint y borra el `-wal` al cerrar la Ãºltima:
    si `_conn` no cerrara (antes se cerraba reciÃ©n en el GC), el `-wal` quedarÃ­a."""
    st = ProjectStore(tmp_path / "c.db")
    pid = st.create(Document("x"))
    st.save(pid, Document("y"))
    st.load_bytes(pid)
    assert st.exists(pid) and not st.exists(pid + 1)
    assert not Path(st.path + "-wal").exists()
