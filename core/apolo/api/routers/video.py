"""Rutas de la grabación del video desde el visor (plan video-realista, D4 y D5).

El navegador dibuja cada cuadro con su reloj virtual (D3) y lo sube; la API lo guarda en `data/` y
al cerrar lo codifica con `media/codificar.py` (el mismo ffmpeg, música y CRF que el video de la
tienda). Las sesiones y los cuadros son de `media/grabacion.py`.

Con GUION (F3, D5): una sesión abierta con `guion` + `plan` (el plan cuadro por cuadro de
`publicacion/plan_navegador.py`, armado por quien abre: el CLI sobre su copia del documento, el
botón «Grabar video» con `POST /api/video/guion`, de `video_guion.py`) los guarda para el
navegador, que lee `…/{sesion}/plan`. Las tarjetas y los rótulos salen de `…/tarjeta/{parte}` y
`…/rotulo/{etapa}`, dibujados con las mismas funciones que el video de VTK.

Sin `STATE_LOCK` ni documento: es E/S pura (lo que lee la escena vive en `video_guion.py`). El
cierre corre en el pool de hilos de la API (una ruta `def`) y puede tardar minutos con un video
largo: quien espera puede consultar el avance con `GET /api/video/grabacion/{sesion}`.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from apolo import paths
from apolo.media import grabacion as g
from apolo.media.codificar import ErrorCodificacion, FfmpegNoEncontrado

router = APIRouter()

#: Las sesiones del proceso. Un test la reemplaza por una con su carpeta temporal.
GRABACIONES = g.Grabaciones(paths.grabaciones_dir)

_CODIGOS = [(g.SesionNoEncontrada, 404), (g.Conflicto, 409), (g.EspacioInsuficiente, 507),
            (g.ParametrosInvalidos, 400), (FfmpegNoEncontrado, 503), (ErrorCodificacion, 500)]


def _http(exc: Exception) -> HTTPException:
    codigo = next(c for tipo, c in _CODIGOS if isinstance(exc, tipo))
    return HTTPException(codigo, str(exc))


_ERRORES = tuple(t for t, _ in _CODIGOS)


class GrabacionIn(BaseModel):
    ancho: int = 1920
    alto: int = 1080
    fps: int = 30
    formato: Literal["jpeg", "png"] = "jpeg"
    #: Cuántos cuadros tendrá el video (estima el disco y detecta los que falten al cerrar).
    cuadros: int | None = None
    #: El guion a reproducir (F3) y su plan cuadro por cuadro (`plan_navegador.plan`): el plan
    #: fija tamaño, fps y cuadros; el navegador lo lee y la API dibuja las tarjetas del guion.
    guion: dict | None = None
    plan: dict | None = None
    #: Lo que hará `cerrar` si el navegador no dice otra cosa (lo fija quien abre).
    musica: str | None = None
    salida: str | None = None
    conservar_cuadros: bool | None = None


class CerrarIn(BaseModel):
    #: Ruta de una pista de audio en esta máquina (la elige quien graba; nunca se descarga).
    musica: str | None = None
    #: Dónde dejar el MP4; por defecto, lo que fijó quien abrió o la carpeta de la sesión.
    salida: str | None = None
    conservar_cuadros: bool | None = None


class FalloIn(BaseModel):
    mensaje: str
    motivo: Literal["sin_gpu", "error"] = "error"


def _medidas_del_plan(guion: dict | None, plan: dict | None) -> tuple[int, int, int, int]:
    """(ancho, alto, fps, cuadros) de un plan bien formado; 400 si no lo es."""
    try:
        if not isinstance(guion, dict) or not isinstance(plan, dict):
            raise TypeError
        v, n = plan["video"], plan["cuadros"]
        medidas = (int(v["ancho"]), int(v["alto"]), int(v["fps"]), int(n))
        if len(plan["cuadro"]["az"]) != n or plan["tramos"][-1]["fin"] != n:
            raise ValueError
    except (TypeError, KeyError, IndexError, ValueError):
        raise HTTPException(400, "Una grabación con guion lleva el guion y su plan completo "
                                 "(`publicacion/plan_navegador.py`): ármalo de nuevo.") from None
    return medidas


@router.post("/api/video/grabacion")
def abrir_grabacion(body: GrabacionIn | None = None) -> dict:
    """Abre una sesión de grabación: devuelve su id, lo que ocuparán los cuadros y el espacio
    libre (con `aviso` si es mucho; 507 si no caben). Con `guion` + `plan`, el tamaño, los fps
    y los cuadros salen del plan y la sesión lo guarda para el navegador."""
    b = body or GrabacionIn()
    ancho, alto, fps, cuadros = b.ancho, b.alto, b.fps, b.cuadros
    if b.guion is not None or b.plan is not None:
        ancho, alto, fps, cuadros = _medidas_del_plan(b.guion, b.plan)
    try:
        return GRABACIONES.abrir(ancho=ancho, alto=alto, fps=fps, formato=b.formato,
                                 cuadros=cuadros, guion=b.guion, plan=b.plan,
                                 al_cerrar={"musica": b.musica, "salida": b.salida,
                                            "conservar_cuadros": b.conservar_cuadros})
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.get("/api/video/grabacion/{sesion}")
def estado_grabacion(sesion: str) -> dict:
    """Estado de una sesión: abierta, codificando (con `codificados`), lista (con `informe`),
    error (con `error`) o fallida (el navegador no pudo: `error` y `motivo`)."""
    try:
        return GRABACIONES.estado(sesion)
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.delete("/api/video/grabacion/{sesion}")
def descartar_grabacion(sesion: str) -> dict:
    """Borra los cuadros y la foto de una sesión y la olvida (un video ya codificado queda)."""
    try:
        return GRABACIONES.descartar(sesion)
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.get("/api/video/grabacion/{sesion}/plan")
def plan_grabacion(sesion: str) -> dict:
    """El plan cuadro por cuadro del guion de la sesión (`publicacion/plan_navegador.py`)."""
    try:
        return GRABACIONES.plan(sesion)
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.post("/api/video/grabacion/{sesion}/foto")
async def subir_foto(sesion: str, request: Request) -> dict:
    """La foto de la máquina terminada (PNG o JPEG del tamaño del video): fondo de la portada y
    de la miniatura de YouTube."""
    datos = await request.body()
    try:
        return await run_in_threadpool(GRABACIONES.guardar_foto, sesion, datos)
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.get("/api/video/grabacion/{sesion}/foto")
def bajar_foto(sesion: str) -> Response:
    try:
        ruta = GRABACIONES.foto(sesion)
    except _ERRORES as exc:
        raise _http(exc) from exc
    if ruta is None or not ruta.is_file():
        raise HTTPException(404, "El navegador todavía no subió la foto de la máquina.")
    tipo = "image/png" if ruta.suffix == ".png" else "image/jpeg"
    return Response(ruta.read_bytes(), media_type=tipo)


def _png(fn, sesion: str, *args) -> Response:
    from apolo.media.tarjetas import TarjetaError

    try:
        guion, ancho, alto = GRABACIONES.guion(sesion)
        return Response(fn(guion, *args, ancho, alto), media_type="image/png")
    except _ERRORES as exc:
        raise _http(exc) from exc
    except TarjetaError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/api/video/grabacion/{sesion}/tarjeta/{parte}")
def tarjeta_grabacion(sesion: str, parte: str) -> Response:
    """La tarjeta `parte` (portada, cifras o cierre) del guion, del tamaño del video, en PNG. La
    portada va sobre la foto que subió el navegador."""
    from PIL import Image

    from apolo.media import tarjetas

    try:
        ruta = GRABACIONES.foto(sesion) if parte == "portada" else None
    except _ERRORES as exc:
        raise _http(exc) from exc
    foto = Image.open(ruta).convert("RGB") if ruta is not None and ruta.is_file() else None
    return _png(lambda gn, a, h: tarjetas.tarjeta(gn, parte, a, h, foto), sesion)


@router.get("/api/video/grabacion/{sesion}/rotulo/{etapa}")
def rotulo_grabacion(sesion: str, etapa: int) -> Response:
    """El rótulo de la etapa como capa PNG transparente del tamaño del video (contraste ≥ 4.5:1
    sobre cualquier cuadro)."""
    from apolo.media import tarjetas

    return _png(lambda gn, a, h: tarjetas.rotulo(gn, etapa, a, h), sesion)


@router.post("/api/video/grabacion/{sesion}/fallo")
def fallo_grabacion(sesion: str, body: FalloIn) -> dict:
    """El navegador no pudo grabar: la sesión queda «fallida» con su motivo para quien espera."""
    try:
        return GRABACIONES.fallar(sesion, body.mensaje, body.motivo)
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.post("/api/video/grabacion/{sesion}/cuadro/{n}")
async def subir_cuadro(sesion: str, n: int, request: Request) -> dict:
    """Sube el cuadro `n` (desde 0): el cuerpo es el PNG o el JPEG crudo, del tamaño de la
    sesión. Pueden llegar desordenados; uno repetido da 409."""
    datos = await request.body()
    try:
        return await run_in_threadpool(GRABACIONES.guardar_cuadro, sesion, n, datos)
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.post("/api/video/grabacion/{sesion}/cerrar")
def cerrar_grabacion(sesion: str, body: CerrarIn | None = None) -> dict:
    """Codifica los cuadros 0…N−1 en un MP4 (H.264, BT.709, CRF 18), con la música si se pide, y
    borra los cuadros salvo `conservar_cuadros`. Si falta alguno, 400 con cuáles. Lo que no se
    pasa sale de lo que fijó quien abrió la sesión."""
    b = body or CerrarIn()
    try:
        return GRABACIONES.cerrar(sesion, musica=b.musica, salida=b.salida,
                                  conservar_cuadros=b.conservar_cuadros)
    except _ERRORES as exc:
        raise _http(exc) from exc
