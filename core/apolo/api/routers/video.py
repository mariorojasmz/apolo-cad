"""Rutas de la grabación del video desde el visor (plan video-realista, D4).

El navegador dibuja cada cuadro con su reloj virtual (D3) y lo sube; la API lo guarda en `data/` y
al cerrar lo codifica con `media/codificar.py` (el mismo ffmpeg, música y CRF que el video de la
tienda). Las sesiones y los cuadros son de `media/grabacion.py`.

Sin `STATE_LOCK`: es E/S pura y no lee el documento. El cierre corre en el pool de hilos de la API
(una ruta `def`) y puede tardar minutos con un video largo: quien espera puede consultar el
avance con `GET /api/video/grabacion/{sesion}`.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Request
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


class CerrarIn(BaseModel):
    #: Ruta de una pista de audio en esta máquina (la elige quien graba; nunca se descarga).
    musica: str | None = None
    #: Dónde dejar el MP4; por defecto, en la carpeta de la sesión.
    salida: str | None = None
    conservar_cuadros: bool = False


@router.post("/api/video/grabacion")
def abrir_grabacion(body: GrabacionIn | None = None) -> dict:
    """Abre una sesión de grabación: devuelve su id, lo que ocuparán los cuadros y el espacio
    libre (con `aviso` si es mucho; 507 si no caben)."""
    b = body or GrabacionIn()
    try:
        return GRABACIONES.abrir(ancho=b.ancho, alto=b.alto, fps=b.fps, formato=b.formato,
                                 cuadros=b.cuadros)
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.get("/api/video/grabacion/{sesion}")
def estado_grabacion(sesion: str) -> dict:
    """Estado de una sesión: abierta, codificando (con `codificados`), lista (con `informe`) o
    error (con `error`)."""
    try:
        return GRABACIONES.estado(sesion)
    except _ERRORES as exc:
        raise _http(exc) from exc


@router.delete("/api/video/grabacion/{sesion}")
def descartar_grabacion(sesion: str) -> dict:
    """Borra los cuadros de una sesión y la olvida (un video ya codificado queda)."""
    try:
        return GRABACIONES.descartar(sesion)
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
    borra los cuadros salvo `conservar_cuadros`. Si falta alguno, 400 con cuáles."""
    b = body or CerrarIn()
    try:
        return GRABACIONES.cerrar(sesion, musica=b.musica, salida=b.salida,
                                  conservar_cuadros=b.conservar_cuadros)
    except _ERRORES as exc:
        raise _http(exc) from exc
