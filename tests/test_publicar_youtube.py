"""`publicar youtube` contra un Google falso (plan fabrica-de-publicaciones, F1).

Un `http.server` en un hilo hace de endpoint de tokens de OAuth, de la YouTube Data API
(`channels`) y del servidor de subidas (sesión reanudable y `thumbnails.set`). El navegador se
simula: `abrir` recibe la URL de autorización y, desde otro hilo, llama a la dirección de
retorno en `127.0.0.1` con el código y el `state`, como haría Google tras el clic.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from apolo import paths
from apolo.publicacion import textos
from apolo.publicacion import youtube as yt
from apolo.publicacion import youtube_oauth as oauth
from apolo.publicacion.youtube import CupoAgotado
from apolo.publicacion.youtube_oauth import SinAutorizacion, YoutubeError

RAIZ_REPO = Path(__file__).resolve().parents[1]
SECRETO = "GOCSPX-secreto-del-cliente-0123456789"
CODIGO = "4/0codigo-de-autorizacion-xyz"
REFRESH = "1//0refresh-token-muy-secreto"
ACCESS = ("ya29.access-del-canje", "ya29.access-del-refresco")
SLUG, VERSION = "mesa-de-taller", "1.0.0"
VIDEO = bytes(range(256)) * (3 * 1024 + 4)  # 3 trozos de 256 KiB y un resto


class Google:
    """Estado del Google falso y lo que se puede torcer."""

    def __init__(self):
        self.llamadas: list[tuple[str, str]] = []
        self.canjes: list[dict] = []  # cuerpos del endpoint de tokens
        self.invalid_grant = False
        self.cupo = False
        self.falla_miniatura = False
        self.cortes: set[int] = set()  # n.º de PUT de datos que llegan a medias y dan 503
        self.puts = 0
        self.consultas = 0
        self.metadatos = None
        self.sesiones: list[dict] = []  # los metadatos de cada subida abierta
        self.largo_declarado = None
        self.recibido = b""
        self.miniatura = None
        self.url = ""


def _handler(g: Google):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *_a):
            pass

        def _responder(self, status: int, cuerpo=None, cabeceras=None) -> None:
            data = b"" if cuerpo is None else json.dumps(cuerpo).encode()
            self.send_response(status)
            for k, v in (cabeceras or {}).items():
                self.send_header(k, v)
            if cuerpo is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _cuerpo(self) -> bytes:
            return self.rfile.read(int(self.headers.get("Content-Length") or 0))

        def _autorizado(self) -> bool:
            return self.headers.get("Authorization") in {f"Bearer {a}" for a in ACCESS}

        def do_GET(self):
            ruta = self.path.split("?")[0]
            g.llamadas.append(("GET", ruta))
            if not self._autorizado():
                return self._responder(401, {"error": {"code": 401, "message": "sin permiso"}})
            if ruta == "/youtube/v3/channels":
                q = parse_qs(urlsplit(self.path).query)
                assert q["mine"] == ["true"] and q["part"] == ["snippet"]
                return self._responder(200, {"items": [
                    {"id": "UCapolo", "snippet": {"title": "Apolo CAD"}}]})
            self._responder(404, {"error": {"message": f"no existe {ruta}"}})

        def do_POST(self):
            ruta = self.path.split("?")[0]
            g.llamadas.append(("POST", ruta))
            cuerpo = self._cuerpo()
            if ruta == "/token":
                return self._token({k: v[0] for k, v in parse_qs(cuerpo.decode()).items()})
            if not self._autorizado():
                return self._responder(401, {"error": {"code": 401, "message": "sin permiso"}})
            if ruta == "/upload/youtube/v3/videos":
                q = parse_qs(urlsplit(self.path).query)
                assert q["uploadType"] == ["resumable"] and q["part"] == ["snippet,status"]
                if g.cupo:
                    return self._responder(403, {"error": {"code": 403, "message": "quota", "errors": [
                        {"reason": "quotaExceeded", "domain": "youtube.quota"}]}})
                g.metadatos = json.loads(cuerpo)
                g.largo_declarado = self.headers.get("X-Upload-Content-Length")
                g.sesiones.append(g.metadatos)  # una sesión nueva empieza de cero (la cola sube varias)
                g.recibido = b""
                return self._responder(200, cabeceras={"Location": f"{g.url}/sesion/1"})
            if ruta == "/upload/youtube/v3/thumbnails/set":
                if g.falla_miniatura:
                    return self._responder(403, {"error": {"code": 403, "message": (
                        "The authenticated user doesn't have permissions to upload and set "
                        "custom video thumbnails."), "errors": [{"reason": "forbidden"}]}})
                assert parse_qs(urlsplit(self.path).query)["videoId"] == ["VID123"]
                g.miniatura = cuerpo
                return self._responder(200, {"items": []})
            self._responder(404, {"error": {"message": f"no existe {ruta}"}})

        def _token(self, datos: dict):
            g.canjes.append(datos)
            assert datos["client_id"] == "cid.apps.googleusercontent.com"
            assert datos["client_secret"] == SECRETO
            if datos["grant_type"] == "authorization_code":
                assert datos["code"] == CODIGO and datos["redirect_uri"].startswith("http://127.0.0.1:")
                return self._responder(200, {
                    "access_token": ACCESS[0], "refresh_token": REFRESH, "expires_in": 3599,
                    "token_type": "Bearer", "scope": " ".join(oauth.SCOPES)})
            if g.invalid_grant:
                return self._responder(400, {"error": "invalid_grant",
                                             "error_description": "Token has been expired or revoked."})
            assert datos["refresh_token"] == REFRESH
            self._responder(200, {"access_token": ACCESS[1], "expires_in": 3599})

        def do_PUT(self):
            g.llamadas.append(("PUT", self.path))
            assert self.path == "/sesion/1" and self._autorizado()
            datos = self._cuerpo()
            total = int(g.largo_declarado)
            rango = self.headers["Content-Range"]
            if rango == f"bytes */{total}":
                g.consultas += 1
            else:
                g.puts += 1
                ini, fin = (int(x) for x in re.match(r"bytes (\d+)-(\d+)/\d+$", rango).groups())
                assert ini == len(g.recibido) and fin - ini + 1 == len(datos), rango
                if g.puts in g.cortes:  # llega la mitad (en granos de 256 KiB) y se cae
                    g.recibido += datos[: len(datos) // 2 // yt.GRANO * yt.GRANO]
                    return self._responder(503, {"error": {"message": "backend error"}})
                g.recibido += datos
            if len(g.recibido) == total:
                return self._responder(200, {"id": "VID123", "status": {"uploadStatus": "uploaded"}})
            cab = {"Range": f"bytes=0-{len(g.recibido) - 1}"} if g.recibido else {}
            self._responder(308, cabeceras=cab)

    return H


@pytest.fixture
def google(tmp_path, monkeypatch):
    g = Google()
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _handler(g))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    g.url = f"http://127.0.0.1:{servidor.server_address[1]}"
    credenciales = tmp_path / "credenciales"
    credenciales.mkdir()
    (credenciales / oauth.CLIENTE).write_text(json.dumps({"installed": {
        "client_id": "cid.apps.googleusercontent.com", "client_secret": SECRETO,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"]}}), encoding="utf-8")
    monkeypatch.setenv(oauth.DIR_ENV, str(credenciales))
    for clave, ruta in (("api", "/youtube/v3"), ("upload", "/upload/youtube/v3"),
                        ("token", "/token"), ("auth", "/auth")):
        monkeypatch.setenv(oauth.ENTORNO[clave], g.url + ruta)
    g.credenciales = credenciales
    yield g
    servidor.shutdown()
    servidor.server_close()


@pytest.fixture
def paquete(tmp_path) -> Path:
    carpeta = tmp_path / "publicaciones" / SLUG / VERSION
    carpeta.mkdir(parents=True)
    (carpeta / "ficha.json").write_text(json.dumps({
        "formato": 1, "titulo": "Mesa de taller", "slug": SLUG, "version": VERSION,
        "descripcion": "Una mesa de taller soldada.", "nivel": "gratis", "precio_usd": 0,
        "etiquetas": ["mesa", "taller"], "url_tienda": "",
        "video": {"archivo": "video.mp4", "duracion_s": 60.0,
                  "capitulos": [{"inicio_s": 0, "titulo": "Patas"},
                                {"inicio_s": 15, "titulo": "Tablero"},
                                {"inicio_s": 30, "titulo": "En cifras"}],
                  "musica": {"titulo": "Seno", "autor": "Prueba", "fuente": "La suite",
                             "licencia": "CC0 1.0", "atribucion": ""}},
        "miniatura": "miniatura.png"}), encoding="utf-8")
    (carpeta / "video.mp4").write_bytes(VIDEO)
    (carpeta / "miniatura.png").write_bytes(b"\x89PNG" + b"m" * 100)
    return carpeta


class Navegador:
    """Lo que hace la persona en el navegador: vuelve a la dirección de retorno con el código."""

    def __init__(self, state: str | None = None):
        self.urls: list[str] = []
        self.state = state

    def __call__(self, url: str) -> bool:
        self.urls.append(url)
        q = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        params = {"code": CODIGO, "state": self.state or q["state"],
                  "scope": " ".join(oauth.SCOPES)}
        threading.Thread(target=lambda: httpx.get(q["redirect_uri"], params=params, timeout=10),
                         daemon=True).start()
        return True


def _sin_navegador(url: str) -> bool:
    raise AssertionError("no debía abrir el navegador")


def _subir(paquete, salida: list | None = None, **kw):
    salida = [] if salida is None else salida
    kw.setdefault("abrir", Navegador())
    kw.setdefault("trozo", yt.GRANO)
    return yt.subir(paquete, tienda="https://apolocad.com", eco=salida.append, espera_s=0,
                    espera_navegador_s=10, **kw)


def _token_guardado(g: Google) -> None:
    oauth.guardar_token(g.credenciales, {"refresh_token": REFRESH})


# ------------------------------------------------------------------ el permiso
def test_autoriza_sube_y_no_imprime_secretos(google, paquete, capsys):
    nav, salida = Navegador(), []
    r = _subir(paquete, salida, abrir=nav)
    texto = "\n".join(salida) + capsys.readouterr().out
    for secreto in (SECRETO, CODIGO, REFRESH, *ACCESS):
        assert secreto not in texto
    # la autorización: PKCE S256, state, permiso offline y los dos scopes
    q = {k: v[0] for k, v in parse_qs(urlsplit(nav.urls[0]).query).items()}
    assert nav.urls[0].startswith(google.url + "/auth?")
    assert q["code_challenge_method"] == "S256" and q["access_type"] == "offline"
    assert q["prompt"] == "consent" and q["scope"].split() == list(oauth.SCOPES)
    canje = google.canjes[0]
    reto = base64.urlsafe_b64encode(hashlib.sha256(canje["code_verifier"].encode()).digest())
    assert reto.decode().rstrip("=") == q["code_challenge"]
    assert canje["redirect_uri"] == q["redirect_uri"]
    # el token queda guardado con el canal
    token = json.loads((google.credenciales / oauth.TOKEN).read_text(encoding="utf-8"))
    assert token["refresh_token"] == REFRESH and token["canal"]["titulo"] == "Apolo CAD"
    assert "access_token" not in token
    # el canal se dice antes de subir; el video llega entero y privado
    assert any("Subiendo al canal «Apolo CAD»" in s for s in salida)
    assert google.recibido == VIDEO and google.puts == 4
    assert r["nuevo"] and r["video_id"] == "VID123" and r["privacidad"] == "private"
    guardado = json.loads((paquete / yt.RESULTADO).read_text(encoding="utf-8"))
    assert guardado["url"] == "https://www.youtube.com/watch?v=VID123"
    assert guardado["canal"] == "Apolo CAD" and guardado["titulo"] == "Mesa de taller"
    assert guardado["miniatura"] is True and google.miniatura.startswith(b"\x89PNG")


def test_los_metadatos_salen_de_la_misma_fuente_que_youtube_txt(google, paquete):
    _subir(paquete)
    m = google.metadatos
    assert m["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False}
    s = m["snippet"]
    assert s["categoryId"] == "28" and s["defaultLanguage"] == s["defaultAudioLanguage"] == "es"
    assert s["title"] == "Mesa de taller" and s["tags"] == ["mesa", "taller"]
    # el enlace a la tienda (derivado del slug: la ficha no trae url_tienda), capítulos y música
    assert f"https://apolocad.com/maquinas/{SLUG}" in s["description"]
    assert "00:15 Tablero" in s["description"] and "Música: «Seno» de Prueba" in s["description"]
    ficha = json.loads((paquete / "ficha.json").read_text(encoding="utf-8"))
    d = yt.datos(ficha, "https://apolocad.com")
    caps = [(c["inicio_s"], c["titulo"]) for c in ficha["video"]["capitulos"]]
    txt = textos.youtube({**ficha, "url_tienda": f"https://apolocad.com/maquinas/{SLUG}"}, caps,
                         ficha["video"]["musica"])
    assert d["descripcion"] == s["description"] and d["descripcion"] in txt
    assert google.largo_declarado == str(len(VIDEO))


def test_url_tienda_de_la_ficha_gana(google, paquete):
    ficha = json.loads((paquete / "ficha.json").read_text(encoding="utf-8"))
    ficha["url_tienda"] = "https://tienda.example/mesa"
    assert "https://tienda.example/mesa" in yt.datos(ficha, "https://apolocad.com")["descripcion"]


def test_el_bloque_youtube_de_ficha_json_va_tal_cual(google, paquete):
    """F2: `generar` deja en ficha.json el texto ya validado (el mismo de youtube.txt y el que
    sube la cola de la tienda); la subida no lo vuelve a armar. Uno que no cumple, no sube."""
    ficha = json.loads((paquete / "ficha.json").read_text(encoding="utf-8"))
    ficha["youtube"] = {"titulo": "Mesa de taller", "descripcion": "Texto ya armado.",
                        "etiquetas": ["mesa de taller"]}
    (paquete / "ficha.json").write_text(json.dumps(ficha), encoding="utf-8")
    _subir(paquete)
    s = google.metadatos["snippet"]
    assert s["description"] == "Texto ya armado." and s["tags"] == ["mesa de taller"]
    ficha["youtube"]["descripcion"] = "ñ" * 2501
    from apolo.publicacion.paquete import PublicacionError

    with pytest.raises(PublicacionError, match="bytes UTF-8"):
        yt.datos(ficha, "https://apolocad.com")


def test_refresca_sin_navegador(google, paquete):
    _token_guardado(google)
    r = _subir(paquete, abrir=_sin_navegador)
    assert r["nuevo"] and [c["grant_type"] for c in google.canjes] == ["refresh_token"]


def test_invalid_grant_pide_reautorizar(google, paquete, capsys):
    _token_guardado(google)
    google.invalid_grant = True
    with pytest.raises(SinAutorizacion, match="--reautorizar") as exc:
        _subir(paquete, abrir=_sin_navegador)
    assert REFRESH not in str(exc.value) and SECRETO not in str(exc.value)
    assert not (paquete / yt.RESULTADO).exists()


def test_reautorizar_borra_el_token_y_abre_el_navegador(google, paquete):
    oauth.guardar_token(google.credenciales, {"refresh_token": "1//viejo"})
    nav = Navegador()
    _subir(paquete, abrir=nav, reautorizar=True)
    assert len(nav.urls) == 1 and google.canjes[0]["grant_type"] == "authorization_code"
    assert oauth.leer_token(google.credenciales)["refresh_token"] == REFRESH


def test_state_distinto_se_rechaza(google, paquete):
    with pytest.raises(YoutubeError, match="state"):
        _subir(paquete, abrir=Navegador(state="otro-state"))
    assert google.canjes == [] and not (google.credenciales / oauth.TOKEN).exists()


def test_sin_client_secret_explica_como_crearlo(google, paquete):
    (google.credenciales / oauth.CLIENTE).unlink()
    with pytest.raises(YoutubeError, match="App de escritorio"):
        _subir(paquete)
    assert google.llamadas == []


# ------------------------------------------------------------------ la subida
def test_corte_a_mitad_retoma_por_rango(google, paquete):
    _token_guardado(google)
    google.cortes = {1}  # el primer trozo (512 KiB) llega a medias: sigue desde 256 KiB
    salida = []
    r = _subir(paquete, salida, trozo=2 * yt.GRANO)
    assert r["nuevo"] and google.recibido == VIDEO
    assert google.consultas == 1 and any("reintento" in s for s in salida)


def test_corte_de_red_retoma(google, paquete, monkeypatch):
    _token_guardado(google)
    real = httpx.Client.request
    caidas = [0]

    def request(self, metodo, url, **kw):
        if metodo == "PUT" and "bytes 262144-" in (kw.get("headers") or {}).get(
                "Content-Range", "") and not caidas[0]:
            caidas[0] += 1
            raise httpx.ReadTimeout("se cayó la red")
        return real(self, metodo, url, **kw)

    monkeypatch.setattr(httpx.Client, "request", request)
    assert _subir(paquete)["nuevo"] and google.recibido == VIDEO and google.consultas == 1


def test_miniatura_falla_es_aviso(google, paquete):
    _token_guardado(google)
    google.falla_miniatura = True
    salida = []
    r = _subir(paquete, salida)
    assert r["nuevo"] and r["miniatura"] is False
    assert any(s.startswith("Aviso: la miniatura no se subió") for s in salida)
    assert json.loads((paquete / yt.RESULTADO).read_text(encoding="utf-8"))["video_id"] == "VID123"


def test_cupo_agotado(google, paquete):
    _token_guardado(google)
    google.cupo = True
    with pytest.raises(CupoAgotado, match="(?i)cupo diario de YouTube agotado.*medianoche"):
        _subir(paquete)
    assert not (paquete / yt.RESULTADO).exists() and google.puts == 0


def test_no_resube_salvo_forzar(google, paquete):
    previo = {"video_id": "VIEJO", "url": yt.url_video("VIEJO"), "privacidad": "private",
              "canal": "Apolo CAD", "subido_en": "2026-10-21T10:00:00", "titulo": "Mesa"}
    (paquete / yt.RESULTADO).write_text(json.dumps(previo), encoding="utf-8")
    salida = []
    r = _subir(paquete, salida, abrir=_sin_navegador)
    assert not r["nuevo"] and r["video_id"] == "VIEJO" and google.llamadas == []
    assert any("--forzar" in s for s in salida)
    _token_guardado(google)
    r = _subir(paquete, forzar=True)
    assert r["nuevo"] and r["video_id"] == "VID123"


def test_ensayo_no_sube(google, paquete):
    _token_guardado(google)
    salida = []
    r = _subir(paquete, salida, ensayo=True)
    texto = "\n".join(salida)
    assert not r["nuevo"] and "Canal: «Apolo CAD»" in texto and "Ensayo: no subí nada." in texto
    assert f"https://apolocad.com/maquinas/{SLUG}" in texto and "mesa, taller" in texto
    assert not any(ruta.startswith("/upload") for _m, ruta in google.llamadas)
    assert google.puts == 0 and not (paquete / yt.RESULTADO).exists()


def test_publico_con_flag(google, paquete):
    _token_guardado(google)
    r = _subir(paquete, publico=True)
    assert r["privacidad"] == "public"
    assert google.metadatos["status"]["privacyStatus"] == "public"


# ------------------------------------------------------------------ el CLI
def _cli():
    spec = importlib.util.spec_from_file_location("publicar_cli",
                                                  RAIZ_REPO / "scripts" / "publicar.py")
    mod = importlib.util.module_from_spec(spec)
    previo = sys.dont_write_bytecode
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = previo
    return mod


def test_cli_sube_sin_imprimir_secretos(google, paquete, monkeypatch, capsys):
    monkeypatch.setattr(paths, "publicaciones_dir", lambda: paquete.parents[1])

    assert _cli().main(["youtube", "--slug", SLUG], abrir=Navegador()) == 0
    salida = capsys.readouterr()
    texto = salida.out + salida.err
    assert "Subiendo al canal «Apolo CAD»" in salida.out and "PRIVADO" in salida.out
    for secreto in (SECRETO, CODIGO, REFRESH, *ACCESS):
        assert secreto not in texto
    assert (paquete / yt.RESULTADO).exists()


def test_cli_cupo_sale_con_2(google, paquete, monkeypatch, capsys):
    monkeypatch.setattr(paths, "publicaciones_dir", lambda: paquete.parents[1])
    _token_guardado(google)
    google.cupo = True
    assert _cli().main(["youtube", "--slug", SLUG, "--version", VERSION]) == 2
    assert "Cupo diario de YouTube agotado" in capsys.readouterr().err
