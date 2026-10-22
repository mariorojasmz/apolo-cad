"""`publicar youtube --cola`: el subidor de YouTube vacía la cola que vive en la tienda (plan
fabrica-de-publicaciones, F3 · D5; el contrato HTTP, en la bitácora «T» del plan).

Corre en UNA sola PC (el cupo de YouTube es uno por proyecto de Google), a mano o como tarea
diaria (`tarea_cola`). Con la llave de publicación (`APOLO_TIENDA_LLAVE`, el `Cliente` de
`tienda.py`: Bearer, errores, la llave nunca entera):

  1. pide la cola (`GET /api/maquina/youtube/cola`), de la más antigua;
  2. por cada máquina: si ya se subió (el registro local de subidas, por sha256 del video, o
     una carpeta local del mismo slug con `youtube.json` y el mismo video) avisa `subido` con
     ese id sin volver a subir; si no, la reserva (`POST …/reserva`: 409 = otro la tomó, se
     salta), baja video y miniatura a una carpeta temporal, verifica bytes y sha256, la sube
     con el cliente de F1 con los textos que da la tienda TAL CUAL (no los recalcula) y avisa
     `PUT …/youtube` con `subido`, `fallo` (error corto) o `cupo`;
  3. `CupoAgotado` avisa `cupo` a ESA máquina (vuelve a pendiente sin gastar intento) y PARA el
     lote: las demás quedan como estaban.

Cada video subido se anota ANTES de avisar a la tienda en `subidas.json` (carpeta de las
credenciales de YouTube): si la tienda no respondiera, la próxima corrida avisa `subido` en vez
de duplicar el video en el canal. Los temporales se borran siempre.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import webbrowser
from datetime import datetime
from pathlib import Path

from apolo.publicacion import youtube as yt
from apolo.publicacion import youtube_oauth as oauth
from apolo.publicacion.paquete import FICHA_JSON, PublicacionError
from apolo.publicacion.tienda import Cliente, TiendaError, prefijo, sha256
from apolo.publicacion.youtube import CupoAgotado
from apolo.publicacion.youtube_oauth import SinAutorizacion

SUBIDAS = "subidas.json"
LIMITE_MAX = 20  # el tope del GET de la tienda
ERROR_MAX = 300


def _corto(exc: Exception, llave: str) -> str:
    """El error para la tienda: la primera línea, corta, sin la llave."""
    texto = (str(exc).strip().splitlines() or [type(exc).__name__])[0]
    return texto.replace(llave, prefijo(llave))[:ERROR_MAX]


# ------------------------------------------------------------------ ya subidas
def _leer_subidas(dir_: Path) -> dict:
    try:
        datos = json.loads((dir_ / SUBIDAS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return datos if isinstance(datos, dict) else {}


def _anotar_subida(dir_: Path, clave: str, slug: str, resultado: dict) -> None:
    datos = _leer_subidas(dir_)
    datos[clave] = {"slug": slug, **{k: resultado[k] for k in ("video_id", "url", "privacidad")},
                    "subido_en": resultado.get("subido_en")}
    dir_.mkdir(parents=True, exist_ok=True)
    tmp = dir_ / f".{SUBIDAS}.tmp"
    tmp.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, dir_ / SUBIDAS)


def _sha_local(carpeta: Path) -> str | None:
    """El sha256 del video de un paquete local: el de `ficha.json` o, si no lo trae, el archivo."""
    try:
        ficha = json.loads((carpeta / FICHA_JSON).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    nombre = (ficha.get("video") or {}).get("archivo") or "video.mp4"
    for a in ficha.get("archivos") or []:
        if isinstance(a, dict) and a.get("nombre") == nombre and a.get("sha256"):
            return a["sha256"]
    return sha256(carpeta / nombre) if (carpeta / nombre).is_file() else None


def carpetas_locales(raiz, slug: str) -> list[Path]:
    """Las versiones locales de `slug`, de la última a la primera."""
    from apolo.publicacion.paquete import carpeta_version, versiones

    return [carpeta_version(raiz, slug, v) for v in reversed(versiones(raiz, slug))]


def ya_subido(m: dict, raiz, dir_: Path) -> tuple[dict | None, str]:
    """(lo subido {video_id, url, privacidad}, de dónde) si esta máquina ya está en YouTube: por
    el sha256 del video en el registro de subidas o en una carpeta local con `youtube.json` (el
    mismo video; sin sha256 de la tienda, basta el slug)."""
    sha = (m.get("video") or {}).get("sha256")
    previo = _leer_subidas(dir_).get(sha) if sha else None
    if previo and previo.get("video_id"):
        return previo, f"{dir_ / SUBIDAS}"
    if raiz is None:
        return None, ""
    for carpeta in carpetas_locales(raiz, m["slug"]):
        r = yt.leer_resultado(carpeta)
        if r and (not sha or _sha_local(carpeta) == sha):
            return r, str(carpeta / yt.RESULTADO)
    return None, ""


# ------------------------------------------------------------------ una máquina
def _bajar(t: Cliente, m: dict, temporal: Path) -> tuple[Path, Path | None]:
    """Video (verificado: bytes y sha256) y miniatura (bytes) a `temporal`. Una miniatura que
    no baja no frena: el video sube sin ella y se avisa."""
    v = m.get("video") or {}
    if not v.get("url"):
        raise PublicacionError("la tienda no dio la dirección del video")
    video = t.bajar(v["url"], temporal / "video.mp4", "bajar el video")
    if v.get("bytes") is not None and video.stat().st_size != int(v["bytes"]):
        raise PublicacionError(f"el video bajado pesa {video.stat().st_size} bytes y la tienda "
                               f"dice {v['bytes']}")
    if v.get("sha256") and sha256(video) != v["sha256"]:
        raise PublicacionError("el sha256 del video bajado no coincide con el de la tienda")
    mini = m.get("miniatura") or {}
    if not mini.get("url"):
        return video, None
    try:
        ruta = t.bajar(mini["url"], temporal / "miniatura.png", "bajar la miniatura")
    except TiendaError as exc:
        t.eco(f"  Aviso: {exc} — subo el video sin miniatura.")
        return video, None
    if mini.get("bytes") is not None and ruta.stat().st_size != int(mini["bytes"]):
        t.eco("  Aviso: la miniatura bajada no pesa lo que dice la tienda — subo sin ella.")
        return video, None
    return video, ruta


def _avisar(t: Cliente, m: dict, cuerpo: dict) -> None:
    t.api("PUT", f"/api/maquina/{m['id']}/youtube",
          f"anotar en la tienda «{cuerpo['resultado']}» de {m['slug']}", cuerpo)


def _subido(r: dict) -> dict:
    return {"resultado": "subido", "video_id": r["video_id"], "url": r["url"],
            "privacidad": r["privacidad"]}


# ------------------------------------------------------------------ el lote
class _YouTubePerezoso:
    """El permiso y el canal se piden con el PRIMER video que hay que subir (una cola de
    máquinas ya subidas o reservadas por otro no toca Google)."""

    def __init__(self, http, kw: dict, interactivo: bool, eco):
        self.http, self.kw, self.interactivo, self.eco = http, kw, interactivo, eco
        self.yt = self.canal = None

    def __call__(self):
        if self.yt is None:
            dir_ = oauth.carpeta(self.kw.get("entorno"))
            if not self.interactivo and oauth.leer_token(dir_) is None:
                raise SinAutorizacion(
                    "No hay permiso de YouTube guardado y la tarea programada no puede abrir el "
                    "navegador: corre una vez en una consola `publicar youtube --cola --ensayo` "
                    "y elige el canal «Apolo CAD».")
            self.yt, self.canal = yt.conectar(self.http, eco=self.eco, **self.kw)
        return self.yt, self.canal


def vaciar(*, tienda: str, llave: str, limite: int | None = None, publico: bool = False,
           ensayo: bool = False, reautorizar: bool = False, interactivo: bool = True,
           raiz=None, eco=print, cliente_tienda=None, cliente_youtube=None,
           abrir=webbrowser.open, entorno=None, espera_s: float = 2.0, trozo: int = yt.TROZO,
           espera_navegador_s: float = oauth.ESPERA_NAVEGADOR_S) -> dict:
    """Vacía la cola de la tienda hasta `limite` máquinas (por omisión, lo que da la tienda: 6) o
    hasta agotar el cupo. `raiz`: la carpeta de publicaciones de esta PC (para no resubir lo que
    ya subió `publicar youtube`). `ensayo`: lista la cola y el canal (autoriza la primera vez)
    sin reservar ni subir. `interactivo=False` (la tarea programada): sin permiso guardado,
    falla en vez de abrir el navegador. Devuelve {subidas, ya_subidas, saltadas, fallidas,
    cupo, quedan}."""
    import httpx

    eco = eco or (lambda *_a, **_k: None)
    if limite is not None and not 1 <= limite <= LIMITE_MAX:
        raise PublicacionError(f"--limite va de 1 a {LIMITE_MAX} (llegó {limite}).")
    dir_ = oauth.carpeta(entorno)
    t = Cliente(tienda, llave, cliente=cliente_tienda, eco=eco, espera_s=espera_s)
    http = cliente_youtube or httpx.Client(timeout=httpx.Timeout(120.0))
    conexion = _YouTubePerezoso(http, {"reautorizar": reautorizar, "abrir": abrir,
                                       "entorno": entorno, "espera_s": espera_s,
                                       "espera_navegador_s": espera_navegador_s},
                                interactivo, eco)
    r = {"subidas": [], "ya_subidas": [], "saltadas": [], "fallidas": [], "cupo": False,
         "quedan": None}
    try:
        consulta = "" if limite is None else f"?limite={limite}"
        cola = t.api("GET", f"/api/maquina/youtube/cola{consulta}", "pedir la cola de YouTube",
                     None).get("maquinas") or []
        eco(f"Cola de YouTube en {tienda}: {len(cola)} máquina(s) esperando"
            + (f" (pedí hasta {limite})." if limite else "."))
        if ensayo:
            _, canal = conexion()
            eco(f"Canal: «{canal['titulo']}»")
            for m in cola:
                eco(f"  {m['slug']} — «{m.get('titulo')}» ({m.get('estado')}, "
                    f"{m.get('intentos', 0)} intento(s), "
                    f"{(m.get('video') or {}).get('bytes', 0) / 1e6:.1f} MB)")
            eco("Ensayo: no reservé ni subí nada.")
            r["quedan"] = len(cola)
            return r
        for m in cola:
            if _una(t, m, conexion, r, raiz=raiz, dir_=dir_, publico=publico, trozo=trozo,
                    llave=llave, eco=eco):
                break
        r["quedan"] = len(t.api("GET", f"/api/maquina/youtube/cola?limite={LIMITE_MAX}",
                                "pedir la cola de YouTube", None).get("maquinas") or [])
    finally:
        t.cerrar()
        if cliente_youtube is None:
            http.close()
    _resumen(r, eco)
    return r


def _una(t: Cliente, m: dict, conexion, r: dict, *, raiz, dir_: Path, publico: bool,
         trozo: int, llave: str, eco) -> bool:
    """Una máquina de la cola. Devuelve True si hay que parar el lote (cupo agotado)."""
    slug = m["slug"]
    previo, donde = ya_subido(m, raiz, dir_)
    if previo is None:
        try:
            conexion()  # sin permiso de YouTube (o sin cupo para leer el canal), nada se reserva
        except CupoAgotado:
            eco(f"{yt.MENSAJE_CUPO} No reservo nada más.")
            r["cupo"] = True
            return True
    try:
        t.api("POST", f"/api/maquina/{m['id']}/youtube/reserva", f"reservar {slug}", None)
    except TiendaError as exc:
        if exc.status != 409:
            raise
        eco(f"- {slug}: otra PC la tomó o ya no está disponible (409): la salto.")
        r["saltadas"].append(slug)
        return False
    if previo is not None:
        eco(f"- {slug}: ya estaba en YouTube ({previo['url']}, según {donde}): aviso a la tienda "
            "sin volver a subirla.")
        _avisar(t, m, _subido(previo))
        r["ya_subidas"].append({"slug": slug, **_subido(previo)})
        return False
    eco(f"- {slug}: «{m.get('titulo')}»")
    temporal = Path(tempfile.mkdtemp(prefix="apolo-cola-"))
    try:
        try:
            video, miniatura = _bajar(t, m, temporal)
            d = m.get("youtube") or {}
            if not all(d.get(k) is not None for k in ("titulo", "descripcion", "etiquetas")):
                raise PublicacionError("la tienda no dio los textos de YouTube de la máquina")
            cliente, canal = conexion()
            resultado, aviso = yt.subir_video(cliente, canal, video, miniatura, d,
                                              publico=publico, trozo=trozo)
        except CupoAgotado:
            eco(f"  {yt.MENSAJE_CUPO} Aviso «cupo» a la tienda y paro el lote: las demás siguen "
                "en la cola.")
            _avisar(t, m, {"resultado": "cupo"})
            r["cupo"] = True
            return True
        except SinAutorizacion:
            _avisar(t, m, {"resultado": "cupo"})  # vuelve a pendiente sin gastar un intento
            raise
        except PublicacionError as exc:
            error = _corto(exc, llave)
            eco(f"  Falló: {error}")
            _avisar(t, m, {"resultado": "fallo", "error": error})
            r["fallidas"].append({"slug": slug, "error": error})
            return False
        clave = (m.get("video") or {}).get("sha256") or f"maquina-{m['id']}"
        _anotar_subida(dir_, clave, slug, resultado)  # antes de avisar: nunca un duplicado
        yt.avisar_subido(eco, resultado, aviso)
        _avisar(t, m, _subido(resultado))
        r["subidas"].append({"slug": slug, **_subido(resultado)})
        return False
    finally:
        shutil.rmtree(temporal, ignore_errors=True)


def _resumen(r: dict, eco) -> None:
    quedan = r["quedan"]
    eco(f"\nCola de YouTube ({datetime.now():%Y-%m-%d %H:%M}): {len(r['subidas'])} subida(s), "
        f"{len(r['ya_subidas'])} ya estaban, {len(r['saltadas'])} saltada(s), "
        f"{len(r['fallidas'])} fallida(s).")
    for s in r["subidas"]:
        eco(f"  {s['slug']}: {s['url']} ({s['privacidad']})")
    for f in r["fallidas"]:
        eco(f"  {f['slug']}: FALLÓ — {f['error']}")
    if r["cupo"]:
        eco("  Cupo diario de YouTube agotado: el resto sigue mañana (tarea diaria).")
    if quedan is not None:
        eco(f"Quedan en la cola: {quedan}{' o más' if quedan >= LIMITE_MAX else ''}.")
    privadas = [s for s in r["subidas"] if s["privacidad"] == "private"]
    if privadas:
        eco(f"Mario: {len(privadas)} video(s) PRIVADO(s) esperan tu clic en YouTube Studio "
            "para pasar a públicos (D4: hasta la auditoría).")
