"""El permiso de YouTube de `publicar youtube` (plan fabrica-de-publicaciones, F1 y D3): OAuth de
app instalada con httpx y la biblioteca estándar, sin las bibliotecas de Google.

Las credenciales viven en `~/.apolo/youtube/` (`APOLO_HOME`; `APOLO_YOUTUBE_DIR` la cambia),
fuera del repo:

  - `client_secret.json`: el cliente OAuth «de escritorio» (formato `installed`) que se baja de
    Google Cloud; lo pone una persona y este módulo sólo lo lee;
  - `token.json`: el token de refresco y el canal elegido; lo escribe este módulo al autorizar.

La primera vez se abre el navegador: la respuesta vuelve a un servidor de un solo pedido en
`http://127.0.0.1:<puerto libre>/`, con PKCE S256 y un `state` aleatorio que se verifica. Las
siguientes se refresca el access token sin navegador. Nada de esto se imprime ni se loguea: ni
el client_secret, ni el código, ni los tokens (los mensajes de error pasan por `_ocultar`).
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import secrets
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

from apolo.publicacion.paquete import PublicacionError

DIR_ENV = "APOLO_YOUTUBE_DIR"
CLIENTE = "client_secret.json"
TOKEN = "token.json"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3"
#: Variables que cambian cada extremo (los tests apuntan a servidores falsos).
ENTORNO = {"api": "APOLO_YOUTUBE_API", "upload": "APOLO_YOUTUBE_UPLOAD",
           "token": "APOLO_GOOGLE_TOKEN_URL", "auth": "APOLO_GOOGLE_AUTH_URL"}
#: Subir videos y leer el canal elegido (para mostrar su nombre antes de subir).
SCOPES = ("https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly")
ESPERA_NAVEGADOR_S = 300.0
REAUTORIZAR = "Vuelve a autorizar con --reautorizar (se abre el navegador; elige el canal «Apolo CAD»)."


class YoutubeError(PublicacionError):
    """YouTube o Google rechazaron un paso; el mensaje nunca trae secretos."""


class SinAutorizacion(YoutubeError):
    """El permiso guardado ya no sirve (`invalid_grant`): hay que volver a autorizar."""


@dataclass(frozen=True)
class Extremos:
    api: str
    upload: str
    token: str
    auth: str


def extremos(cliente: dict | None = None, entorno=None, **dados) -> Extremos:
    """Cada extremo: el parámetro, la variable de `ENTORNO`, el del `client_secret.json`
    (`auth_uri`, `token_uri`) o el de Google, en ese orden."""
    entorno = os.environ if entorno is None else entorno
    cliente = cliente or {}
    por_omision = {"api": API, "upload": UPLOAD, "token": cliente.get("token_uri") or TOKEN_URL,
                   "auth": cliente.get("auth_uri") or AUTH_URL}
    return Extremos(**{k: (dados.get(k) or entorno.get(ENTORNO[k]) or v).rstrip("/")
                       for k, v in por_omision.items()})


def carpeta(entorno=None) -> Path:
    """Dónde están `client_secret.json` y `token.json`."""
    from apolo import paths

    entorno = os.environ if entorno is None else entorno
    if entorno.get(DIR_ENV):
        return Path(entorno[DIR_ENV]).expanduser()
    return paths.home() / "youtube"


def leer_cliente(dir_: Path) -> dict:
    """{client_id, client_secret, auth_uri, token_uri} del `client_secret.json` de escritorio."""
    ruta = Path(dir_) / CLIENTE
    como = ("Créalo en Google Cloud (proyecto apolo-publicador): APIs y servicios → Credenciales "
            "→ Crear credenciales → ID de cliente de OAuth, tipo «App de escritorio» → Descargar "
            f"JSON, y guárdalo como {ruta}.")
    if not ruta.is_file():
        raise YoutubeError(f"Falta el cliente OAuth de YouTube ({ruta}).\n  {como}")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise YoutubeError(f"No pude leer {ruta} ({type(exc).__name__}).\n  {como}") from None
    cliente = datos.get("installed") if isinstance(datos, dict) else None
    if not isinstance(cliente, dict) or not cliente.get("client_id") \
            or not cliente.get("client_secret"):
        raise YoutubeError(f"{ruta} no es un cliente OAuth «App de escritorio» (falta "
                           f"`installed` con client_id y client_secret).\n  {como}")
    return {k: cliente.get(k) for k in ("client_id", "client_secret", "auth_uri", "token_uri")}


def _ocultar(texto: str, *secretos) -> str:
    for s in secretos:
        if s:
            texto = texto.replace(str(s), "…")
    return texto


# ------------------------------------------------------------------ token.json
def leer_token(dir_: Path) -> dict | None:
    ruta = Path(dir_) / TOKEN
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return datos if isinstance(datos, dict) and datos.get("refresh_token") else None


def guardar_token(dir_: Path, datos: dict) -> None:
    """Escribe `token.json` de una vez (temporal + reemplazo), sólo para el dueño donde el
    sistema lo permite (0600; en Windows rige el perfil del usuario)."""
    dir_ = Path(dir_)
    dir_.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = dir_ / f".{TOKEN}.{os.getpid()}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, dir_ / TOKEN)
    with contextlib.suppress(OSError):
        os.chmod(dir_ / TOKEN, 0o600)


def anotar_canal(dir_: Path, canal: dict) -> None:
    """Guarda en `token.json` el canal que eligió quien autorizó (id y título)."""
    token = leer_token(dir_)
    if token is not None and token.get("canal") != canal:
        guardar_token(dir_, {**token, "canal": canal})


# ------------------------------------------------------------------ el endpoint de tokens
def _token(http, ext: Extremos, cliente: dict, datos: dict, que: str) -> dict:
    import httpx

    secretos = (cliente["client_secret"], datos.get("code"), datos.get("refresh_token"),
                datos.get("code_verifier"))
    cuerpo = {"client_id": cliente["client_id"], "client_secret": cliente["client_secret"],
              **datos}
    try:
        resp = http.post(ext.token, data=cuerpo, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        raise YoutubeError(f"No pude {que}: Google no responde ({type(exc).__name__}).") from None
    try:
        r = resp.json()
    except ValueError:
        r = {}
    r = r if isinstance(r, dict) else {}
    if resp.status_code < 400 and r.get("access_token"):
        return r
    codigo = str(r.get("error") or resp.status_code)
    detalle = _ocultar(str(r.get("error_description") or ""), *secretos)[:300]
    if codigo == "invalid_grant":
        raise SinAutorizacion(f"Google ya no acepta el permiso guardado al {que} (invalid_grant: "
                              f"revocado, vencido o de otro cliente). {REAUTORIZAR}")
    if codigo in ("invalid_client", "unauthorized_client"):
        raise YoutubeError(f"Google no reconoce el cliente OAuth al {que} ({codigo}): baja otra "
                           f"vez el {CLIENTE} de Google Cloud y reemplázalo.")
    raise YoutubeError(f"Google rechazó {que} ({resp.status_code}, {codigo})"
                       + (f": {detalle}" if detalle else "."))


class Permiso:
    """El access token vigente; `renovar()` pide otro con el token de refresco."""

    def __init__(self, http, ext: Extremos, cliente: dict, refresh: str, access: str = ""):
        self.http, self.ext, self.cliente, self._refresh = http, ext, cliente, refresh
        self._access = access

    def cabeceras(self) -> dict:
        if not self._access:
            self.renovar()
        return {"Authorization": f"Bearer {self._access}"}

    def renovar(self) -> None:
        r = _token(self.http, self.ext, self.cliente,
                   {"grant_type": "refresh_token", "refresh_token": self._refresh},
                   "renovar el permiso de YouTube")
        self._access = r["access_token"]


def permiso(http, dir_: Path, ext: Extremos, cliente: dict, *, reautorizar: bool = False,
            eco=print, abrir=webbrowser.open, espera_s: float = ESPERA_NAVEGADOR_S) -> Permiso:
    """El permiso listo para usar: el guardado (refrescado, sin navegador) o uno nuevo. Con
    `reautorizar` se borra el guardado antes."""
    if reautorizar:
        with contextlib.suppress(FileNotFoundError):
            (Path(dir_) / TOKEN).unlink()
            eco("Borré el permiso guardado: vuelvo a pedirlo en el navegador.")
    token = leer_token(dir_)
    if token is not None:
        p = Permiso(http, ext, cliente, token["refresh_token"])
        p.renovar()
        return p
    refresh, access, alcance = autorizar(http, ext, cliente, eco=eco, abrir=abrir,
                                         espera_s=espera_s)
    guardar_token(dir_, {"refresh_token": refresh, "scopes": alcance,
                         "autorizado_en": datetime.now().isoformat(timespec="seconds")})
    eco(f"Permiso guardado en {Path(dir_) / TOKEN} (no lo compartas ni lo subas a git).")
    return Permiso(http, ext, cliente, refresh, access)


# ------------------------------------------------------------------ la autorización
def _pagina(titulo: str, texto: str) -> bytes:
    return (f"<!doctype html><meta charset=utf-8><title>Apolo CAD</title>"
            f"<body style='font-family:sans-serif;margin:3em'><h2>{titulo}</h2>"
            f"<p>{texto}</p></body>").encode()


class _Retorno(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 — nombre de http.server
        q = {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}
        if "code" in q or "error" in q:
            self.server.retorno = q
            ok = "code" in q
            cuerpo, status = _pagina(
                "Permiso recibido" if ok else "No se recibió el permiso",
                "Ya puedes cerrar esta pestaña y volver a la consola."), 200
        else:
            cuerpo, status = _pagina("Apolo CAD", "Esta dirección espera la respuesta de Google."), 404
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *_a):  # la query trae el código: nada a la consola
        pass


def _esperar(servidor: HTTPServer, espera_s: float) -> dict:
    fin = time.monotonic() + espera_s
    while servidor.retorno is None:
        resta = fin - time.monotonic()
        if resta <= 0:
            raise YoutubeError(f"No llegó la respuesta del navegador en {espera_s / 60:.0f} min: "
                               "vuelve a correr el comando y acepta el permiso.")
        servidor.timeout = resta
        servidor.handle_request()
    return servidor.retorno


def autorizar(http, ext: Extremos, cliente: dict, *, eco=print, abrir=webbrowser.open,
              espera_s: float = ESPERA_NAVEGADOR_S) -> tuple[str, str, str]:
    """La primera autorización en el navegador. Devuelve (refresh, access, scopes)."""
    verificador = secrets.token_urlsafe(64)
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest())
    state = secrets.token_urlsafe(24)
    servidor = HTTPServer(("127.0.0.1", 0), _Retorno)
    servidor.retorno = None
    try:
        retorno_url = f"http://127.0.0.1:{servidor.server_address[1]}/"
        url = ext.auth + "?" + urlencode({
            "client_id": cliente["client_id"], "redirect_uri": retorno_url,
            "response_type": "code", "scope": " ".join(SCOPES),
            "code_challenge": reto.decode().rstrip("="), "code_challenge_method": "S256",
            "state": state, "access_type": "offline", "prompt": "consent"})
        eco("Autoriza a Apolo en el navegador: entra con la cuenta de Google del canal y elige "
            "el canal «Apolo CAD» (no el personal). Si el navegador no se abre, abre esta "
            f"dirección:\n  {url}")
        with contextlib.suppress(Exception):
            abrir(url)
        q = _esperar(servidor, espera_s)
    finally:
        servidor.server_close()
    if not secrets.compare_digest(str(q.get("state") or ""), state):
        raise YoutubeError("La respuesta del navegador no trae el `state` de este pedido: la "
                           "rechacé (una pestaña vieja o un pedido ajeno). Vuelve a correr el "
                           "comando.")
    if "code" not in q:
        raise YoutubeError(f"No se dio el permiso en el navegador ({q.get('error')}): vuelve a "
                           "correr el comando y acepta las dos casillas.")
    r = _token(http, ext, cliente, {"grant_type": "authorization_code", "code": q["code"],
                                    "redirect_uri": retorno_url, "code_verifier": verificador},
               "canjear el permiso")
    alcance = str(r.get("scope") or " ".join(SCOPES))
    if SCOPES[0] not in alcance.split():
        raise YoutubeError("El permiso llegó sin «Subir videos de YouTube» (la casilla quedó sin "
                           "marcar). " + REAUTORIZAR)
    if not r.get("refresh_token"):
        raise YoutubeError("Google no entregó un token de refresco: quita el acceso de «Apolo» en "
                           "tu cuenta de Google (Seguridad → Apps con acceso) y vuelve a autorizar "
                           "con --reautorizar.")
    return r["refresh_token"], r["access_token"], alcance
