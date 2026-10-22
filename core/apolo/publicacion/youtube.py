"""Sube a YouTube el video de un paquete ya generado (plan fabrica-de-publicaciones, F1).

Cliente HTTP puro, como `tienda.py`: lee la carpeta que dejó `publicar generar`
(`publicaciones_dir()/<slug>/<version>/`: `ficha.json`, `video.mp4`, `miniatura.png`) y habla
con la YouTube Data API v3 con el permiso de `youtube_oauth` (D3). Pasos:

  1. si la carpeta ya tiene `youtube.json` con su `video_id`, no resube (salvo `forzar`);
  2. el permiso (el guardado, refrescado; o el navegador la primera vez) y el canal
     (`channels.list?mine=true`): se imprime a qué canal se sube antes de subir;
  3. la subida reanudable: la sesión con los metadatos y el archivo por trozos desde disco;
     un corte o un 5xx pregunta a YouTube cuánto recibió y sigue desde ahí;
  4. la miniatura (`thumbnails.set`): si falla es un AVISO, el video ya subió;
  5. `youtube.json` con {video_id, url, privacidad, canal, subido_en, titulo}.

Título, descripción y etiquetas son el bloque `youtube` de `ficha.json` (F2), la misma fuente
que `youtube.txt`; un paquete de antes lo arma con `textos.datos_youtube` (sin `url_tienda` en
la ficha, el enlace es `<tienda>/maquinas/<slug>`). Privado
salvo `publico` (D4: YouTube deja privado lo que sube un proyecto sin auditar). El cupo diario
agotado es `CupoAgotado`, un estado esperable, y no deja `youtube.json`.
"""

from __future__ import annotations

import json
import os
import time
import webbrowser
from datetime import datetime
from pathlib import Path

from apolo.publicacion import textos
from apolo.publicacion import youtube_oauth as oauth
from apolo.publicacion.paquete import PublicacionError
from apolo.publicacion.youtube_oauth import YoutubeError

RESULTADO = "youtube.json"
CATEGORIA = "28"  # Ciencia y tecnología
GRANO = 256 * 1024  # YouTube exige trozos múltiplos de 256 KiB (salvo el último)
TROZO = 32 * GRANO  # 8 MiB
REINTENTOS = 6
REINTENTABLES = {500, 502, 503, 504}
MAX_MINIATURA = 2 * 1024 * 1024
CUPO = {"quotaExceeded", "uploadLimitExceeded", "dailyLimitExceeded"}
MENSAJE_CUPO = ("Cupo diario de YouTube agotado: vuelve a intentarlo mañana (se reinicia a "
                "medianoche del Pacífico).")


class CupoAgotado(YoutubeError):
    """YouTube no acepta más por hoy (`quotaExceeded`/`uploadLimitExceeded`): no es una falla
    rara, es el cupo del proyecto de Google; mañana se sigue."""


def url_video(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


# ------------------------------------------------------------------ qué se sube
def leer_resultado(carpeta: Path) -> dict | None:
    try:
        datos = json.loads((Path(carpeta) / RESULTADO).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return datos if isinstance(datos, dict) and datos.get("video_id") else None


def datos(ficha: dict, tienda: str) -> dict:
    """{titulo, descripcion, etiquetas}: el bloque `youtube` de `ficha.json` tal cual (F2: el
    mismo texto que `youtube.txt` y que la cola de la tienda) o, en un paquete de antes, armado
    desde `ficha.json` (capítulos y música, los de su `video`; el enlace, el de la ficha o el
    derivado del slug). Con los límites de la tienda (`textos.problemas_youtube`)."""
    bloque = ficha.get("youtube")
    if isinstance(bloque, dict):
        d = {k: bloque.get(k) for k in ("titulo", "descripcion", "etiquetas")}
        problemas = textos.problemas_youtube(d)
        if problemas:
            raise PublicacionError("El bloque youtube de ficha.json no cumple los límites de "
                                   "YouTube:\n  - " + "\n  - ".join(problemas))
        return d
    video = ficha.get("video") or {}
    caps = [(int(c["inicio_s"]), c["titulo"]) for c in video.get("capitulos") or []]
    con_url = {**ficha, "url_tienda": ficha.get("url_tienda")
               or textos.url_maquina(tienda, ficha["slug"])}
    try:
        return textos.datos_youtube(con_url, caps, video.get("musica"), tienda=tienda)
    except ValueError as exc:  # no cumple los límites de YouTube
        raise PublicacionError(str(exc)) from None


def metadatos(d: dict, *, publico: bool) -> dict:
    """El cuerpo de `videos.insert` (part=snippet,status)."""
    return {"snippet": {"title": d["titulo"], "description": d["descripcion"],
                        "tags": d["etiquetas"], "categoryId": CATEGORIA,
                        "defaultLanguage": "es", "defaultAudioLanguage": "es"},
            "status": {"privacyStatus": "public" if publico else "private",
                       "selfDeclaredMadeForKids": False}}


def _rechazo(resp, que: str) -> YoutubeError:
    """El error de Google en su forma {error: {message, errors: [{reason}]}}."""
    try:
        err = resp.json().get("error") or {}
    except (ValueError, AttributeError):
        err = {}
    err = err if isinstance(err, dict) else {"message": str(err)}
    razones = [e.get("reason") for e in err.get("errors") or [] if isinstance(e, dict)]
    if CUPO & set(razones):
        return CupoAgotado(f"{MENSAJE_CUPO} ({', '.join(r for r in razones if r in CUPO)})")
    if resp.status_code == 401:
        return YoutubeError(f"Google no aceptó el permiso al {que}. {oauth.REAUTORIZAR}")
    detalle = str(err.get("message") or (resp.text or "").strip()[:300] or "(sin detalle)")
    return YoutubeError(f"YouTube rechazó {que} ({resp.status_code}"
                        + (f", {', '.join(r for r in razones if r)}" if any(razones) else "")
                        + f"): {detalle}")


def _recibido(resp) -> int:
    """Bytes que YouTube ya tiene, del `Range: bytes=0-N` de un 308 (sin Range, ninguno)."""
    rango = resp.headers.get("Range") or ""
    try:
        return int(rango.rsplit("-", 1)[1]) + 1
    except (IndexError, ValueError):
        return 0


# ------------------------------------------------------------------ el cliente
class _YouTube:
    def __init__(self, http, ext: oauth.Extremos, permiso: oauth.Permiso, eco, espera_s: float):
        import httpx

        self.http, self.ext, self.permiso, self.eco = http, ext, permiso, eco
        self.espera_s, self._httpx = espera_s, httpx

    def pedir(self, metodo: str, url: str, que: str, *, cabeceras=None, **kw):
        """Con el Bearer; un 401 renueva el access token una vez. Un corte de red sube como
        `httpx.HTTPError` (quien llama decide si reintenta)."""
        for intento in (0, 1):
            resp = self.http.request(metodo, url, headers={**self.permiso.cabeceras(),
                                                           **(cabeceras or {})}, **kw)
            if resp.status_code != 401 or intento:
                return resp
            self.permiso.renovar()
        return resp

    def _con_reintentos(self, metodo, url, que, **kw):
        for fallo in range(REINTENTOS + 1):
            try:
                resp = self.pedir(metodo, url, que, **kw)
                if resp.status_code not in REINTENTABLES:
                    return resp
                motivo = f"YouTube respondió {resp.status_code}"
            except self._httpx.HTTPError as exc:
                motivo = f"corte de red: {type(exc).__name__}"
            if fallo == REINTENTOS:
                raise YoutubeError(f"No pude {que} tras {REINTENTOS} reintentos ({motivo}). "
                                   "Vuelve a correr el comando.")
            self._esperar(fallo, motivo)
        raise AssertionError("inalcanzable")

    def _esperar(self, fallo: int, motivo: str) -> None:
        espera = min(self.espera_s * 2 ** fallo, 60.0)
        self.eco(f"  {motivo}: reintento en {espera:.0f} s")
        time.sleep(espera)

    def canal(self) -> dict:
        resp = self._con_reintentos("GET", f"{self.ext.api}/channels", "leer el canal",
                                    params={"part": "snippet", "mine": "true"})
        if resp.status_code >= 400:
            raise _rechazo(resp, "leer el canal")
        items = resp.json().get("items") or []
        if not items:
            raise YoutubeError("La cuenta autorizada no tiene canal de YouTube. "
                               + oauth.REAUTORIZAR)
        return {"id": items[0].get("id"), "titulo": (items[0].get("snippet") or {}).get("title")}

    def iniciar(self, cuerpo: dict, tamano: int) -> str:
        """La sesión reanudable: devuelve la dirección a la que se manda el archivo."""
        resp = self._con_reintentos(
            "POST", f"{self.ext.upload}/videos", "abrir la subida",
            params={"uploadType": "resumable", "part": "snippet,status"}, json=cuerpo,
            cabeceras={"X-Upload-Content-Type": "video/mp4",
                       "X-Upload-Content-Length": str(tamano)})
        if resp.status_code >= 400:
            raise _rechazo(resp, "abrir la subida")
        sesion = resp.headers.get("Location")
        if not sesion:
            raise YoutubeError(f"YouTube abrió la subida ({resp.status_code}) sin la dirección "
                               "de la sesión (Location).")
        return sesion

    def subir_archivo(self, sesion: str, ruta: Path, trozo: int) -> dict:
        """El archivo por trozos desde disco. Un corte o un 5xx pregunta cuánto llegó
        (`Content-Range: bytes */total` → 308 + Range) y sigue desde ahí."""
        total, hecho, fallos, preguntar = ruta.stat().st_size, 0, 0, False
        with open(ruta, "rb") as fh:
            while True:
                try:
                    if preguntar:
                        resp = self.pedir("PUT", sesion, "consultar la subida", content=b"",
                                          cabeceras={"Content-Range": f"bytes */{total}"})
                    else:
                        fh.seek(hecho)
                        datos_ = fh.read(trozo)
                        resp = self.pedir("PUT", sesion, "subir el video", content=datos_,
                                          cabeceras={"Content-Type": "video/mp4",
                                                     "Content-Range": f"bytes {hecho}-"
                                                     f"{hecho + len(datos_) - 1}/{total}"})
                    motivo = f"YouTube respondió {resp.status_code}"
                except self._httpx.HTTPError as exc:
                    resp, motivo = None, f"corte de red: {type(exc).__name__}"
                if resp is not None and resp.status_code in (200, 201):
                    self._avance(ruta, total, total)
                    return resp.json()
                if resp is not None and resp.status_code == 308:
                    hecho, preguntar, fallos = _recibido(resp), False, 0
                    self._avance(ruta, hecho, total)
                    if hecho < total:
                        continue
                    motivo = "YouTube tiene todo pero no cerró la subida"
                elif resp is not None and resp.status_code == 404:
                    raise YoutubeError("La sesión de subida venció (YouTube la guarda ~1 día): "
                                       "vuelve a correr el comando, empieza de cero.")
                elif resp is not None and resp.status_code not in REINTENTABLES:
                    raise _rechazo(resp, "subir el video")
                fallos += 1
                if fallos > REINTENTOS:
                    raise YoutubeError(f"La subida se cortó {REINTENTOS} veces seguidas "
                                       f"({motivo}); vuelve a correr el comando.")
                self._esperar(fallos - 1, motivo)
                preguntar = True

    def _avance(self, ruta: Path, hecho: int, total: int) -> None:
        self.eco(f"  {ruta.name}: {100 * hecho // max(total, 1)} % "
                 f"({hecho / 1e6:.1f} de {total / 1e6:.1f} MB)")

    def miniatura(self, video_id: str, ruta: Path) -> str | None:
        """Sube la miniatura; devuelve el aviso si no se pudo (el video ya está arriba)."""
        if not ruta.is_file():
            return f"no hay {ruta.name} en la carpeta"
        if ruta.stat().st_size > MAX_MINIATURA:
            return f"{ruta.name} pesa más de 2 MB (el tope de YouTube)"
        try:
            resp = self._con_reintentos(
                "POST", f"{self.ext.upload}/thumbnails/set", "subir la miniatura",
                params={"videoId": video_id}, content=ruta.read_bytes(),
                cabeceras={"Content-Type": "image/png"})
        except PublicacionError as exc:
            return str(exc)
        if resp.status_code >= 400:
            return str(_rechazo(resp, "subir la miniatura"))
        return None


# ------------------------------------------------------------------ el paso
def _escribir(carpeta: Path, resultado: dict) -> None:
    tmp = carpeta / f".{RESULTADO}.tmp"
    tmp.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, carpeta / RESULTADO)


def subir(carpeta, *, tienda: str, publico: bool = False, ensayo: bool = False,
          forzar: bool = False, reautorizar: bool = False, eco=print, cliente=None,
          abrir=webbrowser.open, entorno=None, espera_s: float = 2.0, trozo: int = TROZO,
          espera_navegador_s: float = oauth.ESPERA_NAVEGADOR_S) -> dict:
    """`publicar youtube`. `tienda`: la URL de la tienda (para el enlace derivado);
    `cliente`: un `httpx.Client` (por omisión, uno propio); `abrir`: cómo se abre el navegador
    (los tests simulan la vuelta). Devuelve lo de `youtube.json` más `nuevo` (False si ya
    estaba subido o es un ensayo)."""
    import httpx

    from apolo.publicacion.tienda import contenido

    eco = eco or (lambda *_a, **_k: None)
    if trozo <= 0 or trozo % GRANO:
        raise ValueError(f"el trozo debe ser múltiplo de {GRANO} bytes")
    carpeta = Path(carpeta)
    previo = leer_resultado(carpeta)
    if previo and not forzar and not ensayo:
        eco(f"Ya está en YouTube: {previo.get('url')} ({previo.get('privacidad')}, canal "
            f"«{previo.get('canal')}», {RESULTADO}). No lo vuelvo a subir; con --forzar se "
            "sube otra vez (y queda un video duplicado en el canal).")
        return {**previo, "nuevo": False}
    ficha, _ = contenido(carpeta)
    video = carpeta / ((ficha.get("video") or {}).get("archivo") or "video.mp4")
    if not video.is_file() or video.stat().st_size == 0:
        raise PublicacionError(f"No hay video en {video}: corre `publicar generar` primero.")
    d = datos(ficha, tienda)
    cuerpo = metadatos(d, publico=publico)

    dir_ = oauth.carpeta(entorno)
    cliente_oauth = oauth.leer_cliente(dir_)
    ext = oauth.extremos(cliente_oauth, entorno)
    http = cliente or httpx.Client(timeout=httpx.Timeout(120.0))
    try:
        p = oauth.permiso(http, dir_, ext, cliente_oauth, reautorizar=reautorizar, eco=eco,
                          abrir=abrir, espera_s=espera_navegador_s)
        yt = _YouTube(http, ext, p, eco, espera_s)
        canal = yt.canal()
        oauth.anotar_canal(dir_, canal)
        privacidad = cuerpo["status"]["privacyStatus"]
        if ensayo:
            eco(f"Canal: «{canal['titulo']}»\nTítulo: {d['titulo']}\nPrivacidad: {privacidad}\n"
                f"Etiquetas: {', '.join(d['etiquetas']) or '(ninguna)'}\nVideo: {video.name} "
                f"({video.stat().st_size / 1e6:.1f} MB)\nDescripción:\n{d['descripcion']}")
            if previo:
                eco(f"(Ya subido antes: {previo.get('url')}.)")
            eco("Ensayo: no subí nada.")
            return {"titulo": d["titulo"], "canal": canal["titulo"], "privacidad": privacidad,
                    "descripcion": d["descripcion"], "etiquetas": d["etiquetas"], "nuevo": False}
        eco(f"Subiendo al canal «{canal['titulo']}»: {d['titulo']} ({privacidad})")
        sesion = yt.iniciar(cuerpo, video.stat().st_size)
        subido = yt.subir_archivo(sesion, video, trozo)
        video_id = subido.get("id")
        if not video_id:
            raise YoutubeError(f"YouTube cerró la subida sin el id del video: {str(subido)[:300]}")
        aviso = yt.miniatura(video_id, carpeta / (ficha.get("miniatura") or "miniatura.png"))
    finally:
        if cliente is None:
            http.close()
    resultado = {"video_id": video_id, "url": url_video(video_id), "privacidad": privacidad,
                 "canal": canal["titulo"], "canal_id": canal["id"],
                 "subido_en": datetime.now().isoformat(timespec="seconds"),
                 "titulo": d["titulo"], "miniatura": aviso is None}
    _escribir(carpeta, resultado)
    if aviso:
        eco(f"Aviso: la miniatura no se subió ({aviso}). El video ya está en YouTube: súbela a "
            "mano en YouTube Studio.")
    eco(f"Subido: {resultado['url']}"
        + (" — PRIVADO (D4): pásalo a público en YouTube Studio cuando toque."
           if privacidad == "private" else " — público."))
    return {**resultado, "nuevo": True}
