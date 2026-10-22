"""El DWG como requisito chequeado y los entregables en paralelo con el video (plan
video-tienda-pulido, F3: D5 y D6).

D5: `GET /api/health` publica si hay ODA File Converter; `publicar guion` y `generar` lo avisan
al EMPEZAR, con el enlace de descarga, y el paquete sale sin DWG diciéndolo en el LEEME. Los
endpoints DWG se niegan antes de componer láminas (eran minutos de HLR bajo `STATE_LOCK`).
D6: `EnFondo` pide los entregables en un hilo mientras quien llama renderiza; con la API en el
mismo proceso (estos tests) `generar` va en serie, así que el hilo se prueba con un cliente falso.
"""

from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from test_publicacion_e2e import _cli, _mesa, aprobar_calidad, con_ffmpeg

import apolo.api.main as api
import apolo.drawing as drawing
import apolo.drawing.dwg as dwg_mod
from apolo.doc import Document
from apolo.projects import ProjectStore
from apolo.publicacion import flujo
from apolo.publicacion.entregables import EnFondo, Entregable, Recolector, lista, omitidos
from apolo.publicacion.paquete import PublicacionError

DWG = "planos/juego_dwg.zip"


def _sin_oda(monkeypatch):
    monkeypatch.setattr(dwg_mod, "_discover", lambda roots=None: False)


# ── D5: la API dice si puede, y se niega sin trabajar ─────────────────────────


@pytest.mark.parametrize("hay", [True, False])
def test_health_publica_si_hay_con_que_exportar_dwg(monkeypatch, hay):
    monkeypatch.setattr(dwg_mod, "_discover", lambda roots=None: hay)
    api.DOC = Document("salud")
    dwg = TestClient(api.app).get("/api/health").json()["dwg"]
    if hay:
        assert dwg == {"disponible": True, "aviso": None}
    else:
        assert dwg["disponible"] is False and dwg_mod.ODA_URL in dwg["aviso"]


@pytest.mark.parametrize("pedir", [
    lambda c: c.get("/api/drawingset.dwg"),
    lambda c: c.post("/api/drawing/spec", json={"format": "dwg"}),
])
def test_sin_oda_el_dwg_se_niega_antes_de_componer_laminas(monkeypatch, pedir):
    _sin_oda(monkeypatch)
    compuestas = []
    for nombre in ("sheet_set", "compose_sheet"):
        monkeypatch.setattr(drawing, nombre, lambda *a, _n=nombre, **k: compuestas.append(_n))
    api.DOC = Document("dwg")
    c = TestClient(api.app)
    c.post("/api/commands", json={"type": "create_box", "params": {"name": "Placa"}})
    r = pedir(c)
    assert r.status_code == 400 and dwg_mod.ODA_URL in r.json()["detail"]
    assert compuestas == []


def test_omitidos_lee_la_capacidad_de_la_salud():
    todos = lista(1, "x")
    aviso = {"disponible": False, "aviso": "falta ODA"}
    assert omitidos({"dwg": aviso}, todos) == {DWG: "falta ODA"}
    assert omitidos({"dwg": {"disponible": True, "aviso": None}}, todos) == {}
    assert omitidos({}, todos) == {}  # una API vieja no la niega: se pide como siempre


# ── D6: el hilo de los entregables ────────────────────────────────────────────


class _Resp:
    def __init__(self, ruta: str, ok: bool):
        self.ruta, self.ok, self.content = ruta, ok, b"ok" if ok else b""

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"{self.ruta} reventó")

    def json(self):
        return {"ok": True}


class _Lenta:
    """Un cliente falso: cada petición tarda `s` y responde bien, salvo las rutas de `fallan`."""

    def __init__(self, s=0.15, fallan=()):
        self.s, self.fallan, self.pedidas, self.hilos = s, set(fallan), [], set()

    def request(self, metodo, ruta, **_kw):
        self.pedidas.append(ruta)
        self.hilos.add(threading.current_thread().name)
        time.sleep(self.s)
        return _Resp(ruta, ruta not in self.fallan)


def _tres(opcional_c=True):
    E = Entregable
    return [E("A", "a", "GET", "/a", "a.bin", "bytes"),
            E("A", "b", "GET", "/b", "b.bin", "bytes", opcional=True, requiere="dwg"),
            E("A", "c", "GET", "/c", "c.json", "json", opcional=opcional_c)]


def test_en_fondo_pide_en_su_hilo_y_devuelve_en_orden(tmp_path):
    cli = _Lenta()
    t0 = time.perf_counter()
    en = EnFondo(Recolector(cli, tmp_path, eco=False), _tres(), omitir={"b.bin": "sin ODA"})
    assert time.perf_counter() - t0 < 0.1  # vuelve en seguida: el trabajo es del hilo
    regs = en.esperar()
    assert [(r["file"], r["status"]) for r in regs] == [
        ("a.bin", "ok"), ("b.bin", "skip"), ("c.json", "ok")]
    assert regs[1]["note"] == "sin ODA" and cli.pedidas == ["/a", "/c"]  # el omitido no se pide
    assert cli.hilos == {"entregables"} and not en.grave.is_set()
    assert en.segundos >= 2 * cli.s and (tmp_path / "a.bin").read_bytes() == b"ok"


def test_en_serie_lo_trae_todo_antes_de_volver(tmp_path):
    cli = _Lenta(s=0.0)
    en = EnFondo(Recolector(cli, tmp_path, eco=False), _tres(), paralelo=False)
    assert len(en.registros) == 3 and cli.hilos == {threading.current_thread().name}
    assert en.esperar() is en.registros


def test_un_grave_prende_la_alarma_pero_se_intentan_todos(tmp_path):
    cli = _Lenta(s=0.0, fallan={"/a", "/c"})
    en = EnFondo(Recolector(cli, tmp_path, eco=False), _tres(opcional_c=False))
    regs = en.esperar()
    assert en.grave.is_set() and cli.pedidas == ["/a", "/b", "/c"]
    assert [r["status"] for r in regs] == ["error", "ok", "error"]
    with pytest.raises(PublicacionError, match=r"(?s)- a: .*- c: "):
        flujo._exigir(en)


def test_un_opcional_que_falla_no_es_grave(tmp_path):
    en = EnFondo(Recolector(_Lenta(s=0.0, fallan={"/b"}), tmp_path, eco=False), _tres())
    assert [r["status"] for r in flujo._exigir(en)] == ["ok", "error", "ok"]
    assert not en.grave.is_set()


def test_cancelar_no_pide_mas_y_un_error_del_hilo_vuelve_a_quien_espera(tmp_path):
    cli = _Lenta(s=0.2)
    en = EnFondo(Recolector(cli, tmp_path, eco=False), _tres())
    en.cancelar()
    en.esperar()
    assert cli.pedidas == ["/a"]  # el que estaba en vuelo termina; el resto no se pide

    class _Rota(Recolector):
        def traer(self, entregables):
            raise RuntimeError("se cortó la red")

    en = EnFondo(_Rota(cli, tmp_path, eco=False), _tres())
    with pytest.raises(RuntimeError, match="se cortó la red"):
        en.esperar()
    assert en.grave.is_set()


# ── D5 de punta a punta: aviso al empezar, sin pedirlo, y el LEEME lo dice ─────


@pytest.fixture()
def mesa(tmp_path):
    api.DOC = Document("vacío")
    api.STORE = ProjectStore(tmp_path / "proyectos.db")
    try:
        yield SimpleNamespace(c=TestClient(api.app), raiz=tmp_path / "publicaciones",
                              verde=api.STORE.create(_mesa()))
    finally:
        api._autosave_sched.cancel()
        api.STORE = None
        api.PROJECT_ID = None


@con_ffmpeg
def test_sin_oda_avisa_al_empezar_y_el_paquete_lo_dice(mesa, monkeypatch):
    _sin_oda(monkeypatch)
    dichos = []
    r = flujo.guion(mesa.c, mesa.verde, raiz=mesa.raiz, eco=dichos.append)
    assert len(r["avisos"]) == 1 and dichos[0] == r["avisos"][0]  # lo primero que se dice
    assert "juego de planos (DWG zip)" in dichos[0] and dwg_mod.ODA_URL in dichos[0]
    _achicar(r, mesa.c)

    pedidas = []
    real = mesa.c.request
    monkeypatch.setattr(mesa.c, "request", lambda m, ruta, **kw: pedidas.append(ruta)
                        or real(m, ruta, **kw))
    dichos.clear()
    res = flujo.generar(mesa.c, mesa.verde, raiz=mesa.raiz, eco=dichos.append)
    assert dwg_mod.ODA_URL in next(d for d in dichos if d.startswith("Aviso:"))
    assert "/api/drawingset.dwg" not in pedidas and "/api/drawingset.pdf" in pedidas
    dwg = next(x for x in res["registros"] if x["file"] == DWG)
    assert dwg["status"] == "skip" and dwg_mod.ODA_URL in dwg["note"]
    assert any("DWG" in x for x in res["faltantes"]) and res["paralelo"] is False
    leeme = {n: (res["carpeta"] / n / "LEEME.md").read_text(encoding="utf-8")
             for n in ("gratis", "completo")}
    assert "> Esta versión no trae los planos en DWG" in leeme["completo"]
    assert "DWG" not in leeme["gratis"]  # el gratis nunca lo trajo
    assert "espera de entregables" not in res["tiempos_s"]


def _achicar(r: dict, cliente) -> None:
    """Lo que hace una persona tras `guion` (como `_preparar` de test_publicacion_e2e): video
    chico y corto, ficha con descripción; y la puerta de publicación aprobada (sin ella, `generar`
    se niega: puerta-de-publicacion D8)."""
    aprobar_calidad(cliente, r["carpeta"])
    g = json.loads(r["guion"].read_text(encoding="utf-8"))
    g["video"].update(ancho=320, alto=180)
    for parte in ("portada", "cifras", "orbita", "cierre"):
        g[parte]["duracion_s"] = 1.0
    for e in g["etapas"]:
        e["duracion_s"] = 1.5
    r["guion"].write_text(json.dumps(g, ensure_ascii=False), encoding="utf-8")
    texto = r["ficha"].read_text(encoding="utf-8")
    r["ficha"].write_text(texto.replace('descripcion: ""', 'descripcion: "Mesa de taller."'),
                          encoding="utf-8")


class _PorTurnos:
    """El `TestClient` atendido por turnos con el trabajo local: la API de los tests vive en
    este proceso y su VTK/OCCT no puede correr a la vez que el del video (por eso `generar`
    va en serie con un cliente prestado). Así se ejercita el camino paralelo sin ese riesgo."""

    def __init__(self, c, turno, fallar=None):
        self.c, self.turno, self.fallar, self.hilos = c, turno, fallar, {}

    def request(self, metodo, ruta, **kw):
        self.hilos.setdefault(ruta, threading.current_thread().name)
        if self.fallar and ruta in self.fallar[0]:
            self.fallar[1].wait(30)  # cae cuando el video ya empezó
            raise RuntimeError("la API se cayó")
        with self.turno:
            return self.c.request(metodo, ruta, **kw)


def _por_turnos(mesa, monkeypatch, fallar=None) -> _PorTurnos:
    turno = threading.Lock()
    real = flujo._lo_local

    def local(*a, **k):
        with turno:
            return real(*a, **k)

    monkeypatch.setattr(flujo, "_lo_local", local)
    return _PorTurnos(mesa.c, turno, fallar)


@con_ffmpeg
def test_en_paralelo_los_entregables_van_en_su_hilo(mesa, monkeypatch):
    _achicar(flujo.guion(mesa.c, mesa.verde, raiz=mesa.raiz, eco=None), mesa.c)
    cli = _por_turnos(mesa, monkeypatch)
    res = flujo.generar(cli, mesa.verde, raiz=mesa.raiz, eco=None, paralelo=True)
    assert res["paralelo"] is True and "espera de entregables" in res["tiempos_s"]
    assert cli.hilos["/api/drawingset.pdf"] == "entregables"
    assert cli.hilos["/api/delivery-check"] == threading.current_thread().name
    assert (res["carpeta"] / "ficha.json").is_file() and (res["carpeta"] / "video.mp4").is_file()
    assert {r["status"] for r in res["registros"] if r["file"] != DWG} == {"ok"}


@con_ffmpeg
def test_en_paralelo_un_entregable_caido_aborta_el_video(mesa, monkeypatch):
    from apolo.publicacion import video as videos

    _achicar(flujo.guion(mesa.c, mesa.verde, raiz=mesa.raiz, eco=None), mesa.c)
    empezo, abortado = threading.Event(), []
    real = videos.renderizar

    def renderizar(*a, **k):
        empezo.set()
        try:
            return real(*a, **k)
        except PublicacionError as exc:
            abortado.append(str(exc))
            raise

    monkeypatch.setattr(videos, "renderizar", renderizar)
    rutas = {e.ruta for e in lista(mesa.verde, "x")}
    cli = _por_turnos(mesa, monkeypatch, fallar=(rutas, empezo))
    with pytest.raises(PublicacionError, match="Faltan entregables") as exc:
        flujo.generar(cli, mesa.verde, raiz=mesa.raiz, eco=None, paralelo=True)
    assert abortado and "juego de planos (PDF)" in str(exc.value)  # se cortó DENTRO del video
    carpeta = mesa.raiz / "mesa-de-taller" / "1.0.0"
    assert not (carpeta / "ficha.json").exists() and not (carpeta / ".generando").exists()


def test_el_cli_va_en_paralelo_solo_con_su_propio_cliente(monkeypatch):
    vistos = []
    monkeypatch.setattr(flujo, "generar", lambda *a, **k: vistos.append(k["paralelo"]))
    cli = _cli()
    assert cli.main(["generar", "--project", "1"], cliente=object()) == 0
    assert cli.main(["generar", "--project", "1", "--url", "http://127.0.0.1:9"]) == 0
    assert vistos == [False, True]
