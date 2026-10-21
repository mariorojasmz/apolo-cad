"""Un proyecto abierto en un proceso de la API no lo abre otro (plan
`docs/plans/varias-maquinas-a-la-vez.md`, D4).

- El candado vive en `project_leases` de la SQLite: dueño `host:pid:puerto` y latido.
- Abrir uno con candado vivo de otro dueño → 409 con el mensaje; latido viejo (o pid muerto en
  esta máquina) → se toma. Cambiar de proyecto suelta el anterior.
- El autosave sin candado no escribe y deja `autosave_error`.
- El `:8000` de siempre (un proceso, sin `APOLO_PROJECT`) abre y guarda igual.
"""

from __future__ import annotations

import os
import signal
import socket
import sqlite3
import subprocess
import sys
import time

import pytest
from fastapi.testclient import TestClient

import apolo.api.main as api
from apolo.api import candado
from apolo.api.session import S, initialize_store
from apolo.doc import Document
from apolo.projects import ProjectStore, _utc

OTRO = "otra-pc:1234:8102"  # otra máquina: ni se mira si su pid vive


def _poner_candado(st: ProjectStore, pid: int, dueno: str, edad_s: float = 0.0) -> None:
    with st._conn() as con:
        con.execute("INSERT OR REPLACE INTO project_leases VALUES(?,?,?)",
                    (pid, dueno, _utc(-edad_s)))


@pytest.fixture
def base(tmp_path, monkeypatch):
    """Almacén con dos proyectos (A con una caja, B vacío) y la API apuntando a él."""
    st = ProjectStore(tmp_path / "candados.db")
    doc_a = Document("A")
    doc_a.execute("create_box", {"width": 10})
    a, b = st.create(doc_a), st.create(Document("B"))
    monkeypatch.setattr(api, "STORE", st)
    monkeypatch.setattr(api, "PROJECT_ID", None)
    monkeypatch.setattr(api, "DOC", Document("vacío"))
    monkeypatch.setattr(api, "AUTOSAVE_ERROR", None)
    return st, a, b, TestClient(api.app)


# ------------------------------------------------------------------ almacén
def test_la_tabla_nace_sola_en_una_base_vieja(tmp_path):
    ruta = tmp_path / "vieja.db"
    with sqlite3.connect(ruta) as con:
        con.execute("CREATE TABLE projects(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT "
                    "NULL, updated_at TEXT NOT NULL, pieces INTEGER DEFAULT 0, data BLOB NOT NULL)")
    con.close()
    st = ProjectStore(ruta)
    assert st.candado(1) is None and st.tomar_candado(1, "yo:1:1") is None
    assert st.candado(1)[0] == "yo:1:1"


def test_operaciones_del_almacen(tmp_path):
    st = ProjectStore(tmp_path / "s.db")
    assert st.tomar_candado(7, "yo") is None
    assert st.tomar_candado(7, "yo") is None          # el mismo dueño lo re-toma
    assert st.tomar_candado(7, "el") == "yo"          # vivo: no se toma
    assert st.latir_candado(7, "el") is False and st.latir_candado(7, "yo") is True
    st.soltar_candado(7, "el")                         # sólo el dueño suelta
    assert st.candado(7)[0] == "yo"
    _poner_candado(st, 7, "yo", edad_s=31)
    assert st.asegurar_candado(7, "el") == "yo"       # el autosave no roba aunque venza
    assert st.tomar_candado(7, "el") is None          # abrir sí: el latido venció
    assert st.robar_candado(7, "otro", de="yo") is False
    assert st.candado_vivo_ajeno(7, "yo") == "el" and st.candado_vivo_ajeno(7, "el") is None
    assert st.asegurar_candado(8, "yo") is None       # libre: el autosave lo toma
    st.soltar_candado(7, "el")
    assert st.candado(7) is None


def test_borrar_el_proyecto_borra_su_candado(base):
    st, a, _b, _client = base
    _poner_candado(st, a, "yo")
    st.delete(a)
    assert st.candado(a) is None


def test_el_dueno_es_host_pid_puerto_y_fijo_en_el_proceso(monkeypatch):
    yo = candado.dueno()
    assert yo.startswith(f"{socket.gethostname()}:{os.getpid()}:")
    monkeypatch.setenv("APOLO_PORT", "8999")
    assert candado.dueno() == yo  # fijado una vez: el mismo proceso reabre sin 409


def test_el_mensaje_dice_puerto_y_pid():
    assert (candado.mensaje_ocupado(74, "pc:1234:8102")
            == "El proyecto 74 está abierto en el puerto 8102 (pid 1234)")
    assert candado.mensaje_ocupado(5, "pc:99:?") == "El proyecto 5 está abierto en otro proceso (pid 99)"


# ---------------------------------------------------------------------- API
def test_abrir_con_candado_vivo_de_otro_da_409_con_el_mensaje(base):
    st, a, _b, client = base
    _poner_candado(st, a, OTRO, edad_s=5)
    r = client.post(f"/api/projects/{a}/open")
    assert r.status_code == 409
    assert r.json()["detail"] == f"El proyecto {a} está abierto en el puerto 8102 (pid 1234)"
    assert S.project_id is None and S.doc.name == "vacío"  # nada cambió
    assert st.candado(a)[0] == OTRO


def test_un_candado_con_latido_viejo_se_toma(base):
    st, a, _b, client = base
    _poner_candado(st, a, OTRO, edad_s=30)
    r = client.post(f"/api/projects/{a}/open")
    assert r.status_code == 200 and S.project_id == a
    assert st.candado(a)[0] == candado.dueno()


def test_un_pid_muerto_de_esta_maquina_se_toma_aunque_lata_fresco(base):
    """El `--reload` del :8000 mata al worker sin su shutdown: el nuevo no puede esperar."""
    st, a, _b, client = base
    muerto = subprocess.Popen([sys.executable, "-c", "pass"])
    muerto.wait()
    assert not candado.pid_vivo(muerto.pid)
    _poner_candado(st, a, f"{socket.gethostname()}:{muerto.pid}:8000")
    assert client.post(f"/api/projects/{a}/open").status_code == 200
    assert st.candado(a)[0] == candado.dueno()


def test_cambiar_de_proyecto_suelta_el_anterior(base):
    st, a, b, client = base
    assert client.post(f"/api/projects/{a}/open").status_code == 200
    assert st.candado(a)[0] == candado.dueno()
    assert client.post(f"/api/projects/{b}/open").status_code == 200
    assert st.candado(a) is None and st.candado(b)[0] == candado.dueno()
    assert client.post(f"/api/projects/{a}/open").status_code == 200  # el mismo proceso vuelve
    nuevo = client.post("/api/project/new", json={"name": "C"})
    assert nuevo.status_code == 200
    assert st.candado(a) is None and st.candado(S.project_id)[0] == candado.dueno()


def test_un_open_que_falla_no_deja_candado_ni_suelta_el_actual(base):
    st, a, _b, client = base
    client.post(f"/api/projects/{a}/open")
    assert client.post("/api/projects/9999/open").status_code == 404
    assert st.candado(9999) is None and st.candado(a)[0] == candado.dueno()
    assert S.project_id == a


def test_restaurar_una_revision_de_un_proyecto_ajeno_da_409(base):
    st, a, b, client = base
    rev = st.save_revision(a, st.load(a), "r1")
    client.post(f"/api/projects/{b}/open")
    _poner_candado(st, a, OTRO)
    r = client.post(f"/api/revisions/{rev}/restore")
    assert r.status_code == 409 and "8102" in r.json()["detail"]
    assert S.project_id == b and st.candado(b)[0] == candado.dueno()


def test_borrar_un_proyecto_abierto_en_otro_proceso_da_409(base):
    st, a, _b, client = base
    _poner_candado(st, a, OTRO)
    r = client.delete(f"/api/projects/{a}")
    assert r.status_code == 409 and st.exists(a)


def test_el_autosave_sin_candado_no_escribe_y_deja_autosave_error(base):
    st, a, _b, client = base
    client.post(f"/api/projects/{a}/open")
    antes = st.load_bytes(a)
    _poner_candado(st, a, OTRO)  # otro proceso se lo llevó (p. ej. el nuestro se congeló)
    r = client.post("/api/commands", json={"type": "create_box", "params": {"width": 33}})
    assert r.status_code == 200
    api._flush_autosave()
    assert st.load_bytes(a) == antes
    assert S.autosave_error.startswith(f"No se guardó: este proceso perdió el candado del proyecto {a}.")
    assert "puerto 8102 (pid 1234)" in S.autosave_error
    assert client.get("/api/health").json()["autosave_failed"] == S.autosave_error


def test_el_latido_renueva_el_candado(base):
    st, a, _b, client = base
    client.post(f"/api/projects/{a}/open")
    _poner_candado(st, a, candado.dueno(), edad_s=25)
    viejo = st.candado(a)[1]
    hilo = candado.iniciar_latido(lambda: (st, a), intervalo=0.05)
    try:
        fin = time.monotonic() + 5
        while st.candado(a)[1] == viejo and time.monotonic() < fin:
            time.sleep(0.05)
    finally:
        candado.detener_latido()
    assert st.candado(a)[1] > viejo and not hilo.is_alive()


# ------------------------------------------------------------ el :8000 de siempre
def test_el_8000_de_siempre_abre_y_guarda_igual(tmp_path, monkeypatch):
    monkeypatch.delenv("APOLO_PROJECT", raising=False)
    ruta = str(tmp_path / "apolo.db")
    initialize_store(ruta)  # base vacía: crea el «Sin título» y toma su candado
    pid = S.project_id
    assert S.startup_error is None and S.store.candado(pid)[0] == candado.dueno()
    client = TestClient(api.app)
    assert client.post("/api/commands", json={"type": "create_box",
                                              "params": {"width": 21}}).status_code == 200
    api._flush_autosave()
    assert S.autosave_error is None and len(ProjectStore(ruta).load(pid).scene) == 1
    initialize_store(ruta)  # el mismo proceso arranca otra vez: sin 409
    assert S.startup_error is None and S.project_id == pid and len(S.doc.scene) == 1
    candado.soltar(S.store, S.project_id)  # = el shutdown
    assert S.store.candado(pid) is None


def test_el_arranque_con_el_proyecto_tomado_por_otro_deja_startup_error(tmp_path, monkeypatch):
    st = ProjectStore(tmp_path / "f.db")
    pid = st.create(Document("faja"))
    _poner_candado(st, pid, OTRO)
    monkeypatch.setenv("APOLO_PROJECT", str(pid))
    initialize_store(st.path)
    assert S.project_id is None and len(S.doc.commands) == 0
    assert S.startup_error == (f"No se abrió el proyecto {pid} (APOLO_PROJECT): El proyecto "
                               f"{pid} está abierto en el puerto 8102 (pid 1234)")


# ------------------------------------------------------- dos procesos de verdad
_HIJO = """
import os, sys
from apolo.api import candado
from apolo.api.session import S, initialize_store
initialize_store(sys.argv[1])
candado.iniciar_latido(lambda: (S.store, S.project_id), intervalo=0.2)
print("LISTO", os.getpid(), S.project_id, S.startup_error, flush=True)
sys.stdin.readline()
"""


def test_dos_procesos_sobre_la_misma_base(base):
    """Otro proceso abre A (y late); éste recibe el 409 con su pid y puerto, B sí abre. Si
    el otro muere sin soltar (crash o `--reload`), A se toma enseguida. El pid es el que
    informa el hijo: el `python.exe` de un venv en Windows es un lanzador con otro pid."""
    st, a, b, client = base
    env = {**os.environ, "APOLO_PROJECT": str(a), "APOLO_PORT": "8197",
           "APOLO_SANDBOX_PREWARM": "0"}
    hijo = subprocess.Popen([sys.executable, "-B", "-c", _HIJO, st.path], env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    real = None
    try:
        linea = hijo.stdout.readline().split()
        assert linea[:1] == ["LISTO"] and linea[2:] == [str(a), "None"], linea
        real = int(linea[1])
        assert st.candado(a)[0] == f"{socket.gethostname()}:{real}:8197"
        r = client.post(f"/api/projects/{a}/open")
        assert r.status_code == 409
        assert r.json()["detail"] == f"El proyecto {a} está abierto en el puerto 8197 (pid {real})"
        assert client.post(f"/api/projects/{b}/open").status_code == 200
        latido = st.candado(a)[1]
        fin = time.monotonic() + 10
        while st.candado(a)[1] == latido and time.monotonic() < fin:
            time.sleep(0.1)
        assert st.candado(a)[1] > latido  # el otro late
    finally:
        if real is not None:
            os.kill(real, signal.SIGTERM)  # muere sin soltar (en Windows, TerminateProcess)
        hijo.kill()
        hijo.wait(timeout=30)
    fin = time.monotonic() + 10
    while candado.pid_vivo(real) and time.monotonic() < fin:
        time.sleep(0.1)
    assert st.candado(a)[0].endswith(f":{real}:8197")  # murió sin soltar
    assert client.post(f"/api/projects/{a}/open").status_code == 200
    assert st.candado(a)[0] == candado.dueno() and st.candado(b) is None
