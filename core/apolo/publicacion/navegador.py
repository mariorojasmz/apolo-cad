"""El video de la tienda grabado por el navegador que ya está instalado (plan video-realista, D7).

`publicar generar --render navegador`:
  1. busca Edge o Chrome (Edge viene con Windows; `APOLO_NAVEGADOR` apunta a otro ejecutable);
  2. arma el plan cuadro por cuadro del guion sobre su copia del documento
     (`plan_navegador.py`) y abre en la API una sesión de grabación con los dos
     (`POST /api/video/grabacion`), la música, la salida y si se conservan los cuadros;
  3. lanza el navegador SIN VENTANA y con la GPU contra `<url>/?grabar=<sesion>`, con un perfil
     TEMPORAL dentro de la carpeta de la sesión (nunca el de la persona) que se borra al final;
  4. espera a que la sesión quede «lista» (el navegador subió los cuadros y la API codificó) y
     arma la miniatura con la foto de la máquina terminada que subió el navegador.

Sin navegador, o si el navegador dibuja sin GPU (la sesión «fallida» con motivo «sin_gpu»), lanza
`NavegadorNoDisponible`: `flujo.generar` avisa y cae al respaldo VTK (D8). Cualquier otro fallo
es un error de verdad y sube como `PublicacionError`. Nada se descarga.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from apolo.publicacion.paquete import PublicacionError

#: Sin avance de la sesión por más que esto (s), el navegador se dio por colgado. Cubre la carga
#: de la escena (1 M de triángulos) y la simulación de la marcha antes del primer cuadro.
SIN_AVANCE_S = 300.0
ESPERA_S = 1.0
#: Banderas de Chromium: sin ventana (con la GPU: F0 lo midió sin banderas de GPU), sin primera
#: ejecución ni extensiones, y sin frenar los temporizadores ni el render de una página de fondo.
BANDERAS = ("--headless=new", "--no-first-run", "--no-default-browser-check",
            "--disable-extensions", "--disable-sync", "--mute-audio",
            "--window-size=1920,1080", "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows")


class NavegadorNoDisponible(Exception):
    """No hay con qué grabar en el navegador (no está, o dibuja sin GPU): se cae a VTK."""


def _candidatos() -> list[Path]:
    out: list[Path] = []
    if sys.platform == "win32":
        for var in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                out += [Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                        Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"]
    elif sys.platform == "darwin":
        out += [Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")]
    for nombre in ("msedge", "microsoft-edge", "microsoft-edge-stable", "google-chrome",
                   "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        ruta = shutil.which(nombre)
        if ruta:
            out.append(Path(ruta))
    return out


def buscar_navegador() -> Path | None:
    """Edge o Chrome instalados (en ese orden), o el de `APOLO_NAVEGADOR`; None si no hay."""
    propio = os.environ.get("APOLO_NAVEGADOR")
    if propio:
        return Path(propio) if Path(propio).is_file() else None
    return next((p for p in _candidatos() if p.is_file()), None)


def comando(ejecutable: Path, url: str, perfil: Path) -> list[str]:
    return [str(ejecutable), *BANDERAS, f"--user-data-dir={perfil}", url]


def lanzar(ejecutable: Path, url: str, perfil: Path) -> subprocess.Popen:
    """El navegador sin ventana; su salida se descarta (Chromium escribe ruido de GPU)."""
    return subprocess.Popen(comando(ejecutable, url, perfil), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)


def _cerrar_proceso(proc) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def _borrar_perfil(perfil: Path) -> None:
    """Chromium suelta sus archivos un rato después de salir: unos reintentos antes de rendirse."""
    for _ in range(20):
        shutil.rmtree(perfil, ignore_errors=True)
        if not perfil.exists():
            return
        time.sleep(0.5)


def _base(cliente) -> str:
    return str(getattr(cliente, "base_url", "")).rstrip("/")


def renderizar(cliente, doc, g: dict, carpeta, *, musica=None, conservar_cuadros: bool = False,
               progreso=None, lanzador=lanzar, url: str | None = None):
    """Graba el video del guion `g` (de montaje, validado contra `doc`, la copia privada del
    documento) en `carpeta/video.mp4` con la miniatura al lado. El plan cuadro por cuadro se
    arma aquí, sobre `doc` (D1 de publicacion-tienda). Devuelve un `video.InformeVideo`.
    `lanzador(ejecutable, url, perfil)` → un objeto con `poll()` (los tests simulan el
    navegador)."""
    from PIL import Image

    from apolo.media import tarjetas
    from apolo.publicacion.flujo import _Api
    from apolo.services.plan_navegador import PlanError, plan
    from apolo.publicacion.video import InformeVideo

    ejecutable = buscar_navegador()
    if ejecutable is None:
        raise NavegadorNoDisponible("No encontré Edge ni Chrome instalados (ni APOLO_NAVEGADOR).")
    api = _Api(cliente)
    try:
        p = plan(doc, g, api.salud().get("project_id"))
    except PlanError as exc:
        raise PublicacionError(str(exc)) from exc
    carpeta = Path(carpeta)
    salida = carpeta / "video.mp4"
    t0 = time.perf_counter()
    sesion = api._pedir("POST", "/api/video/grabacion", "abrir la grabación", json={
        "guion": g, "plan": p, "musica": str(musica) if musica else None, "salida": str(salida),
        "conservar_cuadros": conservar_cuadros}).json()
    sid = sesion["sesion"]
    propia = Path(sesion.get("carpeta") or "")
    perfil = (propia / "navegador") if propia.is_dir() else Path(tempfile.mkdtemp(prefix="apolo-nav-"))
    proc = None
    try:
        proc = lanzador(ejecutable, f"{(url or _base(cliente))}/?grabar={sid}", perfil)
        estado = _esperar(api, sid, proc, progreso)
        foto = api._pedir("GET", f"/api/video/grabacion/{sid}/foto", "bajar la foto de la máquina")
        mini = tarjetas.miniatura(g, Image.open(io.BytesIO(foto.content)).convert("RGB"),
                                  carpeta / "miniatura.png")
    except BaseException:
        _cerrar_proceso(proc)
        _borrar_perfil(perfil)
        try:  # los cuadros se quedan si falló al codificar (la sesión en «error»): se borran igual
            cliente.request("DELETE", f"/api/video/grabacion/{sid}")
        except Exception:  # noqa: BLE001 — limpieza best-effort
            pass
        raise
    _cerrar_proceso(proc)
    _borrar_perfil(perfil)
    if not conservar_cuadros:
        cliente.request("DELETE", f"/api/video/grabacion/{sid}")
    inf = estado["informe"]
    return InformeVideo(Path(inf["video"]), mini, inf["cuadros"], inf["duracion_s"],
                        time.perf_counter() - t0, bool(inf["con_musica"]))


def _esperar(api, sid: str, proc, progreso) -> dict:
    """Hasta que la sesión quede lista; falla si queda fallida, si el navegador se cierra antes
    o si no avanza en `SIN_AVANCE_S`."""
    ultimo, desde = None, time.perf_counter()
    while True:
        e = api._pedir("GET", f"/api/video/grabacion/{sid}", "leer la grabación").json()
        if e["estado"] == "lista":
            return e
        if e["estado"] == "fallida":
            if e.get("motivo") == "sin_gpu":
                raise NavegadorNoDisponible(e.get("error") or "El navegador dibuja sin GPU.")
            raise PublicacionError(f"El navegador no pudo grabar el video: {e.get('error')}")
        if e["estado"] == "error":
            raise PublicacionError(f"La API no pudo codificar el video: {e.get('error')}")
        avance = (e["recibidos"], e["codificados"], e["estado"])
        if avance != ultimo:
            ultimo, desde = avance, time.perf_counter()
            if progreso is not None:
                progreso(e["recibidos"], e["cuadros"] or 0)
        elif time.perf_counter() - desde > SIN_AVANCE_S:
            raise PublicacionError(f"El navegador lleva {SIN_AVANCE_S:.0f} s sin subir cuadros: "
                                   "lo doy por colgado.")
        if proc is not None and proc.poll() is not None and e["estado"] == "abierta":
            raise PublicacionError("El navegador se cerró antes de terminar el video "
                                   f"({e['recibidos']} de {e['cuadros']} cuadros).")
        time.sleep(ESPERA_S)
