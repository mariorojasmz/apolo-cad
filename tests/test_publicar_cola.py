"""`publicar youtube --cola` (el subidor) y su tarea diaria (plan fabrica-de-publicaciones, F3).

Una tienda falsa en un hilo con la cola de la bitácora «T» (GET de la cola, reserva atómica con
409, PUT del resultado) que sirve también el video y la miniatura de cada máquina; YouTube es el
Google falso de `test_publicar_youtube.py`. La tarea de Windows nunca se instala: `ejecutar`
recibe la línea de `schtasks` y la prueba la mira.
"""

# ruff: noqa: F811 — `google` es un fixture importado de otro test: los tests lo reciben por nombre
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from test_publicar_youtube import (  # noqa: F401 — `google` es un fixture
    REFRESH,
    VIDEO,
    _cli,
    _sin_navegador,
    google,
)

from apolo import paths
from apolo.publicacion import cola_youtube as cola
from apolo.publicacion import tarea_cola
from apolo.publicacion import youtube_oauth as oauth
from apolo.publicacion.tienda import LLAVE_ENV
from apolo.publicacion.youtube_oauth import SinAutorizacion

LLAVE = "apolo_pub_" + "Q7" * 21 + "x"
PNG = b"\x89PNG" + b"m" * 100


class Tienda:
    def __init__(self):
        self.maquinas: dict[int, dict] = {}
        self.archivos: dict[str, bytes] = {}
        self.reservadas: set[int] = set()
        self.reserva_409: set[int] = set()
        self.reservas: list[int] = []
        self.avisos: list[tuple[int, dict]] = []
        self.auth_archivos: list[str | None] = []
        self.al_avisar = None
        self.url = ""

    def cola(self, limite: int) -> list[dict]:
        return [m for i, m in sorted(self.maquinas.items()) if i not in self.reservadas
                and (m["estado"] == "pendiente" or (m["estado"] == "fallo" and m["intentos"] < 3))
                ][:limite]


def _handler(t: Tienda):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def _json(self, status, cuerpo):
            data = json.dumps(cuerpo).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _autorizado(self) -> bool:
            return self.headers.get("Authorization") == f"Bearer {LLAVE}"

        def do_GET(self):
            ruta = self.path.split("?")[0]
            if ruta.startswith("/publico/"):  # las URL públicas: sin llave
                t.auth_archivos.append(self.headers.get("Authorization"))
                data = t.archivos.get(ruta)
                if data is None:
                    return self._json(404, {"error": "no existe"})
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                return self.wfile.write(data)
            if not self._autorizado():
                return self._json(401, {"error": "Llave inválida, vencida o revocada."})
            if ruta == "/api/maquina/youtube/cola":
                limite = int(parse_qs(urlsplit(self.path).query).get("limite", ["6"])[0])
                return self._json(200, {"ok": True, "maquinas": t.cola(limite)})
            self._json(404, {"error": f"no existe {ruta}"})

        def do_POST(self):
            partes = self.path.strip("/").split("/")
            if not self._autorizado():
                return self._json(401, {"error": "Llave inválida, vencida o revocada."})
            ident = int(partes[2])
            t.reservas.append(ident)
            if ident in t.reserva_409 or ident in t.reservadas:
                return self._json(409, {"error": "Otra la tomó."})
            t.reservadas.add(ident)
            t.maquinas[ident]["estado"] = "subiendo"
            self._json(200, {"ok": True, "maquina": ident, "reservada_hasta": "2026-10-22T05:30"})

        def do_PUT(self):
            ident = int(self.path.strip("/").split("/")[2])
            cuerpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if not self._autorizado():
                return self._json(401, {"error": "Llave inválida."})
            t.avisos.append((ident, cuerpo))
            m = t.maquinas[ident]
            if cuerpo["resultado"] in ("fallo", "cupo") and ident not in t.reservadas:
                return self._json(409, {"error": "No está reservada."})
            t.reservadas.discard(ident)
            if cuerpo["resultado"] == "subido":
                m["estado"] = "subido"
            elif cuerpo["resultado"] == "fallo":
                m["estado"], m["intentos"] = "fallo", m["intentos"] + 1
            else:
                m["estado"] = "pendiente"
            if t.al_avisar:
                t.al_avisar(ident, cuerpo)
            self._json(200, {"ok": True})

    return H


@pytest.fixture
def tienda(monkeypatch, tmp_path):
    t = Tienda()
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _handler(t))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    t.url = f"http://127.0.0.1:{servidor.server_address[1]}"
    temporal = tmp_path / "temporales"
    temporal.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temporal))
    t.temporal = temporal
    yield t
    servidor.shutdown()
    servidor.server_close()


def _maquina(t: Tienda, ident: int, slug: str, *, sha: str | None = None) -> dict:
    video = VIDEO + bytes([ident])  # cada una, su video (y su sha256)
    t.archivos[f"/publico/{slug}.mp4"] = video
    t.archivos[f"/publico/{slug}.png"] = PNG
    m = {"id": ident, "slug": slug, "titulo": f"Máquina {ident}", "url": f"{t.url}/maquinas/{slug}",
         "estado": "pendiente", "intentos": 0,
         "video": {"url": f"/publico/{slug}.mp4", "bytes": len(video),
                   "sha256": sha or hashlib.sha256(video).hexdigest()},
         "miniatura": {"url": f"{t.url}/publico/{slug}.png", "bytes": len(PNG)},
         "youtube": {"titulo": f"Máquina {ident} — de la tienda",
                     "descripcion": f"Texto que armó la tienda para {slug}.",
                     "etiquetas": ["tienda", slug], "origen": "paquete"}}
    t.maquinas[ident] = m
    return m


def _token(g) -> None:
    oauth.guardar_token(g.credenciales, {"refresh_token": REFRESH})


def _vaciar(t: Tienda, salida: list | None = None, **kw):
    salida = [] if salida is None else salida
    kw.setdefault("abrir", _sin_navegador)
    kw.setdefault("trozo", 4 * 256 * 1024)
    return cola.vaciar(tienda=t.url, llave=LLAVE, eco=salida.append, espera_s=0, **kw)


def _subidas(g) -> int:
    return sum(1 for m, r in g.llamadas if m == "POST" and r == "/upload/youtube/v3/videos")


# ------------------------------------------------------------------ el subidor
def test_cola_vacia_no_toca_youtube(tienda, google):
    salida = []
    r = _vaciar(tienda, salida)
    assert r["subidas"] == [] and r["quedan"] == 0 and tienda.reservas == []
    assert google.llamadas == [] and any("0 máquina(s)" in s for s in salida)


def test_dos_maquinas_subidas_con_los_textos_de_la_tienda(tienda, google):
    _token(google)
    for i, slug in ((1, "mesa"), (2, "faja")):
        _maquina(tienda, i, slug)
    salida = []
    r = _vaciar(tienda, salida)
    assert [s["slug"] for s in r["subidas"]] == ["mesa", "faja"] and r["quedan"] == 0
    assert [(i, c["resultado"]) for i, c in tienda.avisos] == [(1, "subido"), (2, "subido")]
    assert tienda.avisos[0][1] == {"resultado": "subido", "video_id": "VID123",
                                   "url": "https://www.youtube.com/watch?v=VID123",
                                   "privacidad": "private"}
    # los textos, TAL CUAL los dio la tienda (no se recalculan)
    s = google.sesiones[1]["snippet"]
    assert s["title"] == "Máquina 2 — de la tienda" and s["tags"] == ["tienda", "faja"]
    assert s["description"] == "Texto que armó la tienda para faja."
    assert google.recibido == VIDEO + bytes([2]) and google.miniatura == PNG
    assert len(tienda.auth_archivos) == 4  # video (URL relativa) y miniatura de cada una
    # el registro local de subidas y los temporales borrados
    registro = json.loads((google.credenciales / cola.SUBIDAS).read_text(encoding="utf-8"))
    assert {v["slug"] for v in registro.values()} == {"mesa", "faja"}
    assert list(tienda.temporal.iterdir()) == []
    assert any("PRIVADO(s) esperan tu clic" in x for x in salida)
    assert all(LLAVE not in x for x in salida)


def test_reserva_409_se_salta(tienda, google):
    _token(google)
    _maquina(tienda, 1, "mesa")
    _maquina(tienda, 2, "faja")
    tienda.reserva_409 = {1}
    r = _vaciar(tienda)
    assert r["saltadas"] == ["mesa"] and [s["slug"] for s in r["subidas"]] == ["faja"]
    assert [i for i, _c in tienda.avisos] == [2] and _subidas(google) == 1


def test_cupo_en_la_segunda_avisa_cupo_y_para(tienda, google):
    _token(google)
    for i, slug in ((1, "mesa"), (2, "faja"), (3, "puerta")):
        _maquina(tienda, i, slug)
    tienda.al_avisar = lambda _i, _c: setattr(google, "cupo", True)  # tras la primera
    salida = []
    r = _vaciar(tienda, salida)
    assert r["cupo"] and [s["slug"] for s in r["subidas"]] == ["mesa"]
    assert tienda.avisos[1] == (2, {"resultado": "cupo"})
    assert tienda.reservas == [1, 2]  # la tercera, ni reservada
    assert tienda.maquinas[2]["estado"] == "pendiente" and tienda.maquinas[2]["intentos"] == 0
    assert tienda.maquinas[3]["estado"] == "pendiente" and len(tienda.avisos) == 2
    assert r["quedan"] == 2 and any("sigue mañana" in s for s in salida)


def test_sha256_que_no_coincide_es_fallo_y_sigue(tienda, google):
    _token(google)
    _maquina(tienda, 1, "mesa", sha="0" * 64)
    _maquina(tienda, 2, "faja")
    r = _vaciar(tienda)
    assert r["fallidas"] == [{"slug": "mesa", "error": "el sha256 del video bajado no coincide "
                                                       "con el de la tienda"}]
    assert tienda.avisos[0] == (1, {"resultado": "fallo", "error": r["fallidas"][0]["error"]})
    assert tienda.maquinas[1]["intentos"] == 1 and [s["slug"] for s in r["subidas"]] == ["faja"]
    assert list(tienda.temporal.iterdir()) == []


def test_youtube_json_local_avisa_subido_sin_subir(tienda, google, tmp_path):
    """Sin permiso de YouTube y sin navegador: lo ya subido por `publicar youtube` no lo pide."""
    m = _maquina(tienda, 1, "mesa")
    carpeta = tmp_path / "publicaciones" / "mesa" / "1.0.0"
    carpeta.mkdir(parents=True)
    (carpeta / "ficha.json").write_text(json.dumps({
        "video": {"archivo": "video.mp4"},
        "archivos": [{"nombre": "video.mp4", "sha256": m["video"]["sha256"]}]}), encoding="utf-8")
    (carpeta / "youtube.json").write_text(json.dumps({
        "video_id": "LOCAL123456", "url": "https://www.youtube.com/watch?v=LOCAL123456",
        "privacidad": "private"}), encoding="utf-8")
    r = _vaciar(tienda, raiz=tmp_path / "publicaciones")
    assert r["ya_subidas"][0]["video_id"] == "LOCAL123456" and r["subidas"] == []
    assert tienda.avisos == [(1, {"resultado": "subido", "video_id": "LOCAL123456",
                                  "url": "https://www.youtube.com/watch?v=LOCAL123456",
                                  "privacidad": "private"})]
    assert google.llamadas == []


def test_el_registro_de_subidas_evita_el_duplicado(tienda, google):
    """Subido a YouTube pero la tienda no se enteró: la próxima corrida avisa sin resubir."""
    _token(google)
    m = _maquina(tienda, 1, "mesa")
    cola._anotar_subida(google.credenciales, m["video"]["sha256"], "mesa", {
        "video_id": "PREVIO12345", "url": "https://youtu.be/PREVIO12345", "privacidad": "private"})
    r = _vaciar(tienda)
    assert r["ya_subidas"][0]["video_id"] == "PREVIO12345" and _subidas(google) == 0


def test_tarea_sin_permiso_guardado_no_reserva(tienda, google):
    _maquina(tienda, 1, "mesa")
    with pytest.raises(SinAutorizacion, match="--cola --ensayo"):
        _vaciar(tienda, interactivo=False)
    assert tienda.reservas == [] and google.llamadas == []


def test_ensayo_lista_sin_reservar(tienda, google):
    _token(google)
    _maquina(tienda, 1, "mesa")
    salida = []
    _vaciar(tienda, salida, ensayo=True)
    assert tienda.reservas == [] and _subidas(google) == 0
    assert any("Canal: «Apolo CAD»" in s for s in salida) and any("mesa" in s for s in salida)


def test_limite_fuera_de_rango(tienda):
    with pytest.raises(cola.PublicacionError, match="1 a 20"):
        _vaciar(tienda, limite=21)


# ------------------------------------------------------------------ el CLI
def test_cli_la_llave_nunca_entera(tienda, google, monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(paths, "publicaciones_dir", lambda: tmp_path)
    _token(google)
    _maquina(tienda, 1, "mesa")
    monkeypatch.setenv(LLAVE_ENV, LLAVE)
    assert _cli().main(["youtube", "--cola", "--tienda", tienda.url]) == 0
    otra = "apolo_pub_" + "Zz8" * 14 + "y"
    monkeypatch.setenv(LLAVE_ENV, otra)
    assert _cli().main(["youtube", "--cola", "--tienda", tienda.url]) == 2
    salida = capsys.readouterr()
    texto = salida.out + salida.err
    assert "no aceptó la llave" in salida.err and otra[:12] in salida.err
    for llave in (LLAVE, otra):
        assert llave not in texto and llave[12:] not in texto


def test_cli_cola_no_mezcla_con_slug(tienda, capsys):
    assert _cli().main(["youtube", "--cola", "--slug", "mesa"]) == 2
    assert "--cola no usa --slug" in capsys.readouterr().err


# ------------------------------------------------------------------ la tarea diaria
class Ejecutor:
    def __init__(self, codigo: int = 0):
        self.lineas: list[list[str]] = []
        self.codigo = codigo

    def __call__(self, linea, **_kw):
        self.lineas.append(linea)
        return subprocess.CompletedProcess(linea, self.codigo, "", "ERROR: acceso denegado.")


def test_tarea_linea_de_schtasks_con_espacios(tmp_path):
    python = Path("C:/Mis Repos/apolo cad/.venv/Scripts/pythonw.exe")
    script = Path("C:/Mis Repos/apolo cad/scripts/publicar.py")
    ej, salida = Ejecutor(), []
    linea = tarea_cola.instalar(script, hora="03:15", extra=["--limite", "4"], ejecutar=ej,
                                plataforma="win32", leer_llave=lambda _n: LLAVE, python=python,
                                eco=salida.append)
    tr = f'"{python}" -B "{script.resolve()}" youtube --cola --registro --limite 4'
    assert ej.lineas == [linea] == [["schtasks", "/Create", "/SC", "DAILY", "/TN",
                                     "Apolo - cola de YouTube", "/TR", tr, "/ST", "03:15", "/F"]]
    # así la ve schtasks: el /TR entero entre comillas y las de adentro escapadas
    cmd = subprocess.list2cmdline(linea)
    assert f'/TR "\\"{python}\\" -B \\"{script.resolve()}\\" youtube --cola --registro ' \
           '--limite 4"' in cmd
    assert '/TN "Apolo - cola de YouTube"' in cmd
    assert not any("no está en tus variables" in s for s in salida)
    largo = tmp_path / ("x" * 200) / "pythonw.exe"  # schtasks no acepta un /TR de más de 261
    with pytest.raises(cola.PublicacionError, match="261"):
        tarea_cola.instalar(script, ejecutar=ej, plataforma="win32", python=largo)
    assert len(ej.lineas) == 1


def test_tarea_avisa_sin_llave_de_usuario(tmp_path):
    salida = []
    tarea_cola.instalar(tmp_path / "publicar.py", ejecutar=Ejecutor(), plataforma="win32",
                        leer_llave=lambda _n: None, python=tmp_path / "python.exe",
                        entorno={LLAVE_ENV: LLAVE}, eco=salida.append)
    texto = "\n".join(salida)
    assert "no está en tus variables de USUARIO (sólo en esta consola)" in texto
    assert "SetEnvironmentVariable" in texto and LLAVE not in texto
    assert "02:30" in texto  # la hora por defecto


def test_tarea_errores(tmp_path):
    with pytest.raises(cola.PublicacionError, match="Programador de tareas"):
        tarea_cola.instalar(tmp_path / "p.py", ejecutar=Ejecutor(), plataforma="linux")
    with pytest.raises(cola.PublicacionError, match="HH:MM"):
        tarea_cola.instalar(tmp_path / "p.py", hora="25:00", ejecutar=Ejecutor(),
                            plataforma="win32", python=tmp_path / "python.exe")
    with pytest.raises(cola.PublicacionError, match="acceso denegado"):
        tarea_cola.quitar(ejecutar=Ejecutor(1), plataforma="win32")
    ej = Ejecutor()
    assert tarea_cola.quitar(ejecutar=ej, plataforma="win32", eco=lambda *_a: None) == \
        ["schtasks", "/Delete", "/TN", "Apolo - cola de YouTube", "/F"]


def test_cli_instala_la_tarea_con_la_hora(monkeypatch, capsys):
    if not tarea_cola.sys.platform.startswith("win"):
        pytest.skip("la tarea es de Windows")
    ej = Ejecutor()
    assert _cli().main(["youtube", "--cola", "--instalar-tarea", "--hora", "04:05"],
                       ejecutar=ej) == 0
    linea = ej.lineas[0]
    assert linea[linea.index("/ST") + 1] == "04:05"
    tr = linea[linea.index("/TR") + 1]
    assert tr.endswith("youtube --cola --registro") and "publicar.py" in tr
    assert "Tarea «Apolo - cola de YouTube» lista" in capsys.readouterr().out


def test_registro_rota_el_log(tmp_path, capsys):
    log = tmp_path / "logs" / "cola-youtube.log"
    log.parent.mkdir()
    log.write_text("x" * 50, encoding="utf-8")
    with tarea_cola.registro(log, max_bytes=10):
        print("una corrida")
    assert (tmp_path / "logs" / "cola-youtube.log.1").read_text(encoding="utf-8") == "x" * 50
    texto = log.read_text(encoding="utf-8")
    assert "publicar youtube --cola ===" in texto and "una corrida" in texto
    assert capsys.readouterr().out == ""
