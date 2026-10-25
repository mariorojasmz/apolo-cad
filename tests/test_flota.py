"""`scripts/flota.py`: varias APIs a la vez, una máquina por proceso (plan
`docs/plans/varias-maquinas-a-la-vez.md`, F3).

Los de `flota_viva` levantan DOS uvicorn reales en puertos libres desde `BASE_PUERTOS` (uno ocupado a
propósito, para ver que lo salta), sobre una base NUEVA en tmp (nunca `data/apolo.db` ni el
`:8000`), con el worker del sandbox apagado para no pagar su RAM dos veces. Arrancan una vez por
módulo (~1 min, casi todo el import de cada proceso) y el último test los PARA: va al final y
en orden. El finalizer los mata aunque algo falle: no quedan procesos vivos.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from apolo.doc import Document
from apolo.projects import ProjectStore

RAIZ = Path(__file__).resolve().parents[1]

# Con pytest-xdist, el módulo entero en UN worker y en su orden (`--dist loadgroup`, lo fija el
# conftest): repartido, cada worker armaría su `flota_viva` y dos `puertos_libres(1, 8150)` a la
# vez devuelven el mismo puerto (el `bind` del tapón o el uvicorn del otro revienta); y
# `test_parar…` tiene que correr después de los que usan la flota.
pytestmark = pytest.mark.xdist_group("flota")

#: Base de los puertos de ESTE proceso de pytest. Con una base fija (8150), dos suites a la vez en
#: la misma máquina (dos sesiones, dos carriles) buscaban en el mismo tramo: entre que una ve un
#: puerto libre y su uvicorn lo enlaza, el de la otra se lo gana («puerto 8152: abrió maquina-b,
#: no el 1»). Por pid caen en tramos distintos de 20000–27996, fuera del efímero de Windows
#: (49152+) y del de Linux (32768+); `puertos_libres` igual salta lo ocupado.
BASE_PUERTOS = 20000 + (os.getpid() % 2000) * 4


def _cargar_flota():
    spec = importlib.util.spec_from_file_location("flota_cli", RAIZ / "scripts" / "flota.py")
    modulo = importlib.util.module_from_spec(spec)
    sys.modules["flota_cli"] = modulo  # dataclasses/annotations lo buscan por nombre
    spec.loader.exec_module(modulo)
    return modulo


flota = _cargar_flota()
so = flota.so

# ── sin procesos ─────────────────────────────────────────────────────────────


def test_tope_d8_es_el_minimo_de_cpu_y_ram():
    gb = 2**30
    # la PC de Mario en F0: 12 núcleos lógicos y 4,5 GB libres → min(6, 5) = 5
    assert flota.tope(nucleos=12, ram_libre=4.5 * gb)[0] == 5
    assert flota.tope(nucleos=12, ram_libre=64 * gb, vivos=4)[0] == 2  # los vivos gastan CPU
    assert flota.tope(nucleos=12, ram_libre=0.5 * gb)[0] == 0
    assert flota.tope(nucleos=1, ram_libre=64 * gb)[0] == 0
    cabe, texto = flota.tope(nucleos=8, ram_libre=None)
    assert cabe == 4 and "GB" not in texto  # sin dato de RAM manda el CPU


def test_el_tope_rechaza_un_n_excesivo_sin_lanzar_nada(monkeypatch, tmp_path):
    monkeypatch.setattr(so, "nucleos_logicos", lambda: 4)
    monkeypatch.setattr(so, "ram_libre_bytes", lambda: 100 * 2**30)
    with pytest.raises(flota.TopeExcedido, match=r"caben 2 procesos más y pides 3"):
        flota.arrancar([1, 2, 3], db=str(tmp_path / "no-existe.db"), d=tmp_path)
    assert not (tmp_path / "flota.json").exists()
    # la CLI sale con 2 y lo dice
    assert flota.main(["--dir", str(tmp_path), "arrancar", "1", "2", "3"]) == 2


def test_el_tope_real_rechaza_uno_mas_de_los_que_caben(tmp_path):
    cabe, _ = flota.tope()
    with pytest.raises(flota.TopeExcedido):
        flota.arrancar(list(range(1, cabe + 2)), db=str(tmp_path / "x.db"), d=tmp_path)


def test_problema_de_dueno_ve_el_zombie_y_el_proceso_ajeno():
    padres = {40: 4, 4: 1, 41: 40}  # 4 = lanzador, 40 = API, 41 = worker del sandbox
    assert flota.problema_de_dueno(8100, 40, 4, {8100: {40}}, padres) is None
    assert "zombie" in flota.problema_de_dueno(8100, 40, 4, {8100: {40, 77}}, padres)
    assert "nadie" in flota.problema_de_dueno(8100, 40, 4, {}, padres)
    assert "no es de los que lanzó" in flota.problema_de_dueno(8100, 40, 9, {8100: {40}},
                                                               {**padres, 9: 1})


def test_puertos_libres_saltan_el_8000_los_que_escuchan_y_los_evitados():
    escuchando = so.escuchas()
    puertos = flota.puertos_libres(3, 7998, evitar={7999})
    assert flota.PUERTO_SESION not in puertos and 7999 not in puertos
    assert not set(puertos) & set(escuchando)
    assert puertos == sorted(puertos) and len(set(puertos)) == 3


def test_el_arbol_de_este_proceso_lo_contiene():
    assert os.getpid() in so.arbol(os.getppid())
    assert so.vivo(os.getpid())
    assert so.arbol(-5) == set()


def test_un_pid_reciclado_no_sigue_vivo():
    """La identidad es pid + hora de creación: el MISMO pid con otra hora es otro proceso (el SO
    recicló el pid del muerto) y `parar` no debe darlo por vivo."""
    yo = os.getpid()
    firma = so.firmas([yo])
    assert firma[yo] is not None and so.siguen_vivos(firma) == [yo]
    assert so.siguen_vivos({yo: firma[yo] - 1}) == []  # nació en otra hora: no es el de la firma
    assert so.siguen_vivos({-5: None}) == []


def test_un_hijo_mas_viejo_que_su_padre_no_es_del_arbol(monkeypatch):
    """Windows deja el ppid VIEJO en un huérfano: si ese pid se recicla, el «hijo» nació antes
    que su supuesto padre y no es suyo (matarlo sería matar un proceso ajeno)."""
    monkeypatch.setattr(so, "_ES_WINDOWS", True)
    horas = {1: 100, 2: 200, 3: 300, 4: 50}  # 4 nació antes que 2: su ppid=2 es un pid reciclado
    monkeypatch.setattr(so, "creado", horas.get)
    assert so.arbol(1, {1: 0, 2: 1, 3: 2, 4: 2}) == {1, 2, 3}


def test_deshacer_espera_que_muera_el_arbol_y_suelta_cada_candado(monkeypatch, tmp_path):
    """El «nada» de `arrancar`: `taskkill` vuelve con el árbol aún terminando, así que espera por
    la firma; y suelta el candado de CUALQUIER pid del árbol (sin preguntarle a un health que,
    con la máquina cargada, no contesta a tiempo), ya con el árbol muerto."""
    db = tmp_path / "base.db"
    st = ProjectStore(db)
    a, b = st.create(Document("a")), st.create(Document("b"))
    assert st.tomar_candado(a, "host:41:8101") is None  # la API (nieto del lanzador 4)
    assert st.tomar_candado(b, "host:77:8101") is None  # otro proceso, mismo puerto: no se toca
    monkeypatch.setattr(so, "padres", lambda: {4: 1, 40: 4, 41: 40})
    monkeypatch.setattr(so, "creado", lambda pid: 1000 + pid)
    muertos: list[int] = []
    vueltas = iter([[40, 41], [41], []])  # tarda dos miradas en irse

    def siguen_vivos(firma):
        assert firma == {4: 1004, 40: 1040, 41: 1041}  # firma tomada ANTES de matar
        vivos = next(vueltas)
        if vivos:  # mientras agoniza, su candado sigue ahí: se suelta después
            assert st.candado(a) is not None
        return vivos

    monkeypatch.setattr(so, "siguen_vivos", siguen_vivos)
    monkeypatch.setattr(so, "matar_arbol", lambda raiz, gracia_s=0.0: muertos.append(raiz))
    assert flota._deshacer([(8101, 4)], str(db)) == []
    assert muertos == [4]
    assert st.candado(a) is None and st.candado(b)[0] == "host:77:8101"


def test_deshacer_devuelve_lo_que_no_murio(monkeypatch, tmp_path):
    monkeypatch.setattr(so, "padres", lambda: {4: 1, 40: 4})
    monkeypatch.setattr(so, "matar_arbol", lambda raiz, gracia_s=0.0: None)
    monkeypatch.setattr(so, "siguen_vivos", lambda firma: [40])
    assert flota._deshacer([(8101, 4)], str(tmp_path / "x.db"), espera_s=0.0) == [40]


def test_estado_no_confunde_un_pid_reciclado_con_un_colgado(tmp_path):
    """Una entrada cuyo pid hoy es de OTRO proceso (otra hora de creación) está caída, no
    colgada; y `parar` no lo cuenta ni lo mata."""
    import subprocess

    ajeno = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        hora = so.creado(ajeno.pid)
        libre = flota.puertos_libres(1, BASE_PUERTOS + 2)[0]  # nadie contesta su health
        entrada = {"puerto": libre, "url": f"http://127.0.0.1:{libre}", "proyecto": {"id": 1},
                   "pid": ajeno.pid, "lanzador": ajeno.pid, "creado": hora - 1,
                   "creado_lanzador": hora - 1, "db": str(tmp_path / "x.db"),
                   "mcp": str(tmp_path / "mcp.json")}
        flota._escribir(tmp_path, [entrada])
        assert flota.estado(tmp_path)[0]["estado"] == "caído"
        flota._escribir(tmp_path, [{**entrada, "creado": hora}])
        assert flota.estado(tmp_path)[0]["estado"] == "colgado"  # el mismo, sin health
        flota._escribir(tmp_path, [entrada])
        (r,) = flota.parar(tmp_path, espera_s=0.0)
        assert r["ok"] and r["procesos_vivos"] == [] and flota.leer(tmp_path) == []
        assert ajeno.poll() is None  # el que heredó el pid sigue vivo: no era de la flota
    finally:
        so.matar_arbol(ajeno.pid)
        ajeno.wait(30)


def test_arrancar_rechaza_un_proyecto_inexistente_sin_lanzar(tmp_path):
    db = tmp_path / "base.db"
    pid = ProjectStore(db).create(Document("unico"))
    with pytest.raises(flota.FlotaError, match=r"No existen .*\[999\]"):
        flota.arrancar([pid, 999], db=str(db), d=tmp_path, forzar=True)
    with pytest.raises(flota.FlotaError, match="repetidos"):
        flota.arrancar([pid, pid], db=str(db), d=tmp_path, forzar=True)
    assert not (tmp_path / "flota.json").exists()


def test_apolo_logs_manda_en_la_carpeta_de_logs(monkeypatch, tmp_path):
    from apolo import paths

    monkeypatch.setenv("APOLO_LOGS", str(tmp_path))
    assert paths.logs_dir() == tmp_path
    monkeypatch.delenv("APOLO_LOGS")
    assert paths.logs_dir().name == "logs"


def test_parar_un_puerto_que_no_es_de_la_flota_da_error(tmp_path):
    with pytest.raises(flota.FlotaError, match="No son de la flota"):
        flota.parar(tmp_path, [8123])


def test_soltar_candados_borra_solo_los_de_ese_dueno(tmp_path):
    db = tmp_path / "base.db"
    st = ProjectStore(db)
    a, b = st.create(Document("a")), st.create(Document("b"))
    assert st.tomar_candado(a, "host:111:8101") is None
    assert st.tomar_candado(b, "host:222:8102") is None
    assert flota.candados_de(str(db), 111, 8101) == [a]
    assert flota.soltar_candados(str(db), 111, 8101) == [a]
    assert st.candado(a) is None and st.candado(b)[0] == "host:222:8102"


# ── dos procesos reales ──────────────────────────────────────────────────────


def _post(url: str) -> tuple[int, dict]:
    pedido = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(pedido, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


@pytest.fixture(scope="module")
def flota_viva(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("flota")
    db = carpeta / "apolo.db"
    st = ProjectStore(db)
    ids = [st.create(Document(n)) for n in ("maquina-a", "maquina-b", "maquina-c")]
    ocupado = flota.puertos_libres(1, BASE_PUERTOS)[0]
    tapon = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tapon.bind(("127.0.0.1", ocupado))
    tapon.listen(1)
    d = carpeta / "estado"
    try:
        nuevas = flota.arrancar(ids[:2], puerto_base=ocupado, db=str(db), d=d, forzar=True,
                                timeout_s=240, entorno={"APOLO_SANDBOX_PREWARM": "0",
                                                         "APOLO_LOGS": str(carpeta / "logs")})
        yield {"d": d, "db": db, "ids": ids, "ocupado": ocupado, "entradas": nuevas,
               "logs": carpeta / "logs"}
    finally:
        tapon.close()
        try:
            flota.parar(d)
        finally:  # red: lo que parar no pudo con, a la fuerza
            for e in flota.leer(d):
                for raiz in (e["lanzador"], e["pid"]):
                    if so.vivo(raiz):
                        so.matar_arbol(raiz)


def test_arranca_dos_en_puertos_libres_saltando_el_ocupado(flota_viva):
    entradas = flota_viva["entradas"]
    puertos = [e["puerto"] for e in entradas]
    assert len(set(puertos)) == 2 and flota_viva["ocupado"] not in puertos
    assert min(puertos) > flota_viva["ocupado"] and flota.PUERTO_SESION not in puertos
    for e, pid_proyecto in zip(entradas, flota_viva["ids"][:2], strict=True):
        h = flota.health(e["puerto"])
        assert h["pid"] == e["pid"] and h["puerto"] == e["puerto"]
        assert h["proyecto"]["id"] == pid_proyecto and not h["startup_error"]
        # el dueño REAL del puerto es el pid de health y cuelga del que lanzó la flota
        assert so.escuchas()[e["puerto"]] == {e["pid"]}
        assert e["pid"] in so.arbol(e["lanzador"])
    assert [e["puerto"] for e in flota.leer(flota_viva["d"])] == sorted(puertos)


def test_estado_los_ve_con_pid_puerto_y_proyecto(flota_viva, capsys):
    filas = flota.estado(flota_viva["d"])
    assert [(f["estado"], f["proyecto"]["id"]) for f in filas] == [
        ("vivo", i) for i in flota_viva["ids"][:2]]
    assert flota.main(["--dir", str(flota_viva["d"]), "estado", "--json"]) == 0
    impreso = json.loads(capsys.readouterr().out)
    assert {f["pid"] for f in impreso} == {e["pid"] for e in flota_viva["entradas"]}


def test_abrir_un_proyecto_tomado_por_otro_proceso_da_409(flota_viva):
    a, b = flota_viva["entradas"]
    codigo, cuerpo = _post(f"{a['url']}/api/projects/{b['proyecto']['id']}/open")
    assert codigo == 409
    assert cuerpo["detail"] == (f"El proyecto {b['proyecto']['id']} está abierto en el puerto "
                                f"{b['puerto']} (pid {b['pid']})")
    # el 409 quedó en el log de la prueba (APOLO_LOGS), firmado por quien lo dio
    log = (flota_viva["logs"] / "errors.log").read_text(encoding="utf-8")
    assert f"pid={a['pid']} puerto={a['puerto']}" in log
    # cada proceso tiene SU candado, con su pid y su puerto
    st = ProjectStore(flota_viva["db"])
    for e in (a, b):
        assert st.candado(e["proyecto"]["id"])[0].endswith(f":{e['pid']}:{e['puerto']}")
    # uno libre sí abre (y suelta el anterior, que queda para otro)
    libre = flota_viva["ids"][2]
    codigo, _ = _post(f"{a['url']}/api/projects/{libre}/open")
    assert codigo == 200
    assert st.candado(a["proyecto"]["id"]) is None
    assert flota.candados_de(str(flota_viva["db"]), a["pid"], a["puerto"]) == [libre]
    assert flota.estado(flota_viva["d"])[0]["proyecto"]["id"] == libre


def test_los_mcp_json_son_validos(flota_viva):
    for e in flota_viva["entradas"]:
        cfg = json.loads(Path(e["mcp"]).read_text(encoding="utf-8"))
        servidor = cfg["mcpServers"]["apolo-cad"]
        assert list(cfg["mcpServers"]) == ["apolo-cad"]  # las tools se llaman igual que siempre
        assert Path(servidor["command"]).is_file()
        assert servidor["args"][-2:] == ["-m", "apolo.mcp_server"]
        assert servidor["env"]["APOLO_URL"] == e["url"] == f"http://127.0.0.1:{e['puerto']}"
        assert Path(e["mcp"]).name == f"mcp-{e['puerto']}.json"


def test_parar_mata_el_arbol_y_suelta_los_candados(flota_viva):
    """Va AL FINAL del módulo: deja la flota vacía (el finalizer queda en no-op)."""
    entradas = flota_viva["entradas"]
    padres = so.padres()
    arbol = set().union(*(so.arbol(e["lanzador"], padres) for e in entradas))
    assert {e["pid"] for e in entradas} <= arbol
    firma = so.firmas(arbol)  # pid + hora de creación: el pid solo lo recicla otro proceso
    res = flota.parar(flota_viva["d"])
    assert all(r["ok"] for r in res), res
    assert so.siguen_vivos(firma) == []
    escuchas = so.escuchas()
    assert not any(e["puerto"] in escuchas for e in entradas)
    st = ProjectStore(flota_viva["db"])
    for i in flota_viva["ids"]:
        assert st.candado(i) is None
    assert flota.leer(flota_viva["d"]) == []
    assert not any(Path(e["mcp"]).exists() for e in entradas)


def test_si_uno_no_arranca_no_queda_ninguno(tmp_path, monkeypatch):
    """Todo o nada: el segundo encuentra su proyecto tomado por un dueño vivo (este proceso de
    pytest) y arranca con `startup_error`; la flota mata a los dos y no anota nada. El dueño
    LATE mientras tanto: un arranque de más de 30 s (la suite completa carga la máquina) lo
    daría por muerto y el hijo tomaría el candado con todo derecho.

    «No queda ninguno» se mide sobre lo que la flota lanzó y mató (pid + hora de creación de
    cada árbol, tomada justo antes de matarlo), no sobre todos los hijos de este proceso: en la
    suite completa, otro hilo de este worker puede lanzar su propio proceso a mitad del test."""
    import threading

    lanzados: list = []
    lanzar = flota._lanzar
    monkeypatch.setattr(flota, "_lanzar",
                        lambda *a, **kw: lanzados.append(lanzar(*a, **kw)) or lanzados[-1])
    matados: dict[int, int | None] = {}
    matar = so.matar_arbol

    def matar_espiando(raiz, **kw):
        matados.update(so.firmas(so.arbol(raiz)))
        return matar(raiz, **kw)

    monkeypatch.setattr(so, "matar_arbol", matar_espiando)

    db = tmp_path / "apolo.db"
    st = ProjectStore(db)
    libre, tomado = st.create(Document("libre")), st.create(Document("tomado"))
    dueno = f"{socket.gethostname()}:{os.getpid()}:9"
    assert st.tomar_candado(tomado, dueno) is None
    basta = threading.Event()

    def latir():
        while not basta.wait(5.0):
            st.latir_candado(tomado, dueno)

    latido = threading.Thread(target=latir, daemon=True)
    latido.start()
    try:
        with pytest.raises(flota.FlotaError, match=f"El proyecto {tomado} está abierto"):
            flota.arrancar([libre, tomado], puerto_base=BASE_PUERTOS, db=str(db), d=tmp_path,
                           forzar=True, timeout_s=240,
                           entorno={"APOLO_SANDBOX_PREWARM": "0",
                                    "APOLO_LOGS": str(tmp_path / "logs")})
    finally:
        basta.set()
        latido.join()
        if (tmp_path / "flota.json").exists():  # arrancó lo que no debía: que no quede vivo
            flota.parar(tmp_path)
    assert not (tmp_path / "flota.json").exists()
    # arrancar volvió con TODO lo suyo muerto: los dos lanzadores y sus árboles (la API real)
    assert len(lanzados) == 2 and all(p.poll() is not None for p in lanzados)
    # <= y no <: en Windows el python.exe del venv es un lanzador que abre al intérprete real
    # (el árbol suma un hijo); en Linux el lanzado ES la API y el árbol es él solo (CI).
    assert {p.pid for p in lanzados} <= set(matados)
    assert so.siguen_vivos(matados) == [], {p: so.creado(p) for p in so.siguen_vivos(matados)}
    assert st.candado(libre) is None and st.candado(tomado)[0] == dueno
    assert not list(tmp_path.glob("mcp-*.json"))

